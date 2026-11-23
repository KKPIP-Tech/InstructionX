"""预设目录测试（core/llm/catalog/）

覆盖：目录完整性（适配器注册、Logo 文件、端点拼接）、兜底适配器、
目录数据不可变约束、预设模型目录一致性。
"""

from dataclasses import FrozenInstanceError

import pytest

from core.llm.catalog import (
    CUSTOM_ADAPTER,
    PRESET_MODELS,
    PROVIDER_PRESETS,
    get_preset_logo_path,
    get_provider_preset,
)
from core.llm.model_schema import ALL_CAPABILITIES
from core.llm.providers import (
    OpenAICompatibleProvider, OpenAIProvider, get_adapter_class,
)

# 内置预设数量（openai / siliconflow / glm / minimax / ollama）
EXPECTED_PRESET_COUNT = 5


class TestProviderPresets:
    """提供商预设目录数据"""

    def test_preset_table_complete(self):
        """目录包含 5 家内置预设，键与 preset_id 一致"""
        assert len(PROVIDER_PRESETS) == EXPECTED_PRESET_COUNT
        assert set(PROVIDER_PRESETS) == {
            "openai", "siliconflow", "glm", "minimax", "ollama"}
        for key, preset in PROVIDER_PRESETS.items():
            assert key == preset.preset_id
            assert preset.display_name

    def test_every_preset_adapter_registered(self):
        """每个预设的 adapter 均已在适配器注册表中注册"""
        for preset in PROVIDER_PRESETS.values():
            assert get_adapter_class(preset.adapter) is not None, (
                f"预设 {preset.preset_id} 的适配器 {preset.adapter} 未注册")

    def test_every_preset_logo_exists(self):
        """每个预设的 Logo 文件存在于 catalog/logos/ 并可解析"""
        for preset in PROVIDER_PRESETS.values():
            assert preset.logo_filename
            path = get_preset_logo_path(preset.preset_id)
            assert path is not None, f"预设 {preset.preset_id} 的 Logo 缺失"

    def test_endpoint_concatenation_legal(self):
        """default_base_url 与 chat_endpoint_path 拼接为合法 http(s) 地址"""
        for preset in PROVIDER_PRESETS.values():
            assert preset.default_base_url.startswith("http")
            url = preset.default_base_url + preset.chat_endpoint_path
            assert url.startswith(("http://", "https://"))
            assert " " not in url

    def test_preset_is_frozen(self):
        """目录数据为 frozen dataclass，不允许运行时修改"""
        preset = get_provider_preset("glm")
        assert preset is not None
        with pytest.raises(FrozenInstanceError):
            preset.display_name = "篡改"  # type: ignore[misc]

    def test_get_provider_preset_unknown_returns_none(self):
        """查询不存在的预设返回 None（边界）"""
        assert get_provider_preset("no-such-preset") is None
        assert get_preset_logo_path("no-such-preset") is None


class TestCustomAdapter:
    """自定义 OpenAI 兼容兜底适配器"""

    def test_custom_adapter_registered(self):
        """CUSTOM_ADAPTER 为 openai-compatible 且已注册"""
        assert CUSTOM_ADAPTER == "openai-compatible"
        assert get_adapter_class(CUSTOM_ADAPTER) is OpenAICompatibleProvider

    def test_custom_adapter_reuses_openai_protocol(self):
        """兜底适配器复用 OpenAIProvider 协议实现（子类关系）"""
        assert issubclass(OpenAICompatibleProvider, OpenAIProvider)
        assert OpenAICompatibleProvider.provider_type == CUSTOM_ADAPTER


class TestPresetModels:
    """预设模型目录"""

    def test_preset_models_keys_subset_of_presets(self):
        """PRESET_MODELS 的键均为已注册预设（当前收录 glm / minimax）"""
        assert set(PRESET_MODELS) <= set(PROVIDER_PRESETS)
        assert set(PRESET_MODELS) == {"glm", "minimax"}

    def test_preset_model_entries_normalized(self):
        """预设模型条目均为统一 schema（capabilities 合法、键齐备）"""
        legal = set(ALL_CAPABILITIES)
        for preset_id, entries in PRESET_MODELS.items():
            assert entries, f"预设 {preset_id} 应有模型条目"
            for entry in entries:
                assert entry["id"]
                assert set(entry["capabilities"]) <= legal
                assert "support_streaming" in entry
                assert "input_price_per_1m" in entry
