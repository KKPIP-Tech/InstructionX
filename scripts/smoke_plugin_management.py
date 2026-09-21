"""
插件管理功能无网冒烟测试

覆盖能力：
- 插件加载后版本注册表（PluginRegistry）自动回填
- 自定义分组保存与「分组 → 组内 → 未分组」排序
- 本地 zip 插件包安装 / 升级 / 降级 / 重装关系检测
- 无公共根目录的 zip 插件包安装
- **插件集 zip 自动识别与一次安装（GitHub 下载形态，含任意层嵌套）**
- **插件集子集安装（selected_plugins）与 IXRepo.json 索引驱动的默认勾选策略**
- **无法识别的压缩包给出可诊断信息而非笼统报错**
- **本地插件包按 Tab 范围安装（官方 / 第三方）且已安装插件不搬家**
- **插件在官方 / 第三方目录之间移动（move_plugin_to_scope）**
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
from typing import Dict, List, Optional, Tuple

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


def make_multi_plugin_zip(zip_path: Path, root: str,
                          plugins: List[Tuple[str, str, str]],
                          index_entries: Optional[List[Dict]] = None) -> None:
    """制作插件集 zip（GitHub 仓库形态：root/ 下并列多个插件目录）

    Args:
        zip_path: 目标 zip 路径
        root: 仓库根目录名（GitHub 下载的 zip 为 ``<repo>-<branch>``，空串表示无包装层）
        plugins: [(目录名, 版本, 显示名), ...]
        index_entries: 非 None 时写入 IXRepo.json（索引驱动场景）
    """
    prefix_root = f"{root}/" if root else ""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for dir_name, version, name in plugins:
            prefix = f"{prefix_root}{dir_name}/"
            zf.writestr(f"{prefix}__init__.py", "")
            zf.writestr(f"{prefix}entrance.py", FAKE_ENTRANCE.format(name=name))
            descriptor = {"id": dir_name, "name": name, "version": version,
                          "main": "entrance.py"}
            zf.writestr(f"{prefix}IXPlugin.json", json.dumps(descriptor, ensure_ascii=False))
        if index_entries is not None:
            index = {"version": 1, "plugins": index_entries}
            zf.writestr(f"{prefix_root}IXRepo.json", json.dumps(index, ensure_ascii=False))


def make_plain_zip(zip_path: Path, files: Dict[str, str]) -> None:
    """制作不含任何插件描述文件的普通 zip（用于无效包诊断用例）"""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for rel_path, content in files.items():
            zf.writestr(rel_path, content)


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

        print("== 8. 插件集 zip 自动识别与一次安装（GitHub 下载形态） ==")
        # 用户下载的 GitHub 仓库 zip：repo-main/ 下并列多个插件目录
        zip_collection = work_dir / "collection.zip"
        make_multi_plugin_zip(zip_collection, "repo-main", [
            ("demo-five", "release.1.0.0", "演示插件五"),
            ("demo-six", "release.1.0.0", "演示插件六"),
        ])
        inspection = installer.inspect_local_package(zip_collection)
        check("识别为插件集", inspection.kind == "multi")
        check("识别到 2 个插件", len(inspection.plans) == 2)
        check("无索引时全部默认勾选",
              all(plan.default_selected for plan in inspection.plans))
        check("识别阶段不做安装（目录尚未出现）",
              not (work_dir / "custom_plugin" / "demo-five").exists())
        results = installer.install_from_zip(zip_collection)
        check("插件集一次安装 2 个插件",
              len(results) == 2 and all(r.success for r in results))
        check("插件集成员均已落盘",
              (work_dir / "custom_plugin" / "demo-five").exists()
              and (work_dir / "custom_plugin" / "demo-six").exists())
        check("注册表记录来源为本地插件包",
              (pm.registry.find_by_descriptor("thirdparty", "demo-five") or (None, {}))[1]
              .get("source_type") == "local_zip")
        check("注册表记录包内相对路径",
              (pm.registry.find_by_descriptor("thirdparty", "demo-five") or (None, {}))[1]
              .get("source_path") == "demo-five")

        print("== 9. 插件集子集安装（selected_plugins） ==")
        zip_subset = work_dir / "collection-subset.zip"
        make_multi_plugin_zip(zip_subset, "repo-main", [
            ("demo-seven", "release.1.0.0", "演示插件七"),
            ("demo-eight", "release.1.0.0", "演示插件八"),
        ])
        results = installer.install_from_zip(
            zip_subset, selected_plugins=["demo-seven"])
        check("仅安装所选插件",
              len(results) == 1 and results[0].plugin_id == "demo-seven")
        check("未选插件未落盘",
              not (work_dir / "custom_plugin" / "demo-eight").exists())

        print("== 10. IXRepo.json 索引驱动的默认勾选策略 ==")
        zip_indexed = work_dir / "collection-indexed.zip"
        make_multi_plugin_zip(
            zip_indexed, "repo-main",
            [("demo-nine", "release.1.0.0", "演示插件九"),
             ("demo-extra", "release.1.0.0", "未声明插件")],
            index_entries=[{"id": "demo-nine", "name": "演示插件九", "path": "demo-nine"}])
        inspection = installer.inspect_local_package(zip_indexed)
        selected_map = {plan.candidate.descriptor_id: plan.default_selected
                        for plan in inspection.plans}
        check("索引声明项默认勾选", selected_map.get("demo-nine") is True)
        check("未声明项默认不勾选", selected_map.get("demo-extra") is False)
        check("给出未声明提示",
              any("未在" in w and "声明" in w for w in inspection.warnings))
        results = installer.install_from_zip(zip_indexed)
        check("未指定 selected_plugins 时仍安装全部可安装项",
              len(results) == 2 and all(r.success for r in results))

        print("== 11. 无效包给出可诊断信息 ==")
        zip_invalid = work_dir / "not-a-plugin.zip"
        make_plain_zip(zip_invalid, {"repo-main/README.md": "hello",
                                     "repo-main/docs/guide.md": "guide"})
        inspection = installer.inspect_local_package(zip_invalid)
        check("无插件包识别为 invalid", inspection.kind == "invalid")
        check("诊断含扫描统计与指引",
              "已扫描到" in inspection.error and "IXPlugin.json" in inspection.error)
        results = installer.install_from_zip(zip_invalid)
        check("无效包安装返回单条错误结果",
              len(results) == 1 and not results[0].success)
        check("无效包不产生任何插件目录",
              not any((work_dir / "custom_plugin" / name).exists()
                      for name in ("repo-main", "docs")))

        print("== 12. 插件目录内包外文件的兜底备份 ==")
        # 模拟「插件把运行时数据写进自己目录」（规范要求改存 DataProvider）
        installed_dir = work_dir / "custom_plugin" / "demo-five"
        (installed_dir / "runtime.dat").write_text("runtime", encoding="utf-8")
        zip_upgrade = work_dir / "demo-five-2.0.0.zip"
        make_plugin_zip(zip_upgrade, "demo-five", "release.2.0.0", "演示插件五")
        results = installer.install_from_zip(zip_upgrade)
        check("升级成功", results[0].success)
        check("结果提示已备份包外文件",
              "已备份 1 个包外文件" in results[0].message)
        backup_root = work_dir / "data" / "plugin_backup" / "demo-five"
        snapshots = sorted(backup_root.iterdir()) if backup_root.is_dir() else []
        check("已生成快照", len(snapshots) == 1)
        check("快照内含包外数据文件",
              bool(snapshots) and (snapshots[0] / "runtime.dat").is_file())
        check("升级后新目录内不再有包外数据文件",
              not (installed_dir / "runtime.dat").exists())
        zip_upgrade2 = work_dir / "demo-five-3.0.0.zip"
        make_plugin_zip(zip_upgrade2, "demo-five", "release.3.0.0", "演示插件五")
        results = installer.install_from_zip(zip_upgrade2)
        check("无包外文件时不提示备份",
              "已备份" not in results[0].message)
        check("无包外文件时不新增快照",
              len(sorted(backup_root.iterdir())) == 1)

        print("== 13. 本地插件包按 Tab 范围安装（官方 / 第三方）==")
        zip_official = work_dir / "official-tab.zip"
        make_plugin_zip(zip_official, "demo-official", "release.1.0.0", "官方演示插件")
        inspection = installer.inspect_local_package(zip_official, target_scope="official")
        check("预演范围跟随 target_scope",
              inspection.plans[0].target_scope == "official")
        check("预演不落盘",
              not (work_dir / "plugin" / "demo-official").exists())
        results = installer.install_from_zip(zip_official, target_scope="official")
        check("安装成功", len(results) == 1 and results[0].success)
        check("装进官方插件目录",
              (work_dir / "plugin" / "demo-official").is_dir())
        check("第三方目录无副本",
              not (work_dir / "custom_plugin" / "demo-official").exists())
        check("注册表登记为 official",
              pm.registry.find_by_descriptor("official", "demo-official") is not None)
        # 已安装插件保持原地：即使传入另一侧范围也不搬家、不产生第二份安装
        results = installer.install_from_zip(zip_official, target_scope="thirdparty")
        check("已安装插件重复安装成功", len(results) == 1 and results[0].success)
        check("已安装插件仍在官方目录",
              (work_dir / "plugin" / "demo-official").is_dir())
        check("已安装插件未在第三方生成副本",
              not (work_dir / "custom_plugin" / "demo-official").exists())

        print("== 14. 插件在官方 / 第三方之间移动 ==")
        pm.reload_plugins()
        uuid_move = find_uuid(pm, "demo-one")
        identity_file = work_dir / "plugin" / "demo-one" / ".plugin_info.json"
        check("移动前插件位于官方目录并已生成 UUID 文件", identity_file.is_file())
        pm.group_store.save("official", [], [("plugin", uuid_move)])
        result = pm.move_plugin_to_scope(uuid_move, "thirdparty")
        check("移动返回成功", result["success"])
        check("官方目录中已不存在",
              not (work_dir / "plugin" / "demo-one").exists())
        check("插件已出现在第三方目录",
              (work_dir / "custom_plugin" / "demo-one").is_dir())
        check("UUID 文件随目录一起移动",
              (work_dir / "custom_plugin" / "demo-one" / ".plugin_info.json").is_file())
        check("注册表分类已更新为 thirdparty",
              (pm.registry.get(uuid_move) or {}).get("scope") == "thirdparty")
        check("原分组/排序记录已清除",
              not pm.group_store.load_order("official"))
        pm.reload_plugins()
        check("重新加载后归入第三方列表",
              any(p.plugin_id == uuid_move for p in pm.get_thirdparty_plugins()))
        check("重新加载后 UUID 保持不变", find_uuid(pm, "demo-one") == uuid_move)
        # 已在目标分类中的插件再次移动应被拒绝
        result = pm.move_plugin_to_scope(uuid_move, "thirdparty")
        check("同分类移动被拒绝", not result["success"] and "已在" in result["message"])
        # 目标分类存在同名目录时拒绝移动
        (work_dir / "plugin" / "demo-one").mkdir(parents=True, exist_ok=True)
        result = pm.move_plugin_to_scope(uuid_move, "official")
        check("目标存在同名目录时被拒绝",
              not result["success"] and "同名" in result["message"])
        check("被拒绝时插件仍在原目录",
              (work_dir / "custom_plugin" / "demo-one").is_dir())
        shutil.rmtree(work_dir / "plugin" / "demo-one", ignore_errors=True)
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
