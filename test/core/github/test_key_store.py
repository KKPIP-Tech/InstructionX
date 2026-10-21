"""GitHub KeyStore 的 CRUD、持久化与恢复测试。"""

import json
from pathlib import Path

import pytest

from core.github import (
    GitHubCredentialVaultError,
    GitHubExpirationSource,
    GitHubKeyNotFoundError,
    GitHubKeyStatus,
    GitHubKeyStore,
    GitHubTokenKind,
    InMemorySecretVault,
    MAX_GITHUB_KEY_NAME_LENGTH,
    MAX_GITHUB_TOKEN_LENGTH,
)


class TestGitHubKeyStoreCrud:
    """验证多 Key 管理与无敏感字段展示。"""

    def test_add_multiple_keys_and_list_views(self, key_store):
        """可添加多个命名 Key，展示模型不暴露密文。"""
        first = key_store.add_key(
            "工作账号",
            "token-one",
            account_login="work",
            token_kind=GitHubTokenKind.FINE_GRAINED,
            status=GitHubKeyStatus.VALID,
        )
        second = key_store.add_key("个人账号", "token-two")

        views = key_store.list_views()

        assert {view.id for view in views} == {first.id, second.id}
        assert all(not hasattr(view, "encrypted_token") for view in views)
        assert key_store.get_secret(first.id) == "token-one"

    def test_rename_keeps_stable_id(self, key_store):
        """重命名不得改变 Key ID。"""
        created = key_store.add_key("旧名称", "token")

        renamed = key_store.rename_key(created.id, "新名称")

        assert renamed.id == created.id
        assert renamed.name == "新名称"

    def test_duplicate_name_is_case_insensitive(self, key_store):
        """Key 名称重复检查忽略大小写。"""
        key_store.add_key("Work", "token-one")

        with pytest.raises(ValueError, match="名称已存在"):
            key_store.add_key("work", "token-two")

    def test_empty_name_is_rejected(self, key_store):
        """Key 名称不能为空。"""
        with pytest.raises(ValueError, match="名称不能为空"):
            key_store.add_key("   ", "token")

    def test_overlong_name_is_rejected(self, key_store):
        """超长 Key 名称不得写入。"""
        with pytest.raises(ValueError, match="不能超过"):
            key_store.add_key("x" * (MAX_GITHUB_KEY_NAME_LENGTH + 1), "token")

    def test_overlong_token_is_rejected(self, key_store):
        """超长 Token 不得进入加密后端。"""
        with pytest.raises(GitHubCredentialVaultError, match="长度异常"):
            key_store.add_key("账号", "x" * (MAX_GITHUB_TOKEN_LENGTH + 1))

    def test_empty_token_is_rejected(self, key_store):
        """空白 Token 不能进入加密后端。"""
        with pytest.raises(Exception, match="Token 不能为空"):
            key_store.add_key("账号", "   ")

    def test_default_key_is_cleared_on_delete(self, key_store):
        """删除默认 Key 时同步清空默认值。"""
        created = key_store.add_key("账号", "token")
        key_store.set_default(created.id)

        key_store.remove_key(created.id)

        assert key_store.get_default_key_id() == ""
        assert key_store.list_views() == []

    def test_unknown_key_raises_domain_error(self, key_store):
        """不存在的 Key 使用明确领域异常。"""
        with pytest.raises(GitHubKeyNotFoundError):
            key_store.get_view("missing")

    def test_update_verification_keeps_token(self, key_store):
        """验证元数据更新不得替换 Token。"""
        created = key_store.add_key("账号", "token")

        updated = key_store.update_verification(
            created.id,
            account_login="octocat",
            token_kind=GitHubTokenKind.CLASSIC,
            status=GitHubKeyStatus.VALID,
            expires_at=None,
            expiration_source=GitHubExpirationSource.UNAVAILABLE,
            oauth_scopes=("repo",),
        )

        assert updated.account_login == "octocat"
        assert updated.oauth_scopes == ("repo",)
        assert key_store.get_secret(created.id) == "token"

    def test_replace_token_updates_secret_and_identity(self, key_store):
        """替换 Token 应更新密文与验证身份。"""
        created = key_store.add_key("账号", "old-token")

        replaced = key_store.replace_token(
            created.id,
            "new-token",
            account_login="new-user",
            token_kind=GitHubTokenKind.CLASSIC,
            status=GitHubKeyStatus.VALID,
            oauth_scopes=("repo",),
        )

        assert replaced.account_login == "new-user"
        assert replaced.token_kind is GitHubTokenKind.CLASSIC
        assert key_store.get_secret(created.id) == "new-token"

    def test_delete_non_default_keeps_default(self, key_store):
        """删除非默认 Key 不影响默认值。"""
        default = key_store.add_key("默认", "token-a")
        other = key_store.add_key("其他", "token-b")
        key_store.set_default(default.id)

        key_store.remove_key(other.id)

        assert key_store.get_default_key_id() == default.id


class TestGitHubKeyStorePersistence:
    """验证文件安全、重载、损坏恢复和原子写。"""

    def test_file_contains_no_plaintext(self, key_store, tmp_path):
        """磁盘配置不得包含 Token 明文。"""
        key_store.add_key("账号", "plain-secret")

        content = (tmp_path / "config" / "github_keys.json").read_text(
            encoding="utf-8")

        assert "plain-secret" not in content

    def test_reload_reads_records_and_default(
        self, key_store, tmp_path, mock_logger
    ):
        """重载后恢复 Key 与默认绑定。"""
        created = key_store.add_key("账号", "token")
        key_store.set_default(created.id)
        reloaded = GitHubKeyStore(
            tmp_path / "config", InMemorySecretVault(), logger=mock_logger)

        reloaded.load()

        assert len(reloaded.list_views()) == 1
        assert reloaded.get_default_key_id() == created.id

    def test_invalid_default_is_ignored(self, tmp_path, mock_logger):
        """默认 Key ID 不存在时安全降级为空。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "github_keys.json").write_text(
            '{"version": 1, "default_key_id": "missing", "keys": []}',
            encoding="utf-8",
        )
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.get_default_key_id() == ""

    def test_corrupt_json_is_backed_up_and_rebuilt(self, tmp_path, mock_logger):
        """损坏配置备份后重建为空配置。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "github_keys.json").write_text("{broken", encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.list_views() == []
        assert list(config_dir.glob("github_keys.json.corrupt-*.bak"))

    def test_non_list_keys_is_rebuilt(self, tmp_path, mock_logger):
        """顶层 keys 类型错误时备份重建。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "github_keys.json").write_text(
            '{"version": 1, "keys": {}}', encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.list_views() == []

    def test_non_object_record_is_rebuilt(self, tmp_path, mock_logger):
        """Key 条目不是对象时备份重建。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "github_keys.json").write_text(
            '{"version": 1, "keys": ["bad"]}', encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.list_views() == []

    def test_duplicate_names_are_rebuilt(self, tmp_path, mock_logger):
        """手工配置中的重复名称应安全重建。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        records = [{
            "id": key_id,
            "name": "Same",
            "encrypted_token": "memory:v1:1",
            "token_kind": "unknown",
            "status": "untested",
            "expiration_source": "unavailable",
        } for key_id in ("a", "b")]
        (config_dir / "github_keys.json").write_text(
            json.dumps({"version": 1, "keys": records}), encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.list_views() == []

    def test_save_failure_becomes_domain_error(
        self, key_store, monkeypatch
    ):
        """原子写失败应转换为领域异常。"""
        key_store.load()
        monkeypatch.setattr(
            "os.replace",
            lambda *_args: (_ for _ in ()).throw(OSError("denied")),
        )

        with pytest.raises(GitHubCredentialVaultError, match="保存"):
            key_store.add_key("账号", "token")
        assert key_store.list_views() == []

    def test_future_schema_is_not_overwritten(self, tmp_path, mock_logger):
        """更高版本配置必须拒绝加载和覆盖。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        path = config_dir / "github_keys.json"
        original = '{"version": 99, "keys": []}'
        path.write_text(original, encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        with pytest.raises(GitHubCredentialVaultError, match="更高版本"):
            store.load()

        assert path.read_text(encoding="utf-8") == original

    def test_invalid_record_is_backed_up_and_rebuilt(
        self, tmp_path, mock_logger
    ):
        """字段值损坏时也应安全备份重建。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "github_keys.json").write_text(json.dumps({
            "version": 1,
            "default_key_id": "",
            "keys": [{
                "id": "key-a",
                "name": "坏 Key",
                "encrypted_token": "memory:v1:1",
                "token_kind": "unsupported",
            }],
        }), encoding="utf-8")
        store = GitHubKeyStore(
            config_dir, InMemorySecretVault(), logger=mock_logger)

        store.load()

        assert store.list_views() == []
        assert list(config_dir.glob("github_keys.json.corrupt-*.bak"))

    def test_default_can_be_cleared(self, key_store):
        """空字符串可清除默认 Key。"""
        created = key_store.add_key("账号", "token")
        key_store.set_default(created.id)

        key_store.set_default("")

        assert key_store.get_default_key_id() == ""

    def test_saved_schema_contains_version(self, key_store, tmp_path):
        """持久化文件包含 schema version。"""
        key_store.add_key("账号", "token")
        path = Path(tmp_path) / "config" / "github_keys.json"

        data = json.loads(path.read_text(encoding="utf-8"))

        assert data["version"] == 1
