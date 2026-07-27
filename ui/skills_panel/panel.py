from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QLabel,
    QStyle
)
from PySide6.QtCore import Signal, Qt

from PySide6.QtGui import QIcon

from utils.logging_tools import LoggerManager, get_name
from .skill_button import SkillButton
from .plugin_group_widget import PluginGroupWidget


class SkillsPanel(QWidget):
    """
    技能面板组件
    支持横向滚动，包含官方技能和第三方技能两个标签页
    """

    # 信号：
    skill_clicked = Signal(object)  # 发送插件对象

    def __init__(self, parent: QWidget):
        super().__init__(parent=parent)
        self.plugin_manager = None
        self._active_button = None  # 当前激活的按钮
        self._logger = LoggerManager()
        self._init_ui()

    def set_plugin_manager(self, plugin_manager):
        """设置插件管理器"""
        self.plugin_manager = plugin_manager

    def _init_ui(self):
        """初始化 UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ========== Header（Pill 切换区） ==========
        header_widget = QWidget()
        header_widget.setObjectName("skillsPanelHeader")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 6, 10, 6)
        header_layout.setSpacing(0)

        # Pill 容器
        pill_container = QWidget()
        pill_container.setObjectName("skillsPillContainer")
        pill_layout = QHBoxLayout(pill_container)
        pill_layout.setContentsMargins(2, 2, 2, 2)
        pill_layout.setSpacing(2)

        # 官方功能按钮
        self.official_btn = QPushButton("官方功能")
        self.official_btn.setObjectName("skillsPillButton")
        self.official_btn.setProperty("active", "true")
        # 可访问性：保留默认可聚焦策略，支持键盘 Tab 导航
        self.official_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.official_btn.clicked.connect(lambda: self._switch_tab(0))

        # 第三方功能按钮
        self.thirdparty_btn = QPushButton("第三方功能")
        self.thirdparty_btn.setObjectName("skillsPillButton")
        self.thirdparty_btn.setProperty("active", "false")
        # 可访问性：保留默认可聚焦策略，支持键盘 Tab 导航
        self.thirdparty_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.thirdparty_btn.clicked.connect(lambda: self._switch_tab(1))

        pill_layout.addWidget(self.official_btn)
        pill_layout.addWidget(self.thirdparty_btn)

        # 分隔线
        separator = QLabel("|")
        separator.setObjectName("skillsSeparator")

        # 计数标签
        self.count_label = QLabel("0 Plugins")
        self.count_label.setObjectName("skillsCountLabel")

        header_layout.addWidget(pill_container)
        header_layout.addSpacing(10)
        header_layout.addWidget(separator)
        header_layout.addSpacing(10)
        header_layout.addWidget(self.count_label)
        header_layout.addStretch()

        main_layout.addWidget(header_widget)

        # ========== 内容区（StackedWidget） ==========
        self.stacked_widget = QStackedWidget()

        # 官方功能页面
        self.official_page, self.official_layout = self._create_skills_page()
        self.stacked_widget.addWidget(self.official_page)

        # 第三方功能页面
        self.thirdparty_page, self.thirdparty_layout = self._create_skills_page()
        self.stacked_widget.addWidget(self.thirdparty_page)

        main_layout.addWidget(self.stacked_widget)

    def _create_skills_page(self):
        """创建一个技能页面（包含滚动区域和按钮布局）"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 创建横向滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 创建容器 widget 用于放置技能按钮
        container = QWidget()
        container.setObjectName("skillsContainer")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(4, 2, 4, 2)
        container_layout.setSpacing(4)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)

        return page, container_layout

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
        self.count_label.setText(f"{count} Plugins")

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

        self.skill_clicked.emit(plugin)

    def load_skills_from_manager(self):
        """从插件管理器加载所有技能（按「分组 → 组内 → 未分组」顺序渲染）"""
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

        except Exception as e:
            self._logger.error(get_name(), f'从插件管理器加载技能失败: {e}')

    def _add_group_widget(self, layout, group, plugins):
        """向布局添加一个分组折叠控件

        Args:
            layout: 目标布局（官方/第三方页面容器）
            group: PluginGroup 分组数据
            plugins: 组内插件实例列表
        """
        group_widget = PluginGroupWidget(group, plugins, self._create_skill_button)
        layout.addWidget(group_widget)

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

    def refresh_skills(self):
        """刷新技能列表"""
        if self.plugin_manager:
            self.plugin_manager.reload_plugins()
            self.load_skills_from_manager()
