"""
字符串工具插件 - UI 界面入口
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, 
    QPushButton, QGroupBox, QLineEdit,
    QTextEdit, QHBoxLayout, QGridLayout
)
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class StringToolsPlugin(IPlugin):
    """字符串工具插件"""
    
    @property
    def plugin_name(self) -> str:
        return "字符串\n工具"
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        # 创建服务实例
        service = Service()
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("字符串处理工具")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 输入区域
        input_group = QGroupBox("输入文本")
        input_layout = QVBoxLayout()
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("在此输入要处理的文本...")
        self.input_text.setMinimumHeight(80)
        input_layout.addWidget(self.input_text)
        
        input_group.setLayout(input_layout)
        layout.addWidget(input_group)
        
        # 操作按钮网格
        buttons_group = QGroupBox("操作")
        buttons_layout = QGridLayout()
        
        # 大写转换
        btn_upper = QPushButton("转大写")
        btn_upper.clicked.connect(
            lambda: self._process_text(service.to_uppercase)
        )
        buttons_layout.addWidget(btn_upper, 0, 0)
        
        # 小写转换
        btn_lower = QPushButton("转小写")
        btn_lower.clicked.connect(
            lambda: self._process_text(service.to_lowercase)
        )
        buttons_layout.addWidget(btn_lower, 0, 1)
        
        # 反转文本
        btn_reverse = QPushButton("反转文本")
        btn_reverse.clicked.connect(
            lambda: self._process_text(service.reverse_text)
        )
        buttons_layout.addWidget(btn_reverse, 0, 2)
        
        # 首字母大写
        btn_capitalize = QPushButton("首字母大写")
        btn_capitalize.clicked.connect(
            lambda: self._process_text(service.capitalize_words)
        )
        buttons_layout.addWidget(btn_capitalize, 1, 0)
        
        # 移除空白
        btn_remove_space = QPushButton("移除空白")
        btn_remove_space.clicked.connect(
            lambda: self._process_text(service.remove_whitespace)
        )
        buttons_layout.addWidget(btn_remove_space, 1, 1)
        
        # 统计信息
        btn_stats = QPushButton("统计信息")
        btn_stats.clicked.connect(self._show_stats)
        buttons_layout.addWidget(btn_stats, 1, 2)
        
        buttons_group.setLayout(buttons_layout)
        layout.addWidget(buttons_group)
        
        # 输出区域
        output_group = QGroupBox("输出结果")
        output_layout = QVBoxLayout()
        
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        self.output_text.setMinimumHeight(80)
        output_layout.addWidget(self.output_text)
        
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)
        
        # 统计信息显示
        self.stats_label = QLabel()
        self.stats_label.setStyleSheet("color: #666; padding: 5px;")
        layout.addWidget(self.stats_label)
        
        layout.addStretch()
        return widget
    
    def _process_text(self, func):
        """处理文本"""
        input_text = self.input_text.toPlainText()
        if not input_text:
            self.output_text.setText("请输入文本")
            return
        
        try:
            result = func(input_text)
            self.output_text.setText(result)
        except Exception as e:
            self.output_text.setText(f"错误: {str(e)}")
    
    def _show_stats(self):
        """显示统计信息"""
        input_text = self.input_text.toPlainText()
        if not input_text:
            self.stats_label.setText("请输入文本")
            return
        
        try:
            word_count = Service().count_words(input_text)
            char_count_with_space = Service().count_chars(input_text, True)
            char_count_no_space = Service().count_chars(input_text, False)
            
            stats = f"单词数: {word_count} | 字符数(含空格): {char_count_with_space} | 字符数(不含空格): {char_count_no_space}"
            self.stats_label.setText(stats)
        except Exception as e:
            self.stats_label.setText(f"统计错误: {str(e)}")