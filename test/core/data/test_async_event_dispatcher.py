"""异步事件分发、有界背压与资源清理测试。"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.data import DataProvider, DataNamespace
from core.data.event_dispatcher import BackpressurePolicy, EventDispatcher


def _wait_for(predicate, timeout=2):
    """按条件轮询，避免固定长睡眠造成验收抖动。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def dispatcher():
    """每个用例使用独立分发器并在结束时停止全部 worker。"""
    instance = EventDispatcher(default_queue_capacity=2)
    yield instance
    instance.close()


def test_slow_subscriber_does_not_block_publisher_or_fast_subscriber(dispatcher):
    """500ms 慢回调不阻塞发布 p99，也不阻塞另一订阅者收到全部事件。"""
    slow_calls = []
    fast_calls = []

    def slow_callback(*args):
        slow_calls.append(args[3])
        time.sleep(0.5)

    dispatcher.subscribe("slow", "pub", "status", slow_callback, queue_capacity=16)
    dispatcher.subscribe("fast", "pub", "status", lambda *args: fast_calls.append(args[3]), queue_capacity=16)
    delays = []
    for index in range(5):
        started = time.perf_counter()
        receipt = dispatcher.publish("pub", "status", index - 1, index)
        delays.append((time.perf_counter() - started) * 1000)
        assert receipt.accepted
    assert sorted(delays)[-1] <= 10
    assert _wait_for(lambda: len(fast_calls) == 5)
    assert fast_calls == list(range(5))
    stats = dispatcher.get_stats("fast")
    assert stats.delivered == 5
    assert stats.lag_ms >= 0


def test_reject_policy_reports_queue_full(dispatcher):
    """容量满时 REJECT 必须返回失败原因，不得隐式接受或无限排队。"""
    dispatcher.subscribe("sub", "pub", "key", lambda *args: time.sleep(0.1), queue_capacity=1)
    first = dispatcher.publish("pub", "key", 0, 1)
    second = dispatcher.publish("pub", "key", 1, 2)
    assert first.accepted
    assert not second.accepted
    assert second.reason == "queue_full"
    assert dispatcher.get_stats("sub").dropped == 1


def test_drop_oldest_policy_keeps_latest_event(dispatcher):
    """DROP_OLDEST 必须显式计数并交付最新值。"""
    received = []
    release = threading.Event()
    started = threading.Event()
    def blocking_callback(*args):
        started.set()
        release.wait(timeout=2)
        received.append(args[3])
    dispatcher.subscribe("sub", "pub", "key", blocking_callback, queue_capacity=1)
    dispatcher.publish("pub", "key", 0, 1, BackpressurePolicy.DROP_OLDEST)
    assert started.wait(timeout=1)
    dispatcher.publish("pub", "key", 1, 2, BackpressurePolicy.DROP_OLDEST)
    dispatcher.publish("pub", "key", 2, 3, BackpressurePolicy.DROP_OLDEST)
    release.set()
    assert _wait_for(lambda: len(received) >= 2)
    assert received[-1] == 3
    assert dispatcher.get_stats("sub").dropped >= 1


def test_coalesce_policy_merges_pending_events(dispatcher):
    """COALESCE 合并待处理事件，保留最新并统计合并数。"""
    dispatcher.subscribe("sub", "pub", "key", lambda *args: time.sleep(0.05), queue_capacity=1)
    for index in range(4):
        dispatcher.publish("pub", "key", index - 1, index, policy=BackpressurePolicy.COALESCE)
    assert _wait_for(lambda: dispatcher.get_stats("sub").delivered >= 1)
    assert dispatcher.get_stats("sub").coalesced >= 1


def test_callback_failure_is_isolated_and_counted(dispatcher):
    """回调异常不得杀死 worker 或阻断后续事件，失败数必须可观测。"""
    received = []

    def failing_callback(*args):
        received.append(args[3])
        raise RuntimeError("插件异常")

    dispatcher.subscribe("sub", "pub", "key", failing_callback)
    dispatcher.publish("pub", "key", 0, 1)
    dispatcher.publish("pub", "key", 1, 2)
    assert _wait_for(lambda: dispatcher.get_stats("sub").failed == 2)
    assert received == [1, 2]


def test_sequence_is_monotonic_and_unsubscribe_stops_delivery(dispatcher):
    """事件序号单调递增，取消订阅后邮箱关闭且不再收到事件。"""
    received = []
    subscription = dispatcher.subscribe("sub", "pub", "key", lambda *args: received.append(args[3]))
    first = dispatcher.publish("pub", "key", 0, 1)
    second = dispatcher.publish("pub", "key", 1, 2)
    assert second.event_id > first.event_id
    assert _wait_for(lambda: len(received) == 2)
    dispatcher.unsubscribe(subscription)
    dispatcher.publish("pub", "key", 2, 3)
    assert _wait_for(lambda: len(received) == 2)
    assert received == [1, 2]


def test_dataprovider_publish_async_persists_and_dispatches(tmp_path, mocker):
    """DataProvider 新 API 先持久化再异步通知，旧同步 publish 行为不变。"""
    DataProvider._instance = None
    mocker.patch("core.data.data_provider.LoggerManager", return_value=MagicMock())
    mocker.patch("core.data.sqlite_backend.LoggerManager", return_value=MagicMock())
    provider = DataProvider(data_dir=str(tmp_path), data_filename="test.json")
    provider.register_plugin("pub", "Type")
    received = []
    provider.subscribe("sub", "pub", "status", lambda *args: received.append(args[3]))
    receipt = provider.publish_async("pub", "status", "ready")
    assert receipt.accepted
    assert provider.get_plugin_data("pub", "status", DataNamespace.PUBLIC) == "ready"
    assert _wait_for(lambda: received == ["ready"])
    provider.close()
    DataProvider._instance = None
