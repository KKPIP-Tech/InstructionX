"""
LLM Facade 接口

定义大语言模型统一访问的抽象接口。
插件通过此接口访问 LLM 能力，而非直接依赖 LLMProvider 实现。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Callable

# 复用现有的数据类型（这些是纯数据结构，不依赖具体实现）
from core.llm.provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo


class ILLMFacade(ABC):
    """
    LLM 统一门面接口

    定义大语言模型统一访问的抽象接口。
    插件通过此接口访问聊天、嵌入、模型列表等 LLM 能力。
    """

    @abstractmethod
    def chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）"""
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[ChatResponse], None]] = None,
        **kwargs
    ):
        """发送流式聊天请求（同步）"""
        pass

    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        provider: str = "default",
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送文本嵌入请求（同步）"""
        pass

    @abstractmethod
    def get_models(self, provider: Optional[str] = None) -> Dict[str, List[ModelInfo]]:
        """获取可用模型列表"""
        pass

    @abstractmethod
    def get_provider(self, name: str) -> Optional[Any]:
        """获取指定名称的提供商实例"""
        pass

    @abstractmethod
    def get_all_providers(self) -> Dict[str, Any]:
        """获取所有已创建的提供商实例"""
        pass

    @abstractmethod
    def get_cached_models(self, provider_name: str) -> List[ModelInfo]:
        """获取指定提供商的缓存模型列表"""
        pass
