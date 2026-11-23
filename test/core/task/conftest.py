"""
Task module test fixtures

提供 Task 模块测试所需的 fixtures，包括：
- BackgroundTaskManager 工厂函数
- Mock 依赖注入
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock
import threading


# ─── BackgroundTaskManager 工厂 ────────────────────────────────────────────

@pytest.fixture
def btm_objects(mocker):
    """
    返回完全初始化的 BackgroundTaskManager 实例及 Mock 依赖。

    返回 (manager, mock_storage, mock_executor, mock_scheduler) 元组。

    使用 __new__ patch 绕过单例机制，适合单元测试。
    所有外部依赖（TaskStorage, ThreadPoolExecutor, TaskScheduler）均被 Mock。
    """
    import core.task.background_task as btm_module
    from core.task.background_task import BackgroundTaskManager

    # Mock TaskStorage
    mock_storage = MagicMock()

    # Mock ThreadPoolExecutor
    mock_executor = MagicMock()

    # Mock TaskScheduler
    mock_scheduler = MagicMock()

    # Mock SchedulerCallback
    mock_scheduler_cb = MagicMock()

    # Patch 所有外部副作用
    mocker.patch('core.task.background_task.TaskStorage', return_value=mock_storage)
    mocker.patch('core.task.background_task.ThreadPoolExecutor', return_value=mock_executor)
    mocker.patch('core.task.background_task.TaskScheduler', return_value=mock_scheduler)
    mocker.patch('core.task.background_task.SchedulerCallback', return_value=mock_scheduler_cb)
    mocker.patch('time.sleep')
    mocker.patch.object(threading, 'Thread')

    # 重置类级别单例状态
    btm_module.BackgroundTaskManager._instance = None
    btm_module.BackgroundTaskManager._initialized = False

    # 创建实例
    manager = BackgroundTaskManager()

    # 初始化 Mock storage 返回值
    mock_storage.get_task.return_value = None
    mock_storage.get_all_tasks.return_value = []
    mock_storage.get_all_scheduled_tasks.return_value = []
    mock_storage.get_scheduled_tasks_by_plugin.return_value = []
    mock_storage.get_all_long_running_tasks.return_value = []
    mock_storage.get_long_running_tasks_by_plugin.return_value = []

    return manager, mock_storage, mock_executor, mock_scheduler


# ─── Mock Task ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_task():
    """
    返回一个 Mock BackgroundTask 对象。

    适用于需要模拟任务但不实际执行的测试场景。
    """
    task = MagicMock()
    task.task_id = "test-task-id"
    task.name = "test-task"
    task.plugin_id = "test-plugin"
    task.status = "pending"
    return task
