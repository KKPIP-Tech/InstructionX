"""
文本格式化插件 - 官方插件示例
提供常用的文本格式化功能
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QLineEdit
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""
    
    @property
    def plugin_name(self) -> str:
        return "文本\n格式化"
    
    @property
    def skill_icon(self) -> QIcon:
        # 使用系统标准图标
        from PySide6.QtWidgets import QApplication
        return QApplication.style().standardIcon(
            QApplication.style().StandardPixmap.SP_FileIcon
        )
    
    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("文本格式化工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 转大写
        uppercase_group = QGroupBox("转换为大写")
        uppercase_layout = QVBoxLayout()
        uppercase_input = QLineEdit()
        uppercase_input.setPlaceholderText("输入文本...")
        uppercase_layout.addWidget(uppercase_input)
        
        uppercase_btn = QPushButton("转换为大写")
        uppercase_btn.clicked.connect(
            lambda: uppercase_input.setText(service.to_uppercase(uppercase_input.text()))
        )
        uppercase_layout.addWidget(uppercase_btn)
        
        uppercase_group.setLayout(uppercase_layout)
        layout.addWidget(uppercase_group)
        
        # 转小写
        lowercase_group = QGroupBox("转换为小写")
        lowercase_layout = QVBoxLayout()
        lowercase_input = QLineEdit()
        lowercase_input.setPlaceholderText("输入文本...")
        lowercase_layout.addWidget(lowercase_input)
        
        lowercase_btn = QPushButton("转换为小写")
        lowercase_btn.clicked.connect(
            lambda: lowercase_input.setText(service.to_lowercase(lowercase_input.text()))
        )
        lowercase_layout.addWidget(lowercase_btn)
        
        lowercase_group.setLayout(lowercase_layout)
        layout.addWidget(lowercase_group)
        
        layout.addStretch()
        return widget
