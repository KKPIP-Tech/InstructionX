"""框架 Release 模型与检查器测试。"""

import importlib
from unittest.mock import MagicMock

import pytest

from core.version import APP_VERSION


@pytest.fixture
def models():
    """加载待实现的 Release 模型模块。"""
    return importlib.import_module("core.framework_update.models")


@pytest.fixture
def checker_module():
    """加载待实现的更新检查器模块。"""
    return importlib.import_module("core.framework_update.checker")


def _api_release(
    release_id: int,
    tag: str,
    published_at: str,
    *,
    prerelease: bool = False,
    draft: bool = False,
) -> dict:
    """构造 GitHub Release API 条目。"""
    return {
        "id": release_id,
        "name": f"Release {release_id}",
        "tag_name": tag,
        "published_at": published_at,
        "created_at": "2026-01-01T00:00:00Z",
        "prerelease": prerelease,
        "draft": draft,
        "body": f"Notes {release_id}",
        "html_url": f"https://github.com/KKPIP-Tech/InstructionX/releases/{release_id}",
    }


class TestReleaseTag:
    """验证框架 Release Tag 与版本对象的转换。"""

    @pytest.mark.parametrize(
        ("tag", "expected"),
        [
            ("alpha-v1.2.3", "alpha.1.2.3"),
            ("beta-v2.0.0", "beta.2.0.0"),
            ("pre-release-v1.3.0", "pre-release.1.3.0"),
            ("release-v2.1.0", "release.2.1.0"),
            ("internal-v0.0.9", "internal.0.0.9"),
            ("v1.4.0", "release.1.4.0"),
        ],
    )
    def test_parses_supported_tags(self, models, tag, expected):
        """支持的 Tag 应转换为既有 PluginVersion。"""
        assert models.parse_release_tag(tag).to_string() == expected

    @pytest.mark.parametrize("tag", ["main", "alpha-v1.2", "v1.2.3-beta", ""])
    def test_rejects_unsupported_tags(self, models, tag):
        """无法识别的 Tag 必须明确拒绝。"""
        with pytest.raises(ValueError, match="Release Tag"):
            models.parse_release_tag(tag)


class TestFrameworkUpdateChecker:
    """验证 Release 保留、时间排序和当前版本定位。"""

    def test_sorts_by_time_and_marks_current(self, models, checker_module):
        """时间线应 newest-first，而不是按版本号排序。"""
        api = MagicMock()
        api.list_all_releases.return_value = [
            _api_release(1, "alpha-v1.0.0", "2026-03-01T00:00:00Z"),
            _api_release(2, "alpha-v1.1.4", "2026-02-01T00:00:00Z"),
            _api_release(3, "alpha-v0.9.0", "2026-04-01T00:00:00Z"),
            _api_release(4, "alpha-v9.0.0", "2026-01-01T00:00:00Z", draft=True),
        ]
        checker = checker_module.FrameworkUpdateChecker(api_client=api)

        result = checker.check()

        assert [item.release_id for item in result.releases] == [3, 1, 2]
        assert result.latest_release.release_id == 3
        assert result.current_release_id == 2
        assert result.releases[0].version < APP_VERSION
        assert not result.has_update

    def test_keeps_prerelease_and_unparseable_release(self, models, checker_module):
        """Pre-release 与非标准 Tag 均应展示，不能静默过滤。"""
        api = MagicMock()
        api.list_all_releases.return_value = [
            _api_release(1, "nightly", "2026-03-01T00:00:00Z", prerelease=True),
            _api_release(2, "alpha-v1.1.4", "2026-02-01T00:00:00Z", prerelease=True),
        ]
        result = checker_module.FrameworkUpdateChecker(api_client=api).check()

        assert len(result.releases) == 2
        assert result.releases[0].version is None
        assert result.releases[0].prerelease
        assert result.current_release_id == 2
        assert not result.can_update(1)

    def test_uses_created_at_when_published_at_missing(self, models, checker_module):
        """缺少发布时间时应回退到创建时间。"""
        api = MagicMock()
        first = _api_release(1, "alpha-v1.0.0", "2026-03-01T00:00:00Z")
        first["published_at"] = None
        first["created_at"] = "2026-05-01T00:00:00Z"
        second = _api_release(2, "alpha-v1.1.4", "2026-02-01T00:00:00Z")
        api.list_all_releases.return_value = [second, first]

        result = checker_module.FrameworkUpdateChecker(api_client=api).check()

        assert result.releases[0].release_id == 1

    def test_update_available_only_for_newer_version(self, models, checker_module):
        """只有高于当前版本的 Release 才允许更新。"""
        api = MagicMock()
        api.list_all_releases.return_value = [
            _api_release(1, "alpha-v1.2.0", "2026-03-01T00:00:00Z"),
            _api_release(2, "alpha-v1.1.4", "2026-02-01T00:00:00Z"),
            _api_release(3, "alpha-v1.0.0", "2026-01-01T00:00:00Z"),
        ]
        result = checker_module.FrameworkUpdateChecker(api_client=api).check()

        assert result.has_update
        assert result.can_update(1)
        assert not result.can_update(2)
        assert not result.can_update(3)

    def test_current_version_may_be_absent(self, models, checker_module):
        """当前版本没有对应 Release 时应明确返回空定位。"""
        api = MagicMock()
        api.list_all_releases.return_value = []

        result = checker_module.FrameworkUpdateChecker(api_client=api).check()

        assert result.releases == ()
        assert result.latest_release is None
        assert result.current_release_id is None
        assert not result.has_update
