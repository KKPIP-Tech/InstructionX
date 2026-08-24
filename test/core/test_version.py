"""框架版本号单一来源（core/version.py）测试。

覆盖点（对应 dev 分支「框架版本号升级为 Alpha 1.0.5」提交）：

- ``VERSION`` 常量符合 ``大.小.补丁`` 数字格式；
- ``APP_VERSION`` 由 ``VERSION`` 正确解析（类型 / 大中小号一致）；
- 版本字符串 / 显示字符串的格式与当前版本值（Alpha 1.0.5）；
- ``pyproject.toml`` 的 ``tool.setuptools.dynamic`` 确实指向
  ``core.version.VERSION``（单一来源约束不被破坏）。
"""

import re
from pathlib import Path

import pytest

from core.plugin.plugin_version import VersionType
from core.version import (
    APP_VERSION,
    VERSION,
    get_instructionx_version_display,
    get_instructionx_version_string,
)

#: 当前发布版本（每次版本号升级时需同步更新本常量）
EXPECTED_VERSION = "1.0.5"
#: 版本号格式：大.小.补丁 全数字
_VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
#: 项目根目录（本文件位于 test/core/ 下）
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestVersionConstant:
    """VERSION 常量的格式与当前值。"""

    def test_version_matches_semver_format(self):
        """VERSION 必须为 大.小.补丁 的全数字格式。"""
        assert _VERSION_PATTERN.match(VERSION), f"VERSION 格式非法: {VERSION!r}"

    def test_version_is_current_release(self):
        """VERSION 等于当前发布版本（版本升级时需同步更新 EXPECTED_VERSION）。"""
        assert VERSION == EXPECTED_VERSION


class TestAppVersion:
    """APP_VERSION 由 VERSION 解析得到，两者必须一致。"""

    def test_app_version_type_is_alpha(self):
        """当前处于 Alpha 阶段。"""
        assert APP_VERSION.version_type == VersionType.ALPHA

    def test_app_version_numbers_match_version(self):
        """APP_VERSION 的大/小/补丁号与 VERSION 拆分结果一致。"""
        major, minor, patch = (int(part) for part in VERSION.split("."))
        assert APP_VERSION.major == major
        assert APP_VERSION.minor == minor
        assert APP_VERSION.patch == patch


class TestVersionStrings:
    """版本字符串 / 显示字符串的格式。"""

    def test_version_string_format(self):
        """版本字符串为 'Alpha 大.小.补丁' 形式。"""
        assert get_instructionx_version_string() == f"Alpha {VERSION}"

    def test_version_string_current_value(self):
        """当前版本字符串固定为 'Alpha 1.0.5'（防回归钉扎）。"""
        assert get_instructionx_version_string() == "Alpha 1.0.5"

    def test_version_display_has_prefix(self):
        """显示字符串带 '版本 ' 前缀。"""
        assert get_instructionx_version_display() == f"版本 Alpha {VERSION}"


class TestPyprojectSingleSource:
    """pyproject.toml 动态版本必须指向 core.version.VERSION（单一来源约束）。"""

    def test_pyproject_dynamic_version_source(self):
        """pyproject 通过 tool.setuptools.dynamic 静态读取 VERSION，不另写版本号。"""
        content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert 'dynamic = ["version"]' in content
        assert 'version = {attr = "core.version.VERSION"}' in content

    def test_pyproject_has_no_hardcoded_version(self):
        """pyproject 的 [project] 段禁止出现硬编码 version 字段。"""
        content = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        project_section = content.split("[project]", 1)[1].split("\n[", 1)[0]
        assert not re.search(r"^version\s*=", project_section, re.MULTILINE)
