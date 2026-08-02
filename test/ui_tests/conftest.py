"""UI 测试目录级配置

提供本目录共用的自动化兜底 fixture：
- _auto_dismiss_close_confirm：防止任何测试路径弹出真实模态「关闭确认」对话框
"""

import pytest

pytest.importorskip("pytestqt")


@pytest.fixture(autouse=True)
def _auto_dismiss_close_confirm(monkeypatch):
    """兜底：主窗口的任何关闭触发都自动按「取消」处理，绝不弹真实模态确认框。

    背景：pytest-qt 会在测试收尾时对 qtbot.addWidget 登记的 widget 无条件
    调用 close()（qtbot.py 的 _close_widgets），而主窗口 closeEvent 的默认
    路径是弹出模态 CloseConfirmDialog 并 exec()——若不经拦截，收尾 close()
    会打开真实对话框阻塞等待人工点击，CI（GitHub Actions）上将永久挂起。

    本 fixture 在类级别将 _ask_close_choice 替换为直接返回 CANCEL：
    - 收尾自动 close() → closeEvent → 返回 CANCEL → event.ignore()，立即返回；
    - 专项分发测试（test_close_event_dispatch.py）用 monkeypatch.setattr(
      window, "_ask_close_choice", ...) 设置的是实例属性，优先于类属性，
      其断言不受本兜底影响。
    """
    from ui.dialog.close_confirm_dialog import CloseChoice
    from ui.main_window import InstructionXMainWindow

    monkeypatch.setattr(
        InstructionXMainWindow,
        "_ask_close_choice",
        lambda self: CloseChoice.CANCEL,
    )
