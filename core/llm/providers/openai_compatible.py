"""自定义 OpenAI 兼容 Provider 适配器模块

该模块提供自定义 OpenAI 兼容实例的兜底适配器。预设目录之外的任何
OpenAI 兼容端点（自建网关、vLLM、LocalAI、第三方兼容服务等）均可通过
创建 ``preset_id=None``、``adapter="openai-compatible"`` 的实例零代码接入。

实现上完全复用 OpenAIProvider 的协议适配逻辑（端点、响应解析、
流式 usage 统计、自定义模型列表），仅差异化适配器标识与默认显示名，
实际端点与模型由实例配置（base_url / custom_models）驱动。

Classes:
    OpenAICompatibleProvider: 自定义 OpenAI 兼容实例的兜底适配器
"""

from .openai import OpenAIProvider


class OpenAICompatibleProvider(OpenAIProvider):
    """自定义 OpenAI 兼容实例的兜底适配器

    与 OpenAIProvider 协议行为完全一致，区别在于：
    - 适配器家族键为 ``openai-compatible``，与官方 openai 预设区分；
    - 默认显示名为「自定义 OpenAI 兼容服务」；
    - 不携带任何厂商预设模型，模型列表完全由实例配置的
      ``custom_models`` 或端点 ``/models`` API 提供。

    Class Attributes:
        provider_type: 适配器家族键 ("openai-compatible")
        provider_name: 默认显示名称 ("自定义 OpenAI 兼容服务")
    """

    provider_type = "openai-compatible"
    provider_name = "自定义 OpenAI 兼容服务"
