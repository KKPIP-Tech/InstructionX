"""GitHubKeyManager 多 Key 生命周期测试。"""

from unittest.mock import MagicMock

import pytest

from core.github import (
    ENVIRONMENT_KEY_ID,
    GitHubAuthIdentity,
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyInvalidError,
    GitHubKeyManager,
    GitHubKeyNotFoundError,
    GitHubKeyStore,
    GitHubKeyStatus,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
    InMemorySecretVault,
    get_github_key_manager,
)


def _identity(account: str = "octocat"):
    """构造验证身份结果。"""
    return GitHubAuthIdentity(
        account_login=account,
        token_kind=GitHubTokenKind.FINE_GRAINED,
        expires_at="2026-12-01",
        expiration_source=GitHubExpirationSource.GITHUB_HEADER,
        oauth_scopes=(),
    )


class TestKeyLifecycle:
    """验证新增、验证、重命名和默认 Key。"""

    def test_add_key_verifies_before_persisting(self, key_manager):
        """新增 Key 应记录验证身份与过期信息。"""
        manager, store, api = key_manager
        api.get_authenticated_user.return_value = _identity()

        view = manager.add_key("工作账号", "github_pat_token")

        assert view.status is GitHubKeyStatus.VALID
        assert view.account_login == "octocat"
        assert view.expires_at == "2026-12-01"
        assert len(store.list_views()) == 1

    def test_invalid_new_key_is_not_persisted(self, key_manager):
        """新增时验证失败不得写入配置。"""
        manager, store, api = key_manager
        api.get_authenticated_user.side_effect = GitHubKeyInvalidError("bad")

        with pytest.raises(GitHubKeyInvalidError):
            manager.add_key("坏 Key", "bad")

        assert store.list_views() == []

    def test_duplicate_name_is_rejected_before_network(self, key_manager):
        """重复名称在调用 GitHub 前即被拒绝。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        manager.add_key("Work", "github_pat_one")
        api.get_authenticated_user.reset_mock()

        with pytest.raises(ValueError, match="已存在"):
            manager.add_key("work", "github_pat_two")

        api.get_authenticated_user.assert_not_called()

    def test_verify_success_updates_existing_record(self, key_manager):
        """再次验证成功应更新账号和状态。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity("first")
        view = manager.add_key("账号", "github_pat_token")
        api.get_authenticated_user.return_value = _identity("second")

        result = manager.verify_key(view.id)

        assert result.success is True
        assert result.view.account_login == "second"

    def test_verify_failure_marks_invalid(self, key_manager):
        """验证失败应持久化 invalid 状态。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("账号", "github_pat_token")
        api.get_authenticated_user.side_effect = GitHubKeyInvalidError("expired")

        result = manager.verify_key(view.id)

        assert result.success is False
        assert result.view.status is GitHubKeyStatus.INVALID
        assert result.error_code == "GitHubKeyInvalidError"

    def test_repository_success_clears_invalid_status(self, key_manager):
        """仓库访问成功应清除之前缓存的 invalid 状态。"""
        manager, store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("账号", "github_pat_token")
        store.update_verification(
            view.id,
            account_login="octocat",
            token_kind=GitHubTokenKind.FINE_GRAINED,
            status=GitHubKeyStatus.INVALID,
            expires_at=None,
            expiration_source=GitHubExpirationSource.UNAVAILABLE,
            oauth_scopes=(),
        )

        manager.mark_repository_access_valid(view.id)

        assert store.get_view(view.id).status is GitHubKeyStatus.VALID

    def test_default_key_can_be_changed(self, key_manager):
        """默认 Key 可设置和清除。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("账号", "github_pat_token")

        manager.set_default_key(view.id)
        assert manager.get_default_key_id() == view.id

        manager.set_default_key("")
        assert manager.get_default_key_id() == ""

    def test_rename_and_replace_token(self, key_manager):
        """重命名和替换 Token 应复用同一 Key ID。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("旧名称", "github_pat_old")

        renamed = manager.rename_key(view.id, "新名称")
        replaced = manager.replace_token(view.id, "github_pat_new")

        assert renamed.id == view.id
        assert replaced.name == "新名称"
        assert replaced.account_login == "octocat"

    def test_delete_key(self, key_manager):
        """删除 Key 后列表为空。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("账号", "github_pat_token")

        manager.delete_key(view.id)

        assert manager.list_keys() == []

    def test_missing_key_raises(self, key_manager):
        """不存在的 Key 应抛出领域异常。"""
        manager, _store, _api = key_manager

        with pytest.raises(Exception, match="不存在"):
            manager.get_credential("missing")


class TestEnvironmentCompatibility:
    """验证环境变量 Key 只读兼容语义。"""

    def test_environment_key_is_listed_read_only(
        self, tmp_path, mock_logger
    ):
        """环境变量 Key 应出现在列表但不可删除。"""
        store = GitHubKeyStore(
            tmp_path / "config", InMemorySecretVault(), logger=mock_logger)
        manager = GitHubKeyManager(
            store=store,
            api_client=MagicMock(),
            environment_reader=lambda _name: "env-token",
            logger=mock_logger,
        )

        views = manager.list_keys()

        assert any(view.id == ENVIRONMENT_KEY_ID for view in views)
        with pytest.raises(ValueError, match="只读"):
            manager.delete_key(ENVIRONMENT_KEY_ID)

    def test_environment_key_view_is_available(
        self, tmp_path, mock_logger
    ):
        """环境变量 Key 可读取只读展示模型。"""
        manager = GitHubKeyManager(
            store=GitHubKeyStore(
                tmp_path / "config",
                InMemorySecretVault(),
                logger=mock_logger,
            ),
            api_client=MagicMock(),
            environment_reader=lambda _name: "env-token",
            logger=mock_logger,
        )

        view = manager.get_key_view(ENVIRONMENT_KEY_ID)

        assert view.id == ENVIRONMENT_KEY_ID
        assert view.is_environment is True

    def test_singleton_reuses_manager(self, tmp_path, mock_logger):
        """重复构造返回同一管理器并保留初始化状态。"""
        store = GitHubKeyStore(
            tmp_path / "config", InMemorySecretVault(), logger=mock_logger)
        first = GitHubKeyManager(
            store=store, api_client=MagicMock(), logger=mock_logger)
        second = GitHubKeyManager()

        assert get_github_key_manager() is first
        assert second is first

    def test_environment_credential_is_resolved(
        self, tmp_path, mock_logger
    ):
        """环境变量 Token 应解析为内存凭据。"""
        manager = GitHubKeyManager(
            store=GitHubKeyStore(
                tmp_path / "config",
                InMemorySecretVault(),
                logger=mock_logger,
            ),
            api_client=MagicMock(),
            environment_reader=lambda _name: "env-token",
            logger=mock_logger,
        )

        credential = manager.get_credential(ENVIRONMENT_KEY_ID)

        assert credential.token == "env-token"
        assert credential.is_environment is True

    def test_environment_key_can_be_verified(
        self, tmp_path, mock_logger
    ):
        """环境变量 Key 验证成功但不写入配置。"""
        api = MagicMock()
        api.get_authenticated_user.return_value = _identity()
        manager = GitHubKeyManager(
            store=GitHubKeyStore(
                tmp_path / "config",
                InMemorySecretVault(),
                logger=mock_logger,
            ),
            api_client=api,
            environment_reader=lambda _name: "env-token",
            logger=mock_logger,
        )

        result = manager.verify_key(ENVIRONMENT_KEY_ID)

        assert result.success is True
        assert result.view.is_environment is True
        assert manager._store.list_views() == []

    def test_missing_environment_key_raises(
        self, tmp_path, mock_logger
    ):
        """环境变量未设置时不得构造空凭据。"""
        manager = GitHubKeyManager(
            store=GitHubKeyStore(
                tmp_path / "config",
                InMemorySecretVault(),
                logger=mock_logger,
            ),
            api_client=MagicMock(),
            environment_reader=lambda _name: "",
            logger=mock_logger,
        )

        with pytest.raises(GitHubKeyNotFoundError, match="不存在"):
            manager.get_credential(ENVIRONMENT_KEY_ID)


class TestRepositoryVerification:
    """验证目标仓库授权检查。"""

    def test_repository_access_uses_bound_key(self, key_manager):
        """仓库验证必须使用指定 Key 解析出的凭据。"""
        manager, _store, api = key_manager
        api.get_authenticated_user.return_value = _identity()
        view = manager.add_key("账号", "github_pat_token")
        repository = GitHubRepositoryInfo(
            owner="owner",
            repo="private-repo",
            visibility=GitHubRepositoryVisibility.PRIVATE,
            auth_key_id=view.id,
        )
        api.get_repository.return_value = repository

        result = manager.verify_repository_access(
            view.id, "owner", "private-repo")

        assert result.visibility is GitHubRepositoryVisibility.PRIVATE
        credential = api.get_repository.call_args.args[2]
        assert isinstance(credential, GitHubCredential)
        assert credential.key_id == view.id
