from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, 
    QTabWidget, QScrollArea,
    QStyle, QToolButton, QLayout
)
from PySide6.QtCore import (
    Signal, Qt, QSize
)

from PySide6.QtGui import QIcon

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
        self.setIconSize(QSize(36, 36))  # 减小图标尺寸
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(60, 80)  # 恢复原有尺寸
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
        - 每行最多4个字，超出用...替代
        """
        max_chars_per_line = 4
        
        # 如果文本包含换行符，按换行符分割
        if '\n' in text:
            lines = text.split('\n')
        else:
            # 没有换行符，自动分成两行
            if len(text) > max_chars_per_line:
                lines = [text[:max_chars_per_line], text[max_chars_per_line:]]
            else:
                lines = [text]
        
        # 最多显示两行
        if len(lines) > 2:
            lines = lines[:2]
        
        # 处理每一行，确保不超过4个字
        processed_lines = []
        for line in lines:
            if len(line) > max_chars_per_line:
                processed_lines.append(line[:max_chars_per_line] + "...")
            else:
                processed_lines.append(line)
        
        # 合并成显示文本
        display_text = '\n'.join(processed_lines)
        self.setText(display_text)
    
    def _apply_style(self):
        """应用 MS Office 风格的样式"""
        if self._is_active:
            # 激活状态样式（减小padding，使用1px边框）
            self.setStyleSheet("""
                QToolButton {
                    border: 1px solid #0078D4;
                    border-radius: 4px;
                    padding: 2px;
                    background-color: #E6F2FF;
                    color: #0056B3;
                    text-align: top;
                }
            """)
        else:
            # 普通状态样式
            self.setStyleSheet("""
                QToolButton {
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 4px;
                    background-color: transparent;
                    color: #333333;
                    text-align: top;
                }
                QToolButton:hover {
                    background-color: #E5F3FF;
                    border: 1px solid #B3D9FF;
                }
                QToolButton:pressed {
                    background-color: #CCE8FF;
                    border: 1px solid #99CCFF;
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
        
        # 应用 Tab 样式
        tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #CCCCCC;
                border-top: none;
                background: white;
            }
            QTabBar::tab {
                background: #F0F0F0;
                padding: 2px 12px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                min-height: 20px;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: white;
                border-bottom: 2px solid #0078D4;
            }
            QTabBar::tab:hover:!selected {
                background: #E8E8E8;
            }
        """)
        
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
        
        # 滚动区域样式
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: white;
            }
            QScrollBar:horizontal {
                height: 12px;
                background: #F0F0F0;
                margin: 0px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal {
                background: #C0C0C0;
                min-width: 30px;
                border-radius: 6px;
            }
            QScrollBar::handle:horizontal:hover {
                background: #A0A0A0;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
            }
        """)
        
        # 创建容器 widget 用于放置技能按钮
        container = QWidget()
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(8, 8, 8, 8)
        container_layout.setSpacing(8)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
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
            if icon is None:
                # 使用默认图标
                style = self.style()
                icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            
            name = plugin.plugin_name
            description = getattr(plugin, 'skill_description', name)
        except Exception as e:
            print(f"Error getting plugin info: {e}")
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
        print(f"\n[DEBUG] _on_skill_clicked: 点击按钮 '{button.skill_name}'")
        
        # 打印当前状态
        current_active = self._active_button
        print(f"[DEBUG] _on_skill_clicked: 当前 _active_button = {current_active.skill_name if current_active else None}")
        
        # 清除之前的激活状态
        if self._active_button and self._active_button != button:
            print(f"[DEBUG] _on_skill_clicked: 清除之前激活按钮 '{self._active_button.skill_name}'")
            self._active_button.set_active(False)
        
        # 设置新按钮为激活状态
        if button and isinstance(button, SkillButton):
            button.set_active(True)
            self._active_button = button
            print(f"[DEBUG] _on_skill_clicked: 设置新激活按钮 '{button.skill_name}'")
        
        self.skill_clicked.emit(plugin)
        
        # 获取插件的 widget 并显示（这里可以在对话框中显示，或在主窗口中显示）
        # 根据实际需求调整
        try:
            widget = plugin.get_widget(parent=self)
            if widget:
                # 这里可以实现显示逻辑，例如在对话框中显示
                print(f"Skill '{plugin.plugin_name}' clicked")
        except Exception as e:
            print(f"Error getting widget for plugin: {e}")
    
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
            print(f"Error loading skills from manager: {e}")
    
    def _clear_layout(self, layout):
        """清空布局中的所有控件"""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
    
    def _clear_all_active_states(self):
        """清除所有按钮的激活状态"""
        print("[DEBUG] _clear_all_active_states: 开始清除所有高亮")
        
        active_count = 0
        for layout in [self.official_layout, self.thirdparty_layout]:
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item:
                    widget = item.widget()
                    if isinstance(widget, SkillButton):
                        if widget._is_active:
                            active_count += 1
                            print(f"[DEBUG] _clear_all_active_states: 清除按钮 '{widget.skill_name}' 高亮")
                        widget.set_active(False)
        
        print(f"[DEBUG] _clear_all_active_states: 完成，共清除 {active_count} 个按钮, _active_button 设置为 None")
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
