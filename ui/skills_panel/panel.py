from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTabWidget, QScrollArea,
    QStyle, QToolButton, QLayout
)
from PySide6.QtCore import (
    Signal, Qt, QSize
)

from PySide6.QtGui import QIcon

from utils.logging_tools import LoggerManager, get_name

class SkillButton(QToolButton):
    """
    MS Office 风格的技能按钮
    图标在上，文字在下
    """

    def __init__(self, icon: QIcon, name: str, description: str, parent=None):
        super().__init__(parent)
        self.skill_name = name
        self.skill_description = description
        self._is_active = False  # 是否激活

        # 设置按钮属性
        self.setIcon(icon)
        self._process_display_text(name)
        self.setIconSize(QSize(28, 28))  # 图标尺寸
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(60, 70)  # 紧凑的按钮尺寸
        self.setToolTip(f"{name}\n{description}")

        # 启用自动提升效果（悬停时突出显示）
        self.setAutoRaise(True)

        # 应用样式
        self._apply_style()

    def set_active(self, active: bool):
        """
        设置按钮激活状态

        Args:
            active: 是否激活
        """
        self._is_active = active
        self._apply_style()

    def is_active(self) -> bool:
        """返回按钮是否激活"""
        return self._is_active

    def _process_display_text(self, text: str):
        """
        处理显示文本
        - 允许插件设计者自行决定换行位置（使用 \n）
        - 每行最多5个字，超出用...替代
        """
        max_chars_per_line = 5

        # 如果文本包含换行符，按换行符分割
        if '\n' in text:
            lines = text.split('\n')
        else:
            # 没有换行符，根据长度决定
            if len(text) > max_chars_per_line:
                # 尝试在中间位置分割
                mid = len(text) // 2
                lines = [text[:mid], text[mid:]]
            else:
                lines = [text]

        # 最多显示两行
        if len(lines) > 2:
            lines = lines[:2]

        # 处理每一行，确保不超过5个字
        processed_lines = []
        for line in lines:
            line = line.strip()
            if len(line) > max_chars_per_line:
                processed_lines.append(line[:max_chars_per_line] + "...")
            else:
                processed_lines.append(line)

        # 合并成显示文本
        display_text = '\n'.join(processed_lines)
        self.setText(display_text)

    def _apply_style(self):
        """应用 FluentUI3 风格的样式"""
        if self._is_active:
            # 激活状态样式 - 使用 FluentUI3 变量
            self.setStyleSheet("""
                QToolButton {
                    border: 2px solid #0078D4;
                    border-radius: 6px;
                    padding: 2px;
                    background-color: rgba(0, 120, 212, 15);
                    color: #005A9E;
                    text-align: top;
                    font-weight: 500;
                    font-size: 10px;
                }
            """)
        else:
            # 普通状态样式 - 使用 FluentUI3 变量
            self.setStyleSheet("""
                QToolButton {
                    border: 1px solid transparent;
                    border-radius: 6px;
                    padding: 3px;
                    background-color: transparent;
                    color: #1F1F1F;
                    text-align: top;
                    font-size: 10px;
                }
                QToolButton:hover {
                    background-color: rgba(0, 0, 0, 5);
                    border: 1px solid rgba(0, 0, 0, 10);
                }
                QToolButton:pressed {
                    background-color: rgba(0, 0, 0, 10);
                    border: 1px solid rgba(0, 0, 0, 20);
                }
            """)


class SkillsPanel(QWidget):
    """
    Skills Panel - 类似 MS Office 工具栏的技能面板
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

        # 创建 Tab Widget
        tab_widget = QTabWidget()
        tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        tab_widget.setDocumentMode(True)  # 现代化外观

        # 创建两个标签页
        self.official_tab = self._create_skills_tab("官方功能")
        self.thirdparty_tab = self._create_skills_tab("第三方功能")

        tab_widget.addTab(self.official_tab, "官方功能")
        tab_widget.addTab(self.thirdparty_tab, "第三方功能")

        # 应用 Tab 样式 - Office 风格
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background: #F5F5F5;
            }
            QTabBar::tab {
                background: #E8E8E8;
                padding: 2px 10px;
                margin-right: 1px;
                border-top-left-radius: 3px;
                border-top-right-radius: 3px;
                min-height: 16px;
                font-size: 11px;
                border: none;
            }
            QTabBar::tab:selected {
                background: #F5F5F5;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover:!selected {
                background: #DCDCDC;
            }
        """)

        # 设置面板背景色
        self.setStyleSheet("background-color: #F5F5F5; border-bottom: 1px solid #D0D0D0;")

        main_layout.addWidget(tab_widget)

    def _create_skills_tab(self, tab_name: str) -> QWidget:
        """创建一个技能标签页"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 创建横向滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 滚动区域样式 - 现代细线风格，悬浮显示
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: #F5F5F5;
            }
            /* 滚动条轨道 - 默认透明 */
            QScrollBar:horizontal {
                height: 6px;
                background: transparent;
                margin: 0px;
                border-radius: 3px;
            }
            /* 滚动条滑块 - 默认透明隐藏 */
            QScrollBar::handle:horizontal {
                background: transparent;
                min-width: 30px;
                border-radius: 3px;
            }
            /* 滚动区域悬停时显示滚动条 */
            QScrollArea:hover QScrollBar::handle:horizontal {
                background: rgba(160, 160, 160, 0.8);
            }
            /* 滚动条滑块悬停效果 */
            QScrollArea:hover QScrollBar::handle:horizontal:hover {
                background: rgba(128, 128, 128, 1);
            }
            /* 滚动时保持显示 */
            QScrollBar::handle:horizontal:active {
                background: rgba(128, 128, 128, 1);
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }
        """)

        # 创建容器 widget 用于放置技能按钮
        container = QWidget()
        container.setStyleSheet("background-color: #F5F5F5;")
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 3, 6, 5)
        container_layout.setSpacing(6)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)

        # 保存布局引用，方便后续添加技能按钮
        if "官方" in tab_name:
            self.official_layout = container_layout
        else:
            self.thirdparty_layout = container_layout

        return tab_widget

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
                        if widget._is_active:
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
