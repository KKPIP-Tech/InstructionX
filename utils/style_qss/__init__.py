"""
StyleQSS 样式模块

提供 Qt Style Sheets 样式支持，包含颜色定义、调色板和样式管理
"""

import sys
from PySide6.QtWidgets import QApplication, QStyleFactory
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette

# 导出主要接口
from .colors import StyleQSSColors, get_color_dict
from .palette import create_qss_palette
from .registry import QssRegistry

# 导入样式模块（自动加载所有 QSS）
from . import styles


class StyleQSS:
    """
    StyleQSS 样式类

    提供颜色和样式支持
    """

    def __init__(self):
        self._theme = 'light'
        self._colors = StyleQSSColors.get_colors('light')

    def set_theme(self, theme: str):
        """设置主题"""
        if theme in ('light', 'dark'):
            self._theme = theme
            self._colors = StyleQSSColors.get_colors(theme)

    def theme(self) -> str:
        """获取当前主题"""
        return self._theme

    def colors(self) -> dict:
        """获取当前颜色"""
        return self._colors

    def color(self, name: str) -> str:
        """获取指定颜色"""
        return self._colors.get(name, '#000000')

    def get_color_dict(self) -> dict:
        """获取颜色字典（兼容接口）"""
        return self._colors

    def get(self, key: str, default: str = "") -> str:
        """获取指定样式的值（兼容接口）"""
        from .registry import QssRegistry
        styles = QssRegistry.get_all(self._theme)
        # 这是一个简化实现，实际应该解析 QSS
        return default


# 全局样式实例
_style_qss = StyleQSS()


def get_style_qss() -> StyleQSS:
    """获取全局 StyleQSS 实例"""
    return _style_qss


def set_theme(theme: str):
    """设置全局主题"""
    _style_qss.set_theme(theme)


def create_qss(theme: str = 'light') -> str:
    """
    创建 QSS 样式表

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


def set_style_qss_theme(app: QApplication, theme: str = "auto"):
    """
    设置 StyleQSS 主题

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
    palette = create_qss_palette(theme)
    app.setPalette(palette)

    # 设置全局样式实例
    _style_qss.set_theme(theme)

    # 应用 QSS 样式表
    qss = create_qss(theme)
    app.setStyleSheet(qss)


def set_light_theme(app: QApplication):
    """设置浅色主题（兼容旧接口）"""
    set_style_qss_theme(app, 'light')


# 导出
__all__ = [
    'StyleQSS',
    'StyleQSSColors',
    'get_style_qss',
    'set_theme',
    'create_qss',
    'create_qss_palette',
    'set_style_qss_theme',
    'set_light_theme',
    'detect_system_theme',
    'get_color_dict',
    'QssRegistry',
]
