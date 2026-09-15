# -*- coding: utf-8 -*-
"""本地插件包安装（GitHubPluginInstaller 的 zip 路径）测试

测试目标: `install_from_zip()` / `inspect_local_package()` 的端到端行为
测试范围:

- 单插件包安装（旧签名 `install_from_zip(zip_path)` 行为不变）
- 插件集包一次安装、子集安装（selected_plugins 按相对路径或插件 id 匹配）
- 识别阶段只读：不落盘、不改注册表，并给出安装关系（新装/升级/降级）
- 索引驱动的默认勾选策略（有索引时未声明项默认不勾选）
- 不可安装候选被跳过且不影响其余插件；无效包返回单条错误且零副作用
- 临时目录在成功/失败路径下都被清理

约定：使用 `isolated_pm` fixture 把官方/第三方目录与配置全部指向 `tmp_path`，
不触碰仓库真实 `plugin/`、`custom_plugin/`、`config/`。
"""

import json
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest

from core.plugin.config_manager import PluginConfigManager
from core.plugin.github_plugin_installer import GitHubPluginInstaller
from core.plugin.manager import PluginManager
from core.plugin.package_discovery import PACKAGE_KIND_INVALID
from core.plugin.plugin_groups import PluginGroupStore
from core.plugin.plugin_registry import PluginRegistry

FAKE_ENTRANCE = "# fake entrance\n"

#: 插件集 zip 的默认包装层（GitHub 下载的仓库压缩包形态）
REPO_ROOT = "repo-main"


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


@pytest.fixture
def installer(isolated_pm):
    """使用隔离 PluginManager 的安装器"""
    return GitHubPluginInstaller(isolated_pm)


def make_plugin_zip(zip_path: Path, root: str = REPO_ROOT,
                    plugins: List[Tuple[str, str]] = None,
                    index_entries: Optional[List[Dict]] = None,
                    files: Optional[Dict[str, str]] = None,
                    descriptors: Optional[Dict[str, dict]] = None) -> Path:
    """制作插件集 zip

    Args:
        zip_path: 目标 zip 路径
        root: 包装层目录名（空串表示无包装层）
        plugins: [(目录名, 版本), ...]
        index_entries: 非 None 时写入 IXRepo.json
        files: 附加文件 {相对路径: 内容}
        descriptors: 覆盖某目录的描述内容 {目录名: dict}

    Returns:
        Path: zip 路径
    """
    prefix_root = f"{root}/" if root else ""
    with zipfile.ZipFile(zip_path, "w") as archive:
        for dir_name, version in plugins or []:
            prefix = f"{prefix_root}{dir_name}/"
            archive.writestr(f"{prefix}__init__.py", "")
            archive.writestr(f"{prefix}entrance.py", FAKE_ENTRANCE)
            descriptor = (descriptors or {}).get(dir_name) or {
                "id": dir_name, "name": dir_name, "version": version,
                "main": "entrance.py"}
            archive.writestr(f"{prefix}IXPlugin.json",
                             json.dumps(descriptor, ensure_ascii=False))
        if index_entries is not None:
            index = {"version": 1, "plugins": index_entries}
            archive.writestr(f"{prefix_root}IXRepo.json",
                             json.dumps(index, ensure_ascii=False))
        for rel_path, content in (files or {}).items():
            archive.writestr(f"{prefix_root}{rel_path}", content)
    return zip_path


class TestSinglePluginPackage:
    """单插件包：与历史行为一致"""

    def test_install_single_plugin_zip(self, installer, isolated_pm, tmp_path):
        """旧签名 install_from_zip(zip_path) 仍安装单个插件并登记注册表"""
        zip_path = make_plugin_zip(tmp_path / "solo.zip", plugins=[("solo-plugin", "release.1.0.0")])

        results = installer.install_from_zip(zip_path)

        assert len(results) == 1 and results[0].success
        assert (isolated_pm.thirdparty_plugin_dir / "solo-plugin").is_dir()
        record = isolated_pm.registry.find_by_descriptor("thirdparty", "solo-plugin")
        assert record is not None and record[1]["version"] == "release.1.0.0"

    def test_inspect_single_plugin(self, installer, tmp_path):
        """识别单插件包：kind=single、计划一项、默认勾选"""
        zip_path = make_plugin_zip(tmp_path / "solo.zip", plugins=[("solo-plugin", "release.1.0.0")])

        inspection = installer.inspect_local_package(zip_path)

        assert inspection.kind == "single"
        assert len(inspection.plans) == 1
        assert inspection.plans[0].default_selected is True
        assert inspection.plans[0].relation == "new"

    def test_inspect_does_not_install(self, installer, isolated_pm, tmp_path):
        """识别是只读操作：不产生插件目录、不改注册表"""
        zip_path = make_plugin_zip(tmp_path / "solo.zip", plugins=[("solo-plugin", "release.1.0.0")])

        installer.inspect_local_package(zip_path)

        assert not (isolated_pm.thirdparty_plugin_dir / "solo-plugin").exists()
        assert isolated_pm.registry.all() == {}


class TestCollectionPackage:
    """插件集包：一次装完与子集安装"""

    def test_install_collection_in_one_call(self, installer, isolated_pm, tmp_path):
        """插件集一次安装全部插件，并记录 source_type / source_path"""
        zip_path = make_plugin_zip(tmp_path / "collection.zip", plugins=[
            ("plugin-a", "release.1.0.0"), ("plugin-b", "release.2.0.0")])

        results = installer.install_from_zip(zip_path)

        assert len(results) == 2 and all(r.success for r in results)
        assert (isolated_pm.thirdparty_plugin_dir / "plugin-a").is_dir()
        assert (isolated_pm.thirdparty_plugin_dir / "plugin-b").is_dir()
        record = isolated_pm.registry.find_by_descriptor("thirdparty", "plugin-a")
        assert record[1]["source_type"] == "local_zip"
        assert record[1]["source_path"] == "plugin-a"

    def test_install_subset_by_rel_path(self, installer, isolated_pm, tmp_path):
        """selected_plugins 按包内相对路径筛选，未选插件不落盘"""
        zip_path = make_plugin_zip(tmp_path / "collection.zip", plugins=[
            ("plugin-a", "release.1.0.0"), ("plugin-b", "release.1.0.0")])

        results = installer.install_from_zip(zip_path, selected_plugins=["plugin-a"])

        assert len(results) == 1 and results[0].plugin_id == "plugin-a"
        assert not (isolated_pm.thirdparty_plugin_dir / "plugin-b").exists()

    def test_install_subset_by_descriptor_id(self, installer, isolated_pm, tmp_path):
        """selected_plugins 也可用插件 id 匹配（目录名与 id 不一致时）"""
        zip_path = make_plugin_zip(
            tmp_path / "collection.zip", plugins=[("folder-name", "release.1.0.0")],
            descriptors={"folder-name": {"id": "descriptor-id", "name": "X",
                                         "version": "release.1.0.0",
                                         "main": "entrance.py"}})

        results = installer.install_from_zip(zip_path, selected_plugins=["descriptor-id"])

        assert len(results) == 1 and results[0].plugin_id == "descriptor-id"
        assert (isolated_pm.thirdparty_plugin_dir / "descriptor-id").is_dir()

    def test_empty_selection_installs_nothing(self, installer, isolated_pm, tmp_path):
        """未选中任何插件时返回空列表且不落盘"""
        zip_path = make_plugin_zip(tmp_path / "collection.zip",
                                   plugins=[("plugin-a", "release.1.0.0")])

        results = installer.install_from_zip(zip_path, selected_plugins=["not-exists"])

        assert results == []
        assert not (isolated_pm.thirdparty_plugin_dir / "plugin-a").exists()

    def test_invalid_candidate_skipped_without_blocking(self, installer, isolated_pm, tmp_path):
        """不可安装候选被跳过，其余插件照常安装"""
        zip_path = make_plugin_zip(
            tmp_path / "collection.zip", plugins=[("plugin-a", "release.1.0.0")],
            files={"plugin-b/IXPlugin.json": json.dumps({"id": "plugin-b"}),
                   "plugin-b/entrance.py": FAKE_ENTRANCE})

        results = installer.install_from_zip(zip_path)

        assert len(results) == 1 and results[0].plugin_id == "plugin-a"
        assert not (isolated_pm.thirdparty_plugin_dir / "plugin-b").exists()


class TestRelationsAndSelection:
    """安装关系预演与默认勾选策略"""

    def test_upgrade_relation_and_prev_version(self, installer, tmp_path):
        """已装低版本后识别为升级，并带出已装版本号"""
        installer.install_from_zip(make_plugin_zip(
            tmp_path / "v1.zip", plugins=[("plugin-a", "release.1.0.0")]))
        zip_v2 = make_plugin_zip(tmp_path / "v2.zip", plugins=[("plugin-a", "release.2.0.0")])

        plan = installer.inspect_local_package(zip_v2).plans[0]

        assert plan.relation == "upgrade"
        assert plan.prev_version == "release.1.0.0"
        assert plan.target_scope == "thirdparty"

    def test_downgrade_relation(self, installer, tmp_path):
        """已装高版本后识别为降级"""
        installer.install_from_zip(make_plugin_zip(
            tmp_path / "v2.zip", plugins=[("plugin-a", "release.2.0.0")]))
        zip_v1 = make_plugin_zip(tmp_path / "v1.zip", plugins=[("plugin-a", "release.1.0.0")])

        assert installer.inspect_local_package(zip_v1).plans[0].relation == "downgrade"

    def test_index_declared_selected_undeclared_not(self, installer, tmp_path):
        """有索引时：索引声明项默认勾选，未声明项默认不勾选"""
        zip_path = make_plugin_zip(
            tmp_path / "indexed.zip",
            plugins=[("plugin-a", "release.1.0.0"), ("plugin-extra", "release.1.0.0")],
            index_entries=[{"id": "plugin-a", "name": "A", "path": "plugin-a"}])

        inspection = installer.inspect_local_package(zip_path)

        selected = {plan.candidate.descriptor_id: plan.default_selected
                    for plan in inspection.plans}
        assert inspection.has_index is True
        assert selected["plugin-a"] is True
        assert selected["plugin-extra"] is False
        assert any("未在" in w for w in inspection.warnings)

    def test_no_index_selects_all_by_default(self, installer, tmp_path):
        """无索引时全部默认勾选"""
        zip_path = make_plugin_zip(tmp_path / "plain.zip", plugins=[
            ("plugin-a", "release.1.0.0"), ("plugin-b", "release.1.0.0")])

        inspection = installer.inspect_local_package(zip_path)

        assert inspection.has_index is False
        assert all(plan.default_selected for plan in inspection.plans)


class TestInvalidPackage:
    """无效包：可诊断信息与零副作用"""

    def test_invalid_package_reports_diagnostics(self, installer, tmp_path):
        """无插件的压缩包 → invalid + 扫描统计与指引"""
        zip_path = make_plugin_zip(tmp_path / "bad.zip", plugins=[],
                                   files={"README.md": "hello"})

        inspection = installer.inspect_local_package(zip_path)

        assert inspection.kind == PACKAGE_KIND_INVALID
        assert "已扫描到" in inspection.error

    def test_invalid_package_install_returns_error(self, installer, isolated_pm, tmp_path):
        """对无效包执行安装 → 单条错误结果，且不产生任何插件目录"""
        zip_path = make_plugin_zip(tmp_path / "bad.zip", plugins=[],
                                   files={"README.md": "hello"})

        results = installer.install_from_zip(zip_path)

        assert len(results) == 1 and not results[0].success
        thirdparty = isolated_pm.thirdparty_plugin_dir
        assert not thirdparty.exists() or list(thirdparty.iterdir()) == []

    def test_missing_zip_reports_error(self, installer, tmp_path):
        """zip 不存在 → 单条错误结果"""
        results = installer.install_from_zip(tmp_path / "not-exists.zip")

        assert len(results) == 1 and not results[0].success


class TestTempDirectoryCleanup:
    """临时目录清理（成功与失败路径）"""

    @pytest.mark.parametrize("make_case", ["success", "invalid"])
    def test_temp_dir_removed(self, installer, tmp_path, monkeypatch, make_case):
        """安装结束后安装器创建的临时目录必须被删除"""
        created: List[Path] = []
        real_mkdtemp = tempfile.mkdtemp

        def tracking_mkdtemp(prefix=None, dir=None):
            """把临时目录限制在 tmp_path 内并记录，便于断言清理"""
            path = Path(real_mkdtemp(prefix=prefix, dir=str(tmp_path)))
            created.append(path)
            return str(path)

        monkeypatch.setattr(
            "core.plugin.github_plugin_installer.tempfile.mkdtemp", tracking_mkdtemp)
        if make_case == "success":
            zip_path = make_plugin_zip(tmp_path / "ok.zip",
                                       plugins=[("plugin-a", "release.1.0.0")])
        else:
            zip_path = make_plugin_zip(tmp_path / "bad.zip", plugins=[],
                                       files={"README.md": "hi"})

        installer.install_from_zip(zip_path)

        assert created, "安装器应创建临时目录"
        assert all(not path.exists() for path in created)
