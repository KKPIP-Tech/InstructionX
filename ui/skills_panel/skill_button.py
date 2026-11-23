"""支持宽松图标上文下文、紧凑仅图标两种外观的技能按钮。"""

from PySide6.QtWidgets import QToolButton
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon


RELAXED_BUTTON_WIDTH = 78
RELAXED_BUTTON_HEIGHT = 64
RELAXED_ICON_SIZE = 28
COMPACT_BUTTON_WIDTH = 32
COMPACT_ICON_MAX_SIZE = 20
COMPACT_ICON_VERTICAL_PADDING = 2


class SkillButton(QToolButton):
    """插件入口按钮，支持激活高亮、完整名称提示和统一紧凑行高。"""

    def __init__(self, icon: QIcon, name: str, description: str, parent=None):
        super().__init__(parent)
        self.skill_name = name
        self.skill_description = description
        self._is_active = False  # 是否激活
        self._compact = False

        # 设置按钮属性
        self.setIcon(icon)
        self._process_display_text(name)
        self.setIconSize(QSize(RELAXED_ICON_SIZE, RELAXED_ICON_SIZE))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(RELAXED_BUTTON_WIDTH, RELAXED_BUTTON_HEIGHT)
        self._update_tooltip()

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

    def set_compact(self, compact: bool, row_height: int) -> None:
        """切换显示外观，紧凑高度由 SkillsPanel 的统一行高提供。

        Args:
            compact: True 仅显示图标，False 恢复图标上文下文的宽松外观。
            row_height: 紧凑按钮高度，必须与切换按钮的实际行高一致。

        Raises:
            ValueError: 行高无法容纳图标时抛出。
        """
        if compact and row_height <= 2 * COMPACT_ICON_VERTICAL_PADDING:
            raise ValueError("紧凑按钮行高必须大于上下图标边距")
        self._compact = compact
        if compact:
            self._apply_compact_metrics(row_height)
        else:
            self._apply_relaxed_metrics()
        self._update_tooltip()
        self.setProperty("compact", "true" if compact else "false")
        self._apply_style()

    def is_compact(self) -> bool:
        """返回当前是否为紧凑外观。"""
        return self._compact

    def _apply_compact_metrics(self, row_height: int) -> None:
        """应用紧凑尺寸，图标不得超出统一行高。"""
        icon_size = min(
            COMPACT_ICON_MAX_SIZE,
            row_height - 2 * COMPACT_ICON_VERTICAL_PADDING,
        )
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setFixedSize(COMPACT_BUTTON_WIDTH, row_height)
        self.setIconSize(QSize(icon_size, icon_size))

    def _apply_relaxed_metrics(self) -> None:
        """恢复宽松按钮尺寸和图标上文下文布局。"""
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.setFixedSize(RELAXED_BUTTON_WIDTH, RELAXED_BUTTON_HEIGHT)
        self.setIconSize(QSize(RELAXED_ICON_SIZE, RELAXED_ICON_SIZE))

    def _update_tooltip(self) -> None:
        """紧凑模式只显示完整名称，宽松模式保留名称和描述。"""
        tooltip = self.skill_name if self._compact else f"{self.skill_name}\n{self.skill_description}"
        self.setToolTip(tooltip)

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
