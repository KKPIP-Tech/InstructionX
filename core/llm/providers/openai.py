"""OpenAI 兼容 Provider 实现模块

该模块提供标准 OpenAI API 的接口实现，支持用户通过配置自定义模型列表。
继承自 BaseProvider，实现聊天、嵌入、流式输出等功能。

支持用户自定义模型列表（custom_models），使其可以适配任何 OpenAI 兼容端点：
- OpenAI 官方 API
- DeepSeek API
- vLLM / LocalAI 等本地部署
- 其他 OpenAI 兼容服务

Classes:
    OpenAIProvider: OpenAI 兼容提供商实现

使用示例:
    >>> from core.llm.providers.openai import OpenAIProvider
    >>> config = {
    ...     "api_key": "xxx",
    ...     "base_url": "https://api.openai.com/v1",
    ...     "custom_models": [
    ...         {"id": "gpt-4o", "name": "GPT-4o", "context_length": 128000}
    ...     ]
    ... }
    >>> provider = OpenAIProvider(config, provider_name="openai")
    >>> response = provider.chat([Message("user", "你好")])
"""

from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class OpenAIProvider(BaseProvider):
    """OpenAI 兼容 LLM Provider

    标准 OpenAI API 提供商实现，支持配置驱动的自定义模型列表。
    用户可通过 `custom_models` 配置项定义任意模型，使其可以适配各种
    OpenAI 兼容端点。

    Class Attributes:
        provider_type: 提供商类型标识 ("openai")
        provider_name: 提供商显示名称 ("OpenAI")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (True)

    API 端点:
        - /chat/completions: 聊天完成
        - /embeddings: 嵌入生成
        - /models: 模型列表

    使用示例:
        >>> from core.llm.providers.openai import OpenAIProvider
        >>> from core.llm import Message
        >>> config = {
        ...     "api_key": "your_api_key",
        ...     "chat_model": "gpt-4o",
        ...     "custom_models": [
        ...         {"id": "gpt-4o", "name": "GPT-4o", "context_length": 128000}
        ...     ]
        ... }
        >>> provider = OpenAIProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    provider_type = "openai"
    provider_name = "OpenAI"

    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 OpenAI Provider

        Args:
            config: 提供商配置字典，可包含 custom_models 定义自定义模型
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        self._chat_endpoint = "/chat/completions"
        self._embedding_endpoint = "/embeddings"
        self._models_endpoint = "/models"

    # ==================== 模型列表 ====================

    def get_models(self) -> List[ModelInfo]:
        """获取可用模型列表

        优先从配置中的 custom_models 读取用户自定义模型列表。
        若 custom_models 为空，则从 API 获取。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        custom_models = self._get_custom_models_from_config()
        if custom_models:
            return custom_models
        # 没有自定义模型，从 API 获取
        return self.fetch_and_cache_models()

    def refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """刷新模型列表

        若配置中有 custom_models，直接返回（配置驱动不需要刷新）。
        否则从 API 获取。

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        custom_models = self._get_custom_models_from_config()
        if custom_models:
            return custom_models
        return super().refresh_models(force=force)

    def _get_custom_models_from_config(self) -> List[ModelInfo]:
        """从配置中读取自定义模型列表

        Returns:
            List[ModelInfo]: 自定义模型列表，如果没有则返回空列表
        """
        config = getattr(self, 'config', {}) or {}
        custom_models_data = config.get("custom_models", [])
        if not custom_models_data:
            return []

        models = []
        for model_data in custom_models_data:
            if not model_data.get("id"):
                continue
            model_info = ModelInfo.from_dict(model_data)
            model_info.provider = self.provider_type
            models.append(model_info)
        return models

    # ==================== 模型能力推断 ====================

    VISION_KEYWORDS = ["vision", "gpt-4o", "4o"]
    FC_KEYWORDS = ["gpt-4", "o3", "o1"]
    EMBEDDING_KEYWORDS = ["embedding", "embed"]

    def _infer_capabilities(self, model_id: str) -> Dict[str, Any]:
        """从模型 ID 推断模型能力

        Args:
            model_id: 模型 ID

        Returns:
            Dict[str, Any]: 能力字典
        """
        mid = model_id.lower()
        is_embedding = any(k in mid for k in self.EMBEDDING_KEYWORDS)
        return {
            "support_vision": any(k in mid for k in self.VISION_KEYWORDS) and not is_embedding,
            "support_function_calling": any(k in mid for k in self.FC_KEYWORDS) and not is_embedding,
            "context_length": self._estimate_context_length(model_id),
        }

    def _estimate_context_length(self, model_id: str) -> Optional[int]:
        """根据模型名称估算上下文窗口大小

        Args:
            model_id: 模型 ID

        Returns:
            Optional[int]: 估算的上下文长度，不知道则返回 None
        """
        KNOWN_CONTEXTS = {
            "gpt-4o": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4": 8192,
            "gpt-3.5-turbo": 16385,
            "text-embedding": 8192,
        }
        mid = model_id.lower()
        for name, ctx in KNOWN_CONTEXTS.items():
            if name in mid:
                return ctx
        return None

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 OpenAI API 返回的模型列表

        从 OpenAI /models API 响应中提取模型信息。

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []

        for model_data in response.get("data", []):
            model_id = model_data.get("id", "")

            if not model_id:
                continue

            caps = self._infer_capabilities(model_id)
            is_embedding = any(k in model_id.lower() for k in self.EMBEDDING_KEYWORDS)

            if is_embedding:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False,
                    support_function_calling=False,
                    context_length=caps["context_length"],
                    provider="openai",
                    extra=model_data
                ))
            else:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=caps["support_vision"],
                    support_function_calling=caps["support_function_calling"],
                    context_length=caps["context_length"],
                    provider="openai",
                    extra=model_data
                ))

        return models

    # ==================== 请求载荷准备 ====================

    def _prepare_chat_payload(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """准备聊天请求载荷

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            stream: 是否流式输出
            **kwargs: 其他参数

        Returns:
            Dict[str, Any]: 请求载荷字典
        """
        prepared_messages = self._prepare_messages(messages)

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": prepared_messages,
            "temperature": temperature,
            "stream": stream,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        payload.update(kwargs)
        return payload

    # ==================== 响应解析 ====================

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            APIError: 当响应为空时抛出
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("Empty response from OpenAI")

        choice = choices[0]
        message = choice.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content", ""),
            tool_calls=message.get("tool_calls", []),
            usage=self._parse_usage(response),
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应

        Args:
            data: 流式数据块

        Returns:
            ChatResponse: 聊天响应对象
        """
        if data.get("choices"):
            choices = data.get("choices", [])
            if choices:
                choice = choices[0]
                delta = choice.get("delta", {})
                return ChatResponse(
                    content=delta.get("content", ""),
                    model=data.get("model", ""),
                    role=delta.get("role", "assistant"),
                    reasoning_content=delta.get("reasoning_content", ""),
                    tool_calls=delta.get("tool_calls", []),
                    usage=self._parse_usage(data),
                    extra=data
                )
        return ChatResponse(
            content="",
            model=data.get("model", ""),
            tool_calls=[],
            usage=self._parse_usage(data),
            extra=data
        )

    # ==================== 同步 API ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）"""
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=False, **kwargs
        )
        response = self._make_request("POST", self._chat_endpoint, data=payload)
        return self._parse_chat_response(response)

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        callback=None,
        **kwargs
    ):
        """发送流式聊天请求（同步）"""
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=True, **kwargs
        )
        return self._make_stream_request(self._chat_endpoint, payload, callback)

    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求（同步）"""
        if isinstance(texts, str):
            texts = [texts]

        payload = {
            "model": model or self.embedding_model,
            "input": texts,
        }
        payload.update(kwargs)

        response = self._make_request("POST", self._embedding_endpoint, data=payload)

        embeddings = response.get("data", [])
        return [
            EmbeddingResponse(
                embedding=item.get("embedding", []),
                model=response.get("model", ""),
                extra=item
            )
            for item in embeddings
        ]

    # ==================== 异步 API ====================

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求"""
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=False, **kwargs
        )
        response = await self._make_async_request("POST", self._chat_endpoint, data=payload)
        return self._parse_chat_response(response)

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """异步发送流式聊天请求"""
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=True, **kwargs
        )
        async for response in self._make_async_stream_request(self._chat_endpoint, payload):
            yield response

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送嵌入请求"""
        if isinstance(texts, str):
            texts = [texts]

        payload = {
            "model": model or self.embedding_model,
            "input": texts,
        }
        payload.update(kwargs)

        response = await self._make_async_request("POST", self._embedding_endpoint, data=payload)

        embeddings = response.get("data", [])
        return [
            EmbeddingResponse(
                embedding=item.get("embedding", []),
                model=response.get("model", ""),
                extra=item
            )
            for item in embeddings
        ]

    async def async_get_models(self) -> List[ModelInfo]:
        """异步获取可用模型列表"""
        return self.get_models()
