"""
Ollama Provider 实现
"""
from typing import Dict, Any, Optional, List, Union, AsyncIterator

from .base import BaseProvider
from ..provider_interface import Message, ChatResponse, EmbeddingResponse, ModelInfo
from ..exceptions import APIError


class OllamaProvider(BaseProvider):
    """Ollama LLM Provider (本地部署)"""

    provider_type = "ollama"
    provider_name = "Ollama"

    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        super().__init__(config, provider_name)
        self._chat_endpoint = "/api/chat"
        self._generate_endpoint = "/api/generate"
        self._embedding_endpoint = "/api/embeddings"
        self._models_endpoint = "/api/tags"
        # Ollama 默认端口
        if not self.base_url:
            self.base_url = "http://localhost:11434"

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """
        解析 Ollama API 返回的模型列表

        API 端点: GET /api/tags

        响应格式:
        {
            "models": [
                {
                    "name": "llama3.1",
                    "model": "llama3.1:latest",
                    "size": 3826793472,
                    "digest": "...",
                    "details": {
                        "parent_model": "",
                        "format": "gguf",
                        "family": "llama",
                        "families": ["llama"],
                        "parameter_size": "7B",
                        "quantization_level": "Q4_0"
                    }
                }
            ]
        }
        """
        models = []

        for model_data in response.get("models", []):
            model_id = model_data.get("name", "")

            if not model_id:
                continue

            # 判断是否为 Vision 模型
            # Ollama vision 模型通常名称包含 "vision" 或 "llava"
            is_vision = "vision" in model_id.lower() or "llava" in model_id.lower()

            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=True,
                support_streaming=True,
                support_embedding=True,
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

        # 转换消息格式为 Ollama 格式
        ollama_messages = []
        for msg in prepared_messages:
            ollama_msg = {
                "role": msg["role"],
                "content": msg["content"]
            }
            # 处理多模态图片
            if "images" in msg and msg["images"]:
                ollama_msg["images"] = msg["images"]
            ollama_messages.append(ollama_msg)

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        payload.update(kwargs)
        return payload

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应"""
        message = response.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("thinking", ""),
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应"""
        message = data.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("thinking", ""),
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

        model_name = model or self.embedding_model

        embeddings = []
        for text in texts:
            payload = {
                "model": model_name,
                "prompt": text,
            }
            payload.update(kwargs)

            response = self._make_request("POST", self._embedding_endpoint, data=payload)

            embeddings.append(EmbeddingResponse(
                embedding=response.get("embedding", []),
                model=model_name,
                extra=response
            ))

        return embeddings

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

        model_name = model or self.embedding_model

        embeddings = []
        for text in texts:
            payload = {
                "model": model_name,
                "prompt": text,
            }
            payload.update(kwargs)

            response = await self._make_async_request("POST", self._embedding_endpoint, data=payload)

            embeddings.append(EmbeddingResponse(
                embedding=response.get("embedding", []),
                model=model_name,
                extra=response
            ))

        return embeddings

    async def async_get_models(self) -> List[ModelInfo]:
        """异步获取可用模型列表"""
        return self.get_models()

    def validate_config(self) -> bool:
        """验证配置"""
        # Ollama 不需要 API Key，只需要确保 base_url 可用
        return bool(self.base_url)
