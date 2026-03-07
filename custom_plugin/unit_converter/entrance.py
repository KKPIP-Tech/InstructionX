"""
单位转换插件 - 第三方插件示例
提供常用单位转换功能
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QComboBox, QLineEdit, QMessageBox
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class UnitConverterPlugin(IPlugin):
    """单位转换插件"""
    
    @property
    def plugin_name(self) -> str:
        return "单位\n转换"
    
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("单位转换工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 长度转换
        length_group = QGroupBox("长度转换")
        length_layout = QVBoxLayout()
        
        length_input_layout = QVBoxLayout()
        length_input_layout.addWidget(QLabel("数值:"))
        self.length_input = QLineEdit()
        length_input_layout.addWidget(self.length_input)
        
        unit_layout = QVBoxLayout()
        self.length_from = QComboBox()
        self.length_from.addItems(['m', 'km', 'cm', 'mm', 'inch', 'ft'])
        self.length_to = QComboBox()
        self.length_to.addItems(['m', 'km', 'cm', 'mm', 'inch', 'ft'])
        self.length_to.setCurrentIndex(1)
        
        unit_layout.addWidget(QLabel("从:"))
        unit_layout.addWidget(self.length_from)
        unit_layout.addWidget(QLabel("到:"))
        unit_layout.addWidget(self.length_to)
        
        length_input_layout.addLayout(unit_layout)
        
        length_btn = QPushButton("转换")
        length_btn.clicked.connect(lambda: self._convert_length(service))
        length_input_layout.addWidget(length_btn)
        
        length_result = QLabel("结果: ")
        length_result.setStyleSheet("color: blue; font-weight: bold;")
        length_input_layout.addWidget(length_result)
        self.length_result = length_result
        
        length_layout.addLayout(length_input_layout)
        length_group.setLayout(length_layout)
        layout.addWidget(length_group)
        
        # 温度转换
        temp_group = QGroupBox("温度转换")
        temp_layout = QVBoxLayout()
        
        temp_input_layout = QVBoxLayout()
        temp_input_layout.addWidget(QLabel("数值:"))
        self.temp_input = QLineEdit()
        temp_input_layout.addWidget(self.temp_input)
        
        temp_unit_layout = QVBoxLayout()
        self.temp_from = QComboBox()
        self.temp_from.addItems(['C', 'F', 'K'])
        self.temp_to = QComboBox()
        self.temp_to.addItems(['C', 'F', 'K'])
        self.temp_to.setCurrentIndex(1)
        
        temp_unit_layout.addWidget(QLabel("从:"))
        temp_unit_layout.addWidget(self.temp_from)
        temp_unit_layout.addWidget(QLabel("到:"))
        temp_unit_layout.addWidget(self.temp_to)
        
        temp_input_layout.addLayout(temp_unit_layout)
        
        temp_btn = QPushButton("转换")
        temp_btn.clicked.connect(lambda: self._convert_temperature(service))
        temp_input_layout.addWidget(temp_btn)
        
        temp_result = QLabel("结果: ")
        temp_result.setStyleSheet("color: blue; font-weight: bold;")
        temp_input_layout.addWidget(temp_result)
        self.temp_result = temp_result
        
        temp_layout.addLayout(temp_input_layout)
        temp_group.setLayout(temp_layout)
        layout.addWidget(temp_group)
        
        layout.addStretch()
        return widget
    
    def _convert_length(self, service):
        """转换长度"""
        try:
            value = float(self.length_input.text())
            from_unit = self.length_from.currentText()
            to_unit = self.length_to.currentText()
            
            result = service.length_converter(value, from_unit, to_unit)
            self.length_result.setText(f"结果: {result:.4f} {to_unit}")
        except ValueError:
            QMessageBox.warning(None, "错误", "请输入有效的数值！")
    
    def _convert_temperature(self, service):
        """转换温度"""
        try:
            value = float(self.temp_input.text())
            from_unit = self.temp_from.currentText()
            to_unit = self.temp_to.currentText()
            
            result = service.temperature_converter(value, from_unit, to_unit)
            self.temp_result.setText(f"结果: {result:.2f}°{to_unit}")
        except ValueError:
            QMessageBox.warning(None, "错误", "请输入有效的数值！")