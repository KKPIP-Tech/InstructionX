"""LLM 缓存相关类型定义

该模块定义统一的缓存信息类型，支持所有 LLM 供应商的缓存机制。
采用适配器模式，通过配置驱动的抽象层隔离不同供应商的实现差异。

类型:
    - CacheType: 缓存类型枚举
    - CacheInfo: 统一缓存信息
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class CacheType(Enum):
    """缓存类型枚举"""
    NONE = "none"
    PROMPT_CACHE = "prompt_cache"           # MiniMax 被动缓存
    ANTHROPIC_CACHE = "anthropic_cache"       # Anthropic 主动缓存
    KV_CACHE = "kv_cache"                    # OpenAI 自动 KV Cache
    CONTEXT_CACHE = "context_cache"           # Gemini 上下文缓存
    SPECULATIVE = "speculative"               # 推测解码


@dataclass
class CacheInfo:
    """统一缓存信息 - 适配所有供应商

    这是缓存信息的核心抽象类，所有 LLM 供应商的缓存信息
    都会被转换为这个统一格式，供上层代码使用。

    Attributes:
        enabled: 是否启用了缓存
        cache_type: 缓存类型 (CacheType value string)
        cached_tokens: 命中缓存的 token 数
        new_tokens: 新增的 token 数（非缓存）
        cache_hit: 是否命中缓存
        cache_hit_rate: 缓存命中率 (0.0 ~ 1.0)
        ttl_seconds: 缓存过期时间（秒），None 表示未知
        raw_data: 供应商原始信息
    """
    enabled: bool = False
    cache_type: str = CacheType.NONE.value
    cached_tokens: int = 0
    new_tokens: int = 0
    cache_hit: bool = False
    cache_hit_rate: float = 0.0
    ttl_seconds: Optional[int] = None
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_input_tokens(self) -> int:
        """总输入 token 数"""
        return self.cached_tokens + self.new_tokens

    @property
    def efficiency(self) -> float:
        """缓存效率（命中 token / 总输入 token）"""
        total = self.total_input_tokens
        if total == 0:
            return 0.0
        return self.cached_tokens / total
