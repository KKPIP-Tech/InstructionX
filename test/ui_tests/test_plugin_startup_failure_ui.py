"""插件启动失败提示界面测试。

验证依赖或入口加载失败后，主窗口首次显示会弹出提示，并且资源目录
不会被误报。
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.plugin.plugin_startup import (
    FAILURE_DEPENDENCY_INSTALL,
    FAILURE_MISSING_MODULE,
    PluginLoadFailure,
)


def test_format_dependency_failure_contains_plugin_and_dependencies():
    """依赖安装失败提示应包含插件名、路径和缺失依赖。"""
    from ui.main_window import InstructionXMainWindow

    failure = PluginLoadFailure(
        plugin_name="Demo Plugin",
        plugin_dir=Path("C:/InstructionX/plugin/demo"),
        reason=FAILURE_DEPENDENCY_INSTALL,
        detail="pip failed",
        missing_dependencies=("demo-pkg",),
    )
    fake_window = SimpleNamespace()

    text = InstructionXMainWindow._format_plugin_load_failure(
        fake_window, failure)

    assert "Demo Plugin" in text
    assert "plugin" in text
    assert "demo" in text
    assert "demo-pkg" in text
    assert "pip failed" in text


def test_format_missing_module_contains_module_name():
    """缺少模块提示应展示具体模块名。"""
    from ui.main_window import InstructionXMainWindow

    failure = PluginLoadFailure(
        plugin_name="Demo Plugin",
        plugin_dir=Path("C:/InstructionX/plugin/demo"),
        reason=FAILURE_MISSING_MODULE,
        detail="No module named 'demo_sdk'",
        missing_module="demo_sdk",
    )

    text = InstructionXMainWindow._format_plugin_load_failure(
        SimpleNamespace(), failure)

    assert "demo_sdk" in text


def test_show_failure_dialog_uses_single_acknowledge_button(
    mocker, qtbot
):
    """存在启动失败时，应弹出一个可确认的提示框。"""
    from ui.main_window import InstructionXMainWindow

    failure = PluginLoadFailure(
        plugin_name="Demo Plugin",
        plugin_dir=Path("C:/InstructionX/plugin/demo"),
        reason=FAILURE_DEPENDENCY_INSTALL,
        detail="install failed",
        missing_dependencies=("demo-pkg",),
    )
    fake_window = SimpleNamespace()
    fake_window.plugin_manager = MagicMock()
    fake_window.plugin_manager.get_plugin_load_failures.return_value = [
        failure]
    fake_window._format_plugin_load_failure = (
        lambda item: InstructionXMainWindow._format_plugin_load_failure(
            fake_window, item))
    dialog_info = mocker.patch("ui.main_window.Dialog.info")

    InstructionXMainWindow._show_plugin_load_failures(fake_window)

    dialog_info.assert_called_once()
    assert dialog_info.call_args.kwargs["ok_text"]


def test_failure_dialog_is_requested_once_after_first_show(
    mocker, qtbot
):
    """同一窗口重复显示时不得重复弹出启动失败提示。"""
    from ui.main_window import InstructionXMainWindow

    mocker.patch("ui.main_window.TrayIconManager")
    mocker.patch.object(InstructionXMainWindow, "_load_saved_theme")
    mocker.patch.object(InstructionXMainWindow, "_create_menus")
    mocker.patch.object(InstructionXMainWindow, "_create_main_layout")
    mocker.patch.object(
        InstructionXMainWindow, "_prewarm_blueprint_viewport")
    window = InstructionXMainWindow()
    qtbot.addWidget(window)
    window._show_plugin_load_failures = MagicMock()

    window.show()
    qtbot.wait(0)
    window.hide()
    window.show()
    qtbot.wait(0)

    window._show_plugin_load_failures.assert_called_once()
    window.hide()


def test_no_failure_dialog_when_manager_has_no_failures(mocker):
    """没有启动失败时不创建提示框。"""
    from ui.main_window import InstructionXMainWindow

    fake_window = SimpleNamespace()
    fake_window.plugin_manager = MagicMock()
    fake_window.plugin_manager.get_plugin_load_failures.return_value = []
    dialog_info = mocker.patch("ui.main_window.Dialog.info")

    InstructionXMainWindow._show_plugin_load_failures(fake_window)

    dialog_info.assert_not_called()
