"""GitHub 安装对话框的 Key 选择与私有提示测试。"""

from unittest.mock import MagicMock

from PySide6.QtWidgets import QDialog

from core.github import (
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
    NO_KEY_ID,
)
from core.plugin.github_plugin_installer import (
    PluginInfo,
    RepoInspectionResult,
)
from ui.dialog import github_plugin_install_dialog as module
from ui.dialog.github_plugin_install_dialog import (
    INFO_STACK_MIN_HEIGHT,
    GitHubPluginInstallDialog,
)


def _key_view(key_id: str, name: str) -> GitHubKeyView:
    """构造测试 Key。"""
    return GitHubKeyView(
        id=key_id,
        name=name,
        account_login=f"{key_id}-user",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=GitHubKeyStatus.VALID,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="",
        last_error_code="",
        last_error_message="",
    )


def _private_result() -> RepoInspectionResult:
    """构造私有单插件检查结果。"""
    repository = GitHubRepositoryInfo(
        owner="acme",
        repo="private-plugins",
        visibility=GitHubRepositoryVisibility.PRIVATE,
        default_branch="main",
        auth_key_id="key-b",
        auth_key_name="备用账号",
        auth_account_login="backup-user",
    )
    plugin = PluginInfo(
        plugin_id="private-plugin",
        name="私有插件",
        version="release.1.0.0",
        main="entrance.py",
    )
    return RepoInspectionResult.single(
        plugin, repository=repository, key_id="key-b")


class TestInstallKeySelection:
    """验证 Key 下拉框和私有提示。"""

    def test_key_combo_lists_auto_and_named_keys(
        self, qtbot, mocker
    ):
        """下拉框包含自动模式与所有 Key。"""
        mocker.patch.object(module, "GitHubPluginInstaller", return_value=MagicMock())
        manager = MagicMock()
        manager.list_keys.return_value = [
            _key_view("key-a", "工作账号"),
            _key_view("key-b", "备用账号"),
        ]
        dialog = GitHubPluginInstallDialog(key_manager=manager)
        qtbot.addWidget(dialog)

        assert dialog.key_combo.count() == 3
        assert dialog.key_combo.itemData(0) == NO_KEY_ID
        assert dialog.key_combo.itemText(0) == "不使用 Key"
        assert dialog.key_combo.itemData(1) == "key-a"
        assert dialog.info_stack.minimumHeight() == INFO_STACK_MIN_HEIGHT

    def test_private_notice_displays_repository_and_key(
        self, qtbot, mocker
    ):
        """私有结果应显示仓库、Key 和账号。"""
        mocker.patch.object(module, "GitHubPluginInstaller", return_value=MagicMock())
        manager = MagicMock()
        manager.list_keys.return_value = []
        dialog = GitHubPluginInstallDialog(key_manager=manager)
        qtbot.addWidget(dialog)
        dialog.url_input.setText("https://github.com/acme/private-plugins")

        dialog._update_private_notice(_private_result())

        assert dialog.private_notice.isVisibleTo(dialog) is True
        assert "acme/private-plugins" in dialog.private_notice._detail.text()
        assert "备用账号" in dialog.private_notice._detail.text()
        qtbot.wait(20)
        assert dialog.private_notice.minimumHeight() > 0

    def test_public_result_clears_private_notice(
        self, qtbot, mocker
    ):
        """公共仓库不得显示私有提示。"""
        mocker.patch.object(module, "GitHubPluginInstaller", return_value=MagicMock())
        manager = MagicMock()
        manager.list_keys.return_value = []
        dialog = GitHubPluginInstallDialog(key_manager=manager)
        qtbot.addWidget(dialog)
        result = _private_result()
        result.repository = GitHubRepositoryInfo(
            owner="acme",
            repo="private-plugins",
            visibility=GitHubRepositoryVisibility.PUBLIC,
        )

        dialog._update_private_notice(result)

        assert dialog.private_notice.isVisibleTo(dialog) is False

    def test_install_worker_receives_selected_key(
        self, qtbot, mocker
    ):
        """安装线程必须接收固定 Key ID，而不是 Token。"""
        mocker.patch.object(module, "GitHubPluginInstaller", return_value=MagicMock())
        manager = MagicMock()
        manager.list_keys.return_value = [_key_view("key-b", "备用账号")]
        dialog = GitHubPluginInstallDialog(key_manager=manager)
        qtbot.addWidget(dialog)
        dialog.key_combo.setCurrentIndex(1)
        dialog.url_input.setText("https://github.com/acme/private-plugins")
        dialog.repo_result = _private_result()
        dialog._confirm_private_install = MagicMock(return_value=True)
        worker_factory = mocker.patch.object(module, "GitHubInstallWorker")

        dialog._on_install()

        args = worker_factory.call_args.args
        assert args[-1] == "key-b"

    def test_private_confirmation_is_required(self, qtbot, mocker):
        """私有安装必须弹出确认对话框。"""
        mocker.patch.object(module, "GitHubPluginInstaller", return_value=MagicMock())
        manager = MagicMock()
        manager.list_keys.return_value = []
        dialog = GitHubPluginInstallDialog(key_manager=manager)
        qtbot.addWidget(dialog)
        dialog.url_input.setText("https://github.com/acme/private-plugins")
        dialog.repo_result = _private_result()
        dialog_factory = mocker.patch.object(module, "Dialog")
        dialog_factory.return_value.exec.return_value = (
            QDialog.DialogCode.Rejected)

        accepted = dialog._confirm_private_install()

        assert accepted is False
        dialog_factory.return_value.set_text.assert_called_once()
