"""GitHub Key 管理器、编辑器和重新绑定 UI 测试。"""

from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLineEdit

from core.github import (
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubTokenKind,
    MAX_GITHUB_KEY_NAME_LENGTH,
    MAX_GITHUB_TOKEN_LENGTH,
    PluginSourceKeyResolution,
)
from ui.dialog.github_key_editor_dialog import GitHubKeyEditorDialog
from ui.dialog.github_key_manager_dialog import GitHubKeyManagerDialog
from ui.dialog.github_key_rebind_dialog import GitHubKeyRebindDialog


def _view(
    key_id: str = "key-a",
    name: str = "工作账号",
    *,
    is_default: bool = False,
    is_environment: bool = False,
) -> GitHubKeyView:
    """构造 UI 测试 Key 数据。"""
    return GitHubKeyView(
        id=key_id,
        name=name,
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=GitHubKeyStatus.VALID,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="2026-10-21",
        last_error_code="",
        last_error_message="",
        is_default=is_default,
        is_environment=is_environment,
    )


class TestKeyManagerDialog:
    """验证 Key 列表、权限和环境变量只读状态。"""

    def test_lists_multiple_named_keys(self, qtbot):
        """表格应按 Key 列表显示多行。"""
        manager = MagicMock()
        manager.list_keys.return_value = [
            _view("key-a", "工作账号", is_default=True),
            _view("key-b", "个人账号"),
        ]
        dialog = GitHubKeyManagerDialog(manager)
        qtbot.addWidget(dialog)

        assert dialog._table.rowCount() == 2
        assert dialog._table.item(0, 0).text() == "工作账号"
        assert dialog._table.item(0, 6).text()

    def test_environment_key_is_read_only(self, qtbot):
        """环境变量 Key 不得编辑或删除。"""
        manager = MagicMock()
        manager.list_keys.return_value = [
            _view("environment:github-token", "环境变量 GitHub Token",
                  is_environment=True),
        ]
        dialog = GitHubKeyManagerDialog(manager)
        qtbot.addWidget(dialog)
        dialog._table.selectRow(0)

        assert dialog._edit_btn.isEnabled() is False
        assert dialog._delete_btn.isEnabled() is False
        assert dialog._verify_btn.isEnabled() is True

    def test_delete_shows_affected_plugins_and_deletes(
        self, qtbot, mocker
    ):
        """删除确认后调用管理器删除。"""
        manager = MagicMock()
        manager.list_keys.return_value = [_view()]
        registry = MagicMock()
        registry.find_by_source_key.return_value = [
            ("uuid", {"name": "私有插件"}),
        ]
        dialog = GitHubKeyManagerDialog(manager, registry)
        qtbot.addWidget(dialog)
        dialog._table.selectRow(0)
        assert dialog._affected_plugins("key-a") == ["私有插件"]
        mocker.patch.object(dialog, "_confirm_delete", return_value=True)

        dialog._on_delete()

        manager.delete_key.assert_called_once_with("key-a")

    def test_set_default_updates_manager(self, qtbot):
        """按钮应设置选中 Key 为默认。"""
        manager = MagicMock()
        manager.list_keys.return_value = [_view()]
        dialog = GitHubKeyManagerDialog(manager)
        qtbot.addWidget(dialog)
        dialog._table.selectRow(0)

        dialog._on_set_default()

        manager.set_default_key.assert_called_once_with("key-a")


class TestKeyEditorDialog:
    """验证名称、Token 与后台保存交互。"""

    def test_token_uses_password_mode(self, qtbot):
        """Token 输入默认应为密码显示。"""
        dialog = GitHubKeyEditorDialog(MagicMock())
        qtbot.addWidget(dialog)

        assert dialog._token_input.echoMode() == QLineEdit.EchoMode.Password
        assert dialog._name_input.maxLength() == MAX_GITHUB_KEY_NAME_LENGTH
        assert dialog._token_input.maxLength() == MAX_GITHUB_TOKEN_LENGTH

    def test_name_is_required(self, qtbot):
        """空名称应在本地拒绝。"""
        dialog = GitHubKeyEditorDialog(MagicMock())
        qtbot.addWidget(dialog)

        dialog._on_save()

        assert "名称" in dialog._status.text()

    def test_add_validates_and_closes(self, qtbot):
        """有效输入应后台添加并记录结果。"""
        manager = MagicMock()
        manager.add_key.return_value = _view()
        dialog = GitHubKeyEditorDialog(manager)
        qtbot.addWidget(dialog)
        dialog._name_input.setText("工作账号")
        dialog._token_input.setText("github_pat_test")

        dialog._on_save()
        qtbot.waitUntil(lambda: dialog.result_view is not None, timeout=2000)

        assert dialog.result_view.id == "key-a"
        manager.add_key.assert_called_once_with(
            "工作账号", "github_pat_test")

    def test_edit_can_keep_existing_token(self, qtbot):
        """编辑模式 Token 留空应只重命名。"""
        manager = MagicMock()
        manager.rename_key.return_value = _view(name="新名称")
        dialog = GitHubKeyEditorDialog(manager, _view())
        qtbot.addWidget(dialog)
        dialog._name_input.setText("新名称")

        dialog._on_save()
        qtbot.waitUntil(lambda: dialog.result_view is not None, timeout=2000)

        manager.rename_key.assert_called_once_with("key-a", "新名称")
        manager.replace_token.assert_not_called()


class TestKeyRebindDialog:
    """验证重新绑定对话框选择与结果。"""

    def test_lists_configured_keys(self, qtbot):
        """下拉框应列出非环境变量 Key。"""
        manager = MagicMock()
        manager.list_keys.return_value = [
            _view("key-a", "工作账号"),
            _view("environment:github-token", "环境变量", is_environment=True),
        ]
        dialog = GitHubKeyRebindDialog(
            MagicMock(), manager, "plugin-uuid")
        qtbot.addWidget(dialog)

        assert dialog._key_combo.count() == 1
        assert dialog._key_combo.currentData() == "key-a"

    def test_successful_rebind_accepts(self, qtbot):
        """新 Key 验证成功后对话框接受。"""
        manager = MagicMock()
        manager.list_keys.return_value = [_view("key-b", "备用账号")]
        binder = MagicMock()
        binder.rebind.return_value = PluginSourceKeyResolution(
            plugin_id="plugin-uuid",
            available=True,
            visibility="private",
            key_id="key-b",
        )
        dialog = GitHubKeyRebindDialog(
            binder, manager, "plugin-uuid")
        qtbot.addWidget(dialog)

        dialog._on_rebind()
        qtbot.waitUntil(
            lambda: dialog.result_resolution is not None,
            timeout=2000,
        )

        assert dialog.result_resolution.key_id == "key-b"
        assert dialog.result() == dialog.DialogCode.Accepted
