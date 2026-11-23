"""
utils/style_qss/registry.py 单元测试

QssRegistry 使用类级状态，测试由 conftest 中的 reset_qss_registry fixture
在每个用例前后自动清理，确保隔离。
"""

from __future__ import annotations

import pytest

from utils.style_qss.registry import QssRegistry, register_styles


# reset_qss_registry 在 test/utils/conftest.py 中 autouse


def test_register_and_get():
    QssRegistry.register("button", "QPushButton {{ color: {accent}; }}")
    assert QssRegistry.get("button") == "QPushButton {{ color: {accent}; }}"


def test_get_missing_returns_empty_string():
    assert QssRegistry.get("not_exists") == ""


def test_register_default_priority_is_fifty():
    QssRegistry.register("a", "a")
    # 未知名称默认优先级为 50
    assert QssRegistry._get_priority("a") == 50


def test_load_order_sorted_by_priority():
    QssRegistry.register("dialog", "dialog", priority=90)
    QssRegistry.register("base", "base", priority=10)
    QssRegistry.register("button", "button", priority=40)
    QssRegistry.register("z_misc", "z_misc")  # default 50

    assert QssRegistry._load_order == ["base", "button", "z_misc", "dialog"]


def test_register_same_name_updates_content_and_preserves_order():
    QssRegistry.register("x", "old", priority=10)
    QssRegistry.register("x", "new", priority=90)
    assert QssRegistry.get("x") == "new"
    assert QssRegistry._load_order.count("x") == 1
    assert QssRegistry._load_order == ["x"]


def test_get_all_concatenates_and_replaces_variables(mocker):
    mocker.patch(
        "utils.style_qss.registry.get_color_dict",
        return_value={"accent": "#0078D4", "text": "#000000"},
    )
    QssRegistry.register("button", "QPushButton {{ color: {accent}; }}")
    QssRegistry.register("label", "QLabel {{ color: {text}; }}")

    qss = QssRegistry.get_all("light")
    assert "#0078D4" in qss
    assert "#000000" in qss
    assert "{accent}" not in qss
    assert "{text}" not in qss
    assert "QPushButton" in qss
    assert "QLabel" in qss


def test_get_all_omits_styles_removed_from_registry():
    QssRegistry.register("a", "content_a")
    QssRegistry.register("b", "content_b")
    del QssRegistry._styles["a"]

    qss = QssRegistry.get_all()
    assert "content_a" not in qss
    assert "content_b" in qss


def test_get_all_empty_registry_returns_empty_string(mocker):
    mocker.patch(
        "utils.style_qss.registry.get_color_dict",
        return_value={"accent": "#0078D4"},
    )
    assert QssRegistry.get_all("light") == ""


def test_replace_variables():
    colors = {"accent": "#0078D4", "text": "#000000"}
    qss = QssRegistry._replace_variables(
        "A {accent} B {text} C {unknown}", colors
    )
    assert qss == "A #0078D4 B #000000 C {unknown}"


def test_priority_lookup_known_and_default():
    assert QssRegistry._get_priority("base") == 10
    assert QssRegistry._get_priority("mainwindow") == 100
    assert QssRegistry._get_priority("custom") == 20
    assert QssRegistry._get_priority("unknown_thing") == 50


def test_apply_variables_with_explicit_theme(mocker):
    mocker.patch(
        "utils.style_qss.registry.get_color_dict",
        return_value={"accent": "#123456"},
    )
    result = QssRegistry.apply_variables("X {accent}", theme="dark")
    assert result == "X #123456"


def test_apply_variables_with_global_theme(mocker):
    mock_style_qss = mocker.MagicMock()
    mock_style_qss.theme.return_value = "dark"
    mocker.patch("utils.style_qss.get_style_qss", return_value=mock_style_qss)
    mocker.patch(
        "utils.style_qss.registry.get_color_dict",
        return_value={"accent": "#123456"},
    )

    result = QssRegistry.apply_variables("X {accent}")
    assert result == "X #123456"
    mock_style_qss.theme.assert_called_once()


def test_clear_removes_all_styles():
    QssRegistry.register("a", "a")
    QssRegistry.register("b", "b")
    QssRegistry.clear()
    assert QssRegistry._styles == {}
    assert QssRegistry._load_order == []
    assert QssRegistry.get("a") == ""


def test_register_styles_delegates_to_styles_init(mocker):
    mock_init_styles = mocker.patch("utils.style_qss.styles.init_styles")
    register_styles()
    mock_init_styles.assert_called_once()
