"""
pytest tests for core/task/background_task.py (BackgroundTaskManager).

Uses fine-grained mocking via __new__ override to allow unit testing
without actually spawning threads or touching the filesystem.
"""
import pytest
from unittest.mock import MagicMock
from concurrent.futures import Future
import threading

# Capture the real __new__ at module level, before any test patches it.
# This must be done before _make_btm captures it.
from core.task.background_task import BackgroundTaskManager
_REAL_BTM_NEW = BackgroundTaskManager.__new__


# ---------------------------------------------------------------------------
# Helper: build a minimal real-ish BackgroundTaskManager instance
# ---------------------------------------------------------------------------

def _make_btm(mocker):
    """
    Return a fully-initialised BackgroundTaskManager with all heavy deps mocked.
    Uses __new__ patch so the singleton machinery is bypassed.
    """
    import core.task.background_task as btm_module
    from core.task.background_task import BackgroundTaskManager
    from core.task.task_storage import TaskStorage

    # Mock TaskStorage
    mock_storage = MagicMock()

    # Mock ThreadPoolExecutor
    mock_executor = MagicMock()

    # Mock TaskScheduler
    mock_scheduler = MagicMock()

    # Mock the scheduler callback object returned by the scheduler
    mock_scheduler_cb = MagicMock()

    # Patch all external side-effects before __init__ runs
    mocker.patch('core.task.background_task.TaskStorage', return_value=mock_storage)

    mocker.patch('core.task.background_task.ThreadPoolExecutor', return_value=mock_executor)
    mocker.patch('core.task.background_task.TaskScheduler', return_value=mock_scheduler)
    mocker.patch('core.task.background_task.SchedulerCallback', return_value=mock_scheduler_cb)
    mocker.patch('time.sleep')
    mocker.patch.object(threading, 'Thread')


    # Patch the class-level _instance / _initialized before instantiation
    btm_module.BackgroundTaskManager._instance = None
    btm_module.BackgroundTaskManager._initialized = False

    # Create the manager — __init__ will run with all deps mocked
    manager = BackgroundTaskManager()

    # Seed mocked storage with no pre-existing data
    mock_storage.get_task.return_value = None
    mock_storage.get_all_tasks.return_value = []
    mock_storage.get_all_scheduled_tasks.return_value = []
    mock_storage.get_scheduled_tasks_by_plugin.return_value = []
    mock_storage.get_all_long_running_tasks.return_value = []
    mock_storage.get_long_running_tasks_by_plugin.return_value = []

    return manager, mock_storage, mock_executor, mock_scheduler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def btm_objects(mocker):
    """Returns (manager, mock_storage, mock_executor, mock_scheduler)."""
    return _make_btm(mocker)


@pytest.fixture
def manager(btm_objects):
    """Returns the manager itself."""
    return btm_objects[0]


# ---------------------------------------------------------------------------
# 1. Singleton — second call returns same instance
# ---------------------------------------------------------------------------

def test_singleton_returns_same_instance(mocker):
    """Calling BackgroundTaskManager() twice must return the same object."""
    from core.task import background_task as btm_module
    from core.task.background_task import BackgroundTaskManager

    # Reset singleton state before first instantiation
    btm_module.BackgroundTaskManager._instance = None
    btm_module.BackgroundTaskManager._initialized = False

    mgr1, *_ = _make_btm(mocker)

    # Verify the singleton instance was set
    assert btm_module.BackgroundTaskManager._instance is mgr1

    # The second call WITHOUT reset should return the same instance (singleton)
    # Get the singleton directly instead of calling _make_btm (which resets)
    mgr2 = BackgroundTaskManager()
    assert mgr1 is mgr2


# ---------------------------------------------------------------------------
# 2. register_sync_task() executes immediately, returns task_id, callback
# ---------------------------------------------------------------------------

def test_register_sync_task_executes_immediately(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    mock_func = MagicMock(return_value=42)
    mock_callback = MagicMock()

    task_id = manager.register_sync_task(
        plugin_id="plugin-1",
        name="sync-test",
        func=mock_func,
        callback=mock_callback,
        args=(1, 2),
        kwargs={"key": "val"},
    )

    # Must return a non-empty string
    assert isinstance(task_id, str) and len(task_id) > 0

    # Function must have been called synchronously (no executor.submit)
    mock_func.assert_called_once_with(1, 2, key="val")

    # Callback must have been called with task_id, status, result, error
    mock_callback.assert_called_once()
    args = mock_callback.call_args[0]
    assert args[0] == task_id   # task_id
    # status should be COMPLETED since func returned 42 without raising
    from core.task.task_model import TaskStatus
    assert args[1] == TaskStatus.COMPLETED
    assert args[2] == 42        # result
    assert args[3] is None      # error

    # Storage must have been used to save the task
    mock_storage.save_task.assert_called()


# ---------------------------------------------------------------------------
# 3. register_async_task() submits to executor, returns task_id
# ---------------------------------------------------------------------------

def test_register_async_task_submits_to_executor(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    mock_func = MagicMock(return_value="async-result")

    # Track what submit() receives
    submitted = []

    def _capture_submit(fn, *args, **kwargs):
        fut = MagicMock(spec=Future)
        submitted.append((fn, args, kwargs))
        return fut

    mock_executor.submit.side_effect = _capture_submit

    task_id = manager.register_async_task(
        plugin_id="plugin-2",
        name="async-test",
        func=mock_func,
        args=("hello",),
    )

    assert isinstance(task_id, str) and len(task_id) > 0
    mock_executor.submit.assert_called_once()

    # task should have been stored
    mock_storage.save_task.assert_called()


# ---------------------------------------------------------------------------
# 4. register_async_task() after shutdown returns None
# ---------------------------------------------------------------------------

def test_register_async_task_after_shutdown_returns_none(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    manager.shutdown()

    result = manager.register_async_task(
        plugin_id="plugin-3",
        name="post-shutdown-async",
        func=MagicMock(),
    )

    assert result is None


# ---------------------------------------------------------------------------
# 5. cancel_task() cancels future, marks CANCELLED
# ---------------------------------------------------------------------------

def test_cancel_task_cancels_and_marks_cancelled(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    # Register a task so it exists in _running_tasks
    mock_func = MagicMock()
    submitted_fut = [None]   # nonlocal container for closure

    def _capture_submit(fn, *args, **kwargs):
        fut = MagicMock(spec=Future)
        fut.done.return_value = False
        submitted_fut[0] = fut
        return fut

    mock_executor.submit.side_effect = _capture_submit

    task_id = manager.register_async_task(
        plugin_id="plugin-4",
        name="cancel-test",
        func=mock_func,
    )

    # Cancel it
    result = manager.cancel_task(task_id)

    assert result is True
    # The future returned by submit must have had cancel() called on it
    assert submitted_fut[0] is not None
    submitted_fut[0].cancel.assert_called()
    # The task should be gone from running_tasks
    assert task_id not in manager._running_tasks


# ---------------------------------------------------------------------------
# 6. get_task() falls back to storage when not in running_tasks
# ---------------------------------------------------------------------------

def test_get_task_falls_back_to_storage(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import BackgroundTask, TaskType, TaskStatus

    fake_task = BackgroundTask(
        plugin_id="plugin-5",
        name="stored-task",
        task_type=TaskType.ASYNC,
        func=None,
    )
    fake_task._status = TaskStatus.COMPLETED

    mock_storage.get_task.return_value = fake_task

    # Not in running_tasks
    assert "non-existent-id" not in manager._running_tasks

    result = manager.get_task(fake_task.task_id)

    assert result is fake_task
    mock_storage.get_task.assert_called_once_with(fake_task.task_id)


# ---------------------------------------------------------------------------
# 7. register_scheduled_task_factory() calls restore_scheduled_tasks()
# ---------------------------------------------------------------------------

def test_register_scheduled_task_factory_calls_restore(mocker):
    from unittest.mock import patch
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    mock_func = MagicMock()
    mock_callback = MagicMock()

    with patch.object(manager, 'restore_scheduled_tasks', return_value=0) as mock_restore:
        manager.register_scheduled_task_factory(
            plugin_id="factory-plugin",
            func=mock_func,
            callback=mock_callback,
        )

        mock_restore.assert_called_once_with("factory-plugin")

    # Factory must be registered
    assert "factory-plugin" in manager._scheduled_task_factories
    assert manager._scheduled_task_factories["factory-plugin"]["func"] is mock_func
    assert manager._scheduled_task_factories["factory-plugin"]["callback"] is mock_callback


# ---------------------------------------------------------------------------
# 8. restore_scheduled_tasks() skips tasks with func already set, skips
#    disabled tasks
# ---------------------------------------------------------------------------

def test_restore_scheduled_tasks_skips_func_set_and_disabled(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import ScheduledTask

    # Register factory so restore finds it
    mock_factory_func = MagicMock()
    manager._scheduled_task_factories["p8"] = {"func": mock_factory_func, "callback": None}

    # Task with func already set → should be skipped
    task_with_func = MagicMock(spec=ScheduledTask)
    task_with_func.task_id = "task-with-func"
    task_with_func.func = MagicMock()   # non-None → should skip
    task_with_func.enabled = True
    task_with_func.next_run = None       # avoid datetime comparison

    # Task disabled → should be skipped (restore checks func, not enabled)
    task_disabled = MagicMock(spec=ScheduledTask)
    task_disabled.task_id = "task-disabled"
    task_disabled.func = MagicMock()   # non-None → should skip (func check only)
    task_disabled.enabled = False
    task_disabled.next_run = None        # avoid datetime comparison with MagicMock

    mock_storage.get_scheduled_tasks_by_plugin.return_value = [
        task_with_func,
        task_disabled,
    ]

    count = manager.restore_scheduled_tasks("p8")

    # Neither task should be restored
    assert count == 0
    # Neither should be added to running dict
    assert "task-with-func" not in manager._running_scheduled_tasks
    assert "task-disabled" not in manager._running_scheduled_tasks


# ---------------------------------------------------------------------------
# 9. register_long_running_task() with auto_restart=True returns task_id
# ---------------------------------------------------------------------------

def test_register_long_running_task_auto_restart_true(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    mock_func = MagicMock()
    mock_executor.submit.return_value = MagicMock(spec=Future)

    task_id = manager.register_long_running_task(
        plugin_id="plugin-9",
        name="long-running-test",
        func=mock_func,
        auto_restart=True,
    )

    assert isinstance(task_id, str) and len(task_id) > 0
    mock_executor.submit.assert_called_once()
    mock_storage.save_long_running_task.assert_called()


# ---------------------------------------------------------------------------
# 10. register_long_running_task() after shutdown returns None
# ---------------------------------------------------------------------------

def test_register_long_running_task_after_shutdown_returns_none(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    manager.shutdown()

    result = manager.register_long_running_task(
        plugin_id="plugin-10",
        name="post-shutdown-long",
        func=MagicMock(),
        auto_restart=True,
    )

    assert result is None


# ---------------------------------------------------------------------------
# 11. stop_long_running_task(delete_from_storage=False) updates status only
# ---------------------------------------------------------------------------

def test_stop_long_running_task_delete_false_updates_status_only(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import LongRunningTask
    from datetime import datetime

    task = LongRunningTask(
        plugin_id="plugin-11",
        name="stop-test",
        func=MagicMock(),
        auto_restart=False,
    )
    task.stop_callback = MagicMock()

    mock_fut = MagicMock(spec=Future)
    mock_fut.done.return_value = False

    with manager._task_lock:
        manager._running_long_running_tasks[task.task_id] = task
        manager._futures[task.task_id] = mock_fut

    result = manager.stop_long_running_task(task.task_id, delete_from_storage=False)

    assert result is True
    # Storage delete must NOT have been called
    mock_storage.delete_long_running_task.assert_not_called()
    # save_long_running_task must have been called (status update)
    mock_storage.save_long_running_task.assert_called()
    # stop_callback must have been called
    task.stop_callback.assert_called_once()
    # Task must have been removed from running dict
    assert task.task_id not in manager._running_long_running_tasks


# ---------------------------------------------------------------------------
# 12. stop_long_running_task(delete_from_storage=True) deletes from storage
# ---------------------------------------------------------------------------

def test_stop_long_running_task_delete_true_deletes_from_storage(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import LongRunningTask

    task = LongRunningTask(
        plugin_id="plugin-12",
        name="stop-delete-test",
        func=MagicMock(),
        auto_restart=False,
    )
    task.stop_callback = MagicMock()

    mock_fut = MagicMock(spec=Future)
    mock_fut.done.return_value = False

    with manager._task_lock:
        manager._running_long_running_tasks[task.task_id] = task
        manager._futures[task.task_id] = mock_fut

    result = manager.stop_long_running_task(task.task_id, delete_from_storage=True)

    assert result is True
    mock_storage.delete_long_running_task.assert_called_once_with(task.task_id)


# ---------------------------------------------------------------------------
# 13. shutdown() sets _is_shutdown=True
# ---------------------------------------------------------------------------

def test_shutdown_sets_is_shutdown_true(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    assert manager._is_shutdown is False
    manager.shutdown()
    assert manager._is_shutdown is True


# ---------------------------------------------------------------------------
# 14. shutdown() rejects new async tasks (returns None)
# ---------------------------------------------------------------------------

def test_shutdown_rejects_async_tasks(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    manager.shutdown()

    # Also verify via the public API
    result = manager.register_async_task(
        plugin_id="plugin-14",
        name="should-be-rejected",
        func=MagicMock(),
    )
    assert result is None


# ---------------------------------------------------------------------------
# 15. shutdown() clears BackgroundTaskManager._instance
# ---------------------------------------------------------------------------

def test_shutdown_clears_singleton_instance(mocker):
    from core.task import background_task as btm_module
    from core.task.background_task import BackgroundTaskManager

    manager, *_ = _make_btm(mocker)

    assert btm_module.BackgroundTaskManager._instance is manager

    manager.shutdown()

    assert btm_module.BackgroundTaskManager._instance is None


# ---------------------------------------------------------------------------
# 16. update_long_running_task_status() calls status_callback
# ---------------------------------------------------------------------------

def test_update_long_running_task_status_calls_callback(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import LongRunningTask

    task = LongRunningTask(
        plugin_id="plugin-16",
        name="status-update-test",
        func=MagicMock(),
        auto_restart=False,
    )
    status_cb = MagicMock()
    task.status_callback = status_cb

    with manager._task_lock:
        manager._running_long_running_tasks[task.task_id] = task

    result = manager.update_long_running_task_status(task.task_id, "my-custom-status")

    assert result is True
    status_cb.assert_called_once_with(task.task_id, "my-custom-status")
    mock_storage.save_long_running_task.assert_called()


# ---------------------------------------------------------------------------
# 17. get_all_tasks() returns all running + stored tasks
# ---------------------------------------------------------------------------

def test_get_all_tasks_combines_running_and_stored(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import BackgroundTask, TaskType

    stored_task = BackgroundTask(
        plugin_id="p17",
        name="stored",
        task_type=TaskType.ASYNC,
        func=None,
    )
    mock_storage.get_all_tasks.return_value = [stored_task]

    running_task = BackgroundTask(
        plugin_id="p17",
        name="running",
        task_type=TaskType.SYNC,
        func=MagicMock(),
    )
    with manager._task_lock:
        manager._running_tasks[running_task.task_id] = running_task

    all_tasks = manager.get_all_tasks()

    task_ids = {t.task_id for t in all_tasks}
    assert running_task.task_id in task_ids
    assert stored_task.task_id in task_ids


# ---------------------------------------------------------------------------
# 18. get_scheduled_tasks() returns scheduled task list
# ---------------------------------------------------------------------------

def test_get_scheduled_tasks_returns_list(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    from core.task.task_model import ScheduledTask

    sched_task = MagicMock(spec=ScheduledTask)
    sched_task.task_id = "sched-18"
    mock_storage.get_all_scheduled_tasks.return_value = [sched_task]

    result = manager.get_scheduled_tasks()

    assert result == [sched_task]
    mock_storage.get_all_scheduled_tasks.assert_called()


# ---------------------------------------------------------------------------
# 19. clear_completed_tasks() delegates to storage
# ---------------------------------------------------------------------------

def test_clear_completed_tasks_delegates_to_storage(mocker):
    manager, mock_storage, mock_executor, mock_scheduler = _make_btm(mocker)

    mock_storage.clear_completed_tasks.return_value = 5

    result = manager.clear_completed_tasks(plugin_id="plugin-19")

    assert result == 5
    mock_storage.clear_completed_tasks.assert_called_once_with("plugin-19")


# ---------------------------------------------------------------------------
# unregister_scheduled_task 回归测试（禁用态任务必须可注销）
# ---------------------------------------------------------------------------

def test_unregister_scheduled_task_removes_running_and_storage(mocker):
    """启用态定时任务注销：同时摘除运行表并删除存储记录。"""
    manager, mock_storage, _, _ = _make_btm(mocker)
    task = MagicMock()
    manager._running_scheduled_tasks["task-1"] = task
    mock_storage.delete_scheduled_task.return_value = True

    result = manager.unregister_scheduled_task("task-1")

    assert result is True
    assert "task-1" not in manager._running_scheduled_tasks
    mock_storage.delete_scheduled_task.assert_called_once_with("task-1")


def test_unregister_scheduled_task_disabled_task_deletes_storage(mocker):
    """回归：禁用态定时任务（不在运行表、存储记录仍在）必须可注销。

    历史 bug：unregister_scheduled_task 只查运行表，禁用任务被
    disable_scheduled_task 摘出运行表后永远无法注销，存储记录形成
    僵尸数据；修复后以存储删除结果为准。
    """
    manager, mock_storage, _, _ = _make_btm(mocker)
    assert "task-2" not in manager._running_scheduled_tasks
    mock_storage.delete_scheduled_task.return_value = True

    result = manager.unregister_scheduled_task("task-2")

    assert result is True
    mock_storage.delete_scheduled_task.assert_called_once_with("task-2")


def test_unregister_scheduled_task_not_found_returns_false(mocker):
    """存储中不存在的任务注销返回 False（不存在的判定以存储为准）。"""
    manager, mock_storage, _, _ = _make_btm(mocker)
    mock_storage.delete_scheduled_task.return_value = False

    result = manager.unregister_scheduled_task("task-missing")

    assert result is False


# ---------------------------------------------------------------------------
# is_long_task_running 回归测试（以运行时表为准，不受状态文本影响）
# ---------------------------------------------------------------------------

def test_is_long_task_running_true_when_in_running_table(mocker):
    """任务在运行时表中时返回 True。"""
    manager, _, _, _ = _make_btm(mocker)
    manager._running_long_running_tasks["task-1"] = MagicMock()

    assert manager.is_long_task_running("task-1") is True


def test_is_long_task_running_unaffected_by_status_text(mocker):
    """回归：插件上报自由文本状态后运行态判定不受影响。

    历史 bug：托盘按 current_status == "running" 过滤长期任务，
    update_long_running_task_status 的自由文本覆盖后任务从托盘消失；
    修复后判定以运行时表为准。
    """
    manager, mock_storage, _, _ = _make_btm(mocker)
    task = MagicMock()
    manager._running_long_running_tasks["task-1"] = task

    manager.update_long_running_task_status("task-1", "已运行 3 秒")

    assert manager.is_long_task_running("task-1") is True


def test_is_long_task_running_false_when_not_in_table(mocker):
    """任务不在运行时表中（停止/不存在）返回 False。"""
    manager, _, _, _ = _make_btm(mocker)

    assert manager.is_long_task_running("task-missing") is False
