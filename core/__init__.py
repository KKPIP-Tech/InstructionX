"""Core 模块 - 应用程序核心功能

该模块是应用程序的核心功能模块，包含以下子系统：

1. 插件系统 (Plugin System)
    - PluginManager: 插件管理器，负责插件的加载、卸载、启用/禁用等
    - IPlugin: 插件抽象基类，定义所有插件必须实现的接口
    - IPluginInfo: 插件信息接口，定义插件元数据

2. 数据层 (Data Layer)
    - DataProvider: 数据提供者，负责插件数据的持久化、缓存和插件间通信
    - DataNamespace: 数据命名空间枚举（PRIVATE/PUBLIC）

3. 后台任务 (Background Tasks)
    - BackgroundTaskManager: 后台任务管理器，负责任务的创建、执行、取消等
    - TaskType: 任务类型枚举
    - TaskStatus: 任务状态枚举
    - BackgroundTask: 后台任务模型
    - ScheduledTask: 定时任务模型

使用示例:
    >>> from core import PluginManager, DataProvider, BackgroundTaskManager
    >>>
    >>> # 插件管理
    >>> plugin_manager = PluginManager()
    >>> plugin_manager.load_plugins()
    >>>
    >>> # 数据提供
    >>> data_provider = DataProvider()
    >>> data_provider.register_plugin("plugin-001", "MyPlugin")
    >>>
    >>> # 后台任务
    >>> task_manager = BackgroundTaskManager()
    >>> task_manager.create_task(TaskType.PLUGIN, callback_func)

模块依赖:
    - core/plugin: 插件系统模块
    - core/data: 数据层模块
    - core/task: 后台任务模块
    - core/llm: LLM 提供商模块（未在主模块导出，按需导入）
"""

# ==================== 插件系统 ====================

from .plugin.manager import PluginManager
from .plugin.plugin_interface import IPlugin
from .plugin.plugin_info_interface import IPluginInfo

# ==================== 数据层 ====================

from .data.data_provider import DataProvider, DataNamespace

# ==================== 后台任务 ====================

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