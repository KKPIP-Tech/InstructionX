"""
代码格式化插件 - 官方插件示例
提供代码格式化功能
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox, QTextEdit, QComboBox, QMessageBox
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class CodeFormatterPlugin(IPlugin):
    """代码格式化插件"""
    
    @property
    def plugin_name(self) -> str:
        return "代码\n格式化"
    
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("代码格式化工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 输入区域
        input_group = QGroupBox("输入代码")
        input_layout = QVBoxLayout()
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("粘贴代码...")
        input_layout.addWidget(self.input_text)
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 功能按钮
        button_layout = QVBoxLayout()
        
        # JSON格式化
        json_btn = QPushButton("格式化 JSON")
        json_btn.clicked.connect(lambda: self._format_json(service))
        button_layout.addWidget(json_btn)
        
        # 移除注释
        comment_group = QGroupBox("移除注释")
        comment_layout = QVBoxLayout()
        
        lang_layout = QVBoxLayout()
        lang_layout.addWidget(QLabel("选择语言:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["python", "javascript"])
        lang_layout.addWidget(self.lang_combo)
        comment_layout.addLayout(lang_layout)
        
        remove_comment_btn = QPushButton("移除注释")
        remove_comment_btn.clicked.connect(lambda: self._remove_comments(service))
        comment_layout.addWidget(remove_comment_btn)
        
        comment_group.setLayout(comment_layout)
        button_layout.addWidget(comment_group)
        
        # 压缩代码
        compress_btn = QPushButton("压缩代码")
        compress_btn.clicked.connect(lambda: self._compress_code(service))
        button_layout.addWidget(compress_btn)
        
        layout.addLayout(button_layout)
        
        layout.addStretch()
        return widget
    
    def _format_json(self, service):
        """格式化JSON"""
        code = self.input_text.toPlainText()
        if not code:
            QMessageBox.warning(None, "警告", "请输入JSON代码！")
            return
        
        result = service.format_json(code)
        self.input_text.setText(result)
    
    def _remove_comments(self, service):
        """移除注释"""
        code = self.input_text.toPlainText()
        if not code:
            QMessageBox.warning(None, "警告", "请输入代码！")
            return
        
        language = self.lang_combo.currentText()
        result = service.remove_comments(code, language)
        self.input_text.setText(result)
    
    def _compress_code(self, service):
        """压缩代码"""
        code = self.input_text.toPlainText()
        if not code:
            QMessageBox.warning(None, "警告", "请输入代码！")
            return
        
        result = service.compress_code(code)
        self.input_text.setText(result)