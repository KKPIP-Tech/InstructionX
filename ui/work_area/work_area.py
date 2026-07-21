"""
工作区模块
负责管理主窗口中的工作区，用于显示插件内容
"""
from typing import Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QLayoutItem
from PySide6.QtCore import Qt


class WorkArea:
    """
    工作区管理类
    封装工作区的布局和管理功能
    """

    def __init__(self, parent: QWidget):
        """
        初始化工作区

        Args:
            parent: 父窗口 widget
        """
        # 父窗口 widget 引用（全项目无外部访问，命名私有化）
        self._parent_widget = parent

        # 创建工作区
        self.work_area = QWidget(parent)
        self.work_layout = QVBoxLayout(self.work_area)
        self.work_layout.setContentsMargins(0, 0, 0, 0)

        # 初始显示的占位标签
        self.work_placeholder = QLabel("点击上方技能按钮，在此处显示插件功能")
        self.work_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.work_placeholder.setProperty("placeholder", "true")
        self.work_placeholder.style().unpolish(self.work_placeholder)
        self.work_placeholder.style().polish(self.work_placeholder)
        self.work_layout.addWidget(self.work_placeholder)

    def get_widget(self) -> QWidget:
        """
        获取工作区 widget

        Returns:
            工作区 QWidget
        """
        return self.work_area

    def clear(self, clear_highlight: bool = True):
        """
        清空工作区

        Args:
            clear_highlight: 是否清除按钮高亮状态
        """
        while self.work_layout.count():
            item: Optional[QLayoutItem] = self.work_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()

        # 如果需要清除高亮状态，通过回调处理
        if clear_highlight and hasattr(self, '_clear_highlight_callback'):
            self._clear_highlight_callback()

    def clear_keep_highlight(self):
        """
        清空工作区，但保留按钮的高亮状态
        用于切换插件时保持当前激活按钮的高亮
        注意：这里不再调用 deleteLater()，而是保留 Widget 实例以便缓存复用
        """
        while self.work_layout.count():
            item: Optional[QLayoutItem] = self.work_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    # 隐藏 widget，避免 Qt 状态问题
                    widget.hide()
                # 不再调用 deleteLater()，保留 widget 实例以便缓存复用
                # widget 会被 IPlugin 基类缓存，下次切换回来时直接使用

    def add_widget(self, widget):
        """
        添加 widget 到工作区

        Args:
            widget: 要添加的 QWidget
        """
        self.work_layout.addWidget(widget)
        # 确保 widget 可见
        widget.show()

    def set_clear_highlight_callback(self, callback):
        """
        设置清除高亮的回调函数

        Args:
            callback: 回调函数
        """
        self._clear_highlight_callback = callback
