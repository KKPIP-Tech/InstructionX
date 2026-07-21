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
        self.setFixedSize(78, 64)  # 按钮尺寸
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
        - 默认单行模式，最多 13 个字符，超出用...替代
        - 若包含换行符，最多显示两行，每行最多 8 个字符
        """
        max_chars_single = 13
        max_chars_per_line = 8

        # 如果文本包含换行符，按换行符分割（双行模式）
        if '\n' in text:
            lines = text.split('\n')
            # 最多显示两行
            if len(lines) > 2:
                lines = lines[:2]
            processed_lines = []
            for line in lines:
                line = line.strip()
                if len(line) > max_chars_per_line:
                    processed_lines.append(line[:max_chars_per_line] + "...")
                else:
                    processed_lines.append(line)
            display_text = '\n'.join(processed_lines)
        else:
            # 单行模式
            if len(text) > max_chars_single:
                display_text = text[:max_chars_single] + "..."
            else:
                display_text = text

        self.setText(display_text)

    def _apply_style(self):
        """应用 StyleQSS 风格的样式"""
        self.setProperty("active", "true" if self._is_active else "false")
        self.style().unpolish(self)
        self.style().polish(self)
