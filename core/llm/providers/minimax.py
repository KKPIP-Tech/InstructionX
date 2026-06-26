"""MiniMax Provider 实现模块

该模块提供 MiniMax 大语言模型的接口实现。
继承自 BaseProvider，实现聊天、嵌入、流式输出等功能。

MiniMax API 文档: https://platform.minimaxi.com/docs/api-reference

支持的模型:
    - CHAT_MODELS: 文本聊天模型（MiniMax-M2.5, MiniMax-M2.1 等）
    - EMBEDDING_MODELS: 向量嵌入模型（embedding-2）

Classes:
    MiniMaxProvider: MiniMax 提供商实现

使用示例:
    >>> from core.llm.providers.minimax import MiniMaxProvider
    >>> config = {"api_key": "xxx", "base_url": "https://api.minimax.chat/v1"}
    >>> provider = MiniMaxProvider(config, provider_name="minimax")
    >>> response = provider.chat([Message("user", "你好")])
"""

from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class MiniMaxProvider(BaseProvider):
    """MiniMax LLM Provider

    MiniMax 大语言模型提供商实现，支持文本聊天、嵌入生成等功能。
    由于 MiniMax 官方没有提供模型列表 API，使用预设模型列表。

    Class Attributes:
        provider_type: 提供商类型标识 ("minimax")
        provider_name: 提供商显示名称 ("MiniMax")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (False - 当前不支持图像和音频输入)
        CHAT_MODELS: 文本聊天模型列表
        EMBEDDING_MODELS: 向量嵌入模型列表
        MODEL_DETAILS: 预设模型详细信息

    API 端点:
        - /text/chatcompletion_v2: 聊天完成
        - /embeddings/embedding_async_v2: 嵌入生成

    使用示例:
        >>> from core.llm.providers.minimax import MiniMaxProvider
        >>> from core.llm import Message
        >>> config = {"api_key": "your_api_key", "chat_model": "MiniMax-M2.5"}
        >>> provider = MiniMaxProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "minimax"
    provider_name = "MiniMax"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    # MiniMax 不支持 Vision（官方文档明确说明"当前不支持图像和音频类型的输入"）
    support_vision = False

    # ==================== 预设模型列表 ====================

    # MiniMax 官方没有提供模型列表 API，使用预设列表
    # 参考: https://platform.minimaxi.com/docs/api-reference/api-overview
    CHAT_MODELS = [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
        "MiniMax-M2.1-highspeed",
        "MiniMax-M2",
    ]

    EMBEDDING_MODELS = [
        "embedding-2",
    ]

    # 预设模型详情（从官方文档获取）
    MODEL_DETAILS = {
        "MiniMax-M2.7": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "MiniMax 旗舰大模型，全面升级推理与多模态能力"
        },
        "MiniMax-M2.7-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.7 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2.5": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "顶尖性能与极致性价比，轻松驾驭复杂任务"
        },
        "MiniMax-M2.5-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.5 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2.1": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "强大多语言编程能力，全面升级编程体验"
        },
        "MiniMax-M2.1-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.1 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "专为高效编码与Agent工作流而生"
        },
        "embedding-2": {
            "context_length": None,
            "support_function_calling": False,
            "description": "Embedding 模型"
        },
    }

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 MiniMax Provider

        Args:
            config: 提供商配置字典
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        # API 端点定义
        self._chat_endpoint = "/text/chatcompletion_v2"
        self._embedding_endpoint = "/embeddings/embedding-async_v2"
        # MiniMax 没有模型列表 API，使用预设列表

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 MiniMax API 返回的模型列表

        从 MiniMax API 响应中提取模型信息，并根据模型类型判断支持的功能。

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []

        for model_data in response.get("data", []):
            model_id = model_data.get("model_id", "")
            model_type = model_data.get("model_type", "")

            # 根据模型类型判断支持的功能
            if model_type in ["chat", "text"]:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=True
                ))
            elif model_type == "embedding":
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False
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

        准备发送给 MiniMax API 的请求参数。
        特别注意：MiniMax 使用 base64 编码的图片，需要特殊处理。

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

        # 处理多模态消息
        for msg in prepared_messages:
            if "images" in msg and msg["images"]:
                # MiniMax 使用 base64 编码的图片
                msg["image_url"] = [{"url": f"data:image/jpeg;base64,{img}"} for img in msg["images"]]
                del msg["images"]

        payload.update(kwargs)
        return payload

    # ==================== 响应解析 ====================

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应

        从 MiniMax API 响应中提取聊天内容和思考过程。

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            APIError: 当响应为空时抛出
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("Empty response from MiniMax")

        choice = choices[0]
        message = choice.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content", ""),
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

        Raises:
            APIError: 当响应为空时抛出
        """
        choices = data.get("choices", [])
        if not choices:
            raise APIError("Empty stream chunk from MiniMax")

        choice = choices[0]
        delta = choice.get("delta", {})

        return ChatResponse(
            content=delta.get("content", ""),
            model=data.get("model", ""),
            role=delta.get("role", "assistant"),
            reasoning_content=delta.get("reasoning_content", ""),
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

        向 MiniMax API 发送聊天请求，获取完整的响应文本。

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

        向 MiniMax API 发送流式聊天请求，逐块获取响应。

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

        由于使用预设模型列表，直接返回同步版本的结果。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.get_models()