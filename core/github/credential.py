"""GitHub PAT 与仓库访问结果的数据模型。"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class GitHubTokenKind(str, Enum):
    """GitHub PAT 类型。"""

    FINE_GRAINED = "fine_grained"
    CLASSIC = "classic"
    UNKNOWN = "unknown"


class GitHubKeyStatus(str, Enum):
    """本地记录的 Key 验证状态。"""

    UNTESTED = "untested"
    VALID = "valid"
    INVALID = "invalid"


class GitHubRepositoryVisibility(str, Enum):
    """GitHub 仓库可见性。"""

    PUBLIC = "public"
    PRIVATE = "private"
    UNKNOWN = "unknown"


class GitHubExpirationSource(str, Enum):
    """Key 过期时间的来源。"""

    GITHUB_HEADER = "github_header"
    UNAVAILABLE = "unavailable"


@dataclass(slots=True)
class GitHubKeyRecord:
    """持久化在本地配置中的单个 GitHub Key。

    ``encrypted_token`` 只能保存 SecretVault 输出的密文；
    任何日志和 UI 数据模型都不得暴露该字段。
    """

    id: str
    name: str
    encrypted_token: str
    account_login: str = ""
    token_kind: GitHubTokenKind = GitHubTokenKind.UNKNOWN
    status: GitHubKeyStatus = GitHubKeyStatus.UNTESTED
    expires_at: Optional[str] = None
    expiration_source: GitHubExpirationSource = (
        GitHubExpirationSource.UNAVAILABLE
    )
    oauth_scopes: tuple[str, ...] = ()
    created_at: str = ""
    updated_at: str = ""
    last_verified_at: str = ""
    last_error_code: str = ""
    last_error_message: str = ""


@dataclass(frozen=True, slots=True)
class GitHubKeyView:
    """可安全传递给 UI 的 Key 展示数据，不包含 Token 或密文。"""

    id: str
    name: str
    account_login: str
    token_kind: GitHubTokenKind
    status: GitHubKeyStatus
    expires_at: Optional[str]
    expiration_source: GitHubExpirationSource
    oauth_scopes: tuple[str, ...]
    last_verified_at: str
    last_error_code: str
    last_error_message: str
    is_default: bool = False
    is_environment: bool = False


@dataclass(slots=True)
class GitHubCredential:
    """一次 GitHub 操作期间使用的内存凭据。

    ``token`` 不进入默认 repr，防止异常日志意外泄漏。
    """

    key_id: str
    key_name: str
    token: str
    account_login: str = ""
    is_environment: bool = False

    def __repr__(self) -> str:
        """返回不含 Token 的调试表示。"""
        return (
            f"GitHubCredential(key_id={self.key_id!r}, "
            f"key_name={self.key_name!r}, account_login={self.account_login!r})"
        )


@dataclass(frozen=True, slots=True)
class GitHubAuthIdentity:
    """GitHub Token 身份验证结果。"""

    account_login: str
    token_kind: GitHubTokenKind
    expires_at: Optional[str] = None
    expiration_source: GitHubExpirationSource = (
        GitHubExpirationSource.UNAVAILABLE
    )
    oauth_scopes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GitHubRepositoryInfo:
    """GitHub 仓库元数据及本次访问所用凭据的展示信息。"""

    owner: str
    repo: str
    visibility: GitHubRepositoryVisibility
    default_branch: str = ""
    can_pull: bool = False
    auth_key_id: str = ""
    auth_key_name: str = ""
    auth_account_login: str = ""
    raw_permissions: Optional[Dict[str, Any]] = None


@dataclass(frozen=True, slots=True)
class GitHubKeyVerificationResult:
    """一次 Key 验证的最终状态。"""

    success: bool
    view: GitHubKeyView
    error_code: str = ""
    error_message: str = ""
