"""Base Provider 基类模块

该模块提供所有 LLM 提供商的抽象基类 BaseProvider，包含通用功能实现。
具体提供商只需继承此类并实现特定方法即可，大幅减少重复代码。

主要功能:
    - 同步/异步 HTTP 请求封装
    - 模型列表获取和缓存管理
    - 聊天/嵌入/流式请求基类实现
    - Function Calling 支持
    - 错误处理和异常转换

Classes:
    BaseProvider: LLM 提供商抽象基类

使用示例:
    >>> from core.llm.providers.base import BaseProvider
    >>> class MyProvider(BaseProvider):
    ...     provider_type = "my_provider"
    ...     # 实现具体方法...
"""

import json
import requests
import aiohttp
import asyncio
from typing import Dict, Any, Optional, List, Union, Callable, AsyncIterator
from abc import ABC

from ..provider_interface import (
    ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo
)
from ..exceptions import (
    APIError, AuthenticationError, RateLimitError,
    InvalidRequestError, ConnectionError, TimeoutError
)
from ..cache_adapter import get_cache_adapter, CacheAdapter
from ..types_cache import CacheInfo


class BaseProvider(ILLM):
    """LLM Provider 基类

    所有具体 LLM 提供商的基类，提供通用功能实现。
    子类只需继承此类并重写必要的方法即可。

    设计原则:
        - 模板方法模式：基类提供算法骨架，子类提供具体实现
        - 复用优先：通用的 HTTP 请求、缓存管理等功能在基类实现
        - 灵活性：子类可重写特定方法以适配不同 API 格式

    Class Attributes:
        _models_endpoint: 获取模型列表的 API 端点（子类需定义）

    Attributes:
        api_key: API 密钥
        base_url: API 基础 URL
        chat_model: 默认聊天模型
        embedding_model: 默认嵌入模型
        timeout: 请求超时时间（秒）
        _session: 同步 HTTP Session
        _async_session: 异步 HTTP Session
        _provider_name: 提供商名称（用于缓存标识）

    Example:
        >>> class MyProvider(BaseProvider):
        ...     provider_type = "my_provider"
        ...     provider_name = "My Provider"
        ...     _models_endpoint = "/v1/models"
        ...
        ...     def chat(self, messages, model=None, **kwargs):
        ...         # 实现聊天请求
        ...         pass
    """

    # 子类需要定义这些类属性
    _models_endpoint: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 BaseProvider

        Args:
            config: 提供商配置字典，包含 api_key、base_url、chat_model 等
            provider_name: 提供商名称，用于缓存标识
        """
        super().__init__(config)
        self.api_key = config.get("api_key", "") if config else ""
        self.base_url = config.get("base_url", "").rstrip("/")
        self.chat_model = config.get("chat_model", "") if config else ""
        self.embedding_model = config.get("embedding_model", "") if config else ""
        self.timeout = config.get("timeout", 60) if config else 60
        self._session = None
        self._async_session = None
        self._provider_name = provider_name  # 用于缓存标识
        self._cache_adapter: Optional[CacheAdapter] = None
        self._init_cache_adapter()

    def _init_cache_adapter(self) -> None:
        """初始化缓存适配器"""
        if self.config:
            cache_cfg = getattr(self.config, "cache_fields", None)
            self._cache_adapter = get_cache_adapter(self.provider_type, cache_cfg)
        else:
            self._cache_adapter = get_cache_adapter(self.provider_type)

    def _parse_cache_info(self, response: Dict) -> CacheInfo:
        """从响应中提取缓存信息"""
        if self._cache_adapter:
            return self._cache_adapter.extract_cache_info(response)
        return CacheInfo()

    # ==================== 模型获取与缓存 ====================

    def _fetch_models_from_api(self) -> List[ModelInfo]:
        """从 API 获取模型列表

        从提供商的 API 端点获取模型列表。子类可重写此方法以适配特定 API 格式。

        Returns:
            List[ModelInfo]: 模型信息列表

        Note:
            - 如果 api_key 或 _models_endpoint 为空，返回空列表
            - 请求失败时返回空列表，不抛出异常
        """
        if not self.api_key or not self._models_endpoint:
            return []

        try:
            response = self._make_request("GET", self._models_endpoint)
            return self._parse_models_response(response)
        except Exception:
            return []

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 API 返回的模型列表

        解析提供商 API 返回的模型列表数据。子类可重写此方法以适配特定格式。

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表

        Note:
            默认实现尝试从通用字段解析，子类通常需要重写
        """
        return []

    def fetch_and_cache_models(self) -> List[ModelInfo]:
        """获取模型列表并缓存

        优先从 API 获取模型列表，如果成功则缓存到本地文件。
        如果 API 获取失败，尝试从缓存加载。如果缓存也没有，从配置中读取默认模型。

        优先级顺序:
            1. API 获取（优先）
            2. 本地缓存
            3. 配置文件中的默认模型

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
        """从配置中读取默认模型

        当 API 和缓存都无法获取模型列表时，从配置中的 chat_model 和 embedding_model 字段创建默认模型信息。

        Returns:
            List[ModelInfo]: 从配置创建的默认模型列表
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
        """获取可用模型列表（统一实现）

        如果子类定义了 CHAT_MODELS 或 EMBEDDING_MODELS 类属性，则使用预设模型列表。
        否则从 API 获取并缓存，获取失败则尝试从缓存加载。

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
        """获取预设模型列表

        当子类定义了 CHAT_MODELS、EMBEDDING_MODELS、VISION_MODELS 等类属性时使用。
        从这些预设列表和 MODEL_DETAILS 创建模型信息对象。

        Returns:
            List[ModelInfo]: 预设模型列表

        Note:
            支持多种模型类型：
            - CHAT_MODELS: 聊天模型
            - EMBEDDING_MODELS: 嵌入模型
            - VISION_MODELS: 视觉模型
            - IMAGE_MODELS: 图像生成模型（GLM 专用）
            - VIDEO_MODELS: 视频生成模型（GLM 专用）
            - AUDIO_MODELS: 音频生成模型（GLM 专用）
            - OTHER_MODELS: 其他模型（GLM 专用）
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
        """刷新模型列表

        强制或非强制刷新模型列表。

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
        """异步获取模型列表

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.get_models()

    async def async_refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """异步刷新模型列表

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.refresh_models(force=force)

    def _save_models_to_cache(self, models: List[ModelInfo]) -> None:
        """保存模型列表到缓存

        将模型列表保存到本地缓存文件。

        Args:
            models: 模型信息列表
        """
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
        """从缓存加载模型列表

        从本地缓存文件加载模型列表。

        Returns:
            List[ModelInfo]: 缓存中的模型列表，如果无缓存则返回空列表
        """
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
        """准备聊天请求载荷（基类统一实现）

        准备发送给 LLM API 的请求参数。
        子类可以重写此方法以适配特定 Provider 的请求格式。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            stream: 是否流式输出
            tools: Function calling 工具定义列表
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

        # 添加 function calling 工具
        if tools:
            payload["tools"] = tools

        # 处理多模态消息（子类的 _prepare_chat_payload 可以覆盖此逻辑）
        prepared_messages = self._prepare_vision_messages(prepared_messages)

        payload["messages"] = prepared_messages
        payload.update(kwargs)
        return payload

    def _prepare_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理多模态消息

        默认实现不处理图片，子类如需支持 Vision 需要重写此方法。

        Args:
            messages: 消息列表

        Returns:
            List[Dict[str, Any]]: 处理后的消息列表
        """
        return messages

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应（基类统一实现）

        从 API 响应中提取 content、tool_calls 和 usage 信息。

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            APIError: 当响应为空时抛出
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
            usage=self._parse_usage(response),
            extra=response
        )

    def _parse_usage(self, response: Dict[str, Any]) -> Optional[UsageInfo]:
        """从 API 响应中提取 usage 信息，包含缓存字段

        Args:
            response: API 响应字典

        Returns:
            Optional[UsageInfo]: 用量信息，如果 API 未返回则返回 None
        """
        usage = response.get("usage", response.get("usageMetadata", {}))
        if not usage:
            return None

        # 标准 token 计数（兼容不同字段名）
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        total_tokens = usage.get("total_tokens")

        # 通过适配器提取缓存信息
        cache_info = self._parse_cache_info(response)

        return UsageInfo(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cache_read_tokens=cache_info.cached_tokens if cache_info else None,
            cache_creation_tokens=None,
        )

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 API 返回的模型列表（基类默认实现）

        尝试从通用字段解析模型列表。子类可以重写此方法以适配特定 Provider 的响应格式。

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表

        Note:
            默认实现尝试多种常见的模型列表响应格式：
            - response.get("data")
            - response.get("models")
            - response.get("model_list")
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
        """获取同步 HTTP Session

        使用单例模式管理 HTTP Session，避免重复创建。
        Session 会自动添加 Content-Type 和 Authorization 头。

        Returns:
            requests.Session: HTTP Session 对象
        """
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
        """发起同步 HTTP 请求

        封装通用的 HTTP 请求逻辑，自动处理错误和异常转换。

        Args:
            method: HTTP 方法（GET、POST 等）
            endpoint: API 端点（相对于 base_url）
            data: 请求体数据（字典）
            params: URL 查询参数
            timeout: 超时时间（秒）

        Returns:
            Dict[str, Any]: API 响应数据

        Raises:
            AuthenticationError: API 密钥无效（401）
            RateLimitError: 请求频率超限（429）
            TimeoutError: 请求超时
            ConnectionError: 连接失败
            APIError: 其他 API 错误
        """
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
        """获取异步 HTTP Session

        使用单例模式管理异步 HTTP Session。

        Returns:
            aiohttp.ClientSession: 异步 HTTP Session 对象
        """
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
        """发起异步 HTTP 请求

        封装通用的异步 HTTP 请求逻辑。

        Args:
            method: HTTP 方法
            endpoint: API 端点
            data: 请求体数据
            params: URL 查询参数
            timeout: 超时时间（秒）

        Returns:
            Dict[str, Any]: API 响应数据

        Raises:
            AuthenticationError: API 密钥无效
            RateLimitError: 请求频率超限
            TimeoutError: 请求超时
            ConnectionError: 连接失败
            APIError: 其他 API 错误
        """
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
        """发起同步流式请求

        使用生成器模式实现流式响应，逐块解析并返回。

        Args:
            endpoint: API 端点
            data: 请求体数据
            callback: 可选的回调函数，每收到一个响应块调用一次

        Yields:
            ChatResponse: 聊天响应块

        Raises:
            AuthenticationError: API 密钥无效
            RateLimitError: 请求频率超限
            TimeoutError: 请求超时
            ConnectionError: 连接失败
        """
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
        """发起异步流式请求

        使用异步生成器实现流式响应。

        Args:
            endpoint: API 端点
            data: 请求体数据

        Yields:
            ChatResponse: 聊天响应块

        Raises:
            AuthenticationError: API 密钥无效
            RateLimitError: 请求频率超限
            TimeoutError: 请求超时
            ConnectionError: 连接失败
        """
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
        """解析流式响应

        子类需要重写此方法以适配特定的流式响应格式。
        基类提供统一实现，子类可按需重写。

        Args:
            data: 流式数据块

        Returns:
            ChatResponse: 聊天响应对象
        """
        # 处理 message 格式（可能是 delta 或 message）
        message = data.get("delta", data.get("message", {}))

        # 提取 tool_calls（Function Calling）
        tool_calls = message.get("tool_calls", [])

        # 尝试从 chunk 中提取 usage（部分 API 在流式结束时返回）
        usage = self._parse_usage(data)

        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content", ""),
            tool_calls=tool_calls,
            usage=usage,
            extra=data
        )

    # ==================== 抽象方法实现 ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求

        子类需要重写此方法以实现具体的聊天逻辑。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            NotImplementedError: 子类未重写时抛出
        """
        raise NotImplementedError("Subclass must implement chat method")

    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求

        子类需要重写此方法以实现具体的嵌入逻辑。

        Args:
            texts: 文本或文本列表
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            NotImplementedError: 子类未重写时抛出
        """
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
        """异步发送聊天请求

        子类需要重写此方法以实现具体的异步聊天逻辑。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            NotImplementedError: 子类未重写时抛出
        """
        raise NotImplementedError("Subclass must implement async_chat method")

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """异步发送流式聊天请求

        子类需要重写此方法以实现具体的异步流式聊天逻辑。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            AsyncIterator[ChatResponse]: 异步流式响应迭代器

        Raises:
            NotImplementedError: 子类未重写时抛出
        """
        raise NotImplementedError("Subclass must implement async_stream_chat method")

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送嵌入请求

        子类需要重写此方法以实现具体的异步嵌入逻辑。

        Args:
            texts: 文本或文本列表
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            NotImplementedError: 子类未重写时抛出
        """
        raise NotImplementedError("Subclass must implement async_embed method")

    def validate_config(self) -> bool:
        """验证配置是否有效

        检查 api_key 或 base_url 是否至少有一个非空。

        Returns:
            bool: 配置是否有效
        """
        return bool(self.api_key or self.base_url)