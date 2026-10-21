"""GitHub Key 添加与编辑对话框。"""

from typing import Callable, Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from InstructionX_UIKit import T
from InstructionX_UIKit.components import Button, LineEdit
from core.github import (
    MAX_GITHUB_KEY_NAME_LENGTH,
    MAX_GITHUB_TOKEN_LENGTH,
    GitHubKeyManager,
    GitHubKeyView,
)
from core.i18n import tr

_TR_GROUP = "github_key_editor"


class _KeyMutationWorker(QThread):
    """在后台验证并保存 Key。"""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable, parent=None):
        """保存待执行操作。"""
        super().__init__(parent)
        self._operation = operation

    def run(self) -> None:
        """执行操作并发出结果。"""
        try:
            self.succeeded.emit(self._operation())
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubKeyEditorDialog(QDialog):
    """添加或编辑单个 GitHub Key。"""

    def __init__(
        self,
        key_manager: GitHubKeyManager,
        key_view: Optional[GitHubKeyView] = None,
        parent=None,
    ):
        """初始化编辑对话框。

        Args:
            key_manager: GitHub Key 管理器。
            key_view: 编辑时传入现有 Key；添加时为空。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._manager = key_manager
        self._key_view = key_view
        self._worker: Optional[_KeyMutationWorker] = None
        self.result_view: Optional[GitHubKeyView] = None
        self.setWindowTitle(tr(
            _TR_GROUP, "title.edit" if key_view else "title.add"))
        self.setMinimumWidth(520)
        self._init_ui()

    def _init_ui(self) -> None:
        """构建表单与按钮。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)
        self._name_input = LineEdit(placeholder=tr(_TR_GROUP, "name.placeholder"))
        self._name_input.setMaxLength(MAX_GITHUB_KEY_NAME_LENGTH)
        self._token_input = LineEdit(
            placeholder=tr(_TR_GROUP, "token.placeholder"),
            clearable=True,
        )
        self._token_input.setMaxLength(MAX_GITHUB_TOKEN_LENGTH)
        self._token_input.set_password_mode(True)
        layout.addWidget(QLabel(tr(_TR_GROUP, "name.label")))
        layout.addWidget(self._name_input)
        layout.addWidget(QLabel(tr(_TR_GROUP, "token.label")))
        layout.addWidget(self._token_input)
        self._hint = QLabel(tr(_TR_GROUP, "permissions.hint"))
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        layout.addLayout(self._build_buttons())
        self._load_existing()

    def _build_buttons(self) -> QHBoxLayout:
        """构建底部按钮。"""
        buttons = QHBoxLayout()
        buttons.addStretch()
        self._cancel_btn = Button(tr("common", "cancel"), variant="default")
        self._cancel_btn.clicked.connect(self.reject)
        self._save_btn = Button(tr(_TR_GROUP, "button.save"), variant="primary")
        self._save_btn.clicked.connect(self._on_save)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._save_btn)
        return buttons

    def _load_existing(self) -> None:
        """填充编辑模式数据。"""
        if self._key_view is None:
            return
        self._name_input.setText(self._key_view.name)
        self._token_input.setPlaceholderText(
            tr(_TR_GROUP, "token.keep_placeholder"))

    def _on_save(self) -> None:
        """校验输入并启动后台保存。"""
        if self._worker and self._worker.isRunning():
            return
        name = self._name_input.text().strip()
        token = self._token_input.text().strip()
        if not name:
            self._show_error(tr(_TR_GROUP, "error.name_required"))
            return
        if self._key_view is None and not token:
            self._show_error(tr(_TR_GROUP, "error.token_required"))
            return
        self._set_busy(True)
        operation = self._build_operation(name, token)
        self._worker = _KeyMutationWorker(operation, self)
        self._worker.succeeded.connect(self._on_saved)
        self._worker.failed.connect(self._on_save_failed)
        self._worker.start()

    def _build_operation(self, name: str, token: str) -> Callable:
        """按添加或编辑模式构造保存操作。"""
        if self._key_view is None:
            return lambda: self._manager.add_key(name, token)
        key_id = self._key_view.id
        if token:
            return lambda: self._replace_and_rename(key_id, name, token)
        return lambda: self._manager.rename_key(key_id, name)

    def _replace_and_rename(self, key_id: str, name: str, token: str):
        """替换 Token 后同步名称。"""
        self._manager.replace_token(key_id, token)
        return self._manager.rename_key(key_id, name)

    def _on_saved(self, view: GitHubKeyView) -> None:
        """保存成功并关闭对话框。"""
        self._worker = None
        self.result_view = view
        self.accept()

    def _on_save_failed(self, message: str) -> None:
        """展示后台保存失败。"""
        self._worker = None
        self._set_busy(False)
        self._show_error(message)

    def _set_busy(self, busy: bool) -> None:
        """切换忙碌状态。"""
        self._save_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(not busy)

    def _show_error(self, message: str) -> None:
        """在表单内显示错误。"""
        self._status.setText(message)
        self._status.setStyleSheet(f"color: {T('color.danger')};")

    def closeEvent(self, event) -> None:
        """后台保存期间拒绝关闭，避免销毁运行中的 QThread。"""
        if self._worker and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
