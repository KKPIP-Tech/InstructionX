"""
StyleQSS 颜色定义
"""

import base64
import os
from pathlib import Path
from PySide6.QtGui import QColor, QImage, QPainter, QPolygonF
from PySide6.QtCore import Qt, QPointF, QByteArray, QBuffer, QIODevice


class StyleQSSColors:
    """StyleQSS 颜色定义类"""

    # 颜色定义
    COLORS = {
        'light': {
            # 基础色
            'window': '#FFFFFF',
            'windowText': '#000000',
            'base': '#FFFFFF',
            'alternateBase': '#F3F3F3',
            'toolTipBase': '#FFFFFF',
            'toolTipText': '#000000',

            # 技能面板专用
            'skillPanel': '#F5F7FA',
            'skillPanelTab': '#E8E8E8',
            'skillPanelHeaderBg': '#EBEEF2',
            'skillButtonHover': '#E8F4FD',
            'skillButtonActiveText': '#0078D4',

            # 列表控件专用
            'listBg': '#FFFFFF',
            'listBorder': '#D8D8D8',
            'listText': '#000000',
            'treeBranchArrow': '#6B7280',

            # 卡片/面板专用
            'cardBackground': '#FFFFFF',
            'codeBackground': '#F5F5F5',

            # 分割器专用
            'splitterHandle': '#E5E7EB',

            # 进度条专用
            'progressBg': '#F8F9FA',
            'progressBorder': '#E5E7EB',
            'progressSuccess': '#10B981',
            'progressWarning': '#F59E0B',
            'progressError': '#EF4444',

            # 菜单/工具栏专用
            'menuBarBg': '#F0F2F5',
            'menuPopupBg': '#FFFFFF',
            'accentDim': 'rgba(0, 120, 212, 0.08)',

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

            # 专用
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
            'radius': '3px',
            'radiusLarge': '6px',
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

            # 技能面板专用
            'skillPanel': '#2C2C2C',
            'skillPanelTab': '#6A6A6A',
            'skillPanelHeaderBg': '#363636',
            'skillButtonHover': '#1A3A5C',
            'skillButtonActiveText': '#FFFFFF',

            # 列表控件专用
            'listBg': '#1E1E1E',
            'listBorder': '#2A2A2C',
            'listText': '#B0B8BC',
            'treeBranchArrow': '#9CA3AF',

            # 卡片/面板专用
            'cardBackground': '#2C2C2C',
            'codeBackground': '#1E1E1E',

            # 分割器专用
            'splitterHandle': '#21262D',

            # 进度条专用
            'progressBg': '#161B22',
            'progressBorder': '#21262D',
            'progressSuccess': '#10B981',
            'progressWarning': '#F59E0B',
            'progressError': '#EF4444',

            # 菜单/工具栏专用
            'menuBarBg': '#22272E',
            'menuPopupBg': '#1C2128',
            'accentDim': 'rgba(0, 120, 212, 0.1)',

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

            # 专用
            'accent': '#0078D4',
            'accentLight': '#1A3A5C',
            'accentDark': '#005A9E',

            # 控件状态填充
            'controlFill': 'rgba(255, 255, 255, 7)',
            'controlFillHover': 'rgba(255, 255, 255, 12)',
            'controlFillPressed': 'rgba(255, 255, 255, 18)',
            'controlFillDisabled': 'rgba(255, 255, 255, 4)',
            'controlFillSelected': 'rgba(0, 120, 212, 40)',

            # 圆角
            'radius': '3px',
            'radiusLarge': '6px',
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


def _render_arrow_image(color: str, direction: str, filepath: str) -> None:
    """渲染单个箭头 PNG 到指定路径（异常向上抛出，由调用方降级处理）"""
    img = QImage(10, 6, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)

    if direction == 'down':
        polygon = QPolygonF([
            QPointF(0, 0), QPointF(10, 0), QPointF(5, 6)
        ])
    else:
        polygon = QPolygonF([
            QPointF(0, 6), QPointF(10, 6), QPointF(5, 0)
        ])
    painter.drawPolygon(polygon)
    painter.end()
    img.save(filepath)


def _ensure_arrow_images(theme: str, colors: dict) -> dict:
    """
    获取主题色箭头 PNG 的绝对路径字典（正斜杠格式）

    优先只读使用包内预生成图片（assets/arrows/）；缺失时生成到用户缓存
    目录（~/.instructionx/cache/arrows），不再向包目录写文件（只读安装
    位置下写包目录会失败）；缓存写入失败时静默降级（仍返回目标路径，
    Qt 加载失败仅表现为不显示箭头）。
    """
    # 包内预生成图片目录（只读使用）
    package_dir = os.path.join(os.path.dirname(__file__), 'assets', 'arrows')

    arrows = {
        'spinBoxArrowUp': ('windowText', 'up'),
        'spinBoxArrowDown': ('windowText', 'down'),
        'comboBoxArrowDown': ('buttonText', 'down'),
    }

    cache_dir = None  # 用户缓存目录，惰性创建
    result = {}
    for var_name, (color_key, direction) in arrows.items():
        color = colors.get(color_key, '#000000')
        filename = f"{var_name}_{theme}.png"

        # 包内已有预生成图片：直接只读使用
        package_path = os.path.join(package_dir, filename)
        if os.path.exists(package_path):
            result[var_name] = package_path.replace('\\', '/')
            continue

        # 缺失时生成到用户缓存目录
        if cache_dir is None:
            cache_dir = str(Path.home() / '.instructionx' / 'cache' / 'arrows')
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except OSError:
                pass
        filepath = os.path.join(cache_dir, filename)

        if not os.path.exists(filepath):
            try:
                _render_arrow_image(color, direction, filepath)
            except Exception:
                pass  # 写失败静默降级

        result[var_name] = filepath.replace('\\', '/')

    return result


# 导出颜色常量供 QSS 使用
def get_color_dict(theme: str = 'light') -> dict:
    """获取颜色字典，用于 QSS 变量替换"""
    colors = StyleQSSColors.get_colors(theme)
    arrow_paths = _ensure_arrow_images(theme, colors)
    colors.update(arrow_paths)
    return colors
