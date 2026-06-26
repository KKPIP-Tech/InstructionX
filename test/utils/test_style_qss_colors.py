"""
utils/style_qss/colors.py 单元测试

- 所有需要 QPainter/QImage 的测试都使用 qapp_instance fixture。
- 箭头图片生成通过 monkeypatch __file__ 重定向到 tmp_path，
  避免写入项目 utils/style_qss/assets/arrows 目录。
"""

from __future__ import annotations

import os

import pytest

from utils.style_qss.colors import (
    StyleQSSColors,
    _ensure_arrow_images,
    get_color_dict,
)


def test_get_colors_returns_independent_copy():
    c1 = StyleQSSColors.get_colors("light")
    c2 = StyleQSSColors.get_colors("light")
    assert c1 is not c2
    assert c1 == c2
    c1["window"] = "#000000"
    assert StyleQSSColors.get_colors("light")["window"] == "#FFFFFF"


def test_get_colors_light_and_dark_differ():
    light = StyleQSSColors.get_colors("light")
    dark = StyleQSSColors.get_colors("dark")
    assert light["window"] != dark["window"]
    assert light["windowText"] != dark["windowText"]


def test_get_colors_unknown_theme_defaults_to_light():
    colors = StyleQSSColors.get_colors("nonexistent")
    assert colors == StyleQSSColors.get_colors("light")


def test_get_color_known_keys():
    assert StyleQSSColors.get_color("window", "light") == "#FFFFFF"
    assert StyleQSSColors.get_color("window", "dark") == "#202020"


def test_get_color_unknown_returns_black():
    assert StyleQSSColors.get_color("does_not_exist", "light") == "#000000"


def test_instance_defaults_to_light():
    inst = StyleQSSColors()
    assert inst.theme == "light"
    assert inst.colors == StyleQSSColors.COLORS["light"]


def test_instance_set_theme():
    inst = StyleQSSColors()
    inst.set_theme("dark")
    assert inst.theme == "dark"
    assert inst.colors == StyleQSSColors.COLORS["dark"]


def test_instance_set_invalid_theme_is_ignored():
    inst = StyleQSSColors()
    inst.set_theme("dark")
    inst.set_theme("invalid")
    assert inst.theme == "dark"
    inst2 = StyleQSSColors()
    inst2.set_theme("invalid")
    assert inst2.theme == "light"


def test_instance_colors_property_returns_internal_dict():
    inst = StyleQSSColors()
    inst.set_theme("dark")
    assert inst.colors is inst._colors


def test_get_color_dict_includes_arrow_paths(mocker):
    """get_color_dict 应在颜色字典基础上注入箭头图片路径。"""
    mocker.patch(
        "utils.style_qss.colors._ensure_arrow_images",
        return_value={
            "spinBoxArrowUp": "/tmp/spin_up.png",
            "spinBoxArrowDown": "/tmp/spin_down.png",
            "comboBoxArrowDown": "/tmp/combo_down.png",
        },
    )
    colors = get_color_dict("dark")
    assert colors["spinBoxArrowUp"] == "/tmp/spin_up.png"
    assert colors["window"] == StyleQSSColors.COLORS["dark"]["window"]


def test_ensure_arrow_images_generates_files(qapp_instance, tmp_path, monkeypatch):
    """箭头图片不存在时应创建 PNG 文件并返回正斜杠路径。"""
    import utils.style_qss.colors as colors_module

    monkeypatch.setattr(colors_module, "__file__", str(tmp_path / "colors.py"))
    colors = StyleQSSColors.get_colors("light")

    result = _ensure_arrow_images("light", colors)

    assert set(result.keys()) == {
        "spinBoxArrowUp",
        "spinBoxArrowDown",
        "comboBoxArrowDown",
    }
    for var_name, path in result.items():
        assert os.path.exists(path)
        assert path == path.replace("\\", "/")
        assert path.endswith(f"{var_name}_light.png")


def test_ensure_arrow_images_skips_existing_files(
    qapp_instance, tmp_path, monkeypatch, mocker
):
    """箭头图片已存在时不应再实例化 QImage。"""
    import utils.style_qss.colors as colors_module

    monkeypatch.setattr(colors_module, "__file__", str(tmp_path / "colors.py"))
    colors = StyleQSSColors.get_colors("dark")

    # 先生成文件
    _ensure_arrow_images("dark", colors)

    mock_image = mocker.patch("utils.style_qss.colors.QImage")
    _ensure_arrow_images("dark", colors)
    mock_image.assert_not_called()
