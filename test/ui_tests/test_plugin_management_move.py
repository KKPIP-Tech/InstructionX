# -*- coding: utf-8 -*-
"""插件管理对话框「移动分类」按钮 UI 测试

测试目标: 详情面板的「移至官方插件 / 移至第三方插件」按钮与本地安装的目标范围接线
测试范围:

- 按钮文案随当前 Tab 变化（官方 Tab → 移至第三方插件；第三方 Tab → 移至官方插件）
- 点击按钮后按「另一侧」范围移动插件目录，并刷新两个 Tab 的列表
- 未选择插件时给出提示且不移动任何文件
- 「安装本地插件包」把当前 Tab 的范围作为 target_scope 传给本地安装对话框

约定：使用隔离的 PluginManager（目录全部指向 tmp_path）与最小假插件，
模态提示（确认框 / 结果提示）在用例内替换为直接返回，避免测试阻塞。
"""

import json
from pathlib import Path

import pytest

pytest.importorskip("pytestqt")

from core.plugin.config_manager import PluginConfigManager
from core.plugin.manager import (
    SCOPE_OFFICIAL, SCOPE_THIRDPARTY, PluginManager,
)
from core.plugin.plugin_groups import PluginGroupStore
from core.plugin.plugin_registry import PluginRegistry
from ui.dialog import plugin_management_dialog as pmd_module
from ui.dialog.plugin_management_dialog import PluginManagementDialog

FAKE_ENTRANCE = '''"""fake plugin"""
from core.interfaces import IPlugin


class FakePlugin(IPlugin):
    @property
    def plugin_name(self):
        return "{name}"

    def _create_widget(self, parent=None, data_provider=None):
        return None
'''

OFFICIAL_TAB_INDEX = 0
THIRDPARTY_TAB_INDEX = 1


@pytest.fixture
def isolated_pm(tmp_path, monkeypatch):
    """构建目录全部指向 tmp_path 的隔离 PluginManager，并加载一个官方插件"""
    monkeypatch.setattr(PluginManager, "_instance", None)
    monkeypatch.setattr(PluginManager, "_initialized", False)
    pm = PluginManager()
    pm.official_plugin_dir = tmp_path / "plugin"
    pm.thirdparty_plugin_dir = tmp_path / "custom_plugin"
    pm.config_manager = PluginConfigManager(tmp_path / "config")
    pm.registry = PluginRegistry(tmp_path / "config")
    pm.group_store = PluginGroupStore(tmp_path / "config")
    _make_plugin(pm.official_plugin_dir, "demo-move")
    pm.load_plugins()
    return pm


def _make_plugin(base: Path, dir_name: str, name: str = "") -> None:
    """创建最小可加载插件目录"""
    plugin_dir = base / dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "entrance.py").write_text(
        FAKE_ENTRANCE.format(name=name or dir_name), encoding="utf-8")
    (plugin_dir / "IXPlugin.json").write_text(json.dumps({
        "id": dir_name, "name": name or dir_name,
        "version": "release.1.0.0", "main": "entrance.py"}), encoding="utf-8")


@pytest.fixture
def notices(monkeypatch):
    """屏蔽模态提示：确认框一律同意，结果提示记录到列表"""
    recorded = []
    monkeypatch.setattr(PluginManagementDialog, "_confirm_move",
                        lambda self, name, target: True)
    monkeypatch.setattr(pmd_module, "_notice",
                        lambda *args, **kwargs: recorded.append(args))
    return recorded


@pytest.fixture
def dialog(qtbot, isolated_pm, notices):
    """已加载一个官方插件的插件管理对话框"""
    dlg = PluginManagementDialog(isolated_pm)
    qtbot.addWidget(dlg)
    return dlg


class TestMoveButtonText:
    """按钮文案随当前 Tab 变化"""

    def test_official_tab_offers_move_to_thirdparty(self, dialog):
        """官方 Tab 下按钮提供「移至第三方插件」"""
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)

        assert dialog.move_btn.text() == "移至第三方插件"

    def test_thirdparty_tab_offers_move_to_official(self, dialog):
        """第三方 Tab 下按钮提供「移至官方插件」"""
        dialog.scope_tabs.setCurrentIndex(THIRDPARTY_TAB_INDEX)

        assert dialog.move_btn.text() == "移至官方插件"

    def test_button_text_follows_tab_switch(self, dialog):
        """切换 Tab 时文案实时更新"""
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)
        first = dialog.move_btn.text()

        dialog.scope_tabs.setCurrentIndex(THIRDPARTY_TAB_INDEX)

        assert dialog.move_btn.text() != first


class TestMovePlugin:
    """点击按钮执行移动"""

    def test_move_plugin_to_thirdparty(self, dialog, isolated_pm):
        """官方 Tab 下点击后插件移动到第三方目录并刷新列表"""
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)
        dialog._plugin_lists[SCOPE_OFFICIAL].setCurrentRow(0)

        dialog._on_move_plugin()

        assert not (isolated_pm.official_plugin_dir / "demo-move").exists()
        assert (isolated_pm.thirdparty_plugin_dir / "demo-move").is_dir()
        assert dialog._plugin_lists[SCOPE_OFFICIAL].count() == 0
        assert dialog._plugin_lists[SCOPE_THIRDPARTY].count() == 1

    def test_move_plugin_back_to_official(self, dialog, isolated_pm):
        """第三方 Tab 下点击后插件移动回官方目录"""
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)
        dialog._plugin_lists[SCOPE_OFFICIAL].setCurrentRow(0)
        dialog._on_move_plugin()

        dialog.scope_tabs.setCurrentIndex(THIRDPARTY_TAB_INDEX)
        dialog._plugin_lists[SCOPE_THIRDPARTY].setCurrentRow(0)
        dialog._on_move_plugin()

        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()
        assert not (isolated_pm.thirdparty_plugin_dir / "demo-move").exists()
        assert dialog._plugin_lists[SCOPE_OFFICIAL].count() == 1

    def test_move_without_selection_moves_nothing(self, dialog, isolated_pm,
                                                  monkeypatch):
        """未选择插件时只提示，不移动任何目录"""
        shown = []
        monkeypatch.setattr(pmd_module.Message, "info",
                            lambda *args, **kwargs: shown.append(args))
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)

        dialog._on_move_plugin()

        assert shown, "应提示先选择插件"
        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()

    def test_move_failure_is_reported(self, dialog, isolated_pm, notices,
                                      monkeypatch):
        """核心层拒绝移动时提示失败，且不改变目录位置"""
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)
        dialog._plugin_lists[SCOPE_OFFICIAL].setCurrentRow(0)
        # 目标分类放入同名目录 → 核心层拒绝
        (isolated_pm.thirdparty_plugin_dir / "demo-move").mkdir(parents=True)

        dialog._on_move_plugin()

        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()
        assert notices, "失败时应给出提示"


class TestLocalInstallScope:
    """本地插件包安装的目标范围跟随当前 Tab"""

    def test_install_zip_passes_official_scope(self, dialog, monkeypatch):
        """官方 Tab 下打开本地安装对话框时传入 official"""
        captured = _patch_local_dialog(monkeypatch)
        dialog.scope_tabs.setCurrentIndex(OFFICIAL_TAB_INDEX)

        dialog._on_install_zip()

        assert captured.get("target_scope") == SCOPE_OFFICIAL

    def test_install_zip_passes_thirdparty_scope(self, dialog, monkeypatch):
        """第三方 Tab 下打开本地安装对话框时传入 thirdparty"""
        captured = _patch_local_dialog(monkeypatch)
        dialog.scope_tabs.setCurrentIndex(THIRDPARTY_TAB_INDEX)

        dialog._on_install_zip()

        assert captured.get("target_scope") == SCOPE_THIRDPARTY


def _patch_local_dialog(monkeypatch) -> dict:
    """用替身替换本地安装对话框，记录构造参数（不弹模态窗口）"""
    captured = {}

    class _FakeDialog:
        """记录 target_scope 的对话框替身"""

        def __init__(self, parent=None, installer=None, target_scope=None):
            captured["target_scope"] = target_scope
            captured["installer"] = installer

        plugin_installed = type("_Sig", (), {
            "connect": staticmethod(lambda _cb: None)})()

        def exec(self) -> int:
            return 0

    monkeypatch.setattr(pmd_module, "LocalPackageInstallDialog", _FakeDialog)
    return captured
