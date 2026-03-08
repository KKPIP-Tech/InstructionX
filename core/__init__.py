"""
Core 模块

包含应用程序的核心功能模块。
"""

# 插件系统
from .plugin.manager import PluginManager
from .plugin.plugin_interface import IPlugin
from .plugin.plugin_info_interface import IPluginInfo

# 数据层
from .data.data_provider import DataProvider, DataNamespace

# 后台任务
from .task.background_task import BackgroundTaskManager
from .task.task_model import TaskType, TaskStatus, BackgroundTask, ScheduledTask

__all__ = [
    # 插件系统
    "PluginManager",
    "IPlugin",
    "IPluginInfo",

    # 数据层
    "DataProvider",
    "DataNamespace",

    # 后台任务
    "BackgroundTaskManager",
    "TaskType",
    "TaskStatus",
    "BackgroundTask",
    "ScheduledTask",
]
