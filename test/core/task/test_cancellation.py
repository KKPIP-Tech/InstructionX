"""协作式取消与旧状态取消兼容性测试。"""

import threading
import time

import pytest

from core.task.background_task import BackgroundTaskManager
from core.task.cancellation import CancellationToken, TaskPriority
from core.task.task_model import TaskStatus
from core.task.task_storage import TaskStorage


@pytest.fixture
def manager(tmp_path):
    """使用临时存储和真实执行线程，测试后释放所有任务。"""
    TaskStorage._instance = None
    TaskStorage(data_dir=str(tmp_path))
    BackgroundTaskManager._instance = None
    instance = BackgroundTaskManager()
    yield instance
    instance.shutdown()
    BackgroundTaskManager._instance = None
    TaskStorage._instance = None


def test_cooperative_cancel_confirms_actual_stop(manager):
    """只有任务函数实际响应退出后，状态才能从 CANCELLING 变为 CANCELLED。"""
    started = threading.Event()
    after_cancel = threading.Event()

    def worker(token: CancellationToken):
        started.set()
        while not token.is_cancelled:
            time.sleep(0.005)
        token.raise_if_cancelled()
        after_cancel.set()

    task_id = manager.register_cancellable_task(
        "p", "cooperative", worker, priority=TaskPriority.HIGH
    )
    assert started.wait(timeout=1)
    result = manager.request_task_cancellation(task_id)
    assert result.accepted
    assert result.status is TaskStatus.CANCELLING
    deadline = time.monotonic() + 1
    while manager.get_task_status(task_id) is not TaskStatus.CANCELLED:
        assert time.monotonic() < deadline
        time.sleep(0.005)
    assert not after_cancel.is_set()


def test_uncooperative_function_cannot_be_marked_cancelled(manager):
    """函数忽略取消并正常返回时必须报告 COMPLETED，而非伪造 CANCELLED。"""
    started = threading.Event()
    release = threading.Event()
    side_effect = threading.Event()

    def worker(_token):
        started.set()
        release.wait(timeout=2)
        side_effect.set()

    task_id = manager.register_cancellable_task("p", "uncooperative", worker)
    assert started.wait(timeout=1)
    result = manager.request_task_cancellation(task_id, timeout=0.01)
    assert result.status is TaskStatus.CANCELLING
    assert manager.get_task_status(task_id) is not TaskStatus.CANCELLED
    release.set()
    assert side_effect.wait(timeout=1)
    deadline = time.monotonic() + 1
    while manager.get_task_status(task_id) is not TaskStatus.COMPLETED:
        assert time.monotonic() < deadline
        time.sleep(0.005)


def test_queued_cancellation_prevents_function_start(manager):
    """排队任务取消成功后不得再执行函数。"""
    release = threading.Event()
    workers_started = threading.Barrier(4)
    never_started = threading.Event()

    def blocking():
        workers_started.wait(timeout=1)
        release.wait(timeout=2)

    for index in range(4):
        manager.register_async_task("p", f"blocking-{index}", blocking)
    workers_started.wait(timeout=1)
    task_id = manager.register_cancellable_task("p", "queued", never_started.set)
    result = manager.request_task_cancellation(task_id)
    assert result.status is TaskStatus.CANCELLED
    release.set()
    time.sleep(0.1)
    assert not never_started.is_set()


def test_legacy_cancel_task_semantics_remain_compatible(manager):
    """旧 cancel_task 仍保留状态取消兼容，新 API 不改变旧插件行为。"""
    started = threading.Event()
    release = threading.Event()
    side_effect = threading.Event()

    def legacy_worker():
        started.set()
        release.wait(timeout=2)
        side_effect.set()

    task_id = manager.register_async_task("p", "legacy", legacy_worker)
    assert started.wait(timeout=1)
    assert manager.cancel_task(task_id) is True
    assert manager.get_task_status(task_id) is TaskStatus.CANCELLED
    release.set()
    assert side_effect.wait(timeout=1)
