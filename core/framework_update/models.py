"""框架 GitHub Release 数据模型与版本解析。"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.plugin.plugin_version import PluginVersion
from core.version import APP_VERSION

RELEASE_TAG_PATTERN = re.compile(
    r"^(?:(?P<channel>alpha|beta|pre-release|release|internal)-)?"
    r"v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
)
_GITHUB_ZERO_TIME = datetime.min.replace(tzinfo=timezone.utc)


def parse_release_tag(tag_name: str) -> PluginVersion:
    """把框架 Release Tag 解析为版本对象。

    Args:
        tag_name: 如 ``alpha-v1.2.3`` 或正式版 ``v1.2.3``。

    Returns:
        对应的 ``PluginVersion``。

    Raises:
        ValueError: Tag 不符合框架发布格式时抛出。
    """
    match = RELEASE_TAG_PATTERN.fullmatch(tag_name.strip())
    if match is None:
        raise ValueError(f"无效的框架 Release Tag: {tag_name}")
    channel = match.group("channel") or "release"
    version_text = (
        f"{channel}.{match.group('major')}."
        f"{match.group('minor')}.{match.group('patch')}"
    )
    return PluginVersion.from_string(version_text)


def _parse_github_time(value: Any) -> Optional[datetime]:
    """解析 GitHub ISO 时间；无效值返回 None。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass(frozen=True, slots=True)
class FrameworkRelease:
    """一个可供用户浏览的 GitHub Release。"""

    release_id: int
    name: str
    tag_name: str
    version: Optional[PluginVersion]
    prerelease: bool
    published_at: datetime
    body: str
    html_url: str

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "FrameworkRelease":
        """从 GitHub API 条目构造 Release；无法解析的 Tag 保留为无版本。"""
        tag_name = str(data.get("tag_name") or "")
        try:
            version = parse_release_tag(tag_name)
        except ValueError:
            version = None
        published_at = (
            _parse_github_time(data.get("published_at"))
            or _parse_github_time(data.get("created_at"))
            or _GITHUB_ZERO_TIME
        )
        return cls(
            release_id=int(data.get("id") or 0),
            name=str(data.get("name") or tag_name),
            tag_name=tag_name,
            version=version,
            prerelease=bool(data.get("prerelease", False)),
            published_at=published_at,
            body=str(data.get("body") or ""),
            html_url=str(data.get("html_url") or ""),
        )


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    """按发布时间倒序排列的 Release 时间线及当前版本定位。"""

    releases: tuple[FrameworkRelease, ...]
    current_release_id: Optional[int]
    current_version: PluginVersion = APP_VERSION

    @property
    def latest_release(self) -> Optional[FrameworkRelease]:
        """返回发布时间最新的 Release；空列表返回 None。"""
        return self.releases[0] if self.releases else None

    @property
    def has_update(self) -> bool:
        """最新发布的 Release 是否高于当前版本。"""
        latest = self.latest_release
        return bool(latest and self.can_update(latest.release_id))

    def can_update(self, release_id: int) -> bool:
        """判断指定 Release 是否为可识别且高于当前版本的版本。"""
        for release in self.releases:
            if release.release_id == release_id:
                return bool(release.version and release.version > self.current_version)
        return False
