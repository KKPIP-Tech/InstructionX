import sys
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


class FluentStyle:
    """
    FluentUI3 风格样式

    提供 FluentUI3 颜色和 Qt Style Sheets 样式支持
    """

    # FluentUI3 颜色定义
    COLORS = {
        'light': {
            # 基础色
            'window': '#FFFFFF',
            'windowText': '#000000',
            'base': '#FFFFFF',
            'alternateBase': '#F3F3F3',
            'toolTipBase': '#FFFFFF',
            'toolTipText': '#000000',

            # 控件色
            'button': '#F3F3F3',
            'buttonText': '#000000',
            'light': '#FFFFFF',
            'midlight': '#E3E3E3',
            'dark': '#CCCCCC',
            'mid': '#C6C6C6',
            'shadow': '#696969',

            # 高亮色 - Windows Blue
            'highlight': '#0078D4',
            'highlightedText': '#FFFFFF',

            # 链接
            'link': '#0063B1',
            'linkVisited': '#800080',

            # 禁用
            'text': '#000000',
            'textDisabled': '#6D6D6D',

            # 边框
            'border': '#898989',
            'borderLight': '#CCCCCC',
            'borderDark': '#898989',

            # Fluent 专用
            'accent': '#0078D4',
            'accentLight': '#4CC2FF',
            'accentDark': '#005A9E',

            # 控件状态填充
            'controlFill': 'rgba(0, 0, 0, 7)',
            'controlFillHover': 'rgba(0, 0, 0, 12)',
            'controlFillPressed': 'rgba(0, 0, 0, 18)',
            'controlFillDisabled': 'rgba(0, 0, 0, 4)',
            'controlFillSelected': 'rgba(0, 120, 212, 20)',

            # 圆角
            'radius': '4px',
            'radiusLarge': '8px',
            'radiusSmall': '2px',
        },
        'dark': {
            # 基础色
            'window': '#202020',
            'windowText': '#FFFFFF',
            'base': '#2C2C2C',
            'alternateBase': '#323232',
            'toolTipBase': '#323232',
            'toolTipText': '#FFFFFF',

            # 控件色
            'button': '#2C2C2C',
            'buttonText': '#FFFFFF',
            'light': '#5A5A5A',
            'midlight': '#404040',
            'dark': '#1E1E1E',
            'mid': '#333333',
            'shadow': '#000000',

            # 高亮色
            'highlight': '#0078D4',
            'highlightedText': '#FFFFFF',

            # 链接
            'link': '#99BFFF',
            'linkVisited': '#B987B9',

            # 禁用
            'text': '#FFFFFF',
            'textDisabled': '#6D6D6D',

            # 边框
            'border': '#646464',
            'borderLight': '#3C3C3C',
            'borderDark': '#646464',

            # Fluent 专用
            'accent': '#0078D4',
            'accentLight': '#4CC2FF',
            'accentDark': '#005A9E',

            # 控件状态填充
            'controlFill': 'rgba(255, 255, 255, 7)',
            'controlFillHover': 'rgba(255, 255, 255, 12)',
            'controlFillPressed': 'rgba(255, 255, 255, 18)',
            'controlFillDisabled': 'rgba(255, 255, 255, 4)',
            'controlFillSelected': 'rgba(0, 120, 212, 40)',

            # 圆角
            'radius': '4px',
            'radiusLarge': '8px',
            'radiusSmall': '2px',
        }
    }

    def __init__(self):
        self._theme = 'light'
        self._colors = self.COLORS['light'].copy()

    def set_theme(self, theme: str):
        """设置主题"""
        if theme in ('light', 'dark'):
            self._theme = theme
            self._colors = self.COLORS[theme].copy()

    def theme(self) -> str:
        """获取当前主题"""
        return self._theme

    def colors(self) -> dict:
        """获取当前颜色"""
        return self._colors

    def color(self, name: str) -> str:
        """获取指定颜色"""
        return self._colors.get(name, '#000000')


# 全局样式实例
_fluent_style = FluentStyle()


def get_fluent_style() -> FluentStyle:
    """获取全局 FluentStyle 实例"""
    return _fluent_style


def set_theme(theme: str):
    """设置全局主题"""
    _fluent_style.set_theme(theme)


def create_fluent_qss(theme: str = 'light') -> str:
    """
    创建 FluentUI3 Qt Style Sheets - 完整版

    Args:
        theme: 主题类型，'light' 或 'dark'

    Returns:
        QSS 样式字符串
    """
    style = FluentStyle()
    style.set_theme(theme)
    c = style.colors()

    # 完整 QSS
    qss = f"""
/* ═════════════════════════════════════════════════════════════════════════════
 * FluentUI3 风格样式 - 完整版
 * 基于 Windows 11 FluentUI3 设计语言
 * ═════════════════════════════════════════════════════════════════════════════ */

/* ===== 基础设置 ===== */
* {{
    outline: none;
}}

QWidget {{
    font-family: "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif;
    font-size: 14px;
}}

QMainWindow, QDialog, QMessageBox {{
    background-color: {c['window']};
}}

QWindowsStyle, QFusionStyle {{
    name: "FluentUI3";
}}

/* ===== 通用框架 ===== */
QFrame, QStackedWidget, QScrollArea, QDecorationBackground {{
    background-color: {c['window']};
}}

QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
}}

/* ===== 按钮 ===== */
QPushButton {{
    background-color: {c['controlFill']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 6px 16px;
    color: {c['buttonText']};
    min-width: 75px;
    min-height: 24px;
}}

QPushButton:hover {{
    background-color: {c['controlFillHover']};
    border-color: {c['border']};
}}

QPushButton:pressed {{
    background-color: {c['controlFillPressed']};
}}

QPushButton:disabled {{
    background-color: {c['controlFillDisabled']};
    color: {c['textDisabled']};
    border-color: {c['borderLight']};
}}

QPushButton:focus {{
    border: 2px solid {c['accent']};
    padding: 5px 15px;
}}

QPushButton:flat {{
    background-color: transparent;
    border: none;
}}

QPushButton:flat:hover {{
    background-color: {c['controlFillHover']};
}}

QPushButton:flat:pressed {{
    background-color: {c['controlFillPressed']};
}}

/* 主要按钮 */
QPushButton[class="primary"], QPushButton[class="accent"] {{
    background-color: {c['accent']};
    border: 1px solid {c['accent']};
    color: {c['highlightedText']};
}}

QPushButton[class="primary"]:hover, QPushButton[class="accent"]:hover {{
    background-color: {c['accentLight']};
    border-color: {c['accentLight']};
}}

QPushButton[class="primary"]:pressed, QPushButton[class="accent"]:pressed {{
    background-color: {c['accentDark']};
    border-color: {c['accentDark']};
}}

QPushButton[class="primary"]:disabled, QPushButton[class="accent"]:disabled {{
    background-color: {c['controlFillDisabled']};
    border-color: {c['borderLight']};
    color: {c['textDisabled']};
}}

/* ===== 行编辑 ===== */
QLineEdit {{
    background-color: {c['base']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 6px 8px;
    color: {c['windowText']};
    selection-background-color: {c['highlight']};
}}

QLineEdit:hover {{
    border-color: {c['border']};
}}

QLineEdit:focus {{
    border: 2px solid {c['accent']};
    padding: 5px 7px;
}}

QLineEdit:disabled {{
    background-color: {c['alternateBase']};
    color: {c['textDisabled']};
}}

QLineEdit:read-only {{
    background-color: {c['alternateBase']};
}}

/* ===== 文本编辑 ===== */
QTextEdit, QPlainTextEdit {{
    background-color: {c['base']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    color: {c['windowText']};
    selection-background-color: {c['highlight']};
}}

QTextEdit:hover, QPlainTextEdit:hover {{
    border-color: {c['border']};
}}

QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {c['accent']};
}}

QTextEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {c['alternateBase']};
    color: {c['textDisabled']};
}}

/* ===== 组合框 ===== */
QComboBox {{
    background-color: {c['controlFill']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 6px 12px;
    color: {c['buttonText']};
    min-width: 75px;
}}

QComboBox:hover {{
    background-color: {c['controlFillHover']};
    border-color: {c['border']};
}}

QComboBox:focus {{
    border: 2px solid {c['accent']};
}}

QComboBox:disabled {{
    background-color: {c['controlFillDisabled']};
    color: {c['textDisabled']};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c['buttonText']};
    margin-right: 8px;
}}

QComboBox QAbstractItemView {{
    background-color: {c['window']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    selection-background-color: {c['highlight']};
    selection-color: {c['highlightedText']};
    padding: 4px;
    show-decoration-selected: 1;
}}

QComboBox QAbstractItemView::item {{
    min-height: 32px;
    padding: 6px 12px;
}}

QComboBox QAbstractItemView::item:hover {{
    background-color: {c['controlFillHover']};
}}

/* ===== 复选框 ===== */
QCheckBox {{
    color: {c['windowText']};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {c['border']};
    border-radius: 3px;
    background-color: {c['controlFill']};
}}

QCheckBox::indicator:hover {{
    border-color: {c['accent']};
    background-color: {c['controlFillHover']};
}}

QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
    image: url(none);
}}

QCheckBox::indicator:checked:hover {{
    background-color: {c['accentLight']};
    border-color: {c['accentLight']};
}}

QCheckBox::indicator:indeterminate {{
    background-color: {c['accent']};
    border-color: {c['accent']};
}}

QCheckBox:disabled {{
    color: {c['textDisabled']};
}}

QCheckBox::indicator:disabled {{
    background-color: {c['controlFillDisabled']};
    border-color: {c['borderLight']};
}}

/* ===== 单选按钮 ===== */
QRadioButton {{
    color: {c['windowText']};
    spacing: 8px;
}}

QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {c['border']};
    border-radius: 9px;
    background-color: {c['controlFill']};
}}

QRadioButton::indicator:hover {{
    border-color: {c['accent']};
    background-color: {c['controlFillHover']};
}}

QRadioButton::indicator:checked {{
    background-color: {c['accent']};
    border-color: {c['accent']};
}}

QRadioButton::indicator:checked:hover {{
    background-color: {c['accentLight']};
    border-color: {c['accentLight']};
}}

QRadioButton:disabled {{
    color: {c['textDisabled']};
}}

QRadioButton::indicator:disabled {{
    background-color: {c['controlFillDisabled']};
    border-color: {c['borderLight']};
}}

/* ===== 滑块 ===== */
QSlider::groove:horizontal {{
    border: none;
    height: 4px;
    background: {c['borderLight']};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    width: 16px;
    height: 16px;
    margin: -6px 0;
    background: {c['accent']};
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {c['accentLight']};
}}

QSlider::handle:horizontal:pressed {{
    background: {c['accentDark']};
}}

QSlider::sub-page:horizontal {{
    background: {c['accent']};
    border-radius: 2px;
}}

QSlider::groove:vertical {{
    border: none;
    width: 4px;
    background: {c['borderLight']};
    border-radius: 2px;
}}

QSlider::handle:vertical {{
    width: 16px;
    height: 16px;
    margin: 0 -6px;
    background: {c['accent']};
    border-radius: 8px;
}}

QSlider::handle:vertical:hover {{
    background: {c['accentLight']};
}}

QSlider::handle:vertical:pressed {{
    background: {c['accentDark']};
}}

QSlider::add-page:vertical {{
    background: {c['accent']};
    border-radius: 2px;
}}

/* ===== 旋钮 ===== */
QDial {{
    background-color: {c['controlFill']};
    border: 1px solid {c['borderLight']};
}}

QDial::groove:horizontal {{
    background: {c['borderLight']};
}}

QDial::handle:horizontal {{
    background: {c['accent']};
    border-radius: 8px;
}}

/* ===== 进度条 ===== */
QProgressBar {{
    border: none;
    background-color: {c['borderLight']};
    border-radius: {c['radius']};
    text-align: center;
    color: {c['windowText']};
    min-height: 6px;
}}

QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: {c['radius']};
}}

QProgressBar:horizontal {{
    border: none;
}}

QProgressBar:vertical {{
    border: none;
    width: 6px;
}}

/* ===== 标签 ===== */
QLabel {{
    color: {c['windowText']};
    background: transparent;
}}

QLabel[heading="true"] {{
    font-size: 24px;
    font-weight: bold;
}}

QLabel[subheading="true"] {{
    font-size: 18px;
    font-weight: bold;
}}

QLabel[caption="true"] {{
    font-size: 12px;
    color: {c['textDisabled']};
}}

QLabel:disabled {{
    color: {c['textDisabled']};
}}

/* ===== 链接标签 ===== */
QLabel[link="true"] {{
    color: {c['link']};
    text-decoration: underline;
}}

QLabel[link="true"]:hover {{
    color: {c['accentLight']};
}}

/* ===== 数字选择框 ===== */
QSpinBox, QDoubleSpinBox {{
    background-color: {c['base']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 6px 8px;
    color: {c['windowText']};
}}

QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {c['border']};
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {c['accent']};
    padding: 5px 7px;
}}

QSpinBox:disabled, QDoubleSpinBox:disabled {{
    background-color: {c['alternateBase']};
    color: {c['textDisabled']};
}}

QSpinBox::up-button, QDoubleSpinBox::up-button {{
    border: none;
    width: 16px;
    border-left: 1px solid {c['borderLight']};
    background-color: transparent;
}}

QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border: none;
    width: 16px;
    border-left: 1px solid {c['borderLight']};
    background-color: transparent;
}}

QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {c['controlFillHover']};
}}

QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid {c['buttonText']};
}}

QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c['buttonText']};
}}

/* ===== 日期时间选择框 ===== */
QDateTimeEdit, QDateEdit, QTimeEdit {{
    background-color: {c['base']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 6px 8px;
    color: {c['windowText']};
}}

QDateTimeEdit:hover, QDateEdit:hover, QTimeEdit:hover {{
    border-color: {c['border']};
}}

QDateTimeEdit:focus, QDateEdit:focus, QTimeEdit:focus {{
    border: 2px solid {c['accent']};
}}

QDateTimeEdit::drop-down, QDateEdit::drop-down, QTimeEdit::drop-down {{
    border: none;
    width: 20px;
}}

QDateTimeEdit QCalendarWidget QSpinBox,
QDateEdit QCalendarWidget QSpinBox,
QTimeEdit QCalendarWidget QSpinBox {{
    background-color: {c['window']};
}}

QCalendarWidget QAbstractItemView {{
    background-color: {c['window']};
    selection-background-color: {c['highlight']};
}}

QCalendarWidget QAbstractItemView::item:hover {{
    background-color: {c['controlFillHover']};
}}

/* ===== 菜单 ===== */
QMenuBar {{
    background-color: {c['window']};
    border-bottom: 1px solid {c['borderLight']};
    padding: 2px;
}}

QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    color: {c['windowText']};
}}

QMenuBar::item:selected {{
    background-color: {c['controlFillHover']};
}}

QMenuBar::item:pressed {{
    background-color: {c['controlFillPressed']};
}}

QMenuBar::item:disabled {{
    color: {c['textDisabled']};
}}

QMenu {{
    background-color: {c['window']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 32px 6px 12px;
    border-radius: {c['radius']};
    color: {c['windowText']};
}}

QMenu::item:selected {{
    background-color: {c['highlight']};
    color: {c['highlightedText']};
}}

QMenu::item:disabled {{
    color: {c['textDisabled']};
}}

QMenu::separator {{
    height: 1px;
    background-color: {c['borderLight']};
    margin: 4px 8px;
}}

QMenu::indicator {{
    width: 16px;
    height: 16px;
    margin-left: 4px;
}}

QMenu::right-arrow {{
    image: none;
    border-left: 5px solid {c['buttonText']};
    border-top: 5px solid transparent;
    border-bottom: 5px solid transparent;
}}

/* ===== 工具栏 ===== */
QToolBar {{
    background-color: {c['window']};
    border: none;
    padding: 4px;
    spacing: 4px;
}}

QToolBar::separator {{
    width: 1px;
    background-color: {c['borderLight']};
    margin: 4px;
}}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: {c['radius']};
    padding: 6px;
}}

QToolButton:hover {{
    background-color: {c['controlFillHover']};
}}

QToolButton:pressed {{
    background-color: {c['controlFillPressed']};
}}

QToolButton:disabled {{
    background-color: transparent;
    opacity: 0.5;
}}

QToolButton[popupMode="1"]::menu-button {{
    border: none;
    width: 16px;
}}

QToolButton[popupMode="2"]::menu-button {{
    border: none;
    width: 16px;
}}

/* ===== 滚动条 ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {c['borderLight']};
    border-radius: 5px;
    min-height: 30px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['border']};
}}

QScrollBar::handle:vertical:pressed {{
    background: {c['accentDark']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {c['borderLight']};
    border-radius: 5px;
    min-width: 30px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {c['border']};
}}

QScrollBar::handle:horizontal:pressed {{
    background: {c['accentDark']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
}}

/* ===== 标签页 ===== */
QTabWidget::pane {{
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    background-color: {c['window']};
}}

QTabBar::tab {{
    background-color: transparent;
    color: {c['windowText']};
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}}

QTabBar::tab:selected {{
    color: {c['accent']};
    border-bottom-color: {c['accent']};
}}

QTabBar::tab:hover:!selected {{
    background-color: {c['controlFillHover']};
}}

QTabBar::tab:disabled {{
    color: {c['textDisabled']};
}}

QTabBar::close-button {{
    image: none;
    border-radius: 4px;
}}

QTabBar::close-button:hover {{
    background-color: {c['controlFillHover']};
}}

/* ===== 堆叠窗口 ===== */
QStackedWidget {{
    background-color: {c['window']};
}}

/* ===== 工具箱 ===== */
QToolBox {{
    background-color: {c['window']};
}}

QToolBox::tab {{
    background-color: {c['controlFill']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    padding: 8px 12px;
    color: {c['windowText']};
}}

QToolBox::tab:selected {{
    background-color: {c['accent']};
    color: {c['highlightedText']};
}}

QToolBox::tab:hover {{
    background-color: {c['controlFillHover']};
}}

QToolBox::tab:!selected {{
    background-color: {c['window']};
}}

/* ===== 分组框 ===== */
QGroupBox {{
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    margin-top: 12px;
    padding-top: 12px;
    color: {c['windowText']};
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {c['windowText']};
}}

QGroupBox::indicator {{
    width: 18px;
    height: 18px;
}}

QGroupBox::indicator:checked {{
    background-color: {c['accent']};
}}

/* ===== 滚动区域 ===== */
QScrollArea {{
    border: none;
    background-color: {c['window']};
}}

QScrollArea > QWidget > QWidget {{
    background-color: {c['window']};
}}

/* ===== 工具提示 ===== */
QToolTip, QTipLabel {{
    background-color: {c['toolTipBase']};
    border: 1px solid {c['border']};
    border-radius: {c['radius']};
    padding: 4px 8px;
    color: {c['toolTipText']};
}}

/* ===== 状态提示 ===== */
QStatusBar {{
    background-color: {c['window']};
    border-top: 1px solid {c['borderLight']};
    color: {c['windowText']};
}}

QStatusBar::item {{
    border: none;
}}

/* ===== 分割器 ===== */
QSplitter {{
    background-color: {c['window']};
}}

QSplitter::handle {{
    background-color: {c['borderLight']};
}}

QSplitter::handle:horizontal {{
    width: 1px;
}}

QSplitter::handle:vertical {{
    height: 1px;
}}

QSplitter::handle:hover {{
    background-color: {c['accent']};
}}

/* ===== 列表视图 ===== */
QListView, QTreeView, QTableView, QColumnView {{
    background-color: {c['base']};
    border: 1px solid {c['borderLight']};
    border-radius: {c['radius']};
    color: {c['windowText']};
    show-decoration-selected: 1;
}}

QListView::item, QTreeView::item, QTableView::item {{
    padding: 6px;
    border-radius: {c['radius']};
}}

QListView::item:selected, QTreeView::item:selected, QTableView::item:selected {{
    background-color: {c['highlight']};
    color: {c['highlightedText']};
}}

QListView::item:hover, QTreeView::item:hover, QTableView::item:hover {{
    background-color: {c['controlFillHover']};
}}

QListView::item:selected:!active, QTreeView::item:selected:!active {{
    background-color: {c['controlFillSelected']};
}}

/* ===== 表格头 ===== */
QHeaderView {{
    background-color: {c['button']};
    border: none;
    border-bottom: 1px solid {c['borderLight']};
}}

QHeaderView::section {{
    background-color: {c['button']};
    color: {c['buttonText']};
    padding: 6px 12px;
    border: none;
    border-right: 1px solid {c['borderLight']};
    font-weight: bold;
}}

QHeaderView::section:last {{
    border-right: none;
}}

QHeaderView::section:hover {{
    background-color: {c['controlFillHover']};
}}

QHeaderView::section:pressed {{
    background-color: {c['controlFillPressed']};
}}

QHeaderView::section:horizontal {{
    border-bottom: 2px solid transparent;
}}

QHeaderView::section:horizontal:selected {{
    border-bottom-color: {c['accent']};
}}

QHeaderView::section:vertical {{
    border-right: 1px solid {c['borderLight']};
    border-bottom: none;
}}

QHeaderView::section:vertical:selected {{
    border-right-color: {c['accent']};
}}

QHeaderView::sort-indicator {{
    image: none;
}}

/* ===== 树视图展开按钮 ===== */
QTreeView::branch {{
    background: transparent;
}}

QTreeView::branch:has-children:!has-siblings {{
    border: none;
}}

/* ===== 停靠窗口 ===== */
QDockWidget {{
    background-color: {c['window']};
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {c['button']};
    border: none;
    border-bottom: 1px solid {c['borderLight']};
    padding: 6px;
    text-align: left;
}}

QDockWidget::close-button, QDockWidget::float-button {{
    border: none;
    background: transparent;
    padding: 2px;
}}

QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {c['controlFillHover']};
    border-radius: 2px;
}}

QDockWidget::separator {{
    background-color: {c['borderLight']};
}}

QDockWidget < QTitleBar {{
    background-color: {c['button']};
}}

/* ===== 主窗口 ===== */
QMainWindow::separator {{
    background-color: {c['borderLight']};
    width: 1px;
    height: 1px;
}}

QMainWindow::separator:hover {{
    background-color: {c['accent']};
}}

/* ===== 对话框按钮 ===== */
QDialogButtonBox {{
    button-layout: 0;
}}

QDialogButtonBox QPushButton {{
    min-width: 75px;
    min-height: 28px;
}}

QDialogButtonBox QPushButton:focus {{
    border: 2px solid {c['accent']};
}}

QDialogButtonBox QPushButton:default {{
    background-color: {c['accent']};
    color: {c['highlightedText']};
}}

/* ===== 自定义按钮样式类 ===== */
QPushButton[class="danger"] {{
    background-color: #D13438;
    border: 1px solid #D13438;
    color: white;
}}

QPushButton[class="danger"]:hover {{
    background-color: #E74856;
    border-color: #E74856;
}}

QPushButton[class="danger"]:pressed {{
    background-color: #A80000;
    border-color: #A80000;
}}

QPushButton[class="success"] {{
    background-color: #107C10;
    border: 1px solid #107C10;
    color: white;
}}

QPushButton[class="success"]:hover {{
    background-color: #16C60C;
    border-color: #16C60C;
}}

QPushButton[class="success"]:pressed {{
    background-color: #0B6A0B;
    border-color: #0B6A0B;
}}

QPushButton[class="outline"] {{
    background-color: transparent;
    border: 1px solid {c['border']};
    color: {c['buttonText']};
}}

QPushButton[class="outline"]:hover {{
    background-color: {c['controlFillHover']};
    border-color: {c['accent']};
}}

QPushButton[class="subtle"] {{
    background-color: transparent;
    border: none;
    color: {c['buttonText']};
}}

QPushButton[class="subtle"]:hover {{
    background-color: {c['controlFillHover']};
}}

QPushButton[class="subtle"]:pressed {{
    background-color: {c['controlFillPressed']};
}}

/* ===== 输入框占位符颜色 ===== */
QLineEdit QPlaceholderText {{
    color: {c['textDisabled']};
}}

/* ===== 聚焦边框动画 ===== */
QWidget:focus {{
    outline: none;
}}

QWidget:focus-visible {{
    outline: 2px solid {c['accent']};
    outline-offset: -2px;
}}

/* ===== 拖拽区域 ===== */
QWidget[Drag="true"] {{
    background-color: {c['controlFillHover']};
}}

/* ===== 载入指示器 ===== */
QLoadingIndicator {{
    color: {c['accent']};
}}

    """

    return qss


def create_fluent_palette(theme: str = 'light') -> QPalette:
    """
    创建 FluentUI3 调色板

    Args:
        theme: 主题类型，'light' 或 'dark'

    Returns:
        QPalette 对象
    """
    style = FluentStyle()
    style.set_theme(theme)
    colors = style.colors()

    # 解析颜色字符串
    def parse_color(hex_color: str) -> QColor:
        if hex_color.startswith('#'):
            return QColor(hex_color)
        return QColor(hex_color)

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, parse_color(colors['window']))
    palette.setColor(QPalette.ColorRole.WindowText, parse_color(colors['windowText']))
    palette.setColor(QPalette.ColorRole.Base, parse_color(colors['base']))
    palette.setColor(QPalette.ColorRole.AlternateBase, parse_color(colors['alternateBase']))
    palette.setColor(QPalette.ColorRole.ToolTipBase, parse_color(colors['toolTipBase']))
    palette.setColor(QPalette.ColorRole.ToolTipText, parse_color(colors['toolTipText']))
    palette.setColor(QPalette.ColorRole.Button, parse_color(colors['button']))
    palette.setColor(QPalette.ColorRole.ButtonText, parse_color(colors['buttonText']))
    palette.setColor(QPalette.ColorRole.Light, parse_color(colors['light']))
    palette.setColor(QPalette.ColorRole.Midlight, parse_color(colors['midlight']))
    palette.setColor(QPalette.ColorRole.Dark, parse_color(colors['dark']))
    palette.setColor(QPalette.ColorRole.Mid, parse_color(colors['mid']))
    palette.setColor(QPalette.ColorRole.Shadow, parse_color(colors['shadow']))
    palette.setColor(QPalette.ColorRole.Highlight, parse_color(colors['highlight']))
    palette.setColor(QPalette.ColorRole.HighlightedText, parse_color(colors['highlightedText']))
    palette.setColor(QPalette.ColorRole.Link, parse_color(colors['link']))
    palette.setColor(QPalette.ColorRole.LinkVisited, parse_color(colors['linkVisited']))
    palette.setColor(QPalette.ColorRole.Text, parse_color(colors['text']))
    palette.setColor(QPalette.ColorRole.PlaceholderText, parse_color(colors['textDisabled']))

    return palette


def detect_system_theme() -> str:
    """
    检测系统主题

    Returns:
        'dark' 或 'light'
    """
    if sys.platform == 'win32':
        try:
            import winreg
            # 读取 Windows 注册表中的主题设置
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return 'dark' if value == 0 else 'light'
        except Exception:
            pass
    return 'light'


def set_fluent_theme(app: QApplication, theme: str = "auto"):
    """
    设置 FluentUI3 主题

    Args:
        app: QApplication 实例
        theme: 主题类型，'light'、'dark' 或 'auto'（自动检测系统主题）
    """
    # 自动检测系统主题
    if theme == "auto":
        theme = detect_system_theme()

    # 设置 Fusion 样式
    app.setStyle(QStyleFactory.create("Fusion"))

    # 设置调色板
    palette = create_fluent_palette(theme)
    app.setPalette(palette)

    # 设置全局样式实例
    _fluent_style.set_theme(theme)

    # 应用 QSS 样式表
    qss = create_fluent_qss(theme)
    app.setStyleSheet(qss)


def set_light_theme(app: QApplication):
    """设置浅色主题（兼容旧接口）"""
    set_fluent_theme(app, 'light')


# 导出
__all__ = [
    'FluentStyle',
    'get_fluent_style',
    'set_theme',
    'create_fluent_qss',
    'create_fluent_palette',
    'set_fluent_theme',
    'set_light_theme',
    'detect_system_theme',
]
