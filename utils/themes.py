"""主题工具兼容层

detect_system_theme / set_light_theme 的实现已统一到 utils.style_qss，
此处直接 re-export，保持 utils.themes.xxx 引用路径向后兼容。
"""
from PySide6.QtWidgets import QApplication

# 导入 StyleQSS 样式（detect_system_theme / set_light_theme 为 re-export）
from utils.style_qss import (
    detect_system_theme,
    set_light_theme,
    set_style_qss_theme as _set_style_qss_theme,
)


def set_style_qss_theme(app: QApplication, theme: str = "auto") -> None:
    """
    设置 StyleQSS 主题

    Args:
        app: QApplication 实例
        theme: 主题类型，'light'、'dark' 或 'auto'（自动检测系统主题）
    """
    _set_style_qss_theme(app, theme=theme)
