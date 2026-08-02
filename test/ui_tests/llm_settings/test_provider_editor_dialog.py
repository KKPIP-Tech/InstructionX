"""Provider 编辑器对话框测试（ui/dialog/llm_settings/provider_editor_dialog.py）

覆盖：预设创建（字段预填目录默认值）、自定义创建（openai-compatible）、
实例 id 生成规则、MODE_EDIT 编辑、表单校验。
"""

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt

from core.llm.catalog import CUSTOM_ADAPTER, get_provider_preset
from core.llm.config import get_llm_config
from ui.dialog.llm_settings.provider_editor_dialog import (
    MODE_CREATE,
    MODE_EDIT,
    ProviderEditorDialog,
    generate_instance_id,
)


def _choose_type(dialog: ProviderEditorDialog, preset_id):
    """在「选择类型」页点选指定预设（None 表示自定义项）"""
    for index in range(dialog._type_list.count()):
        item = dialog._type_list.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == preset_id:
            dialog._type_list.itemClicked.emit(item)
            return
    raise AssertionError(f"类型项不存在: {preset_id}")


class TestGenerateInstanceId:
    """实例 id 生成规则"""

    def test_first_preset_instance_uses_preset_id(self):
        """预设尚无实例时直接使用 preset_id（向后兼容）"""
        assert generate_instance_id("glm", set()) == "glm"
        assert generate_instance_id("glm", {"ollama"}) == "glm"

    def test_conflict_generates_short_code(self):
        """preset_id 已被占用时生成带短码后缀的 id"""
        instance_id = generate_instance_id("glm", {"glm"})
        assert instance_id.startswith("glm-")
        assert len(instance_id) == len("glm-") + 8

    def test_custom_prefix(self):
        """自定义实例使用 custom 前缀"""
        instance_id = generate_instance_id(None, set())
        assert instance_id.startswith("custom-")


class TestCreateFromPreset:
    """MODE_CREATE：从预设创建"""

    def test_prefill_and_create(self, qtbot):
        """选择预设后字段预填目录默认值，确认后配置落盘"""
        dialog = ProviderEditorDialog(MODE_CREATE)
        qtbot.addWidget(dialog)
        _choose_type(dialog, "glm")
        preset = get_provider_preset("glm")
        assert dialog.name_edit.text() == preset.display_name
        assert dialog.base_url_edit.text() == preset.default_base_url
        dialog.api_key_edit.setText("test-key")
        dialog._on_confirm()
        assert dialog.created_instance_id == "glm"
        cfg = get_llm_config().get_provider("glm")
        assert cfg is not None
        assert cfg.preset_id == "glm"
        assert cfg.adapter == "glm"
        assert cfg.api_key == "test-key"
        assert cfg.base_url == preset.default_base_url

    def test_second_instance_gets_short_code(self, qtbot, mock_config_factory):
        """同预设第二实例：实例 id 为短码形式"""
        get_llm_config().add_provider("glm", mock_config_factory(name="已有GLM"))
        dialog = ProviderEditorDialog(MODE_CREATE)
        qtbot.addWidget(dialog)
        _choose_type(dialog, "glm")
        dialog._on_confirm()
        assert dialog.created_instance_id.startswith("glm-")
        assert get_llm_config().get_provider(
            dialog.created_instance_id) is not None


class TestCreateCustom:
    """MODE_CREATE：自定义 OpenAI 兼容服务"""

    def test_create_custom_instance(self, qtbot):
        """自定义创建：adapter 为 openai-compatible，preset_id 为 None"""
        dialog = ProviderEditorDialog(MODE_CREATE)
        qtbot.addWidget(dialog)
        _choose_type(dialog, None)
        assert dialog.base_url_edit.text() == ""
        dialog.name_edit.setText("我的网关")
        dialog.base_url_edit.setText("https://gw.example.com/v1")
        dialog._on_confirm()
        cfg = get_llm_config().get_provider(dialog.created_instance_id)
        assert cfg.preset_id is None
        assert cfg.adapter == CUSTOM_ADAPTER
        assert cfg.name == "我的网关"
        assert cfg.base_url == "https://gw.example.com/v1"

    def test_custom_requires_base_url(self, qtbot, block_message_boxes):
        """自定义实例缺 Base URL：校验失败弹中文警告且不落盘（异常路径）"""
        dialog = ProviderEditorDialog(MODE_CREATE)
        qtbot.addWidget(dialog)
        _choose_type(dialog, None)
        dialog._on_confirm()
        assert dialog.created_instance_id is None
        assert block_message_boxes["warning"]
        assert any("Base URL" in str(arg)
                   for call in block_message_boxes["warning"] for arg in call)
        assert get_llm_config().get_all_providers() == {}

    def test_empty_name_rejected(self, qtbot, block_message_boxes):
        """名称为空：校验失败（异常路径）"""
        dialog = ProviderEditorDialog(MODE_CREATE)
        qtbot.addWidget(dialog)
        _choose_type(dialog, "glm")
        dialog.name_edit.setText("   ")
        dialog._on_confirm()
        assert dialog.created_instance_id is None
        assert block_message_boxes["warning"]
        assert any("实例名称" in str(arg)
                   for call in block_message_boxes["warning"] for arg in call)


class TestEditMode:
    """MODE_EDIT：编辑既有实例"""

    def test_edit_updates_fields_and_keeps_key(self, qtbot, mock_config_factory):
        """编辑名称/地址；API Key 留空不修改"""
        config = get_llm_config()
        config.add_provider("mock-1", mock_config_factory(name="旧名称"))
        dialog = ProviderEditorDialog(MODE_EDIT, instance_id="mock-1")
        qtbot.addWidget(dialog)
        assert dialog.name_edit.text() == "旧名称"
        dialog.name_edit.setText("新名称")
        dialog.base_url_edit.setText("https://new.example.com/v1")
        dialog._on_confirm()
        cfg = config.get_provider("mock-1")
        assert cfg.name == "新名称"
        assert cfg.base_url == "https://new.example.com/v1"
        assert cfg.api_key == "mock-key"  # 留空未修改
        assert dialog.created_instance_id == "mock-1"

    def test_edit_missing_instance_warns(self, qtbot, block_message_boxes):
        """编辑不存在的实例：中文警告且不接受（异常路径）"""
        dialog = ProviderEditorDialog(MODE_EDIT, instance_id="not-exist")
        qtbot.addWidget(dialog)
        dialog.name_edit.setText("任意")
        dialog._on_confirm()
        assert dialog.created_instance_id is None
        assert block_message_boxes["warning"]
        assert any("实例不存在" in str(arg)
                   for call in block_message_boxes["warning"] for arg in call)
