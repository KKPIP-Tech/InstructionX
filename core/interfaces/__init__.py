"""
Core interfaces module

抽象接口层，定义核心服务与插件之间的契约。
所有插件通过这些接口与核心服务交互，而非直接依赖具体实现。

导入方式：
    from core.interfaces import IPlugin, IDataProvider, ITaskManager, ...
"""

from .i_plugin import IPlugin
from .i_plugin_info import IPluginInfo
from .i_data_provider import IDataProvider, DataNamespace
from .i_task_manager import ITaskManager, TaskType, TaskStatus
from .i_llm_facade import ILLMFacade, Message, ChatResponse, EmbeddingResponse, ModelInfo
from utils.i_logger import ILogger
from .plugin_services import PluginServices

__all__ = [
    "IPlugin",
    "IPluginInfo",
    "IDataProvider",
    "DataNamespace",
    "ITaskManager",
    "TaskType",
    "TaskStatus",
    "ILLMFacade",
    "Message",
    "ChatResponse",
    "EmbeddingResponse",
    "ModelInfo",
    "ILogger",
    "PluginServices",
]
