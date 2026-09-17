# -*- coding: utf-8 -*-
"""插件分类移动（PluginManager.move_plugin_to_scope）测试

测试目标: 已安装插件在官方 / 第三方插件目录之间的移动
测试范围:

- 正常路径：目录移动、UUID 文件随迁、注册表 scope 更新、分组/排序记录清除、
  重新加载后归入目标分类且 UUID 不变（插件数据与语言覆盖依据 UUID 保留）
- 边界：已在目标分类中的重复移动、目标分类存在同名目录、未注册 / 未加载的插件
- 异常路径：目录移动失败（模拟 OSError）时返回失败并重新扫描恢复列表
- 附带校验：_scope_directory() 对合法 / 非法范围的解析
"""

import json
from pathlib import Path

import pytest

from core.plugin.config_manager import PluginConfigManager
from core.plugin.manager import (
    SCOPE_OFFICIAL, SCOPE_THIRDPARTY, PluginManager,
)
from core.plugin.plugin_groups import PluginGroupStore
from core.plugin.plugin_registry import PluginRegistry


FAKE_ENTRANCE = '''"""fake plugin"""
from core.interfaces import IPlugin


class FakePlugin(IPlugin):
    @property
    def plugin_name(self):
        return "{name}"

    def _create_widget(self, parent=None, data_provider=None):
        return None
'''


@pytest.fixture
def isolated_pm(tmp_path, monkeypatch):
    """构建目录全部指向 tmp_path 的隔离 PluginManager"""
    monkeypatch.setattr(PluginManager, "_instance", None)
    monkeypatch.setattr(PluginManager, "_initialized", False)
    pm = PluginManager()
    pm.official_plugin_dir = tmp_path / "plugin"
    pm.thirdparty_plugin_dir = tmp_path / "custom_plugin"
    pm.config_manager = PluginConfigManager(tmp_path / "config")
    pm.registry = PluginRegistry(tmp_path / "config")
    pm.group_store = PluginGroupStore(tmp_path / "config")
    return pm


def make_fake_plugin(base: Path, dir_name: str, name: str = "") -> Path:
    """在 base 下创建一个最小可加载插件目录"""
    plugin_dir = base / dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "entrance.py").write_text(
        FAKE_ENTRANCE.format(name=name or dir_name), encoding="utf-8")
    (plugin_dir / "IXPlugin.json").write_text(json.dumps({
        "id": dir_name, "name": name or dir_name,
        "version": "release.1.0.0", "main": "entrance.py"}), encoding="utf-8")
    return plugin_dir


def load_one_official_plugin(pm: PluginManager) -> str:
    """在官方目录创建一个插件并加载，返回其 UUID"""
    make_fake_plugin(pm.official_plugin_dir, "demo-move", "演示移动插件")
    pm.load_plugins()
    for plugin in pm.get_official_plugins():
        if plugin._plugin_dir.name == "demo-move":
            return plugin.plugin_id
    raise AssertionError("插件未加载")


class TestScopeDirectory:
    """范围标识 → 插件目录解析"""

    def test_known_scopes(self, isolated_pm):
        """official / thirdparty 解析到对应目录"""
        assert isolated_pm._scope_directory(SCOPE_OFFICIAL) == isolated_pm.official_plugin_dir
        assert (isolated_pm._scope_directory(SCOPE_THIRDPARTY)
                == isolated_pm.thirdparty_plugin_dir)

    def test_unknown_scope_returns_none(self, isolated_pm):
        """非法范围返回 None（由调用方转为失败结果）"""
        assert isolated_pm._scope_directory("nowhere") is None


class TestMoveSuccess:
    """正常路径：官方 → 第三方 → 官方"""

    def test_move_official_to_thirdparty(self, isolated_pm):
        """移动后目录、注册表分类与加载列表全部跟随目标分类"""
        uuid_move = load_one_official_plugin(isolated_pm)
        identity_file = isolated_pm.official_plugin_dir / "demo-move" / ".plugin_info.json"
        assert identity_file.is_file(), "加载时应已生成插件 UUID 文件"

        result = isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)

        assert result["success"] is True
        assert not (isolated_pm.official_plugin_dir / "demo-move").exists()
        assert (isolated_pm.thirdparty_plugin_dir / "demo-move").is_dir()
        assert (isolated_pm.thirdparty_plugin_dir / "demo-move"
                / ".plugin_info.json").is_file()
        assert isolated_pm.registry.get(uuid_move)["scope"] == SCOPE_THIRDPARTY
        # 移动后需重新加载才会出现在目标分类的加载列表
        isolated_pm.reload_plugins()
        assert [p.plugin_id for p in isolated_pm.get_thirdparty_plugins()] == [uuid_move]
        assert isolated_pm.get_official_plugins() == []

    def test_uuid_preserved_after_move(self, isolated_pm):
        """UUID 随目录迁移保持不变（插件数据与语言覆盖以 UUID 为键）"""
        uuid_before = load_one_official_plugin(isolated_pm)

        isolated_pm.move_plugin_to_scope(uuid_before, SCOPE_THIRDPARTY)
        isolated_pm.reload_plugins()

        uuid_after = isolated_pm.get_thirdparty_plugins()[0].plugin_id
        assert uuid_after == uuid_before

    def test_move_back_to_official(self, isolated_pm):
        """第三方 → 官方往返移动"""
        uuid_move = load_one_official_plugin(isolated_pm)
        isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)
        isolated_pm.reload_plugins()

        result = isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_OFFICIAL)

        assert result["success"] is True
        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()
        assert isolated_pm.registry.get(uuid_move)["scope"] == SCOPE_OFFICIAL

    def test_sort_and_group_records_cleared(self, isolated_pm):
        """原分类的排序与分组记录被清除（移动后按未分组处理）"""
        uuid_move = load_one_official_plugin(isolated_pm)
        isolated_pm.group_store.save(SCOPE_OFFICIAL, [], [("plugin", uuid_move)])
        assert isolated_pm.group_store.load_order(SCOPE_OFFICIAL)

        isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)

        assert isolated_pm.group_store.load_order(SCOPE_OFFICIAL) == []

    def test_registry_entry_fields_preserved(self, isolated_pm):
        """移动只改 scope：版本 / 来源 / 安装时间保持不变"""
        uuid_move = load_one_official_plugin(isolated_pm)
        before = dict(isolated_pm.registry.get(uuid_move))

        isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)

        after = isolated_pm.registry.get(uuid_move)
        for field in ("descriptor_id", "name", "version", "installed_at",
                      "source_type", "source_url", "source_path"):
            assert after[field] == before[field]
        assert after["scope"] == SCOPE_THIRDPARTY


class TestMoveRejected:
    """边界与异常：不满足条件时拒绝移动且不破坏现状"""

    def test_plugin_not_loaded(self, isolated_pm):
        """插件未加载（UUID 不存在）时返回失败"""
        result = isolated_pm.move_plugin_to_scope("not-a-uuid", SCOPE_THIRDPARTY)

        assert result["success"] is False
        assert "不存在" in result["message"]

    def test_unknown_target_scope(self, isolated_pm):
        """目标范围非法时返回失败"""
        uuid_move = load_one_official_plugin(isolated_pm)

        result = isolated_pm.move_plugin_to_scope(uuid_move, "nowhere")

        assert result["success"] is False
        assert "分类" in result["message"]
        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()

    def test_same_scope_rejected(self, isolated_pm):
        """插件已在目标分类中时返回失败（不重复移动）"""
        uuid_move = load_one_official_plugin(isolated_pm)

        result = isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_OFFICIAL)

        assert result["success"] is False
        assert "已在" in result["message"]

    def test_same_name_directory_conflict(self, isolated_pm):
        """目标分类已存在同名目录时拒绝，插件留在原目录"""
        uuid_move = load_one_official_plugin(isolated_pm)
        (isolated_pm.thirdparty_plugin_dir / "demo-move").mkdir(parents=True)

        result = isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)

        assert result["success"] is False
        assert "同名" in result["message"]
        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()
        # 拒绝后插件仍在运行时表中可用
        assert isolated_pm.get_plugin_by_id(uuid_move) is not None

    def test_directory_move_failure(self, isolated_pm, monkeypatch):
        """目录移动抛错时返回失败，并重新扫描目录恢复插件列表"""
        uuid_move = load_one_official_plugin(isolated_pm)

        def broken_move(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("core.plugin.manager.shutil.move", broken_move)

        result = isolated_pm.move_plugin_to_scope(uuid_move, SCOPE_THIRDPARTY)

        assert result["success"] is False
        assert "移动插件目录失败" in result["message"]
        # 插件目录未变，重新扫描后仍可加载
        assert (isolated_pm.official_plugin_dir / "demo-move").is_dir()
        assert [p.plugin_id for p in isolated_pm.get_official_plugins()] == [uuid_move]
