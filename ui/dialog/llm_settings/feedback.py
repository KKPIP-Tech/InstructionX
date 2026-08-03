# ui/dialog/llm_settings/feedback.py
"""llm_settings 包内统一的用户反馈入口（基于 InstructionX_UIKit 组件）。

- :func:`confirm`：阻塞式确认对话框（替代 QMessageBox.question）；
- :func:`notice`：阻塞式结果告知对话框（替代 QMessageBox.information/warning
  的结果汇报场景）；
- :func:`info` / :func:`warn` / :func:`success`：非阻塞轻提示
  （替代校验失败、操作完成等轻量提示）。
"""

from PySide6.QtWidgets import QDialog

from InstructionX_UIKit.components import Dialog, Message


def confirm(parent, title: str, text: str) -> bool:
    """阻塞式确认对话框，用户点「确定」返回 True"""
    dialog = Dialog(parent, title=title)
    dialog.set_text(text)
    return dialog.exec() == QDialog.DialogCode.Accepted


def notice(parent, title: str, text: str) -> None:
    """阻塞式结果告知对话框（仅「知道了」按钮）"""
    dialog = Dialog(parent, title=title, ok_text="知道了", show_cancel=False)
    dialog.set_text(text)
    dialog.exec()


def info(parent, text: str) -> None:
    """非阻塞信息轻提示（顶部居中，自动消失）"""
    Message.info(parent, text)


def warn(parent, text: str) -> None:
    """非阻塞警告轻提示（顶部居中，自动消失）"""
    Message.warning(parent, text)


def success(parent, text: str) -> None:
    """非阻塞成功轻提示（顶部居中，自动消失）"""
    Message.success(parent, text)
