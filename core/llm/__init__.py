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
from .provider_interface import ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo
from .config import LLMConfig, ProviderConfig
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

__all__ = [
    "LLMProvider",
    "get_llm_provider",
    "ILLM",
    "Message",
    "ChatResponse",
    "EmbeddingResponse",
    "ModelInfo",
    "LLMConfig",
    "ProviderConfig",
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
]
