"""LLM 模块 - 大语言模型提供商抽象层

该模块提供统一的 LLM 接口抽象，支持多种 LLM 提供商（GLM、MiniMax、SiliconFlow、Ollama 等）。
采用策略模式设计，通过抽象基类 ILLM 定义统一接口，各提供商实现具体逻辑。

主要功能:
    - 统一的聊天Completion接口
    - 流式输出支持
    - 嵌入（Embedding）向量生成
    - 模型列表获取
    - 异步API支持

使用示例:
    >>> from core.llm import LLMProvider, ILLM, Message
    >>> provider = LLMProvider()
    >>> response = provider.chat([Message("user", "你好")])

异常类:
    - LLMException: 基础异常类
    - ConfigurationError: 配置错误
    - AuthenticationError: 认证错误
    - APIError: API调用错误
    - RateLimitError: 速率限制
    - InvalidRequestError: 无效请求
    - ModelNotSupportedError: 模型不支持
    - ConnectionError: 连接错误
    - TimeoutError: 超时错误
    - StreamingError: 流式输出错误
"""

from .llm_provider import LLMProvider, get_llm_provider
from .provider_interface import (
    ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo,
    UsageInfo, ToolCall, ModelCheckResult
)
from .config import LLMConfig, ProviderConfig, get_llm_config
from .exceptions import (
    LLMException,
    ConfigurationError,
    AuthenticationError,
    APIError,
    RateLimitError,
    InvalidRequestError,
    ModelNotSupportedError,
    ConnectionError,
    TimeoutError,
    StreamingError,
)

# 新增：插件服务层类型（types.py）
from .types import (
    DEFAULT_PROVIDER,
    DEFAULT_MODEL,
    Conversation,
    ToolResult,
    ToolChatResult,
    ToolDefinition,
    UsageStats,
    ImageResult,
    AudioResult,
    ProviderInfo,
    StreamChunk,
    UsageRecord,
)

# 新增：用量记录持久化
from .usage_record_store import UsageRecordStore, get_usage_record_store

# 新增：缓存相关
from .types_cache import CacheInfo, CacheType
from .cache_adapter import CacheAdapter, get_cache_adapter, DEFAULT_CACHE_CONFIG

# 新增：插件服务层类
from .plugin_service import LLMPluginService, get_llm_plugin_service
from .conversation_manager import ConversationManager
from .tool_call_executor import ToolCallExecutor, ToolRegistry

__all__ = [
    # 核心
    "LLMProvider",
    "get_llm_provider",
    "ILLM",
    "Message",
    "ChatResponse",
    "EmbeddingResponse",
    "ModelInfo",
    "UsageInfo",
    "ToolCall",
    "ModelCheckResult",
    "LLMConfig",
    "ProviderConfig",
    "get_llm_config",
    # 异常
    "LLMException",
    "ConfigurationError",
    "AuthenticationError",
    "APIError",
    "RateLimitError",
    "InvalidRequestError",
    "ModelNotSupportedError",
    "ConnectionError",
    "TimeoutError",
    "StreamingError",
    # 插件服务层类型
    "DEFAULT_PROVIDER",
    "DEFAULT_MODEL",
    "Conversation",
    "ToolResult",
    "ToolChatResult",
    "ToolDefinition",
    "UsageStats",
    "ImageResult",
    "AudioResult",
    "ProviderInfo",
    "StreamChunk",
    "UsageRecord",
    # 用量记录持久化
    "UsageRecordStore",
    "get_usage_record_store",
    # 缓存相关
    "CacheInfo",
    "CacheType",
    "CacheAdapter",
    "get_cache_adapter",
    "DEFAULT_CACHE_CONFIG",
    # 插件服务层类
    "LLMPluginService",
    "get_llm_plugin_service",
    "ConversationManager",
    "ToolCallExecutor",
    "ToolRegistry",
]
