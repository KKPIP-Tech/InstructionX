"""插件框架兼容性声明的解析与判定测试。"""

import importlib

import pytest

from core.plugin.plugin_version import PluginVersion
from core.version import APP_VERSION


CURRENT = PluginVersion.from_string("alpha.1.1.3")
FIELD = "compatible_framework_versions"


@pytest.fixture
def compatibility_module():
    """按需加载待实现的兼容性评估模块。"""
    return importlib.import_module("core.plugin.framework_compatibility")


def _descriptor(versions):
    """构造只包含兼容性字段的描述片段。"""
    return {FIELD: versions}


def test_missing_field_is_unverified(compatibility_module):
    """旧插件缺少字段时应保留安装能力，但状态为未声明。"""
    result = compatibility_module.evaluate_framework_compatibility({}, CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.MISSING_DECLARATION
    assert not result.is_verified
    assert result.declared_versions == ()
    assert result.current_version == CURRENT.to_string()


def test_exact_current_version_is_verified(compatibility_module):
    """声明数组精确包含当前版本时才属于已验证。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(["alpha.1.1.0", "alpha.1.1.3"]), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.VERIFIED
    assert result.is_verified
    assert result.declared_versions == ("alpha.1.1.0", "alpha.1.1.3")


def test_current_version_not_listed_preserves_declared_versions(compatibility_module):
    """当前版本未列入时必须保留作者声明的版本供界面展示。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(["alpha.1.1.0", "alpha.1.2.0"]), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.CURRENT_NOT_LISTED
    assert not result.is_verified
    assert result.declared_versions == ("alpha.1.1.0", "alpha.1.2.0")


def test_release_channel_is_part_of_exact_match(compatibility_module):
    """相同数字但不同发布通道不能视为兼容当前 Alpha。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(["release.1.1.2"]), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.CURRENT_NOT_LISTED
    assert not result.is_verified


@pytest.mark.parametrize("raw", [None, "alpha.1.1.3", {"versions": []}, 42])
def test_non_array_declaration_is_invalid(compatibility_module, raw):
    """显式 null 和非数组值均属于非法声明，而不是缺字段。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(raw), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.INVALID_DECLARATION
    assert not result.is_verified


def test_empty_array_is_invalid(compatibility_module):
    """空数组没有任何已验证版本，应归为非法声明。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor([]), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.INVALID_DECLARATION
    assert not result.is_verified


def test_mixed_invalid_entries_never_count_as_verified(compatibility_module):
    """即使数组包含当前版本，存在非法项也不能整体视为有效声明。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(["alpha.1.1.3", "not-a-version", 7]), CURRENT)

    assert result.status == compatibility_module.FrameworkCompatibilityStatus.INVALID_DECLARATION
    assert not result.is_verified
    assert result.declared_versions == ("alpha.1.1.3",)
    assert result.invalid_entries == ("not-a-version", "7")


def test_duplicate_versions_are_normalized(compatibility_module):
    """重复项和首尾空白应归一化，不改变精确匹配语义。"""
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor([" alpha.1.1.3 ", "alpha.1.1.3"]), CURRENT)

    assert result.is_verified
    assert result.declared_versions == ("alpha.1.1.3",)


def test_current_version_can_be_injected(compatibility_module):
    """调用方可评估未来框架版本，而不修改全局版本号。"""
    future = PluginVersion.from_string("alpha.1.2.0")
    result = compatibility_module.evaluate_framework_compatibility(
        _descriptor(["alpha.1.2.0"]), future)

    assert result.is_verified
    assert result.current_version == "alpha.1.2.0"


def test_default_current_version_uses_framework_version(compatibility_module):
    """未显式注入时必须读取框架 APP_VERSION。"""
    result = compatibility_module.evaluate_framework_compatibility({})

    assert result.current_version == APP_VERSION.to_string()
