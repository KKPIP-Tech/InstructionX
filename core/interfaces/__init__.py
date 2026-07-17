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
from .i_llm_facade import ILLMFacade
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

# 延迟导出的 LLM 数据类型（来自 core.llm.provider_interface），
# 保持 `from core.interfaces import Message` 等导入路径可用，
# 同时避免 import core.interfaces 时牵入 core.llm / core.plugin / PySide6。
_LAZY_LLM_TYPES = {"Message", "ChatResponse", "EmbeddingResponse", "ModelInfo"}


def __getattr__(name: str):
    if name in _LAZY_LLM_TYPES:
        from core.llm import provider_interface
        return getattr(provider_interface, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

