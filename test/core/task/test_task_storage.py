"""TaskStorage 单元测试

覆盖任务持久化存储的 CRUD、缓存、损坏回退等核心行为。
"""

import json
from datetime import datetime

import pytest

from core.task.task_model import BackgroundTask, ScheduledTask, LongRunningTask, TaskStatus
from core.task.task_storage import TaskStorage


@pytest.fixture
def storage(tmp_path):
    """返回使用临时目录的 TaskStorage 实例。"""
    return TaskStorage(data_dir=str(tmp_path))


class TestSingleton:
    def test_same_instance(self, tmp_path):
        s1 = TaskStorage(data_dir=str(tmp_path))
        s2 = TaskStorage(data_dir=str(tmp_path / "other"))
        assert s1 is s2


class TestInitialization:
    def test_creates_default_file_when_missing(self, storage):
        assert storage.tasks_file.exists()
        data = json.loads(storage.tasks_file.read_text(encoding="utf-8"))
        assert data == {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}

    def test_uses_existing_file(self, tmp_path):
        tasks_file = tmp_path / "tasks.json"
        existing = {
            "tasks": {"t1": {"task_id": "t1", "plugin_id": "p1", "name": "n1",
                             "task_type": "async", "status": "pending"}},
            "scheduled_tasks": {},
            "long_running_tasks": {},
        }
        tasks_file.write_text(json.dumps(existing), encoding="utf-8")

        storage = TaskStorage(data_dir=str(tmp_path))
        assert storage.get_task("t1") is not None


class TestBackgroundTaskCrud:
    def test_save_and_get_task(self, storage):
        task = BackgroundTask(task_id="t1", plugin_id="p1", name="task-one")
        storage.save_task(task)

        loaded = storage.get_task("t1")
        assert loaded is not None
        assert loaded.task_id == "t1"
        assert loaded.plugin_id == "p1"
        assert loaded.name == "task-one"

    def test_get_task_returns_none_for_missing(self, storage):
        assert storage.get_task("missing") is None

    def test_get_all_tasks(self, storage):
        storage.save_task(BackgroundTask(task_id="t1", plugin_id="p1"))
        storage.save_task(BackgroundTask(task_id="t2", plugin_id="p2"))
        tasks = storage.get_all_tasks()
        assert len(tasks) == 2
        assert {t.task_id for t in tasks} == {"t1", "t2"}

    def test_get_tasks_by_plugin(self, storage):
        storage.save_task(BackgroundTask(task_id="t1", plugin_id="p1"))
        storage.save_task(BackgroundTask(task_id="t2", plugin_id="p1"))
        storage.save_task(BackgroundTask(task_id="t3", plugin_id="p2"))

        tasks = storage.get_tasks_by_plugin("p1")
        assert len(tasks) == 2
        assert {t.task_id for t in tasks} == {"t1", "t2"}

    def test_delete_task_removes_and_returns_true(self, storage):
        storage.save_task(BackgroundTask(task_id="t1"))
        assert storage.delete_task("t1") is True
        assert storage.get_task("t1") is None

    def test_delete_task_returns_false_for_missing(self, storage):
        assert storage.delete_task("missing") is False


class TestClearCompletedTasks:
    def test_clears_completed_failed_cancelled(self, storage):
        completed = BackgroundTask(task_id="t1", plugin_id="p1")
        completed.mark_completed()
        failed = BackgroundTask(task_id="t2", plugin_id="p1")
        failed.mark_failed("err")
        cancelled = BackgroundTask(task_id="t3", plugin_id="p1")
        cancelled.mark_cancelled()
        pending = BackgroundTask(task_id="t4", plugin_id="p1")

        for t in [completed, failed, cancelled, pending]:
            storage.save_task(t)

        count = storage.clear_completed_tasks()
        assert count == 3
        assert storage.get_task("t4") is not None
        assert storage.get_task("t1") is None

    def test_clear_completed_tasks_filters_by_plugin(self, storage):
        t1 = BackgroundTask(task_id="t1", plugin_id="p1")
        t1.mark_completed()
        t2 = BackgroundTask(task_id="t2", plugin_id="p2")
        t2.mark_completed()
        storage.save_task(t1)
        storage.save_task(t2)

        assert storage.clear_completed_tasks(plugin_id="p1") == 1
        assert storage.get_task("t1") is None
        assert storage.get_task("t2") is not None


class TestScheduledTaskCrud:
    def test_save_and_get_scheduled_task(self, storage):
        task = ScheduledTask(task_id="s1", plugin_id="p1", name="scheduled", interval=30)
        storage.save_scheduled_task(task)

        loaded = storage.get_scheduled_task("s1")
        assert loaded is not None
        assert loaded.task_id == "s1"
        assert loaded.interval == 30

    def test_update_scheduled_task(self, storage):
        task = ScheduledTask(task_id="s1", plugin_id="p1", interval=30)
        storage.save_scheduled_task(task)
        task.interval = 60
        storage.update_scheduled_task(task)
        assert storage.get_scheduled_task("s1").interval == 60

    def test_delete_scheduled_task(self, storage):
        storage.save_scheduled_task(ScheduledTask(task_id="s1"))
        assert storage.delete_scheduled_task("s1") is True
        assert storage.get_scheduled_task("s1") is None


class TestLongRunningTaskCrud:
    def test_save_and_get_long_running_task(self, storage):
        task = LongRunningTask(task_id="l1", plugin_id="p1", name="long", auto_restart=False)
        storage.save_long_running_task(task)

        loaded = storage.get_long_running_task("l1")
        assert loaded is not None
        assert loaded.task_id == "l1"
        assert loaded.auto_restart is False

    def test_get_long_running_tasks_by_plugin(self, storage):
        storage.save_long_running_task(LongRunningTask(task_id="l1", plugin_id="p1"))
        storage.save_long_running_task(LongRunningTask(task_id="l2", plugin_id="p2"))
        tasks = storage.get_long_running_tasks_by_plugin("p1")
        assert len(tasks) == 1
        assert tasks[0].task_id == "l1"

    def test_delete_long_running_task(self, storage):
        storage.save_long_running_task(LongRunningTask(task_id="l1"))
        assert storage.delete_long_running_task("l1") is True
        assert storage.get_long_running_task("l1") is None


class TestCorruptionFallback:
    def test_load_data_returns_default_on_corrupted_json(self, storage):
        storage.tasks_file.write_text("{ invalid json }", encoding="utf-8")
        storage.clear_cache()

        data = storage.load_data(force_reload=True)
        assert data["tasks"] == {}
        assert data["scheduled_tasks"] == {}


class TestCacheBehavior:
    def test_load_data_returns_copy(self, storage):
        storage.save_task(BackgroundTask(task_id="t1", plugin_id="p1"))
        data = storage.load_data()
        data["tasks"]["t1"]["plugin_id"] = "tampered"
        assert storage.get_task("t1").plugin_id == "p1"

    def test_save_data_writes_cache(self, storage):
        storage.save_task(BackgroundTask(task_id="t1"))
        storage.clear_cache()
        assert storage.get_task("t1") is not None
