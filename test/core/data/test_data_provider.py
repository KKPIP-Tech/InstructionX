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


# ---------------------------------------------------------------------------
# LRU 缓存
# ---------------------------------------------------------------------------

class TestLRUCache:
    def test_none_value_is_cached(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", None, DataNamespace.PRIVATE)
        # 第一次读取填充缓存
        assert p.get_plugin_data("p1", "k", DataNamespace.PRIVATE, "DEFAULT") is None
        # 第二次读取应命中缓存并仍然返回 None（不是默认值）
        assert p.get_plugin_data("p1", "k", DataNamespace.PRIVATE, "DEFAULT") is None

    def test_capacity_evicts_oldest(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p._backend._value_cache.capacity = 2
        p.set_plugin_data("p1", "k1", "v1", DataNamespace.PRIVATE)
        p.set_plugin_data("p1", "k2", "v2", DataNamespace.PRIVATE)
        p.set_plugin_data("p1", "k3", "v3", DataNamespace.PRIVATE)
        # 读取填充缓存
        p.get_plugin_data("p1", "k1", DataNamespace.PRIVATE)
        p.get_plugin_data("p1", "k2", DataNamespace.PRIVATE)
        p.get_plugin_data("p1", "k3", DataNamespace.PRIVATE)
        keys = list(p._backend._value_cache._data.keys())
        assert len(keys) == 2
        # k1 应该被淘汰
        assert ("p1", "private", "k1") not in keys

    def test_invalidation_on_write(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        p.set_plugin_data("p1", "k", "v1", DataNamespace.PRIVATE)
        p.get_plugin_data("p1", "k", DataNamespace.PRIVATE)
        assert len(p._backend._value_cache._data) == 1
        p.set_plugin_data("p1", "k", "v2", DataNamespace.PRIVATE)
        assert len(p._backend._value_cache._data) == 0


# ---------------------------------------------------------------------------
# 迁移失败回滚
# ---------------------------------------------------------------------------

class TestMigrationFailure:
    def test_migration_failure_cleans_up_db_and_keeps_json(self, tmp_path, monkeypatch):
        json_data = {
            "plugins": {
                "p1": {"type": "T", "active": False, "private": {"k": "first"}, "public": {}},
                "p2": {"type": "T", "active": False, "private": {"k": "second"}, "public": {}},
            },
            "active_instances": {}
        }
        json_file = tmp_path / "test.json"
        json_file.write_text(json.dumps(json_data), encoding="utf-8")

        from core.data.sqlite_backend import SQLiteBackend, _serialize

        def _patched_migrate(self, conn, data):
            plugins = data.get("plugins", {})
            for i, (instance_id, plugin_info) in enumerate(plugins.items()):
                if i == 1:
                    raise RuntimeError("模拟迁移中途失败")
                plugin_type = plugin_info.get("type", "")
                active = 1 if plugin_info.get("active", False) else 0
                conn.execute(
                    "INSERT INTO plugins (instance_id, plugin_type, active) VALUES (?, ?, ?);",
                    (instance_id, plugin_type, active),
                )
                private = plugin_info.get("private", {})
                for key, value in private.items():
                    value_json = _serialize(value)
                    conn.execute(
                        "INSERT INTO plugin_data (instance_id, namespace, key, value_json) VALUES (?, ?, ?, ?);",
                        (instance_id, "private", key, value_json),
                    )

        monkeypatch.setattr(SQLiteBackend, "_migrate_json_to_sqlite", _patched_migrate)

        _reset_singleton()
        with pytest.raises(DataProviderError):
            DataProvider(data_dir=str(tmp_path), data_filename="test.json")

        # data.db 应被清理
        db_file = tmp_path / "test.db"
        assert not db_file.exists()
        # 原始 json 应保留
        assert json_file.exists()


# ---------------------------------------------------------------------------
# 锁顺序
# ---------------------------------------------------------------------------

class TestNotifyLockOrder:
    def test_callback_not_under_file_lock(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("pub", "TypeA")
        callback_lock_state = []

        def callback(pid, key, old, new):
            callback_lock_state.append(p._file_lock._is_owned())

        p.subscribe("sub", "pub", "status", callback)
        p.set_plugin_data("pub", "status", "ready", DataNamespace.PUBLIC)
        assert len(callback_lock_state) == 1
        assert callback_lock_state[0] is False

    def test_callback_can_reenter_dataprovider(self, tmp_path):
        p = _provider(tmp_path)
        p.register_plugin("pub", "TypeA")
        p.register_plugin("sub", "TypeB")

        def callback(pid, key, old, new):
            # 回调中再次读取数据不应死锁
            p.get_plugin_data("pub", "status", DataNamespace.PUBLIC)

        p.subscribe("sub", "pub", "status", callback)
        p.set_plugin_data("pub", "status", "ready", DataNamespace.PUBLIC)
        # 如果死锁，上面的调用不会返回


# ---------------------------------------------------------------------------
# 并发
# ---------------------------------------------------------------------------

class TestConcurrency:
    def test_concurrent_set_get(self, tmp_path):
        import threading
        p = _provider(tmp_path)
        p.register_plugin("p1", "TypeA")
        errors = []

        def worker(start):
            try:
                for i in range(start, start + 50):
                    p.set_plugin_data("p1", f"key_{i}", i, DataNamespace.PRIVATE)
                    p.get_plugin_data("p1", f"key_{i}", DataNamespace.PRIVATE)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i * 50,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # 最终一致
        for i in range(200):
            assert p.get_plugin_data("p1", f"key_{i}", DataNamespace.PRIVATE) == i


# ---------------------------------------------------------------------------
# 资源文件
# ---------------------------------------------------------------------------

class TestAssets:
    def test_save_and_load_asset(self, tmp_path):
        p = _provider(tmp_path)
        content = b"fake image data"
        relative_path = p.save_asset("p1", "thumb.png", content)
        assert relative_path == "assets/plugins/p1/thumb.png"
        loaded = p.load_asset(relative_path)
        assert loaded == content

    def test_get_asset_path_rejects_traversal(self, tmp_path):
        p = _provider(tmp_path)
        with pytest.raises(DataProviderError):
            p.get_asset_path("assets/plugins/../secret.txt")

    def test_save_asset_rejects_path_traversal(self, tmp_path):
        """save_asset 拒绝包含 .. 的路径穿越文件名。"""
        p = _provider(tmp_path)
        with pytest.raises(DataProviderError):
            p.save_asset("p1", "../secret.txt", b"leak")

    def test_save_asset_rejects_empty_filename(self, tmp_path):
        """save_asset 拒绝空文件名。"""
        p = _provider(tmp_path)
        with pytest.raises(DataProviderError):
            p.save_asset("p1", "", b"content")


# ---------------------------------------------------------------------------
# Schema 升级
# ---------------------------------------------------------------------------

class TestSchemaUpgrade:
    def test_high_version_rejected(self, tmp_path):
        p = _provider(tmp_path)
        conn = sqlite3.connect(str(p._backend.db_file))
        conn.execute(
            "INSERT INTO db_metadata (key, value) VALUES ('schema_version', '99') "
            "ON CONFLICT(key) DO UPDATE SET value='99';"
        )
        conn.commit()
        conn.close()
        p._backend.close()

        _reset_singleton()
        with pytest.raises(DataProviderError):
            DataProvider(data_dir=str(tmp_path), data_filename="test.json")

    def test_corrupt_version_rejected(self, tmp_path):
        p = _provider(tmp_path)
        conn = sqlite3.connect(str(p._backend.db_file))
        conn.execute(
            "INSERT INTO db_metadata (key, value) VALUES ('schema_version', 'abc') "
            "ON CONFLICT(key) DO UPDATE SET value='abc';"
        )
        conn.commit()
        conn.close()
        p._backend.close()

        _reset_singleton()
        with pytest.raises(DataProviderError):
            DataProvider(data_dir=str(tmp_path), data_filename="test.json")

    def test_legacy_database_upgraded(self, tmp_path):
        # 模拟一个有核心表但无 db_metadata 的旧数据库
        p = _provider(tmp_path)
        p._backend.close()
        conn = sqlite3.connect(str(p._backend.db_file))
        conn.execute("DROP TABLE db_metadata;")
        conn.execute("INSERT INTO plugins (instance_id, plugin_type, active) VALUES ('p1', 'T', 1);")
        conn.commit()
        conn.close()

        _reset_singleton()
        p2 = DataProvider(data_dir=str(tmp_path), data_filename="test.json")
        # 应补齐 schema_version 为 1，且不丢数据
        conn = sqlite3.connect(str(p2._backend.db_file))
        cur = conn.execute("SELECT value FROM db_metadata WHERE key='schema_version';")
        assert cur.fetchone()[0] == "1"
        cur = conn.execute("SELECT value FROM db_metadata WHERE key='migrated_from';")
        assert cur.fetchone()[0] == "legacy"
        cur = conn.execute("SELECT COUNT(*) FROM plugins;")
        assert cur.fetchone()[0] == 1
        conn.close()


