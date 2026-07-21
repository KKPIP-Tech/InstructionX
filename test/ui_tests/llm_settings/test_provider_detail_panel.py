"""Provider 详情面板测试（ui/dialog/llm_settings/provider_detail_panel.py）

覆盖：自动保存语义（密钥/地址编辑即时落盘）、总开关与停用遮罩、
地址重置回退目录默认、连接检测（成功自动启用 / 失败错误展示）。
"""

import pytest

pytest.importorskip("pytestqt")

from core.llm.catalog import get_provider_preset
from core.llm.config import get_llm_config
from ui.dialog.llm_settings.provider_detail_panel import ProviderDetailPanel

# 连接检测 Worker 等待超时（毫秒）
CHECK_WAIT_TIMEOUT_MS = 5000


def _make_panel(qtbot, mock_config_factory, enabled=True):
    """构造面板并加载一个 mock 实例"""
    config = get_llm_config()
    config.add_provider("mock-1", mock_config_factory(
        name="测试实例", enabled_chat=enabled))
    panel = ProviderDetailPanel()
    qtbot.addWidget(panel)
    panel.load_instance("mock-1")
    return panel, config


class TestAutoSave:
    """自动保存语义（无保存按钮，编辑即时落盘）"""

    def test_api_key_saved_on_editing_finished(self, qtbot, mock_config_factory):
        """密钥编辑完成即落盘"""
        panel, config = _make_panel(qtbot, mock_config_factory)
        panel._key_edit.setText("brand-new-key")
        panel._key_edit.editingFinished.emit()
        assert config.get_provider("mock-1").api_key == "brand-new-key"

    def test_base_url_saved_on_editing_finished(self, qtbot, mock_config_factory):
        """地址编辑完成即落盘（去首尾空白）"""
        panel, config = _make_panel(qtbot, mock_config_factory)
        panel._host_edit.setText("  https://other.example.com/v1  ")
        panel._host_edit.editingFinished.emit()
        assert config.get_provider("mock-1").base_url == (
            "https://other.example.com/v1")

    def test_master_switch_persists_and_overlay(self, qtbot, mock_config_factory):
        """总开关切换写 enabled_chat 落盘，停用时主体覆盖遮罩"""
        panel, config = _make_panel(qtbot, mock_config_factory)
        assert panel._overlay.isHidden()
        panel._master_switch.setChecked(False)
        assert config.get_provider("mock-1").enabled_chat is False
        assert not panel._overlay.isHidden()
        assert not panel._body.isEnabled()
        # 重新开启恢复
        panel._master_switch.setChecked(True)
        assert config.get_provider("mock-1").enabled_chat is True
        assert panel._overlay.isHidden()

    def test_load_disabled_instance_shows_overlay(self, qtbot, mock_config_factory):
        """加载已停用实例：总开关关态 + 遮罩可见"""
        panel, _ = _make_panel(qtbot, mock_config_factory, enabled=False)
        assert panel._master_switch.isChecked() is False
        assert not panel._overlay.isHidden()


class TestBaseUrlReset:
    """地址重置与目录默认"""

    def test_reset_clears_override(self, qtbot, mock_config_factory):
        """「重置」清空实例覆写并显示目录默认地址（占位符/文本）"""
        config = get_llm_config()
        cfg = mock_config_factory(name="GLM 实例")
        cfg.preset_id = "glm"
        config.add_provider("mock-1", cfg)
        panel = ProviderDetailPanel()
        qtbot.addWidget(panel)
        panel.load_instance("mock-1")
        panel._host_edit.setText("https://custom.example.com/v1")
        panel._host_edit.editingFinished.emit()
        panel._reset_btn.click()
        saved = config.get_provider("mock-1")
        assert saved.base_url == ""  # 覆写清空，运行时回退目录默认
        assert panel._host_edit.text() == get_provider_preset("glm").default_base_url


class TestConnectionCheck:
    """连接检测（ConnectionCheckWorker 后台线程）"""

    def test_check_success_shows_count(self, qtbot, mock_config_factory):
        """检测成功：状态显示「连接正常 · N 个模型」（Worker 全链路）"""
        panel, config = _make_panel(qtbot, mock_config_factory, enabled=True)
        panel._check_btn.click()
        qtbot.waitUntil(
            lambda: "连接正常" in panel._check_status.text(),
            timeout=CHECK_WAIT_TIMEOUT_MS)
        assert "2 个模型" in panel._check_status.text()
        panel.shutdown_workers()

    def test_check_success_auto_enables_disabled_instance(
            self, qtbot, mock_config_factory):
        """检测成功且实例未启用时自动开启 enabled_chat（完成槽逻辑）"""
        panel, config = _make_panel(qtbot, mock_config_factory, enabled=False)
        assert config.get_provider("mock-1").enabled_chat is False
        # 实例停用时主体禁用（检测按钮不可点），直接驱动完成槽验证联动逻辑
        panel._on_check_finished("mock-1", True, None, 2)
        assert "连接正常" in panel._check_status.text()
        assert config.get_provider("mock-1").enabled_chat is True
        assert panel._master_switch.isChecked() is True

    def test_check_failure_shows_error(
            self, qtbot, mock_config_factory, monkeypatch):
        """检测失败：状态显示错误详情（异常路径）

        检测前落盘会触发配置版本递增，Worker 线程内惰性刷新会重建适配器
        实例，因此故障注入须作用于类级（重建后仍然生效）。
        """
        from llm_v2_helpers import MockAdapter

        def failing_refresh(self, force: bool = False):
            raise ConnectionError("模拟连接失败")

        monkeypatch.setattr(MockAdapter, "refresh_models", failing_refresh)
        panel, config = _make_panel(qtbot, mock_config_factory, enabled=True)
        panel._check_btn.click()
        qtbot.waitUntil(
            lambda: "连接失败" in panel._check_status.text(),
            timeout=CHECK_WAIT_TIMEOUT_MS)
        assert "模拟连接失败" in panel._check_status.text()
        panel.shutdown_workers()

    def test_late_signal_from_other_instance_ignored(
            self, qtbot, mock_config_factory):
        """迟到信号（非当前实例）被忽略（边界）"""
        panel, config = _make_panel(qtbot, mock_config_factory, enabled=True)
        panel._on_check_finished("other-instance", True, None, 9)
        assert panel._check_status.text() == ""


class TestLoadInstance:
    """实例加载与空态"""

    def test_header_populated(self, qtbot, mock_config_factory):
        """加载实例后头部名称与总开关状态正确"""
        panel, _ = _make_panel(qtbot, mock_config_factory)
        assert panel._name_label.text() == "测试实例"
        assert panel._master_switch.isChecked() is True

    def test_load_none_shows_empty_state(self, qtbot, mock_config_factory):
        """加载 None：空态容错不崩（边界）"""
        panel, _ = _make_panel(qtbot, mock_config_factory)
        panel.load_instance(None)
        assert panel._name_label.text() == ""
        assert not panel._master_switch.isEnabled()
