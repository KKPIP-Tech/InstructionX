"""LLM 提供商模块 - 适配器家族注册表与各提供商实现

该模块包含所有具体 LLM 提供商的实现类，采用注册机制动态管理。
注册表的键为**适配器家族**（adapter）而非厂商：多个预设可共享同一
适配器（协议兼容的厂商只需在目录中追加数据）；自定义实例
（preset_id=None）固定使用 ``openai-compatible`` 兜底适配器。

当前注册的适配器家族:
    - minimax: MiniMax 大模型
    - siliconflow: SiliconFlow API
    - glm: 智谱 GLM 大模型
    - ollama: Ollama 本地大模型
    - openai: OpenAI 兼容 API
    - openai-compatible: 自定义 OpenAI 兼容实例的兜底适配器

Classes:
    BaseProvider: 提供商抽象基类
    MiniMaxProvider: MiniMax 提供商实现
    SiliconFlowProvider: SiliconFlow 提供商实现
    GLMProvider: GLM 提供商实现
    OllamaProvider: Ollama 提供商实现
    OpenAIProvider: OpenAI 兼容 API 实现
    OpenAICompatibleProvider: 自定义 OpenAI 兼容兜底适配器

Functions:
    register_adapter: 注册适配器家族键 -> 适配器类
    get_adapter_class: 根据适配器家族键获取适配器类
    get_all_adapters: 获取所有已注册的适配器家族键
    register_provider / get_provider_class / get_all_provider_types:
        保留的旧名薄别名（语义为适配器家族），供尚未迁移的调用点使用

使用示例:
    >>> from core.llm.providers import get_adapter_class
    >>> provider_class = get_adapter_class("glm")
    >>> provider = provider_class(config, provider_name="my_glm")
"""

from .base import BaseProvider
from .minimax import MiniMaxProvider
from .siliconflow import SiliconFlowProvider
from .glm import GLMProvider
from .ollama import OllamaProvider
from .openai import OpenAIProvider
from .openai_compatible import OpenAICompatibleProvider

# ==================== 适配器注册表 ====================

# 适配器注册表：适配器家族键 -> 适配器类的映射
# 用于根据实例配置中的 adapter 动态创建对应的提供商实例
PROVIDER_REGISTRY = {}


def register_adapter(adapter_key, provider_class):
    """注册适配器家族键与适配器类的映射

    Args:
        adapter_key: 适配器家族键（如 "glm"、"openai-compatible"）
        provider_class: 适配器类

    Returns:
        原始的 provider_class（无修改，可用作装饰器）
    """
    PROVIDER_REGISTRY[adapter_key] = provider_class
    return provider_class


def get_adapter_class(adapter_key: str):
    """根据适配器家族键获取对应的适配器类

    Args:
        adapter_key: 适配器家族键（如 "glm"、"minimax"）

    Returns:
        Optional[type]: 适配器类，如果不存在返回 None
    """
    return PROVIDER_REGISTRY.get(adapter_key)


def get_all_adapters():
    """获取所有已注册的适配器家族键

    Returns:
        List[str]: 已注册的适配器家族键列表
    """
    return list(PROVIDER_REGISTRY.keys())


# ==================== 旧名兼容别名 ====================
# 以下函数保留旧名（语义为适配器家族），内部转发到新函数；
# ui/、scripts/ 等旧调用点在后续阶段统一切换后移除。

def register_provider(provider_class):
    """Provider 注册装饰器（保留旧名，语义为适配器家族）

    将适配器类按其 provider_type 类属性注册到全局注册表中。
    等价于 register_adapter(provider_class.provider_type, provider_class)。

    Args:
        provider_class: 适配器类（需具有 provider_type 类属性）

    Returns:
        原始的 provider_class（无修改）

    Example:
        @register_provider
        class MyProvider(BaseProvider):
            provider_type = "my_provider"
    """
    return register_adapter(provider_class.provider_type, provider_class)


def get_provider_class(provider_type: str):
    """根据提供商类型获取对应的类（保留旧名，语义为适配器家族）

    等价于 get_adapter_class(provider_type)。

    Args:
        provider_type: 提供商类型标识符（即适配器家族键，如 "glm"）

    Returns:
        Optional[type]: 适配器类，如果不存在返回 None
    """
    return get_adapter_class(provider_type)


def get_all_provider_types():
    """获取所有已注册的 Provider 类型（保留旧名，语义为适配器家族）

    等价于 get_all_adapters()。

    Returns:
        List[str]: 已注册的适配器家族键列表
    """
    return get_all_adapters()


# ==================== 自动注册 ====================

# 模块导入时自动注册所有适配器（键为各适配器类的 provider_type 类属性）
register_provider(MiniMaxProvider)
register_provider(SiliconFlowProvider)
register_provider(GLMProvider)
register_provider(OllamaProvider)
register_provider(OpenAIProvider)
register_provider(OpenAICompatibleProvider)


__all__ = [
    "BaseProvider",
    "MiniMaxProvider",
    "SiliconFlowProvider",
    "GLMProvider",
    "OllamaProvider",
    "OpenAIProvider",
    "OpenAICompatibleProvider",
    "register_adapter",
    "get_adapter_class",
    "get_all_adapters",
    "register_provider",
    "get_provider_class",
    "get_all_provider_types",
    "PROVIDER_REGISTRY",
]
