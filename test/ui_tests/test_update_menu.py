"""帮助菜单手动检查更新入口测试。"""

from unittest.mock import MagicMock, patch


def _window(qtbot):
    """创建不加载插件、不构造真实工作区的主窗口。"""
    from ui.main_window import InstructionXMainWindow

    with patch.object(InstructionXMainWindow, "_load_saved_theme"), \
            patch.object(InstructionXMainWindow, "_create_main_layout"), \
            patch.object(InstructionXMainWindow, "_prewarm_blueprint_viewport"):
        window = InstructionXMainWindow()
    qtbot.addWidget(window)
    return window


class TestUpdateMenu:
    """验证只有用户点击帮助菜单后才创建检查对话框。"""

    def test_menu_click_opens_update_dialog(self, mocker, qtbot):
        """主窗口构造不得检查，点击菜单才创建并执行弹窗。"""
        dialog_class = mocker.patch("ui.main_window.UpdateDialog")
        dialog = dialog_class.return_value
        window = _window(qtbot)

        dialog_class.assert_not_called()
        assert window._action_check_update.text()

        window._action_check_update.trigger()

        dialog_class.assert_called_once_with(window)
        dialog.exec.assert_called_once_with()
        dialog.deleteLater.assert_called_once_with()

    def test_update_started_defers_application_quit(self, mocker, qtbot):
        """外部向导启动后才调度静默退出，避免重入弹窗。"""
        window = _window(qtbot)
        timer = mocker.patch("ui.main_window.QTimer.singleShot")

        window._on_update_started("alpha-v1.2.0")

        assert window._force_quit
        timer.assert_called_once_with(0, window._quit_application)
