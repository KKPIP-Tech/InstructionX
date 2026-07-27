"""
插件管理功能无网冒烟测试

覆盖能力：
- 插件加载后版本注册表（PluginRegistry）自动回填
- 自定义分组保存与「分组 → 组内 → 未分组」排序
- 本地 zip 插件包安装 / 升级 / 降级 / 重装关系检测
- 无公共根目录的 zip 插件包安装
- 插件卸载（目录、UUID 文件、注册表、分组、排序清理 + sys.modules 清理）
- reload_plugins 热重载

运行方式：.venv\\Scripts\\python.exe scripts\\smoke_plugin_management.py
"""

import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

# ===== 项目根目录加入搜索路径 =====
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.plugin.manager import PluginManager
from core.plugin.config_manager import PluginConfigManager
from core.plugin.plugin_registry import PluginRegistry
from core.plugin.plugin_groups import PluginGroupStore, PluginGroup
from core.plugin.github_plugin_installer import GitHubPluginInstaller

# ===== 测试结果统计 =====
_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    """记录一项断言结果"""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name}")


# 假插件入口模板（最小 IPlugin 实现，不创建任何 Qt 控件）
FAKE_ENTRANCE = '''"""fake plugin for smoke test"""
from core.interfaces import IPlugin


class FakePlugin(IPlugin):
    @property
    def plugin_name(self):
        return "{name}"

    def _create_widget(self, parent=None, data_provider=None):
        return None
'''


def make_plugin_dir(base: Path, dir_name: str, version: str, name: str) -> Path:
    """在指定目录下创建一个假插件目录"""
    plugin_dir = base / dir_name
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / "entrance.py").write_text(FAKE_ENTRANCE.format(name=name), encoding="utf-8")
    descriptor = {
        "id": dir_name,
        "name": name,
        "version": version,
        "main": "entrance.py",
    }
    (plugin_dir / "IXPlugin.json").write_text(
        json.dumps(descriptor, ensure_ascii=False), encoding="utf-8"
    )
    return plugin_dir


def make_plugin_zip(zip_path: Path, dir_name: str, version: str,
                    name: str, with_root: bool = True) -> None:
    """制作插件 zip 包（with_root=False 时文件直接位于 zip 根）"""
    prefix = f"{dir_name}/" if with_root else ""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(f"{prefix}__init__.py", "")
        zf.writestr(f"{prefix}entrance.py", FAKE_ENTRANCE.format(name=name))
        descriptor = {"id": dir_name, "name": name, "version": version, "main": "entrance.py"}
        zf.writestr(f"{prefix}IXPlugin.json", json.dumps(descriptor, ensure_ascii=False))


def build_isolated_manager(work_dir: Path) -> PluginManager:
    """构建隔离的 PluginManager（所有目录指向临时工作区）"""
    PluginManager._instance = None
    PluginManager._initialized = False
    pm = PluginManager()
    pm.official_plugin_dir = work_dir / "plugin"
    pm.thirdparty_plugin_dir = work_dir / "custom_plugin"
    pm.config_manager = PluginConfigManager(work_dir / "config")
    pm.registry = PluginRegistry(work_dir / "config")
    pm.group_store = PluginGroupStore(work_dir / "config")
    return pm


def find_uuid(pm: PluginManager, dir_name: str) -> str:
    """按插件目录名查找已加载插件的 UUID"""
    for plugin in pm.get_all_plugins():
        if plugin._plugin_dir.name == dir_name:
            return plugin.plugin_id
    raise AssertionError(f"插件未加载: {dir_name}")


def main() -> int:
    """执行全部冒烟测试，返回失败数"""
    work_dir = Path(tempfile.mkdtemp(prefix="ix_smoke_plugin_mgmt_"))
    try:
        pm = build_isolated_manager(work_dir)

        print("== 1. 插件加载与注册表回填 ==")
        make_plugin_dir(work_dir / "plugin", "demo-one", "release.1.0.0", "演示插件一")
        make_plugin_dir(work_dir / "plugin", "demo-two", "release.1.2.0", "演示插件二")
        make_plugin_dir(work_dir / "custom_plugin", "demo-three", "release.2.0.0", "演示插件三")
        pm.load_plugins()
        check("加载 2 个官方插件", len(pm.get_official_plugins()) == 2)
        check("加载 1 个第三方插件", len(pm.get_thirdparty_plugins()) == 1)
        uuid_one = find_uuid(pm, "demo-one")
        uuid_two = find_uuid(pm, "demo-two")
        uuid_three = find_uuid(pm, "demo-three")
        record_one = pm.registry.get(uuid_one)
        check("注册表回填官方插件版本",
              record_one is not None and record_one["version"] == "release.1.0.0")
        check("注册表回填来源为 unknown", record_one["source_type"] == "unknown")

        print("== 2. 自定义分组与混排排序 ==")
        group = PluginGroup.new("测试分组")
        group.plugins = [uuid_one]
        # 面板顺序：demo-two 插件在前，分组在后（验证分组可插入任意位置）
        panel_order = [("plugin", uuid_two), ("group", group.id)]
        check("保存分组与面板顺序",
              pm.save_groups("official", [group], panel_order))
        sorted_items = pm.get_sorted_plugins("official")
        check("未分组插件可排在分组之前",
              sorted_items[0][0] == "plugin"
              and sorted_items[0][1].plugin_id == uuid_two)
        check("分组按指定位置渲染",
              sorted_items[1][0] == "group"
              and sorted_items[1][2][0].plugin_id == uuid_one)
        check("渲染项总数正确", len(sorted_items) == 2)

        print("== 2.5 分组配置 v1 → v2 迁移 ==")
        v1_config_dir = work_dir / "config_v1"
        v1_config_dir.mkdir(parents=True, exist_ok=True)
        v1_data = {
            "version": 1,
            "official": [{"id": "g1", "name": "旧分组", "icon_key": "📁",
                          "plugins": ["p1"]}],
            "thirdparty": [],
        }
        (v1_config_dir / "plugin_groups.json").write_text(
            json.dumps(v1_data, ensure_ascii=False), encoding="utf-8"
        )
        v1_store = PluginGroupStore(v1_config_dir)
        check("v1 分组可加载", len(v1_store.load("official")) == 1)
        v1_order = v1_store.load_order("official")
        check("v1 迁移生成分组顺序条目",
              v1_order == [("group", "g1")])

        print("== 3. 本地 zip 安装 / 升级 / 降级 / 重装 ==")
        installer = GitHubPluginInstaller(pm)
        zip_v210 = work_dir / "demo-three-2.1.0.zip"
        make_plugin_zip(zip_v210, "demo-three", "release.2.1.0", "演示插件三")
        results = installer.install_from_zip(zip_v210)
        check("zip 升级安装成功", results[0].success)
        check("识别为升级", results[0].relation == "upgrade")
        record_three = pm.registry.find_by_descriptor("thirdparty", "demo-three")
        check("注册表版本更新为 2.1.0",
              record_three is not None and record_three[1]["version"] == "release.2.1.0")
        uuid_three = record_three[0]

        zip_v150 = work_dir / "demo-three-1.5.0.zip"
        make_plugin_zip(zip_v150, "demo-three", "release.1.5.0", "演示插件三")
        results = installer.install_from_zip(zip_v150)
        check("zip 降级安装成功", results[0].success)
        check("识别为降级", results[0].relation == "downgrade")

        results = installer.install_from_zip(zip_v150)
        check("同版本识别为重装", results[0].relation == "reinstall")

        print("== 4. 无公共根目录的 zip 安装 ==")
        zip_flat = work_dir / "demo-four.zip"
        make_plugin_zip(zip_flat, "demo-four", "release.1.0.0", "演示插件四", with_root=False)
        results = installer.install_from_zip(zip_flat)
        check("扁平 zip 安装成功", results[0].success)
        check("新插件识别为 new", results[0].relation == "new")

        print("== 5. reload_plugins 热重载 ==")
        pm.reload_plugins()
        check("重载后插件数量正确", len(pm.get_all_plugins()) == 4)

        print("== 6. 插件卸载 ==")
        # 先把第三方插件加入分组，验证卸载时分组清理
        tp_group = PluginGroup.new("第三方分组")
        tp_group.plugins = [uuid_three]
        pm.save_groups("thirdparty", [tp_group])

        result = pm.uninstall_plugin(uuid_three, remove_data=False)
        check("卸载返回成功", result["success"])
        check("插件目录已删除", not (work_dir / "custom_plugin" / "demo-three").exists())
        check("注册表记录已移除", pm.registry.get(uuid_three) is None)
        check("分组中已移除该插件",
              uuid_three not in pm.get_groups("thirdparty")[0].plugins)
        check("sys.modules 已清理",
              not any("demo-three" in name for name in sys.modules))
        check("卸载不存在的插件返回失败",
              not pm.uninstall_plugin(uuid_three)["success"])

        print("== 6.1 卸载无数据插件并勾选删除数据 ==")
        # demo-four 从未在 DataProvider 注册/写数据，勾选删除数据应静默跳过而非报错
        uuid_four = None
        for plugin in pm.get_thirdparty_plugins():
            if getattr(plugin, '_plugin_dir', None) is not None \
                    and plugin._plugin_dir.name == "demo-four":
                uuid_four = plugin.plugin_id
        result = pm.uninstall_plugin(uuid_four, remove_data=True)
        check("卸载成功", result["success"])
        check("无「删除插件数据失败」警告",
              not any("删除插件数据失败" in w for w in result["warnings"]))

        print("== 7. 卸载后重载一致性 ==")
        pm.reload_plugins()
        check("重载后剩余 2 个插件", len(pm.get_all_plugins()) == 2)
    finally:
        # 关闭后台任务管理器线程池，避免进程悬挂
        try:
            from core.task import BackgroundTaskManager
            BackgroundTaskManager().shutdown()
        except Exception:
            pass
        shutil.rmtree(work_dir, ignore_errors=True)

    print(f"\n结果: {_passed} 通过, {_failed} 失败")
    return _failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
