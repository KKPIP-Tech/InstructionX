"""插件注册表按实际插件文件校准版本的测试。

覆盖用户绕过插件管理器手动替换插件目录后的版本、名称与 UUID 变化，
同时验证已有 GitHub 来源信息不会因重新校准而丢失。
"""

import json
from pathlib import Path

from core.plugin.plugin_registry import PluginRegistry


def _write_descriptor(
    plugin_dir: Path,
    *,
    descriptor_id: str = "manual-plugin",
    name: str = "Manual Plugin",
    version: str = "release.2.0.0",
) -> None:
    """写入指定版本的最小插件描述文件。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "IXPlugin.json").write_text(
        json.dumps({
            "id": descriptor_id,
            "name": name,
            "version": version,
        }),
        encoding="utf-8",
    )


class TestPluginRegistryReconcile:
    """验证手动替换插件后的注册表校准行为。"""

    def test_existing_record_version_is_updated_from_descriptor(
        self, tmp_path
    ):
        """已有记录应更新版本与名称，并保留来源和 Key 绑定。"""
        registry = PluginRegistry(tmp_path / "config")
        registry.upsert(
            "plugin-uuid",
            descriptor_id="manual-plugin",
            name="旧名称",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="github",
            source_url="https://github.com/example/manual-plugin",
            source_visibility="private",
            source_key_id="key-uuid",
        )
        plugin_dir = tmp_path / "manual-plugin"
        _write_descriptor(
            plugin_dir,
            name="新名称",
            version="release.2.3.4",
        )

        changed = registry.reconcile(
            [("plugin-uuid", "thirdparty", plugin_dir)])

        record = registry.get("plugin-uuid")
        assert changed == 1
        assert record["name"] == "新名称"
        assert record["version"] == "release.2.3.4"
        assert record["source_type"] == "github"
        assert record["source_url"].endswith("/manual-plugin")
        assert record["source_visibility"] == "private"
        assert record["source_key_id"] == "key-uuid"

    def test_unchanged_record_is_not_reported_as_modified(self, tmp_path):
        """描述文件未变化时不重复写入注册表。"""
        registry = PluginRegistry(tmp_path / "config")
        plugin_dir = tmp_path / "manual-plugin"
        _write_descriptor(plugin_dir)
        registry.upsert(
            "plugin-uuid",
            descriptor_id="manual-plugin",
            name="Manual Plugin",
            scope="thirdparty",
            version="release.2.0.0",
        )

        changed = registry.reconcile(
            [("plugin-uuid", "thirdparty", plugin_dir)])

        assert changed == 0

    def test_changed_uuid_removes_stale_record_and_keeps_source(
        self, tmp_path
    ):
        """手动替换导致 UUID 文件丢失时，应清理旧记录并继承来源绑定。"""
        registry = PluginRegistry(tmp_path / "config")
        registry.upsert(
            "old-uuid",
            descriptor_id="manual-plugin",
            name="Manual Plugin",
            scope="thirdparty",
            version="release.1.0.0",
            source_type="github",
            source_url="https://github.com/example/manual-plugin",
            source_visibility="private",
            source_key_id="key-uuid",
        )
        plugin_dir = tmp_path / "manual-plugin"
        _write_descriptor(plugin_dir, version="release.3.0.0")

        changed = registry.reconcile(
            [("new-uuid", "thirdparty", plugin_dir)])

        assert changed == 1
        assert registry.get("old-uuid") is None
        new_record = registry.get("new-uuid")
        assert new_record["version"] == "release.3.0.0"
        assert new_record["source_url"].endswith("/manual-plugin")
        assert new_record["source_key_id"] == "key-uuid"

    def test_missing_descriptor_does_not_change_registry(self, tmp_path):
        """没有 IXPlugin.json 的目录不应产生注册表记录。"""
        registry = PluginRegistry(tmp_path / "config")
        plugin_dir = tmp_path / "legacy-plugin"
        plugin_dir.mkdir()

        changed = registry.reconcile(
            [("legacy-uuid", "official", plugin_dir)])

        assert changed == 0
        assert registry.get("legacy-uuid") is None
