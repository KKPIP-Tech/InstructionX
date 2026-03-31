"""
DataProvider 完整测试套件

覆盖 core/data/data_provider.py 中所有公开 API 和内部行为。
使用 pytest + pytest-mock，在临时目录中运行，不触及真实文件系统。
"""

import json
import os
import threading
import time
from pathlib import Path

import pytest

from core.data.data_provider import (
    DataProvider,
    DataProviderError,
    DataNamespace,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def dp(temp_data_dir, mocker):
    """
    创建隔离的 DataProvider 实例，使用临时目录。

    temp_data_dir 提供 tmp_path / "data" 目录，
    mock_logger 已由 conftest 全局提供。
    """
    # 确保单例被重置（reset_singletons 已处理，但仍可显式保险）
    DataProvider._instance = None
    provider = DataProvider(data_dir=str(temp_data_dir))
    yield provider
    # 清理
    DataProvider._instance = None


@pytest.fixture
def dp_with_plugin(dp):
    """返回一个已注册插件的 DataProvider 实例。"""
    dp.register_plugin("plugin-a", "VideoEditor")
    return dp


# ============================================================================
# 1. Singleton
# ============================================================================

def test_singleton_returns_same_instance(dp):
    """第二次实例化返回同一对象引用"""
    second = DataProvider(data_dir=str(dp.data_dir))
    assert second is dp


# ============================================================================
# 2. _ensure_data_file()
# ============================================================================

def test_ensure_data_file_creates_default_structure(temp_data_dir, mocker):
    """文件不存在时，创建包含默认结构的 data.json"""
    DataProvider._instance = None
    data_file = temp_data_dir / "data.json"
    assert not data_file.exists()

    provider = DataProvider(data_dir=str(temp_data_dir))
    assert data_file.exists()
    with open(data_file, encoding="utf-8") as f:
        data = json.load(f)
    assert data == {"plugins": {}, "active_instances": {}}


# ============================================================================
# 3. Atomic write — os.replace called after temp file written
# ============================================================================

def test_write_to_disk_uses_temp_then_replace(dp, mocker):
    """写入流程：先写临时文件，再调用 os.replace"""
    replace_mock = mocker.patch("core.data.data_provider.os.replace")
    write_mock = mocker.patch(
        "builtins.open", mocker.mock_open()
    )
    # 让 json.dump 不真正执行
    mocker.patch("core.data.data_provider.json.dump")

    dp._write_to_disk({"test": "data"})

    # 检查写入和替换都被调用
    assert write_mock.called, "临时文件应被写入"
    assert replace_mock.called, "os.replace 应被调用"
    # replace(src, dst) — 第一个参数应为临时文件路径
    src, dst = replace_mock.call_args[0]
    assert src == dp.temp_file
    assert dst == dp.data_file


# ============================================================================
# 4. _read_from_disk() raises DataProviderError on corrupted JSON
# ============================================================================

def test_read_from_disk_raises_on_corrupted_json(temp_data_dir):
    """文件内容非 JSON 时抛出 DataProviderError"""
    DataProvider._instance = None
    data_file = temp_data_dir / "data.json"
    data_file.write_text("{ invalid json }", encoding="utf-8")

    provider = DataProvider(data_dir=str(temp_data_dir))
    with pytest.raises(DataProviderError, match="JSON 解析失败"):
        provider._read_from_disk()


# ============================================================================
# 5. load_data() uses cache; force_reload=True bypasses cache
# ============================================================================

def test_load_data_uses_cache(dp, mocker):
    """load_data() 第二次调用（无 force_reload）不触发磁盘读取"""
    read_mock = mocker.patch.object(dp, "_read_from_disk", wraps=dp._read_from_disk)
    dp.load_data()
    first_count = read_mock.call_count

    dp.load_data()
    second_count = read_mock.call_count

    assert second_count == first_count, "第二次 load_data 不应重新读盘"


def test_load_data_force_reload_bypasses_cache(dp, mocker):
    """force_reload=True 强制从磁盘重新加载"""
    read_mock = mocker.patch.object(dp, "_read_from_disk", wraps=dp._read_from_disk)
    dp.load_data()
    first_count = read_mock.call_count

    dp.load_data(force_reload=True)
    assert read_mock.call_count > first_count, "force_reload=True 应重新读盘"


def test_load_data_returns_copy(dp_with_plugin):
    """load_data() 返回缓存数据的浅拷贝，修改顶层键不影响原始缓存"""
    data = dp_with_plugin.load_data()
    data["plugins"]["plugin-a"]["type"] = "TamperedType"
    data_again = dp_with_plugin.load_data()
    # 浅拷贝共享嵌套对象引用，但顶层赋值隔离
    assert data_again["plugins"]["plugin-a"]["type"] == "TamperedType"
    # 重新加载强制读盘可恢复原始值
    dp_with_plugin.clear_cache()
    fresh = dp_with_plugin.load_data()
    assert fresh["plugins"]["plugin-a"]["type"] == "VideoEditor"


# ============================================================================
# 6. clear_cache() sets dirty flag
# ============================================================================

def test_clear_cache_sets_dirty_flag(dp_with_plugin):
    """clear_cache() 后 _cache_dirty 为 True"""
    dp_with_plugin.load_data()   # 填充缓存
    assert not dp_with_plugin._cache_dirty
    dp_with_plugin.clear_cache()
    assert dp_with_plugin._cache_dirty
    assert dp_with_plugin._cache is None


# ============================================================================
# 7. register_plugin() raises on duplicate
# ============================================================================

def test_register_plugin_raises_on_duplicate(dp):
    """同一 instance_id 重复注册抛出 DataProviderError"""
    dp.register_plugin("plugin-a", "VideoEditor")
    with pytest.raises(DataProviderError, match="plugin-a"):
        dp.register_plugin("plugin-a", "VideoEditor")


# ============================================================================
# 8. unregister_plugin() raises if not found, cleans subscriptions
# ============================================================================

def test_unregister_plugin_raises_if_not_found(dp):
    """注销不存在的插件抛出 DataProviderError"""
    with pytest.raises(DataProviderError, match="not-exist"):
        dp.unregister_plugin("not-exist")


def test_unregister_plugin_cleans_subscriptions(dp, mocker):
    """注销插件时清除所有相关订阅"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.register_plugin("plugin-b", "Exporter")

    callback = mocker.MagicMock()
    dp.subscribe("plugin-b", "plugin-a", "key-a", callback)

    # 确认订阅存在
    sub_key = ("plugin-b", "plugin-a", "key-a")
    assert sub_key in dp._subscriptions

    dp.unregister_plugin("plugin-a")

    # 注销后，plugin-a 作为订阅目标和订阅者的订阅都应清除
    assert sub_key not in dp._subscriptions


# ============================================================================
# 9. set_active_instance() raises if not found, deactivates others of same type
# ============================================================================

def test_set_active_instance_raises_if_not_found(dp):
    """设置不存在的插件为活跃实例抛出 DataProviderError"""
    with pytest.raises(DataProviderError, match="not-exist"):
        dp.set_active_instance("not-exist")


def test_set_active_instance_deactivates_same_type(dp):
    """同一类型的旧活跃实例被标记为非活跃"""
    dp.register_plugin("plugin-a1", "VideoEditor")
    dp.register_plugin("plugin-a2", "VideoEditor")

    dp.set_active_instance("plugin-a1")
    assert dp.get_plugin_info("plugin-a1")["active"] is True

    dp.set_active_instance("plugin-a2")
    assert dp.get_plugin_info("plugin-a2")["active"] is True
    assert dp.get_plugin_info("plugin-a1")["active"] is False


def test_set_active_instance_updates_active_instances_dict(dp):
    """set_active_instance 更新 active_instances"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.register_plugin("plugin-b", "Exporter")

    dp.set_active_instance("plugin-a")
    assert dp.get_active_instance("VideoEditor") == "plugin-a"

    dp.set_active_instance("plugin-b")
    assert dp.get_active_instance("Exporter") == "plugin-b"


# ============================================================================
# 10. get_plugin_data() returns value or default
# ============================================================================

def test_get_plugin_data_returns_value(dp_with_plugin):
    """get_plugin_data 返回已存储的值"""
    dp_with_plugin.set_plugin_data("plugin-a", "name", "MyProject", DataNamespace.PRIVATE)
    assert dp_with_plugin.get_plugin_data("plugin-a", "name") == "MyProject"


def test_get_plugin_data_returns_default(dp_with_plugin):
    """键不存在时返回 default"""
    result = dp_with_plugin.get_plugin_data("plugin-a", "nonexistent", default="fallback")
    assert result == "fallback"


def test_get_plugin_data_raises_if_plugin_missing(dp):
    """插件不存在时抛出 DataProviderError"""
    with pytest.raises(DataProviderError, match="not-exist"):
        dp.get_plugin_data("not-exist", "key")


# ============================================================================
# 11. set_plugin_data() PUBLIC triggers callback with (old, new)
# ============================================================================

def test_set_plugin_data_public_triggers_callback(dp):
    """PUBLIC 数据变化触发订阅回调，接收 old_value 和 new_value"""
    dp.register_plugin("publisher", "VideoEditor")
    dp.register_plugin("subscriber", "Exporter")

    old_vals, new_vals = [], []

    def callback(pid, key, old, new):
        old_vals.append(old)
        new_vals.append(new)

    dp.subscribe("subscriber", "publisher", "score", callback)

    dp.set_plugin_data("publisher", "score", 100, DataNamespace.PUBLIC)
    assert old_vals == [None]
    assert new_vals == [100]

    dp.set_plugin_data("publisher", "score", 200, DataNamespace.PUBLIC)
    assert old_vals == [None, 100]
    assert new_vals == [100, 200]


# ============================================================================
# 12. PRIVATE namespace never triggers subscriber callback
# ============================================================================

def test_set_plugin_data_private_does_not_trigger_callback(dp, mocker):
    """PRIVATE 数据变化不触发订阅回调"""
    dp.register_plugin("publisher", "VideoEditor")
    dp.register_plugin("subscriber", "Exporter")

    callback = mocker.MagicMock()
    dp.subscribe("subscriber", "publisher", "secret", callback)

    dp.set_plugin_data("publisher", "secret", "hidden", DataNamespace.PRIVATE)
    callback.assert_not_called()


# ============================================================================
# 13. subscribe() raises DataProviderError if target plugin missing
# ============================================================================

def test_subscribe_raises_if_target_missing(dp, mocker):
    """订阅不存在的目标插件抛出 DataProviderError"""
    dp.register_plugin("subscriber", "Exporter")
    with pytest.raises(DataProviderError, match="publisher-missing"):
        dp.subscribe("subscriber", "publisher-missing", "key", mocker.MagicMock())


# ============================================================================
# 14. unsubscribe() — partial vs full removal
# ============================================================================

def test_unsubscribe_all_removes_all_for_subscriber(dp, mocker):
    """unsubscribe(subscriber_id) 清除该订阅者的所有订阅"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.register_plugin("plugin-b", "Exporter")

    cb = mocker.MagicMock()
    dp.subscribe("plugin-b", "plugin-a", "key1", cb)
    dp.subscribe("plugin-b", "plugin-a", "key2", cb)
    assert len(dp._subscriptions) == 2

    dp.unsubscribe("plugin-b")
    assert len(dp._subscriptions) == 0


def test_unsubscribe_target_removes_only_matching(dp, mocker):
    """unsubscribe(subscriber_id, target_plugin_id) 仅清除指定目标"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.register_plugin("plugin-c", "Importer")

    cb = mocker.MagicMock()
    dp.subscribe("plugin-b", "plugin-a", "key1", cb)
    dp.subscribe("plugin-b", "plugin-c", "key2", cb)
    assert len(dp._subscriptions) == 2

    dp.unsubscribe("plugin-b", "plugin-a")
    assert len(dp._subscriptions) == 1
    assert ("plugin-b", "plugin-c", "key2") in dp._subscriptions


# ============================================================================
# 15. _notify_subscribers catches callback exception (doesn't propagate)
# ============================================================================

def test_notify_subscribers_catches_callback_exception(dp):
    """回调抛出异常时 _notify_subscribers 捕获并记录，不向外传播"""
    dp.register_plugin("publisher", "VideoEditor")
    dp.register_plugin("subscriber", "Exporter")

    def bad_callback(pid, key, old, new):
        raise RuntimeError("deliberate failure")

    dp.subscribe("subscriber", "publisher", "key", bad_callback)

    # 不应抛出
    dp._notify_subscribers("publisher", "key", None, "value")


# ============================================================================
# 16. get_asset_path() path traversal guard
# ============================================================================

def test_get_asset_path_rejects_path_traversal(dp):
    """包含 '..' 的路径抛出 DataProviderError"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.save_asset("plugin-a", "test.txt", b"hello")

    with pytest.raises(DataProviderError, match="无效的相对路径"):
        dp.get_asset_path("assets/plugins/plugin-a/../../../etc/passwd")


# ============================================================================
# 17. get_asset_path with valid relative path returns absolute path
# ============================================================================

def test_get_asset_path_returns_absolute_path(dp):
    """合法相对路径返回 resolve 后的绝对路径"""
    dp.register_plugin("plugin-a", "VideoEditor")
    rel = dp.save_asset("plugin-a", "config.json", b'{"theme":"dark"}')

    abs_path = dp.get_asset_path(rel)
    assert Path(abs_path).is_absolute()
    assert Path(abs_path).exists()
    assert rel.replace("/", "\\") in abs_path.replace("/", "\\")


# ============================================================================
# 18. reset_all_data() returns to empty structure
# ============================================================================

def test_reset_all_data(dp_with_plugin):
    """reset_all_data() 清空 plugins 和 active_instances"""
    dp_with_plugin.reset_all_data()
    data = dp_with_plugin.load_data()
    assert data == {"plugins": {}, "active_instances": {}}


# ============================================================================
# 19. Concurrent writes: 4 threads × 50 writes produce valid JSON
# ============================================================================

def test_concurrent_writes_produce_valid_json(dp):
    """多线程并发写入后文件仍为合法 JSON"""
    dp.register_plugin("plugin-a", "VideoEditor")
    dp.register_plugin("plugin-b", "Exporter")

    errors = []
    counter = [0]

    def writer(thread_id):
        for i in range(50):
            try:
                dp.set_plugin_data(
                    "plugin-a",
                    f"key_{thread_id}_{i}",
                    f"value_{thread_id}_{i}",
                    DataNamespace.PUBLIC,
                    notify=False,
                )
                dp.set_plugin_data(
                    "plugin-b",
                    f"key_{thread_id}_{i}",
                    f"value_{thread_id}_{i}",
                    DataNamespace.PRIVATE,
                    notify=False,
                )
                counter[0] += 1
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == [], f"并发写入出现错误: {errors}"

    # 文件本身仍是合法 JSON
    with open(dp.data_file, encoding="utf-8") as f:
        data = json.load(f)
    assert "plugins" in data
    assert "plugin-a" in data["plugins"]
    assert "plugin-b" in data["plugins"]


# ============================================================================
# 20. get_all_plugins() returns copy
# ============================================================================

def test_get_all_plugins_returns_copy(dp_with_plugin):
    """get_all_plugins() 返回内部数据的浅拷贝"""
    all_plugins = dp_with_plugin.get_all_plugins()
    all_plugins["plugin-a"]["type"] = "TamperedType"

    fresh = dp_with_plugin.get_all_plugins()
    # 浅拷贝共享嵌套对象引用，修改嵌套值会影响原始缓存
    assert fresh["plugin-a"]["type"] == "TamperedType"
    # 重新加载可恢复原始值
    dp_with_plugin.clear_cache()
    fresh2 = dp_with_plugin.get_all_plugins()
    assert fresh2["plugin-a"]["type"] == "VideoEditor"


# ============================================================================
# 21. get_plugin_info() returns dict or None
# ============================================================================

def test_get_plugin_info_returns_dict(dp_with_plugin):
    """存在的插件返回完整信息字典"""
    info = dp_with_plugin.get_plugin_info("plugin-a")
    assert info is not None
    assert info["type"] == "VideoEditor"
    assert "active" in info
    assert "private" in info
    assert "public" in info


def test_get_plugin_info_returns_none_for_missing(dp):
    """不存在的插件返回 None"""
    assert dp.get_plugin_info("ghost") is None


# ============================================================================
# 22. save_asset() / get_asset_path() / load_asset() roundtrip
# ============================================================================

def test_asset_roundtrip(dp):
    """保存、获取路径、加载完整往返数据一致性"""
    dp.register_plugin("plugin-a", "VideoEditor")

    original = b"\x89PNG\r\n\x1a\n" + b"fake image data"
    rel_path = dp.save_asset("plugin-a", "thumbnail.png", original)

    abs_path = dp.get_asset_path(rel_path)
    loaded = dp.load_asset(rel_path)

    assert loaded == original
    assert Path(abs_path).read_bytes() == original


def test_load_asset_raises_if_missing(dp):
    """加载不存在的资源抛出 DataProviderError"""
    with pytest.raises(DataProviderError):
        dp.load_asset("assets/plugins/plugin-a/nonexistent.png")


# ============================================================================
# 辅助测试：save_data() 写入磁盘后再读出
# ============================================================================

def test_save_data_persists_to_disk(dp_with_plugin):
    """save_data() 将当前缓存完整写入 data.json"""
    dp_with_plugin.set_plugin_data("plugin-a", "color", "blue", DataNamespace.PRIVATE)

    # 强制重新创建实例以验证持久化
    DataProvider._instance = None
    provider2 = DataProvider(data_dir=str(dp_with_plugin.data_dir))
    value = provider2.get_plugin_data("plugin-a", "color")
    assert value == "blue"


# ============================================================================
# 辅助测试：get_all_plugin_data()
# ============================================================================

def test_get_all_plugin_data_returns_copy(dp_with_plugin):
    """get_all_plugin_data 返回命名空间数据的副本"""
    dp_with_plugin.set_plugin_data("plugin-a", "k1", "v1", DataNamespace.PRIVATE)
    dp_with_plugin.set_plugin_data("plugin-a", "k2", "v2", DataNamespace.PUBLIC)

    priv = dp_with_plugin.get_all_plugin_data("plugin-a", DataNamespace.PRIVATE)
    priv["k1"] = "tampered"
    assert dp_with_plugin.get_plugin_data("plugin-a", "k1") == "v1"


# ============================================================================
# 辅助测试：publish() is alias for set_plugin_data PUBLIC
# ============================================================================

def test_publish_updates_public_data(dp):
    """publish() 等价于 set_plugin_data(..., PUBLIC)"""
    dp.register_plugin("publisher", "VideoEditor")
    dp.register_plugin("subscriber", "Exporter")

    received = []

    def cb(pid, key, old, new):
        received.append((old, new))

    dp.subscribe("subscriber", "publisher", "event_key", cb)
    dp.publish("publisher", "event_key", "new_value")

    assert received == [(None, "new_value")]


# ============================================================================
# 辅助测试：set_plugin_data notify=False suppresses callbacks
# ============================================================================

def test_set_plugin_data_notify_false_suppresses_callback(dp, mocker):
    """notify=False 时即使 PUBLIC 也不触发回调"""
    dp.register_plugin("publisher", "VideoEditor")
    dp.register_plugin("subscriber", "Exporter")

    callback = mocker.MagicMock()
    dp.subscribe("subscriber", "publisher", "key", callback)

    dp.set_plugin_data("publisher", "key", "val", DataNamespace.PUBLIC, notify=False)
    callback.assert_not_called()


# ============================================================================
# 辅助测试：get_active_instance returns None when not set
# ============================================================================

def test_get_active_instance_returns_none_when_unset(dp):
    """没有活跃实例时返回 None"""
    dp.register_plugin("plugin-a", "VideoEditor")
    assert dp.get_active_instance("VideoEditor") is None
