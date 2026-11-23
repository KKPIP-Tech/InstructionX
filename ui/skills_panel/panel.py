from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QLabel,
    QStyle, QSizePolicy, QFrame
)
from PySide6.QtCore import Signal, Qt, QTimer

from PySide6.QtGui import QIcon

from core.i18n import tr, get_language_manager
from utils.logging_tools import LoggerManager, get_name
from InstructionX_UIKit.theme import ThemeManager
from .skill_button import SkillButton
from .plugin_group_widget import PluginGroupWidget
from .scroll_navigation import SkillsScrollNavigator


SKILLS_PANEL_RELAXED = "relaxed"
SKILLS_PANEL_COMPACT = "compact"
SKILLS_PANEL_MODES = frozenset((SKILLS_PANEL_RELAXED, SKILLS_PANEL_COMPACT))
SKILLS_HEADER_VERTICAL_MARGIN = 6
SKILLS_PILL_VERTICAL_MARGIN = 2
RELAXED_PANEL_MIN_HEIGHT = 125
RELAXED_PANEL_MAX_HEIGHT = 135
RELAXED_CONTAINER_MARGINS = (4, 2, 4, 2)
COMPACT_CONTAINER_MARGINS = (4, 0, 4, 0)
RELAXED_CONTAINER_SPACING = 4
COMPACT_CONTAINER_SPACING = 2


class SkillsPanel(QWidget):
    """技能面板组件。

    宽松模式使用「切换/计数行 + 插件滚动行」，紧凑模式将仅图标的
    插件滚动行并入切换行，并在溢出时提供 UIKit 左右箭头导航。
    """

    # 信号：
    skill_clicked = Signal(object)  # 发送插件对象

    def __init__(self, parent: QWidget):
        super().__init__(parent=parent)
        self.plugin_manager = None
        self._active_button = None  # 当前激活的按钮
        self._active_plugin = None  # 当前激活插件（重建按钮后据此恢复高亮）
        #: 面板上已渲染的插件显示名快照（插件实例 id → plugin_name），
        #: 语言变化时据此判断是否真的需要重建按钮
        self._rendered_names: dict = {}
        self._display_mode = SKILLS_PANEL_RELAXED
        self.setProperty("compact", "false")
        self._logger = LoggerManager()
        self._init_ui()

        # 首次填充文案，并跟随语言切换重设（Qt 对象销毁时自动断开连接）
        self._retranslate_ui()
        get_language_manager().language_changed.connect(self._retranslate_ui)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    @property
    def display_mode(self) -> str:
        """返回当前显示模式（relaxed / compact）。"""
        return self._display_mode

    def showEvent(self, event) -> None:
        """首次显示后按真实字体与 QSS 同步紧凑行高。"""
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_compact_metrics)

    def _on_theme_changed(self, _mode: str) -> None:
        """主题变化后重新计算紧凑行高与导航状态。"""
        QTimer.singleShot(0, self._sync_compact_metrics)

    def _retranslate_ui(self) -> None:
        """集中重设技能面板用户可见文案（Pill 按钮与计数标签）"""
        self.official_btn.setText(tr("skills_panel", "tab.official"))
        self.thirdparty_btn.setText(tr("skills_panel", "tab.thirdparty"))
        # 计数标签由 _switch_tab 按当前页刷新（模板含 {count} 占位符）
        self._switch_tab(self.stacked_widget.currentIndex())
        QTimer.singleShot(0, self._sync_compact_metrics)

    def set_plugin_manager(self, plugin_manager):
        """设置插件管理器"""
        self.plugin_manager = plugin_manager

    def _init_ui(self):
        """初始化宽松布局，后续模式切换复用同一批控件。"""
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)
        self._create_header()
        self._create_pages()
        self._apply_panel_height(False, 0)

    def _create_header(self) -> None:
        """创建切换按钮、分隔线、计数器和紧凑导航的宿主行。"""
        header_widget = QWidget()
        header_widget.setObjectName("skillsPanelHeader")
        self._header_layout = QHBoxLayout(header_widget)
        self._header_layout.setContentsMargins(10, 6, 10, 6)
        self._header_layout.setSpacing(0)
        pill_container = self._create_scope_switch()
        separator = QLabel("|")
        separator.setObjectName("skillsSeparator")
        self.count_label = QLabel()
        self.count_label.setObjectName("skillsCountLabel")
        self.scroll_navigator = SkillsScrollNavigator(header_widget)
        self._header_layout.addWidget(pill_container)
        self._header_layout.addSpacing(10)
        self._header_layout.addWidget(separator)
        self._header_layout.addSpacing(10)
        self._header_layout.addWidget(self.count_label)
        self._header_layout.setStretchFactor(self.count_label, 1)
        self._header_layout.addWidget(self.scroll_navigator)
        self._main_layout.addWidget(header_widget)

    def _create_scope_switch(self) -> QWidget:
        """创建官方/第三方 Pill 切换按钮。"""
        pill_container = QWidget()
        pill_container.setObjectName("skillsPillContainer")
        pill_layout = QHBoxLayout(pill_container)
        pill_layout.setContentsMargins(2, 2, 2, 2)
        pill_layout.setSpacing(2)
        self.official_btn = QPushButton()
        self.official_btn.setObjectName("skillsPillButton")
        self.official_btn.setProperty("active", "true")
        self.official_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.official_btn.clicked.connect(lambda: self._switch_tab(0))
        self.thirdparty_btn = QPushButton()
        self.thirdparty_btn.setObjectName("skillsPillButton")
        self.thirdparty_btn.setProperty("active", "false")
        self.thirdparty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thirdparty_btn.clicked.connect(lambda: self._switch_tab(1))
        pill_layout.addWidget(self.official_btn)
        pill_layout.addWidget(self.thirdparty_btn)
        return pill_container

    def _create_pages(self) -> None:
        """创建两个插件页面并接入当前页滚动导航。"""
        self.stacked_widget = QStackedWidget(self)
        self.stacked_widget.setMinimumWidth(0)
        official = self._create_skills_page()
        thirdparty = self._create_skills_page()
        self.official_page, self.official_layout, official_scroll = official
        self.thirdparty_page, self.thirdparty_layout, thirdparty_scroll = thirdparty
        self.stacked_widget.addWidget(self.official_page)
        self.stacked_widget.addWidget(self.thirdparty_page)
        self._scroll_areas = {0: official_scroll, 1: thirdparty_scroll}
        self._container_layouts = {0: self.official_layout, 1: self.thirdparty_layout}
        self._scroll_size_constraints = {
            scroll: (scroll.minimumHeight(), scroll.maximumHeight())
            for scroll in self._scroll_areas.values()
        }
        self._scroll_frame_shapes = {
            scroll: scroll.frameShape() for scroll in self._scroll_areas.values()
        }
        for scroll_area in self._scroll_areas.values():
            self.scroll_navigator.watch(scroll_area)
        self.scroll_navigator.set_current(official_scroll)
        self._main_layout.addWidget(self.stacked_widget)

    def _create_skills_page(self):
        """创建一个技能页面及其横向滚动区域。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("skillsContainer")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(*RELAXED_CONTAINER_MARGINS)
        container_layout.setSpacing(RELAXED_CONTAINER_SPACING)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)
        return page, container_layout, scroll_area

    def set_display_mode(self, mode: str) -> None:
        """切换宽松/紧凑布局，不重建插件按钮或插件实例。

        Args:
            mode: ``relaxed`` 或 ``compact``。

        Raises:
            ValueError: 模式不在支持集合中时抛出。
        """
        if mode not in SKILLS_PANEL_MODES:
            raise ValueError(f"未知技能面板模式: {mode}")
        if mode == self._display_mode:
            return
        self._display_mode = mode
        compact = mode == SKILLS_PANEL_COMPACT
        self.setProperty("compact", "true" if compact else "false")
        self.style().unpolish(self)
        self.style().polish(self)
        scroll_values = {
            index: scroll_area.horizontalScrollBar().value()
            for index, scroll_area in self._scroll_areas.items()
        }
        row_height = self._compact_row_height() if compact else 0
        self._apply_button_mode(compact, row_height)
        self._apply_scroll_mode(compact, row_height)
        self._place_stacked_widget(compact)
        for index, value in scroll_values.items():
            self._scroll_areas[index].horizontalScrollBar().setValue(value)
        self._apply_panel_height(compact, row_height)
        self.count_label.setVisible(not compact)
        if compact:
            self.scroll_navigator.set_row_height(row_height)
        self.scroll_navigator.set_active(compact)
        QTimer.singleShot(0, self._sync_compact_metrics)
        self._schedule_navigation_refresh()

    def _compact_row_height(self) -> int:
        """读取切换按钮行高；未显示时使用 sizeHint，显示后使用实际高度。"""
        if self.isVisible():
            return max(self.official_btn.height(), self.thirdparty_btn.height())
        return max(
            self.official_btn.sizeHint().height(),
            self.thirdparty_btn.sizeHint().height(),
        )

    def _apply_button_mode(self, compact: bool, row_height: int) -> None:
        """向未分组按钮和分组控件传播显示模式与统一行高。"""
        for layout in self._container_layouts.values():
            for index in range(layout.count()):
                item = layout.itemAt(index)
                widget = item.widget() if item else None
                if isinstance(widget, (SkillButton, PluginGroupWidget)):
                    widget.set_compact(compact, row_height)

    def _apply_scroll_mode(self, compact: bool, row_height: int) -> None:
        """切换滚动策略、内容间距和页面高度。"""
        policy = (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff if compact
            else Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        margins = COMPACT_CONTAINER_MARGINS if compact else RELAXED_CONTAINER_MARGINS
        spacing = COMPACT_CONTAINER_SPACING if compact else RELAXED_CONTAINER_SPACING
        for index, scroll_area in self._scroll_areas.items():
            scroll_area.setHorizontalScrollBarPolicy(policy)
            self._container_layouts[index].setContentsMargins(*margins)
            self._container_layouts[index].setSpacing(spacing)
            if compact:
                scroll_area.setFrameShape(QFrame.Shape.NoFrame)
                scroll_area.setFixedHeight(row_height)
            else:
                scroll_area.setFrameShape(self._scroll_frame_shapes[scroll_area])
                minimum, maximum = self._scroll_size_constraints[scroll_area]
                scroll_area.setMinimumHeight(minimum)
                scroll_area.setMaximumHeight(maximum)

    def _place_stacked_widget(self, compact: bool) -> None:
        """紧凑时把同一 Stack 移入 Header，宽松时移回第二行。"""
        if compact:
            self._main_layout.removeWidget(self.stacked_widget)
            index = self._header_layout.indexOf(self.scroll_navigator)
            self._header_layout.insertWidget(index, self.stacked_widget, 1)
            self._header_layout.setStretchFactor(self.count_label, 0)
            policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        else:
            self._header_layout.removeWidget(self.stacked_widget)
            self._header_layout.setStretchFactor(self.count_label, 1)
            self._main_layout.addWidget(self.stacked_widget)
            policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.stacked_widget.setSizePolicy(policy)
        self.stacked_widget.show()

    def _apply_panel_height(self, compact: bool, row_height: int) -> None:
        """按模式设置面板高度，紧凑高度包含既有容器边距。"""
        if compact:
            height = (
                row_height + 2 * SKILLS_HEADER_VERTICAL_MARGIN
                + 2 * SKILLS_PILL_VERTICAL_MARGIN
            )
            self.setFixedHeight(height)
            return
        self.setMinimumHeight(RELAXED_PANEL_MIN_HEIGHT)
        self.setMaximumHeight(RELAXED_PANEL_MAX_HEIGHT)

    def _sync_compact_metrics(self) -> None:
        """在显示、语言和主题变化后同步紧凑行高。"""
        if self._display_mode != SKILLS_PANEL_COMPACT:
            return
        row_height = self._compact_row_height()
        self._apply_button_mode(True, row_height)
        self._apply_scroll_mode(True, row_height)
        self.scroll_navigator.set_row_height(row_height)
        self._apply_panel_height(True, row_height)
        self._sync_compact_content_width()

    def _sync_compact_content_width(self) -> None:
        """同步紧凑内容宽度，避免分组收起后保留旧滚动范围。"""
        if self._display_mode != SKILLS_PANEL_COMPACT:
            return
        scroll_area = self._scroll_areas[self.stacked_widget.currentIndex()]
        content = scroll_area.widget()
        width = max(content.sizeHint().width(), scroll_area.viewport().width())
        content.resize(width, content.height())
        self.scroll_navigator.refresh()

    def _schedule_navigation_refresh(self) -> None:
        """在布局完成后重新计算当前页溢出。"""
        QTimer.singleShot(0, self.scroll_navigator.refresh)

    def _switch_tab(self, index: int):
        """切换标签页"""
        self.stacked_widget.setCurrentIndex(index)

        is_official = (index == 0)
        self.official_btn.setProperty("active", "true" if is_official else "false")
        self.thirdparty_btn.setProperty("active", "false" if is_official else "true")

        self.official_btn.style().unpolish(self.official_btn)
        self.official_btn.style().polish(self.official_btn)
        self.thirdparty_btn.style().unpolish(self.thirdparty_btn)
        self.thirdparty_btn.style().polish(self.thirdparty_btn)

        # 更新计数（按插件数量统计，分组不作为独立项计数）
        if self.plugin_manager is not None:
            if is_official:
                count = len(self.plugin_manager.get_official_plugins())
            else:
                count = len(self.plugin_manager.get_thirdparty_plugins())
        else:
            target_layout = self.official_layout if is_official else self.thirdparty_layout
            count = target_layout.count()
        self.count_label.setText(tr("skills_panel", "header.plugin_count", count=count))
        self.scroll_navigator.set_current(self._scroll_areas[index])
        self._schedule_navigation_refresh()

    def add_skill_button(self, plugin, is_official: bool):
        """
        添加一个技能按钮到相应的标签页

        Args:
            plugin: 插件对象
            is_official: 是否为官方插件
        """
        skill_btn = self._create_skill_button(plugin)
        if skill_btn is None:
            return

        # 添加到相应的布局
        if is_official:
            self.official_layout.addWidget(skill_btn)
        else:
            self.thirdparty_layout.addWidget(skill_btn)

    def _create_skill_button(self, plugin):
        """创建并连接一个技能按钮

        供未分组插件与分组控件（PluginGroupWidget）共用，
        保证按钮外观与激活逻辑一致。

        Args:
            plugin: 插件对象

        Returns:
            SkillButton 实例；获取插件信息失败时返回 None
        """
        # 获取插件图标和描述
        try:
            icon = getattr(plugin, 'skill_icon', None)
            if icon is None or (isinstance(icon, QIcon) and icon.isNull()):
                # 使用默认图标
                style = self.style()
                icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)

            name = plugin.plugin_name
            description = getattr(plugin, 'skill_description', name)
        except Exception as e:
            self._logger.error(get_name(), f'获取插件信息失败: {e}')
            return None

        # 创建技能按钮
        skill_btn = SkillButton(icon, name, description, self)
        if self._display_mode == SKILLS_PANEL_COMPACT:
            skill_btn.set_compact(True, self._compact_row_height())
        # 重建按钮（语言切换 / 插件集合刷新）后恢复激活插件的高亮
        if plugin is self._active_plugin:
            skill_btn.set_active(True)
            self._active_button = skill_btn

        # 绑定点击事件，传递按钮和插件对象
        skill_btn.clicked.connect(lambda checked=False, btn=skill_btn, p=plugin: self._on_skill_clicked(btn, p))
        return skill_btn

    def _on_skill_clicked(self, button, plugin):
        """处理技能按钮点击事件"""
        # 清除之前的激活状态
        if self._active_button and self._active_button != button:
            self._active_button.set_active(False)

        # 设置新按钮为激活状态
        if button and isinstance(button, SkillButton):
            button.set_active(True)
            self._active_button = button
            self._active_plugin = plugin

        self.skill_clicked.emit(plugin)

    def load_skills_from_manager(self):
        """从插件管理器加载所有技能（按 get_sorted_plugins 返回的统一顺序混排分组与未分组插件）"""
        if self.plugin_manager is None:
            return

        try:
            # 清空现有按钮
            self._clear_layout(self.official_layout)
            self._clear_layout(self.thirdparty_layout)

            # 清除激活状态（重要：因为旧按钮已被删除）
            self._active_button = None

            # 按 scope 渲染：分组控件 + 未分组插件按钮
            for scope, layout in (("official", self.official_layout),
                                  ("thirdparty", self.thirdparty_layout)):
                for item in self.plugin_manager.get_sorted_plugins(scope):
                    if item[0] == "group":
                        self._add_group_widget(layout, item[1], item[2])
                    else:
                        skill_btn = self._create_skill_button(item[1])
                        if skill_btn is not None:
                            layout.addWidget(skill_btn)

            # 更新当前标签页的计数
            self._switch_tab(self.stacked_widget.currentIndex())

            # 记录本次渲染时各插件的显示名，供语言变化时判断是否需要重建
            self._rendered_names = self._collect_plugin_names()
            QTimer.singleShot(0, self._sync_compact_content_width)
            self._schedule_navigation_refresh()

        except Exception as e:
            self._logger.error(get_name(), f'从插件管理器加载技能失败: {e}')

    def _collect_plugin_names(self) -> dict:
        """收集当前各插件显示名快照（键为插件实例 id，值为 plugin_name）"""
        names = {}
        for scope in ("official", "thirdparty"):
            for item in self.plugin_manager.get_sorted_plugins(scope):
                plugins = item[2] if item[0] == "group" else (item[1],)
                for plugin in plugins:
                    names[id(plugin)] = plugin.plugin_name
        return names

    def _add_group_widget(self, layout, group, plugins):
        """向布局添加一个分组折叠控件

        Args:
            layout: 目标布局（官方/第三方页面容器）
            group: PluginGroup 分组数据
            plugins: 组内插件实例列表
        """
        group_widget = PluginGroupWidget(group, plugins, self._create_skill_button)
        if self._display_mode == SKILLS_PANEL_COMPACT:
            group_widget.set_compact(True, self._compact_row_height())
        group_widget.toggled.connect(self._on_group_toggled)
        layout.addWidget(group_widget)

    def _on_group_toggled(self, _expanded: bool) -> None:
        """分组展开尺寸变化后重新计算内容宽度和溢出。"""
        QTimer.singleShot(0, self._sync_compact_content_width)
        self._schedule_navigation_refresh()

    def _clear_layout(self, layout):
        """清空布局中的所有控件"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_all_active_states(self):
        """清除所有按钮的激活状态"""
        for layout in [self.official_layout, self.thirdparty_layout]:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item:
                    widget = item.widget()
                    if isinstance(widget, SkillButton):
                        widget.set_active(False)

        self._active_button = None

    def clear_active_state(self):
        """
        公共方法：清除所有按钮的激活状态
        用于当工作区被清空时，取消所有按钮的高亮
        """
        self._clear_all_active_states()

    def retranslate_ui(self):
        """语言变化后按新语言重建技能按钮（插件名未变则完全不动面板）

        插件显示名来自 ``plugin.plugin_name``：本地化取词的插件（如 RoboSpine）
        名字会随语言变化，而多数插件用的是固定品牌名（如 ``"Blueprint\\nOpenCV"``），
        此时重建只会得到同样的文案。故先比对显示名快照，**只有确实变化才重建**
        ——否则会白白重置用户的分组展开状态与滚动位置。

        重建只涉及按钮（``load_skills_from_manager``），不重载插件、不触碰插件
        实例与工作区内容；展开状态与激活高亮在重建后恢复。
        """
        if self.plugin_manager is None:
            return
        if self._collect_plugin_names() == self._rendered_names:
            return
        expanded_groups = self._expanded_group_ids()
        self.load_skills_from_manager()
        self._restore_expanded_groups(expanded_groups)

    def _group_widgets(self) -> list:
        """收集面板内全部分组控件（官方 + 第三方页）"""
        widgets = []
        for layout in (self.official_layout, self.thirdparty_layout):
            for index in range(layout.count()):
                item = layout.itemAt(index)
                widget = item.widget() if item else None
                if isinstance(widget, PluginGroupWidget):
                    widgets.append(widget)
        return widgets

    def _expanded_group_ids(self) -> set:
        """当前处于展开状态的分组 id 集合（重建按钮时保留用户的展开状态）"""
        return {w.group.id for w in self._group_widgets() if w.is_expanded()}

    def _restore_expanded_groups(self, group_ids: set) -> None:
        """重建后恢复分组的展开状态

        Args:
            group_ids: 需要展开的分组 id 集合
        """
        if not group_ids:
            return
        for widget in self._group_widgets():
            if widget.group.id in group_ids:
                widget.set_expanded(True)

    def refresh_skills(self):
        """刷新技能列表"""
        if self.plugin_manager:
            self.plugin_manager.reload_plugins()
            self.load_skills_from_manager()
