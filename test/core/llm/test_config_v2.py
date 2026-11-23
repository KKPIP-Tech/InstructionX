"""配置 schema v2 与 v1→v2 迁移测试（core/llm/config.py）

覆盖：迁移（备份、字段映射、双 schema 规范化、密钥编解码）、
读写往返、不再自动补齐、单例与变更订阅。
"""

import json

from core.llm.config import (
    CONFIG_SCHEMA_VERSION,
    EVENT_PROVIDERS_CHANGED,
    LLMConfig,
    ProviderConfig,
    get_llm_config,
)


class TestV1ToV2Migration:
    """v1 → v2 自动迁移"""

    def test_migration_fields_and_backup(self, write_config, config_file):
        """迁移后字段映射正确且生成时间戳 .bak 备份"""
        write_config({
            "providers": {
                "glm": {
                    "name": "GLM", "provider_type": "glm",
                    "api_key": "", "base_url": "",
                    "chat_model": "glm-4",
                },
                "ollama": {
                    "name": "Ollama", "provider_type": "ollama",
                    "enabled_chat": True,
                },
            }
        })
        config = LLMConfig()
        glm = config.get_provider("glm")
        assert glm is not None
        # provider_type → preset_id / adapter 同名映射，实例 id 保持旧键名
        assert glm.preset_id == "glm"
        assert glm.adapter == "glm"
        assert glm.order == 0
        assert config.get_provider("ollama").order == 1
        # 迁移后磁盘文件为 v2，且生成 .bak 备份
        with open(config_file, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["version"] == CONFIG_SCHEMA_VERSION
        backups = list(config_file.parent.glob("llm_providers.migrated-*.bak"))
        assert len(backups) == 1

    def test_migration_unifies_mixed_custom_models(
            self, write_config, v1_config_data):
        """v1 混合双 schema 的 custom_models 迁移后统一为新 schema"""
        write_config(v1_config_data())
        config = LLMConfig()
        models = config.get_provider("glm").extra["custom_models"]
        by_id = {m["id"]: m for m in models}
        legacy = by_id["legacy-bool-model"]
        # 模板式布尔键 → capabilities；per_1k → per_1m ×1000
        assert legacy["capabilities"] == ["vision", "tools"]
        assert "support_vision" not in legacy
        assert legacy["input_price_per_1m"] == 2000
        assert legacy["output_price_per_1m"] == 6000
        ui_style = by_id["ui-schema-model"]
        assert ui_style["capabilities"] == ["vision", "tools"]
        assert ui_style["input_price_per_1m"] == 15

    def test_migration_api_key_decoded(self, write_config, v1_config_data):
        """迁移路径 api_key 落盘编码不变、加载后解码为明文"""
        write_config(v1_config_data())
        config = LLMConfig()
        assert config.get_provider("glm").api_key == "glm-test-key"


class TestV2RoundTrip:
    """v2 读写往返"""

    def test_load_v2_and_field_roundtrip(self, write_config, v2_config_data):
        """v2 加载字段守恒（含 order 与自定义实例）"""
        write_config(v2_config_data())
        config = LLMConfig()
        glm = config.get_provider("glm")
        assert (glm.preset_id, glm.adapter, glm.order) == ("glm", "glm", 0)
        assert glm.api_key == "glm-test-key"
        custom = config.get_provider("custom-a1b2c3d4")
        assert custom.preset_id is None
        assert custom.adapter == "openai-compatible"
        assert custom.order == 1

    def test_save_then_reload_consistent(self, mock_config_factory):
        """save 后重置单例重新加载：字段守恒、密钥编码还原、order 持久化"""
        config = get_llm_config()
        config.add_provider(
            "mock-1", mock_config_factory(name="实例一", order=7))
        LLMConfig._instance = None
        reloaded = LLMConfig()
        cfg = reloaded.get_provider("mock-1")
        assert cfg.name == "实例一"
        assert cfg.order == 7
        assert cfg.api_key == "mock-key"
        assert cfg.adapter == "mock-adapter"

    def test_api_key_encoded_on_disk(self, config_file, mock_config_factory):
        """api_key 落盘为 b64: 编码（明文不落盘）"""
        config = get_llm_config()
        config.add_provider("mock-1", mock_config_factory())
        with open(config_file, encoding="utf-8") as f:
            saved = json.load(f)
        stored_key = saved["providers"]["mock-1"]["api_key"]
        assert stored_key.startswith("b64:")
        assert "mock-key" not in stored_key


class TestNoDefaultBackfill:
    """不再自动补齐默认 provider"""

    def test_first_run_creates_empty_v2(self, config_file):
        """配置文件不存在时创建空 providers 的 v2 文件（目录即默认值）"""
        config = LLMConfig()
        assert config.get_all_providers() == {}
        with open(config_file, encoding="utf-8") as f:
            saved = json.load(f)
        assert saved == {"version": CONFIG_SCHEMA_VERSION, "providers": {}}

    def test_removed_instance_not_revived(self, mock_config_factory):
        """删除实例后重新加载不复活"""
        config = get_llm_config()
        config.add_provider("mock-1", mock_config_factory())
        assert config.remove_provider("mock-1") is True
        LLMConfig._instance = None
        reloaded = LLMConfig()
        assert reloaded.get_provider("mock-1") is None
        # 边界：删除不存在的实例返回 False
        assert reloaded.remove_provider("not-exist") is False


class TestSingletonAndSubscription:
    """单例与变更订阅"""

    def test_singleton_identity(self):
        """多处 LLMConfig() 与 get_llm_config() 为同一实例"""
        assert LLMConfig() is LLMConfig()
        assert get_llm_config() is LLMConfig()

    def test_subscribe_notified_and_version_increments(
            self, mock_config_factory):
        """add/remove/save 触发回调（事件名与实例 id），version 单调递增"""
        config = get_llm_config()
        events = []
        config.subscribe(lambda event, name: events.append((event, name)))
        base_version = config.version
        config.add_provider("mock-1", mock_config_factory())
        assert config.version == base_version + 1
        assert events[-1] == (EVENT_PROVIDERS_CHANGED, None)
        config.remove_provider("mock-1")
        assert config.version == base_version + 2
        assert len(events) == 2

    def test_callback_exception_does_not_break_others(
            self, mock_config_factory):
        """订阅回调异常被吞并记日志，不影响主流程与其余回调"""
        config = get_llm_config()
        received = []

        def bad_callback(event, name):
            raise RuntimeError("回调故障")

        config.subscribe(bad_callback)
        config.subscribe(lambda event, name: received.append(name))
        config.add_provider("mock-1", mock_config_factory())  # 不抛异常
        assert len(received) == 1
        assert config.get_provider("mock-1") is not None

    def test_unsubscribe_stops_notification(self, mock_config_factory):
        """退订后不再收到通知"""
        config = get_llm_config()
        received = []
        callback = lambda event, name: received.append(name)  # noqa: E731
        config.subscribe(callback)
        config.unsubscribe(callback)
        config.add_provider("mock-1", mock_config_factory())
        assert received == []


class TestProviderConfigDict:
    """ProviderConfig 序列化"""

    def test_to_dict_from_dict_roundtrip(self):
        """to_dict / from_dict 字段守恒（v2 字段集 + extra）"""
        cfg = ProviderConfig(
            name="测试", preset_id="glm", adapter="glm",
            api_key="k", base_url="https://x", chat_model="m",
            enabled_chat=False, enabled_embedding=True, order=3,
            timeout=30,
        )
        restored = ProviderConfig.from_dict(cfg.to_dict())
        assert restored.preset_id == "glm"
        assert restored.adapter == "glm"
        assert restored.order == 3
        assert restored.enabled_chat is False
        assert restored.enabled_embedding is True
        assert restored.extra["timeout"] == 30

    def test_from_dict_drops_legacy_provider_type(self):
        """from_dict 静默丢弃 v1 残留的 provider_type 键（不落入 extra）"""
        cfg = ProviderConfig.from_dict({
            "name": "旧实例", "provider_type": "glm", "adapter": "glm"})
        assert "provider_type" not in cfg.extra
