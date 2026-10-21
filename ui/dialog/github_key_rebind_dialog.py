"""失效插件来源 Key 的重新绑定对话框。"""

from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QVBoxLayout

from InstructionX_UIKit import T
from InstructionX_UIKit.components import Button, ComboBox
from core.github import (
    GitHubKeyManager,
    PluginSourceKeyBinder,
    PluginSourceKeyResolution,
)
from core.i18n import tr

from .github_key_manager_dialog import GitHubKeyManagerDialog

_TR_GROUP = "github_key_rebind"


class _RebindWorker(QThread):
    """后台验证并重新绑定 Key。"""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, binder, plugin_id: str, key_id: str, parent=None):
        super().__init__(parent)
        self._binder = binder
        self._plugin_id = plugin_id
        self._key_id = key_id

    def run(self) -> None:
        """执行重新绑定。"""
        try:
            self.succeeded.emit(
                self._binder.rebind(self._plugin_id, self._key_id))
        except Exception as exc:
            self.failed.emit(str(exc))


class GitHubKeyRebindDialog(QDialog):
    """选择并验证新的 GitHub Key。"""

    def __init__(
        self,
        binder: PluginSourceKeyBinder,
        key_manager: GitHubKeyManager,
        plugin_id: str,
        resolution: Optional[PluginSourceKeyResolution] = None,
        parent=None,
    ):
        """初始化重新绑定对话框。"""
        super().__init__(parent)
        self._binder = binder
        self._manager = key_manager
        self._plugin_id = plugin_id
        self._resolution = resolution
        self._worker: Optional[_RebindWorker] = None
        self.result_resolution: Optional[PluginSourceKeyResolution] = None
        self.setWindowTitle(tr(_TR_GROUP, "title"))
        self.setMinimumWidth(520)
        self._init_ui()
        self._reload_keys()

    def _init_ui(self) -> None:
        """构建说明、下拉框和按钮。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        self._message = QLabel(self._initial_message())
        self._message.setWordWrap(True)
        layout.addWidget(self._message)
        self._key_combo = ComboBox()
        layout.addWidget(self._key_combo)
        self._error = QLabel("")
        self._error.setWordWrap(True)
        layout.addWidget(self._error)
        actions = QHBoxLayout()
        manage_btn = Button(tr(_TR_GROUP, "button.manage"))
        manage_btn.clicked.connect(self._on_manage)
        self._confirm_btn = Button(
            tr(_TR_GROUP, "button.rebind"), variant="primary")
        self._confirm_btn.clicked.connect(self._on_rebind)
        cancel_btn = Button(tr("common", "cancel"))
        cancel_btn.clicked.connect(self.reject)
        actions.addWidget(manage_btn)
        actions.addStretch()
        actions.addWidget(cancel_btn)
        actions.addWidget(self._confirm_btn)
        layout.addLayout(actions)

    def _initial_message(self) -> str:
        """返回当前 Key 不可用说明。"""
        if self._resolution and self._resolution.error_message:
            return tr(
                _TR_GROUP, "message.unavailable",
                error=self._resolution.error_message)
        return tr(_TR_GROUP, "message.select_key")

    def _reload_keys(self) -> None:
        """加载所有可用 Key。"""
        self._key_combo.clear()
        for view in self._manager.list_keys():
            if view.is_environment:
                continue
            label = tr(
                _TR_GROUP, "key.label",
                name=view.name,
                account=view.account_login or tr(_TR_GROUP, "unknown_account"),
            )
            self._key_combo.addItem(label, view.id)
        self._confirm_btn.setEnabled(self._key_combo.count() > 0)

    def _on_manage(self) -> None:
        """打开 Key 管理器并刷新。"""
        dialog = GitHubKeyManagerDialog(self._manager, parent=self)
        dialog.exec()
        self._reload_keys()

    def _on_rebind(self) -> None:
        """验证选中 Key 并重新绑定。"""
        key_id = self._key_combo.currentData()
        if not key_id or (self._worker and self._worker.isRunning()):
            return
        self._set_busy(True)
        self._worker = _RebindWorker(
            self._binder, self._plugin_id, key_id, self)
        self._worker.succeeded.connect(self._on_rebind_finished)
        self._worker.failed.connect(self._on_rebind_failed)
        self._worker.start()

    def _on_rebind_finished(self, resolution) -> None:
        """重新绑定成功则关闭对话框。"""
        self._worker = None
        self._set_busy(False)
        if not resolution.available:
            self._show_error(resolution.error_message)
            return
        self.result_resolution = resolution
        self.accept()

    def _on_rebind_failed(self, message: str) -> None:
        """展示未预期异常。"""
        self._worker = None
        self._set_busy(False)
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        """显示验证失败。"""
        self._error.setText(message)
        self._error.setStyleSheet(f"color: {T('color.danger')};")

    def _set_busy(self, busy: bool) -> None:
        """切换忙碌状态。"""
        self._confirm_btn.setEnabled(not busy and self._key_combo.count() > 0)
        self._key_combo.setEnabled(not busy)

    def closeEvent(self, event) -> None:
        """后台验证期间拒绝关闭。"""
        if self._worker and self._worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
