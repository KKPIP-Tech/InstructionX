"""兼容性结果在本地包、仓库详情与 Release 中的传播测试。"""

import json
from unittest.mock import MagicMock

from core.plugin.github_plugin_installer import GitHubPluginInstaller
from core.plugin.package_discovery import inspect_package
from core.version import APP_VERSION


CURRENT = APP_VERSION.to_string()
FIELD = "compatible_framework_versions"


def _descriptor(version=CURRENT, versions=None):
    """构造合法的插件描述文件。"""
    return {
        "id": "demo",
        "name": "Demo",
        "version": version,
        "main": "entrance.py",
        FIELD: [CURRENT] if versions is None else versions,
    }


def test_local_candidate_carries_compatibility(tmp_path):
    """本地包候选必须保留当前版本已验证的评估结果。"""
    (tmp_path / "entrance.py").write_text("# test\n", encoding="utf-8")
    (tmp_path / "IXPlugin.json").write_text(
        json.dumps(_descriptor()), encoding="utf-8")

    candidate = inspect_package(tmp_path).candidates[0]

    assert candidate.framework_compatibility.is_verified
    assert candidate.framework_compatibility.declared_versions == (CURRENT,)


def test_legacy_local_candidate_is_missing_declaration(tmp_path):
    """没有字段的旧包仍产生候选，但兼容状态为未声明。"""
    descriptor = _descriptor()
    del descriptor[FIELD]
    (tmp_path / "entrance.py").write_text("# test\n", encoding="utf-8")
    (tmp_path / "IXPlugin.json").write_text(
        json.dumps(descriptor), encoding="utf-8")

    candidate = inspect_package(tmp_path).candidates[0]

    assert candidate.valid
    assert not candidate.framework_compatibility.is_verified
    assert candidate.framework_compatibility.declared_versions == ()


def test_repository_plugin_info_carries_compatibility():
    """GitHub 仓库检查不能丢弃描述文件中的兼容性声明。"""
    installer = GitHubPluginInstaller(MagicMock())

    info = installer._parse_plugin_descriptor(_descriptor(), "")

    assert info.framework_compatibility.is_verified
    assert info.framework_compatibility.declared_versions == (CURRENT,)


def test_each_release_uses_compatibility_from_its_own_tag():
    """Release 列表必须读取各 Tag 的声明，且每个 Tag 只读取一次。"""
    installer = GitHubPluginInstaller(MagicMock())
    descriptors = {
        "v1": _descriptor(version="release.1.0.0", versions=[CURRENT]),
        "v2": _descriptor(version="release.2.0.0", versions=["alpha.0.9.0"]),
    }
    installer._fetch_file_content = MagicMock(
        side_effect=lambda _owner, _repo, _path, ref=None, credential=None: descriptors[ref])
    releases = [
        {"tag_name": "v1", "name": "V1", "prerelease": False, "published_at": ""},
        {"tag_name": "v2", "name": "V2", "prerelease": False, "published_at": ""},
    ]

    results = installer._build_release_infos(
        "owner", "repo", releases, "IXPlugin.json", None)

    assert results[0].framework_compatibility.is_verified
    assert not results[1].framework_compatibility.is_verified
    assert results[1].framework_compatibility.declared_versions == ("alpha.0.9.0",)
    assert installer._fetch_file_content.call_count == 2
