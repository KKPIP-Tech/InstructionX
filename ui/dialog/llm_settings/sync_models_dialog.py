# ui/dialog/llm_settings/sync_models_dialog.py
"""模型同步对话框

将远端模型列表（FetchModelsWorker 强制刷新，不阻塞 UI）与**打开对话框时**
的本地合并列表对比，按「新增 / 已存在 / 已失效」三区分组展示：

- 新增：远端有而本地合并列表无（绿标，勾选后可批量写入 custom_models）；
- 已存在：两边都有（灰标，勾选框禁用，仅展示）；
- 已失效：本地 custom_models 有但远端已无（红标，勾选后可批量清理）。

「添加」/「清理」操作一次落盘（经 get_llm_config()）并中文提示结果条数；
新增条目以远端 ModelInfo.to_dict() 为基础经 normalize_model_entry 补全。

特例：预设目录型提供商（catalog preset 的 models_endpoint_path 为空，如
MiniMax）无远端模型列表 API，打开时提示「无需同步」并禁用操作；远端拉取
失败时中文提示原因，降级为仅展示本地列表并禁用操作。
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from core.llm.catalog import PRESET_MODELS, get_provider_preset
from core.llm.config import ProviderConfig, get_llm_config
from core.llm.provider_interface import ModelInfo
from core.llm.model_schema import normalize_model_entry
from utils.logging_tools import LoggerManager, get_name

from . import theme as _theme_module
from .constants import (
    FORM_BUTTON_HEIGHT, MODEL_ROW_HEIGHT, MODEL_ROW_MARGIN_LEFT,
    MODEL_ROW_MARGIN_RIGHT, MODEL_ROW_SPACING, SEARCH_EDIT_HEIGHT,
    SUB_DIALOG_MARGIN, SUB_DIALOG_SPACING, SYNC_DIALOG_HEIGHT,
    SYNC_DIALOG_WIDTH, WORKER_STOP_WAIT_MS,
)
from .theme import apply_dialog_theme
from .feedback import info as _info_toast
from .feedback import success as _success_toast
from .widgets import install_focus_halo, make_badge
from .workers import FetchModelsWorker

_logger = LoggerManager()

# 分组键：新增 / 已存在 / 已失效
_GROUP_NEW = "new"
_GROUP_EXISTING = "existing"
_GROUP_INVALID = "invalid"

# 分组键 -> 中文徽章文案
_GROUP_LABELS: Dict[str, str] = {
    _GROUP_NEW: "新增",
    _GROUP_EXISTING: "已存在",
    _GROUP_INVALID: "已失效",
}


class _SyncRow(QWidget):
    """同步列表单行：勾选框 + 模型 id + 状态徽章（新增/已存在/已失效）

    新增行默认勾选、已失效行默认不勾选、已存在行勾选框禁用（仅展示）。
    """

    def __init__(
        self,
        model_id: str,
        group: str,
        checkable: bool,
        checked: bool = False,
        parent: Optional[QWidget] = None,
    ):
        """构造同步行

        Args:
            model_id: 模型 id
            group: 分组键（_GROUP_NEW / _GROUP_EXISTING / _GROUP_INVALID）
            checkable: 勾选框是否可用
            checked: 勾选框初始态
            parent: 父控件
        """
        super().__init__(parent)
        self.setFixedHeight(MODEL_ROW_HEIGHT)
        self.model_id = model_id
        self.group = group
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            MODEL_ROW_MARGIN_LEFT, 0, MODEL_ROW_MARGIN_RIGHT, 0)
        layout.setSpacing(MODEL_ROW_SPACING)
        self.checkbox = QCheckBox(self)
        self.checkbox.setEnabled(checkable)
        self.checkbox.setChecked(checked)
        layout.addWidget(self.checkbox)
        id_label = QLabel(model_id, self)
        id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(id_label, 1)
        t = _theme_module.current_theme()
        color = {_GROUP_NEW: t.success, _GROUP_EXISTING: t.fg_muted,
                 _GROUP_INVALID: t.danger}[group]
        layout.addWidget(make_badge(_GROUP_LABELS[group], color))

    def is_checked(self) -> bool:
        """该行是否被勾选（仅新增/已失效行可选）"""
        return self.checkbox.isEnabled() and self.checkbox.isChecked()


class SyncModelsDialog(QDialog):
    """模型同步对话框（远端列表 ↔ 本地合并列表对比管理）

    Attributes:
        changed: 本次会话是否发生过落盘变更（供调用方决定是否重渲染）

    Signals:
        sig_models_changed(): 模型配置发生变更（已落盘）
    """

    sig_models_changed = Signal()

    def __init__(
        self,
        instance_id: str,
        current_entries: List[Dict[str, Any]],
        parent: Optional[QWidget] = None,
    ):
        """构造同步对话框（构建 UI、换肤并自动开始对比流程）

        Args:
            instance_id: 提供商实例 id
            current_entries: 打开时的本地合并列表（未 hidden 的统一 schema
                条目，作为「已存在 / 新增」对比基准）
            parent: 父控件
        """
        super().__init__(parent)
        self.setWindowTitle("模型同步")
        self.setModal(True)
        self.resize(SYNC_DIALOG_WIDTH, SYNC_DIALOG_HEIGHT)
        self._instance_id = instance_id
        self._local_by_id: Dict[str, Dict[str, Any]] = {
            str(e.get("id")): e for e in current_entries if e.get("id")}
        self._remote_by_id: Dict[str, ModelInfo] = {}
        self._invalid_entries: List[Dict[str, Any]] = []
        self._fetch_worker: Optional[FetchModelsWorker] = None
        self._sync_ready = False
        self.changed = False
        self._rows: List[_SyncRow] = []
        self._groups: List[Tuple[QLabel, List[_SyncRow]]] = []
        self._init_ui()
        apply_dialog_theme(self)
        install_focus_halo(self)
        self._start()

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建提示条 + 搜索框 + 状态行 + 分组列表 + 底部按钮"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SUB_DIALOG_MARGIN, SUB_DIALOG_MARGIN,
            SUB_DIALOG_MARGIN, SUB_DIALOG_MARGIN)
        layout.setSpacing(SUB_DIALOG_SPACING)
        self._hint = QLabel("", self)
        self._hint.setWordWrap(True)
        self._hint.setVisible(False)
        layout.addWidget(self._hint)
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("搜索模型 id")
        self._search.setClearButtonEnabled(True)
        self._search.setFixedHeight(SEARCH_EDIT_HEIGHT)
        self._search.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search)
        self._status = QLabel("", self)
        self._status.setObjectName("CountLabel")
        layout.addWidget(self._status)
        layout.addWidget(self._build_scroll_area(), 1)
        layout.addLayout(self._build_buttons())

    def _build_scroll_area(self) -> QScrollArea:
        """构建分组列表滚动区（内容布局由 _rebuild_list 填充）"""
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("DetailContent")
        self._list_layout = QVBoxLayout(content)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _build_buttons(self) -> QHBoxLayout:
        """构建底部按钮行：添加选中 / 清理选中（初始禁用）+ 关闭"""
        row = QHBoxLayout()
        self._add_btn = QPushButton("添加选中到列表", self)
        self._add_btn.setProperty("accent", True)
        self._add_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        self._add_btn.setEnabled(False)
        self._add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_btn.clicked.connect(self._on_add_selected)
        row.addWidget(self._add_btn)
        self._clean_btn = QPushButton("清理选中失效模型", self)
        self._clean_btn.setProperty("danger", True)
        self._clean_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        self._clean_btn.setEnabled(False)
        self._clean_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clean_btn.clicked.connect(self._on_clean_selected)
        row.addWidget(self._clean_btn)
        row.addStretch(1)
        close_btn = QPushButton("关闭", self)
        close_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.accept)
        row.addWidget(close_btn)
        return row

    # ==================== 打开流程 ====================

    def _start(self) -> None:
        """开始对比流程：预设目录型直接提示，否则后台强制刷新远端列表"""
        cfg = get_llm_config().get_provider(self._instance_id)
        if cfg is None:
            self._show_hint("提供商实例不存在，无法同步。", danger=True)
            self._render_local_only()
            return
        preset = get_provider_preset(cfg.preset_id) if cfg.preset_id else None
        if preset is not None and not preset.models_endpoint_path:
            self._show_hint("该提供商使用预设模型目录，无需同步。")
            self._render_local_only()
            return
        self._status.setText("正在从远端获取模型列表…")
        worker = FetchModelsWorker(self._instance_id, parent=self)
        worker.succeeded.connect(self._on_fetch_succeeded)
        worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker = worker
        worker.start()

    def _on_fetch_succeeded(self, instance_id: str, models: list) -> None:
        """远端拉取成功：对比三态并重建列表、解锁操作

        Args:
            instance_id: 实例 id（与当前实例不符时忽略迟到信号）
            models: 远端 ModelInfo 列表
        """
        if instance_id != self._instance_id:
            return
        self._fetch_worker = None
        self._remote_by_id = {
            m.id: m for m in models if getattr(m, "id", "")}
        self._invalid_entries = self._find_invalid_entries()
        self._sync_ready = True
        new_count = len(set(self._remote_by_id) - set(self._local_by_id))
        self._status.setText(
            f"远端共 {len(self._remote_by_id)} 个模型 · 新增 {new_count}"
            f" · 已失效 {len(self._invalid_entries)}")
        self._rebuild_list()

    def _on_fetch_failed(self, instance_id: str, error: str) -> None:
        """远端拉取失败：中文提示 + 降级为仅展示本地列表（操作保持禁用）

        Args:
            instance_id: 实例 id（与当前实例不符时忽略迟到信号）
            error: 错误信息
        """
        if instance_id != self._instance_id:
            return
        self._fetch_worker = None
        _logger.warning(
            get_name(), f"模型同步拉取远端失败: {instance_id} ({error})")
        self._show_hint(
            f"远端模型列表获取失败：{error or '未知错误'}，仅展示本地列表。",
            danger=True)
        self._status.setText("")
        self._render_local_only()

    def _show_hint(self, text: str, danger: bool = False) -> None:
        """显示顶部提示条（danger 时按语义危险色着色）

        Args:
            text: 提示文案
            danger: 是否为错误提示
        """
        t = _theme_module.current_theme()
        self._hint.setText(text)
        self._hint.setStyleSheet(f"color: {t.danger if danger else t.warning};")
        self._hint.setVisible(True)

    # ==================== 列表渲染 ====================

    def _clear_list(self) -> None:
        """清空分组列表（控件随布局摘除销毁，行/组索引重置）"""
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item.widget():
                # 先隐藏再延迟删除，避免 deleteLater 处理前以旧位置重绘
                item.widget().hide()
                item.widget().deleteLater()
        self._rows.clear()
        self._groups.clear()

    def _add_group(
        self, group: str, model_ids: List[str], checkable: bool, checked: bool,
    ) -> None:
        """追加一个分组（彩色小标题 + 行列表），空分组跳过

        Args:
            group: 分组键
            model_ids: 该组的模型 id 列表
            checkable: 行勾选框是否可用
            checked: 行勾选框初始态
        """
        if not model_ids:
            return
        t = _theme_module.current_theme()
        color = {_GROUP_NEW: t.success, _GROUP_EXISTING: t.fg_muted,
                 _GROUP_INVALID: t.danger}[group]
        caption = QLabel(f"{_GROUP_LABELS[group]} · {len(model_ids)}")
        caption.setStyleSheet(f"color: {color}; font-size: 12px;")
        caption.setContentsMargins(0, SUB_DIALOG_SPACING, 0, 0)
        self._list_layout.addWidget(caption)
        rows: List[_SyncRow] = []
        for model_id in model_ids:
            row = _SyncRow(model_id, group, checkable, checked)
            self._list_layout.addWidget(row)
            rows.append(row)
            self._rows.append(row)
        self._groups.append((caption, rows))

    def _finish_list(self) -> None:
        """列表收尾：空态提示 + 底部拉伸 + 搜索过滤 + 按钮态刷新"""
        if not self._rows:
            empty = QLabel("暂无模型")
            empty.setObjectName("EmptyHint")
            self._list_layout.addWidget(empty)
        self._list_layout.addStretch(1)
        self._apply_filter(self._search.text())
        self._update_buttons()

    def _rebuild_list(self) -> None:
        """按当前远端/本地数据重建「新增 / 已存在 / 已失效」三区分组"""
        self._clear_list()
        remote_ids = set(self._remote_by_id)
        new_ids = sorted(remote_ids - set(self._local_by_id))
        existing_ids = [mid for mid in self._local_by_id if mid in remote_ids]
        invalid_ids = [str(e.get("id")) for e in self._invalid_entries]
        self._add_group(_GROUP_NEW, new_ids, True, True)
        self._add_group(_GROUP_EXISTING, existing_ids, False, False)
        self._add_group(_GROUP_INVALID, invalid_ids, True, False)
        self._finish_list()

    def _render_local_only(self) -> None:
        """降级渲染：仅展示本地合并列表（勾选框禁用，同步操作不可用）"""
        self._clear_list()
        self._add_group(
            _GROUP_EXISTING, list(self._local_by_id), False, False)
        self._finish_list()

    def _apply_filter(self, text: str) -> None:
        """按搜索文本过滤行（大小写不敏感的子串匹配），空组标题一并隐藏

        Args:
            text: 搜索文本
        """
        needle = text.strip().lower()
        for caption, rows in self._groups:
            visible_count = 0
            for row in rows:
                visible = not needle or needle in row.model_id.lower()
                row.setVisible(visible)
                visible_count += 1 if visible else 0
            caption.setVisible(visible_count > 0)

    def _update_buttons(self) -> None:
        """按当前分组内容刷新「添加 / 清理」按钮可用态"""
        new_count = sum(1 for r in self._rows if r.group == _GROUP_NEW)
        invalid_count = sum(1 for r in self._rows if r.group == _GROUP_INVALID)
        self._add_btn.setEnabled(self._sync_ready and new_count > 0)
        self._clean_btn.setEnabled(self._sync_ready and invalid_count > 0)

    # ==================== 数据计算与落盘 ====================

    def _find_invalid_entries(self) -> List[Dict[str, Any]]:
        """找出已失效的自定义条目：custom_models 有但远端已无

        目录预设条目的覆写（enabled/hidden 等）不参与失效判定——预设模型
        由目录维护，清理覆写不在本对话框职责内。
        """
        cfg = get_llm_config().get_provider(self._instance_id)
        if cfg is None:
            return []
        preset_ids = {
            e.get("id") for e in PRESET_MODELS.get(cfg.preset_id or "", [])}
        invalid: List[Dict[str, Any]] = []
        for entry in cfg.extra.get("custom_models", []):
            if not isinstance(entry, dict):
                continue
            model_id = entry.get("id")
            if not model_id or model_id in self._remote_by_id:
                continue
            if model_id in preset_ids:
                continue
            invalid.append(entry)
        return invalid

    def _checked_ids(self, group: str) -> List[str]:
        """取指定分组中全部勾选行的模型 id

        Args:
            group: 分组键

        Returns:
            List[str]: 勾选的模型 id 列表
        """
        return [row.model_id for row in self._rows
                if row.group == group and row.is_checked()]

    @staticmethod
    def _build_custom_entry(model: ModelInfo) -> Dict[str, Any]:
        """由远端 ModelInfo 构建规范化 custom_models 条目

        以 to_dict() 为基础（保留上下文长度、能力等），移除缓存来源标记
        键 provider，再经 normalize_model_entry 补全统一 schema 默认值。

        Args:
            model: 远端模型信息

        Returns:
            Dict[str, Any]: 统一 schema 模型条目
        """
        data = model.to_dict()
        data.pop("provider", None)
        return normalize_model_entry(data)

    def _persist(self, apply: Callable[[ProviderConfig], None]) -> bool:
        """对当前实例应用修改并落盘

        Args:
            apply: 修改函数，接收 ProviderConfig 并就地修改

        Returns:
            bool: 是否落盘成功
        """
        config = get_llm_config()
        cfg = config.get_provider(self._instance_id)
        if cfg is None:
            return False
        apply(cfg)
        config.add_provider(self._instance_id, cfg)
        return True

    def _notify_changed(self) -> None:
        """标记变更并外发信号（供调用方重渲染）"""
        self.changed = True
        self.sig_models_changed.emit()

    # ==================== 添加 / 清理操作 ====================

    def _on_add_selected(self) -> None:
        """「添加选中到列表」：勾选的新增模型经规范化写入 custom_models 落盘"""
        ids = self._checked_ids(_GROUP_NEW)
        if not ids:
            _info_toast(self, "请先勾选要添加的新增模型。")
            return
        added: List[str] = []

        def apply(cfg: ProviderConfig) -> None:
            customs = cfg.extra.setdefault("custom_models", [])
            for model_id in ids:
                model = self._remote_by_id.get(model_id)
                if model is None:
                    continue
                customs[:] = [c for c in customs if not (
                    isinstance(c, dict) and c.get("id") == model_id)]
                customs.append(self._build_custom_entry(model))
                added.append(model_id)

        if not self._persist(apply):
            return
        self._notify_changed()
        for model_id in added:
            self._local_by_id[model_id] = self._build_custom_entry(
                self._remote_by_id[model_id])
        _success_toast(self, f"已添加 {len(added)} 个模型到列表。")
        self._rebuild_list()

    def _on_clean_selected(self) -> None:
        """「清理选中失效模型」：从 custom_models 移除勾选的已失效条目落盘"""
        ids = set(self._checked_ids(_GROUP_INVALID))
        if not ids:
            _info_toast(self, "请先勾选要清理的失效模型。")
            return
        removed = 0

        def apply(cfg: ProviderConfig) -> None:
            nonlocal removed
            customs = cfg.extra.get("custom_models", [])
            kept = [c for c in customs if not (
                isinstance(c, dict) and c.get("id") in ids)]
            removed = len(customs) - len(kept)
            cfg.extra["custom_models"] = kept

        if not self._persist(apply):
            return
        self._notify_changed()
        self._invalid_entries = [
            e for e in self._invalid_entries if e.get("id") not in ids]
        _success_toast(self, f"已清理 {removed} 个失效模型。")
        self._rebuild_list()

    # ==================== 关闭与 Worker 回收 ====================

    def _stop_worker(self) -> None:
        """安全终止进行中的拉取 Worker（幂等；一次性请求在结束后响应中断）"""
        worker = self._fetch_worker
        self._fetch_worker = None
        if worker is not None and worker.isRunning():
            worker.requestInterruption()
            worker.wait(WORKER_STOP_WAIT_MS)

    def reject(self) -> None:
        """Esc / 取消路径：先安全终止 Worker 再退出"""
        self._stop_worker()
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """窗口关闭路径：先安全终止 Worker 再交给基类"""
        self._stop_worker()
        super().closeEvent(event)
