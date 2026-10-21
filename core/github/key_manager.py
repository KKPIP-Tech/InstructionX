"""GitHub Key 验证、解析与生命周期管理。"""

import os
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from .api_client import GitHubApiClient
from .credential import (
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubKeyVerificationResult,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubTokenKind,
)
from .exceptions import (
    GitHubKeyInvalidError,
    GitHubKeyNotFoundError,
    GitHubCredentialVaultError,
)
from .key_store import (
    MAX_GITHUB_TOKEN_LENGTH,
    GitHubKeyStore,
)
from .secret_vault import SecretVault, create_default_secret_vault

ENVIRONMENT_TOKEN_NAME = "INSTRUCTIONX_GITHUB_TOKEN"
ENVIRONMENT_KEY_ID = "environment:github-token"
ENVIRONMENT_KEY_NAME = "环境变量 GitHub Token"
NO_KEY_ID = "no-key"


class GitHubKeyManager:
    """管理用户 GitHub Key，并为仓库操作解析有效凭据。"""

    _instance: Optional["GitHubKeyManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """返回全进程共享的管理器实例。"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        config_dir: Optional[Path] = None,
        *,
        vault: Optional[SecretVault] = None,
        store: Optional[GitHubKeyStore] = None,
        api_client: Optional[GitHubApiClient] = None,
        environment_reader: Optional[Callable[[str], str]] = None,
        logger: Any = None,
    ):
        """初始化 Key 管理器；重复构造保留已注入依赖。"""
        if getattr(self, "_initialized", False):
            return
        selected_vault = vault or create_default_secret_vault()
        self._store = store or GitHubKeyStore(
            config_dir, selected_vault, logger=logger)
        self._api_client = api_client or GitHubApiClient()
        self._environment_reader = environment_reader or os.environ.get
        self._initialized = True

    def list_keys(self) -> list[GitHubKeyView]:
        """返回已配置 Key 和只读环境变量 Key。"""
        views = self._store.list_views()
        environment = self._environment_token()
        if environment:
            views.append(GitHubKeyView(
                id=ENVIRONMENT_KEY_ID,
                name=ENVIRONMENT_KEY_NAME,
                account_login="",
                token_kind=GitHubTokenKind.UNKNOWN,
                status=GitHubKeyStatus.UNTESTED,
                expires_at=None,
                expiration_source=GitHubExpirationSource.UNAVAILABLE,
                oauth_scopes=(),
                last_verified_at="",
                last_error_code="",
                last_error_message="",
                is_environment=True,
            ))
        return views

    def add_key(self, name: str, token: str) -> GitHubKeyView:
        """验证并添加新 Key；无效 Token 不写入配置。"""
        self._ensure_name_available(name)
        clean_token = self._validated_token(token)
        candidate = GitHubCredential(
            key_id="pending",
            key_name=name.strip(),
            token=clean_token,
        )
        identity = self._api_client.get_authenticated_user(candidate)
        return self._store.add_key(
            name,
            token,
            account_login=identity.account_login,
            token_kind=identity.token_kind,
            status=GitHubKeyStatus.VALID,
            expires_at=identity.expires_at,
            expiration_source=identity.expiration_source,
            oauth_scopes=identity.oauth_scopes,
        )

    def _ensure_name_available(self, name: str) -> None:
        """在联网验证前拒绝重复名称。"""
        target = name.strip().casefold()
        if any(view.name.casefold() == target for view in self._store.list_views()):
            raise ValueError("GitHub Key 名称已存在")

    def rename_key(self, key_id: str, name: str) -> GitHubKeyView:
        """重命名本地 Key。"""
        self._reject_environment_mutation(key_id)
        return self._store.rename_key(key_id, name)

    def replace_token(self, key_id: str, token: str) -> GitHubKeyView:
        """验证并替换现有 Key 的 Token。"""
        self._reject_environment_mutation(key_id)
        clean_token = self._validated_token(token)
        current = self._store.get_view(key_id)
        candidate = GitHubCredential(key_id, current.name, clean_token)
        identity = self._api_client.get_authenticated_user(candidate)
        return self._store.replace_token(
            key_id,
            clean_token,
            account_login=identity.account_login,
            token_kind=identity.token_kind,
            status=GitHubKeyStatus.VALID,
            expires_at=identity.expires_at,
            expiration_source=identity.expiration_source,
            oauth_scopes=identity.oauth_scopes,
        )

    @staticmethod
    def _validated_token(token: str) -> str:
        """返回规范化 Token，拒绝空值和异常长度。"""
        clean_token = token.strip()
        if not clean_token or len(clean_token) > MAX_GITHUB_TOKEN_LENGTH:
            raise ValueError("GitHub Token 为空或长度异常")
        return clean_token

    def verify_key(self, key_id: str) -> GitHubKeyVerificationResult:
        """重新验证 Key，并持久化成功或失败状态。"""
        if key_id == ENVIRONMENT_KEY_ID:
            return self._verify_environment_key()
        try:
            credential = self.get_credential(key_id)
            identity = self._api_client.get_authenticated_user(credential)
        except (GitHubKeyInvalidError, GitHubCredentialVaultError) as exc:
            return self._mark_verification_failed(key_id, exc)
        view = self._store.update_verification(
            key_id,
            account_login=identity.account_login,
            token_kind=identity.token_kind,
            status=GitHubKeyStatus.VALID,
            expires_at=identity.expires_at,
            expiration_source=identity.expiration_source,
            oauth_scopes=identity.oauth_scopes,
        )
        return GitHubKeyVerificationResult(success=True, view=view)

    def verify_repository_access(
        self, key_id: str, owner: str, repo: str
    ) -> GitHubRepositoryInfo:
        """验证 Key 是否可访问目标仓库。"""
        credential = self.get_credential(key_id)
        return self._api_client.get_repository(owner, repo, credential)

    def mark_repository_access_valid(self, key_id: str) -> None:
        """把成功访问私有仓库的 Key 标记为有效。

        环境变量 Key 无本地记录，因此只验证不修改。

        Args:
            key_id: 刚完成仓库权限验证的 Key UUID。
        """
        if key_id == ENVIRONMENT_KEY_ID:
            return
        current = self._store.get_view(key_id)
        self._store.update_verification(
            key_id,
            account_login=current.account_login,
            token_kind=current.token_kind,
            status=GitHubKeyStatus.VALID,
            expires_at=current.expires_at,
            expiration_source=current.expiration_source,
            oauth_scopes=current.oauth_scopes,
        )

    def delete_key(self, key_id: str) -> None:
        """删除本地 Key。"""
        self._reject_environment_mutation(key_id)
        self._store.remove_key(key_id)

    def set_default_key(self, key_id: str) -> None:
        """设置默认 Key；空串表示清除。"""
        if key_id:
            self._reject_environment_mutation(key_id)
        self._store.set_default(key_id)

    def get_default_key_id(self) -> str:
        """返回默认 Key ID。"""
        return self._store.get_default_key_id()

    def get_key_view(self, key_id: str) -> GitHubKeyView:
        """返回指定 Key 的安全展示数据。"""
        if key_id == ENVIRONMENT_KEY_ID:
            if not self._environment_token():
                raise GitHubKeyNotFoundError("环境变量 GitHub Token 不存在")
            return next(
                view for view in self.list_keys()
                if view.id == ENVIRONMENT_KEY_ID
            )
        return self._store.get_view(key_id)

    def get_credential(self, key_id: str) -> GitHubCredential:
        """解析指定 Key 为仅存在于内存的凭据。"""
        if key_id == NO_KEY_ID:
            raise GitHubKeyNotFoundError("未选择 GitHub Key")
        if key_id == ENVIRONMENT_KEY_ID:
            token = self._environment_token()
            if not token:
                raise GitHubKeyNotFoundError("环境变量 GitHub Token 不存在")
            return GitHubCredential(
                ENVIRONMENT_KEY_ID, ENVIRONMENT_KEY_NAME, token,
                is_environment=True)
        view = self._store.get_view(key_id)
        return GitHubCredential(
            key_id=view.id,
            key_name=view.name,
            token=self._store.get_secret(key_id),
            account_login=view.account_login,
        )

    def _verify_environment_key(self) -> GitHubKeyVerificationResult:
        """验证环境变量 Token，但不持久化其状态。"""
        credential = self.get_credential(ENVIRONMENT_KEY_ID)
        identity = self._api_client.get_authenticated_user(credential)
        view = GitHubKeyView(
            id=ENVIRONMENT_KEY_ID,
            name=ENVIRONMENT_KEY_NAME,
            account_login=identity.account_login,
            token_kind=identity.token_kind,
            status=GitHubKeyStatus.VALID,
            expires_at=identity.expires_at,
            expiration_source=identity.expiration_source,
            oauth_scopes=identity.oauth_scopes,
            last_verified_at="",
            last_error_code="",
            last_error_message="",
            is_environment=True,
        )
        return GitHubKeyVerificationResult(success=True, view=view)

    def _mark_verification_failed(
        self, key_id: str, error: Exception
    ) -> GitHubKeyVerificationResult:
        """记录无效 Key 状态并返回可展示结果。"""
        current = self._store.get_view(key_id)
        view = self._store.update_verification(
            key_id,
            account_login=current.account_login,
            token_kind=current.token_kind,
            status=GitHubKeyStatus.INVALID,
            expires_at=current.expires_at,
            expiration_source=current.expiration_source,
            oauth_scopes=current.oauth_scopes,
            error_code=error.__class__.__name__,
            error_message=str(error),
        )
        return GitHubKeyVerificationResult(
            success=False,
            view=view,
            error_code=error.__class__.__name__,
            error_message=str(error),
        )

    def _environment_token(self) -> str:
        """读取兼容环境变量中的 Token。"""
        return (self._environment_reader(ENVIRONMENT_TOKEN_NAME) or "").strip()

    @staticmethod
    def _reject_environment_mutation(key_id: str) -> None:
        """拒绝对只读环境变量 Key 执行修改。"""
        if key_id == ENVIRONMENT_KEY_ID:
            raise ValueError("环境变量 GitHub Token 为只读，不能在此修改")


def get_github_key_manager() -> GitHubKeyManager:
    """获取 GitHubKeyManager 单例。"""
    return GitHubKeyManager()
