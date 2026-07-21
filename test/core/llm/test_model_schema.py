"""统一模型 schema 测试（core/llm/model_schema.py）

覆盖：历史双 schema 规范化、定价键迁移、能力闭集过滤、互斥规则、
分组推断、三路合并。
"""

from core.llm.model_schema import (
    ALL_CAPABILITIES,
    CAPABILITY_EMBEDDING,
    CAPABILITY_RERANK,
    CAPABILITY_TOOLS,
    CAPABILITY_VISION,
    GROUP_OTHER,
    GROUP_UNGROUPED,
    MUTUALLY_EXCLUSIVE_CAPABILITY_GROUPS,
    get_disabled_capabilities,
    infer_model_group,
    merge_model_entries,
    models_to_groups,
    normalize_model_entry,
)


class TestNormalizeLegacyBoolSchema:
    """模板式（support_* 布尔键）schema 转换"""

    def test_bool_keys_mapped_to_capabilities(self):
        """模板式布尔键转换为 capabilities（vision/function_calling/embedding）"""
        entry = normalize_model_entry({
            "id": "m1",
            "support_chat": True,
            "support_vision": True,
            "support_function_calling": True,
            "support_embedding": True,
            "context_length": 8192,
        })
        assert entry["capabilities"] == [
            CAPABILITY_VISION, CAPABILITY_TOOLS, CAPABILITY_EMBEDDING]
        # support_chat 不映射为能力，且全部历史布尔键被删除
        for key in ("support_chat", "support_vision",
                    "support_function_calling", "support_embedding"):
            assert key not in entry
        assert entry["context_length"] == 8192

    def test_ui_schema_passthrough_and_defaults(self):
        """UI 式（capabilities 列表）透传并补全缺失键默认值"""
        entry = normalize_model_entry({"id": "m2", "capabilities": ["vision"]})
        assert entry["capabilities"] == [CAPABILITY_VISION]
        assert entry["name"] == "m2"
        assert entry["group"] == ""
        assert entry["context_length"] is None
        assert entry["support_streaming"] is True
        assert entry["currency"] == "$"
        assert entry["input_price_per_1m"] is None
        assert entry["output_price_per_1m"] is None

    def test_invalid_capabilities_filtered_and_unknown_keys_kept(self):
        """非法 capabilities 值过滤、非列表按空处理；未知额外键保留"""
        entry = normalize_model_entry({
            "id": "m3",
            "capabilities": ["vision", "not-a-cap", "tools"],
            "description": "额外描述",
        })
        assert entry["capabilities"] == [CAPABILITY_VISION, CAPABILITY_TOOLS]
        assert entry["description"] == "额外描述"
        entry2 = normalize_model_entry({"id": "m4", "capabilities": "vision"})
        assert entry2["capabilities"] == []


class TestPriceKeyMigration:
    """历史 per_1k 定价键迁移"""

    def test_per_1k_migrated_to_per_1m_times_1000(self):
        """per_1k 键迁移为 per_1m 键（×1000）并删除旧键"""
        entry = normalize_model_entry({
            "id": "m5",
            "input_price_per_1k": 2,
            "output_price_per_1k": 0.5,
        })
        assert entry["input_price_per_1m"] == 2000
        assert entry["output_price_per_1m"] == 500
        assert "input_price_per_1k" not in entry
        assert "output_price_per_1k" not in entry

    def test_per_1m_wins_when_both_present(self):
        """per_1k 与 per_1m 并存时以 per_1m 为准并删除 per_1k"""
        entry = normalize_model_entry({
            "id": "m6",
            "input_price_per_1k": 2,
            "input_price_per_1m": 1500,
        })
        assert entry["input_price_per_1m"] == 1500
        assert "input_price_per_1k" not in entry


class TestCapabilityExclusion:
    """能力互斥规则"""

    def test_mutually_exclusive_groups_constant(self):
        """互斥规则常量：embedding 与 rerank 同属一个互斥组"""
        assert len(MUTUALLY_EXCLUSIVE_CAPABILITY_GROUPS) == 1
        assert MUTUALLY_EXCLUSIVE_CAPABILITY_GROUPS[0] == frozenset(
            {CAPABILITY_EMBEDDING, CAPABILITY_RERANK})

    def test_embedding_selected_disables_all_others(self):
        """选中 embedding 时除自身外全部能力禁用"""
        disabled = get_disabled_capabilities([CAPABILITY_EMBEDDING])
        assert CAPABILITY_EMBEDDING not in disabled
        assert set(disabled) == set(ALL_CAPABILITIES) - {CAPABILITY_EMBEDDING}

    def test_chat_capability_selected_disables_nothing(self):
        """选中非互斥能力（vision）时不禁用任何能力"""
        assert get_disabled_capabilities([CAPABILITY_VISION]) == []


class TestGroupInference:
    """模型分组推断与聚合"""

    def test_keyword_hit(self):
        """关键字命中返回对应系列分组名"""
        assert infer_model_group("glm-4-flash") == "GLM"
        assert infer_model_group("Pro/deepseek-ai/DeepSeek-V3") == "deepseek-ai"

    def test_path_fallback_and_other(self):
        """未命中关键字时取路径首段；无路径时归「其他」"""
        assert infer_model_group("Pro/some-model") == "Pro"
        assert infer_model_group("some-unknown-model") == GROUP_OTHER

    def test_models_to_groups_ungrouped(self):
        """空组名条目归入「未分组」，其余按原组聚合"""
        groups = models_to_groups([
            {"id": "a", "group": ""},
            {"id": "b", "group": "对话模型"},
            {"id": "c"},
        ])
        assert [m["id"] for m in groups[GROUP_UNGROUPED]] == ["a", "c"]
        assert [m["id"] for m in groups["对话模型"]] == ["b"]


class TestMergeModelEntries:
    """三路合并（目录预设 + API 拉取 + 用户覆写）"""

    def test_merge_priority_and_order(self):
        """同 id 后者覆盖（用户覆写优先），顺序为首次出现顺序"""
        merged = merge_model_entries(
            preset_models=[{"id": "a", "name": "预设A"}, {"id": "b"}],
            fetched_models=[{"id": "b", "name": "拉取B"}, {"id": "c"}],
            custom_models=[{"id": "a", "name": "用户A"}, {"id": "d"}],
        )
        ids = [m["id"] for m in merged]
        assert ids == ["a", "b", "c", "d"]
        by_id = {m["id"]: m for m in merged}
        assert by_id["a"]["name"] == "用户A"   # custom 最高优先
        assert by_id["b"]["name"] == "拉取B"   # fetched 覆盖 preset

    def test_merge_normalizes_and_skips_missing_id(self):
        """合并过程逐项规范化；缺少 id 的条目跳过"""
        merged = merge_model_entries(
            preset_models=[{"id": "a", "support_vision": True}],
            fetched_models=None,
            custom_models=[{"name": "无 id 条目"}],
        )
        assert len(merged) == 1
        assert merged[0]["capabilities"] == [CAPABILITY_VISION]
