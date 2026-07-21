"""模型编辑对话框测试（ui/dialog/llm_settings/model_edit_dialog.py）

覆盖：新建/编辑模式、能力标签互斥、context_length 与定价往返、
分组自动推断、统一 schema 输出、ID 校验。
"""

import pytest

pytest.importorskip("pytestqt")

from core.llm.model_schema import ALL_CAPABILITIES, CAPABILITY_LABELS
from ui.dialog.llm_settings.model_edit_dialog import ModelEditDialog


def _tag(dialog: ModelEditDialog, capability: str):
    """按能力键取能力标签按钮"""
    for tag in dialog._capability_tags:
        if tag.capability_key == capability:
            return tag
    raise AssertionError(f"能力标签不存在: {capability}")


class TestCreateMode:
    """新建模式"""

    def test_output_normalized_schema(self, qtbot):
        """新建：get_model_data 输出统一 schema（缺省键补全）"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        dialog._id_edit.setText("my-model")
        dialog._context_spin.setValue(131072)
        _tag(dialog, "tools").setChecked(True)
        data = dialog.get_model_data()
        assert data["id"] == "my-model"
        assert data["name"] == "my-model"  # 名称留空回退 id
        assert data["capabilities"] == ["tools"]
        assert data["context_length"] == 131072
        assert data["support_streaming"] is True
        assert data["currency"] == "$"
        assert set(data) >= {
            "id", "name", "group", "capabilities", "context_length",
            "support_streaming", "currency",
            "input_price_per_1m", "output_price_per_1m",
        }

    def test_group_inferred_when_blank(self, qtbot):
        """分组留空时按模型 ID 自动推断"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        dialog._id_edit.setText("glm-4-flash")
        assert dialog.get_model_data()["group"] == "GLM"

    def test_empty_id_rejected(self, qtbot, block_message_boxes):
        """模型 ID 为空：校验失败弹中文警告且不接受（异常路径）"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        dialog._on_confirm()
        assert block_message_boxes["warning"]
        assert dialog.result() == 0  # 未接受


class TestCapabilityExclusion:
    """能力标签互斥"""

    def test_embedding_disables_others(self, qtbot):
        """勾选 embedding 后除自身外全部能力禁用，取消后恢复"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        _tag(dialog, "embedding").setChecked(True)
        for capability in ALL_CAPABILITIES:
            tag = _tag(dialog, capability)
            assert tag.isEnabled() == (capability == "embedding")
        # 取消勾选恢复全部可用
        _tag(dialog, "embedding").setChecked(False)
        assert all(_tag(dialog, cap).isEnabled() for cap in ALL_CAPABILITIES)

    def test_rerank_mutually_exclusive_with_embedding(self, qtbot):
        """embedding 与 rerank 彼此互斥"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        _tag(dialog, "rerank").setChecked(True)
        assert not _tag(dialog, "embedding").isEnabled()
        assert _tag(dialog, "rerank").isEnabled()

    def test_capability_labels_cover_closed_set(self, qtbot):
        """能力标签按闭集顺序构建且均有中文标签"""
        dialog = ModelEditDialog()
        qtbot.addWidget(dialog)
        keys = [t.capability_key for t in dialog._capability_tags]
        assert keys == list(ALL_CAPABILITIES)
        assert all(t.text() == CAPABILITY_LABELS[k]
                   for t, k in zip(dialog._capability_tags, keys))


class TestEditModeRoundTrip:
    """编辑模式字段往返"""

    def _existing_entry(self):
        return {
            "id": "existing-model",
            "name": "既有模型",
            "group": "对话模型",
            "capabilities": ["vision", "tools"],
            "context_length": 65536,
            "support_streaming": False,
            "currency": "¥",
            "input_price_per_1m": 1.25,
            "output_price_per_1m": 2.5,
        }

    def test_fields_loaded_and_roundtrip(self, qtbot):
        """编辑模式回填全部字段；不改动直接输出数据守恒"""
        entry = self._existing_entry()
        dialog = ModelEditDialog(model_data=entry)
        qtbot.addWidget(dialog)
        assert dialog._id_edit.text() == "existing-model"
        assert dialog._id_edit.isReadOnly()  # 编辑模式 ID 不可改
        assert dialog._name_edit.text() == "既有模型"
        assert dialog._group_edit.text() == "对话模型"
        assert dialog._context_spin.value() == 65536
        assert dialog._streaming_switch.isChecked() is False
        data = dialog.get_model_data()
        assert data["capabilities"] == ["vision", "tools"]
        assert data["context_length"] == 65536  # 往返不丢
        assert data["currency"] == "¥"
        assert data["input_price_per_1m"] == 1.25
        assert data["output_price_per_1m"] == 2.5
        assert data["support_streaming"] is False

    def test_zero_means_unset(self, qtbot):
        """context_length / 定价为 0 时输出 None（未设置语义）"""
        dialog = ModelEditDialog(model_data=self._existing_entry())
        qtbot.addWidget(dialog)
        dialog._context_spin.setValue(0)
        dialog._input_price_spin.setValue(0.0)
        data = dialog.get_model_data()
        assert data["context_length"] is None
        assert data["input_price_per_1m"] is None
        assert data["output_price_per_1m"] == 2.5
