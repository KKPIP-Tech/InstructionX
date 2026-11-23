"""测试辅助模块：Mock 适配器、配置样本工厂与 LLM 环境隔离

独立成模块（而非放在 conftest.py）是为了让任意层级的测试目录都能
稳定导入（conftest 模块名在多层 conftest 并存时会被就近遮蔽）。
全部工具无真实网络访问、不含真实密钥。

- MockAdapter / MOCK_ADAPTER_KEY：可控 Mock 适配器（注册表临时注入）；
- build_v1_sample / build_v2_sample / make_mock_provider_config：配置样本工厂；
- isolated_llm_env：LLM 运行环境隔离上下文管理器，供各测试目录的
  conftest 包装为 fixture（test/core/llm 与 test/ui_tests/llm_settings 共用）。
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import core.llm.config as _config_mod
import core.llm.plugin_service as _plugin_service_mod
import core.llm.usage_record_store as _usage_store_mod
from core.llm.config import LLMConfig, ProviderConfig
from core.llm.llm_provider import LLMProvider
from core.llm.provider_interface import (
    ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo,
)
from core.llm.providers import PROVIDER_REGISTRY, register_adapter
from core.llm.secure_keys import encode_secret


# ==================== Mock 适配器 ====================

# Mock 适配器家族键（注册表临时注入，用例结束移除）
MOCK_ADAPTER_KEY = "mock-adapter"
# Mock 实例的初始读取超时（秒），供 check_model 超时覆盖/恢复断言
MOCK_INITIAL_TIMEOUT = 60
# Mock 适配器默认模型 id
MOCK_CHAT_MODEL_ID = "mock-chat-1"
MOCK_EMBEDDING_MODEL_ID = "mock-emb-1"


class MockAdapter:
    """可控的 mock 适配器：记录调用、可注入异常，无任何网络访问"""

    provider_type = MOCK_ADAPTER_KEY

    def __init__(self, config: Optional[Dict] = None, provider_name: str = ""):
        config = config or {}
        self.config = config
        self.provider_name = provider_name
        self.chat_model = config.get("chat_model", "")
        self.embedding_model = config.get("embedding_model", "")
        self.last_error = None
        self.timeout = MOCK_INITIAL_TIMEOUT
        # 调用记录与行为控制
        self.chat_calls: List[Dict] = []
        self.embed_calls: List[Dict] = []
        self.chat_error: Optional[Exception] = None
        self.refresh_error: Optional[Exception] = None
        self.chat_usage: Optional[UsageInfo] = None
        self.stream_chunks: Optional[List[ChatResponse]] = None
        self.models = [
            ModelInfo(id=MOCK_CHAT_MODEL_ID, name=MOCK_CHAT_MODEL_ID),
            ModelInfo(id=MOCK_EMBEDDING_MODEL_ID,
                      name=MOCK_EMBEDDING_MODEL_ID, support_embedding=True),
        ]

    def chat(self, messages, model=None, **kwargs):
        """记录调用（含调用瞬间的 timeout，供超时覆盖断言）"""
        self.chat_calls.append({
            "messages": messages, "model": model,
            "seen_timeout": self.timeout, **kwargs,
        })
        if self.chat_error is not None:
            raise self.chat_error
        return ChatResponse(
            content="mock 回复", model=model or MOCK_CHAT_MODEL_ID,
            usage=self.chat_usage,
        )

    def stream_chat(self, messages, model=None, **kwargs):
        """返回 ChatResponse 块迭代器（可由 stream_chunks 定制）"""
        self.chat_calls.append({
            "messages": messages, "model": model,
            "seen_timeout": self.timeout, "stream": True, **kwargs,
        })
        if self.chat_error is not None:
            raise self.chat_error
        chunks = self.stream_chunks
        if chunks is None:
            chunks = [
                ChatResponse(content="mock ", model=model or MOCK_CHAT_MODEL_ID),
                ChatResponse(content="回复", model=model or MOCK_CHAT_MODEL_ID),
            ]
        return iter(chunks)

    def embed(self, texts, model=None, **kwargs):
        """记录嵌入调用并返回固定向量"""
        self.embed_calls.append({"texts": texts, "model": model, **kwargs})
        texts_list = texts if isinstance(texts, list) else [texts]
        return [
            EmbeddingResponse(embedding=[0.1, 0.2],
                              model=model or MOCK_EMBEDDING_MODEL_ID)
            for _ in texts_list
        ]

    def refresh_models(self, force: bool = False):
        """刷新模型列表（可经 refresh_error 注入失败）"""
        if self.refresh_error is not None:
            raise self.refresh_error
        return list(self.models)

    def get_models(self):
        """返回模型列表"""
        return list(self.models)

    def validate_config(self):
        """配置校验（恒成功）"""
        return True

    def close(self):
        """关闭连接（无操作）"""


# ==================== LLM 环境隔离 ====================

@contextmanager
def isolated_llm_env(tmp_path: Path, monkeypatch) -> Iterator[Path]:
    """隔离 LLM 运行环境（供各测试目录 conftest 包装为 autouse fixture）

    - 配置/模型缓存/会话持久化路径全部指向 tmp_path（不读写真实 config/ 与 data/）；
    - LLMConfig 单例在进入与退出时重置（其余单例由 test/conftest.py 全局重置）；
    - 注册 Mock 适配器（退出时从注册表移除）；
    - 用量记录重定向到临时文件（构造时会读一次真实文件，仅读不写；
      重定向后测试产生的模拟记录不会写入真实 data/llm_usage.json）；
    - 全程无真实网络访问。

    Args:
        tmp_path: pytest 提供的用例级临时目录
        monkeypatch: pytest 的 monkeypatch fixture（用例结束自动还原）

    Yields:
        Path: 隔离后的临时目录（tmp_path 原样透出）
    """
    monkeypatch.setattr(_config_mod, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(
        _config_mod, "CONFIG_FILE", tmp_path / "llm_providers.json")
    monkeypatch.setattr(
        _config_mod, "MODELS_CACHE_FILE", tmp_path / "llm_models_cache.json")
    monkeypatch.setattr(
        _plugin_service_mod, "_DEFAULT_CONVERSATION_STORAGE",
        tmp_path / "conversations.json")
    LLMConfig._instance = None
    register_adapter(MOCK_ADAPTER_KEY, MockAdapter)
    # 重定向用量记录存储到临时文件
    store = _usage_store_mod.get_usage_record_store()
    store._records_file = tmp_path / "llm_usage.json"
    store._cache = {"version": 1, "records": []}
    store._cache_dirty = False
    yield tmp_path
    # 清理：关闭可能存在的 provider 连接、移除 Mock 适配器、重置 LLMConfig 单例
    if LLMProvider._instance is not None:
        LLMProvider._instance.close()
    PROVIDER_REGISTRY.pop(MOCK_ADAPTER_KEY, None)
    LLMConfig._instance = None


# ==================== 配置样本工厂 ====================

def build_v1_sample() -> Dict[str, Any]:
    """构造 v1 配置样本（顶层无 version 键，含混合 custom_models schema）

    覆盖：provider_type 字段、混合两种历史 custom_models schema
    （模板式 support_* 布尔键 + UI 式 capabilities 列表）、
    per_1k 历史定价键、api_key 落盘编码。
    """
    return {
        "providers": {
            "glm": {
                "name": "GLM",
                "provider_type": "glm",
                "api_key": encode_secret("glm-test-key"),
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "chat_model": "glm-4",
                "embedding_model": "embedding-3",
                "enabled_chat": True,
                "enabled_embedding": True,
                "support_vision": True,
                "custom_models": [
                    {
                        "id": "legacy-bool-model",
                        "name": "Legacy Bool Model",
                        "support_chat": True,
                        "support_vision": True,
                        "support_function_calling": True,
                        "support_embedding": False,
                        "input_price_per_1k": 2,
                        "output_price_per_1k": 6,
                    },
                    {
                        "id": "ui-schema-model",
                        "capabilities": ["vision", "tools"],
                        "input_price_per_1m": 15,
                    },
                ],
            },
            "ollama": {
                "name": "Ollama",
                "provider_type": "ollama",
                "api_key": "",
                "base_url": "http://localhost:11434",
                "chat_model": "llama3.1",
                "enabled_chat": True,
                "enabled_embedding": False,
            },
        }
    }


def build_v2_sample() -> Dict[str, Any]:
    """构造 v2 配置样本（version: 2，含预设实例与自定义实例）"""
    return {
        "version": 2,
        "providers": {
            "glm": {
                "preset_id": "glm",
                "name": "GLM",
                "adapter": "glm",
                "api_key": encode_secret("glm-test-key"),
                "base_url": "",
                "chat_model": "glm-4",
                "embedding_model": "embedding-3",
                "enabled_chat": True,
                "enabled_embedding": True,
                "support_vision": True,
                "order": 0,
            },
            "custom-a1b2c3d4": {
                "preset_id": None,
                "name": "自建服务",
                "adapter": "openai-compatible",
                "api_key": "",
                "base_url": "https://llm.example.com/v1",
                "chat_model": "my-model",
                "embedding_model": "",
                "enabled_chat": True,
                "enabled_embedding": False,
                "support_vision": False,
                "order": 1,
                "custom_models": [
                    {
                        "id": "my-model",
                        "capabilities": ["tools"],
                        "input_price_per_1m": 1.5,
                        "output_price_per_1m": 3.0,
                    },
                ],
            },
        }
    }


def make_mock_provider_config(
    name: str = "Mock 实例",
    enabled_chat: bool = True,
    enabled_embedding: bool = False,
    order: int = 0,
    **extra: Any,
) -> ProviderConfig:
    """构造使用 Mock 适配器的 ProviderConfig

    Args:
        name: 实例显示名
        enabled_chat: 是否启用聊天
        enabled_embedding: 是否启用嵌入
        order: 排序权重
        **extra: 额外字段（如 custom_models），存入 ProviderConfig.extra

    Returns:
        ProviderConfig: adapter 为 mock-adapter 的实例配置
    """
    return ProviderConfig(
        name=name,
        preset_id=None,
        adapter=MOCK_ADAPTER_KEY,
        api_key="mock-key",
        base_url="http://mock.local/v1",
        chat_model=MOCK_CHAT_MODEL_ID,
        embedding_model=MOCK_EMBEDDING_MODEL_ID if enabled_embedding else "",
        enabled_chat=enabled_chat,
        enabled_embedding=enabled_embedding,
        order=order,
        **extra,
    )
