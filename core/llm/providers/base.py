"""
Base Provider 基类实现
"""
import json
import requests
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List, Union, Callable, AsyncIterator
from abc import ABC

from ..provider_interface import (
    ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo
)
from ..exceptions import (
    APIError, AuthenticationError, RateLimitError,
    InvalidRequestError, ConnectionError, TimeoutError
)


class BaseProvider(ILLM):
    """LLM Provider 基类"""

    # 子类需要定义这些类属性
    _models_endpoint: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        super().__init__(config)
        self.api_key = config.get("api_key", "") if config else ""
        self.base_url = config.get("base_url", "").rstrip("/")
        self.chat_model = config.get("chat_model", "") if config else ""
        self.embedding_model = config.get("embedding_model", "") if config else ""
        self.timeout = config.get("timeout", 60) if config else 60
        self._session = None
        self._async_session = None
        self._provider_name = provider_name  # 用于缓存标识

    # ==================== 模型获取与缓存 ====================

    def _fetch_models_from_api(self) -> List[ModelInfo]:
        """
        从 API 获取模型列表 - 子类需要重写此方法

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        if not self.api_key or not self._models_endpoint:
            return []

        try:
            response = self._make_request("GET", self._models_endpoint)
            return self._parse_models_response(response)
        except Exception:
            return []

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """
        解析 API 返回的模型列表 - 子类需要重写此方法

        Args:
            response: API 响应

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return []

    def fetch_and_cache_models(self) -> List[ModelInfo]:
        """
        获取模型列表并缓存

        优先从 API 获取，如果成功则缓存结果
        如果 API 获取失败，尝试从缓存加载
        如果缓存也没有，从配置中读取默认模型

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        # 尝试从 API 获取
        api_models = self._fetch_models_from_api()

        if api_models:
            # API 获取成功，保存到缓存
            self._save_models_to_cache(api_models)
            return api_models

        # API 获取失败，尝试从缓存加载
        cached_models = self._load_models_from_cache()
        if cached_models:
            return cached_models

        # 缓存也没有，从配置中读取默认模型
        return self._get_default_models_from_config()

    def _get_default_models_from_config(self) -> List[ModelInfo]:
        """
        从配置中读取默认模型

        当 API 和缓存都无法获取时使用
        """
        models = []

        # 从配置中读取 chat_model
        if self.chat_model:
            models.append(ModelInfo(
                id=self.chat_model,
                name=self.chat_model,
                support_chat=True,
                support_streaming=True,
                support_embedding=False,
                support_vision=False
            ))

        # 从配置中读取 embedding_model
        if self.embedding_model:
            models.append(ModelInfo(
                id=self.embedding_model,
                name=self.embedding_model,
                support_chat=False,
                support_streaming=False,
                support_embedding=True,
                support_vision=False
            ))

        return models

    def get_models(self) -> List[ModelInfo]:
        """
        获取可用模型列表（统一实现）

        如果子类定义了 CHAT_MODELS 或 EMBEDDING_MODELS，则使用预设模型列表
        否则从 API 获取并缓存，失败则尝试缓存

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        # 检查是否有预设模型列表
        if hasattr(self, 'CHAT_MODELS') or hasattr(self, 'EMBEDDING_MODELS'):
            return self._get_fallback_models()

        # 从 API 获取并缓存
        models = self.fetch_and_cache_models()

        # API 和缓存都没有，返回空列表
        return models

    def _get_fallback_models(self) -> List[ModelInfo]:
        """
        获取预设模型列表（子类可重写）

        当子类定义了 CHAT_MODELS 或 EMBEDDING_MODELS 时使用
        """
        models = []

        # 检查是否有 MODEL_DETAILS
        model_details = getattr(self, 'MODEL_DETAILS', {})

        # 获取 CHAT_MODELS（兼容子类可能没有定义的情况）
        chat_models = getattr(self, 'CHAT_MODELS', [])
        for model_id in chat_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=True,
                support_streaming=True,
                support_embedding=False,
                support_vision=False,
                support_function_calling=details.get('support_function_calling', False),
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 EMBEDDING_MODELS
        embedding_models = getattr(self, 'EMBEDDING_MODELS', [])
        for model_id in embedding_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=True,
                support_vision=False,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 VISION_MODELS
        vision_models = getattr(self, 'VISION_MODELS', [])
        for model_id in vision_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=False,
                support_vision=True,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 IMAGE_MODELS (GLM 专用)
        image_models = getattr(self, 'IMAGE_MODELS', [])
        for model_id in image_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=False,
                support_vision=False,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 VIDEO_MODELS (GLM 专用)
        video_models = getattr(self, 'VIDEO_MODELS', [])
        for model_id in video_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=False,
                support_vision=False,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 AUDIO_MODELS (GLM 专用)
        audio_models = getattr(self, 'AUDIO_MODELS', [])
        for model_id in audio_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=False,
                support_vision=False,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        # 获取 OTHER_MODELS (GLM 专用)
        other_models = getattr(self, 'OTHER_MODELS', [])
        for model_id in other_models:
            details = model_details.get(model_id, {})
            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=False,
                support_streaming=False,
                support_embedding=False,
                support_vision=False,
                support_function_calling=False,
                context_length=details.get('context_length'),
                description=details.get('description', '')
            ))

        return models

    def refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """
        刷新模型列表

        Args:
            force: 是否强制从 API 刷新（忽略缓存）

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        # 如果有预设模型列表，直接使用预设列表
        if hasattr(self, 'CHAT_MODELS') or hasattr(self, 'EMBEDDING_MODELS'):
            return self._get_fallback_models()

        if force:
            # 强制从 API 刷新
            models = self._fetch_models_from_api()
            if models:
                self._save_models_to_cache(models)
                return models
            # API 拉取失败，尝试从缓存加载
            cached_models = self._load_models_from_cache()
            if cached_models:
                return cached_models
            return []

        # 正常获取（优先缓存）
        return self.get_models()

    async def async_get_models(self) -> List[ModelInfo]:
        """异步获取模型列表"""
        return self.get_models()

    async def async_refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """异步刷新模型列表"""
        return self.refresh_models(force=force)

    def _save_models_to_cache(self, models: List[ModelInfo]) -> None:
        """保存模型列表到缓存"""
        if not self._provider_name:
            return

        try:
            from ..config import LLMConfig
            config = LLMConfig()
            models_data = [m.to_dict() for m in models]
            config.save_models_cache(self._provider_name, models_data)
        except Exception:
            pass

    def _load_models_from_cache(self) -> List[ModelInfo]:
        """从缓存加载模型列表"""
        if not self._provider_name:
            return []

        try:
            from ..config import LLMConfig
            config = LLMConfig()
            cached_data = config.load_models_cache(self._provider_name)
            if cached_data:
                return [ModelInfo.from_dict(m) for m in cached_data]
        except Exception:
            pass

        return []

    # ==================== Function Calling 支持 ====================

    def _prepare_chat_payload(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        准备聊天请求载荷（基类统一实现）

        子类可以重写此方法以适配特定 Provider 的请求格式

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            stream: 是否流式输出
            tools: Function calling 工具定义列表
            **kwargs: 其他参数

        Returns:
            请求载荷字典
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

        # 添加 function calling 工具
        if tools:
            payload["tools"] = tools

        # 处理多模态消息（子类的 _prepare_chat_payload 可以覆盖此逻辑）
        prepared_messages = self._prepare_vision_messages(prepared_messages)

        payload["messages"] = prepared_messages
        payload.update(kwargs)
        return payload

    def _prepare_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        处理多模态消息 - 子类可重写

        默认实现不处理图片，子类如需支持 Vision 需要重写此方法
        """
        return messages

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """
        解析聊天响应（基类统一实现）

        提取 content 和 tool_calls

        Args:
            response: API 响应

        Returns:
            ChatResponse 对象
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("Empty response from API")

        choice = choices[0]
        message = choice.get("message", {})

        # 提取 tool_calls（Function Calling）
        tool_calls = message.get("tool_calls", [])

        return ChatResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content", ""),
            tool_calls=tool_calls,
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """
        解析流式响应（基类统一实现）

        提取 content 和 tool_calls

        Args:
            data: 流式数据块

        Returns:
            ChatResponse 对象
        """
        # 处理 message 格式（可能是 delta 或 message）
        message = data.get("delta", data.get("message", {}))

        # 提取 tool_calls（Function Calling）
        tool_calls = message.get("tool_calls", [])

        # 流式结束标记
        if data.get("finish_reason") == "tool_calls":
            # Tool calling 完成
            pass

        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content", ""),
            tool_calls=tool_calls,
            extra=data
        )

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """
        解析 API 返回的模型列表（基类默认实现）

        子类可以重写此方法以适配特定 Provider 的响应格式

        Args:
            response: API 响应

        Returns:
            模型信息列表
        """
        # 默认实现尝试从通用字段解析
        models = []

        # 尝试多种常见的模型列表响应格式
        data = response.get("data", response.get("models", response.get("model_list", [])))

        for item in data:
            if isinstance(item, dict):
                model_id = item.get("id", item.get("model_id", item.get("model", "")))
                if model_id:
                    models.append(ModelInfo(
                        id=model_id,
                        name=model_id,
                        support_chat=True,
                        support_streaming=True,
                        support_embedding="embedding" in model_id.lower() or "bge" in model_id.lower(),
                        support_vision="vision" in model_id.lower() or "vl" in model_id.lower() or "4v" in model_id.lower(),
                        extra=item
                    ))

        return models

    # ==================== 同步请求方法 ====================

    def _get_session(self) -> requests.Session:
        """获取同步 HTTP Session"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Content-Type": "application/json",
            })
            if self.api_key:
                self._session.headers.update({
                    "Authorization": f"Bearer {self.api_key}"
                })
        return self._session

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """发起同步 HTTP 请求"""
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.timeout

        try:
            response = self._get_session().request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=timeout
            )

            if response.status_code == 401:
                raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
            elif response.status_code == 429:
                raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
            elif response.status_code >= 400:
                raise APIError(
                    f"API request failed: {response.text}",
                    status_code=response.status_code,
                    provider=self.provider_type
                )

            return response.json()

        except requests.exceptions.Timeout:
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except requests.exceptions.ConnectionError:
            raise ConnectionError("Connection failed", provider=self.provider_type)
        except requests.exceptions.RequestException as e:
            raise APIError(f"Request error: {str(e)}", provider=self.provider_type)

    # ==================== 异步请求方法 ====================

    async def _get_async_session(self) -> aiohttp.ClientSession:
        """获取异步 HTTP Session"""
        if self._async_session is None or self._async_session.closed:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._async_session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            )
        return self._async_session

    async def _make_async_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """发起异步 HTTP 请求"""
        url = f"{self.base_url}{endpoint}"
        timeout = timeout or self.timeout

        try:
            session = await self._get_async_session()
            async with session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:

                if response.status == 401:
                    raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                elif response.status == 429:
                    raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                elif response.status >= 400:
                    text = await response.text()
                    raise APIError(
                        f"API request failed: {text}",
                        status_code=response.status,
                        provider=self.provider_type
                    )

                return await response.json()

        except asyncio.TimeoutError:
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except aiohttp.ClientConnectorError:
            raise ConnectionError("Connection failed", provider=self.provider_type)
        except aiohttp.ClientError as e:
            raise APIError(f"Request error: {str(e)}", provider=self.provider_type)

    # ==================== 流式请求方法 ====================

    def _make_stream_request(
        self,
        endpoint: str,
        data: Dict,
        callback: Optional[Callable[[ChatResponse], None]] = None
    ):
        """发起同步流式请求（生成器）"""
        url = f"{self.base_url}{endpoint}"

        try:
            session = self._get_session()
            with session.post(url, json=data, stream=True, timeout=self.timeout) as response:
                if response.status_code == 401:
                    raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                elif response.status_code == 429:
                    raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                elif response.status_code >= 400:
                    raise APIError(
                        f"API request failed: {response.text}",
                        status_code=response.status_code,
                        provider=self.provider_type
                    )

                for line in response.iter_lines():
                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                break

                            try:
                                chunk_data = json.loads(data_str)
                                chat_response = self._parse_stream_response(chunk_data)
                                yield chat_response
                                if callback:
                                    callback(chat_response)
                            except json.JSONDecodeError:
                                continue

        except requests.exceptions.Timeout:
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except requests.exceptions.ConnectionError:
            raise ConnectionError("Connection failed", provider=self.provider_type)

    async def _make_async_stream_request(
        self,
        endpoint: str,
        data: Dict
    ) -> AsyncIterator[ChatResponse]:
        """发起异步流式请求"""
        url = f"{self.base_url}{endpoint}"

        try:
            session = await self._get_async_session()
            async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=self.timeout)) as response:
                if response.status == 401:
                    raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                elif response.status == 429:
                    raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                elif response.status >= 400:
                    text = await response.text()
                    raise APIError(
                        f"API request failed: {text}",
                        status_code=response.status,
                        provider=self.provider_type
                    )

                async for line in response.content:
                    if line:
                        line = line.decode('utf-8').strip()
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                break

                            try:
                                chunk_data = json.loads(data_str)
                                chat_response = self._parse_stream_response(chunk_data)
                                yield chat_response
                            except json.JSONDecodeError:
                                continue

        except asyncio.TimeoutError:
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except aiohttp.ClientConnectorError:
            raise ConnectionError("Connection failed", provider=self.provider_type)

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement _parse_stream_response")

    # ==================== 抽象方法实现 ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement chat method")

    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement embed method")

    # 注意: get_models 和 async_get_models 已在基类中实现
    # 子类如需自定义可重写 get_models() 或 _get_default_models_from_config()

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement async_chat method")

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """异步发送流式聊天请求 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement async_stream_chat method")

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送嵌入请求 - 子类需要重写"""
        raise NotImplementedError("Subclass must implement async_embed method")

    def validate_config(self) -> bool:
        """验证配置"""
        return bool(self.api_key or self.base_url)
