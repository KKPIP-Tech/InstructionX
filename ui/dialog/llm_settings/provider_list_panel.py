# ui/dialog/llm_settings/provider_list_panel.py
"""左栏 Provider 列表面板

视觉：「模型服务」小标题 + 搜索框 + Provider 列表（品牌图标 + 自绘
开关，选中为圆角 pill）+ 底部「＋ 添加提供商」。

数据：实例列表取自 ``get_llm_config().get_all_providers()`` 按
``order`` 升序渲染；开关切换经 LLMConfig.add_provider 写
``enabled_chat`` 落盘；搜索匹配实例名 / 实例 id / 预设显示名 /
实例下模型 id 与 name（缓存模型 + custom_models）。

本面板只做 UI 与交互编排，配置读写一律经 ``get_llm_config()``；
选中变化经 ``sig_select`` 信号交由主壳协调。无右键菜单（重命名 /
删除在右侧更多菜单）、无拖拽排序（order 仅用于渲染排序）。
"""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import get_language_manager, tr
from core.llm.catalog import get_provider_preset
from core.llm.config import (
    EVENT_PROVIDERS_CHANGED, ProviderConfig, get_llm_config,
)
from core.llm.llm_provider import get_llm_provider
from utils.logging_tools import LoggerManager, get_name

from .constants import (
    ADD_PROVIDER_BUTTON_HEIGHT, ADD_PROVIDER_ROW_TOP_MARGIN,
    LIST_ITEM_HEIGHT, LIST_ITEM_HINT_WIDTH, LIST_ROW_SPACING,
    SEARCH_EDIT_HEIGHT, SIDEBAR_LIST_TOP_GAP, SIDEBAR_MARGIN_BOTTOM,
    SIDEBAR_MARGIN_H, SIDEBAR_MARGIN_TOP, SIDEBAR_SPACING, SIDEBAR_WIDTH,
)
from .theme import Theme
from .widgets import ProviderItemWidget, make_section_label

_logger = LoggerManager()


class ProviderListPanel(QWidget):
    """Provider 列表面板（左栏）

    Signals:
        sig_select(str): 选中实例变化（实例 id）
        sig_toggle(str, bool): 实例启用开关切换（实例 id, 新状态），
            配置已由本面板落盘，主壳用于同步详情面板
        sig_add(): 点击「＋ 添加提供商」
    """

    sig_select = Signal(str)
    sig_toggle = Signal(str, bool)
    sig_add = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        """构造面板（构建 UI、订阅配置变更并首次加载列表）

        Args:
            parent: 父控件
        """
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._providers: List[Tuple[str, ProviderConfig]] = []
        self._rows: Dict[str, Tuple[QListWidgetItem, ProviderItemWidget]] = {}
        self._selected_id: Optional[str] = None
        # 自身写配置期间抑制 subscribe 触发的刷新，避免通知风暴
        self._suppress_config_refresh = False
        # reload 重建期间抑制 _apply_filter 的自动重选（选中恢复由 reload 负责）
        self._suspend_auto_select = False
        self._init_ui()
        get_llm_config().subscribe(self._on_config_changed)
        self.destroyed.connect(self._on_destroyed)
        # 语言切换实时跟随（Qt 对象销毁自动断开）；_retranslate_ui 内含首次 reload
        self._retranslate_ui()
        get_language_manager().language_changed.connect(
            lambda _code: self._retranslate_ui())

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建标题 + 搜索框 + 列表 + 添加按钮（文案由 _retranslate_ui 设置）"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            SIDEBAR_MARGIN_H, SIDEBAR_MARGIN_TOP,
            SIDEBAR_MARGIN_H, SIDEBAR_MARGIN_BOTTOM)
        layout.setSpacing(SIDEBAR_SPACING)

        self._section_label = make_section_label("")
        layout.addWidget(self._section_label)

        self.search_edit = QLineEdit(self)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedHeight(SEARCH_EDIT_HEIGHT)
        self.search_edit.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search_edit)

        layout.addSpacing(SIDEBAR_LIST_TOP_GAP)

        self.list = QListWidget(self)
        self.list.setFrameShape(QFrame.Shape.NoFrame)
        self.list.setSpacing(LIST_ROW_SPACING)
        self.list.currentItemChanged.connect(self._on_current_changed)
        layout.addWidget(self.list, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, ADD_PROVIDER_ROW_TOP_MARGIN, 0, 0)
        self.add_btn = QPushButton("", self)
        self.add_btn.setObjectName("AddProviderBtn")
        self.add_btn.setFixedHeight(ADD_PROVIDER_BUTTON_HEIGHT)
        self.add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_btn.clicked.connect(self.sig_add.emit)
        bottom.addWidget(self.add_btn, 1)
        layout.addLayout(bottom)

    # ==================== 文案 ====================

    def _retranslate_ui(self) -> None:
        """按当前语言重设全部文案（初始化末尾与语言切换时调用）

        列表行（ProviderItemWidget 开关 tooltip 等）经 reload 重建刷新。
        """
        self._section_label.setText(
            tr("dialog_llm_settings", "list.section_title"))
        self.search_edit.setPlaceholderText(
            tr("dialog_llm_settings", "list.search_placeholder"))
        self.add_btn.setText(tr("dialog_llm_settings", "list.add_button"))
        self.reload()

    # ==================== 列表加载 ====================

    def reload(self, select_id: Optional[str] = None) -> None:
        """整体重建列表（保留搜索词；尽量保持当前选中）

        Args:
            select_id: 指定要选中的实例 id；为 None 时保持当前选中
                （已删除则回退为第一个可见项）
        """
        # 必须在清空前快照目标选中项：list.clear() 后 currentItem 为 None，
        # _apply_filter 的自动重选会把 _selected_id 覆盖为第一项（导致跳回）
        target = select_id or self._selected_id
        providers = get_llm_config().get_all_providers()
        self._providers = sorted(
            providers.items(), key=lambda kv: (kv[1].order, kv[0]))
        self._rows.clear()
        self._suspend_auto_select = True
        self.list.blockSignals(True)
        try:
            self.list.clear()
            for instance_id, cfg in self._providers:
                self._add_row(instance_id, cfg)
            self._apply_filter(self.search_edit.text())
        finally:
            self.list.blockSignals(False)
            self._suspend_auto_select = False
        if target and target in self._rows and not self._rows[target][0].isHidden():
            self._select(target)
        else:
            self._select_first_visible()

    def _add_row(self, instance_id: str, cfg: ProviderConfig) -> None:
        """插入单个实例列表行（ProviderItemWidget 宿主）"""
        item = QListWidgetItem()
        item.setSizeHint(QSize(LIST_ITEM_HINT_WIDTH, LIST_ITEM_HEIGHT))
        item.setData(Qt.ItemDataRole.UserRole, instance_id)
        widget = ProviderItemWidget(
            instance_id, cfg.name, cfg.preset_id, cfg.enabled_chat)
        widget.clicked.connect(self._select)
        widget.toggled.connect(self._on_item_toggled)
        self.list.addItem(item)
        self.list.setItemWidget(item, widget)
        self._rows[instance_id] = (item, widget)

    def refresh_provider(self, instance_id: str) -> None:
        """数据变化后刷新单行（名称/图标/开关）

        Args:
            instance_id: 实例 id
        """
        row = self._rows.get(instance_id)
        cfg = get_llm_config().get_provider(instance_id)
        if row is None or cfg is None:
            return
        row[1].refresh(cfg.name, cfg.preset_id, cfg.enabled_chat)

    def apply_theme(self, theme: Theme) -> None:
        """主题切换：刷新全部列表行的自绘内容

        Args:
            theme: 新主题 token
        """
        for _item, widget in self._rows.values():
            widget.apply_theme(theme)

    def current_provider_id(self) -> Optional[str]:
        """当前选中的实例 id（无选中返回 None）"""
        return self._selected_id

    # ==================== 选中 ====================

    def _select(self, instance_id: str) -> None:
        """选中指定实例（隐藏项不可选中）"""
        row = self._rows.get(instance_id)
        if row is None or row[0].isHidden():
            return
        self.list.setCurrentItem(row[0])
        self._on_current_changed(row[0], None)

    def _select_first_visible(self) -> None:
        """选中第一个可见项；全部不可见时清空选中"""
        for i in range(self.list.count()):
            item = self.list.item(i)
            if not item.isHidden():
                self._select(item.data(Qt.ItemDataRole.UserRole))
                return
        self._on_current_changed(None, None)

    def _on_current_changed(
        self,
        current: Optional[QListWidgetItem],
        _previous: Optional[QListWidgetItem],
    ) -> None:
        """选中变化：刷新各行选中态，选中实例变化时外发 sig_select"""
        current_id: Optional[str] = None
        for pid, (item, widget) in self._rows.items():
            selected = item is current
            widget.set_selected(selected)
            if selected:
                current_id = pid
        if current_id is not None and current_id != self._selected_id:
            self._selected_id = current_id
            self.sig_select.emit(current_id)
        elif current_id is None:
            self._selected_id = None

    # ==================== 搜索过滤 ====================

    def _apply_filter(self, text: str) -> None:
        """按关键字过滤实例项；当前选中被过滤掉时改选第一个可见项

        Args:
            text: 搜索关键字（大小写不敏感）
        """
        needle = text.strip().lower()
        for instance_id, cfg in self._providers:
            item = self._rows[instance_id][0]
            hit = not needle or self._matches_keyword(instance_id, cfg, needle)
            item.setHidden(not hit)
        # 重建（reload）期间禁止自动改选第一项，选中恢复由 reload 统一负责
        if self._suspend_auto_select:
            return
        current = self.list.currentItem()
        if current is None or current.isHidden():
            self._select_first_visible()

    def _matches_keyword(
        self, instance_id: str, cfg: ProviderConfig, needle: str,
    ) -> bool:
        """判断实例是否命中搜索关键字（含其下模型 id/name）"""
        candidates = [cfg.name, instance_id]
        preset = get_provider_preset(cfg.preset_id) if cfg.preset_id else None
        if preset:
            candidates.append(preset.display_name)
        candidates.extend(self._model_texts(instance_id, cfg))
        return any(needle in (text or "").lower() for text in candidates)

    @staticmethod
    def _model_texts(instance_id: str, cfg: ProviderConfig) -> List[str]:
        """收集实例下模型的 id/name 文本（缓存模型 + custom_models）"""
        texts: List[str] = []
        try:
            for model in get_llm_provider().get_cached_models(instance_id):
                texts.extend([model.id, model.name])
        except Exception as e:
            _logger.warning(
                get_name(), f"搜索时读取模型缓存失败: {instance_id} ({e})")
        for entry in cfg.extra.get("custom_models", []):
            if isinstance(entry, dict):
                texts.extend([entry.get("id", ""), entry.get("name", "")])
        return texts

    # ==================== 启用开关 ====================

    def _on_item_toggled(self, instance_id: str, on: bool) -> None:
        """列表项启用开关：写 enabled_chat 落盘并外发 sig_toggle"""
        config = get_llm_config()
        cfg = config.get_provider(instance_id)
        if cfg is None:
            return
        cfg.enabled_chat = on
        self._suppress_config_refresh = True
        try:
            config.add_provider(instance_id, cfg)
        finally:
            self._suppress_config_refresh = False
        self.sig_toggle.emit(instance_id, on)

    # ==================== 配置变更订阅 ====================

    def _on_config_changed(
        self, event: str, _provider_name: Optional[str],
    ) -> None:
        """配置变更订阅回调：非自身触发时重建列表（保持选中）"""
        if event != EVENT_PROVIDERS_CHANGED or self._suppress_config_refresh:
            return
        self.reload()

    def dispose(self) -> None:
        """显式退订配置变更（对话框关闭路径调用，幂等）

        不依赖 ``destroyed`` 信号的销毁时序：LLMConfig 为全局单例，
        对话框关闭后若仍持有本面板回调，再次落盘时会回调到已失效
        （或已隐藏）的面板。
        """
        get_llm_config().unsubscribe(self._on_config_changed)

    def _on_destroyed(self) -> None:
        """控件销毁时退订配置变更（dispose 的兜底，unsubscribe 幂等）"""
        self.dispose()
