"""Base Provider 基类模块

该模块提供所有 LLM 提供商的抽象基类 BaseProvider，包含通用功能实现。
具体提供商只需继承此类并实现特定方法即可，大幅减少重复代码。

主要功能:
    - 同步/异步 HTTP 请求封装（含重试与指数退避）
    - 模型列表获取和缓存管理（含 TTL 过期标记）
    - 聊天/嵌入/流式请求模板方法实现
    - Function Calling 支持
    - OpenAI 兼容 Vision 消息转换
    - 错误处理和异常转换

Classes:
    BaseProvider: LLM 提供商抽象基类

使用示例:
    >>> from core.llm.providers.base import BaseProvider
    >>> class MyProvider(BaseProvider):
    ...     provider_type = "my_provider"
    ...     # 实现具体方法...
"""

import asyncio
import json
import logging
import random
import re
import threading
import time
from abc import ABC
from typing import Dict, Any, Optional, List, Union, Callable, AsyncIterator

import aiohttp
import requests

from ..provider_interface import (
    ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo
)
from ..exceptions import (
    APIError, AuthenticationError, RateLimitError,
    InvalidRequestError, ConnectionError, TimeoutError
)
from ..cache_adapter import get_cache_adapter, CacheAdapter
from ..config import LLMConfig
from ..types_cache import CacheInfo

logger = logging.getLogger(__name__)


def _keyword_in_model(model_id: str, keyword: str) -> bool:
    """按非字母数字边界匹配模型 ID 中的关键词，避免子串误判

    例如关键词 "4o" 可以匹配 "gpt-4o"、"gpt-4o-mini"，
    但不会匹配 "text-embedding-4other" 这类仅包含子串的 ID。

    Args:
        model_id: 模型 ID
        keyword: 关键词

    Returns:
        bool: 是否匹配
    """
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, model_id.lower()) is not None


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
        _supports_stream_usage: 流式请求是否支持 stream_options.include_usage
        DEFAULT_MAX_RETRIES: 默认最大重试次数（不含首次请求）
        RETRY_BASE_DELAY: 指数退避基数（秒）
        RETRY_MAX_DELAY: 单次退避上限（秒）

    Attributes:
        api_key: API 密钥
        base_url: API 基础 URL
        chat_model: 默认聊天模型
        embedding_model: 默认嵌入模型
        timeout: 请求读取超时时间（秒）
        connect_timeout: 连接超时时间（秒）
        last_error: 最近一次错误信息（成功时清空），供上层聚合健康状态
        _session: 同步 HTTP Session
        _async_session: 异步 HTTP Session
        _provider_name: 提供商名称（用于缓存标识）

    Example:
        >>> class MyProvider(BaseProvider):
        ...     provider_type = "my_provider"
        ...     provider_name = "My Provider"
        ...     _models_endpoint = "/v1/models"
    """

    # 子类需要定义这些类属性
    _models_endpoint: str = ""
    _chat_endpoint: str = ""
    _embedding_endpoint: str = ""

    # 流式请求是否支持 stream_options.include_usage（OpenAI 兼容 API）
    _supports_stream_usage: bool = False

    # ==================== 重试配置 ====================
    DEFAULT_MAX_RETRIES: int = 3      # 默认最大重试次数（不含首次请求）
    RETRY_BASE_DELAY: float = 1.0     # 指数退避基数（秒）
    RETRY_MAX_DELAY: float = 8.0      # 单次退避上限（秒）
    RETRY_AFTER_MAX: float = 60.0     # Retry-After 头采用上限（秒）

    # 模型列表缓存 TTL（秒），超过后标记为 stale
    MODELS_CACHE_TTL: float = 24 * 3600

    # 默认请求超时（秒）：读取超时 / 连接超时，可被配置覆盖
    DEFAULT_TIMEOUT: int = 60
    DEFAULT_CONNECT_TIMEOUT: int = 10

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 BaseProvider

        Args:
            config: 提供商配置字典，包含 api_key、base_url、chat_model 等，
                可选 max_retries（重试次数）、connect_timeout（连接超时秒数）
            provider_name: 提供商名称，用于缓存标识
        """
        super().__init__(config)
        config = config or {}
        self.api_key = config.get("api_key", "")
        self.base_url = config.get("base_url", "").rstrip("/")
        self.chat_model = config.get("chat_model", "")
        self.embedding_model = config.get("embedding_model", "")
        self.timeout = config.get("timeout", self.DEFAULT_TIMEOUT)
        self.connect_timeout = config.get("connect_timeout", self.DEFAULT_CONNECT_TIMEOUT)
        self._max_retries = int(config.get("max_retries", self.DEFAULT_MAX_RETRIES))
        self._session = None
        # requests.Session 非线程安全，用可重入锁保护创建与请求发送
        # （_get_session 内部也会获取同一把锁，必须可重入）
        self._session_lock = threading.RLock()
        self._async_session = None
        self._async_session_loop = None  # 异步 session 绑定的事件循环
        self._provider_name = provider_name  # 用于缓存标识
        self._cache_adapter: Optional[CacheAdapter] = None
        self._llm_config = None  # LLMConfig 缓存实例，避免每次重读配置文件
        self._models_cache_stale = False  # 模型缓存是否过期
        self.last_error: Optional[str] = None  # 最近一次错误信息
        self._init_cache_adapter()

    def _init_cache_adapter(self) -> None:
        """初始化缓存适配器"""
        if self.config:
            # self.config 通常是 dict，需用 .get；兼容对象型配置再用 getattr
            if isinstance(self.config, dict):
                cache_cfg = self.config.get("cache_fields")
            else:
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
            - 请求失败时返回空列表并填充 last_error，不抛出异常
        """
        if not self.api_key or not self._models_endpoint:
            return []

        try:
            response = self._make_request("GET", self._models_endpoint)
            models = self._parse_models_response(response)
            self.last_error = None
            return models
        except Exception as e:
            self.last_error = str(e)
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

        # API 获取失败，尝试从缓存加载（即使缓存 stale 也继续使用，
        # 由调用方通过 models_cache_stale 决定是否稍后远程刷新）
        cached_models = self._load_models_from_cache()
        if cached_models:
            if self._models_cache_stale:
                logger.info(
                    "[%s] 模型缓存已超过 %d 小时，远程刷新失败后继续使用旧缓存",
                    self._provider_name or self.provider_type,
                    int(self.MODELS_CACHE_TTL // 3600),
                )
            return cached_models

        # 缓存也没有，从配置中读取默认模型
        return self._get_default_models_from_config()

    @property
    def models_cache_stale(self) -> bool:
        """模型缓存是否已过期（超过 MODELS_CACHE_TTL）

        调用方可据此决定是否强制远程刷新；刷新失败仍可继续使用旧缓存。
        """
        return self._models_cache_stale

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

        def _build(model_ids, chat=False, streaming=False, embedding=False, vision=False):
            for model_id in model_ids:
                details = model_details.get(model_id, {})
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=chat,
                    support_streaming=streaming,
                    support_embedding=embedding,
                    support_vision=vision,
                    support_function_calling=details.get('support_function_calling', False) if chat else False,
                    context_length=details.get('context_length'),
                    description=details.get('description', '')
                ))

        # 获取 CHAT_MODELS（兼容子类可能没有定义的情况）
        _build(getattr(self, 'CHAT_MODELS', []), chat=True, streaming=True)
        # 获取 EMBEDDING_MODELS
        _build(getattr(self, 'EMBEDDING_MODELS', []), embedding=True)
        # 获取 VISION_MODELS
        _build(getattr(self, 'VISION_MODELS', []), vision=True)
        # 获取 IMAGE_MODELS / VIDEO_MODELS / AUDIO_MODELS / OTHER_MODELS (GLM 专用)
        _build(getattr(self, 'IMAGE_MODELS', []))
        _build(getattr(self, 'VIDEO_MODELS', []))
        _build(getattr(self, 'AUDIO_MODELS', []))
        _build(getattr(self, 'OTHER_MODELS', []))

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
            # API 拉取失败，尝试从缓存加载（即使 stale 也继续使用）
            cached_models = self._load_models_from_cache()
            if cached_models:
                return cached_models
            return []

        # 正常获取（优先缓存）
        return self.get_models()

    async def async_get_models(self) -> List[ModelInfo]:
        """异步获取模型列表

        使用 asyncio.to_thread 包装同步实现，避免阻塞事件循环。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return await asyncio.to_thread(self.get_models)

    async def async_refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """异步刷新模型列表

        使用 asyncio.to_thread 包装同步实现，避免阻塞事件循环。

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return await asyncio.to_thread(self.refresh_models, force)

    def _get_llm_config(self):
        """获取 LLMConfig 缓存实例

        避免每次读写模型缓存都重新加载配置文件。

        Returns:
            LLMConfig: 配置管理器实例
        """
        if self._llm_config is None:
            self._llm_config = LLMConfig()
        return self._llm_config

    def _save_models_to_cache(self, models: List[ModelInfo]) -> None:
        """保存模型列表到缓存

        将模型列表连同时间戳保存到本地缓存文件，用于 TTL 过期判断。

        Args:
            models: 模型信息列表
        """
        if not self._provider_name:
            return

        try:
            payload = {
                "timestamp": time.time(),
                "models": [m.to_dict() for m in models],
            }
            self._get_llm_config().save_models_cache(self._provider_name, payload)
        except Exception as e:
            # 缓存写入失败不影响主流程，降级为不使用缓存，但需留痕
            logger.warning("保存模型列表缓存失败 (%s): %s", self._provider_name, e)

    def _load_models_from_cache(self) -> List[ModelInfo]:
        """从缓存加载模型列表

        从本地缓存文件加载模型列表，同时判断缓存是否过期（stale）。
        兼容旧格式（纯模型列表，无时间戳），旧格式一律视为 stale。

        Returns:
            List[ModelInfo]: 缓存中的模型列表，如果无缓存则返回空列表
        """
        self._models_cache_stale = False
        if not self._provider_name:
            return []

        try:
            cached_data = self._get_llm_config().load_models_cache(self._provider_name)
            if not cached_data:
                return []

            if isinstance(cached_data, dict):
                # 新格式：{"timestamp": ..., "models": [...]}
                models_data = cached_data.get("models", [])
                timestamp = cached_data.get("timestamp", 0) or 0
                self._models_cache_stale = (time.time() - timestamp) > self.MODELS_CACHE_TTL
            else:
                # 旧格式：纯模型列表，无时间戳，视为过期
                models_data = cached_data
                self._models_cache_stale = True

            return [ModelInfo.from_dict(m) for m in models_data]
        except Exception as e:
            # 缓存读取失败回退为空列表（后续走 API/默认模型），但需留痕
            logger.warning("读取模型列表缓存失败 (%s): %s", self._provider_name, e)

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

        # 处理多模态消息（默认转换为 OpenAI 兼容格式，子类可覆盖）
        prepared_messages = self._prepare_vision_messages(prepared_messages)

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

        # 流式请求 usage 统计（OpenAI 兼容 API）
        if stream and self._supports_stream_usage:
            payload["stream_options"] = {"include_usage": True}

        payload.update(kwargs)

        # 剔除 None 值，避免污染 API 请求
        return {k: v for k, v in payload.items() if v is not None}

    def _prepare_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理多模态消息（OpenAI 兼容格式）

        将带 images 的消息转换为 OpenAI 兼容的 content 数组格式:
            [{"type": "text", "text": ...},
             {"type": "image_url", "image_url": {"url": "data:image/...;base64,..."}}]

        images 中的图片约定为 base64 字符串；已带 data: 前缀或 http(s) URL 的
        直接使用。仅支持文本消息的 provider 应重写此方法。

        Args:
            messages: 消息列表

        Returns:
            List[Dict[str, Any]]: 处理后的消息列表
        """
        result = []
        for msg in messages:
            images = msg.get("images")
            if images:
                msg = {k: v for k, v in msg.items() if k != "images"}
                content: List[Dict[str, Any]] = []
                text = msg.get("content") or ""
                if text:
                    content.append({"type": "text", "text": text})
                for img in images:
                    img_str = str(img)
                    if img_str.startswith(("data:", "http://", "https://")):
                        url = img_str
                    else:
                        url = f"data:image/jpeg;base64,{img_str}"
                    content.append({"type": "image_url", "image_url": {"url": url}})
                msg["content"] = content
            result.append(msg)
        return result

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应（OpenAI 兼容格式统一实现）

        从 API 响应中提取 content、tool_calls 和 usage 信息。
        tool_calls 保持 OpenAI 风格契约:
            [{"id": str, "type": "function",
              "function": {"name": str, "arguments": str(JSON)}}]

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            APIError: 当响应为空时抛出
        """
        choices = response.get("choices", [])
        if not choices:
            raise APIError("Empty response from API", provider=self.provider_type)

        choice = choices[0]
        message = choice.get("message", {})

        # 提取 tool_calls（Function Calling）
        tool_calls = message.get("tool_calls") or []

        return ChatResponse(
            content=message.get("content") or "",
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("reasoning_content") or "",
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

    # ==================== 重试与退避 ====================

    def _compute_retry_delay(
        self,
        attempt: int,
        retry_after: Optional[str] = None
    ) -> float:
        """计算第 attempt 次重试前的退避等待时间

        指数退避: RETRY_BASE_DELAY * 2^attempt，封顶 RETRY_MAX_DELAY，
        并附加少量随机抖动。若响应带 Retry-After 头则优先采用。

        Args:
            attempt: 当前重试次数（从 0 开始）
            retry_after: 响应头 Retry-After 的值（秒）

        Returns:
            float: 等待秒数
        """
        if retry_after is not None:
            try:
                return min(float(retry_after), self.RETRY_AFTER_MAX)
            except (TypeError, ValueError):
                pass
        delay = min(self.RETRY_MAX_DELAY, self.RETRY_BASE_DELAY * (2 ** attempt))
        return delay + random.uniform(0, 0.2)

    # ==================== 同步请求方法 ====================

    def _get_session(self) -> requests.Session:
        """获取同步 HTTP Session

        使用单例模式管理 HTTP Session，避免重复创建。
        Session 会自动添加 Content-Type 和 Authorization 头。
        创建过程由锁保护，保证线程安全。

        Returns:
            requests.Session: HTTP Session 对象
        """
        if self._session is None:
            with self._session_lock:
                # 双重检查（RLock 允许 _make_request 持锁期间重入）
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
        """发起同步 HTTP 请求（含重试与指数退避）

        封装通用的 HTTP 请求逻辑，自动处理错误和异常转换。
        429、5xx、连接错误、超时会按指数退避重试（最多 self._max_retries 次，
        429 优先采用 Retry-After 头）；其余 4xx 不重试。重试耗尽后抛出相同类型异常。

        Args:
            method: HTTP 方法（GET、POST 等）
            endpoint: API 端点（相对于 base_url）
            data: 请求体数据（字典）
            params: URL 查询参数
            timeout: 读取超时时间（秒），默认使用 self.timeout

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
        read_timeout = timeout or self.timeout

        for attempt in range(self._max_retries + 1):
            try:
                # requests.Session 非线程安全，请求发送阶段加锁保护
                with self._session_lock:
                    response = self._get_session().request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        timeout=(self.connect_timeout, read_timeout)
                    )

                if response.status_code == 401:
                    self.last_error = "Invalid API key"
                    raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                elif response.status_code == 429:
                    if attempt < self._max_retries:
                        time.sleep(self._compute_retry_delay(attempt, response.headers.get("Retry-After")))
                        continue
                    self.last_error = "Rate limit exceeded"
                    raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                elif response.status_code >= 500:
                    if attempt < self._max_retries:
                        time.sleep(self._compute_retry_delay(attempt, response.headers.get("Retry-After")))
                        continue
                    self.last_error = f"API request failed: {response.text}"
                    raise APIError(
                        f"API request failed: {response.text}",
                        status_code=response.status_code,
                        provider=self.provider_type
                    )
                elif response.status_code >= 400:
                    # 其余 4xx 客户端错误不重试
                    self.last_error = f"API request failed: {response.text}"
                    raise APIError(
                        f"API request failed: {response.text}",
                        status_code=response.status_code,
                        provider=self.provider_type
                    )

                self.last_error = None
                return response.json()

            except requests.exceptions.Timeout:
                last_exc: Exception = TimeoutError("Request timeout", provider=self.provider_type)
            except requests.exceptions.ConnectionError:
                last_exc = ConnectionError("Connection failed", provider=self.provider_type)
            except requests.exceptions.RequestException as e:
                # 其他请求异常（如 URL 错误）不重试
                self.last_error = str(e)
                raise APIError(f"Request error: {str(e)}", provider=self.provider_type)

            # 连接错误与超时：指数退避后重试
            if attempt < self._max_retries:
                time.sleep(self._compute_retry_delay(attempt))
                continue
            self.last_error = str(last_exc)
            raise last_exc

        # 理论上不可达
        raise APIError("Request failed after retries", provider=self.provider_type)

    # ==================== 异步请求方法 ====================

    async def _get_async_session(self) -> aiohttp.ClientSession:
        """获取异步 HTTP Session

        使用单例模式管理异步 HTTP Session。
        Session 绑定创建时的事件循环；检测到不同事件循环时自动重建，
        避免跨事件循环复用导致的运行时错误。
        会话级超时: 不设总时长上限（避免长流式回答被掐断），
        仅限制连接超时与单次读取超时。

        Returns:
            aiohttp.ClientSession: 异步 HTTP Session 对象
        """
        loop = asyncio.get_running_loop()
        if (self._async_session is None
                or self._async_session.closed
                or self._async_session_loop is not loop):
            old_session = self._async_session
            if old_session is not None and not old_session.closed:
                # 旧 session 属于其他事件循环，无法安全关闭，detach 避免告警
                try:
                    old_session.detach()
                except Exception as e:
                    logger.debug("旧异步 session detach 失败（忽略，直接重建）: %s", e)

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._async_session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    connect=self.connect_timeout,
                    sock_read=self.timeout,
                )
            )
            self._async_session_loop = loop
        return self._async_session

    async def _make_async_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """发起异步 HTTP 请求（含重试与指数退避）

        封装通用的异步 HTTP 请求逻辑。
        429、5xx、连接错误、超时会按指数退避重试（最多 self._max_retries 次，
        429 优先采用 Retry-After 头）；其余 4xx 不重试。重试耗尽后抛出相同类型异常。

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

        for attempt in range(self._max_retries + 1):
            try:
                session = await self._get_async_session()
                async with session.request(
                    method=method,
                    url=url,
                    json=data,
                    params=params,
                    timeout=aiohttp.ClientTimeout(
                        total=timeout,
                        connect=self.connect_timeout,
                    )
                ) as response:

                    if response.status == 401:
                        self.last_error = "Invalid API key"
                        raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                    elif response.status == 429:
                        if attempt < self._max_retries:
                            await asyncio.sleep(self._compute_retry_delay(attempt, response.headers.get("Retry-After")))
                            continue
                        self.last_error = "Rate limit exceeded"
                        raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                    elif response.status >= 500:
                        text = await response.text()
                        if attempt < self._max_retries:
                            await asyncio.sleep(self._compute_retry_delay(attempt, response.headers.get("Retry-After")))
                            continue
                        self.last_error = f"API request failed: {text}"
                        raise APIError(
                            f"API request failed: {text}",
                            status_code=response.status,
                            provider=self.provider_type
                        )
                    elif response.status >= 400:
                        # 其余 4xx 客户端错误不重试
                        text = await response.text()
                        self.last_error = f"API request failed: {text}"
                        raise APIError(
                            f"API request failed: {text}",
                            status_code=response.status,
                            provider=self.provider_type
                        )

                    self.last_error = None
                    return await response.json()

            except asyncio.TimeoutError:
                last_exc: Exception = TimeoutError("Request timeout", provider=self.provider_type)
            except aiohttp.ClientConnectorError:
                last_exc = ConnectionError("Connection failed", provider=self.provider_type)
            except aiohttp.ClientError as e:
                # 其他客户端异常不重试
                self.last_error = str(e)
                raise APIError(f"Request error: {str(e)}", provider=self.provider_type)

            # 连接错误与超时：指数退避后重试
            if attempt < self._max_retries:
                await asyncio.sleep(self._compute_retry_delay(attempt))
                continue
            self.last_error = str(last_exc)
            raise last_exc

        # 理论上不可达
        raise APIError("Request failed after retries", provider=self.provider_type)

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
            # requests.Session 非线程安全，建立连接阶段加锁保护
            with self._session_lock:
                response = session.post(
                    url,
                    json=data,
                    stream=True,
                    timeout=(self.connect_timeout, self.timeout)
                )
            with response:
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
            self.last_error = "Request timeout"
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except requests.exceptions.ConnectionError:
            self.last_error = "Connection failed"
            raise ConnectionError("Connection failed", provider=self.provider_type)

    async def _make_async_stream_request(
        self,
        endpoint: str,
        data: Dict
    ) -> AsyncIterator[ChatResponse]:
        """发起异步流式请求

        使用异步生成器实现流式响应。
        超时不设总时长上限（避免长回答被掐断），仅限制连接与单次读取超时。

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
            async with session.post(
                url,
                json=data,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    connect=self.connect_timeout,
                    sock_read=self.timeout,
                )
            ) as response:
                if response.status == 401:
                    self.last_error = "Invalid API key"
                    raise AuthenticationError("Invalid API key", status_code=401, provider=self.provider_type)
                elif response.status == 429:
                    self.last_error = "Rate limit exceeded"
                    raise RateLimitError("Rate limit exceeded", status_code=429, provider=self.provider_type)
                elif response.status >= 400:
                    text = await response.text()
                    self.last_error = f"API request failed: {text}"
                    raise APIError(
                        f"API request failed: {text}",
                        status_code=response.status,
                        provider=self.provider_type
                    )

                self.last_error = None
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
            self.last_error = "Request timeout"
            raise TimeoutError("Request timeout", provider=self.provider_type)
        except aiohttp.ClientConnectorError:
            self.last_error = "Connection failed"
            raise ConnectionError("Connection failed", provider=self.provider_type)

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应（OpenAI 兼容格式统一实现）

        基类提供统一实现，子类可按需重写。
        对仅含 usage 的末尾块（choices 为空）也能正确解析。

        Args:
            data: 流式数据块

        Returns:
            ChatResponse: 聊天响应对象
        """
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta", {})
            return ChatResponse(
                content=delta.get("content") or "",
                model=data.get("model", ""),
                role=delta.get("role", "assistant"),
                reasoning_content=delta.get("reasoning_content") or "",
                tool_calls=delta.get("tool_calls") or [],
                usage=self._parse_usage(data),
                extra=data
            )
        # 无 choices 的块（如仅含 usage 的末尾块）
        return ChatResponse(
            content="",
            model=data.get("model", ""),
            tool_calls=[],
            usage=self._parse_usage(data),
            extra=data
        )

    # ==================== 同步 API（模板方法默认实现） ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）

        基类模板方法默认实现，适用于 OpenAI 兼容的聊天端点。
        子类如端点或格式不同可重写。

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

        基类模板方法默认实现，返回流式响应生成器。

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

        基类模板方法默认实现，适用于 OpenAI 兼容的嵌入端点。

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
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        response = self._make_request("POST", self._embedding_endpoint, data=payload)
        return self._parse_embedding_response(response)

    def _parse_embedding_response(self, response: Dict[str, Any]) -> List[EmbeddingResponse]:
        """解析嵌入响应（OpenAI 兼容格式统一实现）

        Args:
            response: API 响应字典

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        embeddings = response.get("data", [])
        return [
            EmbeddingResponse(
                embedding=item.get("embedding", []),
                model=response.get("model", ""),
                extra=item
            )
            for item in embeddings
        ]

    # 注意: get_models 和 async_get_models 已在基类中实现
    # 子类如需自定义可重写 get_models() 或 _get_default_models_from_config()

    # ==================== 异步 API（模板方法默认实现） ====================

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求

        基类模板方法默认实现，适用于 OpenAI 兼容的聊天端点。

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

        基类模板方法默认实现。

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

        基类模板方法默认实现，适用于 OpenAI 兼容的嵌入端点。

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
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        response = await self._make_async_request("POST", self._embedding_endpoint, data=payload)
        return self._parse_embedding_response(response)

    def validate_config(self) -> bool:
        """验证配置是否有效（仅格式校验，不代表连通性）

        检查 api_key 或 base_url 是否至少有一个非空。
        注意：本方法不发起任何网络请求，返回 True 仅表示配置格式完整，
        不代表 API 服务实际可用。

        Returns:
            bool: 配置是否有效
        """
        return bool(self.api_key or self.base_url)
