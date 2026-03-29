import sys
from PySide6.QtWidgets import QApplication, QStyleFactory

from PySide6.QtGui import QPalette, QColor

# 导入 StyleQSS 样式
from utils.style_qss import (
    set_style_qss_theme as _set_style_qss_theme,
    StyleQSS
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
    _set_style_qss_theme(app, theme='light')


def set_style_qss_theme(app: QApplication, theme: str = "auto") -> None:
    """
    设置 StyleQSS 主题

    Args:
        app: QApplication 实例
        theme: 主题类型，'light'、'dark' 或 'auto'（自动检测系统主题）
    """
    _set_style_qss_theme(app, theme=theme)
