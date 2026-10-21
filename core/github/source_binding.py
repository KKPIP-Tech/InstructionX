"""插件 GitHub 来源与本地 Key 绑定解析。"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple
from urllib.parse import urlparse

from core.plugin.plugin_registry import (
    PluginRegistry,
    SOURCE_VISIBILITY_PRIVATE,
    SOURCE_VISIBILITY_PUBLIC,
    SOURCE_VISIBILITY_UNKNOWN,
)

from .api_client import GitHubApiClient
from .credential import (
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
)
from .exceptions import (
    GitHubCredentialVaultError,
    GitHubKeyInvalidError,
    GitHubKeyNotFoundError,
    GitHubNetworkError,
    GitHubRateLimitError,
    GitHubRepositoryAccessError,
)
from .key_manager import GitHubKeyManager

_GITHUB_SSH_PATTERN = re.compile(
    r"git@github\.com:([^/]+)/(.+?)(?:\.git)?$")


class GitHubKeyUnavailableReason(str, Enum):
    """插件来源 Key 不可用的原因。"""

    NOT_FOUND = "not_found"
    NOT_GITHUB = "not_github"
    MISSING_BINDING = "missing_binding"
    KEY_DELETED = "key_deleted"
    KEY_INVALID = "key_invalid"
    KEY_UNDECRYPTABLE = "key_undecryptable"
    REPOSITORY_ACCESS = "repository_access"
    TRANSIENT = "transient"


@dataclass(frozen=True, slots=True)
class PluginSourceKeyResolution:
    """插件来源 Key 解析结果。"""

    plugin_id: str
    available: bool
    visibility: str = SOURCE_VISIBILITY_UNKNOWN
    key_id: str = ""
    key_view: Optional[GitHubKeyView] = None
    repository: Optional[GitHubRepositoryInfo] = None
    reason: Optional[GitHubKeyUnavailableReason] = None
    error_message: str = ""

    @property
    def can_rebind(self) -> bool:
        """来源是否支持重新绑定 Key。"""
        return self.reason not in {
            None,
            GitHubKeyUnavailableReason.NOT_FOUND,
            GitHubKeyUnavailableReason.NOT_GITHUB,
        }


class PluginSourceKeyBinder:
    """解析和更新插件来源 Key，保证失败时不破坏旧绑定。"""

    def __init__(
        self,
        registry: PluginRegistry,
        key_manager: GitHubKeyManager,
        api_client: Optional[GitHubApiClient] = None,
    ):
        """初始化来源绑定服务并注入依赖。

        Args:
            registry: 已安装插件注册表。
            key_manager: GitHub Key 管理器。
            api_client: 可选 GitHub API 客户端。
        """
        self._registry = registry
        self._key_manager = key_manager
        self._api_client = api_client or GitHubApiClient()

    def resolve(self, plugin_id: str) -> PluginSourceKeyResolution:
        """验证插件当前来源与绑定 Key 是否可继续使用。

        Args:
            plugin_id: 插件 UUID。

        Returns:
            PluginSourceKeyResolution: 可用状态、可见性、Key 或失败原因。
        """
        record = self._registry.get(plugin_id)
        if record is None:
            return self._failed(
                plugin_id, GitHubKeyUnavailableReason.NOT_FOUND,
                "插件注册记录不存在")
        if record.get("source_type") != "github":
            return self._failed(
                plugin_id, GitHubKeyUnavailableReason.NOT_GITHUB,
                "插件来源不是 GitHub", record)
        parsed = parse_github_source_url(record.get("source_url", ""))
        if parsed is None:
            return self._failed(
                plugin_id, GitHubKeyUnavailableReason.REPOSITORY_ACCESS,
                "插件来源仓库 URL 无效", record)
        visibility = record.get("source_visibility", SOURCE_VISIBILITY_UNKNOWN)
        if visibility == SOURCE_VISIBILITY_PUBLIC:
            return self._resolve_public_source(plugin_id, record, parsed)
        return self._resolve_key_access(plugin_id, record, parsed)

    def _resolve_public_source(self, plugin_id, record, parsed):
        """确认记录为公共的来源当前仍可匿名访问。"""
        try:
            repository = self._api_client.get_repository(
                parsed[0], parsed[1], None)
        except Exception as exc:
            return self._exception_result(plugin_id, record, exc)
        if repository.visibility is GitHubRepositoryVisibility.PRIVATE:
            return self._failed(
                plugin_id,
                GitHubKeyUnavailableReason.MISSING_BINDING,
                "仓库已变为私有，请重新绑定 GitHub Key",
                record,
            )
        return self._available(
            plugin_id, SOURCE_VISIBILITY_PUBLIC, record, "", repository)

    def rebind(
        self, plugin_id: str, new_key_id: str
    ) -> PluginSourceKeyResolution:
        """验证新 Key 后重新绑定，验证失败时不修改旧记录。

        Args:
            plugin_id: 插件 UUID。
            new_key_id: 用户选择的新 Key UUID。

        Returns:
            PluginSourceKeyResolution: 绑定成功或失败详情。
        """
        record = self._registry.get(plugin_id)
        if record is None:
            return self._failed(
                plugin_id, GitHubKeyUnavailableReason.NOT_FOUND,
                "插件注册记录不存在")
        return self._rebind_record(plugin_id, record, new_key_id)

    def _rebind_record(self, plugin_id, record, new_key_id):
        """验证请求并执行实际重新绑定。"""
        parsed = parse_github_source_url(record.get("source_url", ""))
        if parsed is None:
            return self._failed(
                plugin_id, GitHubKeyUnavailableReason.REPOSITORY_ACCESS,
                "插件来源仓库 URL 无效", record)
        try:
            credential = self._key_manager.get_credential(new_key_id)
            repository = self._api_client.get_repository(
                parsed[0], parsed[1], credential)
        except Exception as exc:
            return self._exception_result(plugin_id, record, exc)
        self._key_manager.mark_repository_access_valid(new_key_id)
        return self._save_rebind_result(
            plugin_id, record, new_key_id, repository)

    def _save_rebind_result(
        self, plugin_id, record, new_key_id, repository
    ) -> PluginSourceKeyResolution:
        """验证成功后才持久化新绑定。"""
        if repository.visibility is GitHubRepositoryVisibility.PRIVATE:
            saved = self._registry.set_source_binding(
                plugin_id,
                source_visibility=SOURCE_VISIBILITY_PRIVATE,
                source_key_id=new_key_id,
            )
            if not saved:
                return self._binding_save_failed(plugin_id, record)
            return self._available(
                plugin_id, SOURCE_VISIBILITY_PRIVATE, record,
                new_key_id, repository)
        saved = self._registry.set_source_binding(
            plugin_id,
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
            source_key_id="",
        )
        if not saved:
            return self._binding_save_failed(plugin_id, record)
        return self._available(
            plugin_id, SOURCE_VISIBILITY_PUBLIC, record, "", repository)

    def _binding_save_failed(self, plugin_id, record):
        """返回绑定持久化失败结果。"""
        return self._failed(
            plugin_id,
            GitHubKeyUnavailableReason.TRANSIENT,
            "无法保存新的 GitHub Key 绑定",
            record,
        )

    def clear_binding(self, plugin_id: str) -> bool:
        """解除 Key 绑定；仅在来源已验证为公共时使用。"""
        return self._registry.set_source_binding(
            plugin_id,
            source_visibility=SOURCE_VISIBILITY_PUBLIC,
            source_key_id="",
        )

    def _resolve_key_access(self, plugin_id, record, parsed):
        """使用记录中的 Key 验证目标仓库。"""
        key_id = record.get("source_key_id", "")
        if not key_id:
            return self._failed(
                plugin_id,
                GitHubKeyUnavailableReason.MISSING_BINDING,
                "私有来源缺少绑定的 GitHub Key",
                record,
            )
        try:
            view = self._key_manager.get_key_view(key_id)
            if view.status is GitHubKeyStatus.INVALID:
                raise GitHubKeyInvalidError("绑定的 GitHub Key 已失效")
            repository = self._key_manager.verify_repository_access(
                key_id, parsed[0], parsed[1])
        except Exception as exc:
            return self._exception_result(plugin_id, record, exc)
        self._key_manager.mark_repository_access_valid(key_id)
        visibility = (
            SOURCE_VISIBILITY_PRIVATE
            if repository.visibility is GitHubRepositoryVisibility.PRIVATE
            else SOURCE_VISIBILITY_PUBLIC
        )
        return self._available(
            plugin_id,
            visibility,
            record,
            key_id if visibility == SOURCE_VISIBILITY_PRIVATE else "",
            repository,
        )

    def _exception_result(self, plugin_id, record, exc):
        """把认证异常转换为稳定的不可用原因。"""
        mapping = {
            GitHubKeyNotFoundError: GitHubKeyUnavailableReason.KEY_DELETED,
            GitHubKeyInvalidError: GitHubKeyUnavailableReason.KEY_INVALID,
            GitHubCredentialVaultError: (
                GitHubKeyUnavailableReason.KEY_UNDECRYPTABLE
            ),
            GitHubRepositoryAccessError: (
                GitHubKeyUnavailableReason.REPOSITORY_ACCESS
            ),
            GitHubRateLimitError: GitHubKeyUnavailableReason.TRANSIENT,
            GitHubNetworkError: GitHubKeyUnavailableReason.TRANSIENT,
        }
        reason = mapping.get(type(exc), GitHubKeyUnavailableReason.TRANSIENT)
        return self._failed(plugin_id, reason, str(exc), record)

    @staticmethod
    def _available(
        plugin_id,
        visibility,
        record,
        key_id="",
        repository=None,
    ) -> PluginSourceKeyResolution:
        """构造可用来源解析结果。"""
        return PluginSourceKeyResolution(
            plugin_id=plugin_id,
            available=True,
            visibility=visibility,
            key_id=key_id,
            repository=repository,
        )

    @staticmethod
    def _failed(plugin_id, reason, message, record=None):
        """构造不可用来源解析结果。"""
        return PluginSourceKeyResolution(
            plugin_id=plugin_id,
            available=False,
            visibility=(record or {}).get(
                "source_visibility", SOURCE_VISIBILITY_UNKNOWN),
            key_id=(record or {}).get("source_key_id", ""),
            reason=reason,
            error_message=message,
        )


def parse_github_source_url(url: str) -> Optional[Tuple[str, str]]:
    """从 HTTPS 或 SSH GitHub URL 中解析 owner/repo。"""
    if not url:
        return None
    if url.startswith("git@"):
        match = _GITHUB_SSH_PATTERN.match(url)
        return (match.group(1), match.group(2)) if match else None
    parsed = urlparse(url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        return None
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        return None
    repo = parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    return parts[0], repo
