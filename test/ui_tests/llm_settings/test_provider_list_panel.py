"""Provider 列表面板测试（ui/dialog/llm_settings/provider_list_panel.py）

覆盖：列表渲染与 order 排序、搜索联动（实例名/预设名/模型名）、
启停开关落盘、选中与添加信号。
"""

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt

from core.llm.config import get_llm_config
from ui.dialog.llm_settings.provider_list_panel import ProviderListPanel


def _setup_two_instances(mock_config_factory):
    """写入两个 mock 实例（order 逆序于添加顺序，验证按 order 渲染）"""
    config = get_llm_config()
    config.add_provider("inst-b", mock_config_factory(name="贝塔服务", order=1))
    config.add_provider("inst-a", mock_config_factory(name="阿尔法服务", order=0))
    return config


class TestListRendering:
    """列表渲染与排序"""

    def test_rows_sorted_by_order(self, qtbot, mock_config_factory):
        """实例按配置 order 升序渲染"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        assert panel.list.count() == 2
        first_id = panel.list.item(0).data(Qt.ItemDataRole.UserRole)
        second_id = panel.list.item(1).data(Qt.ItemDataRole.UserRole)
        assert (first_id, second_id) == ("inst-a", "inst-b")
        assert panel.current_provider_id() == "inst-a"

    def test_empty_list_placeholder_state(self, qtbot):
        """无实例时列表为空且无选中（边界）"""
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        assert panel.list.count() == 0
        assert panel.current_provider_id() is None


class TestSearchFilter:
    """搜索联动过滤"""

    def test_search_by_instance_name(self, qtbot, mock_config_factory):
        """按实例名搜索：未命中项隐藏"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        panel.search_edit.setText("阿尔法")
        rows = {pid: row[0].isHidden() for pid, row in panel._rows.items()}
        assert rows["inst-a"] is False
        assert rows["inst-b"] is True

    def test_search_by_model_name(self, qtbot, mock_config_factory):
        """搜索命中实例下模型 id/name（custom_models）"""
        config = get_llm_config()
        config.add_provider("inst-a", mock_config_factory(
            name="普通服务", order=0))
        config.add_provider("inst-b", mock_config_factory(
            name="另一个服务", order=1,
            custom_models=[{"id": "special-vision-x9"}]))
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        panel.search_edit.setText("special-vision-x9")
        rows = {pid: row[0].isHidden() for pid, row in panel._rows.items()}
        assert rows["inst-b"] is False
        assert rows["inst-a"] is True

    def test_search_by_preset_display_name(self, qtbot, mock_config_factory):
        """搜索命中预设显示名（实例关联 glm 预设）"""
        config = get_llm_config()
        cfg = mock_config_factory(name="我的实例", order=0)
        cfg.preset_id = "glm"
        config.add_provider("inst-a", cfg)
        config.add_provider("inst-b", mock_config_factory(name="无关服务", order=1))
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        panel.search_edit.setText("glm")
        rows = {pid: row[0].isHidden() for pid, row in panel._rows.items()}
        assert rows["inst-a"] is False
        assert rows["inst-b"] is True

    def test_clear_search_restores(self, qtbot, mock_config_factory):
        """清空搜索词后全部恢复可见"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        panel.search_edit.setText("阿尔法")
        panel.search_edit.setText("")
        assert all(not row[0].isHidden() for row in panel._rows.values())


class TestToggleAndSignals:
    """启停开关与信号"""

    def test_toggle_persists_enabled_chat(self, qtbot, mock_config_factory):
        """列表项开关切换写 enabled_chat 落盘并发射 sig_toggle"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        emissions = []
        panel.sig_toggle.connect(lambda pid, on: emissions.append((pid, on)))
        widget = panel._rows["inst-a"][1]
        widget.toggled.emit("inst-a", False)
        assert emissions == [("inst-a", False)]
        assert get_llm_config().get_provider("inst-a").enabled_chat is False

    def test_select_emits_sig_select(self, qtbot, mock_config_factory):
        """选中变化发射 sig_select（实例 id）"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        emissions = []
        panel.sig_select.connect(emissions.append)
        panel._select("inst-b")
        assert emissions == ["inst-b"]
        assert panel.current_provider_id() == "inst-b"

    def test_add_button_emits_sig_add(self, qtbot, mock_config_factory):
        """「＋ 添加提供商」按钮发射 sig_add"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        emissions = []
        panel.sig_add.connect(lambda: emissions.append(True))
        panel.add_btn.click()
        assert emissions == [True]

    def test_config_change_triggers_reload(self, qtbot, mock_config_factory):
        """外部配置变更（订阅驱动）触发列表重建"""
        _setup_two_instances(mock_config_factory)
        panel = ProviderListPanel()
        qtbot.addWidget(panel)
        get_llm_config().add_provider(
            "inst-c", mock_config_factory(name="伽马服务", order=2))
        assert panel.list.count() == 3
