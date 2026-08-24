# ui/dialog/llm_settings/dialog.py
"""LLM 设置主对话框

布局与 Demo 一致：QSplitter（左栏 ``ProviderListPanel`` 固定 248px +
右栏 QStackedWidget：占位页 + ``ProviderDetailPanel``）。

主壳只负责两栏协调（选中联动与记忆 / 添加入口 / 启停同步 / 删除后
空态 / 配置变更刷新）与模型编辑对话框的接入（新增/编辑模型条目写入
custom_models 落盘），不包含具体编辑逻辑。
"""

from typing import Any, Dict, Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QDialog, QLabel, QSplitter, QStackedWidget, QVBoxLayout, QWidget,
)

from core.i18n import get_language_manager, tr
from core.llm.config import get_llm_config

from .constants import (
    DIALOG_DEFAULT_HEIGHT, DIALOG_DEFAULT_WIDTH, DIALOG_MIN_HEIGHT,
    DIALOG_MIN_WIDTH, QSETTINGS_APP_NAME, QSETTINGS_LAST_PROVIDER_KEY,
    QSETTINGS_ORG_NAME,
)
from .model_edit_dialog import ModelEditDialog
from .provider_detail_panel import ProviderDetailPanel
from .provider_editor_dialog import MODE_CREATE, ProviderEditorDialog
from .provider_list_panel import ProviderListPanel
from .theme import apply_dialog_theme
from .widgets import install_focus_halo


class LLMSettingsDialog(QDialog):
    """LLM 设置主对话框

    左栏列表与右栏详情联动；上次选中的实例经 QSettings（组织
    LumenThread / 应用 InstructionX-CE）记忆并在下次打开时恢复。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """构造主对话框（构建 UI、接线、恢复上次选中并换肤）

        Args:
            parent: 父控件
        """
        super().__init__(parent)
        self.setMinimumSize(DIALOG_MIN_WIDTH, DIALOG_MIN_HEIGHT)
        self.resize(DIALOG_DEFAULT_WIDTH, DIALOG_DEFAULT_HEIGHT)
        self._settings = QSettings(QSETTINGS_ORG_NAME, QSETTINGS_APP_NAME)
        self._current_id: Optional[str] = None
        self._shutdown_done = False
        self._init_ui()
        self._connect_signals()
        self._restore_selection()
        apply_dialog_theme(self)
        install_focus_halo(self)
        # 语言切换实时跟随：Qt 对象销毁时自动断开连接
        self._retranslate_ui()
        get_language_manager().language_changed.connect(
            lambda _code: self._retranslate_ui())

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建 QSplitter 两栏布局（左列表 + 右堆栈页）"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        self._list_panel = ProviderListPanel(splitter)
        splitter.addWidget(self._list_panel)
        self._stack = QStackedWidget(splitter)
        self._placeholder = self._build_placeholder()
        self._stack.addWidget(self._placeholder)
        self._detail_panel = ProviderDetailPanel(self._stack)
        self._stack.addWidget(self._detail_panel)
        splitter.addWidget(self._stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

    def _build_placeholder(self) -> QWidget:
        """构建空态占位页（无提供商时显示；文案由 _retranslate_ui 设置）"""
        widget = QWidget(self)
        widget.setObjectName("PlaceholderPage")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        page_layout = QVBoxLayout(widget)
        self._placeholder_label = QLabel(widget)
        self._placeholder_label.setObjectName("PlaceholderText")
        self._placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_layout.addWidget(self._placeholder_label)
        return widget

    # ==================== 文案 ====================

    def _retranslate_ui(self) -> None:
        """按当前语言重设全部文案（初始化末尾与语言切换时调用）"""
        self.setWindowTitle(tr("dialog_llm_settings", "dialog.title"))
        self._placeholder_label.setText(
            tr("dialog_llm_settings", "dialog.placeholder"))

    # ==================== 信号接线 ====================

    def _connect_signals(self) -> None:
        """接线：选中 / 添加 / 启停 / 删除 / 配置变更 / 模型编辑"""
        self._list_panel.sig_select.connect(self._on_provider_selected)
        self._list_panel.sig_add.connect(self._on_add_provider)
        self._list_panel.sig_toggle.connect(self._on_provider_toggled)
        self._detail_panel.sig_config_changed.connect(
            self._on_detail_config_changed)
        self._detail_panel.sig_provider_deleted.connect(
            self._on_provider_deleted)
        self._detail_panel.sig_add_model_requested.connect(
            self._on_add_model_requested)
        self._detail_panel.sig_edit_model_requested.connect(
            self._on_edit_model_requested)

    # ==================== 选中协调 ====================

    def _show_detail(self, instance_id: str) -> None:
        """切换右栏为详情页并加载实例、记忆选中

        Args:
            instance_id: 实例 id
        """
        self._current_id = instance_id
        self._stack.setCurrentWidget(self._detail_panel)
        self._detail_panel.load_instance(instance_id)
        self._settings.setValue(QSETTINGS_LAST_PROVIDER_KEY, instance_id)

    def _show_placeholder(self) -> None:
        """切换右栏为空态占位页（无提供商）"""
        self._current_id = None
        self._detail_panel.load_instance(None)
        self._stack.setCurrentWidget(self._placeholder)

    def _on_provider_selected(self, instance_id: str) -> None:
        """左栏选中变化：加载详情并记忆选中（重复选中忽略）"""
        if instance_id == self._current_id:
            return
        self._show_detail(instance_id)

    def _restore_selection(self) -> None:
        """恢复上次选中的实例；无记忆或已删除时回退为当前/空态"""
        remembered = self._settings.value(
            QSETTINGS_LAST_PROVIDER_KEY, "", type=str)
        providers = get_llm_config().get_all_providers()
        target = remembered if remembered in providers else None
        if target is None:
            target = self._list_panel.current_provider_id()
        if target is None:
            self._show_placeholder()
            return
        # reload 命中既有选中项时不重复发 sig_select，统一由 _show_detail 加载
        self._list_panel.reload(select_id=target)
        self._show_detail(target)

    # ==================== 左栏事件 ====================

    def _on_add_provider(self) -> None:
        """「＋ 添加提供商」：两页添加对话框，成功后选中新实例"""
        editor = ProviderEditorDialog(MODE_CREATE, parent=self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        if not editor.created_instance_id:
            return
        self._list_panel.reload(select_id=editor.created_instance_id)
        self._show_detail(editor.created_instance_id)

    def _on_provider_toggled(self, instance_id: str, _on: bool) -> None:
        """左栏启停开关：配置已落盘，当前实例时同步详情面板（总开关+遮罩）"""
        if instance_id == self._current_id:
            self._detail_panel.load_instance(instance_id)

    # ==================== 右栏事件 ====================

    def _on_detail_config_changed(self) -> None:
        """详情配置变更（重命名/总开关/模型覆写）：刷新左栏对应行"""
        if self._current_id:
            self._list_panel.refresh_provider(self._current_id)

    def _on_provider_deleted(self) -> None:
        """实例已删除：重建列表；删空时切换空态占位页"""
        self._list_panel.reload()
        current = self._list_panel.current_provider_id()
        if current is None:
            self._settings.setValue(QSETTINGS_LAST_PROVIDER_KEY, "")
            self._show_placeholder()
            return
        # reload 选中了其他实例时 sig_select 已联动；命中同一实例则直接加载
        if current != self._current_id:
            self._show_detail(current)

    # ==================== 模型编辑 ====================

    def _on_add_model_requested(self) -> None:
        """「＋ 添加」模型：新建对话框，确认后写 custom_models 落盘并重载"""
        if not self._current_id:
            return
        editor = ModelEditDialog(parent=self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        self._upsert_custom_model(self._current_id, editor.get_model_data())
        self._detail_panel.load_instance(self._current_id)

    def _on_edit_model_requested(self, entry: Dict[str, Any]) -> None:
        """双击模型行：编辑对话框，确认后同 id 覆写 custom_models 落盘

        编辑结果保留原条目的 enabled/hidden 覆写键（表单不承载这两键）。

        Args:
            entry: 被编辑的统一 schema 模型条目
        """
        if not self._current_id:
            return
        editor = ModelEditDialog(model_data=entry, parent=self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        data = editor.get_model_data()
        data["enabled"] = bool(entry.get("enabled", True))
        if entry.get("hidden"):
            data["hidden"] = True
        self._upsert_custom_model(self._current_id, data)
        self._detail_panel.load_instance(self._current_id)

    def _upsert_custom_model(
        self, instance_id: str, entry: Dict[str, Any],
    ) -> None:
        """将模型条目写入实例 custom_models（同 id 覆写）并落盘

        Args:
            instance_id: 实例 id
            entry: 统一 schema 模型条目
        """
        config = get_llm_config()
        cfg = config.get_provider(instance_id)
        if cfg is None:
            return
        customs = [
            item for item in cfg.extra.get("custom_models", [])
            if not (isinstance(item, dict) and item.get("id") == entry.get("id"))
        ]
        customs.append(entry)
        cfg.extra["custom_models"] = customs
        config.add_provider(instance_id, cfg)

    # ==================== 关闭与 Worker 回收 ====================

    def _shutdown(self) -> None:
        """关闭收尾：保存选中记忆、退订配置订阅并安全终止 Worker（幂等）"""
        if self._shutdown_done:
            return
        self._shutdown_done = True
        current = self._list_panel.current_provider_id()
        if current:
            self._settings.setValue(QSETTINGS_LAST_PROVIDER_KEY, current)
        # 显式退订：LLMConfig 为全局单例，避免关闭后回调到已失效面板
        self._list_panel.dispose()
        self._detail_panel.shutdown_workers()

    def reject(self) -> None:
        """关闭（取消）路径：先收尾再退出"""
        self._shutdown()
        super().reject()

    def accept(self) -> None:
        """接受路径：先收尾再退出"""
        self._shutdown()
        super().accept()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt 命名)
        """窗口关闭路径：先收尾再交给基类"""
        self._shutdown()
        super().closeEvent(event)
