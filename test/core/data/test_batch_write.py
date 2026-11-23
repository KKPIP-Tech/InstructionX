"""批量事务写入、分页聚合和全量缓存解耦测试。"""

import pytest

from core.data.data_provider import DataProvider, DataProviderError, DataNamespace
from core.data.sqlite_backend import SQLiteBackend, SQLiteBackendError


@pytest.fixture
def provider(tmp_path):
    DataProvider._instance = None
    instance = DataProvider(str(tmp_path), "data.json")
    instance.register_plugin("plugin-batch", "batch")
    yield instance
    instance.close()
    DataProvider._instance = None


def test_backend_batch_uses_one_transaction_without_per_key_queries(tmp_path):
    """100 键写入只有一个事务，不执行逐键 SELECT。"""
    backend = SQLiteBackend(str(tmp_path), "data.json")
    backend.ensure_database()
    backend.register_plugin("plugin-batch", "batch")
    statements = []
    backend._connect().set_trace_callback(statements.append)
    values = {f"key-{index}": {"value": index} for index in range(100)}
    backend.set_plugin_data_batch("plugin-batch", "private", values)
    normalized = [statement.strip().upper() for statement in statements]
    assert sum(statement.startswith("BEGIN IMMEDIATE") for statement in normalized) == 1
    assert sum(statement.startswith("COMMIT") for statement in normalized) == 1
    assert not any(statement.startswith("SELECT") for statement in normalized)
    assert backend.get_all_plugin_data("plugin-batch", "private") == values
    backend.close()


def test_backend_batch_serialization_failure_is_atomic(tmp_path):
    """任意值序列化失败时整批不写，原值保持不变。"""
    backend = SQLiteBackend(str(tmp_path), "data.json")
    backend.ensure_database()
    backend.register_plugin("plugin-batch", "batch")
    backend.set_plugin_data("plugin-batch", "private", "stable", "old")
    with pytest.raises(SQLiteBackendError, match="序列化"):
        backend.set_plugin_data_batch(
            "plugin-batch", "private", {"stable": "new", "bad": object()}
        )
    assert backend.get_plugin_data("plugin-batch", "private", "stable") == "old"
    assert backend.get_plugin_data("plugin-batch", "private", "bad") is None
    backend.close()


def test_backend_empty_batch_does_not_open_transaction(tmp_path):
    """空批次不启动事务也不访问数据库。"""
    backend = SQLiteBackend(str(tmp_path), "data.json")
    backend.ensure_database()
    backend.register_plugin("plugin-batch", "batch")
    statements = []
    backend._connect().set_trace_callback(statements.append)
    backend.set_plugin_data_batch("plugin-batch", "private", {})
    assert statements == []
    backend.close()


def test_data_provider_batch_notifications_and_cache_contract(provider):
    """公开批量通知保序并带旧值，正常写入不强制加载全量缓存。"""
    provider._cache = None
    provider.set_plugin_data("plugin-batch", "key", 1)
    assert provider._cache is None
    provider.set_plugin_data("plugin-batch", "public-a", 0, DataNamespace.PUBLIC, False)
    provider.set_plugin_data("plugin-batch", "public-b", 0, DataNamespace.PUBLIC, False)
    calls = []
    provider.subscribe(
        "subscriber", "plugin-batch", "public-a",
        lambda *args: calls.append(args),
    )
    provider.subscribe(
        "subscriber", "plugin-batch", "public-b",
        lambda *args: calls.append(args),
    )
    values = {"public-a": 1, "public-b": 2}
    provider.set_plugin_data_batch("plugin-batch", values, DataNamespace.PUBLIC)
    assert provider._cache is None
    assert [(call[1], call[2], call[3]) for call in calls] == [
        ("public-a", 0, 1), ("public-b", 0, 2)
    ]
    loaded = provider.load_data()
    assert loaded["plugins"]["plugin-batch"]["public"] == values
    provider.set_plugin_data_batch("plugin-batch", {"public-a": 3}, DataNamespace.PUBLIC)
    assert provider._cache["plugins"]["plugin-batch"]["public"]["public-a"] == 3


def test_pagination_and_database_count(provider):
    """分页边界、顺序、聚合计数与非法参数均符合契约。"""
    values = {f"key-{index}": index for index in range(5)}
    provider.set_plugin_data_batch("plugin-batch", values)
    page = provider.get_plugin_data_page("plugin-batch", limit=2, offset=2)
    assert page == {"key-2": 2, "key-3": 3}
    assert provider.count_plugin_data("plugin-batch") == 5
    assert provider.get_plugin_data_page("plugin-batch", limit=2, offset=5) == {}
    with pytest.raises(DataProviderError, match="limit"):
        provider.get_plugin_data_page("plugin-batch", limit=0)
    with pytest.raises(DataProviderError, match="offset"):
        provider.get_plugin_data_page("plugin-batch", offset=-1)


def test_json_backend_batch_page_and_count(tmp_path, monkeypatch):
    """应急 JSON 后端保留相同批量、分页和计数语义。"""
    monkeypatch.setenv("INSTRUCTIONX_DATAPROVIDER_BACKEND", "json")
    DataProvider._instance = None
    provider = DataProvider(str(tmp_path), "data.json")
    provider.register_plugin("plugin-json", "json")
    provider.set_plugin_data_batch("plugin-json", {"a": 1, "b": 2, "c": 3})
    assert provider.get_plugin_data_page("plugin-json", limit=1, offset=1) == {"b": 2}
    assert provider.count_plugin_data("plugin-json") == 3
    provider.close()
    DataProvider._instance = None
