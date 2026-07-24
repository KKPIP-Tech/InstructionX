"""OpenAI 兼容 Provider 实现模块

该模块提供标准 OpenAI API 的接口实现，支持用户通过配置自定义模型列表。
继承自 BaseProvider，聊天、嵌入、流式输出等通用逻辑复用基类模板方法，
本模块仅保留 OpenAI 特有的自定义模型列表、能力推断、
流式 tool_calls 聚合、图像生成与语音合成实现。

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

import requests

from .base import BaseProvider, _keyword_in_model
from ..provider_interface import Message, ChatResponse, ModelInfo
from ..exceptions import (
    APIError, AuthenticationError, RateLimitError, ConfigurationError,
    ConnectionError, TimeoutError
)
from ..types import ImageResult, AudioResult


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
        - /images/generations: 图像生成
        - /audio/speech: 语音合成

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

    # OpenAI 兼容 API 支持流式 usage 统计
    _supports_stream_usage = True

    # 图像生成 / 语音合成默认模型（可被配置 image_model / tts_model 覆盖）
    DEFAULT_IMAGE_MODEL = "dall-e-3"
    DEFAULT_TTS_MODEL = "tts-1"
    DEFAULT_TTS_VOICE = "alloy"

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
        self._image_endpoint = "/images/generations"
        self._speech_endpoint = "/audio/speech"

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

    # 关键词按非字母数字边界匹配，避免 "4o" 之类的子串误判
    VISION_KEYWORDS = ["vision", "gpt-4o", "4o"]
    FC_KEYWORDS = ["gpt-4", "gpt-4o", "o3", "o1"]
    EMBEDDING_KEYWORDS = ["embedding", "embed"]

    def _infer_capabilities(self, model_id: str) -> Dict[str, Any]:
        """从模型 ID 推断模型能力

        Args:
            model_id: 模型 ID

        Returns:
            Dict[str, Any]: 能力字典
        """
        mid = model_id.lower()
        is_embedding = any(_keyword_in_model(mid, k) for k in self.EMBEDDING_KEYWORDS)
        return {
            "support_vision": any(_keyword_in_model(mid, k) for k in self.VISION_KEYWORDS) and not is_embedding,
            "support_function_calling": any(_keyword_in_model(mid, k) for k in self.FC_KEYWORDS) and not is_embedding,
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
            is_embedding = any(_keyword_in_model(model_id, k) for k in self.EMBEDDING_KEYWORDS)

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

    # ==================== 流式 tool_calls 聚合 ====================

    @staticmethod
    def _merge_tool_call_deltas(acc: Dict[int, Dict[str, Any]], deltas: List[Dict]) -> None:
        """按 index 聚合流式 tool_calls 增量分片

        OpenAI 流式响应中 tool_calls 以分片形式下发，id/name 仅在首片出现，
        arguments 为 JSON 字符串的连续片段，需要按 index 拼接。

        Args:
            acc: 聚合状态字典（index -> 完整 tool_call）
            deltas: 当前块的 tool_calls 增量列表
        """
        for delta in deltas:
            index = delta.get("index", 0)
            slot = acc.setdefault(index, {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            })
            if delta.get("id"):
                slot["id"] = delta["id"]
            if delta.get("type"):
                slot["type"] = delta["type"]
            function = delta.get("function") or {}
            if function.get("name"):
                slot["function"]["name"] += function["name"]
            if function.get("arguments"):
                slot["function"]["arguments"] += function["arguments"]

    def _stream_with_tool_call_aggregation(self, stream):
        """包装流式生成器，末块返回聚合后的完整 tool_calls 列表

        采用"前瞻一块"缓冲：每读入新块先产出上一块，流结束时把聚合的
        完整 tool_calls 挂到最后一个响应块上再产出。这样消费方在末块
        被 yield 的那一刻即可读到完整 tool_calls（而不是像旧实现那样
        在末块已产出后才回填，导致永远读不到）。

        中间块的 tool_calls 增量分片被聚合缓存，不再逐片外泄。

        Args:
            stream: 原始流式响应生成器

        Yields:
            ChatResponse: 聊天响应块（末块 yield 时即带完整 tool_calls）
        """
        acc: Dict[int, Dict[str, Any]] = {}
        pending: Optional[ChatResponse] = None
        for chunk in stream:
            if pending is not None:
                yield pending
            if chunk.tool_calls:
                self._merge_tool_call_deltas(acc, chunk.tool_calls)
                chunk.tool_calls = []
            pending = chunk
        if pending is not None:
            if acc:
                pending.tool_calls = [acc[i] for i in sorted(acc)]
            yield pending

    async def _astream_with_tool_call_aggregation(self, stream) -> AsyncIterator[ChatResponse]:
        """异步版本的流式 tool_calls 聚合包装

        与同步版本一致采用"前瞻一块"缓冲：末块被 yield 时即携带
        聚合后的完整 tool_calls，中间块的增量分片不外泄。

        Args:
            stream: 原始异步流式响应迭代器

        Yields:
            ChatResponse: 聊天响应块（末块 yield 时即带完整 tool_calls）
        """
        acc: Dict[int, Dict[str, Any]] = {}
        pending: Optional[ChatResponse] = None
        async for chunk in stream:
            if pending is not None:
                yield pending
            if chunk.tool_calls:
                self._merge_tool_call_deltas(acc, chunk.tool_calls)
                chunk.tool_calls = []
            pending = chunk
        if pending is not None:
            if acc:
                pending.tool_calls = [acc[i] for i in sorted(acc)]
            yield pending

    # ==================== 同步 API ====================

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

        与基类实现的区别在于对流式 tool_calls 增量按 index 聚合，
        末块返回完整的 tool_calls 列表。
        """
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=True, **kwargs
        )
        stream = self._make_stream_request(self._chat_endpoint, payload, callback)
        return self._stream_with_tool_call_aggregation(stream)

    # ==================== 异步 API ====================

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """异步发送流式聊天请求

        与基类实现的区别在于对流式 tool_calls 增量按 index 聚合，
        末块返回完整的 tool_calls 列表。
        """
        payload = self._prepare_chat_payload(
            messages, model, temperature, max_tokens, stream=True, **kwargs
        )
        stream = self._make_async_stream_request(self._chat_endpoint, payload)
        async for chunk in self._astream_with_tool_call_aggregation(stream):
            yield chunk

    # ==================== 多模态：图像生成 / 语音合成 ====================

    def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: Optional[str] = None,
        **kwargs
    ) -> ImageResult:
        """生成图像（POST /images/generations）

        Args:
            prompt: 图像描述提示词
            model: 图像生成模型（默认取配置 image_model 或 dall-e-3）
            size: 图像尺寸（如 "1024x1024"）
            **kwargs: 其他 API 参数（如 quality、n）

        Returns:
            ImageResult: 图像生成结果（url 或 base64 至少其一有值）

        Raises:
            ConfigurationError: 未配置图像生成模型时抛出
        """
        model = model or self.config.get("image_model") or self.DEFAULT_IMAGE_MODEL
        if not model:
            raise ConfigurationError(
                "未配置图像生成模型，请在提供商配置中设置 image_model "
                "（如 dall-e-3）或调用时传入 model 参数"
            )

        payload: Dict[str, Any] = {"model": model, "prompt": prompt}
        if size:
            payload["size"] = size
        payload.update(kwargs)
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        response = self._make_request("POST", self._image_endpoint, data=payload)

        data = response.get("data") or []
        item = data[0] if data else {}
        return ImageResult(
            url=item.get("url"),
            base64=item.get("b64_json"),
            revised_prompt=item.get("revised_prompt"),
            model=model,
            provider=self.provider_type,
        )

    def text_to_speech(
        self,
        text: str,
        model: Optional[str] = None,
        voice: Optional[str] = None,
        **kwargs
    ) -> AudioResult:
        """语音合成（POST /audio/speech，二进制响应）

        Args:
            text: 要合成的文本
            model: TTS 模型（默认取配置 tts_model 或 tts-1）
            voice: 声音名称（默认取配置 tts_voice 或 alloy）
            **kwargs: 其他 API 参数（如 response_format、speed）

        Returns:
            AudioResult: 语音合成结果（audio_data 为音频字节流）

        Raises:
            ConfigurationError: 未配置 TTS 模型时抛出
            AuthenticationError: API 密钥无效（401）
            RateLimitError: 请求频率超限（429）
            APIError: 其他 API 错误
        """
        model = model or self.config.get("tts_model") or self.DEFAULT_TTS_MODEL
        if not model:
            raise ConfigurationError(
                "未配置语音合成模型，请在提供商配置中设置 tts_model "
                "（如 tts-1）或调用时传入 model 参数"
            )
        voice = voice or self.config.get("tts_voice") or self.DEFAULT_TTS_VOICE

        payload: Dict[str, Any] = {"model": model, "input": text, "voice": voice}
        payload.update(kwargs)
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        url = f"{self.base_url}{self._speech_endpoint}"
        try:
            with self._session_lock:
                response = self._get_session().post(
                    url,
                    json=payload,
                    timeout=(self.connect_timeout, self.timeout),
                )

            if response.status_code == 401:
                self.last_error = "Invalid API key"
                raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
            elif response.status_code == 429:
                self.last_error = "Rate limit exceeded"
                raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
            elif response.status_code >= 400:
                self.last_error = f"API request failed: {response.text}"
                raise APIError(
                    f"API request failed: {response.text}",
                    status_code=response.status_code,
                    provider=self.provider_type
                )

            self.last_error = None
            return AudioResult(
                audio_data=response.content,
                model=model,
                provider=self.provider_type,
            )
        except requests.exceptions.Timeout:
            self.last_error = "Request timeout"
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except requests.exceptions.ConnectionError:
            self.last_error = "Connection failed"
            raise ConnectionError("Connection failed", provider=self.provider_type)
