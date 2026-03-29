"""
调色板创建模块
"""

from PySide6.QtGui import QColor, QPalette


def parse_color(hex_color: str) -> QColor:
    """解析颜色字符串"""
    if hex_color.startswith('#'):
        return QColor(hex_color)
    return QColor(hex_color)


def create_qss_palette(theme: str = 'light') -> QPalette:
    """
    创建 QSS 调色板

    Args:
        theme: 主题类型，'light' 或 'dark'

    Returns:
        QPalette 对象
    """
    from .colors import StyleQSSColors, get_color_dict

    colors = get_color_dict(theme)

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
