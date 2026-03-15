"""
MiniMax Provider 实现
"""
from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class MiniMaxProvider(BaseProvider):
    """MiniMax LLM Provider"""

    provider_type = "minimax"
    provider_name = "MiniMax"

    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = False  # MiniMax 不支持 Vision（文档明确说明"当前不支持图像和音频类型的输入"）

    # MiniMax 官方没有提供模型列表 API，使用预设列表
    # 参考: https://platform.minimaxi.com/docs/api-reference/api-overview
    CHAT_MODELS = [
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

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        super().__init__(config, provider_name)
        self._chat_endpoint = "/text/chatcompletion_v2"
        self._embedding_endpoint = "/embeddings/embedding-async_v2"
        # MiniMax 没有模型列表 API，使用预设列表

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 MiniMax API 返回的模型列表"""
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

    def _prepare_chat_payload(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """准备聊天请求载荷"""
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

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应"""
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
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应"""
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
        """发送聊天请求"""
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
        """发送流式聊天请求"""
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
        """发送嵌入请求"""
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
