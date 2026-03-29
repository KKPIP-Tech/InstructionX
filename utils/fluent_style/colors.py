"""
FluentUI3 颜色定义
"""

from PySide6.QtGui import QColor


class FluentColors:
    """FluentUI3 颜色定义类"""

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

            # 文本色
            'textPrimary': '#000000',
            'textSecondary': '#666666',

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

            # 文本色
            'textPrimary': '#FFFFFF',
            'textSecondary': '#999999',

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

    @classmethod
    def get_colors(cls, theme: str = 'light') -> dict:
        """获取指定主题的颜色"""
        return cls.COLORS.get(theme, cls.COLORS['light']).copy()

    def set_theme(self, theme: str):
        """设置当前主题"""
        if theme in ('light', 'dark'):
            self._theme = theme
            self._colors = self.COLORS[theme].copy()

    @property
    def theme(self) -> str:
        """获取当前主题"""
        return getattr(self, '_theme', 'light')

    @property
    def colors(self) -> dict:
        """获取当前颜色"""
        return getattr(self, '_colors', self.COLORS['light'])

    @classmethod
    def get_color(cls, name: str, theme: str = 'light') -> str:
        """获取指定颜色"""
        colors = cls.get_colors(theme)
        return colors.get(name, '#000000')


# 导出颜色常量供 QSS 使用
def get_color_dict(theme: str = 'light') -> dict:
    """获取颜色字典，用于 QSS 变量替换"""
    return FluentColors.get_colors(theme)
