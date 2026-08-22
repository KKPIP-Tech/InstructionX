"""关闭确认对话框

点击主窗口关闭按钮（叉子 / Alt+F4 / 任务栏右键关闭）时弹出，
每次必问（不提供「记住我的选择」），三按钮：
退出程序（primary）/ 最小化到托盘 / 取消。

用法::

    choice = CloseConfirmDialog.ask(main_window)
    # choice 为 CloseChoice 三值枚举；Esc / 对话框叉号等价于 CANCEL
"""

from enum import Enum
from typing import Optional

# ===================================================================
# PySide 相关
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

# ===================================================================
# 本地
from core.i18n import tr
from InstructionX_UIKit import set_property

# 对话框文案均经 i18n 子系统取词（分组 dialog_close_confirm），
# 在使用处调用 tr()，不做模块级固化，保证语言切换后新建实例即为新语言

# ===================================================================
# 布局常量
DIALOG_MIN_WIDTH = 420
CONTENT_MARGIN = 24
CONTENT_SPACING = 20
BUTTON_SPACING = 12


class CloseChoice(Enum):
    """关闭确认对话框的用户选择（三值枚举）"""
    EXIT = "exit"                       # 退出程序
    MINIMIZE_TO_TRAY = "minimize_to_tray"  # 最小化到系统托盘
    CANCEL = "cancel"                   # 取消关闭


class CloseConfirmDialog(QDialog):
    """关闭确认对话框：退出程序 / 最小化到托盘 / 取消。

    模态（WindowModal，父窗口为主窗口）；Esc 与对话框叉号等价于「取消」。
    样式令牌取自 UIKit 全局主题（按钮 variant 由全局 QSS 驱动，
    随主题自动切换）。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """初始化对话框。

        Args:
            parent: 父窗口（通常为主窗口）
        """
        super().__init__(parent)
        self._choice = CloseChoice.CANCEL
        self.setWindowTitle(tr("dialog_close_confirm", "title"))
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumWidth(DIALOG_MIN_WIDTH)
        self._init_ui()

    def _init_ui(self) -> None:
        """构建说明文案与三按钮布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN
        )
        layout.setSpacing(CONTENT_SPACING)

        message_label = QLabel(tr("dialog_close_confirm", "message"))
        message_label.setWordWrap(True)
        layout.addWidget(message_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(BUTTON_SPACING)
        button_layout.addStretch()

        exit_button = QPushButton(tr("dialog_close_confirm", "button.exit"))
        set_property(exit_button, "variant", "primary")
        exit_button.setDefault(True)
        exit_button.clicked.connect(self._on_exit_clicked)
        button_layout.addWidget(exit_button)

        minimize_button = QPushButton(tr("dialog_close_confirm", "button.minimize_to_tray"))
        minimize_button.clicked.connect(self._on_minimize_clicked)
        button_layout.addWidget(minimize_button)

        cancel_button = QPushButton(tr("common", "cancel"))
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

    # ===============================================================
    # 对外 API
    def selected_choice(self) -> CloseChoice:
        """返回用户在对话框中的选择。

        Returns:
            三值枚举；对话框被 reject（Esc / 叉号 / 取消按钮）时为 CANCEL
        """
        return self._choice

    @classmethod
    def ask(cls, parent: Optional[QWidget] = None) -> CloseChoice:
        """模态弹出对话框并返回用户选择（一站式便捷接口）。

        Args:
            parent: 父窗口（通常为主窗口）

        Returns:
            用户选择的三值枚举；Esc / 叉号等价于 CANCEL
        """
        dialog = cls(parent)
        dialog.exec()
        choice = dialog.selected_choice()
        # exec 返回后对话框不会自动销毁，显式释放其 C++ 对象树
        dialog.deleteLater()
        return choice

    # ===============================================================
    # 内部处理
    def reject(self) -> None:
        """Esc / 对话框叉号 / 取消按钮统一走 reject，语义为「取消」。"""
        self._choice = CloseChoice.CANCEL
        super().reject()

    def _on_exit_clicked(self) -> None:
        """「退出程序」按钮：记录选择并关闭对话框。"""
        self._choice = CloseChoice.EXIT
        self.accept()

    def _on_minimize_clicked(self) -> None:
        """「最小化到托盘」按钮：记录选择并关闭对话框。"""
        self._choice = CloseChoice.MINIMIZE_TO_TRAY
        self.accept()
