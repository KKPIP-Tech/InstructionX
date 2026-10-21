"""插件管理详情与更新入口的 GitHub 绑定 UI 测试。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from PySide6.QtWidgets import QLabel

from core.github import (
    GitHubExpirationSource,
    GitHubKeyNotFoundError,
    GitHubKeyStatus,
    GitHubKeyUnavailableReason,
    GitHubKeyView,
    GitHubTokenKind,
    PluginSourceKeyResolution,
)
from core.plugin.github_plugin_installer import ReleaseInfo
from ui.dialog.plugin_management_dialog import (
    PluginManagementDialog,
    VersionSelectDialog,
)


def _dialog_stub() -> SimpleNamespace:
    """构造仅含绑定显示依赖的对话框替身。"""
    return SimpleNamespace(
        detail_access=MagicMock(),
        detail_key=MagicMock(),
        rebind_btn=MagicMock(),
        _key_manager=MagicMock(),
    )


def _key_view() -> GitHubKeyView:
    """构造有效 Key 展示值。"""
    return GitHubKeyView(
        id="key-a",
        name="工作账号",
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=GitHubKeyStatus.VALID,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="",
        last_error_code="",
        last_error_message="",
    )


class TestPluginBindingDisplay:
    """验证详情面板的私有状态和 Key 名称。"""

    def test_private_plugin_shows_bound_key(self):
        """私有插件应显示访问权限和 Key 名称。"""
        dialog = _dialog_stub()
        dialog._key_manager.get_key_view.return_value = _key_view()
        record = {
            "source_type": "github",
            "source_visibility": "private",
            "source_key_id": "key-a",
        }

        PluginManagementDialog._update_github_binding_text(dialog, record)

        assert "私有仓库" in dialog.detail_access.setText.call_args.args[0]
        assert "工作账号" in dialog.detail_key.setText.call_args.args[0]
        dialog.rebind_btn.setEnabled.assert_called_with(True)

    def test_deleted_key_is_marked_unavailable(self):
        """绑定 Key 被删除后不得显示旧名称。"""
        dialog = _dialog_stub()
        dialog._key_manager.get_key_view.side_effect = GitHubKeyNotFoundError(
            "missing")

        name = PluginManagementDialog._bound_key_name(dialog, "missing-key")

        assert "不可用" in name or "删除" in name

    def test_non_github_plugin_disables_rebind(self):
        """本地插件不提供 GitHub Key 重绑入口。"""
        dialog = _dialog_stub()

        PluginManagementDialog._update_github_binding_text(dialog, {
            "source_type": "local_zip",
            "source_visibility": "unknown",
        })

        dialog.rebind_btn.setEnabled.assert_called_with(False)
        dialog.detail_access.setText.assert_called_with("")


class TestSourceResolutionContinuation:
    """验证失效 Key 后进入重绑并继续原检查操作。"""

    def test_unavailable_key_prompts_rebind_then_retries(self):
        """重新绑定成功后自动重新执行检查更新。"""
        dialog = SimpleNamespace(
            _prompt_rebind=MagicMock(return_value=True),
            _on_check_updates=MagicMock(),
        )
        resolution = PluginSourceKeyResolution(
            plugin_id="plugin-uuid",
            available=False,
            reason=GitHubKeyUnavailableReason.KEY_INVALID,
        )

        PluginManagementDialog._on_source_resolved(
            dialog, "plugin-uuid", "", resolution)

        dialog._prompt_rebind.assert_called_once_with("plugin-uuid", resolution)
        dialog._on_check_updates.assert_called_once_with()

    def test_available_key_continues_release_fetch(self):
        """来源 Key 可用后继续获取版本列表。"""
        dialog = SimpleNamespace(
            pm=SimpleNamespace(registry=SimpleNamespace(get=lambda _id: {
                "source_url": "https://github.com/acme/repo",
            })),
            installer=MagicMock(),
            _on_versions_fetched=MagicMock(),
            _run_background=lambda fn, callback: callback(fn()),
        )
        dialog.installer.get_available_versions.return_value = []
        resolution = PluginSourceKeyResolution(
            plugin_id="plugin-uuid",
            available=True,
            visibility="private",
            key_id="key-b",
        )

        PluginManagementDialog._on_source_resolved(
            dialog, "plugin-uuid", "", resolution)

        dialog.installer.get_available_versions.assert_called_once_with(
            "https://github.com/acme/repo", "", "key-b")
        dialog._on_versions_fetched.assert_called_once_with("plugin-uuid", [])

    def test_active_key_still_opens_proactive_rebind(self):
        """当前 Key 可用时也应允许主动更换绑定。"""
        dialog = SimpleNamespace(
            _open_rebind_dialog=MagicMock(return_value=True),
            _prompt_rebind=MagicMock(),
            reload_plugin_lists=MagicMock(),
        )
        resolution = PluginSourceKeyResolution(
            plugin_id="plugin-uuid",
            available=True,
            visibility="private",
            key_id="key-a",
        )

        PluginManagementDialog._on_manual_rebind_resolved(
            dialog, "plugin-uuid", resolution)

        dialog._open_rebind_dialog.assert_called_once_with(
            "plugin-uuid", resolution)
        dialog._prompt_rebind.assert_not_called()
        dialog.reload_plugin_lists.assert_called_once_with()

    def test_unavailable_key_uses_recovery_prompt(self):
        """失效 Key 的主动入口继续走恢复提示。"""
        dialog = SimpleNamespace(
            _open_rebind_dialog=MagicMock(),
            _prompt_rebind=MagicMock(return_value=False),
            reload_plugin_lists=MagicMock(),
        )
        resolution = PluginSourceKeyResolution(
            plugin_id="plugin-uuid",
            available=False,
            reason=GitHubKeyUnavailableReason.KEY_INVALID,
            error_message="expired",
        )

        PluginManagementDialog._on_manual_rebind_resolved(
            dialog, "plugin-uuid", resolution)

        dialog._prompt_rebind.assert_called_once_with(
            "plugin-uuid", resolution)
        dialog._open_rebind_dialog.assert_not_called()
        dialog.reload_plugin_lists.assert_not_called()


class TestPrivateVersionDialog:
    """验证版本选择窗口显式标记私有来源。"""

    def test_private_notice_includes_key_name(self, qtbot):
        """私有 Release 选择界面显示 Key 名称。"""
        dialog = VersionSelectDialog(
            "私有插件",
            "release.1.0.0",
            [ReleaseInfo("v1.1.0", "v1.1.0", "release.1.1.0")],
            source_visibility="private",
            key_name="工作账号",
        )
        qtbot.addWidget(dialog)

        texts = [label.text() for label in dialog.findChildren(QLabel)]

        assert any("私有仓库" in text for text in texts)
        assert any("工作账号" in text for text in texts)
