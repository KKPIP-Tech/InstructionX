"""
utils/font_map.py 单元测试

测试策略：
- 只读取全局 _FONT_REGISTRY，不修改它。
- 文件存在性检查使用 mock，避免依赖真实字体文件。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.font_map import (
    FontFamily,
    FontInfo,
    FontMap,
    FontVariant,
    FontWeight,
    _FONT_REGISTRY,
)


def test_font_family_enum_values():
    """FontFamily 枚举值应与注册表键一致。"""
    assert FontFamily.ZEN_DOTS.value == "ZenDots"
    assert FontFamily.ALIMAMA_FANGYUANTI_VF.value == "AlimamaFangYuanTiVF"


def test_font_variant_enum_values():
    assert FontVariant.REGULAR.value == "Regular"
    assert FontVariant.BOLD_ITALIC.value == "BoldItalic"


def test_font_weight_values():
    assert FontWeight.BOLD.value == 85
    assert FontWeight.THIN.value == 35


def test_font_info_properties():
    info = FontInfo(
        family=FontFamily.ZEN_DOTS,
        variant=FontVariant.REGULAR,
        weight=None,
        relative_path="font/ZenDots/ZenDots-Regular.otf",
        absolute_path="/tmp/ZenDots-Regular.otf",
    )
    assert info.font_family_name == "ZenDots"
    assert info.font_style_name == "ZenDots Regular"
    assert info.weight is None


def test_font_info_with_weight():
    info = FontInfo(
        family=FontFamily.ALIBABA_PUHUITI_3,
        variant=FontVariant.BOLD,
        weight=FontWeight.BOLD.value,
        relative_path="font/AlibabaPuHuiTiv3/AlibabaPuHuiTi-3-85-Bold.otf",
        absolute_path="/tmp/AlibabaPuHuiTi-3-85-Bold.otf",
    )
    assert info.weight == 85
    assert info.font_style_name == "AlibabaPuHuiTiv3 Bold"


def test_get_known_font_without_weight():
    info = FontMap.get(FontFamily.ZEN_DOTS, FontVariant.REGULAR)
    assert info is not None
    assert info.family == FontFamily.ZEN_DOTS
    assert info.variant == FontVariant.REGULAR
    assert info.weight is None
    assert Path(info.relative_path) == Path("font") / "ZenDots" / "ZenDots-Regular.otf"
    assert Path(info.absolute_path).name == "ZenDots-Regular.otf"


def test_get_known_font_with_weight():
    info = FontMap.get(
        FontFamily.ALIBABA_PUHUITI_3, FontVariant.MEDIUM, FontWeight.MEDIUM.value
    )
    assert info is not None
    assert info.weight == FontWeight.MEDIUM.value
    assert "AlibabaPuHuiTi-3-65-Medium.otf" in info.absolute_path


def test_get_known_font_jp_weight_zero():
    """AlibabaSansJP 使用 weight=0 的边界键。"""
    info = FontMap.get(FontFamily.ALIBABA_PUHUITI_3, FontVariant.REGULAR, 0)
    assert info is not None
    assert info.weight == 0
    assert "AlibabaSansJP-Regular.otf" in info.absolute_path


def test_get_returns_none_for_unregistered():
    assert FontMap.get(FontFamily.ZEN_DOTS, FontVariant.BOLD) is None
    assert (
        FontMap.get(
            FontFamily.ALIBABA_PUHUITI_3, FontVariant.REGULAR, FontWeight.BLACK.value
        )
        is None
    )


def test_get_path_returns_absolute_string():
    path = FontMap.get_path(FontFamily.SMILEY_SANS, FontVariant.OBLIQUE)
    assert path is not None
    assert path.endswith("SmileySans-Oblique.otf")


def test_get_path_returns_none_when_missing():
    assert FontMap.get_path(FontFamily.ZEN_DOTS, FontVariant.BOLD) is None


def test_get_relative_path():
    rel = FontMap.get_relative_path(FontFamily.SMILEY_SANS, FontVariant.OBLIQUE)
    assert Path(rel) == Path("font") / "SmileySans" / "SmileySans-Oblique.otf"
    assert FontMap.get_relative_path(FontFamily.ZEN_DOTS, FontVariant.BOLD) is None


def test_all_fonts_matches_registry():
    all_fonts = FontMap.all_fonts()
    assert len(all_fonts) == len(_FONT_REGISTRY)
    for info in all_fonts:
        assert isinstance(info, FontInfo)
        assert Path(info.relative_path).parts[0] == "font"


def test_font_dir_and_project_root():
    assert FontMap.font_dir().name == "font"
    assert FontMap.project_root().name == "InstructionX"


def test_exists_true_when_file_present(mocker):
    mocker.patch("utils.font_map.os.path.isfile", return_value=True)
    assert FontMap.exists(FontFamily.ZEN_DOTS, FontVariant.REGULAR) is True


def test_exists_false_when_file_missing(mocker):
    mocker.patch("utils.font_map.os.path.isfile", return_value=False)
    assert FontMap.exists(FontFamily.ZEN_DOTS, FontVariant.REGULAR) is False


def test_exists_false_when_unregistered():
    assert FontMap.exists(FontFamily.ZEN_DOTS, FontVariant.BOLD) is False
