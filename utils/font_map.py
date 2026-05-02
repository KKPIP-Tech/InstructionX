"""
Font map — 字体路径状态机映射模块。

以枚举组合（FontFamily × FontVariant × FontWeight）作为状态，
映射到项目相对路径。项目根目录通过 `Path(__file__).resolve().parent.parent` 获取。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

# 项目根目录（resolved 到本文件的上一级目录的上一级）
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
_FONT_DIR: Path = _PROJECT_ROOT / "font"


class FontFamily(Enum):
    """字体家族枚举。"""

    ALIMAMA_FANGYUANTI_VF = "AlimamaFangYuanTiVF"
    ZEN_DOTS = "ZenDots"
    SMILEY_SANS = "SmileySans"
    ALIMAMA_DONGFANG_DAKAI = "AlimamaDongFangDaKai"
    ALIBABA_PUHUITI_3 = "AlibabaPuHuiTiv3"


class FontVariant(Enum):
    """字体变体枚举。"""

    REGULAR = "Regular"
    THIN = "Thin"
    LIGHT = "Light"
    MEDIUM = "Medium"
    SEMI_BOLD = "SemiBold"
    BOLD = "Bold"
    EXTRA_BOLD = "ExtraBold"
    HEAVY = "Heavy"
    BLACK = "Black"
    OBLIQUE = "Oblique"
    LIGHT_ITALIC = "LightItalic"
    ITALIC = "Italic"
    MEDIUM_ITALIC = "MediumItalic"
    BOLD_ITALIC = "BoldItalic"
    HEAVY_ITALIC = "HeavyItalic"


class FontWeight(Enum):
    """
    阿里巴巴普惠体字重枚举（对应文件名中的数字后缀）。
    其他字体（方正、ZenDots、得意黑）使用 FontVariant 区分，不再使用此枚举。
    """

    THIN = 35
    LIGHT = 45
    REGULAR = 55
    MEDIUM = 65
    SEMI_BOLD = 75
    BOLD = 85
    EXTRA_BOLD = 95
    HEAVY = 105
    BLACK = 115


@dataclass(frozen=True, slots=True)
class FontInfo:
    """字体元信息。"""

    family: FontFamily
    variant: FontVariant
    weight: int | None  # AlibabaPuHuiTi 系列有效
    relative_path: str  # 相对于项目根目录的路径
    absolute_path: str  # 绝对路径

    @property
    def font_family_name(self) -> str:
        """返回字体家族显示名称。"""
        return self.family.value

    @property
    def font_style_name(self) -> str:
        """返回 Qt 样式名（Family Style）。"""
        variant = self.variant.value
        if self.weight is not None:
            # AlibabaPuHuiTi-3 格式
            return f"{self.family.value} {variant}"
        return f"{self.family.value} {variant}"


# ---------------------------------------------------------------------------
# 静态字体路径注册表
# ---------------------------------------------------------------------------
# 格式：(FontFamily, FontVariant, weight_or_None) -> relative_path (相对于 font/)
# weight_or_None: 仅 AlibabaPuHuiTi 系列需要字重数字后缀
# ---------------------------------------------------------------------------

_FONT_REGISTRY: dict[tuple[FontFamily, FontVariant, int | None], str] = {
    # AlimamaFangYuanTiVF
    (
        FontFamily.ALIMAMA_FANGYUANTI_VF,
        FontVariant.THIN,
        None,
    ): "AlimamaFangYuanTiVF/AlimamaFangYuanTiVF-Thin.ttf",
    # ZenDots
    (
        FontFamily.ZEN_DOTS,
        FontVariant.REGULAR,
        None,
    ): "ZenDots/ZenDots-Regular.otf",
    # SmileySans
    (
        FontFamily.SMILEY_SANS,
        FontVariant.OBLIQUE,
        None,
    ): "SmileySans/SmileySans-Oblique.otf",
    # AlimamaDongFangDaKai
    (
        FontFamily.ALIMAMA_DONGFANG_DAKAI,
        FontVariant.REGULAR,
        None,
    ): "AlimamaDongFangDaKai/AlimamaDongFangDaKai-Regular.otf",
    # AlibabaPuHuiTi-3 系列（9 字重）
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.REGULAR,
        55,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-55-Regular.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.THIN,
        35,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-35-Thin.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.LIGHT,
        45,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-45-Light.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.MEDIUM,
        65,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-65-Medium.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.SEMI_BOLD,
        75,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-75-SemiBold.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.BOLD,
        85,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-85-Bold.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.EXTRA_BOLD,
        95,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-95-ExtraBold.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.HEAVY,
        105,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-105-Heavy.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.BLACK,
        115,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-115-Black.otf",
    # AlibabaPuHuiTi-3 Regular L3 变体（仅 Regular 字重但支持更多字形）
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.REGULAR,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-55-RegularL3.otf",
    # AlibabaSans 意大利体系列
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.LIGHT_ITALIC,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaSans-LightItalic.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.ITALIC,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaSans-Italic.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.MEDIUM_ITALIC,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaSans-MediumItalic.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.BOLD_ITALIC,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaSans-BoldItalic.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.HEAVY_ITALIC,
        None,
    ): "AlibabaPuHuiTiv3/AlibabaSans-HeavyItalic.otf",
    # AlibabaSansJP 日文系列
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.REGULAR,
        0,
    ): "AlibabaPuHuiTiv3/AlibabaSansJP-Regular.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.MEDIUM,
        0,
    ): "AlibabaPuHuiTiv3/AlibabaSansJP-Medium.otf",
    (
        FontFamily.ALIBABA_PUHUITI_3,
        FontVariant.BOLD,
        0,
    ): "AlibabaPuHuiTiv3/AlibabaSansJP-Bold.otf",
}


class FontMap:
    """
    字体路径状态机核心类。

    通过 FontFamily × FontVariant × FontWeight（可选）组合，
    以枚举状态转移方式查询字体文件路径。
    """

    @classmethod
    def _make_key(
        cls,
        family: FontFamily,
        variant: FontVariant,
        weight: int | None,
    ) -> tuple[FontFamily, FontVariant, int | None]:
        return (family, variant, weight)

    @classmethod
    def get(cls, family: FontFamily, variant: FontVariant, weight: int | None = None) -> FontInfo | None:
        """
        根据字体家族、变体、字重获取 FontInfo。

        Args:
            family: 字体家族枚举
            variant: 字体变体枚举
            weight: 字重数值（仅 AlibabaPuHuiTi 系列需要）

        Returns:
            FontInfo 或 None（未找到时）
        """
        key = cls._make_key(family, variant, weight)
        relative = _FONT_REGISTRY.get(key)
        if relative is None:
            return None
        absolute = str(_FONT_DIR / relative)
        return FontInfo(
            family=family,
            variant=variant,
            weight=weight,
            relative_path=str(Path("font") / relative),
            absolute_path=absolute,
        )

    @classmethod
    def get_path(
        cls,
        family: FontFamily,
        variant: FontVariant,
        weight: int | None = None,
    ) -> str | None:
        """
        获取字体文件的绝对路径字符串。

        Returns:
            绝对路径字符串或 None
        """
        info = cls.get(family, variant, weight)
        return info.absolute_path if info else None

    @classmethod
    def get_relative_path(
        cls,
        family: FontFamily,
        variant: FontVariant,
        weight: int | None = None,
    ) -> str | None:
        """
        获取字体文件相对于项目根目录的路径字符串。

        Returns:
            相对路径字符串或 None
        """
        info = cls.get(family, variant, weight)
        return info.relative_path if info else None

    @classmethod
    def all_fonts(cls) -> list[FontInfo]:
        """返回注册表中所有字体的 FontInfo 列表。"""
        result: list[FontInfo] = []
        for (family, variant, weight), relative in _FONT_REGISTRY.items():
            absolute = str(_FONT_DIR / relative)
            result.append(
                FontInfo(
                    family=family,
                    variant=variant,
                    weight=weight,
                    relative_path=str(Path("font") / relative),
                    absolute_path=absolute,
                )
            )
        return result

    @classmethod
    def exists(cls, family: FontFamily, variant: FontVariant, weight: int | None = None) -> bool:
        """检查指定的字体文件在文件系统中是否存在。"""
        path = cls.get_path(family, variant, weight)
        if path is None:
            return False
        return os.path.isfile(path)

    @classmethod
    def font_dir(cls) -> Path:
        """返回 font/ 目录的 Path 对象。"""
        return _FONT_DIR

    @classmethod
    def project_root(cls) -> Path:
        """返回项目根目录的 Path 对象。"""
        return _PROJECT_ROOT
