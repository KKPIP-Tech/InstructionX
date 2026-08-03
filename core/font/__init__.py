"""字体子系统（core/font）。

对外导出：FontManager 单例（get_font_manager 访问器）、FontRecord、
FontInstallError。
"""

from .exceptions import FontInstallError
from .font_record import FontRecord
from .manager import FontManager, get_font_manager

__all__ = [
    "FontInstallError",
    "FontManager",
    "FontRecord",
    "get_font_manager",
]
