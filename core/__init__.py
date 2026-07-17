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
    >>> task_id = task_manager.register_async_task(
    ...     plugin_id="plugin-uuid", name="my_task",
    ...     func=callback_func, callback=my_callback)

模块依赖:
    - core/plugin: 插件系统模块
    - core/data: 数据层模块
    - core/task: 后台任务模块
    - core/llm: LLM 提供商模块（未在主模块导出，按需导入）
"""

# ==================== 延迟导出（PEP 562） ====================
#
# 本包的公开符号通过模块级 __getattr__ 按需加载，避免 import core 或
# import core.interfaces 时牵入 core.plugin / PySide6 等重量依赖。
# 所有既有导入路径保持不变：
#     from core import PluginManager, DataProvider, BackgroundTaskManager, ...

_LAZY_EXPORTS = {
    # 插件系统
    "PluginManager": ("core.plugin.manager", "PluginManager"),
    "IPlugin": ("core.plugin.plugin_interface", "IPlugin"),
    "IPluginInfo": ("core.plugin.plugin_info_interface", "IPluginInfo"),
    # 数据层
    "DataProvider": ("core.data.data_provider", "DataProvider"),
    "DataNamespace": ("core.data.data_provider", "DataNamespace"),
    # 后台任务
    "BackgroundTaskManager": ("core.task.background_task", "BackgroundTaskManager"),
    "TaskType": ("core.task.task_model", "TaskType"),
    "TaskStatus": ("core.task.task_model", "TaskStatus"),
    "BackgroundTask": ("core.task.task_model", "BackgroundTask"),
    "ScheduledTask": ("core.task.task_model", "ScheduledTask"),
    "LongRunningTask": ("core.task.task_model", "LongRunningTask"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value  # 缓存到模块命名空间，后续访问不再触发 __getattr__
    return value


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
    "LongRunningTask",
]
