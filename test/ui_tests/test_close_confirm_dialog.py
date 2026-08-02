"""关闭确认对话框测试（ui/dialog/close_confirm_dialog.py）

覆盖：
- 三按钮点击分别返回对应的三值枚举（EXIT / MINIMIZE_TO_TRAY / CANCEL）
- Esc 键与直接 reject() 均归一为 CANCEL（含初始默认值边界、
  accept 后再 reject 复位的边界）
- ask() 类方法语义：monkeypatch QDialog.exec 避免模态阻塞，
  配合 QTimer.singleShot 在嵌套事件循环中触发按钮

仅实例化 CloseConfirmDialog 本身，不构建主窗口、不加载插件、
不创建托盘图标，无需额外的重依赖 Mock。
"""

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import QEventLoop, Qt, QTimer
from PySide6.QtWidgets import QDialog, QPushButton

from ui.dialog.close_confirm_dialog import (
    BUTTON_CANCEL_TEXT, BUTTON_EXIT_TEXT, BUTTON_MINIMIZE_TEXT,
    CloseChoice, CloseConfirmDialog,
)

# 嵌套事件循环等待上限（毫秒），防止 fake_exec 在异常情况下死等
EXEC_LOOP_TIMEOUT_MS = 3000


def _click_button(dialog: CloseConfirmDialog, text: str) -> None:
    """按文本查找对话框按钮并触发点击；找不到即断言失败。

    Args:
        dialog: 目标对话框
        text: 按钮文案
    """
    for button in dialog.findChildren(QPushButton):
        if button.text() == text:
            button.click()
            return
    pytest.fail(f"按钮不存在: {text}")


def _fake_exec_with_action(self: QDialog, action) -> int:
    """模拟模态 exec：用 QTimer.singleShot 在嵌套事件循环中执行动作。

    动作（按钮点击 / reject）在定时器回调中触发，对话框 done 后
    finished 信号退出嵌套循环，返回对话框 result。带超时兜底，
    动作未生效时超时退出而非挂死测试。

    Args:
        self: 被 monkeypatch 的对话框实例
        action: 无参回调，通常为触发某个按钮点击

    Returns:
        对话框的 result 码
    """
    loop = QEventLoop(self)
    self.finished.connect(loop.quit)
    QTimer.singleShot(0, action)
    QTimer.singleShot(EXEC_LOOP_TIMEOUT_MS, loop.quit)
    loop.exec()
    return self.result()


class TestButtonChoices:
    """三按钮点击分别返回对应的三值枚举"""

    def test_exit_button_returns_exit(self, qtbot):
        """点击「退出程序」返回 EXIT"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        _click_button(dialog, BUTTON_EXIT_TEXT)
        assert dialog.selected_choice() is CloseChoice.EXIT

    def test_minimize_button_returns_minimize_to_tray(self, qtbot):
        """点击「最小化到托盘」返回 MINIMIZE_TO_TRAY"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        _click_button(dialog, BUTTON_MINIMIZE_TEXT)
        assert dialog.selected_choice() is CloseChoice.MINIMIZE_TO_TRAY

    def test_cancel_button_returns_cancel(self, qtbot):
        """点击「取消」返回 CANCEL"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        _click_button(dialog, BUTTON_CANCEL_TEXT)
        assert dialog.selected_choice() is CloseChoice.CANCEL


class TestRejectSemantics:
    """reject（Esc / 对话框叉号 / 取消按钮）语义统一归一为取消"""

    def test_initial_choice_is_cancel(self, qtbot):
        """未做任何选择时 selected_choice 默认为 CANCEL（边界）"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        assert dialog.selected_choice() is CloseChoice.CANCEL

    def test_esc_key_returns_cancel(self, qtbot):
        """对话框显示时按 Esc 键：返回 CANCEL 且对话框被关闭"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        dialog.show()
        assert dialog.isVisible() is True

        qtbot.keyClick(dialog, Qt.Key.Key_Escape)

        assert dialog.selected_choice() is CloseChoice.CANCEL
        assert dialog.isVisible() is False

    def test_reject_returns_cancel(self, qtbot):
        """直接调用 reject()（Esc/叉号同路径）返回 CANCEL"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        dialog.reject()
        assert dialog.selected_choice() is CloseChoice.CANCEL

    def test_reject_after_accept_resets_to_cancel(self, qtbot):
        """先点击「退出程序」再 reject：选择被复位为 CANCEL（边界）"""
        dialog = CloseConfirmDialog()
        qtbot.addWidget(dialog)
        _click_button(dialog, BUTTON_EXIT_TEXT)
        assert dialog.selected_choice() is CloseChoice.EXIT

        dialog.reject()
        assert dialog.selected_choice() is CloseChoice.CANCEL


class TestAskClassMethod:
    """ask() 类方法：模态弹出并返回用户选择

    monkeypatch QDialog.exec 避免真实模态阻塞，fake 实现内部经
    QTimer.singleShot 在嵌套事件循环中触发按钮，行为与真实
    模态路径一致（按钮点击 → done → finished → exec 返回）。
    """

    def test_ask_returns_exit(self, qtbot, monkeypatch):
        """exec 期间点击「退出程序」时 ask() 返回 EXIT"""
        def fake_exec(self):
            return _fake_exec_with_action(
                self, lambda: _click_button(self, BUTTON_EXIT_TEXT)
            )

        monkeypatch.setattr(QDialog, "exec", fake_exec)
        assert CloseConfirmDialog.ask() is CloseChoice.EXIT

    def test_ask_returns_minimize_to_tray(self, qtbot, monkeypatch):
        """exec 期间点击「最小化到托盘」时 ask() 返回 MINIMIZE_TO_TRAY"""
        def fake_exec(self):
            return _fake_exec_with_action(
                self, lambda: _click_button(self, BUTTON_MINIMIZE_TEXT)
            )

        monkeypatch.setattr(QDialog, "exec", fake_exec)
        assert CloseConfirmDialog.ask() is CloseChoice.MINIMIZE_TO_TRAY

    def test_ask_rejected_returns_cancel(self, qtbot, monkeypatch):
        """exec 期间走 reject（等价 Esc/叉号/取消按钮）时 ask() 返回 CANCEL"""
        def fake_exec(self):
            return _fake_exec_with_action(self, self.reject)

        monkeypatch.setattr(QDialog, "exec", fake_exec)
        assert CloseConfirmDialog.ask() is CloseChoice.CANCEL
