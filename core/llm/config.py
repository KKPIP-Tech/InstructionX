"""LLM 配置模块 - 提供商配置管理

该模块负责管理 LLM 提供商的配置信息，支持从 JSON 文件加载和保存配置。
提供默认配置模板，支持添加、删除、启用/禁用提供商等操作。

配置结构:
    - config/llm_providers.json: 提供商配置
    - config/llm_models_cache.json: 模型列表缓存

Classes:
    ProviderConfig: 单个提供商的配置类
    LLMConfig: 提供商配置管理类

使用示例:
    >>> from core.llm.config import LLMConfig, ProviderConfig
    >>> config = LLMConfig()
    >>> provider = config.get_provider("glm")
    >>> print(provider.chat_model)
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List

from .exceptions import ConfigurationError


# ==================== 配置路径常量 ====================

# 配置目录: core/llm/config.py -> 项目根目录/config
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

# 提供商配置文件路径
CONFIG_FILE = CONFIG_DIR / "llm_providers.json"

# 模型缓存文件路径
MODELS_CACHE_FILE = CONFIG_DIR / "llm_models_cache.json"


class ProviderConfig:
    """单个 LLM 提供商的配置类

    封装单个提供商的所有配置信息，包括 API 密钥、端 URL、模型名称等。
    支持序列化为字典和从字典反序列化。

    Attributes:
        name: 提供商显示名称
        provider_type: 提供商类型标识（如 "glm", "minimax", "ollama"）
        api_key: API 密钥
        base_url: API 基础 URL
        chat_model: 聊天模型名称
        embedding_model: 嵌入模型名称
        enabled_chat: 是否启用聊天功能
        enabled_embedding: 是否启用嵌入功能
        support_vision: 是否支持视觉（多模态）
        extra: 额外的配置参数
    """

    def __init__(
        self,
        name: str,
        provider_type: str,
        api_key: str = "",
        base_url: str = "",
        chat_model: str = "",
        embedding_model: str = "",
        enabled_chat: bool = True,
        enabled_embedding: bool = False,
        support_vision: bool = True,
        cache_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """初始化提供商配置

        Args:
            name: 提供商显示名称
            provider_type: 提供商类型标识
            api_key: API 密钥（可选）
            base_url: API 基础 URL（可选）
            chat_model: 聊天模型名称（可选）
            embedding_model: 嵌入模型名称（可选）
            enabled_chat: 是否启用聊天功能，默认 True
            enabled_embedding: 是否启用嵌入功能，默认 False
            support_vision: 是否支持视觉（多模态），默认 True
            cache_fields: 缓存字段配置（可选）
            **kwargs: 额外的配置参数
        """
        self.name = name
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.enabled_chat = enabled_chat
        self.enabled_embedding = enabled_embedding
        self.support_vision = support_vision
        self.cache_fields = cache_fields or {}
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典

        Returns:
            Dict[str, Any]: 包含所有配置项的字典
        """
        return {
            "name": self.name,
            "provider_type": self.provider_type,
            "api_key": self.api_key,
            "base_url": self.base_url,
            "chat_model": self.chat_model,
            "embedding_model": self.embedding_model,
            "enabled_chat": self.enabled_chat,
            "enabled_embedding": self.enabled_embedding,
            "support_vision": self.support_vision,
            "cache_fields": self.cache_fields,
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """从字典创建配置对象

        将字典数据反序列化为 ProviderConfig 对象。
        未知字段会被保存到 extra 属性中。

        Args:
            data: 包含配置信息的字典

        Returns:
            ProviderConfig: 配置对象实例
        """
        # 已知的标准字段
        known_fields = {
            "name", "provider_type", "api_key", "base_url",
            "chat_model", "embedding_model", "enabled_chat",
            "enabled_embedding", "support_vision", "cache_fields"
        }
        # 将未知字段保存到 extra 中
        extra = {k: v for k, v in data.items() if k not in known_fields}
        return cls(
            name=data.get("name", ""),
            provider_type=data.get("provider_type", ""),
            api_key=data.get("api_key", ""),
            base_url=data.get("base_url", ""),
            chat_model=data.get("chat_model", ""),
            embedding_model=data.get("embedding_model", ""),
            enabled_chat=data.get("enabled_chat", True),
            enabled_embedding=data.get("enabled_embedding", False),
            support_vision=data.get("support_vision", True),
            cache_fields=data.get("cache_fields"),
            **extra
        )


class LLMConfig:
    """LLM 提供商配置管理类

    负责加载、保存和管理所有 LLM 提供商的配置。
    支持从 JSON 文件加载配置、创建默认配置、获取/设置提供商等操作。

    Features:
        - 从 JSON 文件加载提供商配置
        - 自动创建默认配置文件（首次运行时）
        - 获取/设置单个提供商配置
        - 获取已启用的提供商列表
        - 模型列表缓存管理
    """

    def __init__(self):
        """初始化 LLM 配置管理器

        构造函数会自动调用 _load_config() 方法加载配置。
        如果配置文件不存在，会自动创建默认配置。
        """
        self._providers: Dict[str, ProviderConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        """从 JSON 文件加载配置

        读取 config/llm_providers.json 文件，解析并加载所有提供商配置。
        如果文件不存在，则创建默认配置。

        Raises:
            ConfigurationError: 配置文件格式错误时抛出
        """
        # 如果配置文件不存在，创建默认配置
        if not CONFIG_FILE.exists():
            self._create_default_config()
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            providers = data.get("providers", {})
            for name, config_data in providers.items():
                self._providers[name] = ProviderConfig.from_dict(config_data)
        except Exception as e:
            raise ConfigurationError(f"Failed to load config: {e}")

    def _create_default_config(self) -> None:
        """创建默认配置文件

        在配置目录下创建 llm_providers.json 文件，包含默认的提供商配置。
        默认包含 MiniMax、SiliconFlow、GLM、Ollama 四个提供商的模板配置。

        配置项说明:
            - api_key: 默认为空的，需要用户填写
            - base_url: 各提供商的 API 端点
            - chat_model: 默认选择的聊天模型
            - embedding_model: 默认选择的嵌入模型
        """
        # 确保配置目录存在
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        # 默认配置模板
        default_config = {
            "providers": {
                "minimax": {
                    "name": "MiniMax",
                    "provider_type": "minimax",
                    "api_key": "",
                    "base_url": "https://api.minimax.chat/v1",
                    "chat_model": "MiniMax-M2.5",
                    "embedding_model": "embedding-2",
                    "enabled_chat": True,
                    "enabled_embedding": True,
                    "support_vision": False
                },
                "siliconflow": {
                    "name": "SiliconFlow",
                    "provider_type": "siliconflow",
                    "api_key": "",
                    "base_url": "https://api.siliconflow.cn/v1",
                    "chat_model": "Pro/deepseek-ai/DeepSeek-V3",
                    "embedding_model": "BAAI/bge-m3",
                    "enabled_chat": True,
                    "enabled_embedding": True,
                    "support_vision": True
                },
                "glm": {
                    "name": "GLM",
                    "provider_type": "glm",
                    "api_key": "",
                    "base_url": "https://open.bigmodel.cn/api/paas/v4",
                    "chat_model": "glm-4",
                    "embedding_model": "embedding-3",
                    "enabled_chat": True,
                    "enabled_embedding": True,
                    "support_vision": True
                },
                "ollama": {
                    "name": "Ollama",
                    "provider_type": "ollama",
                    "api_key": "",
                    "base_url": "http://localhost:11434",
                    "chat_model": "llama3.1",
                    "embedding_model": "nomic-embed-text",
                    "enabled_chat": True,
                    "enabled_embedding": True,
                    "support_vision": True
                }
            }
        }

        # 写入配置文件
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)

        # 加载默认配置到内存
        for name, config_data in default_config["providers"].items():
            self._providers[name] = ProviderConfig.from_dict(config_data)

    def save_config(self) -> None:
        """保存配置到 JSON 文件

        将当前内存中的所有提供商配置序列化并保存到配置文件。
        """
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "providers": {
                name: config.to_dict()
                for name, config in self._providers.items()
            }
        }

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """获取指定提供商配置

        Args:
            name: 提供商名称（键名）

        Returns:
            Optional[ProviderConfig]: 提供商配置对象，如果不存在返回 None
        """
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ProviderConfig]:
        """获取所有提供商配置

        Returns:
            Dict[str, ProviderConfig]: 提供商名称到配置对象的映射字典
        """
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ProviderConfig]:
        """获取已启用的提供商列表

        根据功能类型筛选已启用的提供商。

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            Dict[str, ProviderConfig]: 已启用的提供商映射字典
        """
        result = {}
        for name, config in self._providers.items():
            if feature == "chat" and config.enabled_chat:
                result[name] = config
            elif feature == "embedding" and config.enabled_embedding:
                result[name] = config
        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新提供商配置

        Args:
            name: 提供商名称
            config: 提供商配置对象
        """
        self._providers[name] = config
        self.save_config()

    def remove_provider(self, name: str) -> bool:
        """移除提供商配置

        Args:
            name: 提供商名称

        Returns:
            bool: 是否成功移除
        """
        if name in self._providers:
            del self._providers[name]
            self.save_config()
            return True
        return False

    @property
    def config_file_path(self) -> Path:
        """获取配置文件路径

        Returns:
            Path: 配置文件路径对象
        """
        return CONFIG_FILE

    # ==================== 模型缓存 ====================

    def save_models_cache(self, provider_name: str, models: List[Dict[str, Any]]) -> None:
        """保存模型列表到缓存文件

        将指定提供商的模型列表缓存到本地文件，减少 API 调用频率。

        Args:
            provider_name: 提供商名称
            models: 模型信息列表
        """
        cache = self._load_models_cache()
        cache[provider_name] = models
        self._save_models_cache(cache)

    def load_models_cache(self, provider_name: str) -> Optional[List[Dict[str, Any]]]:
        """从缓存加载模型列表

        Args:
            provider_name: 提供商名称

        Returns:
            Optional[List[Dict[str, Any]]]: 模型列表，如果不存在返回 None
        """
        cache = self._load_models_cache()
        return cache.get(provider_name)

    def _load_models_cache(self) -> Dict[str, Any]:
        """加载模型缓存文件

        Returns:
            Dict[str, Any]: 缓存数据字典
        """
        if not MODELS_CACHE_FILE.exists():
            return {}

        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_models_cache(self, cache: Dict[str, Any]) -> None:
        """保存模型缓存文件

        Args:
            cache: 缓存数据字典
        """
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODELS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)