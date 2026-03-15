"""
LLM Provider 实现模块
"""
from .base import BaseProvider
from .minimax import MiniMaxProvider
from .siliconflow import SiliconFlowProvider
from .glm import GLMProvider
from .ollama import OllamaProvider

# Provider 注册表
PROVIDER_REGISTRY = {}


def register_provider(provider_class):
    """Provider 注册装饰器"""
    PROVIDER_REGISTRY[provider_class.provider_type] = provider_class
    return provider_class


def get_provider_class(provider_type: str):
    """获取 Provider 类"""
    return PROVIDER_REGISTRY.get(provider_type)


def get_all_provider_types():
    """获取所有已注册的 Provider 类型"""
    return list(PROVIDER_REGISTRY.keys())


# 自动注册所有 Provider
register_provider(MiniMaxProvider)
register_provider(SiliconFlowProvider)
register_provider(GLMProvider)
register_provider(OllamaProvider)

__all__ = [
    "BaseProvider",
    "MiniMaxProvider",
    "SiliconFlowProvider",
    "GLMProvider",
    "OllamaProvider",
    "register_provider",
    "get_provider_class",
    "get_all_provider_types",
    "PROVIDER_REGISTRY",
]
