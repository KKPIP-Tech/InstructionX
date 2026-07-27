"""
插件分组折叠控件

在技能面板中以「文件夹」形式展示一个用户自定义分组：
- 分组按钮与普通插件按钮样式一致（图标在上、文字在下，78x64）
- 收起状态：仅显示分组按钮（分组图标 + 名称），无额外指示
- 展开状态：分组按钮右侧显示主题强调色半弧（与插件激活态的左侧
  半弧呼应），同时按钮右侧行内展开组内插件按钮，展开区域使用区分背景
"""

from typing import Callable, Optional

from PySide6.QtWidgets import QWidget, QHBoxLayout
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QIcon, QPixmap, QPainter, QFont

from core.plugin.plugin_groups import PluginGroup
from utils.logging_tools import LoggerManager, get_name
from utils.style_qss import get_style_qss
from .skill_button import SkillButton

# 分组按钮尺寸（与 SkillButton 保持一致）
_GROUP_BTN_WIDTH = 78
_GROUP_BTN_HEIGHT = 64
_GROUP_ICON_SIZE = 28

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
        self._logger = LoggerManager()
        self._init_ui(plugins, button_factory)

    def _init_ui(self, plugins: list, button_factory: Callable) -> None:
        """构建界面：分组按钮 + 展开容器"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 分组按钮：与普通插件按钮同款样式（图标在上、文字在下）
        # objectName 供 QSS 定位展开状态的右侧强调条样式
        self.folder_btn = SkillButton(
            _render_group_icon(self.group.icon_key),
            self.group.name,
            f"分组：{self.group.name}（点击展开/收起）",
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
        inner.setContentsMargins(6, 2, 6, 2)
        inner.setSpacing(4)
        for plugin in plugins:
            btn = button_factory(plugin)
            if btn is not None:
                inner.addWidget(btn)
        self.expand_area.setVisible(False)
        self._apply_expand_style()
        layout.addWidget(self.expand_area)

    def _apply_expand_style(self) -> None:
        """为展开区域应用区分背景（跟随应用主题色）"""
        colors = get_style_qss().colors()
        bg = colors.get("controlFillHover", "#e8f4fd")
        border = colors.get("accent", "#0078d4")
        self.expand_area.setStyleSheet(
            f"#skillGroupExpanded {{"
            f" background-color: {bg};"
            f" border: 1px solid {border};"
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
