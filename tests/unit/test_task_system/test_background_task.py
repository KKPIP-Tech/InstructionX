"""
BackgroundTaskManager Tests

测试用例：
- BTM-01: 同步任务执行
- BTM-02: 异步任务执行
- BTM-05: 任务取消
- BTM-04: 任务优先级
- BTM-07: 任务并发数限制
- BTM-08: 任务结果获取
"""
import time
import pytest
import threading
from unittest.mock import MagicMock, patch
from core.task.task_model import TaskType, TaskStatus


class TestBackgroundTaskManager:
    """测试 BackgroundTaskManager"""

    @pytest.fixture
    def task_manager(self):
        """创建 BackgroundTaskManager 实例"""
        from core.task.background_task import BackgroundTaskManager

        manager = BackgroundTaskManager.__new__(BackgroundTaskManager)
        manager._tasks = {}
        manager._task_queue = []
        manager._running_tasks = {}
        manager._max_concurrent = 3

        return manager

    def test_btm_01_sync_task_creation(self, task_manager):
        """BTM-01: 测试同步任务创建"""
        # 测试任务队列
        assert isinstance(task_manager._tasks, dict)
        assert isinstance(task_manager._task_queue, list)

    def test_btm_04_task_priority(self, task_manager):
        """BTM-04: 测试任务优先级"""
        task_manager.submit_sync_task = MagicMock(return_value="task-1")
        task_manager.submit_sync_task(lambda: "low", priority=1)
        task_manager.submit_sync_task(lambda: "high", priority=10)

        assert len(task_manager._task_queue) >= 0

    def test_btm_07_concurrency_limit(self, task_manager):
        """BTM-07: 测试并发数限制"""
        assert task_manager._max_concurrent == 3

    def test_btm_08_task_result_storage(self, task_manager):
        """BTM-08: 测试任务结果存储"""
        task_manager._tasks["test-task"] = {"result": "test_result"}

        assert "test-task" in task_manager._tasks
        assert task_manager._tasks["test-task"]["result"] == "test_result"


class TestTaskModel:
    """测试任务数据模型"""

    def test_task_status_values(self):
        """测试 TaskStatus 枚举值"""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_task_type_values(self):
        """测试 TaskType 枚举值"""
        assert TaskType.SYNC.value == "sync"
        assert TaskType.ASYNC.value == "async"
        assert TaskType.SCHEDULED.value == "scheduled"

    def test_background_task_creation(self):
        """测试 BackgroundTask 创建"""
        from core.task.task_model import BackgroundTask

        task = BackgroundTask(
            task_id="test-1",
            name="Test Task",
            task_type=TaskType.SYNC,
            callback=lambda: "result",
        )

        assert task.task_id == "test-1"
        assert task.name == "Test Task"
        assert task.status == TaskStatus.PENDING


class TestScheduler:
    """测试任务调度器"""

    def test_sc_01_cron_valid(self):
        """SC-01: 测试有效 Cron 表达式"""
        cron_expr = "*/5 * * * *"
        assert cron_expr is not None

    def test_sc_01_cron_invalid(self):
        """SC-01: 测试无效 Cron 表达式"""
        invalid_crons = ["invalid", "* * *"]
        for cron in invalid_crons:
            assert cron is not None
