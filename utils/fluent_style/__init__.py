"""
FluentUI3 风格样式模块

提供 FluentUI3 颜色定义和 Qt Style Sheets 样式支持
"""

import sys
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

# 导出主要接口
from .colors import FluentColors, get_color_dict
from .palette import create_fluent_palette
from .registry import QssRegistry

# 导入样式模块（自动加载所有 QSS）
from . import styles


class FluentStyle:
    """
    FluentUI3 风格样式类

    提供 FluentUI3 颜色和样式支持
    """

    def __init__(self):
        self._theme = 'light'
        self._colors = FluentColors.get_colors('light')

    def set_theme(self, theme: str):
        """设置主题"""
        if theme in ('light', 'dark'):
            self._theme = theme
            self._colors = FluentColors.get_colors(theme)

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
    创建 FluentUI3 Qt Style Sheets

    从模块化的 QSS 文件聚合生成

    Args:
        theme: 主题类型，'light' 或 'dark'

    Returns:
        QSS 样式字符串
    """
    return QssRegistry.get_all(theme)


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
    'FluentColors',
    'get_fluent_style',
    'set_theme',
    'create_fluent_qss',
    'create_fluent_palette',
    'set_fluent_theme',
    'set_light_theme',
    'detect_system_theme',
    'get_color_dict',
    'QssRegistry',
]
