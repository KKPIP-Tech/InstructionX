"""GitHub 私有仓库访问子系统。

集中提供 GitHub PAT 的安全存储、凭据解析和 API 访问能力，
避免插件安装器直接处理明文 Token。
"""

from .credential import (
    GitHubAuthIdentity,
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyRecord,
    GitHubKeyStatus,
    GitHubKeyVerificationResult,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
)
from .api_client import GitHubApiClient
from .exceptions import (
    GitHubCredentialVaultError,
    GitHubKeyInvalidError,
    GitHubKeyNotFoundError,
    GitHubNetworkError,
    GitHubRateLimitError,
    GitHubRepositoryAccessError,
)
from .key_store import (
    MAX_GITHUB_KEY_NAME_LENGTH,
    MAX_GITHUB_TOKEN_LENGTH,
    GitHubKeyStore,
)
from .key_manager import (
    ENVIRONMENT_KEY_ID,
    ENVIRONMENT_TOKEN_NAME,
    NO_KEY_ID,
    GitHubKeyManager,
    get_github_key_manager,
)
from .secret_vault import (
    DpapiSecretVault,
    InMemorySecretVault,
    SecretVault,
    create_default_secret_vault,
)
from .source_binding import (
    GitHubKeyUnavailableReason,
    PluginSourceKeyBinder,
    PluginSourceKeyResolution,
    parse_github_source_url,
)

__all__ = [
    "DpapiSecretVault",
    "ENVIRONMENT_KEY_ID",
    "ENVIRONMENT_TOKEN_NAME",
    "GitHubApiClient",
    "GitHubAuthIdentity",
    "GitHubCredential",
    "GitHubCredentialVaultError",
    "GitHubExpirationSource",
    "GitHubKeyInvalidError",
    "GitHubKeyNotFoundError",
    "GitHubKeyRecord",
    "GitHubKeyStatus",
    "GitHubKeyStore",
    "GitHubKeyManager",
    "GitHubKeyVerificationResult",
    "GitHubKeyUnavailableReason",
    "GitHubKeyView",
    "GitHubNetworkError",
    "GitHubRateLimitError",
    "GitHubRepositoryAccessError",
    "GitHubRepositoryInfo",
    "GitHubRepositoryVisibility",
    "GitHubTokenKind",
    "InMemorySecretVault",
    "MAX_GITHUB_KEY_NAME_LENGTH",
    "MAX_GITHUB_TOKEN_LENGTH",
    "NO_KEY_ID",
    "PluginSourceKeyBinder",
    "PluginSourceKeyResolution",
    "SecretVault",
    "create_default_secret_vault",
    "get_github_key_manager",
    "parse_github_source_url",
]
