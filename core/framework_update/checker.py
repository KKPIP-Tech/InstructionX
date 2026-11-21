"""框架 GitHub Release 检查器。"""

import logging
from typing import Optional

from core.github import GitHubApiClient
from core.plugin.plugin_version import PluginVersion
from core.version import APP_VERSION

from .models import FrameworkRelease, UpdateCheckResult

logger = logging.getLogger(__name__)

FRAMEWORK_REPOSITORY_OWNER = "KKPIP-Tech"
FRAMEWORK_REPOSITORY_NAME = "InstructionX"


class FrameworkUpdateChecker:
    """读取官方仓库全部已发布 Release 并生成版本时间线。"""

    def __init__(
        self,
        api_client: Optional[GitHubApiClient] = None,
        current_version: Optional[PluginVersion] = None,
    ) -> None:
        """初始化检查器，参数用于测试注入，不发起网络请求。"""
        self._api_client = api_client or GitHubApiClient()
        self._current_version = current_version or APP_VERSION

    def check(self) -> UpdateCheckResult:
        """手动触发一次检查，排除 Draft 并按发布时间倒序排列。

        Returns:
            包含全部已发布 Release 和当前版本位置的检查结果。
        """
        api_items = self._api_client.list_all_releases(
            FRAMEWORK_REPOSITORY_OWNER,
            FRAMEWORK_REPOSITORY_NAME,
        )
        releases = [
            self._build_release(item)
            for item in api_items
            if isinstance(item, dict) and not bool(item.get("draft", False))
        ]
        releases.sort(key=lambda item: (item.published_at, item.release_id), reverse=True)
        current_id = self._find_current_release(releases)
        return UpdateCheckResult(
            releases=tuple(releases),
            current_release_id=current_id,
            current_version=self._current_version,
        )

    @staticmethod
    def _build_release(item: dict) -> FrameworkRelease:
        """构造单个 Release，并记录无法参与版本比较的 Tag。"""
        release = FrameworkRelease.from_api(item)
        if release.version is None:
            logger.warning("Release Tag 无法解析为框架版本，仅用于列表展示: %s", release.tag_name)
        return release

    def _find_current_release(self, releases: list[FrameworkRelease]) -> Optional[int]:
        """按解析后的版本查找当前 Release，找不到时返回 None。"""
        for release in releases:
            if release.version == self._current_version:
                return release.release_id
        return None
