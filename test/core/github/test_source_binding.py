"""插件来源 Key 解析与重新绑定测试。"""

from unittest.mock import MagicMock

import pytest

from core.github import (
    GitHubCredential,
    GitHubKeyInvalidError,
    GitHubKeyNotFoundError,
    GitHubKeyStatus,
    GitHubKeyUnavailableReason,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    PluginSourceKeyBinder,
    parse_github_source_url,
)
from core.plugin.plugin_registry import (
    PluginRegistry,
    SOURCE_VISIBILITY_PRIVATE,
    SOURCE_VISIBILITY_PUBLIC,
)


def _key_view(key_id: str, status=GitHubKeyStatus.VALID) -> GitHubKeyView:
    """构造 Key 展示结果。"""
    from core.github import GitHubExpirationSource, GitHubTokenKind

    return GitHubKeyView(
        id=key_id,
        name=f"Key {key_id}",
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=status,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="",
        last_error_code="",
        last_error_message="",
    )


def _repository(visibility: GitHubRepositoryVisibility):
    """构造仓库信息。"""
    return GitHubRepositoryInfo(
        owner="acme",
        repo="private-plugins",
        visibility=visibility,
        can_pull=True,
    )


@pytest.fixture
def binder_bundle(tmp_path, mock_logger, mocker):
    """创建已绑定私有来源的 Binder 和假 Key 服务。"""
    mocker.patch(
        "core.plugin.plugin_registry.LoggerManager",
        return_value=mock_logger,
    )
    registry = PluginRegistry(tmp_path / "config")
    registry.upsert(
        "plugin-uuid",
        descriptor_id="private-plugin",
        name="私有插件",
        scope="thirdparty",
        version="release.1.0.0",
        source_type="github",
        source_url="https://github.com/acme/private-plugins",
        source_visibility=SOURCE_VISIBILITY_PRIVATE,
        source_key_id="key-a",
    )
    key_manager = MagicMock()
    api_client = MagicMock()
    binder = PluginSourceKeyBinder(registry, key_manager, api_client)
    return binder, registry, key_manager, api_client


class TestSourceResolution:
    """验证当前绑定是否可用及失败原因。"""

    def test_valid_private_binding_is_available(self, binder_bundle):
        """有效 Key 和私有仓库应返回可用。"""
        binder, _registry, keys, _api = binder_bundle
        keys.get_key_view.return_value = _key_view("key-a")
        keys.verify_repository_access.return_value = _repository(
            GitHubRepositoryVisibility.PRIVATE)

        result = binder.resolve("plugin-uuid")

        assert result.available is True
        assert result.visibility == SOURCE_VISIBILITY_PRIVATE
        assert result.key_id == "key-a"

    def test_unknown_plugin_is_not_supported(self, binder_bundle):
        """不存在插件返回 not_found。"""
        binder, _registry, _keys, _api = binder_bundle

        result = binder.resolve("missing")

        assert result.reason is GitHubKeyUnavailableReason.NOT_FOUND
        assert result.can_rebind is False

    def test_local_plugin_is_not_supported(self, binder_bundle):
        """本地插件来源不进入 Key 重绑流程。"""
        binder, registry, _keys, _api = binder_bundle
        registry.upsert(
            "local-uuid",
            descriptor_id="local",
            name="本地插件",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="local_zip",
        )

        result = binder.resolve("local-uuid")

        assert result.reason is GitHubKeyUnavailableReason.NOT_GITHUB
        assert result.can_rebind is False

    def test_invalid_source_url_is_reported(self, binder_bundle):
        """无效来源 URL 返回仓库访问错误。"""
        binder, registry, _keys, _api = binder_bundle
        registry.upsert(
            "bad-url",
            descriptor_id="bad",
            name="坏来源",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="github",
            source_url="https://example.com/a/b",
        )

        result = binder.resolve("bad-url")

        assert result.reason is GitHubKeyUnavailableReason.REPOSITORY_ACCESS

    def test_deleted_key_requires_rebind(self, binder_bundle):
        """被删除的 Key 必须返回可重新绑定状态。"""
        binder, _registry, keys, _api = binder_bundle
        keys.get_key_view.side_effect = GitHubKeyNotFoundError("missing")

        result = binder.resolve("plugin-uuid")

        assert result.available is False
        assert result.reason is GitHubKeyUnavailableReason.KEY_DELETED
        assert result.can_rebind is True

    def test_invalid_key_requires_rebind(self, binder_bundle):
        """已标记失效的 Key 不得访问仓库。"""
        binder, _registry, keys, _api = binder_bundle
        keys.get_key_view.return_value = _key_view(
            "key-a", GitHubKeyStatus.INVALID)

        result = binder.resolve("plugin-uuid")

        assert result.reason is GitHubKeyUnavailableReason.KEY_INVALID
        keys.verify_repository_access.assert_not_called()

    def test_missing_private_binding_requests_key(self, binder_bundle):
        """私有来源没有 Key ID 时提示重新绑定。"""
        binder, registry, _keys, _api = binder_bundle
        registry.set_source_binding(
            "plugin-uuid",
            source_visibility=SOURCE_VISIBILITY_PRIVATE,
            source_key_id="",
        )

        result = binder.resolve("plugin-uuid")

        assert result.reason is GitHubKeyUnavailableReason.MISSING_BINDING
        assert result.can_rebind is True

    def test_repository_access_error_requires_rebind(self, binder_bundle):
        """Key 无仓库权限时必须进入重新绑定。"""
        from core.github import GitHubRepositoryAccessError

        binder, _registry, keys, _api = binder_bundle
        keys.get_key_view.return_value = _key_view("key-a")
        keys.verify_repository_access.side_effect = (
            GitHubRepositoryAccessError("no access", authenticated=True))

        result = binder.resolve("plugin-uuid")

        assert result.reason is GitHubKeyUnavailableReason.REPOSITORY_ACCESS
        assert result.can_rebind is True

    def test_public_source_does_not_require_key(self, binder_bundle):
        """已记录为公共的来源无需 Key。"""
        binder, registry, keys, _api = binder_bundle
        registry.set_source_binding(
            "plugin-uuid",
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
            source_key_id="",
        )

        _api.get_repository.return_value = _repository(
            GitHubRepositoryVisibility.PUBLIC)

        result = binder.resolve("plugin-uuid")

        assert result.available is True
        assert result.visibility == SOURCE_VISIBILITY_PUBLIC
        keys.get_key_view.assert_not_called()

    def test_public_source_changed_to_private_requests_key(
        self, binder_bundle
    ):
        """公共来源转为私有时必须要求重新绑定。"""
        binder, registry, _keys, api = binder_bundle
        registry.set_source_binding(
            "plugin-uuid",
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
            source_key_id="",
        )
        api.get_repository.return_value = _repository(
            GitHubRepositoryVisibility.PRIVATE)

        result = binder.resolve("plugin-uuid")

        assert result.available is False
        assert result.reason is GitHubKeyUnavailableReason.MISSING_BINDING


class TestRebind:
    """验证新 Key 验证成功后才覆盖旧绑定。"""

    def test_successful_rebind_updates_registry(self, binder_bundle):
        """新 Key 可访问私有仓库时保存新 ID。"""
        binder, registry, keys, api = binder_bundle
        keys.get_credential.return_value = GitHubCredential(
            "key-b", "备用账号", "token-b", "backup")
        api.get_repository.return_value = _repository(
            GitHubRepositoryVisibility.PRIVATE)

        result = binder.rebind("plugin-uuid", "key-b")
        record = registry.get("plugin-uuid")

        assert result.available is True
        assert result.key_id == "key-b"
        assert record["source_key_id"] == "key-b"
        assert record["source_visibility"] == SOURCE_VISIBILITY_PRIVATE
        keys.mark_repository_access_valid.assert_called_once_with("key-b")

    def test_failed_rebind_keeps_old_key(self, binder_bundle):
        """新 Key 无权限时旧绑定保持不变。"""
        binder, registry, keys, api = binder_bundle
        keys.get_credential.return_value = GitHubCredential(
            "key-b", "备用账号", "token-b", "backup")
        api.get_repository.side_effect = GitHubKeyInvalidError("expired")

        result = binder.rebind("plugin-uuid", "key-b")
        record = registry.get("plugin-uuid")

        assert result.available is False
        assert result.reason is GitHubKeyUnavailableReason.KEY_INVALID
        assert record["source_key_id"] == "key-a"

    def test_public_repository_clears_key_binding(self, binder_bundle):
        """已验证为公共时清除 Key 绑定。"""
        binder, registry, keys, api = binder_bundle
        keys.get_credential.return_value = GitHubCredential(
            "key-b", "备用账号", "token-b", "backup")
        api.get_repository.return_value = _repository(
            GitHubRepositoryVisibility.PUBLIC)

        result = binder.rebind("plugin-uuid", "key-b")
        record = registry.get("plugin-uuid")

        assert result.visibility == SOURCE_VISIBILITY_PUBLIC
        assert record["source_visibility"] == SOURCE_VISIBILITY_PUBLIC
        assert record["source_key_id"] == ""

    def test_clear_binding_is_explicit(self, binder_bundle):
        """公共来源可主动清除旧 Key。"""
        binder, registry, _keys, _api = binder_bundle

        changed = binder.clear_binding("plugin-uuid")

        assert changed is True
        assert registry.get("plugin-uuid")["source_key_id"] == ""


class TestSourceUrlParsing:
    """验证插件来源 URL 解析。"""

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://github.com/acme/repo", ("acme", "repo")),
            ("https://github.com/acme/repo.git", ("acme", "repo")),
            ("https://github.com/acme/repo/releases", ("acme", "repo")),
            ("git@github.com:acme/repo.git", ("acme", "repo")),
            ("https://example.com/acme/repo", None),
            ("", None),
        ],
    )
    def test_parse_supported_urls(self, url, expected):
        """仅 GitHub HTTPS/SSH 形式应被接受。"""
        assert parse_github_source_url(url) == expected
