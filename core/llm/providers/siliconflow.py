"""SiliconFlow Provider 实现模块

该模块提供 SiliconFlow API 的接口实现。
继承自 BaseProvider，实现聊天、嵌入、流式输出等功能。

SiliconFlow API 文档: https://docs.siliconflow.cn/cn/api-reference/models/get-model-list

支持的模型类型:
    - 聊天模型：支持多种开源大模型（如 Qwen、DeepSeek 等）
    - 嵌入模型：支持 bge 系列等
    - 视觉模型：支持 vision、vl、4v 等
    - 重排序模型：支持 rerank

Classes:
    SiliconFlowProvider: SiliconFlow 提供商实现

使用示例:
    >>> from core.llm.providers.siliconflow import SiliconFlowProvider
    >>> config = {"api_key": "xxx", "base_url": "https://api.siliconflow.cn/v1"}
    >>> provider = SiliconFlowProvider(config, provider_name="siliconflow")
    >>> response = provider.chat([Message("user", "你好")])
"""

from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class SiliconFlowProvider(BaseProvider):
    """SiliconFlow LLM Provider

    SiliconFlow 大语言模型提供商实现，通过统一的 API 接口访问多种开源模型。
    支持从 API 动态获取模型列表。

    Class Attributes:
        provider_type: 提供商类型标识 ("siliconflow")
        provider_name: 提供商显示名称 ("SiliconFlow")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (True)

    API 端点:
        - /chat/completions: 聊天完成
        - /embeddings: 嵌入生成
        - /models: 模型列表

    使用示例:
        >>> from core.llm.providers.siliconflow import SiliconFlowProvider
        >>> from core.llm import Message
        >>> config = {"api_key": "your_api_key", "chat_model": "Pro/deepseek-ai/DeepSeek-V3"}
        >>> provider = SiliconFlowProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "siliconflow"
    provider_name = "SiliconFlow"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 SiliconFlow Provider

        Args:
            config: 提供商配置字典
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        # API 端点定义
        self._chat_endpoint = "/chat/completions"
        self._embedding_endpoint = "/embeddings"
        self._models_endpoint = "/models"

    # ==================== 模型能力推断 ====================

    VISION_KEYWORDS = ["vision", "vl", "4v", "qwen2-vl", "cogview", "llava", "internvl"]
    FC_KEYWORDS = ["function", "fc", "tool", "deepseek"]
    RERANK_KEYWORDS = ["rerank"]

    def _infer_capabilities(self, model_id: str) -> Dict[str, Any]:
        """从模型 ID 推断模型能力

        根据模型 ID 中的关键词判断视觉、函数调用等能力。

        Args:
            model_id: 模型 ID

        Returns:
            Dict[str, Any]: 能力字典
        """
        mid = model_id.lower()
        return {
            "support_vision": any(k in mid for k in self.VISION_KEYWORDS),
            "support_function_calling": any(k in mid for k in self.FC_KEYWORDS),
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
            "deepseek-v3": 64000,
            "deepseek-chat": 64000,
            "qwen3": 32000,
            "qwen-turbo": 8000,
            "qwen-plus": 32000,
            "qwen2.5-72b": 32000,
            "qwen2.5-32b": 32000,
            "qwen2.5-14b": 32000,
            "qwen2.5-7b": 8000,
            "glm-4": 128000,
            "kimi": 128000,
            "moonshot": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "claude-3": 200000,
            "claude-3.5": 200000,
            "yi-light": 16000,
            "yi-spark": 32000,
            "yi-large": 32000,
            "llama-3.1-70b": 128000,
            "llama-3.1-8b": 128000,
            "llama-3-70b": 8000,
            "llama-3-8b": 8000,
        }
        mid = model_id.lower()
        for name, ctx in KNOWN_CONTEXTS.items():
            if name in mid:
                return ctx
        return None

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 SiliconFlow API 返回的模型列表

        从 SiliconFlow API 响应中提取模型信息，并根据模型 ID 判断模型类型和上下文长度。

        模型类型判断规则:
            - 嵌入模型：模型 ID 包含 "embedding" 或 "bge-"
            - 视觉模型：模型 ID 包含 "vision", "vl", "4v", "cogview", "qwen2-vl"
            - 重排序模型：模型 ID 包含 "rerank"

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

            # 推断能力
            caps = self._infer_capabilities(model_id)

            # 根据模型 ID 判断类型
            is_embedding = "embedding" in model_id.lower() or "bge-" in model_id.lower()
            is_rerank = any(x in model_id.lower() for x in self.RERANK_KEYWORDS)

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
                    provider="siliconflow",
                    extra=model_data
                ))
            elif is_rerank:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=False,
                    support_vision=False,
                    support_function_calling=False,
                    context_length=caps["context_length"],
                    provider="siliconflow",
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
                    provider="siliconflow",
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

        准备发送给 SiliconFlow API 的请求参数。

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

        从 SiliconFlow API 响应中提取聊天内容和思考过程。

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            APIError: 当响应为空时抛出
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("Empty response from SiliconFlow")

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

        从流式数据块中提取聊天内容和思考过程。

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
        """发送聊天请求（同步）

        向 SiliconFlow API 发送聊天请求，获取完整的响应文本。

        Args:
            messages: 消息列表
            model: 模型名称（可选，默认使用配置中的模型）
            temperature: 温度参数（默认 0.7）
            max_tokens: 最大生成 token 数（可选）
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象
        """
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
        """发送流式聊天请求（同步）

        向 SiliconFlow API 发送流式聊天请求，逐块获取响应。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback: 可选的回调函数
            **kwargs: 其他参数

        Returns:
            生成器: 流式响应生成器
        """
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
        """发送嵌入请求（同步）

        将文本转换为向量嵌入。

        Args:
            texts: 单个文本或文本列表
            model: 嵌入模型名称（可选，默认使用配置中的模型）
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
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

    # 使用基类统一的 get_models 实现

    # ==================== 异步 API ====================

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象
        """
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
        """异步发送流式聊天请求

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Yields:
            ChatResponse: 聊天响应块
        """
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
        """异步发送嵌入请求

        Args:
            texts: 文本或文本列表
            model: 嵌入模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
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
        """异步获取可用模型列表

        返回同步版本的结果（因为底层也是调用同步 API）。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.get_models()