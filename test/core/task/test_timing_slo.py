"""调度与协作取消的短时分位负载门禁，不涉及长稳负载。"""

import math
import threading
import time

import pytest

from core.task.background_task import BackgroundTaskManager
from core.task.cancellation import TaskPriority
from core.task.task_model import TaskStatus
from core.task.task_storage import TaskStorage


SCHEDULED_TASK_COUNT = 100
LONG_TASK_COUNT = 32
CANCELLATION_SAMPLE_COUNT = 20
SCHEDULE_P99_LIMIT_MS = 250.0
CANCELLATION_P99_LIMIT_SECONDS = 2.0


@pytest.fixture
def manager(tmp_path):
    """使用真实执行池和临时任务存储，并在测试后关闭全部资源。"""
    TaskStorage._instance = None
    TaskStorage(data_dir=str(tmp_path))
    BackgroundTaskManager._instance = None
    instance = BackgroundTaskManager()
    yield instance
    instance.shutdown()
    BackgroundTaskManager._instance = None
    TaskStorage._instance = None


def _percentile(samples, percentile=0.99):
    """使用最近秩法计算验收分位。"""
    ordered = sorted(samples)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def test_100_fast_scheduled_tasks_with_long_load_meet_p99(manager):
    """100 个快速定时任务与 32 个长期任务并存时调度 p99 不超过 250ms。"""
    release = threading.Event()
    completed = threading.Event()
    finished = []
    delays = []
    finished_lock = threading.Lock()

    def long_task():
        release.wait(timeout=10)

    def fast_task(scheduled_at):
        with finished_lock:
            delays.append((time.monotonic() - scheduled_at) * 1000)
            finished.append(1)
            if len(finished) == SCHEDULED_TASK_COUNT:
                completed.set()

    for index in range(LONG_TASK_COUNT):
        assert manager.register_long_running_task(
            "load", f"long-{index}", long_task, auto_restart=False
        )
    try:
        for index in range(SCHEDULED_TASK_COUNT):
            task_id = manager.register_scheduled_task(
                "load", f"fast-{index}", fast_task, interval=3600
            )
            task = manager._running_scheduled_tasks[task_id]
            task.next_run_monotonic = time.monotonic()
            task.args = (task.next_run_monotonic,)
            manager._execute_scheduled_task(task)
        assert completed.wait(timeout=10)
        snapshot = manager._pools.supervisor.snapshot()
        assert snapshot["schedule_delay_samples"] == SCHEDULED_TASK_COUNT
        p99 = _percentile(delays)
        print(f"scheduled_100_long_32_actual_start_p99_ms={p99:.6f}")
        assert p99 <= SCHEDULE_P99_LIMIT_MS
    finally:
        release.set()


def test_cooperative_cancellation_stop_confirmation_meets_p99(manager):
    """20 次真实协作停止的确认延迟 p99 不超过 2 秒。"""
    samples = []
    for index in range(CANCELLATION_SAMPLE_COUNT):
        started = threading.Event()

        def worker(token):
            started.set()
            while not token.is_cancelled:
                time.sleep(0.001)
            token.raise_if_cancelled()

        task_id = manager.register_cancellable_task(
            "load", f"cancel-{index}", worker, priority=TaskPriority.HIGH
        )
        assert started.wait(timeout=1)
        begin = time.perf_counter()
        result = manager.request_task_cancellation(task_id)
        assert result.accepted
        deadline = begin + CANCELLATION_P99_LIMIT_SECONDS
        while manager.get_task_status(task_id) is not TaskStatus.CANCELLED:
            assert time.perf_counter() < deadline
            time.sleep(0.001)
        samples.append(time.perf_counter() - begin)
    p99 = _percentile(samples)
    print(f"cooperative_cancel_20_p99_seconds={p99:.6f}")
    assert p99 <= CANCELLATION_P99_LIMIT_SECONDS
