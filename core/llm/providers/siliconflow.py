"""
SiliconFlow Provider 实现
"""
from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class SiliconFlowProvider(BaseProvider):
    """SiliconFlow LLM Provider"""

    provider_type = "siliconflow"
    provider_name = "SiliconFlow"

    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        super().__init__(config, provider_name)
        self._chat_endpoint = "/chat/completions"
        self._embedding_endpoint = "/embeddings"
        self._models_endpoint = "/models"

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """
        解析 SiliconFlow API 返回的模型列表

        API 文档: https://docs.siliconflow.cn/cn/api-reference/models/get-model-list

        响应格式:
        {
            "object": "list",
            "data": [
                {
                    "id": "Qwen/Qwen2.5-72B-Instruct",
                    "object": "model",
                    "created": 1677610602,
                    "owned_by": "Qwen"
                }
            ]
        }
        """
        models = []

        for model_data in response.get("data", []):
            model_id = model_data.get("id", "")

            if not model_id:
                continue

            # 根据模型 ID 判断类型
            # Embedding 模型: 包含 embedding 或 bge-
            is_embedding = "embedding" in model_id.lower() or "bge-" in model_id.lower()
            # Vision 模型: 包含 vision, vl, 4v, qwen2-vl, cogview 等
            is_vision = any(x in model_id.lower() for x in ["vision", "vl", "4v", "cogview", "qwen2-vl"])
            # Rerank 模型: 包含 rerank
            is_rerank = "rerank" in model_id.lower()

            if is_embedding:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False,
                    extra=model_data
                ))
            elif is_rerank:
                # Rerank 模型作为 chat 模型处理（实际支持情况取决于具体模型）
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=False,
                    support_vision=False,
                    extra=model_data
                ))
            else:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=is_vision,
                    extra=model_data
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

        payload.update(kwargs)
        return payload

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应"""
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
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应"""
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
                    extra=data
                )
        return ChatResponse(
            content="",
            model=data.get("model", ""),
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
