"""LLM 提供商模块 - 各提供商实现

该模块包含所有具体 LLM 提供商的实现类，采用注册机制动态管理。
每个提供商都继承自 BaseProvider 抽象基类，实现各自的 API 调用逻辑。

当前支持的提供商:
    - MiniMaxProvider: MiniMax 大模型
    - SiliconFlowProvider: SiliconFlow API
    - GLMProvider: 智谱 GLM 大模型
    - OllamaProvider: Ollama 本地大模型

Classes:
    BaseProvider: 提供商抽象基类
    MiniMaxProvider: MiniMax 提供商实现
    SiliconFlowProvider: SiliconFlow 提供商实现
    GLMProvider: GLM 提供商实现
    OllamaProvider: Ollama 提供商实现

Functions:
    register_provider: 提供商注册装饰器
    get_provider_class: 根据类型获取提供商类
    get_all_provider_types: 获取所有已注册的提供商类型

使用示例:
    >>> from core.llm.providers import get_provider_class, PROVIDER_REGISTRY
    >>> provider_class = get_provider_class("glm")
    >>> provider = provider_class(config, provider_name="my_glm")
"""

from .base import BaseProvider
from .minimax import MiniMaxProvider
from .siliconflow import SiliconFlowProvider
from .glm import GLMProvider
from .ollama import OllamaProvider

# ==================== Provider 注册表 ====================

# Provider 注册表：provider_type -> provider_class 的映射
# 用于根据配置中的 provider_type 动态创建对应的提供商实例
PROVIDER_REGISTRY = {}


def register_provider(provider_class):
    """Provider 注册装饰器

    将提供商类注册到全局注册表中。
    被装饰的类会自动获得 provider_type 属性，用于注册表映射。

    Args:
        provider_class: 提供商类（需具有 provider_type 类属性）

    Returns:
        原始的 provider_class（无修改）

    Example:
        @register_provider
        class MyProvider(BaseProvider):
            provider_type = "my_provider"
    """
    PROVIDER_REGISTRY[provider_class.provider_type] = provider_class
    return provider_class


def get_provider_class(provider_type: str):
    """根据提供商类型获取对应的类

    Args:
        provider_type: 提供商类型标识符（如 "glm", "minimax"）

    Returns:
        Optional[type]: 提供商类，如果不存在返回 None
    """
    return PROVIDER_REGISTRY.get(provider_type)


def get_all_provider_types():
    """获取所有已注册的 Provider 类型

    Returns:
        List[str]: 已注册的提供商类型列表
    """
    return list(PROVIDER_REGISTRY.keys())


# ==================== 自动注册 ====================

# 模块导入时自动注册所有 Provider
# 使用装饰器模式，在类定义时自动完成注册
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