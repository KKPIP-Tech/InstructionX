"""插件注册表 GitHub 来源绑定与 v2 迁移测试。"""

import json
from pathlib import Path

import pytest

from core.plugin.plugin_registry import (
    PluginRegistry,
    SOURCE_VISIBILITY_PRIVATE,
    SOURCE_VISIBILITY_PUBLIC,
    SOURCE_VISIBILITY_UNKNOWN,
)


def _registry(config_dir: Path, mock_logger, mocker) -> PluginRegistry:
    """创建注入测试日志器的插件注册表。"""
    mocker.patch(
        "core.plugin.plugin_registry.LoggerManager",
        return_value=mock_logger,
    )
    return PluginRegistry(config_dir)


def _v1_data() -> dict:
    """构造包含一个旧记录的 v1 注册表。"""
    return {
        "version": 1,
        "plugins": {
            "uuid-1": {
                "descriptor_id": "plugin-one",
                "name": "插件一",
                "scope": "thirdparty",
                "version": "release.1.0.0",
                "installed_at": "2026-01-01T00:00:00+00:00",
                "source_type": "github",
                "source_url": "https://github.com/owner/repo",
                "source_path": "",
            }
        },
    }


class TestRegistryMigration:
    """验证旧注册表无损迁移。"""

    def test_v1_record_gets_unknown_binding(
        self, tmp_path, mock_logger, mocker
    ):
        """旧记录补 unknown 与空 Key ID。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "plugin_registry.json"
        config_file.write_text(
            json.dumps(_v1_data(), ensure_ascii=False),
            encoding="utf-8",
        )

        registry = _registry(config_dir, mock_logger, mocker)
        record = registry.get("uuid-1")

        assert record["source_visibility"] == SOURCE_VISIBILITY_UNKNOWN
        assert record["source_key_id"] == ""

    def test_migration_writes_v2_and_backup(
        self, tmp_path, mock_logger, mocker
    ):
        """迁移写回 v2 并保留一次备份。"""
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        config_file = config_dir / "plugin_registry.json"
        config_file.write_text(json.dumps(_v1_data()), encoding="utf-8")

        registry = _registry(config_dir, mock_logger, mocker)
        registry.get("uuid-1")

        data = json.loads(config_file.read_text(encoding="utf-8"))
        assert data["version"] == 2
        assert (config_dir / "plugin_registry.json.migrated-v1.bak").exists()

    def test_existing_v2_does_not_create_backup(
        self, tmp_path, mock_logger, mocker
    ):
        """已经是 v2 的文件不应重复迁移。"""
        data = _v1_data()
        data["version"] = 2
        data["plugins"]["uuid-1"].update(
            source_visibility="unknown", source_key_id="")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "plugin_registry.json").write_text(
            json.dumps(data), encoding="utf-8")

        registry = _registry(config_dir, mock_logger, mocker)
        registry.get("uuid-1")

        assert not list(config_dir.glob("*.migrated-v1.bak"))


class TestSourceBinding:
    """验证私有来源绑定更新语义。"""

    def _create_registry(self, tmp_path, mock_logger, mocker) -> PluginRegistry:
        """创建包含一条 v2 记录的注册表。"""
        registry = _registry(tmp_path / "config", mock_logger, mocker)
        registry.upsert(
            "uuid-1",
            descriptor_id="plugin-one",
            name="插件一",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="github",
            source_url="https://github.com/owner/private",
            source_visibility=SOURCE_VISIBILITY_PRIVATE,
            source_key_id="key-a",
        )
        return registry

    def test_upsert_persists_private_binding(
        self, tmp_path, mock_logger, mocker
    ):
        """安装登记必须保存可见性和 Key ID。"""
        registry = self._create_registry(tmp_path, mock_logger, mocker)

        record = registry.get("uuid-1")

        assert record["source_visibility"] == SOURCE_VISIBILITY_PRIVATE
        assert record["source_key_id"] == "key-a"

    def test_rebind_replaces_only_key_id(
        self, tmp_path, mock_logger, mocker
    ):
        """重新绑定应保留版本和来源 URL。"""
        registry = self._create_registry(tmp_path, mock_logger, mocker)

        changed = registry.set_source_binding(
            "uuid-1",
            source_visibility=SOURCE_VISIBILITY_PRIVATE,
            source_key_id="key-b",
        )
        record = registry.get("uuid-1")

        assert changed is True
        assert record["source_key_id"] == "key-b"
        assert record["version"] == "release.1.0.0"
        assert record["source_url"].endswith("/private")

    def test_clear_binding_marks_unknown(
        self, tmp_path, mock_logger, mocker
    ):
        """清除绑定后不得伪造公共状态。"""
        registry = self._create_registry(tmp_path, mock_logger, mocker)

        registry.clear_source_binding("uuid-1")
        record = registry.get("uuid-1")

        assert record["source_visibility"] == SOURCE_VISIBILITY_UNKNOWN
        assert record["source_key_id"] == ""

    def test_public_source_has_no_key(
        self, tmp_path, mock_logger, mocker
    ):
        """公共来源保存 public 和空 Key。"""
        registry = _registry(tmp_path / "config", mock_logger, mocker)
        registry.upsert(
            "uuid-public",
            descriptor_id="public-plugin",
            name="公共插件",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="github",
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
        )

        record = registry.get("uuid-public")

        assert record["source_visibility"] == SOURCE_VISIBILITY_PUBLIC
        assert record["source_key_id"] == ""

    def test_invalid_visibility_is_rejected(
        self, tmp_path, mock_logger, mocker
    ):
        """非法可见性值必须拒绝。"""
        registry = self._create_registry(tmp_path, mock_logger, mocker)

        with pytest.raises(ValueError, match="不支持"):
            registry.set_source_binding(
                "uuid-1",
                source_visibility="secret",
                source_key_id="key-b",
            )

    def test_missing_plugin_is_not_created(
        self, tmp_path, mock_logger, mocker
    ):
        """绑定不存在的插件不得创建记录。"""
        registry = _registry(tmp_path / "config", mock_logger, mocker)

        changed = registry.set_source_binding(
            "missing",
            source_visibility=SOURCE_VISIBILITY_PRIVATE,
            source_key_id="key-a",
        )

        assert changed is False
        assert registry.get("missing") is None

    def test_failed_save_restores_old_binding(
        self, tmp_path, mock_logger, mocker
    ):
        """绑定写盘失败必须恢复内存旧值。"""
        registry = self._create_registry(tmp_path, mock_logger, mocker)
        mocker.patch.object(registry, "_save", return_value=False)

        changed = registry.set_source_binding(
            "uuid-1",
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
            source_key_id="",
        )
        record = registry.get("uuid-1")

        assert changed is False
        assert record["source_visibility"] == SOURCE_VISIBILITY_PRIVATE
        assert record["source_key_id"] == "key-a"
