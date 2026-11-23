# -*- coding: utf-8 -*-
"""插件包识别（core/plugin/package_discovery.py）测试

测试目标: 从解压目录树中识别「单插件 / 插件集 / 无效」的全部规则
测试范围:

- 分类：根目录插件、包装层（GitHub ``repo-<branch>/``、二次打包）、并列多插件
- 索引驱动：``IXRepo.json`` 顺序与声明标记、未声明项仍作候选、声明目录缺失、路径越界
- 扫描规则：多层嵌套、噪声目录与 ``_``/``.`` 前缀跳过、命中即停止下潜、重复 ID 去重
- 描述文件校验：缺字段、版本号格式、ID 格式、非 JSON
- 边界与诊断：空包的可诊断信息、深度上限截断、``has_index`` 标志
"""

import json
from pathlib import Path

import pytest

from core.plugin.package_discovery import (
    MAX_DISCOVERY_DEPTH,
    PACKAGE_KIND_INVALID,
    PACKAGE_KIND_MULTI,
    PACKAGE_KIND_SINGLE,
    inspect_package,
    validate_descriptor,
)

#: 合法描述文件的最小内容
_VALID_DESCRIPTOR = {
    "id": "demo-plugin",
    "name": "演示插件",
    "version": "release.1.0.0",
    "main": "entrance.py",
}


def make_plugin(directory: Path, plugin_id: str, version: str = "release.1.0.0",
                descriptor: dict = None) -> Path:
    """在指定目录创建最小可识别插件（可传入自定义描述内容）"""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text("", encoding="utf-8")
    (directory / "entrance.py").write_text("# fake\n", encoding="utf-8")
    content = descriptor if descriptor is not None else {
        "id": plugin_id, "name": plugin_id, "version": version, "main": "entrance.py"}
    (directory / "IXPlugin.json").write_text(
        json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return directory


def make_index(root: Path, entries: list) -> None:
    """写入 IXRepo.json 索引"""
    root.mkdir(parents=True, exist_ok=True)
    (root / "IXRepo.json").write_text(
        json.dumps({"version": 1, "plugins": entries}, ensure_ascii=False),
        encoding="utf-8")


class TestClassification:
    """单插件 / 插件集 的基础分类"""

    def test_root_directory_is_single_plugin(self, tmp_path):
        """描述文件位于包根 → single，且 rel_path 为空串"""
        make_plugin(tmp_path, "solo")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_SINGLE
        assert result.candidates[0].descriptor_id == "solo"
        assert result.candidates[0].rel_path == ""

    def test_github_style_wrapper_is_unwrapped(self, tmp_path):
        """GitHub 下载的 repo-main/ 包装层被穿透 → single"""
        make_plugin(tmp_path / "repo-main", "solo")

        assert inspect_package(tmp_path).kind == PACKAGE_KIND_SINGLE

    def test_double_wrapper_is_unwrapped(self, tmp_path):
        """用户二次打包（外层/仓库名/插件） → single"""
        make_plugin(tmp_path / "outer" / "repo-main", "solo")

        assert inspect_package(tmp_path).kind == PACKAGE_KIND_SINGLE

    def test_parallel_plugins_are_collection(self, tmp_path):
        """并列多个插件目录 → multi（本次需求的核心场景）"""
        make_plugin(tmp_path / "repo-main" / "plugin-a", "plugin-a")
        make_plugin(tmp_path / "repo-main" / "plugin-b", "plugin-b")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_MULTI
        assert sorted(c.descriptor_id for c in result.candidates) == ["plugin-a", "plugin-b"]

    def test_rel_path_is_relative_posix(self, tmp_path):
        """候选的 rel_path 是相对包根的 posix 路径（非绝对路径）"""
        make_plugin(tmp_path / "repo-main" / "packages" / "plugin-a", "plugin-a")
        make_plugin(tmp_path / "repo-main" / "packages" / "plugin-b", "plugin-b")

        result = inspect_package(tmp_path)

        assert all(not Path(c.rel_path).is_absolute() for c in result.candidates)
        assert all("\\" not in c.rel_path for c in result.candidates)


class TestIndexDriven:
    """IXRepo.json 索引驱动的识别"""

    def test_index_order_and_declared_flag(self, tmp_path):
        """索引项优先且按索引顺序，declared_in_index 为 True"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-b", "plugin-b")
        make_plugin(repo / "plugin-a", "plugin-a")
        make_index(repo, [{"id": "plugin-a", "name": "A", "path": "plugin-a"},
                          {"id": "plugin-b", "name": "B", "path": "plugin-b/"}])

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_MULTI
        assert [c.descriptor_id for c in result.candidates] == ["plugin-a", "plugin-b"]
        assert all(c.declared_in_index for c in result.candidates)
        assert result.has_index is True

    def test_undeclared_plugin_is_extra_candidate(self, tmp_path):
        """索引未声明但实际存在的插件也作为候选，且带警告"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        make_plugin(repo / "plugin-extra", "plugin-extra")
        make_index(repo, [{"id": "plugin-a", "name": "A", "path": "plugin-a"}])

        result = inspect_package(tmp_path)

        extras = [c for c in result.candidates if not c.declared_in_index]
        assert [c.descriptor_id for c in extras] == ["plugin-extra"]
        assert any("未在" in w and "声明" in w for w in result.warnings)

    def test_missing_declared_directory_reported(self, tmp_path):
        """索引声明的目录不存在 → 该条目不可安装并给出原因（不静默丢弃）"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        make_index(repo, [{"id": "plugin-a", "name": "A", "path": "plugin-a"},
                          {"id": "plugin-missing", "name": "M", "path": "plugin-missing"}])

        missing = [c for c in inspect_package(tmp_path).candidates
                   if c.descriptor_id == "plugin-missing"]

        assert len(missing) == 1
        assert missing[0].valid is False
        assert "不存在" in missing[0].error

    def test_index_path_escape_rejected(self, tmp_path):
        """索引路径越出包根 → 拒绝并说明原因"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        make_index(repo, [{"id": "escape", "name": "E", "path": "../../outside"}])

        escape = [c for c in inspect_package(tmp_path).candidates
                  if c.descriptor_id == "escape"]

        assert len(escape) == 1
        assert escape[0].valid is False
        assert "越出包根" in escape[0].error

    def test_broken_index_falls_back_to_scan(self, tmp_path):
        """索引文件损坏时退回目录扫描，并把原因作为警告"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        (repo / "IXRepo.json").write_text("{ not json", encoding="utf-8")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_SINGLE
        assert any("IXRepo.json" in w for w in result.warnings)


class TestScanRules:
    """无需索引时的目录扫描规则"""

    def test_deep_nesting_is_found(self, tmp_path):
        """monorepo 多层嵌套仍能命中（包装层下潜 + 递归扫描）"""
        make_plugin(tmp_path / "repo-main" / "left" / "plugin-a", "plugin-a")
        make_plugin(tmp_path / "repo-main" / "right" / "plugin-b", "plugin-b")

        assert inspect_package(tmp_path).kind == PACKAGE_KIND_MULTI

    def test_macos_noise_directory_ignored(self, tmp_path):
        """__MACOSX 等噪声目录不影响判定"""
        make_plugin(tmp_path / "repo-main" / "plugin-a", "plugin-a")
        (tmp_path / "__MACOSX").mkdir()
        (tmp_path / "__MACOSX" / "junk.txt").write_text("x", encoding="utf-8")

        assert inspect_package(tmp_path).kind == PACKAGE_KIND_SINGLE

    def test_underscore_prefixed_directory_skipped(self, tmp_path):
        """下划线前缀目录被跳过（与插件加载器约定一致）"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "_wip", "wip")
        make_plugin(repo / "plugin-a", "plugin-a")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_SINGLE
        assert result.candidates[0].descriptor_id == "plugin-a"

    def test_inner_plugin_directory_not_scanned(self, tmp_path):
        """插件目录内部再嵌套插件目录时不误判（命中即停止下潜）"""
        inner = make_plugin(tmp_path / "repo-main" / "plugin-a", "plugin-a")
        make_plugin(inner / "examples" / "demo", "demo")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_SINGLE
        assert len(result.candidates) == 1

    def test_duplicate_id_keeps_first_and_marks_rest(self, tmp_path):
        """同一包内重复 ID：保留首个，其余标记不可安装"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        make_plugin(repo / "plugin-a-copy", "plugin-a")

        result = inspect_package(tmp_path)

        invalid = [c for c in result.candidates if not c.valid]
        assert len(result.candidates) == 2
        assert len(invalid) == 1 and "重复" in invalid[0].error

    def test_depth_limit_truncates_with_warning(self, tmp_path):
        """超过深度上限的插件不被识别，并给出截断警告"""
        repo = tmp_path / "repo-main"
        (repo / "left").mkdir(parents=True)
        (repo / "right").mkdir(parents=True)     # 两个分支阻止包装层下潜
        deep = repo / "left"
        for index in range(MAX_DISCOVERY_DEPTH + 1):
            deep = deep / f"lvl{index}"
        make_plugin(deep, "too-deep")

        result = inspect_package(tmp_path)

        assert all(c.descriptor_id != "too-deep" for c in result.candidates)
        assert any("层级超过上限" in w for w in result.warnings)


class TestDescriptorValidation:
    """描述文件校验（与安装器共用同一实现）"""

    @pytest.mark.parametrize("descriptor,keyword", [
        ({"id": "x", "name": "X"}, "缺少必需字段"),
        ({"id": "x", "name": "X", "version": "1.0.0", "main": "entrance.py"}, "版本号格式无效"),
        ({"id": "bad id", "name": "X", "version": "release.1.0.0", "main": "entrance.py"},
         "ID 格式无效"),
    ])
    def test_invalid_descriptor_marked_not_installable(self, tmp_path, descriptor, keyword):
        """缺字段 / 版本号非法 / ID 非法 → 该候选不可安装并给出具体原因"""
        make_plugin(tmp_path, "ignored", descriptor=descriptor)

        candidate = inspect_package(tmp_path).candidates[0]

        assert candidate.valid is False
        assert keyword in candidate.error

    def test_non_json_descriptor_reported(self, tmp_path):
        """描述文件不是合法 JSON → 报告读取失败而非崩溃"""
        plugin_dir = tmp_path / "repo-main" / "broken"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "IXPlugin.json").write_text("{ not json", encoding="utf-8")

        candidate = inspect_package(tmp_path).candidates[0]

        assert candidate.valid is False
        assert "失败" in candidate.error

    def test_invalid_candidate_does_not_block_others(self, tmp_path):
        """一个候选非法不影响同包内其他插件的识别"""
        repo = tmp_path / "repo-main"
        make_plugin(repo / "plugin-a", "plugin-a")
        bad = repo / "plugin-b"
        bad.mkdir(parents=True)
        (bad / "IXPlugin.json").write_text(json.dumps({"id": "plugin-b"}), encoding="utf-8")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_MULTI
        assert sum(1 for c in result.candidates if c.valid) == 1

    def test_validate_descriptor_accepts_valid_minimum(self):
        """最小合法描述文件通过校验"""
        assert validate_descriptor(dict(_VALID_DESCRIPTOR)) == (True, "")


class TestDiagnostics:
    """无效包的可诊断信息"""

    def test_empty_package_is_invalid_with_stats(self, tmp_path):
        """无任何插件 → invalid，诊断含扫描统计与指引"""
        (tmp_path / "repo-main" / "docs").mkdir(parents=True)
        (tmp_path / "repo-main" / "README.md").write_text("hi", encoding="utf-8")

        result = inspect_package(tmp_path)

        assert result.kind == PACKAGE_KIND_INVALID
        assert "已扫描到" in result.error
        assert "IXPlugin.json" in result.error

    def test_missing_root_is_invalid(self, tmp_path):
        """解压目录不存在 → invalid（不抛异常）"""
        result = inspect_package(tmp_path / "not-exists")

        assert result.kind == PACKAGE_KIND_INVALID
        assert "不存在" in result.error

    def test_has_index_false_without_index_file(self, tmp_path):
        """无索引文件的包 has_index 为 False（决定默认勾选策略）"""
        make_plugin(tmp_path / "repo-main" / "plugin-a", "plugin-a")

        assert inspect_package(tmp_path).has_index is False
