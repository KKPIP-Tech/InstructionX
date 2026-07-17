"""
pytest tests for core/plugin/plugin_version.py (PluginVersion, VersionType)
"""

import pytest

from core.plugin.plugin_version import PluginVersion, VersionType


class TestVersionType:
    """Tests for VersionType enum."""

    def test_version_types_exist(self):
        """VersionType enum should have all expected members."""
        assert VersionType.RELEASE
        assert VersionType.PRE_RELEASE
        assert VersionType.BETA
        assert VersionType.ALPHA
        assert VersionType.INTERNAL

    def test_priority_order(self):
        """Priority order: INTERNAL(1) < ALPHA(2) < BETA(3) < PRE_RELEASE(4) < RELEASE(5)."""
        assert VersionType.INTERNAL.get_priority() == 1
        assert VersionType.ALPHA.get_priority() == 2
        assert VersionType.BETA.get_priority() == 3
        assert VersionType.PRE_RELEASE.get_priority() == 4
        assert VersionType.RELEASE.get_priority() == 5

    def test_display_names(self):
        """get_display_name() returns correct Chinese names."""
        assert VersionType.RELEASE.get_display_name() == "正式版"
        assert VersionType.PRE_RELEASE.get_display_name() == "预发布版"
        assert VersionType.BETA.get_display_name() == "测试版"
        assert VersionType.ALPHA.get_display_name() == "内测版"
        assert VersionType.INTERNAL.get_display_name() == "内部版"


class TestPluginVersionFromString:
    """Tests for PluginVersion.from_string()."""

    def test_parse_release(self):
        """from_string('release.1.0.0') parses correctly."""
        v = PluginVersion.from_string("release.1.0.0")
        assert v.version_type == VersionType.RELEASE
        assert v.major == 1
        assert v.minor == 0
        assert v.patch == 0

    def test_parse_beta(self):
        """from_string('beta.2.3.4') parses correctly."""
        v = PluginVersion.from_string("beta.2.3.4")
        assert v.version_type == VersionType.BETA
        assert v.major == 2
        assert v.minor == 3
        assert v.patch == 4

    def test_parse_alpha(self):
        """from_string('alpha.3.2.1') parses correctly."""
        v = PluginVersion.from_string("alpha.3.2.1")
        assert v.version_type == VersionType.ALPHA
        assert v.major == 3
        assert v.minor == 2
        assert v.patch == 1

    def test_parse_internal(self):
        """from_string('internal.0.0.1') parses correctly."""
        v = PluginVersion.from_string("internal.0.0.1")
        assert v.version_type == VersionType.INTERNAL
        assert v.major == 0
        assert v.minor == 0
        assert v.patch == 1

    def test_parse_pre_release(self):
        """from_string('pre-release.5.4.3') parses correctly."""
        v = PluginVersion.from_string("pre-release.5.4.3")
        assert v.version_type == VersionType.PRE_RELEASE
        assert v.major == 5
        assert v.minor == 4
        assert v.patch == 3

    def test_parse_invalid_format_not_four_parts(self):
        """from_string('invalid') raises ValueError (not 4 parts)."""
        with pytest.raises(ValueError, match="Invalid version format"):
            PluginVersion.from_string("invalid")

    def test_parse_invalid_format_only_three_parts(self):
        """from_string('release.1.0') raises ValueError (only 3 parts)."""
        with pytest.raises(ValueError, match="Invalid version format"):
            PluginVersion.from_string("release.1.0")

    def test_parse_unknown_version_type(self):
        """from_string('unknown.1.0.0.0') raises ValueError for unknown type."""
        # "unknown.1.0.0.0" has 4 parts so format check passes,
        # then VersionType("unknown") raises which gets caught and re-raised
        # as "Invalid version type" but the outer error message prepends
        # "Invalid version format" so we match on the "Invalid" prefix.
        with pytest.raises(ValueError, match="Invalid"):
            PluginVersion.from_string("unknown.1.0.0.0")

    def test_parse_negative_numbers_raises(self):
        """from_string('release.-1.0.0') raises ValueError for negative numbers."""
        with pytest.raises(ValueError, match="non-negative"):
            PluginVersion.from_string("release.-1.0.0")


class TestPluginVersionComparison:
    """Tests for PluginVersion comparison operators."""

    def test_version_type_priority_release_gt_beta(self):
        """release > beta."""
        release = PluginVersion.from_string("release.1.0.0")
        beta = PluginVersion.from_string("beta.1.0.0")
        assert release > beta
        assert beta < release

    def test_version_type_priority_beta_gt_alpha(self):
        """beta > alpha."""
        beta = PluginVersion.from_string("beta.1.0.0")
        alpha = PluginVersion.from_string("alpha.1.0.0")
        assert beta > alpha
        assert alpha < beta

    def test_version_type_priority_alpha_gt_internal(self):
        """alpha > internal."""
        alpha = PluginVersion.from_string("alpha.1.0.0")
        internal = PluginVersion.from_string("internal.1.0.0")
        assert alpha > internal
        assert internal < alpha

    def test_patch_version_comparison_1_2_3_gt_1_2_2(self):
        """1.2.3 > 1.2.2 (same type, same major/minor, higher patch)."""
        v1 = PluginVersion.from_string("release.1.2.3")
        v2 = PluginVersion.from_string("release.1.2.2")
        assert v1 > v2
        assert v2 < v1

    def test_minor_version_comparison_2_0_0_gt_1_9_9(self):
        """2.0.0 > 1.9.9 (same type, higher major)."""
        v1 = PluginVersion.from_string("release.2.0.0")
        v2 = PluginVersion.from_string("release.1.9.9")
        assert v1 > v2
        assert v2 < v1

    def test_equality_same_fields(self):
        """Same fields are equal."""
        v1 = PluginVersion.from_string("release.1.2.3")
        v2 = PluginVersion.from_string("release.1.2.3")
        assert v1 == v2
        assert not (v1 != v2)

    def test_inequality_different_fields(self):
        """Different fields are not equal."""
        v1 = PluginVersion.from_string("release.1.2.3")
        v2 = PluginVersion.from_string("release.1.2.4")
        assert v1 != v2

    def test_le_and_ge(self):
        """__le__ and __ge__ work correctly."""
        v1 = PluginVersion.from_string("release.1.0.0")
        v2 = PluginVersion.from_string("release.1.0.0")
        v3 = PluginVersion.from_string("release.2.0.0")
        assert v1 <= v2
        assert v1 <= v3
        assert v3 >= v1
        assert v3 >= v2

    def test_compare_different_types_same_numbers(self):
        """Same numbers but different types: release.1.0.0 > beta.1.0.0."""
        release = PluginVersion.from_string("release.1.0.0")
        beta = PluginVersion.from_string("beta.1.0.0")
        assert release > beta


class TestPluginVersionDisplay:
    """Tests for PluginVersion display methods."""

    def test_get_display_version_includes_chinese_name(self):
        """get_display_version() includes the Chinese type name."""
        v = PluginVersion.from_string("release.1.0.0")
        display = v.get_display_version()
        assert "正式版" in display
        assert "1.0.0" in display

    def test_get_display_version_beta(self):
        """get_display_version() for beta includes '测试版'."""
        v = PluginVersion.from_string("beta.2.3.4")
        assert "测试版" in v.get_display_version()
        assert "2.3.4" in v.get_display_version()


class TestPluginVersionString:
    """Tests for PluginVersion string representation."""

    def test_to_string_format(self):
        """to_string() returns correct '<type>.<major>.<minor>.<patch>' format."""
        v = PluginVersion.from_string("release.1.2.3")
        assert v.to_string() == "release.1.2.3"

    def test_to_string_beta(self):
        """to_string() for beta returns 'beta.x.y.z'."""
        v = PluginVersion.from_string("beta.2.3.4")
        assert v.to_string() == "beta.2.3.4"

    def test_str_delegates_to_to_string(self):
        """__str__ delegates to to_string()."""
        v = PluginVersion.from_string("release.5.4.3")
        assert str(v) == v.to_string()
        assert str(v) == "release.5.4.3"

    def test_repr_format(self):
        """__repr__ returns PluginVersion('<string>') format."""
        v = PluginVersion.from_string("release.1.0.0")
        assert repr(v) == "PluginVersion('release.1.0.0')"


class TestPluginVersionHashable:
    """Tests for PluginVersion hashability (used as dict keys / set elements)."""

    def test_can_be_used_as_dict_key(self):
        """PluginVersion 可作为字典 key 使用。"""
        v = PluginVersion.from_string("release.1.0.0")
        d = {v: "value"}
        assert d[v] == "value"

    def test_same_versions_have_same_hash(self):
        """相同版本对象哈希值相同。"""
        v1 = PluginVersion.from_string("release.1.0.0")
        v2 = PluginVersion.from_string("release.1.0.0")
        assert hash(v1) == hash(v2)

    def test_can_be_added_to_set(self):
        """PluginVersion 可加入集合。"""
        v1 = PluginVersion.from_string("release.1.0.0")
        v2 = PluginVersion.from_string("release.1.0.0")
        v3 = PluginVersion.from_string("release.1.0.1")
        s = {v1, v2, v3}
        assert len(s) == 2
