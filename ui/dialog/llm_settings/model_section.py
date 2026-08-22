# ui/dialog/llm_settings/model_section.py
"""详情面板「模型」分区视图模块

自 provider_detail_panel.py 拆分而来，承载模型分区的全部视图与交互编排：
标题行（计数 / 刷新状态 / ↻ 刷新 / ＋ 添加 / ⚡ 检查 / ⇅ 同步 / 管理）、管理模式工具条
（全选 / 删除选中）、按主类型（对话/视觉/嵌入/重排序）分组渲染的模型行
列表（行间 1px hairline）。

本模块只做视图与交互（含删除的中文确认弹窗）；模型条目的三路合并装配
与覆写落盘由 ProviderDetailPanel 负责，经信号外发交互意图：

- 开关切换 / 删除确认 → 面板落盘后调用 ``rebuild`` 重渲染；
- 「＋ 添加」/ 双击编辑 / 「↻ 刷新」→ 面板或主壳接手处理；
- 「⚡ 检查」/ 「⇅ 同步」→ 面板转发打开对应对话框。
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from core.i18n import tr

from .constants import (
    EMPTY_HINT_MARGIN_BOTTOM, FIELD_BLOCK_GAP, FIELD_GAP,
    GROUP_CAPTION_MARGIN_BOTTOM, GROUP_CAPTION_MARGIN_LEFT,
    GROUP_CAPTION_MARGIN_TOP, MANAGE_BAR_MARGIN_H, MANAGE_BAR_MARGIN_V,
    MANAGE_BAR_SPACING, MANAGE_DELETE_BUTTON_HEIGHT, MODEL_TYPE_KEYS,
    MODELS_HEADER_BUTTON_HEIGHT, MODELS_REFRESH_BUTTON_WIDTH,
)
from .theme import Theme
from .feedback import confirm as _confirm_dialog
from .widgets import (
    ModelRow, _model_primary_type, make_hairline, make_section_label,
    model_type_label,
)


class ModelSection(QWidget):
    """详情面板「模型」分区视图

    Signals:
        sig_add_requested(): 点击「＋ 添加」，请求新增模型
        sig_edit_requested(object): 双击模型行，请求编辑该条目（统一 schema dict）
        sig_refresh_requested(): 点击「↻ 刷新」，请求从 API 获取最新模型列表
        sig_model_toggled(str, bool): 模型启用开关切换（模型 id, 新状态；未落盘）
        sig_delete_confirmed(list): 删除确认完成（模型 id 列表；未落盘）
        sig_health_check_requested(): 点击「⚡ 检查」，请求打开健康检查对话框
        sig_sync_requested(): 点击「⇅ 同步」，请求打开模型同步对话框
    """

    sig_add_requested = Signal()
    sig_edit_requested = Signal(object)
    sig_refresh_requested = Signal()
    sig_model_toggled = Signal(str, bool)
    sig_delete_confirmed = Signal(list)
    sig_health_check_requested = Signal()
    sig_sync_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        """构造模型分区视图

        Args:
            parent: 父控件
        """
        super().__init__(parent)
        self._manage_mode = False
        self._rows: List[ModelRow] = []
        self._entries: List[Dict[str, Any]] = []
        self._init_ui()

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建标题行 + 管理工具条 + 分组容器"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(self._build_header())
        layout.addSpacing(FIELD_BLOCK_GAP)
        layout.addWidget(self._build_manage_bar())
        self._groups_widget = QWidget(self)
        self._groups_layout = QVBoxLayout(self._groups_widget)
        self._groups_layout.setContentsMargins(0, 0, 0, 0)
        self._groups_layout.setSpacing(0)
        layout.addWidget(self._groups_widget)

    def _build_header(self) -> QHBoxLayout:
        """构建标题行：小标题 + 计数 + 刷新状态 + ↻ 刷新 + ＋ 添加 + 管理"""
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(FIELD_GAP)
        self._section_label = make_section_label("")
        header.addWidget(self._section_label)
        self._count_label = QLabel("")
        self._count_label.setObjectName("CountLabel")
        header.addWidget(self._count_label, 0, Qt.AlignmentFlag.AlignBottom)
        self._refresh_status = QLabel("")
        self._refresh_status.setObjectName("CountLabel")
        header.addWidget(self._refresh_status, 0, Qt.AlignmentFlag.AlignBottom)
        header.addStretch(1)
        header.addWidget(self._build_refresh_button())
        header.addWidget(self._build_add_button())
        header.addWidget(self._build_health_button())
        header.addWidget(self._build_sync_button())
        header.addWidget(self._build_manage_button())
        return header

    def _build_refresh_button(self) -> QPushButton:
        """构建「↻ 刷新」小按钮（幽灵按钮风格，样式走主题 QSS）"""
        self._refresh_btn = QPushButton("↻", self)
        self._refresh_btn.setFixedSize(
            MODELS_REFRESH_BUTTON_WIDTH, MODELS_HEADER_BUTTON_HEIGHT)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        return self._refresh_btn

    def _build_add_button(self) -> QPushButton:
        """构建「＋ 添加」按钮（仅外发信号，编辑对话框由主壳接入）"""
        self._add_model_btn = QPushButton("", self)
        self._add_model_btn.setFixedHeight(MODELS_HEADER_BUTTON_HEIGHT)
        self._add_model_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_model_btn.clicked.connect(self.sig_add_requested.emit)
        return self._add_model_btn

    def _build_health_button(self) -> QPushButton:
        """构建「⚡ 检查」幽灵按钮（打开健康检查对话框，仅外发信号）"""
        self._health_btn = QPushButton("", self)
        self._health_btn.setFixedHeight(MODELS_HEADER_BUTTON_HEIGHT)
        self._health_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._health_btn.clicked.connect(self.sig_health_check_requested.emit)
        return self._health_btn

    def _build_sync_button(self) -> QPushButton:
        """构建「⇅ 同步」幽灵按钮（打开模型同步对话框，仅外发信号）"""
        self._sync_btn = QPushButton("", self)
        self._sync_btn.setFixedHeight(MODELS_HEADER_BUTTON_HEIGHT)
        self._sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_btn.clicked.connect(self.sig_sync_requested.emit)
        return self._sync_btn

    def _build_manage_button(self) -> QPushButton:
        """构建「管理」切换按钮（进入/退出批量管理模式）"""
        self._manage_btn = QPushButton("", self)
        self._manage_btn.setCheckable(True)
        self._manage_btn.setFixedHeight(MODELS_HEADER_BUTTON_HEIGHT)
        self._manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._manage_btn.toggled.connect(self._on_manage_toggled)
        return self._manage_btn

    def _build_manage_bar(self) -> QWidget:
        """构建管理模式工具条：全选 + 删除选中"""
        self._manage_bar = QWidget(self)
        self._manage_bar.setObjectName("ManageBar")
        self._manage_bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        manage_row = QHBoxLayout(self._manage_bar)
        manage_row.setContentsMargins(
            MANAGE_BAR_MARGIN_H, MANAGE_BAR_MARGIN_V,
            MANAGE_BAR_MARGIN_H, MANAGE_BAR_MARGIN_V)
        manage_row.setSpacing(MANAGE_BAR_SPACING)
        self._select_all = QCheckBox("", self._manage_bar)
        self._select_all.setTristate(True)
        self._select_all.clicked.connect(self._on_select_all_clicked)
        manage_row.addWidget(self._select_all)
        manage_row.addStretch(1)
        self._delete_selected_btn = QPushButton("", self._manage_bar)
        self._delete_selected_btn.setProperty("danger", True)
        self._delete_selected_btn.setFixedHeight(MANAGE_DELETE_BUTTON_HEIGHT)
        self._delete_selected_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_selected_btn.clicked.connect(self._on_delete_selected)
        manage_row.addWidget(self._delete_selected_btn)
        self._manage_bar.setVisible(False)
        return self._manage_bar

    # ==================== 文案 ====================

    def _retranslate_ui(self) -> None:
        """按当前语言重设全部文案并重建分组列表（语言切换时调用）

        分组标题 / 空态提示 / 行内徽章与 tooltip 随 rebuild 重建刷新；
        计数与刷新状态为瞬态文案，随下一次 rebuild / 操作重设。
        """
        self._section_label.setText(
            tr("dialog_llm_settings", "model.section.title"))
        self._refresh_btn.setToolTip(
            tr("dialog_llm_settings", "model.section.refresh_tooltip"))
        self._add_model_btn.setText(
            tr("dialog_llm_settings", "model.section.add"))
        self._health_btn.setText(
            tr("dialog_llm_settings", "model.section.health"))
        self._health_btn.setToolTip(
            tr("dialog_llm_settings", "model.section.health_tooltip"))
        self._sync_btn.setText(
            tr("dialog_llm_settings", "model.section.sync"))
        self._sync_btn.setToolTip(
            tr("dialog_llm_settings", "model.section.sync_tooltip"))
        self._manage_btn.setText(tr(
            "dialog_llm_settings",
            "model.section.manage_done" if self._manage_mode
            else "model.section.manage"))
        self._select_all.setText(
            tr("dialog_llm_settings", "model.section.select_all"))
        self._delete_selected_btn.setText(
            tr("dialog_llm_settings", "model.section.delete_selected"))
        self.rebuild(self._entries)

    # ==================== 渲染 ====================

    def rebuild(self, entries: List[Dict[str, Any]]) -> None:
        """按合并后的模型条目重建分组列表

        Args:
            entries: 三路合并后的统一 schema 条目列表（已过滤 hidden）
        """
        while self._groups_layout.count():
            item = self._groups_layout.takeAt(0)
            if item.widget():
                # 先隐藏再延迟删除：deleteLater 需等事件循环处理，
                # 不隐藏会在处理前以旧位置（分组容器原点）重绘造成叠影
                item.widget().hide()
                item.widget().deleteLater()
        self._rows.clear()
        self._entries = entries
        self._count_label.setText(
            tr("dialog_llm_settings", "model.section.count",
               count=len(entries)) if entries else "")
        if not entries:
            self._add_empty_hint()
        else:
            self._add_model_groups()
        self._sync_select_all()

    def _add_empty_hint(self) -> None:
        """渲染模型空态提示"""
        empty = QLabel(tr("dialog_llm_settings", "model.section.empty_hint"))
        empty.setObjectName("EmptyHint")
        empty.setContentsMargins(
            GROUP_CAPTION_MARGIN_LEFT, GROUP_CAPTION_MARGIN_TOP, 0,
            EMPTY_HINT_MARGIN_BOTTOM)
        self._groups_layout.addWidget(empty)

    def _add_model_groups(self) -> None:
        """按主类型分组渲染 ModelRow（对话/视觉/嵌入/重排序，行间 hairline）"""
        for type_key in MODEL_TYPE_KEYS:
            group = [e for e in self._entries
                     if _model_primary_type(e) == type_key]
            if not group:
                continue
            self._add_group_caption(tr(
                "dialog_llm_settings", "model.group_caption",
                label=model_type_label(type_key), count=len(group)))
            for index, entry in enumerate(group):
                if index > 0:
                    self._groups_layout.addWidget(make_hairline())
                self._add_model_row(entry)
        self._groups_layout.addSpacing(GROUP_CAPTION_MARGIN_BOTTOM)

    def _add_group_caption(self, text: str) -> None:
        """插入分组标题（类型 · 数量）"""
        caption = QLabel(text)
        caption.setObjectName("GroupCaption")
        caption.setContentsMargins(
            GROUP_CAPTION_MARGIN_LEFT, GROUP_CAPTION_MARGIN_TOP, 0,
            GROUP_CAPTION_MARGIN_BOTTOM)
        self._groups_layout.addWidget(caption)

    def _add_model_row(self, entry: Dict[str, Any]) -> None:
        """插入单个模型行并接线"""
        row = ModelRow(entry)
        row.set_manage_mode(self._manage_mode)
        row.sig_delete.connect(self._on_delete_row)
        row.sig_checked.connect(self._sync_select_all)
        row.sig_toggled.connect(self.sig_model_toggled.emit)
        row.sig_edit.connect(self.sig_edit_requested.emit)
        self._groups_layout.addWidget(row)
        self._rows.append(row)

    # ==================== 刷新状态 ====================

    def _on_refresh_clicked(self) -> None:
        """「↻ 刷新」：仅外发请求信号，Worker 由详情面板管理"""
        self.sig_refresh_requested.emit()

    def set_refresh_busy(self, busy: bool) -> None:
        """设置刷新进行态（进行期间禁用刷新按钮，避免重复拉取）

        Args:
            busy: 是否正在获取模型列表
        """
        self._refresh_btn.setEnabled(not busy)

    def set_refresh_status(self, text: str) -> None:
        """设置刷新结果的状态文案（toast 式小字，空串清除）

        Args:
            text: 状态文本（如「✓ 已更新 · 12 个模型」）
        """
        self._refresh_status.setText(text)

    # ==================== 管理（批量删除）模式 ====================

    def reset_manage_mode(self) -> None:
        """退出管理模式（加载实例时调用）"""
        self._manage_btn.blockSignals(True)
        self._manage_btn.setChecked(False)
        self._manage_btn.blockSignals(False)
        self._manage_mode = False
        self._manage_btn.setText(tr("dialog_llm_settings", "model.section.manage"))
        self._manage_bar.setVisible(False)

    def _on_manage_toggled(self, on: bool) -> None:
        """管理模式切换：显示勾选框与工具条"""
        self._manage_mode = on
        self._manage_btn.setText(tr(
            "dialog_llm_settings",
            "model.section.manage_done" if on else "model.section.manage"))
        self._manage_bar.setVisible(on)
        for row in self._rows:
            row.set_manage_mode(on)
        self._sync_select_all()

    def _on_select_all_clicked(self, _checked: bool) -> None:
        """全选：忽略三态自身的循环（当前全选则全不选，否则全选）"""
        all_checked = bool(self._rows) and all(
            row.is_checked() for row in self._rows)
        for row in self._rows:
            row.set_checked(not all_checked)
        self._sync_select_all()

    def _sync_select_all(self) -> None:
        """按各行勾选态同步「全选」三态框"""
        if not self._rows:
            state = Qt.CheckState.Unchecked
        else:
            count = sum(1 for row in self._rows if row.is_checked())
            if count == 0:
                state = Qt.CheckState.Unchecked
            elif count == len(self._rows):
                state = Qt.CheckState.Checked
            else:
                state = Qt.CheckState.PartiallyChecked
        self._select_all.blockSignals(True)
        self._select_all.setCheckState(state)
        self._select_all.blockSignals(False)

    # ==================== 删除（确认后外发） ====================

    def _confirm_delete(self, message: str) -> bool:
        """弹出删除确认框

        Args:
            message: 确认文案

        Returns:
            bool: 用户是否确认删除
        """
        return _confirm_dialog(
            self, tr("dialog_llm_settings", "model.delete.title"), message)

    def _on_delete_row(self, entry: Dict[str, Any]) -> None:
        """单条删除：确认后外发模型 id 列表"""
        model_id = str(entry.get("id", ""))
        if not model_id:
            return
        if self._confirm_delete(tr(
                "dialog_llm_settings", "model.delete.message", id=model_id)):
            self.sig_delete_confirmed.emit([model_id])

    def _on_delete_selected(self) -> None:
        """删除选中：确认后外发勾选模型 id 列表"""
        doomed = [str(row.entry.get("id", "")) for row in self._rows
                  if row.is_checked()]
        doomed = [model_id for model_id in doomed if model_id]
        if not doomed:
            return
        if self._confirm_delete(tr(
                "dialog_llm_settings", "model.delete.message_multi",
                count=len(doomed))):
            self.sig_delete_confirmed.emit(doomed)

    # ==================== 主题 ====================

    def apply_theme(self, theme: Theme) -> None:
        """主题切换：重渲全部模型行的自绘内容

        Args:
            theme: 新主题 token
        """
        for row in self._rows:
            row.apply_theme(theme)
