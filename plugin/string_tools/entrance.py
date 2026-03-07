"""
字符串工具插件 - UI 界面入口
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QPushButton, QGroupBox,
    QTextEdit, QGridLayout
)
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from .service import Service


class StringToolsPlugin(IPlugin):
    """字符串工具插件"""

    @property
    def plugin_name(self) -> str:
        return "字符串\n工具"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
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

        # 使用局部变量而非 self.input_text
        input_text = QTextEdit()
        input_text.setPlaceholderText("在此输入要处理的文本...")
        input_text.setMinimumHeight(80)
        input_layout.addWidget(input_text)

        input_group.setLayout(input_layout)
        layout.addWidget(input_group)

        # 操作按钮网格
        buttons_group = QGroupBox("操作")
        buttons_layout = QGridLayout()

        # 输出文本框（局部变量）
        output_text = QTextEdit()
        output_text.setReadOnly(True)
        output_text.setMinimumHeight(80)

        # 统计信息标签（局部变量）
        stats_label = QLabel()
        stats_label.setStyleSheet("color: #666; padding: 5px;")

        # 大写转换
        btn_upper = QPushButton("转大写")
        btn_upper.clicked.connect(
            lambda: output_text.setText(service.to_uppercase(input_text.toPlainText()))
                if input_text.toPlainText() else output_text.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_upper, 0, 0)

        # 小写转换
        btn_lower = QPushButton("转小写")
        btn_lower.clicked.connect(
            lambda: output_text.setText(service.to_lowercase(input_text.toPlainText()))
                if input_text.toPlainText() else output_text.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_lower, 0, 1)

        # 反转文本
        btn_reverse = QPushButton("反转文本")
        btn_reverse.clicked.connect(
            lambda: output_text.setText(service.reverse_text(input_text.toPlainText()))
                if input_text.toPlainText() else output_text.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_reverse, 0, 2)

        # 首字母大写
        btn_capitalize = QPushButton("首字母大写")
        btn_capitalize.clicked.connect(
            lambda: output_text.setText(service.capitalize_words(input_text.toPlainText()))
                if input_text.toPlainText() else output_text.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_capitalize, 1, 0)

        # 移除空白
        btn_remove_space = QPushButton("移除空白")
        btn_remove_space.clicked.connect(
            lambda: output_text.setText(service.remove_whitespace(input_text.toPlainText()))
                if input_text.toPlainText() else output_text.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_remove_space, 1, 1)

        # 统计信息
        btn_stats = QPushButton("统计信息")
        btn_stats.clicked.connect(
            lambda: stats_label.setText(
                f"单词数: {service.count_words(input_text.toPlainText())} | "
                f"字符数(含空格): {service.count_chars(input_text.toPlainText(), True)} | "
                f"字符数(不含空格): {service.count_chars(input_text.toPlainText(), False)}"
            ) if input_text.toPlainText() else stats_label.setText("请输入文本")
        )
        buttons_layout.addWidget(btn_stats, 1, 2)

        buttons_group.setLayout(buttons_layout)
        layout.addWidget(buttons_group)

        # 输出区域
        output_group = QGroupBox("输出结果")
        output_layout = QVBoxLayout()
        output_layout.addWidget(output_text)
        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # 统计信息显示
        layout.addWidget(stats_label)

        layout.addStretch()
        return widget
