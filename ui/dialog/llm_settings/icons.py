# ui/dialog/llm_settings/icons.py
"""LLM 设置界面品牌图标模块

提供单色 SVG 品牌图标的渲染与任意着色（QSvgRenderer 渲染 +
CompositionMode_SourceIn 着色），并按 (路径, 尺寸, 颜色) 缓存结果；
图标缺失 / QtSvg 不可用时优雅降级为「圆角方块 + 首字符」彩色图标。

SVG 资源位于本包 ``icons/`` 目录；preset_id → 图标文件的映射见
``PRESET_ICON_FILES``。
"""

import hashlib
import os
from typing import Dict, Optional, Tuple

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap

try:  # QtSvg 缺失时优雅降级（品牌图标回退为字母方块）
    from PySide6.QtSvg import QSvgRenderer
    _SVG_OK = True
except ImportError:  # pragma: no cover - 仅在不完整安装时触发
    QSvgRenderer = None
    _SVG_OK = False

# 品牌 SVG 图标资源目录（与本模块同级）
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

# preset_id -> 图标文件名。
# 当前仅为有现成 SVG 的预设建立映射；minimax 与自定义实例暂未覆盖，
# 走字母方块降级（后续补齐 SVG 后在此追加映射即可）。
PRESET_ICON_FILES: Dict[str, str] = {
    "openai": "openai.svg",
    "siliconflow": "siliconflow.svg",
    "glm": "zhipu.svg",
    "ollama": "ollama.svg",
}

# HiDPI 渲染倍率（2x 保证高分屏清晰）
_HIDPI_DPR = 2.0

# 渲染缓存：(路径, 尺寸, 颜色名) -> QPixmap
_svg_cache: Dict[Tuple[str, int, str], QPixmap] = {}


def render_svg_icon(path: str, px: int, color: QColor) -> Optional[QPixmap]:
    """把单色 SVG 渲染成 px 大小并按 color 着色的 QPixmap（2x HiDPI）

    着色原理：先把 SVG 渲染到透明 pixmap，再以
    CompositionMode_SourceIn 用纯色填充 —— 保留 alpha 通道，只替换颜色。
    结果按 (路径, 尺寸, 颜色) 缓存。

    Args:
        path: SVG 文件路径
        px: 目标边长（逻辑像素）
        color: 着色颜色

    Returns:
        Optional[QPixmap]: 渲染结果；QtSvg 不可用或文件非法时返回 None
    """
    if not _SVG_OK:
        return None
    key = (path, px, color.name())
    cached = _svg_cache.get(key)
    if cached is not None:
        return cached
    renderer = QSvgRenderer(path)
    if not renderer.isValid():
        return None
    pm = QPixmap(int(px * _HIDPI_DPR), int(px * _HIDPI_DPR))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0.0, 0.0, pm.width(), pm.height()))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pm.rect(), color)
    painter.end()
    pm.setDevicePixelRatio(_HIDPI_DPR)
    _svg_cache[key] = pm
    return pm


def color_from_name(name: str) -> QColor:
    """按名称哈希取一个低饱和颜色（HSL 空间，避开高饱和）

    Args:
        name: 名称文本

    Returns:
        QColor: 稳定的派生颜色（同名恒同色）
    """
    digest = hashlib.md5(name.encode("utf-8")).hexdigest()
    value = int(digest, 16)
    hue = value % 360
    saturation = 92 + (value >> 9) % 38      # 92-129 / 255，低饱和
    lightness = 128 + (value >> 17) % 24     # 中等明度，保证白字可读
    return QColor.fromHsl(hue, saturation, lightness)


def first_char(name: str) -> str:
    """取名称首字符（ASCII 大写化），用于字母方块降级图标

    Args:
        name: 名称文本

    Returns:
        str: 首字符；空名称返回 "?"
    """
    name = (name or "").strip()
    if not name:
        return "?"
    ch = name[0]
    return ch.upper() if ch.isascii() else ch


def make_avatar(name: str, size: int = 32) -> QPixmap:
    """降级方案：圆角方块 + 首字符的彩色图标

    Args:
        name: 名称文本（取首字符）
        size: 输出边长（px）

    Returns:
        QPixmap: 字母方块图标
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    rect = QRectF(0.5, 0.5, size - 1, size - 1)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color_from_name(name))
    p.drawRoundedRect(rect, size * 0.26, size * 0.26)
    font = p.font()
    font.setPixelSize(int(size * 0.44))
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#ffffff"))
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, first_char(name))
    p.end()
    return pm


def provider_icon_pixmap(
    preset_id: Optional[str], name: str, px: int, color: QColor,
) -> QPixmap:
    """提供商品牌图标：SVG 优先（按 color 着色），失败回退字母方块

    Args:
        preset_id: 预设 id（自定义实例为 None，直接走字母方块）
        name: 实例显示名（字母方块降级时取首字符）
        px: 目标边长（逻辑像素）
        color: SVG 着色颜色

    Returns:
        QPixmap: 品牌图标（HiDPI 2x）
    """
    filename = PRESET_ICON_FILES.get(preset_id or "")
    if filename:
        pm = render_svg_icon(os.path.join(ICONS_DIR, filename), px, color)
        if pm is not None:
            return pm
    pm = make_avatar(name, int(px * _HIDPI_DPR))
    pm.setDevicePixelRatio(_HIDPI_DPR)
    return pm
