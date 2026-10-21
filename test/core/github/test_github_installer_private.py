"""GitHubPluginInstaller 私有仓库鉴权与绑定测试。"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.github import (
    ENVIRONMENT_KEY_ID,
    GitHubCredential,
    GitHubKeyNotFoundError,
    GitHubRepositoryAccessError,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    NO_KEY_ID,
)
from core.plugin.github_plugin_installer import (
    ERROR_AUTH_REQUIRED_OR_NOT_FOUND,
    ERROR_KEY_INVALID,
    ERROR_KEY_NOT_FOUND,
    GitHubPluginInstaller,
)
from core.plugin.plugin_registry import (
    PluginRegistry,
    SOURCE_VISIBILITY_PRIVATE,
    SOURCE_VISIBILITY_PUBLIC,
)


def _descriptor(plugin_id: str = "private-plugin") -> dict:
    """构造最小合法插件描述。"""
    return {
        "id": plugin_id,
        "name": "私有插件",
        "version": "release.1.0.0",
        "main": "entrance.py",
    }


def _repo(
    visibility: GitHubRepositoryVisibility,
    key_id: str = "",
) -> GitHubRepositoryInfo:
    """构造仓库元数据。"""
    return GitHubRepositoryInfo(
        owner="acme",
        repo="private-plugins",
        visibility=visibility,
        default_branch="main",
        can_pull=True,
        auth_key_id=key_id,
    )


@pytest.fixture
def installer_bundle(tmp_path, mock_logger, mocker):
    """创建隔离的插件管理器、安装器和假 GitHub 服务。"""
    mocker.patch(
        "core.plugin.github_plugin_installer.LoggerManager",
        return_value=mock_logger,
    )
    mocker.patch(
        "core.plugin.plugin_registry.LoggerManager",
        return_value=mock_logger,
    )
    official = tmp_path / "plugin"
    thirdparty = tmp_path / "custom_plugin"
    official.mkdir()
    thirdparty.mkdir()
    registry = PluginRegistry(tmp_path / "config")
    plugin_manager = SimpleNamespace(
        official_plugin_dir=official,
        thirdparty_plugin_dir=thirdparty,
        registry=registry,
    )
    key_manager = MagicMock()
    api_client = MagicMock()
    key_manager.get_credential.side_effect = GitHubKeyNotFoundError("missing")
    installer = GitHubPluginInstaller(
        plugin_manager,
        key_manager=key_manager,
        api_client=api_client,
    )
    return installer, plugin_manager, key_manager, api_client, tmp_path


def _credential(key_id: str = "key-a") -> GitHubCredential:
    """构造私有仓库测试凭据。"""
    return GitHubCredential(
        key_id=key_id,
        key_name="工作账号",
        token="secret-token",
        account_login="acme-user",
    )


class TestPrivateRepositoryInspection:
    """验证仓库可见性与 Key 使用。"""

    def test_private_repository_is_explicitly_returned(
        self, installer_bundle
    ):
        """私有仓库检查结果必须携带 private 和 Key ID。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        credential = _credential()
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = credential
        api.get_repository.return_value = _repo(
            GitHubRepositoryVisibility.PRIVATE, "key-a")
        api.get_file_json.side_effect = [None, _descriptor()]

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins", key_id="key-a")

        assert result.repo_type == "single"
        assert result.repository.visibility is GitHubRepositoryVisibility.PRIVATE
        assert result.key_id == "key-a"
        assert api.get_repository.call_args.args[2] is credential

    def test_public_repository_has_no_bound_key(self, installer_bundle):
        """公共仓库结果不得记录 Key ID。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = _credential()
        api.get_repository.return_value = _repo(
            GitHubRepositoryVisibility.PUBLIC)
        api.get_file_json.side_effect = [None, _descriptor()]

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins", key_id="key-a")

        assert result.repository.visibility is GitHubRepositoryVisibility.PUBLIC
        assert result.key_id == ""

    def test_unauthenticated_404_returns_auth_code(self, installer_bundle):
        """未认证 404 必须返回可引导选择 Key 的错误码。"""
        installer, _pm, _keys, api, _tmp = installer_bundle
        api.get_repository.side_effect = GitHubRepositoryAccessError(
            "可能为私有仓库", authenticated=False, status_code=404)

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins")

        assert result.repo_type == "invalid"
        assert result.error_code == ERROR_AUTH_REQUIRED_OR_NOT_FOUND

    def test_invalid_key_returns_key_error_code(self, installer_bundle):
        """401 必须返回 Key 无效错误码。"""
        from core.github import GitHubKeyInvalidError

        installer, _pm, _keys, api, _tmp = installer_bundle
        api.get_repository.side_effect = GitHubKeyInvalidError("expired")

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins")

        assert result.error_code == ERROR_KEY_INVALID

    def test_auto_mode_retries_with_default_key(
        self, installer_bundle
    ):
        """自动模式在匿名 404 后只尝试默认 Key。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        credential = _credential("default-key")
        keys.get_default_key_id.return_value = "default-key"
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = credential
        api.get_repository.side_effect = [
            GitHubRepositoryAccessError(
                "not public", authenticated=False, status_code=404),
            _repo(GitHubRepositoryVisibility.PRIVATE, "default-key"),
        ]
        api.get_file_json.side_effect = [None, _descriptor()]

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins")

        assert result.repo_type == "single"
        assert result.key_id == "default-key"
        assert api.get_repository.call_count == 2
        keys.get_credential.assert_called_with("default-key")

    def test_explicit_key_does_not_fallback(self, installer_bundle):
        """显式选择的 Key 失败时不得静默切换默认 Key。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = _credential("explicit")
        api.get_repository.side_effect = GitHubRepositoryAccessError(
            "no access", authenticated=True, status_code=404)

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins", key_id="explicit")

        assert result.error_code == "repository_access"
        keys.get_default_key_id.assert_not_called()

    def test_no_key_sentinel_never_uses_default_or_environment(
        self, installer_bundle
    ):
        """界面选择“不使用 Key”时只能匿名访问。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        api.get_repository.return_value = _repo(
            GitHubRepositoryVisibility.PUBLIC)
        api.get_file_json.side_effect = [None, _descriptor()]

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins",
            key_id=NO_KEY_ID,
        )

        assert result.repo_type == "single"
        assert api.get_repository.call_args.args[2] is None
        keys.get_default_key_id.assert_not_called()
        keys.get_credential.assert_not_called()

    def test_missing_explicit_key_returns_key_not_found(
        self, installer_bundle
    ):
        """显式 Key ID 不存在时返回可诊断错误码。"""
        installer, _pm, keys, _api, _tmp = installer_bundle
        keys.get_credential.side_effect = GitHubKeyNotFoundError("missing")

        result = installer.inspect_repository(
            "https://github.com/acme/private-plugins",
            key_id="missing",
        )

        assert result.error_code == ERROR_KEY_NOT_FOUND


class TestPrivateRepositoryInstall:
    """验证私有仓库下载、安装与注册表绑定。"""

    def test_private_install_records_visibility_and_key(
        self, installer_bundle, mocker
    ):
        """私有仓库安装成功后绑定 Key。"""
        installer, pm, keys, api, tmp_path = installer_bundle
        repository_root = tmp_path / "downloaded"
        repository_root.mkdir()
        (repository_root / "IXPlugin.json").write_text(
            json.dumps(_descriptor()), encoding="utf-8")
        credential = _credential()
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = credential
        api.get_repository.return_value = _repo(
            GitHubRepositoryVisibility.PRIVATE, "key-a")
        mocker.patch.object(
            installer, "_download_repository", return_value=repository_root)

        results = installer.install_from_url(
            "https://github.com/acme/private-plugins",
            official_dir=pm.official_plugin_dir,
            thirdparty_dir=pm.thirdparty_plugin_dir,
            key_id="key-a",
        )

        assert results[0].success is True
        _uuid, record = pm.registry.find_by_descriptor(
            "thirdparty", results[0].plugin_id)
        assert record["source_visibility"] == SOURCE_VISIBILITY_PRIVATE
        assert record["source_key_id"] == "key-a"

    def test_public_install_records_public_without_key(
        self, installer_bundle, mocker
    ):
        """公共仓库安装不保存 Key 绑定。"""
        installer, pm, keys, api, tmp_path = installer_bundle
        repository_root = tmp_path / "downloaded-public"
        repository_root.mkdir()
        (repository_root / "IXPlugin.json").write_text(
            json.dumps(_descriptor("public-plugin")), encoding="utf-8")
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = _credential()
        api.get_repository.return_value = _repo(
            GitHubRepositoryVisibility.PUBLIC)
        mocker.patch.object(
            installer, "_download_repository", return_value=repository_root)

        results = installer.install_from_url(
            "https://github.com/acme/private-plugins",
            official_dir=pm.official_plugin_dir,
            thirdparty_dir=pm.thirdparty_plugin_dir,
            key_id="key-a",
        )

        _uuid, record = pm.registry.find_by_descriptor(
            "thirdparty", results[0].plugin_id)
        assert record["source_visibility"] == SOURCE_VISIBILITY_PUBLIC
        assert record["source_key_id"] == ""

    def test_download_uses_api_stream_and_credential(self, installer_bundle):
        """归档下载必须走 API 客户端并携带同一个 Key。"""
        installer, _pm, _keys, api, _tmp = installer_bundle
        credential = _credential()
        response = MagicMock(status_code=200)
        api.stream_zipball.return_value = response
        installer._stream_to_zip = MagicMock(return_value=True)

        temp_dir, status = installer._try_download_archive(
            "acme", "private-plugins", "main", credential, "ix_test_")

        assert status is None
        assert temp_dir is not None
        api.stream_zipball.assert_called_once_with(
            "acme", "private-plugins", "main", credential)
        temp_dir.cleanup() if hasattr(temp_dir, "cleanup") else None


class TestPrivateRelease:
    """验证 Release 查询与安装鉴权。"""

    def test_available_versions_uses_bound_key(self, installer_bundle):
        """Release 和描述文件读取必须使用绑定 Key。"""
        installer, _pm, keys, api, _tmp = installer_bundle
        credential = _credential()
        keys.get_credential.side_effect = None
        keys.get_credential.return_value = credential
        api.list_releases.return_value = [{
            "tag_name": "v1.0.0",
            "name": "v1.0.0",
            "prerelease": False,
            "published_at": "2026-01-01",
        }]
        api.get_file_json.return_value = _descriptor()

        releases = installer.get_available_versions(
            "https://github.com/acme/private-plugins", key_id="key-a")

        assert releases[0].version == "release.1.0.0"
        assert api.list_releases.call_args.args[2] is credential
        assert api.get_file_json.call_args.kwargs["credential"] is credential
