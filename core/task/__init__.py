"""Task 模块 - 后台任务管理系统

该模块提供后台任务和定时任务的管理功能，支持：
    - 后台任务执行和状态管理
    - 定时任务调度
    - 任务持久化存储
    - 任务取消和进度跟踪

Classes:
    BackgroundTaskManager: 后台任务管理器
    TaskType: 任务类型枚举
    TaskStatus: 任务状态枚举
    BackgroundTask: 后台任务模型
    ScheduledTask: 定时任务模型
    LongRunningTask: 长时运行任务模型

使用示例:
    >>> from core.task import BackgroundTaskManager, TaskType, TaskStatus
    >>> manager = BackgroundTaskManager()
    >>> task_id = manager.create_task(TaskType.PLUGIN, callback_func)

模块依赖:
    - utils.logging_tools: 日志工具
"""

from .background_task import BackgroundTaskManager
from .task_model import TaskType, TaskStatus, BackgroundTask, ScheduledTask, LongRunningTask, TaskThreadLocal


__all__ = [
    "BackgroundTaskManager",
    "TaskType",
    "TaskStatus",
    "BackgroundTask",
    "ScheduledTask",
    "LongRunningTask",
    "TaskThreadLocal",
]