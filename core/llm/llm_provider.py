"""
LLM Provider 管理器 - 单例模式
"""
import threading
from typing import Dict, Any, Optional, List, Union, Callable, AsyncIterator, TYPE_CHECKING

from .config import LLMConfig, ProviderConfig
from .provider_interface import ILLM, Message, ChatResponse, EmbeddingResponse, ModelInfo
from .providers import get_provider_class, PROVIDER_REGISTRY
from .exceptions import ConfigurationError

if TYPE_CHECKING:
    from .provider_interface import ChatResponse


class LLMProvider:
    """
    LLM Provider 管理器 - 单例模式

    用于一次性初始化所有 Provider，支持多任务并发调用多个语言模型
    """

    _instance: Optional['LLMProvider'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化 LLM Provider 管理器"""
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True
        self._config = LLMConfig()
        self._providers: Dict[str, ILLM] = {}
        self._models_cache: Dict[str, List[ModelInfo]] = {}  # 模型缓存
        self._init_providers()
        self._fetch_all_models()  # 启动时自动拉取模型

    def _init_providers(self) -> None:
        """初始化所有已配置的 Provider"""
        provider_configs = self._config.get_all_providers()

        for name, config_data in provider_configs.items():
            try:
                self._create_provider(name, config_data.to_dict())
            except Exception as e:
                print(f"Failed to initialize provider {name}: {e}")

    def _fetch_all_models(self) -> None:
        """启动时自动拉取所有 Provider 的模型（强制从 API 拉取）"""
        for name, provider in self._providers.items():
            try:
                # 强制从 API 拉取，拉取失败则自动从缓存加载
                models = provider.refresh_models(force=True)
                self._models_cache[name] = models
                print(f"Loaded {len(models)} models for {name}")
            except Exception as e:
                print(f"Failed to fetch models for {name}: {e}")
                self._models_cache[name] = []

    def refresh_provider_models(self, provider_name: str, force: bool = False) -> List[ModelInfo]:
        """
        刷新指定 Provider 的模型列表

        Args:
            provider_name: Provider 名称
            force: 是否强制从 API 刷新

        Returns:
            模型列表
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return []

        try:
            models = provider.refresh_models(force=force)
            self._models_cache[provider_name] = models
            return models
        except Exception as e:
            print(f"Failed to refresh models for {provider_name}: {e}")
            return []

    def refresh_all_models(self, force: bool = False) -> Dict[str, List[ModelInfo]]:
        """
        刷新所有 Provider 的模型列表

        Args:
            force: 是否强制从 API 刷新

        Returns:
            每个 Provider 的模型列表
        """
        for name in self._providers.keys():
            self.refresh_provider_models(name, force=force)
        return self._models_cache

    def get_cached_models(self, provider_name: str) -> List[ModelInfo]:
        """
        获取缓存的模型列表

        Args:
            provider_name: Provider 名称

        Returns:
            模型列表
        """
        return self._models_cache.get(provider_name, [])

    def _create_provider(self, name: str, config: Dict[str, Any]) -> Optional[ILLM]:
        """创建 Provider 实例"""
        provider_type = config.get("provider_type", name)
        provider_class = get_provider_class(provider_type)

        if not provider_class:
            raise ConfigurationError(f"Unknown provider type: {provider_type}")

        # 传递 provider_name 用于模型缓存标识
        provider = provider_class(config, provider_name=name)
        self._providers[name] = provider
        return provider

    def get_provider(self, name: str) -> Optional[ILLM]:
        """获取指定 Provider"""
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ILLM]:
        """获取所有 Provider"""
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ILLM]:
        """获取已启用的 Provider"""
        result = {}
        enabled_configs = self._config.get_enabled_providers(feature)

        for name in enabled_configs.keys():
            provider = self._providers.get(name)
            if provider:
                result[name] = provider

        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新 Provider"""
        self._config.add_provider(name, config)
        self._create_provider(name, config.to_dict())

    def remove_provider(self, name: str) -> bool:
        """移除 Provider"""
        if name in self._providers:
            provider = self._providers[name]
            provider.close()
            del self._providers[name]

        return self._config.remove_provider(name)

    def reload_config(self) -> None:
        """重新加载配置"""
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
        """
        发送聊天请求

        Args:
            messages: 消息列表
            provider: Provider 名称 ("default" 使用第一个启用的 Provider)
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应
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
        """
        发送流式聊天请求

        Args:
            messages: 消息列表
            provider: Provider 名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            callback: 流式回调函数
            **kwargs: 其他参数

        Returns:
            流式响应列表
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
        """
        发送嵌入请求

        Args:
            texts: 文本或文本列表
            provider: Provider 名称
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

        return provider_instance.embed(
            texts=texts,
            model=model,
            **kwargs
        )

    def get_models(self, provider: Optional[str] = None) -> Dict[str, List[ModelInfo]]:
        """
        获取可用模型列表

        Args:
            provider: Provider 名称 (None 表示所有 Provider)

        Returns:
            Dict[str, List[ModelInfo]]: 每个 Provider 的模型列表
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
        """异步发送聊天请求"""
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
        """异步发送流式聊天请求"""
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
        """异步发送嵌入请求"""
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
        """获取配置管理器"""
        return self._config

    @property
    def available_providers(self) -> List[str]:
        """获取可用 Provider 类型列表"""
        return list(PROVIDER_REGISTRY.keys())

    def close(self) -> None:
        """关闭所有 Provider 连接"""
        for provider in self._providers.values():
            provider.close()
        self._providers.clear()


# 全局单例实例访问函数
def get_llm_provider() -> LLMProvider:
    """获取 LLM Provider 单例实例"""
    return LLMProvider()
