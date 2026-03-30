"""
技能按钮组件

定义图标在上、文字在下的技能按钮，支持激活状态高亮显示。
"""

from PySide6.QtWidgets import QToolButton
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon


class SkillButton(QToolButton):
    """
    图标在上、文字在下的技能按钮
    支持激活状态高亮显示
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
        """应用 StyleQSS 风格的样式"""
        self.setProperty("active", "true" if self._is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
