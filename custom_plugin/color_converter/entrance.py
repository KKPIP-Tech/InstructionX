"""
颜色转换插件 - 第三方插件示例
提供颜色格式转换功能
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QLineEdit, QComboBox
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class ColorConverterPlugin(IPlugin):
    """颜色转换插件"""
    
    @property
    def plugin_name(self) -> str:
        return "颜色转换"
    
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("颜色格式转换工具")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # HEX 转 RGB
        hex_group = QGroupBox("HEX 转 RGB")
        hex_layout = QVBoxLayout()
        
        hex_input = QLineEdit()
        hex_input.setPlaceholderText("输入 HEX 颜色 (如 #FF5733)")
        hex_layout.addWidget(hex_input)
        
        rgb_output = QLineEdit()
        rgb_output.setReadOnly(True)
        rgb_output.setPlaceholderText("RGB 结果")
        hex_layout.addWidget(rgb_output)
        
        hex_btn = QPushButton("转换")
        hex_btn.clicked.connect(
            lambda: rgb_output.setText(service.hex_to_rgb(hex_input.text().strip()))
        )
        hex_layout.addWidget(hex_btn)
        
        hex_group.setLayout(hex_layout)
        layout.addWidget(hex_group)
        
        layout.addStretch()
        return widget
