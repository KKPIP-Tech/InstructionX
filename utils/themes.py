import sys
from PySide6.QtWidgets import QApplication, QStyleFactory

from PySide6.QtGui import QPalette, QColor

# 导入 FluentUI3 样式
from utils.fluent_style import (
    set_fluent_theme as _set_fluent_theme,
    FluentStyle
)


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


def set_light_theme(app: QApplication) -> None:
    """
    设置浅色主题（保留兼容）
    """
    _set_fluent_theme(app, theme='light')


def set_fluent_theme(app: QApplication, theme: str = "auto") -> None:
    """
    设置 FluentUI3 主题

    Args:
        app: QApplication 实例
        theme: 主题类型，'light'、'dark' 或 'auto'（自动检测系统主题）
    """
    _set_fluent_theme(app, theme=theme)
