"""执行池隔离、有界背压与定时任务重入测试。"""

import threading
import time

import pytest

from core.task.background_task import BackgroundTaskManager
from core.task.cancellation import QueueFullError, ScheduledOverlapPolicy, TaskPriority
from core.task.executor_pools import BoundedExecutor
from core.task.supervisor import TaskSupervisor
from core.task.task_model import BackgroundTask, ScheduledTask
from core.task.task_storage import TaskStorage


@pytest.fixture
def manager(tmp_path):
    """使用真实线程池和临时任务存储，测试后协作关闭。"""
    TaskStorage._instance = None
    TaskStorage(data_dir=str(tmp_path))
    BackgroundTaskManager._instance = None
    instance = BackgroundTaskManager()
    yield instance
    instance.shutdown()
    BackgroundTaskManager._instance = None
    TaskStorage._instance = None


def _percentile(samples, percentile=0.99):
    """按最近秩计算验收延迟分位。"""
    import math
    values = sorted(samples)
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def test_32_long_tasks_do_not_starve_high_or_normal_tasks(manager):
    """32 个长期任务占满长期池时，高优任务 p99 派发仍小于 100ms。"""
    release = threading.Event()
    started = [threading.Event() for _ in range(32)]

    def long_task(index):
        started[index].set()
        release.wait(timeout=5)

    for index in range(32):
        assert manager.register_long_running_task(
            "load", f"long-{index}", long_task, args=(index,), auto_restart=False
        )
    assert all(event.wait(timeout=2) for event in started)

    delays = []
    high_started = []
    for _ in range(5):
        event = threading.Event()
        begin = time.perf_counter()
        assert manager.register_priority_task(
            "load", "urgent", event.set, priority=TaskPriority.HIGH
        )
        assert event.wait(timeout=1)
        high_started.append(event)
        delays.append((time.perf_counter() - begin) * 1000)
    assert _percentile(delays) <= 100

    normal_finished = threading.Event()
    assert manager.register_async_task("load", "normal", normal_finished.set)
    assert normal_finished.wait(timeout=1)
    release.set()


def test_single_plugin_async_quota_is_enforced(manager):
    """单插件短任务达到配额后，新任务应失败返回且不得进入运行表。"""
    for index in range(manager.MAX_ASYNC_TASKS_PER_PLUGIN):
        task = BackgroundTask(plugin_id="crowded", name=f"queued-{index}")
        manager._running_tasks[task.task_id] = task
    task_id = manager.register_async_task("crowded", "overflow", lambda: None)
    assert task_id is None
    assert all(
        task.plugin_id == "crowded"
        for task in manager._running_tasks.values()
    )
    other_id = manager.register_async_task("other", "allowed", lambda: None)
    assert other_id is not None


def test_bounded_executor_rejects_when_capacity_exhausted():
    """运行与排队总量达到容量后必须返回明确 QueueFullError。"""
    supervisor = TaskSupervisor()
    executor = BoundedExecutor("test-pool", 1, 2, supervisor)
    release = threading.Event()
    started = threading.Event()

    def blocking():
        started.set()
        release.wait(timeout=2)

    executor.submit(blocking)
    executor.submit(blocking)
    assert started.wait(timeout=1)
    with pytest.raises(QueueFullError, match="容量 2"):
        executor.submit(blocking)
    assert supervisor.snapshot()["rejected"]["test-pool"] == 1
    release.set()
    executor.shutdown(wait=True)


def test_scheduled_queue_one_bounds_slow_task_backlog(manager):
    """慢定时任务重入最多保留一个待执行批次，不得无限排队。"""
    release_first = threading.Event()
    release_second = threading.Event()
    first_started = threading.Event()
    second_started = threading.Event()
    calls = []

    def slow_task():
        calls.append(1)
        if len(calls) == 1:
            first_started.set()
            release_first.wait(timeout=2)
        else:
            second_started.set()
            release_second.wait(timeout=2)

    task = ScheduledTask(plugin_id="p", name="slow", func=slow_task, interval=3600)
    manager._execute_scheduled_task(task, overlap_policy=ScheduledOverlapPolicy.QUEUE_ONE)
    assert first_started.wait(timeout=1)
    for _ in range(5):
        manager._execute_scheduled_task(task, overlap_policy=ScheduledOverlapPolicy.QUEUE_ONE)
    assert len(calls) == 1
    release_first.set()
    assert second_started.wait(timeout=1)
    release_second.set()
    deadline = time.monotonic() + 2
    while len(calls) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert len(calls) == 2


def test_scheduled_skip_and_monotonic_delay_metric(manager):
    """SKIP 不保留重入批次，调度使用 monotonic 并记录延迟。"""
    release = threading.Event()
    started = threading.Event()
    calls = []

    def slow_task():
        calls.append(1)
        started.set()
        release.wait(timeout=2)

    task = ScheduledTask(plugin_id="p", name="skip", func=slow_task, interval=3600)
    task.calculate_next_run()
    assert task.next_run_monotonic is not None
    manager._execute_scheduled_task(task, overlap_policy=ScheduledOverlapPolicy.SKIP)
    assert started.wait(timeout=1)
    for _ in range(3):
        manager._execute_scheduled_task(task, overlap_policy=ScheduledOverlapPolicy.SKIP)
    release.set()
    deadline = time.monotonic() + 1
    while manager._pools.supervisor.snapshot()["completed"].get("normal", 0) < 1:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert len(calls) == 1
    assert manager._pools.supervisor.snapshot()["schedule_delay_samples"] >= 1
