"""LLM 提供商预设目录模块

该模块以声明式目录数据描述内置 LLM 提供商预设（preset）的元数据：
显示名、适配器家族、默认端点、帮助链接、API 特性位与 Logo 文件名。
目录数据随程序发布、只读，用户实例配置在运行时继承并覆写这些默认值。

新增厂商时通常只需在 PROVIDER_PRESETS 中追加目录数据；
仅当协议家族不存在时才需要新增适配器类。

Classes:
    ProviderPreset: 单个提供商预设的元数据（frozen dataclass）

数据:
    PROVIDER_PRESETS: preset_id -> ProviderPreset 的只读目录表
    CUSTOM_ADAPTER: 自定义实例使用的兜底适配器家族键
"""

from dataclasses import dataclass, field
from typing import Dict


# 自定义实例（preset_id 为空）固定使用的兜底适配器家族键，
# 对应 OpenAI 兼容协议，不作为厂商预设在目录中展示
CUSTOM_ADAPTER = "openai-compatible"


@dataclass(frozen=True)
class ProviderPreset:
    """单个 LLM 提供商预设的元数据

    描述一个内置厂商的目录级默认值。用户配置中的 Provider 实例通过
    preset_id 关联预设并继承这些元数据；实例字段非空时优先于目录默认。

    Attributes:
        preset_id: 预设唯一标识（如 "openai" / "siliconflow"）
        display_name: 默认显示名
        adapter: 适配器家族键（对应 PROVIDER_REGISTRY 的键）
        default_base_url: 默认 API 基础地址（实例 base_url 为空时使用）
        chat_endpoint_path: 聊天端点路径（驱动 UI 最终地址预览）
        models_endpoint_path: 模型列表端点路径，空串表示不提供模型列表 API
        auth_optional: 是否允许无密钥使用（本地服务如 Ollama 为 True）
        official_url: 官网地址
        api_key_url: 密钥获取页地址（驱动 UI「获取密钥」链接）
        docs_url: 文档页地址
        models_url: 模型列表页地址
        api_features: API 特性位（如 stream_usage 表示支持流式 usage 统计）
        logo_filename: catalog/logos/ 目录下的 Logo 文件名
    """

    preset_id: str
    display_name: str
    adapter: str
    default_base_url: str = ""
    chat_endpoint_path: str = "/chat/completions"
    models_endpoint_path: str = "/models"
    auth_optional: bool = False
    official_url: str = ""
    api_key_url: str = ""
    docs_url: str = ""
    models_url: str = ""
    api_features: Dict[str, bool] = field(default_factory=dict)
    logo_filename: str = ""


# 内置提供商预设目录表（只读常量，键为 preset_id）
# 端点默认值与 core/llm/config.py 的默认配置、core/llm/providers/ 各实现保持一致；
# 帮助链接迁移自原 LLM 设置对话框中的硬编码密钥链接表
PROVIDER_PRESETS: Dict[str, ProviderPreset] = {
    "openai": ProviderPreset(
        preset_id="openai",
        display_name="OpenAI",
        adapter="openai",
        default_base_url="https://api.openai.com/v1",
        official_url="https://openai.com",
        api_key_url="https://platform.openai.com/api-keys",
        docs_url="https://platform.openai.com/docs",
        models_url="https://platform.openai.com/docs/models",
        # 对应 OpenAIProvider 的流式 usage 统计特性
        api_features={"stream_usage": True},
        logo_filename="openai.png",
    ),
    "siliconflow": ProviderPreset(
        preset_id="siliconflow",
        display_name="SiliconFlow",
        adapter="siliconflow",
        default_base_url="https://api.siliconflow.cn/v1",
        official_url="https://www.siliconflow.cn",
        api_key_url="https://www.siliconflow.cn",
        docs_url="https://docs.siliconflow.cn",
        models_url="https://cloud.siliconflow.cn/models",
        logo_filename="siliconflow.png",
    ),
    "glm": ProviderPreset(
        preset_id="glm",
        display_name="GLM",
        adapter="glm",
        default_base_url="https://open.bigmodel.cn/api/paas/v4",
        official_url="https://open.bigmodel.cn",
        api_key_url="https://open.bigmodel.cn",
        docs_url="https://docs.bigmodel.cn",
        models_url="https://docs.bigmodel.cn/cn/guide/start/model-overview",
        logo_filename="glm.png",
    ),
    "minimax": ProviderPreset(
        preset_id="minimax",
        display_name="MiniMax",
        adapter="minimax",
        default_base_url="https://api.minimax.chat/v1",
        chat_endpoint_path="/text/chatcompletion_v2",
        # MiniMax 官方未提供模型列表 API，使用预设模型目录
        models_endpoint_path="",
        official_url="https://www.minimaxi.com",
        api_key_url="https://platform.minimaxi.com",
        docs_url="https://platform.minimaxi.com/docs/api-reference",
        logo_filename="MiniMax.png",
    ),
    "ollama": ProviderPreset(
        preset_id="ollama",
        display_name="Ollama",
        adapter="ollama",
        default_base_url="http://localhost:11434",
        chat_endpoint_path="/api/chat",
        models_endpoint_path="/api/tags",
        # 本地部署服务，无需 API 密钥
        auth_optional=True,
        official_url="https://ollama.com",
        api_key_url="https://ollama.com",
        docs_url="https://github.com/ollama/ollama",
        models_url="https://ollama.com/library",
        logo_filename="ollama.png",
    ),
}
