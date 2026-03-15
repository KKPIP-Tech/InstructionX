"""
ILLM 抽象基类定义
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable, AsyncIterator, Union


class Message:
    """聊天消息"""

    def __init__(
        self,
        role: str,
        content: str,
        images: Optional[List[str]] = None,
        **kwargs
    ):
        self.role = role
        self.content = content
        self.images = images or []
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            result["images"] = self.images
        result.update(self.extra)
        return result


class ChatResponse:
    """聊天响应"""

    def __init__(
        self,
        content: str,
        model: str,
        role: str = "assistant",
        reasoning_content: str = "",
        tool_calls: Optional[List[Dict]] = None,
        **kwargs
    ):
        self.content = content
        self.model = model
        self.role = role
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls or []
        self.extra = kwargs


class EmbeddingResponse:
    """嵌入响应"""

    def __init__(
        self,
        embedding: List[float],
        model: str,
        **kwargs
    ):
        self.embedding = embedding
        self.model = model
        self.extra = kwargs


class ModelInfo:
    """模型信息"""

    def __init__(
        self,
        id: str,
        name: str,
        support_chat: bool = True,
        support_streaming: bool = True,
        support_embedding: bool = False,
        support_vision: bool = False,
        support_function_calling: bool = False,
        context_length: Optional[int] = None,
        **kwargs
    ):
        self.id = id
        self.name = name
        self.support_chat = support_chat
        self.support_streaming = support_streaming
        self.support_embedding = support_embedding
        self.support_vision = support_vision
        self.support_function_calling = support_function_calling
        self.context_length = context_length
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "id": self.id,
            "name": self.name,
            "support_chat": self.support_chat,
            "support_streaming": self.support_streaming,
            "support_embedding": self.support_embedding,
            "support_vision": self.support_vision,
            "support_function_calling": self.support_function_calling,
            "context_length": self.context_length,
        }
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelInfo":
        """从字典创建 ModelInfo"""
        known_fields = {
            "id", "name", "support_chat", "support_streaming",
            "support_embedding", "support_vision",
            "support_function_calling", "context_length"
        }
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            support_chat=data.get("support_chat", True),
            support_streaming=data.get("support_streaming", True),
            support_embedding=data.get("support_embedding", False),
            support_vision=data.get("support_vision", False),
            support_function_calling=data.get("support_function_calling", False),
            context_length=data.get("context_length"),
            **extra
        )


class ILLM(ABC):
    """LLM Provider 抽象基类"""

    # Provider 类型标识
    provider_type: str = ""
    provider_name: str = ""

    # 功能支持标志
    support_chat: bool = True
    support_streaming: bool = True
    support_embedding: bool = False
    support_vision: bool = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Provider

        Args:
            config: Provider 配置字典
        """
        self.config = config or {}
        self._session = None
        self._async_session = None

    # ==================== 同步 API ====================

    @abstractmethod
    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """
        发送聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应
        """
        pass

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[ChatResponse], None]] = None,
        **kwargs
    ) -> Union[AsyncIterator[ChatResponse], List[ChatResponse]]:
        """
        发送流式聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback: 流式回调函数
            **kwargs: 其他参数

        Returns:
            Union[AsyncIterator[ChatResponse], List[ChatResponse]]: 流式响应迭代器或响应列表
        """
        raise NotImplementedError("Streaming not supported")

    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """
        发送嵌入请求

        Args:
            texts: 文本或文本列表
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        pass

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """
        获取可用模型列表

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        pass

    def validate_config(self) -> bool:
        """
        验证配置是否有效

        Returns:
            bool: 配置是否有效
        """
        return bool(self.config.get("api_key") or self.config.get("base_url"))

    # ==================== 异步 API ====================

    @abstractmethod
    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """
        异步发送聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应
        """
        pass

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """
        异步发送流式聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Yields:
            ChatResponse: 聊天响应块
        """
        raise NotImplementedError("Async streaming not supported")

    @abstractmethod
    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """
        异步发送嵌入请求

        Args:
            texts: 文本或文本列表
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        pass

    @abstractmethod
    async def async_get_models(self) -> List[ModelInfo]:
        """
        异步获取可用模型列表

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        pass

    def refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """
        刷新模型列表

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.get_models()

    async def async_refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """
        异步刷新模型列表

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return await self.async_get_models()

    # ==================== 工具方法 ====================

    def _prepare_messages(
        self,
        messages: List[Union[Message, Dict]]
    ) -> List[Dict[str, Any]]:
        """准备消息格式"""
        result = []
        for msg in messages:
            if isinstance(msg, Message):
                result.append(msg.to_dict())
            elif isinstance(msg, dict):
                result.append(msg)
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")
        return result

    def close(self):
        """关闭连接"""
        if self._session:
            self._session.close()
            self._session = None
        if self._async_session:
            try:
                import asyncio
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_session.close())
            except RuntimeError:
                # No running event loop, use synchronous close
                pass
            self._async_session = None

    async def async_close(self):
        """异步关闭连接"""
        if self._async_session:
            await self._async_session.close()
            self._async_session = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.async_close()
        return False
