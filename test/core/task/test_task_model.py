"""
pytest tests for core/task/task_model.py
(BackgroundTask, ScheduledTask, LongRunningTask, TaskType, TaskStatus, TaskThreadLocal)
"""

import threading
import uuid as uuid_module
from datetime import datetime, timedelta

import pytest

from core.task.task_model import (
    BackgroundTask,
    LongRunningTask,
    ScheduledTask,
    TaskStatus,
    TaskThreadLocal,
    TaskType,
)


# ==============================================================================
# TaskType & TaskStatus enum tests
# ==============================================================================

class TestTaskTypeEnum:
    """Tests for TaskType enum values."""

    def test_task_type_values(self):
        """TaskType enum values match expected strings."""
        assert TaskType.SYNC.value == "sync"
        assert TaskType.ASYNC.value == "async"
        assert TaskType.SCHEDULED.value == "scheduled"
        assert TaskType.LONG_RUNNING.value == "long_running"


class TestTaskStatusEnum:
    """Tests for TaskStatus enum values."""

    def test_task_status_values(self):
        """TaskStatus enum values match expected strings."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"
        assert TaskStatus.STOPPED.value == "stopped"


# ==============================================================================
# BackgroundTask tests
# ==============================================================================

class TestBackgroundTaskRoundtrip:
    """Tests for BackgroundTask to_dict / from_dict roundtrip."""

    def test_to_dict_from_dict_preserves_all_fields(self):
        """Roundtrip preserves all fields."""
        task = BackgroundTask(
            task_id="test-task-id",
            plugin_id="plugin-abc",
            name="Test Task",
            task_type=TaskType.ASYNC,
            status=TaskStatus.PENDING,
            result={"key": "value"},
            error=None,
        )
        # Set timestamps explicitly for predictable comparison
        task.created_at = datetime(2024, 3, 15, 10, 0, 0)
        task.started_at = datetime(2024, 3, 15, 10, 1, 0)
        task.finished_at = datetime(2024, 3, 15, 10, 5, 0)

        data = task.to_dict()
        restored = BackgroundTask.from_dict(data)

        assert restored.task_id == task.task_id
        assert restored.plugin_id == task.plugin_id
        assert restored.name == task.name
        assert restored.task_type == task.task_type
        assert restored.status == task.status
        assert restored.result == task.result
        assert restored.error == task.error
        assert restored.created_at == task.created_at
        assert restored.started_at == task.started_at
        assert restored.finished_at == task.finished_at

    def test_uuid_is_auto_generated(self):
        """BackgroundTask uuid is auto-generated via default_factory."""
        task = BackgroundTask()
        # Should be a valid UUID string
        uuid_module.UUID(task.task_id)


class TestBackgroundTaskStateTransitions:
    """Tests for BackgroundTask state transition methods."""

    def test_mark_running_sets_status_and_started_at(self):
        """mark_running() sets status RUNNING and populates started_at."""
        task = BackgroundTask(name="Test Task")
        assert task.status == TaskStatus.PENDING
        assert task.started_at is None

        task.mark_running()

        assert task.status == TaskStatus.RUNNING
        assert task.started_at is not None

    def test_mark_completed_sets_status_result_and_finished_at(self):
        """mark_completed() sets status COMPLETED, result, and finished_at."""
        task = BackgroundTask(name="Test Task")
        task.mark_running()
        expected_result = {"output": "done"}

        task.mark_completed(result=expected_result)

        assert task.status == TaskStatus.COMPLETED
        assert task.result == expected_result
        assert task.finished_at is not None

    def test_mark_failed_sets_status_error_and_finished_at(self):
        """mark_failed() sets status FAILED, error message, and finished_at."""
        task = BackgroundTask(name="Test Task")
        task.mark_running()
        expected_error = "Something went wrong"

        task.mark_failed(error=expected_error)

        assert task.status == TaskStatus.FAILED
        assert task.error == expected_error
        assert task.finished_at is not None

    def test_mark_cancelled_sets_status_and_finished_at(self):
        """mark_cancelled() sets status CANCELLED and finished_at."""
        task = BackgroundTask(name="Test Task")
        task.mark_running()

        task.mark_cancelled()

        assert task.status == TaskStatus.CANCELLED
        assert task.finished_at is not None


# ==============================================================================
# ScheduledTask tests
# ==============================================================================

class TestScheduledTaskRoundtrip:
    """Tests for ScheduledTask to_dict / from_dict roundtrip."""

    def test_to_dict_from_dict_preserves_all_fields(self):
        """Roundtrip preserves all fields."""
        task = ScheduledTask(
            task_id="scheduled-task-id",
            plugin_id="plugin-xyz",
            name="Scheduled Test",
            interval=300,
            enabled=False,
        )
        task.last_run = datetime(2024, 3, 15, 9, 0, 0)
        task.next_run = datetime(2024, 3, 15, 9, 5, 0)
        task.created_at = datetime(2024, 3, 15, 8, 0, 0)

        data = task.to_dict()
        restored = ScheduledTask.from_dict(data)

        assert restored.task_id == task.task_id
        assert restored.plugin_id == task.plugin_id
        assert restored.name == task.name
        assert restored.interval == task.interval
        assert restored.enabled == task.enabled
        assert restored.last_run == task.last_run
        assert restored.next_run == task.next_run
        assert restored.created_at == task.created_at

    def test_calculate_next_run_sets_future_time(self):
        """calculate_next_run() sets next_run to a future time (now + interval)."""
        task = ScheduledTask(name="Interval Task", interval=60)
        before = datetime.now()

        task.calculate_next_run()

        after = datetime.now()
        # next_run should be approximately now + 60 seconds
        assert task.next_run is not None
        expected_min = before + timedelta(seconds=task.interval)
        expected_max = after + timedelta(seconds=task.interval) + timedelta(seconds=1)
        assert expected_min <= task.next_run <= expected_max


# ==============================================================================
# LongRunningTask tests
# ==============================================================================

class TestLongRunningTaskRoundtrip:
    """Tests for LongRunningTask to_dict / from_dict roundtrip."""

    def test_to_dict_from_dict_preserves_all_fields(self):
        """Roundtrip preserves all fields including auto_restart."""
        task = LongRunningTask(
            task_id="long-running-task-id",
            plugin_id="plugin-long",
            name="Long Running Test",
            enabled=True,
            auto_restart=False,
            current_status="running",
            error=None,
            restart_count=5,
        )
        task.created_at = datetime(2024, 3, 15, 8, 0, 0)
        task.last_started_at = datetime(2024, 3, 15, 8, 1, 0)
        task.last_stopped_at = datetime(2024, 3, 15, 12, 0, 0)

        data = task.to_dict()
        restored = LongRunningTask.from_dict(data)

        assert restored.task_id == task.task_id
        assert restored.plugin_id == task.plugin_id
        assert restored.name == task.name
        assert restored.enabled == task.enabled
        assert restored.auto_restart == task.auto_restart
        assert restored.current_status == task.current_status
        assert restored.error == task.error
        assert restored.restart_count == task.restart_count
        assert restored.created_at == task.created_at
        assert restored.last_started_at == task.last_started_at
        assert restored.last_stopped_at == task.last_stopped_at

    def test_auto_restart_default_true(self):
        """LongRunningTask.auto_restart defaults to True."""
        task = LongRunningTask()
        assert task.auto_restart is True


# ==============================================================================
# TaskThreadLocal tests
# ==============================================================================

class TestTaskThreadLocal:
    """Tests for TaskThreadLocal thread-local storage."""

    def test_set_and_get_current_task(self):
        """set_current_task() / get_current_task() store and retrieve a task."""
        task = BackgroundTask(name="Thread Task")
        TaskThreadLocal.clear_current_task()

        TaskThreadLocal.set_current_task(task)
        retrieved = TaskThreadLocal.get_current_task()

        assert retrieved is task

    def test_clear_current_task_removes_association(self):
        """clear_current_task() removes the task association."""
        task = BackgroundTask(name="To Be Cleared")
        TaskThreadLocal.set_current_task(task)
        TaskThreadLocal.clear_current_task()

        assert TaskThreadLocal.get_current_task() is None

    def test_thread_local_isolation(self):
        """Task set in one thread is not visible in another thread."""
        main_task = BackgroundTask(name="Main Task")
        TaskThreadLocal.set_current_task(main_task)

        other_task_ref = []

        def worker():
            # Should not see main_task in the worker thread
            other_task_ref.append(TaskThreadLocal.get_current_task())
            # Set its own task
            worker_task = BackgroundTask(name="Worker Task")
            TaskThreadLocal.set_current_task(worker_task)
            other_task_ref.append(TaskThreadLocal.get_current_task())

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()

        # First read from worker thread should be None (isolated)
        assert other_task_ref[0] is None
        # Second read should be the worker task (still isolated per thread)
        assert other_task_ref[1].name == "Worker Task"

        # Main thread still has its own task
        assert TaskThreadLocal.get_current_task() is main_task
