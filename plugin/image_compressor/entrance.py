"""
图片压缩插件 - 官方插件示例
提供图片压缩功能
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QSlider, QLineEdit, QMessageBox
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class ImageCompressorPlugin(IPlugin):
    """图片压缩插件"""
    
    @property
    def plugin_name(self) -> str:
        return "图片\n压缩"
    
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("图片压缩工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 文件选择
        file_group = QGroupBox("选择图片")
        file_layout = QVBoxLayout()
        self.file_input = QLineEdit()
        self.file_input.setPlaceholderText("选择图片文件...")
        file_layout.addWidget(self.file_input)
        
        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(self._browse_file)
        file_layout.addWidget(browse_btn)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        # 质量设置
        quality_group = QGroupBox("压缩质量")
        quality_layout = QVBoxLayout()
        
        self.quality_label = QLabel("质量: 85%")
        quality_layout.addWidget(self.quality_label)
        
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setMinimum(1)
        self.quality_slider.setMaximum(100)
        self.quality_slider.setValue(85)
        self.quality_slider.valueChanged.connect(
            lambda v: self.quality_label.setText(f"质量: {v}%")
        )
        quality_layout.addWidget(self.quality_slider)
        
        quality_group.setLayout(quality_layout)
        layout.addWidget(quality_group)
        
        # 压缩按钮
        compress_btn = QPushButton("压缩图片")
        compress_btn.clicked.connect(lambda: self._compress(service))
        compress_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                padding: 8px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #106EBE;
            }
        """)
        layout.addWidget(compress_btn)
        
        layout.addStretch()
        return widget
    
    def _browse_file(self):
        """浏览文件"""
        from PySide6.QtWidgets import QFileDialog
        file_path, _ = QFileDialog.getOpenFileName(
            None,
            "选择图片文件",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        if file_path:
            self.file_input.setText(file_path)
    
    def _compress(self, service):
        """压缩图片"""
        file_path = self.file_input.text()
        if not file_path:
            QMessageBox.warning(None, "警告", "请先选择图片文件！")
            return
        
        quality = self.quality_slider.value()
        success = service.compress_image(file_path, quality)
        
        if success:
            QMessageBox.information(None, "成功", f"图片已压缩！质量: {quality}%")
        else:
            QMessageBox.critical(None, "错误", "图片压缩失败！")
