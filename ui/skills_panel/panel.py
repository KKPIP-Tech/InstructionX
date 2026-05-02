from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QScrollArea, QPushButton, QLabel,
    QStyle
)
from PySide6.QtCore import Signal, Qt

from PySide6.QtGui import QIcon

from utils.logging_tools import LoggerManager, get_name
from .skill_button import SkillButton


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
        pill_layout.setContentsMargins(4, 4, 4, 4)
        pill_layout.setSpacing(4)

        # 官方功能按钮
        self.official_btn = QPushButton("官方功能")
        self.official_btn.setObjectName("skillsPillButton")
        self.official_btn.setProperty("active", "true")
        self.official_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.official_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.official_btn.clicked.connect(lambda: self._switch_tab(0))

        # 第三方功能按钮
        self.thirdparty_btn = QPushButton("第三方功能")
        self.thirdparty_btn.setObjectName("skillsPillButton")
        self.thirdparty_btn.setProperty("active", "false")
        self.thirdparty_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
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

        # 更新计数
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
            self._logger.error(get_name(), f'Error getting plugin info: {e}')
            return

        # 创建技能按钮
        skill_btn = SkillButton(icon, name, description, self)

        # 绑定点击事件，传递按钮和插件对象
        skill_btn.clicked.connect(lambda checked=False, btn=skill_btn, p=plugin: self._on_skill_clicked(btn, p))

        # 添加到相应的布局
        if is_official:
            self.official_layout.addWidget(skill_btn)
        else:
            self.thirdparty_layout.addWidget(skill_btn)

    def _on_skill_clicked(self, button, plugin):
        """处理技能按钮点击事件"""
        self._logger.debug(get_name(), f"_on_skill_clicked: 点击按钮 '{button.skill_name}'")

        # 打印当前状态
        current_active = self._active_button
        self._logger.debug(get_name(), f"_on_skill_clicked: 当前 _active_button = {current_active.skill_name if current_active else None}")

        # 清除之前的激活状态
        if self._active_button and self._active_button != button:
            self._logger.debug(get_name(), f"_on_skill_clicked: 清除之前激活按钮 '{self._active_button.skill_name}'")
            self._active_button.set_active(False)

        # 设置新按钮为激活状态
        if button and isinstance(button, SkillButton):
            button.set_active(True)
            self._active_button = button
            self._logger.debug(get_name(), f"_on_skill_clicked: 设置新激活按钮 '{button.skill_name}'")

        self.skill_clicked.emit(plugin)

    def load_skills_from_manager(self):
        """从插件管理器加载所有技能"""
        if self.plugin_manager is None:
            return

        try:
            # 清空现有按钮
            self._clear_layout(self.official_layout)
            self._clear_layout(self.thirdparty_layout)

            # 清除激活状态（重要：因为旧按钮已被删除）
            self._active_button = None

            # 加载官方技能
            official_plugins = self.plugin_manager.get_official_plugins()
            for plugin in official_plugins:
                self.add_skill_button(plugin, is_official=True)

            # 加载第三方技能
            thirdparty_plugins = self.plugin_manager.get_thirdparty_plugins()
            for plugin in thirdparty_plugins:
                self.add_skill_button(plugin, is_official=False)

            # 更新当前标签页的计数
            current_index = self.stacked_widget.currentIndex()
            self._switch_tab(current_index)

        except Exception as e:
            self._logger.error(get_name(), f'Error loading skills from manager: {e}')

    def _clear_layout(self, layout):
        """清空布局中的所有控件"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _clear_all_active_states(self):
        """清除所有按钮的激活状态"""
        self._logger.debug(get_name(), "_clear_all_active_states: 开始清除所有高亮")

        active_count = 0
        for layout in [self.official_layout, self.thirdparty_layout]:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item:
                    widget = item.widget()
                    if isinstance(widget, SkillButton):
                        if widget.is_active():
                            active_count += 1
                            self._logger.debug(get_name(), f"_clear_all_active_states: 清除按钮 '{widget.skill_name}' 高亮")
                        widget.set_active(False)

        self._logger.debug(get_name(), f"_clear_all_active_states: 完成，共清除 {active_count} 个按钮, _active_button 设置为 None")
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
