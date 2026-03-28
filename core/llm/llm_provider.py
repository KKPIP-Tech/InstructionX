"""LLM 提供商管理器模块

该模块提供对多种大语言模型提供商的统一访问接口。采用单例模式管理全局 LLM 提供商实例，
支持聊天、嵌入、流式对话等功能，并自动管理模型列表缓存。

主要功能:
    - 单例模式全局访问
    - 多提供商配置和动态切换
    - 聊天Completion和流式输出
    - 嵌入（Embedding）向量生成
    - 模型列表自动缓存和刷新
    - 同步/异步 API 支持

Classes:
    LLMProvider: LLM 提供商管理器（单例模式）

Functions:
    get_llm_provider: 获取全局 LLM 提供商实例

使用示例:
    >>> from core.llm import LLMProvider, get_llm_provider, Message
    >>> # 获取单例实例
    >>> provider = get_llm_provider()
    >>> # 发送聊天请求
    >>> response = provider.chat([Message("user", "你好")])
    >>> # 流式输出
    >>> for chunk in provider.stream_chat([Message("user", "你好")]):
    ...     print(chunk.content, end="")
"""

import threading
from typing import Dict, Any, Optional, List, Union, Callable, AsyncIterator, TYPE_CHECKING

from .config import LLMConfig, ProviderConfig
from .provider_interface import ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo
from .providers import get_provider_class, PROVIDER_REGISTRY
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from .provider_interface import ChatResponse

from utils.logging_tools import LoggerManager, get_name


class LLMProvider:
    """大语言模型提供商管理器（单例模式）

    统一管理多个 LLM 提供商的配置和调用，是应用程序访问 LLM 能力的入口点。

    主要特性:
        - 单例模式：全局只有一个实例，避免重复初始化
        - 多提供商支持：同时管理多个 LLM 提供商（GLM、MiniMax、SiliconFlow、Ollama）
        - 自动模型获取：启动时自动拉取所有提供商的模型列表
        - 缓存管理：本地缓存模型列表，支持强制刷新
        - 灵活配置：支持启用/禁用特定提供商的特定功能

    Class Attributes:
        _instance: 类变量，存储单例实例
        _lock: 类变量，线程锁，用于线程安全单例创建

    Attributes:
        _config: LLM 配置管理器
        _providers: 提供商实例字典 {name: ILLM 实例}
        _models_cache: 模型列表缓存 {provider_name: [ModelInfo]}
        _logger: 日志管理器

    使用方式:
        >>> from core.llm import get_llm_provider, Message
        >>> provider = get_llm_provider()
        >>> # 聊天
        >>> response = provider.chat([Message("user", "你好")])
        >>> # 嵌入
        >>> embeddings = provider.embed("要嵌入的文本")
        >>> # 获取模型
        >>> models = provider.get_models()
    """

    _instance: Optional['LLMProvider'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式：确保全局只有一个实例

        使用双重检查锁定（Double-Checked Locking）实现线程安全的单例模式。
        第一次检查无需加锁，后续检查和创建需要加锁保护。

        Returns:
            LLMProvider: 单例实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化 LLM 提供商管理器

        初始化配置管理器、创建所有已配置的提供商实例、并自动获取模型列表。
        使用 _initialized 标志防止重复初始化。
        """
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self._config = LLMConfig()
        self._providers: Dict[str, ILLM] = {}
        self._models_cache: Dict[str, List[ModelInfo]] = {}  # 模型缓存
        self._logger = LoggerManager()
        self._init_providers()
        self._fetch_all_models()  # 启动时自动拉取模型列表

    def _init_providers(self) -> None:
        """初始化所有已配置的 LLM 提供商

        从配置中读取所有已配置的提供商，创建对应的实例。
        如果某个提供商创建失败，记录错误日志并继续初始化其他提供商。
        """
        provider_configs = self._config.get_all_providers()

        for name, config_data in provider_configs.items():
            try:
                self._create_provider(name, config_data.to_dict())
            except Exception as e:
                self._logger.error(get_name(), f'Failed to initialize provider {name}: {e}')

    def _fetch_all_models(self) -> None:
        """启动时自动获取所有提供商的模型列表

        遍历所有已初始化的提供商，尝试从 API 实时获取模型列表。
        如果获取失败，自动回退到缓存数据，避免因网络问题导致启动失败。

        缓存逻辑:
            - 优先尝试从 API 获取
            - 获取失败时使用空列表
            - 可通过 refresh_all_models() 强制刷新
        """
        for name, provider in self._providers.items():
            try:
                # 强制从 API 拉取，失败则使用缓存
                models = provider.refresh_models(force=True)
                self._models_cache[name] = models
                self._logger.info(get_name(), f'Loaded {len(models)} models for {name}')
            except Exception as e:
                self._logger.error(get_name(), f'Failed to fetch models for {name}: {e}')
                self._models_cache[name] = []

    def refresh_provider_models(self, provider_name: str, force: bool = False) -> List[ModelInfo]:
        """刷新指定提供商的模型列表

        强制或非强制刷新指定提供商的模型列表，并更新缓存。

        Args:
            provider_name: 提供商名称
            force: 是否强制从 API 刷新，忽略缓存

        Returns:
            List[ModelInfo]: 模型信息列表，如果失败返回空列表
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return []

        try:
            models = provider.refresh_models(force=force)
            self._models_cache[provider_name] = models
            return models
        except Exception as e:
            self._logger.error(get_name(), f'Failed to refresh models for {provider_name}: {e}')
            return []

    def refresh_all_models(self, force: bool = False) -> Dict[str, List[ModelInfo]]:
        """刷新所有提供商的模型列表

        遍历调用所有提供商的模型刷新方法。

        Args:
            force: 是否强制从 API 刷新

        Returns:
            Dict[str, List[ModelInfo]]: 提供商名称到模型列表的映射字典
        """
        for name in self._providers.keys():
            self.refresh_provider_models(name, force=force)
        return self._models_cache

    def get_cached_models(self, provider_name: str) -> List[ModelInfo]:
        """获取指定提供商的缓存模型列表

        Args:
            provider_name: 提供商名称

        Returns:
            List[ModelInfo]: 模型信息列表，如果提供商不存在返回空列表
        """
        return self._models_cache.get(provider_name, [])

    def _create_provider(self, name: str, config: Dict[str, Any]) -> Optional[ILLM]:
        """创建 LLM 提供商实例

        根据配置创建对应类型的 LLM 提供商实例，并注册到管理器中。

        Args:
            name: 提供商名称（键名）
            config: 提供商配置字典，包含 api_key、base_url、provider_type 等

        Returns:
            Optional[ILLM]: 创建的提供商实例，创建失败返回 None

        Raises:
            ConfigurationError: 当 provider_type 不支持时抛出
        """
        provider_type = config.get("provider_type", name)
        provider_class = get_provider_class(provider_type)

        if not provider_class:
            raise ConfigurationError(f"Unknown provider type: {provider_type}")

        # 创建实例，传递 provider_name 用于模型缓存标识
        provider = provider_class(config, provider_name=name)
        self._providers[name] = provider
        return provider

    def get_provider(self, name: str) -> Optional[ILLM]:
        """获取指定名称的提供商实例

        Args:
            name: 提供商名称

        Returns:
            Optional[ILLM]: 提供商实例，如果不存在返回 None
        """
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ILLM]:
        """获取所有已创建的提供商实例

        Returns:
            Dict[str, ILLM]: 提供商名称到实例的映射字典
        """
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ILLM]:
        """获取已启用的提供商（按功能类型筛选）

        根据功能类型（chat 或 embedding）筛选已启用的提供商。

        Args:
            feature: 功能类型，"chat" 表示聊天功能，"embedding" 表示嵌入功能

        Returns:
            Dict[str, ILLM]: 符合条件的提供商实例字典
        """
        result = {}
        enabled_configs = self._config.get_enabled_providers(feature)

        for name in enabled_configs.keys():
            provider = self._providers.get(name)
            if provider:
                result[name] = provider

        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新 LLM 提供商配置

        同时更新配置文件和内存中的实例。

        Args:
            name: 提供商名称
            config: 提供商配置对象
        """
        self._config.add_provider(name, config)
        self._create_provider(name, config.to_dict())

    def remove_provider(self, name: str) -> bool:
        """移除 LLM 提供商

        关闭连接并从配置中删除。

        Args:
            name: 提供商名称

        Returns:
            bool: 操作是否成功（返回配置删除结果）
        """
        if name in self._providers:
            provider = self._providers[name]
            provider.close()
            del self._providers[name]

        return self._config.remove_provider(name)

    def reload_config(self) -> None:
        """重新加载 LLM 提供商配置

        关闭所有现有连接，清空实例缓存，重新从配置文件初始化。
        用于热重载配置的场景。
        """
        # 关闭现有连接
        for provider in self._providers.values():
            provider.close()

        self._providers.clear()
        self._config = LLMConfig()
        self._init_providers()

    # ==================== 便捷方法 ====================

    def chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）

        向 LLM 发送聊天请求，获取完整的响应文本。
        如果 provider 参数为 "default"，会自动选择第一个启用的提供商。

        Args:
            messages: 消息列表，支持 Message 对象或字典格式
            provider: 提供商名称，"default" 自动选择第一个启用的提供商
            model: 模型名称（可选，默认使用配置中的模型）
            temperature: 温度参数，控制随机性，范围 0-2，默认 0.7
            max_tokens: 最大生成 token 数（可选）
            **kwargs: 其他提供商特定参数

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            ConfigurationError: 当没有启用的提供商或提供商不存在时抛出
        """
        if provider == "default":
            enabled = self.get_enabled_providers("chat")
            if not enabled:
                raise ConfigurationError("No enabled chat provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return provider_instance.chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[ChatResponse], None]] = None,
        **kwargs
    ):
        """发送流式聊天请求（同步）

        向 LLM 发送流式聊天请求，通过回调函数或迭代器逐步获取响应。
        如果提供商不支持流式输出，会抛出 NotImplementedError。

        Args:
            messages: 消息列表
            provider: 提供商名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback: 流式响应回调函数，每收到一个响应块调用一次
            **kwargs: 其他参数

        Returns:
            流式响应生成器或回调调用结果

        Raises:
            ConfigurationError: 当提供商不存在时抛出
            NotImplementedError: 当提供商不支持流式输出时抛出
        """
        if provider == "default":
            enabled = self.get_enabled_providers("chat")
            if not enabled:
                raise ConfigurationError("No enabled chat provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return provider_instance.stream_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            callback=callback,
            **kwargs
        )

    def embed(
        self,
        texts: Union[str, List[str]],
        provider: str = "default",
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送文本嵌入请求（同步）

        将文本转换为向量嵌入。

        Args:
            texts: 单个文本或文本列表
            provider: 提供商名称
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            ConfigurationError: 当没有启用的嵌入提供商或提供商不存在时抛出
        """
        if provider == "default":
            enabled = self.get_enabled_providers("embedding")
            if not enabled:
                raise ConfigurationError("No enabled embedding provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return provider_instance.embed(
            texts=texts,
            model=model,
            **kwargs
        )

    def get_models(self, provider: Optional[str] = None) -> Dict[str, List[ModelInfo]]:
        """获取可用模型列表

        获取指定提供商或所有提供商的模型列表。

        Args:
            provider: 可选，指定提供商名称。None 表示获取所有提供商的模型

        Returns:
            Dict[str, List[ModelInfo]]: 提供商名称到模型列表的映射字典
        """
        if provider:
            provider_instance = self.get_provider(provider)
            if provider_instance:
                return {provider: provider_instance.get_models()}
            return {}

        result = {}
        for name, provider_instance in self._providers.items():
            result[name] = provider_instance.get_models()
        return result

    # ==================== 异步方法 ====================

    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """异步发送聊天请求

        异步版本的聊天接口，适用于需要高并发的场景。

        Args:
            messages: 消息列表
            provider: 提供商名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象
        """
        if provider == "default":
            enabled = self.get_enabled_providers("chat")
            if not enabled:
                raise ConfigurationError("No enabled chat provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return await provider_instance.async_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> Any:
        """异步发送流式聊天请求

        异步版本的流式聊天接口。

        Args:
            messages: 消息列表
            provider: 提供商名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            异步流式响应生成器
        """
        if provider == "default":
            enabled = self.get_enabled_providers("chat")
            if not enabled:
                raise ConfigurationError("No enabled chat provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return provider_instance.async_stream_chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        provider: str = "default",
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送文本嵌入请求

        异步版本的嵌入接口。

        Args:
            texts: 单个文本或文本列表
            provider: 提供商名称
            model: 模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        if provider == "default":
            enabled = self.get_enabled_providers("embedding")
            if not enabled:
                raise ConfigurationError("No enabled embedding provider")
            provider = list(enabled.keys())[0]

        provider_instance = self.get_provider(provider)
        if not provider_instance:
            raise ConfigurationError(f"Provider not found: {provider}")

        return await provider_instance.async_embed(
            texts=texts,
            model=model,
            **kwargs
        )

    # ==================== 配置相关 ====================

    @property
    def config(self) -> LLMConfig:
        """获取 LLM 配置管理器

        Returns:
            LLMConfig: 配置管理器实例
        """
        return self._config

    @property
    def available_providers(self) -> List[str]:
        """获取所有支持的提供商类型

        Returns:
            List[str]: 支持的提供商类型列表
        """
        return list(PROVIDER_REGISTRY.keys())

    def close(self) -> None:
        """关闭所有提供商连接，释放资源

        遍历关闭所有提供商的 HTTP 会话，清理实例缓存。
        通常在应用程序退出时调用。
        """
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()


# ==================== 模块级函数 ====================

def get_llm_provider() -> LLMProvider:
    """获取 LLM 提供商管理器的全局单例实例

    这是访问 LLM 功能的推荐入口点，保证全局只有一个实例。

    Returns:
        LLMProvider: LLM 提供商管理器单例实例

    Example:
        >>> from core.llm import get_llm_provider, Message
        >>> provider = get_llm_provider()
        >>> response = provider.chat([Message("user", "你好")])
    """
    return LLMProvider()