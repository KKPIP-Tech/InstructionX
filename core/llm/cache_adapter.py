"""LLM 缓存适配器模块

该模块提供不同 LLM 供应商的缓存适配器，将各供应商的缓存机制
统一转换为 CacheInfo 格式。

核心设计：字段路径从配置读取，不硬编码。
每个 Provider 可在 llm_providers.json 中配置 cache_fields，
指定如何从 API 响应中提取缓存相关字段。

适配器:
    - CacheAdapter: 适配器基类
    - ConfigurableCacheAdapter: 基于配置的泛化适配器

字段路径格式: 点号分隔的嵌套路径
    例如: "usage.prompt_tokens_details.cached_tokens"
    对应 response["usage"]["prompt_tokens_details"]["cached_tokens"]
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .types_cache import CacheInfo, CacheType


# ==================== 内置默认配置 ====================
# 这些配置可被 llm_providers.json 中的 cache_fields 覆盖

DEFAULT_CACHE_CONFIG: Dict[str, Dict[str, Any]] = {
    "minimax": {
        "enabled": True,
        "cached_tokens_path": "usage.cache_read_input_tokens",
        "total_tokens_path": "usage.prompt_tokens",
        "cache_type": "prompt_cache",
        "ttl_seconds": None,
    },
    "openai": {
        "enabled": True,
        "cached_tokens_path": "usage.prompt_tokens_details.cached_tokens",
        "total_tokens_path": "usage.prompt_tokens",
        "cache_type": "kv_cache",
        "ttl_seconds": None,
    },
    "anthropic": {
        "enabled": True,
        "cached_tokens_path": "usage.cache_read_input_tokens",
        "total_tokens_path": "usage.input_tokens",
        "cache_type": "anthropic_cache",
        "ttl_seconds": 300,  # 5分钟
    },
    "gemini": {
        "enabled": True,
        "cached_tokens_path": "usageMetadata.cachedContentTokens",
        "total_tokens_path": "usageMetadata.promptTokenCount",
        "cache_type": "context_cache",
        "ttl_seconds": 3600,  # 1小时
    },
    "glm": {
        "enabled": True,
        "cached_tokens_path": "usage.cache_read_input_tokens",
        "total_tokens_path": "usage.prompt_tokens",
        "cache_type": "prompt_cache",
        "ttl_seconds": None,
    },
    "ollama": {
        "enabled": False,
        "cached_tokens_path": None,
        "total_tokens_path": None,
        "cache_type": "none",
        "ttl_seconds": None,
    },
    "siliconflow": {
        "enabled": True,
        "cached_tokens_path": "usage.prompt_tokens_details.cached_tokens",
        "total_tokens_path": "usage.prompt_tokens",
        "cache_type": "kv_cache",
        "ttl_seconds": None,
    },
}


class CacheAdapter(ABC):
    """缓存信息适配器基类

    定义缓存适配器必须实现的接口方法。
    默认实现使用配置驱动的字段提取。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """初始化适配器

        Args:
            config: 缓存配置字典，可覆盖 DEFAULT_CACHE_CONFIG
        """
        self._config: Dict[str, Any] = {}
        self._init_config(config)

    def _init_config(self, config: Optional[Dict[str, Any]]) -> None:
        """从默认配置和传入配置合并"""
        # 子类设置 provider_type
        provider_type = getattr(self, "provider_type", "unknown")
        default = DEFAULT_CACHE_CONFIG.get(provider_type, {}).copy()
        if config:
            default.update(config)
        self._config = default

    @property
    @abstractmethod
    def provider_type(self) -> str:
        """供应商类型"""
        pass

    def _get_nested(self, response: Dict, path: str) -> Any:
        """从嵌套字典中按路径提取值

        Args:
            response: API 响应字典
            path: 点号分隔的路径，如 "usage.prompt_tokens_details.cached_tokens"

        Returns:
            路径对应的值，如果路径不存在则返回 None
        """
        if not path:
            return None
        parts = path.split(".")
        current: Any = response
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
                if current is None:
                    return None
            else:
                return None
        return current

    def extract_cache_info(self, response: Dict) -> CacheInfo:
        """从 API 响应中提取缓存信息

        Args:
            response: API 响应字典

        Returns:
            CacheInfo: 缓存信息对象
        """
        if not self._config.get("enabled", False):
            return CacheInfo(enabled=False, cache_type=CacheType.NONE.value)

        cached_tokens_path = self._config.get("cached_tokens_path")
        total_tokens_path = self._config.get("total_tokens_path")

        cached = self._get_nested(response, cached_tokens_path) if cached_tokens_path else 0
        total = self._get_nested(response, total_tokens_path) if total_tokens_path else 0

        cached = cached or 0
        total = total or 0

        cache_type_str = self._config.get("cache_type", "none")
        if cache_type_str == "none" or cached <= 0:
            cache_type_str = CacheType.NONE.value

        return CacheInfo(
            enabled=cached > 0 or total > 0,
            cache_type=cache_type_str,
            cached_tokens=cached,
            new_tokens=max(0, total - cached),
            cache_hit=cached > 0,
            cache_hit_rate=cached / total if total > 0 else 0.0,
            ttl_seconds=self._config.get("ttl_seconds"),
            raw_data={"response_sample": str(response)[:500] if response else ""},
        )

    def is_cache_available(self, model: Optional[str] = None) -> bool:
        """检查模型是否支持缓存

        Args:
            model: 模型名称

        Returns:
            bool: 是否支持
        """
        return self._config.get("enabled", False)

    def prepare_cache_params(self, config: Dict) -> Dict:
        """准备缓存相关请求参数（供将来扩展）

        Args:
            config: 提供商配置

        Returns:
            Dict: 缓存相关参数
        """
        return {}


def get_cache_adapter(
    provider_type: str,
    cache_config: Optional[Dict[str, Any]] = None,
) -> CacheAdapter:
    """获取缓存适配器

    Args:
        provider_type: 供应商类型
        cache_config: 可选的缓存配置覆盖

    Returns:
        CacheAdapter: 缓存适配器实例
    """
    # 使用配置驱动的通用适配器
    adapter = ConfigurableCacheAdapter(provider_type, cache_config)
    return adapter


class ConfigurableCacheAdapter(CacheAdapter):
    """基于配置的泛化缓存适配器

    所有供应商使用同一个适配器类，通过配置字典决定字段提取路径。
    用户可在 llm_providers.json 中覆盖任意字段路径。
    """

    def __init__(
        self,
        provider_type: str,
        cache_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._provider_type = provider_type
        self._custom_config = cache_config or {}
        super().__init__(cache_config)

    @property
    def provider_type(self) -> str:
        return self._provider_type

    def _init_config(self, config: Optional[Dict[str, Any]]) -> None:
        """合并默认配置和自定义配置"""
        default = DEFAULT_CACHE_CONFIG.get(self._provider_type, {}).copy()
        if config:
            default.update(config)
        elif self._custom_config:
            default.update(self._custom_config)
        self._config = default
