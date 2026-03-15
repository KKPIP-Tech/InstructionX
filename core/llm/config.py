"""
LLM Provider 配置管理
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from .exceptions import ConfigurationError


# 配置目录和文件路径
# core/llm/config.py -> 项目根目录/config
CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
CONFIG_FILE = CONFIG_DIR / "llm_providers.json"
MODELS_CACHE_FILE = CONFIG_DIR / "llm_models_cache.json"


class ProviderConfig:
    """单个 Provider 的配置"""

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
        **kwargs
    ):
        self.name = name
        self.provider_type = provider_type
        self.api_key = api_key
        self.base_url = base_url
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.enabled_chat = enabled_chat
        self.enabled_embedding = enabled_embedding
        self.support_vision = support_vision
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
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
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """从字典创建"""
        known_fields = {
            "name", "provider_type", "api_key", "base_url",
            "chat_model", "embedding_model", "enabled_chat",
            "enabled_embedding", "support_vision"
        }
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
            **extra
        )


class LLMConfig:
    """LLM 配置管理类"""

    def __init__(self):
        self._providers: Dict[str, ProviderConfig] = {}
        self._load_config()

    def _load_config(self) -> None:
        """从 JSON 文件加载配置"""
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
        """创建默认配置文件"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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
                    "support_vision": True
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

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)

        # 加载默认配置
        for name, config_data in default_config["providers"].items():
            self._providers[name] = ProviderConfig.from_dict(config_data)

    def save_config(self) -> None:
        """保存配置到 JSON 文件"""
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
        """获取指定 Provider 的配置"""
        return self._providers.get(name)

    def get_all_providers(self) -> Dict[str, ProviderConfig]:
        """获取所有 Provider 的配置"""
        return self._providers.copy()

    def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ProviderConfig]:
        """获取已启用的 Provider"""
        result = {}
        for name, config in self._providers.items():
            if feature == "chat" and config.enabled_chat:
                result[name] = config
            elif feature == "embedding" and config.enabled_embedding:
                result[name] = config
        return result

    def add_provider(self, name: str, config: ProviderConfig) -> None:
        """添加或更新 Provider 配置"""
        self._providers[name] = config
        self.save_config()

    def remove_provider(self, name: str) -> bool:
        """移除 Provider 配置"""
        if name in self._providers:
            del self._providers[name]
            self.save_config()
            return True
        return False

    @property
    def config_file_path(self) -> Path:
        """获取配置文件路径"""
        return CONFIG_FILE

    # ==================== 模型缓存 ====================

    def save_models_cache(self, provider_name: str, models: List[Dict[str, Any]]) -> None:
        """
        保存模型列表到缓存文件

        Args:
            provider_name: Provider 名称
            models: 模型信息列表
        """
        cache = self._load_models_cache()
        cache[provider_name] = models
        self._save_models_cache(cache)

    def load_models_cache(self, provider_name: str) -> Optional[List[Dict[str, Any]]]:
        """
        从缓存加载模型列表

        Args:
            provider_name: Provider 名称

        Returns:
            模型列表，如果不存在则返回 None
        """
        cache = self._load_models_cache()
        return cache.get(provider_name)

    def _load_models_cache(self) -> Dict[str, Any]:
        """加载模型缓存文件"""
        if not MODELS_CACHE_FILE.exists():
            return {}

        try:
            with open(MODELS_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_models_cache(self, cache: Dict[str, Any]) -> None:
        """保存模型缓存文件"""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(MODELS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)
