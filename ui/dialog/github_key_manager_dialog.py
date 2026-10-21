"""GitHub Key 列表、验证和删除管理对话框。"""

from typing import Optional

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from InstructionX_UIKit.components import Button, Dialog, Message, Table
from core.github import GitHubKeyManager, GitHubKeyView
from core.i18n import tr
from core.plugin.plugin_registry import PluginRegistry

from .github_key_editor_dialog import GitHubKeyEditorDialog

_TR_GROUP = "github_key_manager"
_KEY_ID_ROLE = Qt.ItemDataRole.UserRole
_KIND_KEYS = {
    "fine_grained": "kind.fine_grained",
    "classic": "kind.classic",
    "unknown": "kind.unknown",
}
_STATUS_KEYS = {
    "untested": "status.untested",
    "valid": "status.valid",
    "invalid": "status.invalid",
}


class _VerifyKeyWorker(QThread):
    """后台验证 Key。"""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, manager: GitHubKeyManager, key_id: str, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._key_id = key_id

    def run(self) -> None:
        """验证并返回结果。"""
        try:
            self.succeeded.emit(self._manager.verify_key(self._key_id))
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubKeyManagerDialog(QDialog):
    """管理多个 GitHub PAT。"""

    def __init__(
        self,
        key_manager: GitHubKeyManager,
        plugin_registry: Optional[PluginRegistry] = None,
        parent=None,
    ):
        """初始化 Key 管理器。"""
        super().__init__(parent)
        self._manager = key_manager
        self._registry = plugin_registry
        self._worker: Optional[_VerifyKeyWorker] = None
        self.setWindowTitle(tr(_TR_GROUP, "title"))
        self.setMinimumSize(860, 480)
        self._init_ui()
        self._reload()

    def _init_ui(self) -> None:
        """构建表格、操作栏和关闭按钮。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        self._table = Table(sortable=False)
        self._table.set_empty_text(tr(_TR_GROUP, "table.empty"))
        self._table.itemSelectionChanged.connect(self._update_actions)
        layout.addWidget(self._table, 1)
        layout.addLayout(self._build_actions())
        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = Button(tr("common", "close"), variant="primary")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def _build_actions(self) -> QHBoxLayout:
        """构建 Key 操作按钮。"""
        actions = QHBoxLayout()
        self._add_btn = Button(tr(_TR_GROUP, "button.add"), variant="primary")
        self._edit_btn = Button(tr(_TR_GROUP, "button.edit"))
        self._verify_btn = Button(tr(_TR_GROUP, "button.verify"))
        self._default_btn = Button(tr(_TR_GROUP, "button.set_default"))
        self._delete_btn = Button(tr(_TR_GROUP, "button.delete"), variant="danger")
        handlers = (
            (self._add_btn, self._on_add),
            (self._edit_btn, self._on_edit),
            (self._verify_btn, self._on_verify),
            (self._default_btn, self._on_set_default),
            (self._delete_btn, self._on_delete),
        )
        for button, handler in handlers:
            button.clicked.connect(handler)
            actions.addWidget(button)
        actions.addStretch()
        self._update_actions()
        return actions

    def _reload(self) -> None:
        """重建 Key 表格。"""
        views = self._manager.list_keys()
        rows = [self._row(view) for view in views]
        self._table.set_data([
            tr(_TR_GROUP, "column.name"),
            tr(_TR_GROUP, "column.account"),
            tr(_TR_GROUP, "column.kind"),
            tr(_TR_GROUP, "column.status"),
            tr(_TR_GROUP, "column.expires"),
            tr(_TR_GROUP, "column.last_verified"),
            tr(_TR_GROUP, "column.default"),
        ], rows)
        for row, view in enumerate(views):
            self._table.item(row, 0).setData(_KEY_ID_ROLE, view.id)
        self._update_actions()

    def _row(self, view: GitHubKeyView) -> list[str]:
        """构造单行展示值。"""
        expires = view.expires_at or tr(_TR_GROUP, "expires.unavailable")
        return [
            view.name,
            view.account_login or tr(_TR_GROUP, "account.unknown"),
            tr(_TR_GROUP, _KIND_KEYS.get(
                view.token_kind.value, "kind.unknown")),
            tr(_TR_GROUP, _STATUS_KEYS.get(
                view.status.value, "status.untested")),
            expires,
            view.last_verified_at or tr(_TR_GROUP, "never_verified"),
            tr(_TR_GROUP, "yes") if view.is_default else "",
        ]

    def _selected_view(self) -> Optional[GitHubKeyView]:
        """返回当前选中 Key。"""
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        key_id = item.data(_KEY_ID_ROLE) if item else ""
        if not key_id:
            return None
        return next(
            (view for view in self._manager.list_keys() if view.id == key_id),
            None,
        )

    def _update_actions(self) -> None:
        """按选中状态切换按钮。"""
        view = self._selected_view()
        mutable = view is not None and not view.is_environment
        for button in (
            self._edit_btn,
            self._delete_btn,
            self._default_btn,
        ):
            button.setEnabled(mutable)
        self._verify_btn.setEnabled(view is not None)

    def _on_add(self) -> None:
        """添加 Key。"""
        dialog = GitHubKeyEditorDialog(self._manager, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_edit(self) -> None:
        """编辑选中 Key。"""
        view = self._selected_view()
        if view is None:
            return
        dialog = GitHubKeyEditorDialog(self._manager, view, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_verify(self) -> None:
        """后台验证选中 Key。"""
        view = self._selected_view()
        if view is None or (self._worker and self._worker.isRunning()):
            return
        self._set_busy(True)
        self._worker = _VerifyKeyWorker(self._manager, view.id, self)
        self._worker.succeeded.connect(self._on_verify_finished)
        self._worker.failed.connect(self._on_verify_failed)
        self._worker.start()

    def _on_verify_finished(self, result) -> None:
        """刷新验证结果。"""
        self._worker = None
        self._set_busy(False)
        self._reload()
        if result.success:
            Message.success(self, tr(_TR_GROUP, "message.verify_success"))
        else:
            Message.warning(
                self,
                tr(_TR_GROUP, "message.verify_failed",
                   error=result.error_message),
            )

    def _on_verify_failed(self, message: str) -> None:
        """展示后台验证异常。"""
        self._worker = None
        self._set_busy(False)
        Message.error(self, message)

    def _on_set_default(self) -> None:
        """设置选中 Key 为默认。"""
        view = self._selected_view()
        if view is None:
            return
        self._manager.set_default_key(view.id)
        self._reload()

    def _on_delete(self) -> None:
        """确认并删除选中 Key。"""
        view = self._selected_view()
        if view is None or not self._confirm_delete(view):
            return
        self._manager.delete_key(view.id)
        self._reload()

    def _confirm_delete(self, view: GitHubKeyView) -> bool:
        """显示删除影响并确认。"""
        affected = self._affected_plugins(view.id)
        text = tr(
            _TR_GROUP, "message.delete_confirm",
            name=view.name, count=len(affected))
        if affected:
            text += "\n" + tr(
                _TR_GROUP, "message.delete_affected",
                names=", ".join(affected),
            )
        dialog = Dialog(self, title=tr(_TR_GROUP, "title.delete"))
        dialog.set_text(text)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def _affected_plugins(self, key_id: str) -> list[str]:
        """返回绑定 Key 的插件名称。"""
        if self._registry is None:
            return []
        return [
            record.get("name", plugin_id)
            for plugin_id, record in self._registry.find_by_source_key(key_id)
        ]

    def _set_busy(self, busy: bool) -> None:
        """切换按钮忙碌状态。"""
        for button in (
            self._add_btn,
            self._edit_btn,
            self._verify_btn,
            self._delete_btn,
            self._default_btn,
        ):
            button.setEnabled(not busy)
        self._status.setText(
            tr(_TR_GROUP, "status.verifying") if busy else "")

    def closeEvent(self, event) -> None:
        """后台验证期间拒绝关闭。"""
        if self._worker and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
