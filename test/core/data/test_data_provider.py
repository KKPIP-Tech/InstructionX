"""DataProvider SQLite 后端单元测试。

注意：DataProvider 是单例，测试之间通过 _reset_singleton 隔离。
"""

import json
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from core.data import DataProvider, DataNamespace, DataProviderError


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _reset_singleton():
    """重置 DataProvider 单例，用于测试隔离。"""
    DataProvider._instance = None


def _provider(tmp_path: Path) -> DataProvider:
    """在临时目录创建一个全新的 DataProvider 实例。"""
    _reset_singleton()
    return DataProvider(data_dir=str(tmp_path), data_filename="test.json")


# ---------------------------------------------------------------------------
# 单例测试
# ---------------------------------------------------------------------------

class TestSingleton:
    def test_singleton(self, tmp_path):
        _reset_singleton()
        p1 = DataProvider(data_dir=str(tmp_path), data_filename="test.json")
        p2 = DataProvider(data_dir=str(tmp_path), data_filename="test.json")
        assert p1 is p2

    def test_db_file_derived_from_json(self, tmp_path):
        p = _provider(tmp_path)
        assert p._backend.db_file.name == "test.db"


# ---------------------------------------------------------------------------
# 插件注册/注销
# ---------------------------------------------------------------------------

class TestRegisterUnregister:
    def test_register_and_exists(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        assert p._backend.plugin_exists("p1")

    def test_register_duplicate_raises(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        with pytest.raises(DataProviderError):
            p.register_plugin("p1", "TypeA")

    def test_unregister_removes_data(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", "v", DataNamespace.PRIVATE)
        p.unregister_plugin("p1")
        assert not p._backend.plugin_exists("p1")
        with pytest.raises(DataProviderError):
            p.get_plugin_data("p1", "k", DataNamespace.PRIVATE)

    def test_unregister_nonexistent_raises(self, tmp_path):
        p = _provider(tmp_path)
        with pytest.raises(DataProviderError):
            p.unregister_plugin("notexist")


# ---------------------------------------------------------------------------
# 活跃实例
# ---------------------------------------------------------------------------

class TestActiveInstance:
    def test_set_and_get_active(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_active_instance("p1")
        assert p.get_active_instance("TypeA") == "p1"

    def test_only_one_active_per_type(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.register_plugin("p2", "TypeA")
        p.set_active_instance("p1")
        p.set_active_instance("p2")
        assert p.get_active_instance("TypeA") == "p2"


# ---------------------------------------------------------------------------
# 插件数据
# ---------------------------------------------------------------------------

class TestPluginData:
    def test_private_round_trip(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "key1", {"nested": [1, 2, 3]}, DataNamespace.PRIVATE)
        value = p.get_plugin_data("p1", "key1", DataNamespace.PRIVATE)
        assert value == {"nested": [1, 2, 3]}

    def test_default_value(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        assert p.get_plugin_data("p1", "missing", DataNamespace.PRIVATE, default="fallback") == "fallback"

    def test_external_modification_does_not_pollute(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "key1", {"a": 1}, DataNamespace.PRIVATE)
        value = p.get_plugin_data("p1", "key1", DataNamespace.PRIVATE)
        value["a"] = 999
        value2 = p.get_plugin_data("p1", "key1", DataNamespace.PRIVATE)
        assert value2 == {"a": 1}

    def test_non_serializable_raises(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        with pytest.raises(DataProviderError):
            p.set_plugin_data("p1", "key1", {"dt": __import__('datetime').datetime.now()}, DataNamespace.PRIVATE)


# ---------------------------------------------------------------------------
# Pub/Sub
# ---------------------------------------------------------------------------

class TestPubSub:
    def test_public_notify_triggers_callback(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("pub", "TypeA")
        calls = []

        def callback(pid, key, old, new):
            calls.append((pid, key, old, new))

        p.subscribe("sub", "pub", "status", callback)
        p.set_plugin_data("pub", "status", "ready", DataNamespace.PUBLIC)
        assert len(calls) == 1
        assert calls[0][3] == "ready"

    def test_private_does_not_trigger(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("pub", "TypeA")
        calls = []

        def callback(pid, key, old, new):
            calls.append((pid, key, old, new))

        p.subscribe("sub", "pub", "status", callback)
        p.set_plugin_data("pub", "status", "ready", DataNamespace.PRIVATE)
        assert len(calls) == 0

    def test_notify_false_does_not_trigger(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("pub", "TypeA")
        calls = []

        def callback(pid, key, old, new):
            calls.append((pid, key, old, new))

        p.subscribe("sub", "pub", "status", callback)
        p.set_plugin_data("pub", "status", "ready", DataNamespace.PUBLIC, notify=False)
        assert len(calls) == 0


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

class TestCache:
    def test_load_data_returns_deep_copy(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", "v", DataNamespace.PRIVATE)
        d1 = p.load_data()
        d2 = p.load_data()
        assert d1 is not d2
        d1["plugins"]["p1"]["private"]["k"] = "changed"
        assert p.get_plugin_data("p1", "k", DataNamespace.PRIVATE) == "v"

    def test_clear_cache_then_save_raises(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.clear_cache()
        with pytest.raises(DataProviderError):
            p.save_data()


# ---------------------------------------------------------------------------
# 重置
# ---------------------------------------------------------------------------

class TestResetAllData:
    def test_reset_clears_data(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", "v", DataNamespace.PRIVATE)
        p.reset_all_data()
        with pytest.raises(DataProviderError):
            p.get_plugin_data("p1", "k", DataNamespace.PRIVATE)


# ---------------------------------------------------------------------------
# 迁移
# ---------------------------------------------------------------------------

class TestMigration:
    def test_json_migrated_to_sqlite(self, tmp_path):
        json_data = {
            "plugins": {
                "old-plugin": {
                    "type": "OldType",
                    "active": True,
                    "private": {"cfg": 1},
                    "public": {"status": "ok"},
                }
            },
            "active_instances": {"OldType": "old-plugin"},
        }
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(json_data), encoding="utf-8")

        _reset_singleton()
        p = DataProvider(data_dir=str(tmp_path), data_filename="test.json")

        assert p.get_plugin_data("old-plugin", "status", DataNamespace.PUBLIC) == "ok"
        assert p.get_active_instance("OldType") == "old-plugin"
        assert p._backend.plugin_exists("old-plugin")
        # 备份文件应生成
        backups = list(tmp_path.glob("test.migrated-*.bak"))
        assert len(backups) == 1


# ---------------------------------------------------------------------------
# Schema 版本
# ---------------------------------------------------------------------------

class TestSchemaVersion:
    def test_new_database_has_version_1(self, tmp_path):
        p = _provider(tmp_path)
        conn = sqlite3.connect(str(p._backend.db_file))
        cur = conn.execute("SELECT value FROM db_metadata WHERE key='schema_version';")
        assert cur.fetchone()[0] == "1"


# ---------------------------------------------------------------------------
# 序列化兼容性
# ---------------------------------------------------------------------------

class TestSerializationCompatibility:
    def test_int_enum_key(self, tmp_path):
        from enum import IntEnum

        class K(IntEnum):
            A = 1

        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", {K.A: "value"}, DataNamespace.PRIVATE)
        value = p.get_plugin_data("p1", "k", DataNamespace.PRIVATE)
        assert value == {"1": "value"}

    def test_nan_rejected(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        with pytest.raises(DataProviderError):
            p.set_plugin_data("p1", "k", float("nan"), DataNamespace.PRIVATE)
