"""主窗口 closeEvent 分发专项测试

覆盖（对应 close-to-tray-report.md §6，被测代码：ui/main_window.py 的
closeEvent / _ask_close_choice / _dispatch_close_choice）：
- EXIT 选择：_force_quit 置位 + event.accept + QApplication.quit 被调
- MINIMIZE_TO_TRAY 选择：event.ignore + _minimize_to_tray 被调，不退出
- CANCEL 选择：仅 event.ignore，不最小化、不退出
- _force_quit 已置位：直接 accept 退出，不弹确认框
- _close_dialog_showing 置位：重入关闭直接 ignore，不再弹窗

主窗口经 mock 构建（SkillsPanel/WorkArea/PluginManager/DataProvider/
TrayIconManager 均替换为 Mock，不加载真实插件、不创建真实托盘图标），
写法参照 test/ui_tests/test_system_tray.py；event 使用真实 QCloseEvent
实例，以 isAccepted() 状态断言 accept / ignore 的真实效果。
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

from ui.dialog.close_confirm_dialog import CloseChoice


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """确保 QApplication 存在：构建 QWidget 与 QCloseEvent 分发的前提。"""
    return qapp


def _make_window(mocker, qtbot):
    """构建重依赖全 Mock 的主窗口（不加载真实插件、不创建真实托盘）。

    Returns:
        InstructionXMainWindow 实例（_tray_manager 为 MagicMock，
        _force_quit / _close_dialog_showing 均为初始 False）
    """
    mocker.patch("ui.main_window.SkillsPanel")
    mocker.patch("ui.main_window.WorkArea")
    mocker.patch("ui.main_window.DataProvider")
    mocker.patch("ui.main_window.PluginManager")
    mocker.patch("ui.main_window.TrayIconManager")

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, "_load_saved_theme"):
        with patch.object(InstructionXMainWindow, "_create_menus"):
            with patch.object(InstructionXMainWindow, "_create_main_layout"):
                window = InstructionXMainWindow()
    qtbot.addWidget(window)
    return window


class TestCloseEventDispatch:
    """closeEvent：三种 CloseChoice 分发、_force_quit 直放、防重入"""

    def test_initial_close_state_defaults(self, mocker, qtbot):
        """新建主窗口的关闭编排状态均为初始值（不直放、无防重入）"""
        window = _make_window(mocker, qtbot)

        assert window._force_quit is False
        assert window._close_dialog_showing is False

    def test_exit_choice_accepts_and_quits(self, mocker, qtbot, monkeypatch):
        """EXIT：_force_quit 置位 + event.accept + QApplication.quit 被调"""
        window = _make_window(mocker, qtbot)
        monkeypatch.setattr(
            window, "_ask_close_choice", lambda: CloseChoice.EXIT
        )
        quit_spy = MagicMock()
        monkeypatch.setattr(QApplication, "quit", quit_spy)
        # 预置 ignore，确保 accept 断言能真实反映状态翻转而非默认值
        event = QCloseEvent()
        event.ignore()

        window.closeEvent(event)

        assert event.isAccepted() is True
        assert window._force_quit is True
        quit_spy.assert_called_once()

    def test_minimize_choice_ignores_and_minimizes_to_tray(
        self, mocker, qtbot, monkeypatch
    ):
        """MINIMIZE_TO_TRAY：event.ignore + 调 _minimize_to_tray，不退出"""
        window = _make_window(mocker, qtbot)
        monkeypatch.setattr(
            window, "_ask_close_choice", lambda: CloseChoice.MINIMIZE_TO_TRAY
        )
        minimize_spy = MagicMock()
        monkeypatch.setattr(window, "_minimize_to_tray", minimize_spy)
        quit_spy = MagicMock()
        monkeypatch.setattr(QApplication, "quit", quit_spy)
        # 真实 QCloseEvent 默认 accepted，ignore 后应翻转为未接受
        event = QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted() is False
        minimize_spy.assert_called_once()
        assert window._force_quit is False
        quit_spy.assert_not_called()

    def test_cancel_choice_ignores_only(self, mocker, qtbot, monkeypatch):
        """CANCEL：仅 event.ignore，不最小化、不退出"""
        window = _make_window(mocker, qtbot)
        monkeypatch.setattr(
            window, "_ask_close_choice", lambda: CloseChoice.CANCEL
        )
        minimize_spy = MagicMock()
        monkeypatch.setattr(window, "_minimize_to_tray", minimize_spy)
        quit_spy = MagicMock()
        monkeypatch.setattr(QApplication, "quit", quit_spy)
        event = QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted() is False
        minimize_spy.assert_not_called()
        assert window._force_quit is False
        quit_spy.assert_not_called()

    def test_force_quit_skips_dialog_and_accepts(
        self, mocker, qtbot, monkeypatch
    ):
        """_force_quit 已置位：直接 accept 退出，不弹确认框"""
        window = _make_window(mocker, qtbot)
        window._force_quit = True
        ask_spy = MagicMock()
        monkeypatch.setattr(window, "_ask_close_choice", ask_spy)
        quit_spy = MagicMock()
        monkeypatch.setattr(QApplication, "quit", quit_spy)
        event = QCloseEvent()
        event.ignore()

        window.closeEvent(event)

        assert event.isAccepted() is True
        ask_spy.assert_not_called()
        quit_spy.assert_called_once()

    def test_reentry_while_dialog_showing_is_ignored(
        self, mocker, qtbot, monkeypatch
    ):
        """_close_dialog_showing 置位：重入关闭直接 ignore，不再弹窗、不最小化"""
        window = _make_window(mocker, qtbot)
        window._close_dialog_showing = True
        ask_spy = MagicMock()
        monkeypatch.setattr(window, "_ask_close_choice", ask_spy)
        minimize_spy = MagicMock()
        monkeypatch.setattr(window, "_minimize_to_tray", minimize_spy)
        quit_spy = MagicMock()
        monkeypatch.setattr(QApplication, "quit", quit_spy)
        event = QCloseEvent()

        window.closeEvent(event)

        assert event.isAccepted() is False
        ask_spy.assert_not_called()
        minimize_spy.assert_not_called()
        quit_spy.assert_not_called()
        # 防重入路径不得清除守卫（守卫由弹窗方在 finally 中复位）
        assert window._close_dialog_showing is True
