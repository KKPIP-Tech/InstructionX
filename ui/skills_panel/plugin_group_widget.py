"""
插件分组折叠控件

在技能面板中以「文件夹」形式展示一个用户自定义分组：
- 宽松模式为图标上文下文（78x64），紧凑模式与插件按钮统一为仅图标和实际行高
- 收起状态：仅显示分组按钮（分组图标；宽松模式另含名称），无额外指示
- 展开状态：分组按钮右侧显示主题强调色半弧（与插件激活态的左侧
  半弧呼应），同时按钮右侧行内展开组内插件按钮，展开区域使用区分背景
"""

from typing import Callable, Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont

from core.plugin.plugin_groups import PluginGroup
from core.i18n import tr, get_language_manager
from utils.logging_tools import LoggerManager, get_name
from InstructionX_UIKit import T
from .skill_button import SkillButton

# 分组按钮尺寸（与 SkillButton 保持一致）
_GROUP_BTN_WIDTH = 78
_GROUP_BTN_HEIGHT = 64
_GROUP_ICON_SIZE = 28
_RELAXED_GROUP_MARGINS = (6, 2, 6, 2)
_COMPACT_GROUP_MARGINS = (0, 0, 0, 0)
_RELAXED_GROUP_SPACING = 4
_COMPACT_GROUP_SPACING = 2

# 图标绘制参数
_EMOJI_PIXMAP_SIZE = 32
_EMOJI_FONT_POINT_SIZE = 17


def _render_group_icon(emoji: str) -> QIcon:
    """将分组 emoji 渲染为 QIcon

    Args:
        emoji: 分组图标字符

    Returns:
        渲染完成的 QIcon
    """
    pixmap = QPixmap(_EMOJI_PIXMAP_SIZE, _EMOJI_PIXMAP_SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    emoji_font = QFont()
    emoji_font.setPointSize(_EMOJI_FONT_POINT_SIZE)
    painter.setFont(emoji_font)
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()
    return QIcon(pixmap)


class PluginGroupWidget(QWidget):
    """
    插件分组折叠控件

    组成：分组按钮（SkillButton 样式）+ 展开容器（QHBoxLayout 放置组内
    插件按钮）。组内插件按钮由外部传入的 button_factory 创建，以便与
    技能面板共享同一套按钮创建/激活逻辑。

    Signals:
        toggled(bool): 展开状态变化，True 为展开
    """

    toggled = Signal(bool)

    def __init__(self, group: PluginGroup, plugins: list,
                 button_factory: Callable, parent: Optional[QWidget] = None):
        """初始化分组控件

        Args:
            group: 分组数据（名称、图标）
            plugins: 组内插件实例列表
            button_factory: 插件按钮工厂，签名为 callable(plugin) -> Optional[QWidget]
            parent: 父控件
        """
        super().__init__(parent)
        self.group = group
        self._expanded = False
        self._compact = False
        self._logger = LoggerManager()
        self._init_ui(plugins, button_factory)

        # 语言切换时重设分组按钮 tooltip（Qt 对象销毁时自动断开连接）
        get_language_manager().language_changed.connect(self._retranslate_ui)

    def _retranslate_ui(self) -> None:
        """语言切换时重设分组按钮描述与 tooltip（分组名本身为用户数据，不翻译）"""
        description = tr("skills_panel", "group.tooltip", name=self.group.name)
        self.folder_btn.skill_description = description
        self.folder_btn._update_tooltip()

    def _init_ui(self, plugins: list, button_factory: Callable) -> None:
        """构建界面：分组按钮 + 展开容器"""
        layout = QHBoxLayout(self)
        self._layout = layout
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(_RELAXED_GROUP_SPACING)

        # 分组按钮：与普通插件按钮同款样式（图标在上、文字在下）
        # objectName 供 QSS 定位展开状态的右侧强调条样式
        self.folder_btn = SkillButton(
            _render_group_icon(self.group.icon_key),
            self.group.name,
            tr("skills_panel", "group.tooltip", name=self.group.name),
            self,
        )
        self.folder_btn.setObjectName("skillGroupButton")
        self.folder_btn.setFixedSize(_GROUP_BTN_WIDTH, _GROUP_BTN_HEIGHT)
        self.folder_btn.setIconSize(QSize(_GROUP_ICON_SIZE, _GROUP_ICON_SIZE))
        self.folder_btn.setProperty("expanded", "false")
        self.folder_btn.clicked.connect(self.toggle)
        layout.addWidget(self.folder_btn)

        # 展开容器（区分背景）
        self.expand_area = QWidget()
        self.expand_area.setObjectName("skillGroupExpanded")
        inner = QHBoxLayout(self.expand_area)
        self._inner_layout = inner
        inner.setContentsMargins(*_RELAXED_GROUP_MARGINS)
        inner.setSpacing(_RELAXED_GROUP_SPACING)
        for plugin in plugins:
            btn = button_factory(plugin)
            if btn is not None:
                inner.addWidget(btn)
        self.expand_area.setVisible(False)
        self._apply_expand_style()
        layout.addWidget(self.expand_area)

    def set_compact(self, compact: bool, row_height: int) -> None:
        """向文件夹和全部组内按钮传播紧凑外观与统一行高。

        Args:
            compact: 是否使用仅图标的紧凑外观。
            row_height: SkillsPanel 切换按钮的实际行高。
        """
        self.folder_btn.set_compact(compact, row_height)
        for index in range(self._inner_layout.count()):
            item = self._inner_layout.itemAt(index)
            button = item.widget() if item else None
            if isinstance(button, SkillButton):
                button.set_compact(compact, row_height)
        margins = _COMPACT_GROUP_MARGINS if compact else _RELAXED_GROUP_MARGINS
        spacing = _COMPACT_GROUP_SPACING if compact else _RELAXED_GROUP_SPACING
        self._inner_layout.setContentsMargins(*margins)
        self._inner_layout.setSpacing(spacing)
        self._layout.setSpacing(spacing)
        self._compact = compact
        self._apply_expand_style()

    def _apply_expand_style(self) -> None:
        """为展开区域应用区分背景（跟随应用主题色）"""
        bg = T("color.bg.muted")
        border = "none" if self._compact else f"1px solid {T('color.primary')}"
        self.expand_area.setStyleSheet(
            f"#skillGroupExpanded {{"
            f" background-color: {bg};"
            f" border: {border};"
            f" border-radius: 6px;"
            f" }}"
        )

    def toggle(self) -> None:
        """切换展开/收起状态"""
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """设置展开状态

        展开时分组按钮右侧显示主题强调色半弧（QSS expanded 属性驱动），
        收起时恢复普通按钮样式。

        Args:
            expanded: True 展开组内插件，False 收起
        """
        self._expanded = expanded
        self.expand_area.setVisible(expanded)
        self.folder_btn.setProperty("expanded", "true" if expanded else "false")
        self.folder_btn.style().unpolish(self.folder_btn)
        self.folder_btn.style().polish(self.folder_btn)
        self.toggled.emit(expanded)

    def is_expanded(self) -> bool:
        """返回当前是否处于展开状态"""
        return self._expanded
