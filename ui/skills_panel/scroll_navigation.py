"""SkillsPanel 紧凑模式的横向滚动导航控件。"""

from PySide6.QtCore import QEvent, QObject, QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QToolButton, QWidget

from core.i18n import get_language_manager, tr
from InstructionX_UIKit import T, get_pixmap
from InstructionX_UIKit.theme import ThemeManager


NAV_BUTTON_WIDTH = 28
NAV_ICON_MAX_SIZE = 16
NAV_ICON_VERTICAL_PADDING = 2
NAV_LAYOUT_SPACING = 2
DEFAULT_ROW_HEIGHT = 24
SCROLL_DIRECTION_PREVIOUS = -1
SCROLL_DIRECTION_NEXT = 1


def _arrow_icon(name: str, icon_size: int) -> QIcon:
    """从 UIKit Iconoir 构建普通和禁用两态箭头图标。"""
    icon = QIcon()
    icon.addPixmap(
        get_pixmap(name, icon_size, T("color.text.secondary")),
        QIcon.Mode.Normal,
    )
    icon.addPixmap(
        get_pixmap(name, icon_size, T("color.text.disabled")),
        QIcon.Mode.Disabled,
    )
    return icon


class SkillsScrollNavigator(QWidget):
    """绑定当前 ScrollArea，提供溢出显示、分页滚动和边界禁用。

    控件只负责横向导航，不拥有插件页面。调用方需在各页面创建时执行
    ``watch()``，切换页面时执行 ``set_current()``，紧凑模式时执行
    ``set_active(True)`` 并传入与切换按钮一致的行高。
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._current_scroll_area: QScrollArea | None = None
        self._watched_scroll_areas: set[QScrollArea] = set()
        self._active = False
        self._row_height = DEFAULT_ROW_HEIGHT
        self._icon_size = self._fit_icon_size(self._row_height)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(NAV_LAYOUT_SPACING)
        self.left_btn = self._create_button("previous", SCROLL_DIRECTION_PREVIOUS)
        self.right_btn = self._create_button("next", SCROLL_DIRECTION_NEXT)
        layout.addWidget(self.left_btn)
        layout.addWidget(self.right_btn)
        self._retranslate_ui()
        self._reload_icons()
        self.refresh()
        get_language_manager().language_changed.connect(self._retranslate_ui)
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _create_button(self, direction_name: str, direction: int) -> QToolButton:
        """创建一个仅显示 UIKit 图标的导航按钮。"""
        button = QToolButton(self)
        button.setObjectName("skillsScrollButton")
        button.setProperty("direction", direction_name)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(NAV_BUTTON_WIDTH, self._row_height)
        button.setIconSize(QSize(self._icon_size, self._icon_size))
        button.clicked.connect(lambda _checked=False, value=direction: self._scroll_page(value))
        return button

    def watch(self, scroll_area: QScrollArea) -> None:
        """监听一个页面的滚动范围和视口尺寸，重复监听无副作用。"""
        if scroll_area in self._watched_scroll_areas:
            return
        self._watched_scroll_areas.add(scroll_area)
        scroll_area.destroyed.connect(self._on_scroll_area_destroyed)
        bar = scroll_area.horizontalScrollBar()
        bar.rangeChanged.connect(self._on_scroll_changed)
        bar.valueChanged.connect(self._on_scroll_changed)
        scroll_area.viewport().installEventFilter(self)

    def set_current(self, scroll_area: QScrollArea | None) -> None:
        """切换导航控制的当前页面，None 表示没有可控制页面。"""
        if scroll_area is not None:
            self.watch(scroll_area)
        self._current_scroll_area = scroll_area
        self.refresh()

    def set_active(self, active: bool) -> None:
        """设置是否允许在溢出时显示导航。"""
        self._active = active
        self.refresh()

    def set_row_height(self, row_height: int) -> None:
        """设置与切换按钮一致的高度，并按可用空间缩放图标。"""
        if row_height <= 2 * NAV_ICON_VERTICAL_PADDING:
            raise ValueError("导航行高必须大于上下图标边距")
        self._row_height = row_height
        self._icon_size = self._fit_icon_size(row_height)
        for button in (self.left_btn, self.right_btn):
            button.setFixedSize(NAV_BUTTON_WIDTH, row_height)
            button.setIconSize(QSize(self._icon_size, self._icon_size))
        self._reload_icons()

    @staticmethod
    def _fit_icon_size(row_height: int) -> int:
        """计算不超出统一行高的图标边长。"""
        return min(
            NAV_ICON_MAX_SIZE,
            row_height - 2 * NAV_ICON_VERTICAL_PADDING,
        )

    def _current_scroll_bar(self):
        """安全读取当前滚动条，处理 Qt 销毁与延迟回调竞态。"""
        if self._current_scroll_area is None:
            self._hide_safely()
            return None
        try:
            return self._current_scroll_area.horizontalScrollBar()
        except RuntimeError:
            self._current_scroll_area = None
            self._hide_safely()
            return None

    def _hide_safely(self) -> None:
        """导航自身已销毁时忽略后续隐藏请求。"""
        try:
            self.hide()
        except RuntimeError:
            return

    def refresh(self) -> None:
        """根据当前页溢出和滚动位置同步可见性与边界状态。"""
        bar = self._current_scroll_bar()
        if bar is None:
            return
        try:
            overflow = self._active and bar.maximum() > bar.minimum()
            self.setVisible(overflow)
            self.left_btn.setEnabled(overflow and bar.value() > bar.minimum())
            self.right_btn.setEnabled(overflow and bar.value() < bar.maximum())
        except RuntimeError:
            self._current_scroll_area = None

    def _scroll_page(self, direction: int) -> None:
        """按当前可视页滚动，QScrollBar 自动钳制到合法范围。"""
        bar = self._current_scroll_bar()
        if bar is None:
            return
        bar.setValue(bar.value() + direction * bar.pageStep())

    def _on_scroll_area_destroyed(self, _obj=None) -> None:
        """页面销毁后清空引用，阻止延迟回调访问失效对象。"""
        self._current_scroll_area = None
        self._hide_safely()

    def _on_scroll_changed(self, *_args) -> None:
        """滚动范围或位置变化后同步按钮状态。"""
        self.refresh()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """视口 Resize 后在布局完成时重新计算溢出。"""
        if event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.refresh)
        return super().eventFilter(watched, event)

    def _reload_icons(self) -> None:
        """按当前主题和行高重建 UIKit 图标。"""
        self.left_btn.setIcon(_arrow_icon("arrow-left", self._icon_size))
        self.right_btn.setIcon(_arrow_icon("arrow-right", self._icon_size))

    def _on_theme_changed(self, _mode: str) -> None:
        """主题变化后刷新图标颜色。"""
        self._reload_icons()

    def _retranslate_ui(self, *_args) -> None:
        """集中刷新导航按钮的翻译和无障碍名称。"""
        for button, key in (
            (self.left_btn, "navigation.previous"),
            (self.right_btn, "navigation.next"),
        ):
            text = tr("skills_panel", key)
            button.setToolTip(text)
            button.setAccessibleName(text)
