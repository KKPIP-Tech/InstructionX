"""GitHub Key 本地持久化存储。"""

import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from utils.logging_tools import LoggerManager, get_name

from .credential import (
    GitHubExpirationSource,
    GitHubKeyRecord,
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubTokenKind,
)
from .exceptions import GitHubCredentialVaultError, GitHubKeyNotFoundError
from .secret_vault import SecretVault

KEY_STORE_SCHEMA_VERSION = 1
KEY_STORE_FILE_NAME = "github_keys.json"
MAX_GITHUB_KEY_NAME_LENGTH = 80
MAX_GITHUB_TOKEN_LENGTH = 4096
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class GitHubKeyStore:
    """管理 ``config/github_keys.json`` 中的 Key 元数据与加密凭据。"""

    def __init__(
        self,
        config_dir: Optional[Path],
        vault: SecretVault,
        logger: Any = None,
    ):
        """初始化 Key 存储。

        Args:
            config_dir: 配置目录；None 使用项目根目录的 ``config/``。
            vault: 凭据加解密后端。
            logger: 可注入日志器；None 时使用框架 LoggerManager。
        """
        self.config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / KEY_STORE_FILE_NAME
        self._vault = vault
        self._logger = logger or LoggerManager()
        self._records: dict[str, GitHubKeyRecord] = {}
        self._default_key_id = ""
        self._loaded = False

    def load(self) -> None:
        """加载配置；文件不存在时初始化空存储。"""
        if self._loaded:
            return
        if not self.config_file.exists():
            self._records = {}
            self._default_key_id = ""
            self._loaded = True
            return
        data = self._read_json()
        self._validate_schema_version(data)
        try:
            self._apply_loaded_data(data)
        except (KeyError, TypeError, ValueError) as exc:
            self._logger.error(
                get_name(), f"GitHub Key 配置内容无效，已重建: {exc}")
            self._backup_corrupt_file()
            self._records = {}
            self._default_key_id = ""
        self._loaded = True

    def list_views(self) -> list[GitHubKeyView]:
        """返回不含 Token 或密文的 Key 展示列表。"""
        self.load()
        ordered = sorted(self._records.values(), key=lambda record: record.name.casefold())
        return [self._to_view(record) for record in ordered]

    def get_view(self, key_id: str) -> GitHubKeyView:
        """按 Key ID 获取展示数据。

        Raises:
            GitHubKeyNotFoundError: Key 不存在。
        """
        return self._to_view(self._get_record(key_id))

    def get_default_key_id(self) -> str:
        """返回默认 Key ID；未设置时为空串。"""
        self.load()
        return self._default_key_id

    def add_key(
        self,
        name: str,
        token: str,
        *,
        account_login: str = "",
        token_kind: GitHubTokenKind = GitHubTokenKind.UNKNOWN,
        status: GitHubKeyStatus = GitHubKeyStatus.UNTESTED,
        expires_at: Optional[str] = None,
        expiration_source: GitHubExpirationSource = GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes: Iterable[str] = (),
    ) -> GitHubKeyView:
        """添加 Key 并加密 Token。"""
        self.load()
        clean_name = self._validate_name(name)
        self._validate_token(token)
        encrypted = self._vault.encrypt(token.strip())
        now = self._now()
        record = GitHubKeyRecord(
            id=str(uuid.uuid4()),
            name=clean_name,
            encrypted_token=encrypted,
            account_login=account_login,
            token_kind=token_kind,
            status=status,
            expires_at=expires_at,
            expiration_source=expiration_source,
            oauth_scopes=tuple(oauth_scopes),
            created_at=now,
            updated_at=now,
            last_verified_at=now if status is not GitHubKeyStatus.UNTESTED else "",
        )
        previous = self._snapshot()
        self._records[record.id] = record
        self._commit(previous)
        return self._to_view(record)

    def rename_key(self, key_id: str, name: str) -> GitHubKeyView:
        """重命名 Key，保持 ID 与绑定关系不变。"""
        self.load()
        record = self._get_record(key_id)
        previous = self._snapshot()
        record.name = self._validate_name(name, exclude_id=key_id)
        record.updated_at = self._now()
        self._commit(previous)
        return self._to_view(record)

    def replace_token(
        self,
        key_id: str,
        token: str,
        *,
        account_login: str = "",
        token_kind: GitHubTokenKind = GitHubTokenKind.UNKNOWN,
        status: GitHubKeyStatus = GitHubKeyStatus.UNTESTED,
        expires_at: Optional[str] = None,
        expiration_source: GitHubExpirationSource = GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes: Iterable[str] = (),
    ) -> GitHubKeyView:
        """替换 Key 的加密 Token 并更新验证元数据。"""
        self.load()
        record = self._get_record(key_id)
        previous = self._snapshot()
        self._validate_token(token)
        record.encrypted_token = self._vault.encrypt(token.strip())
        self._apply_verification(
            record, account_login, token_kind, status, expires_at,
            expiration_source, tuple(oauth_scopes))
        self._commit(previous)
        return self._to_view(record)

    def update_verification(
        self,
        key_id: str,
        *,
        account_login: str,
        token_kind: GitHubTokenKind,
        status: GitHubKeyStatus,
        expires_at: Optional[str],
        expiration_source: GitHubExpirationSource,
        oauth_scopes: Iterable[str],
        error_code: str = "",
        error_message: str = "",
    ) -> GitHubKeyView:
        """更新 Key 的验证结果，不修改 Token。"""
        self.load()
        record = self._get_record(key_id)
        previous = self._snapshot()
        self._apply_verification(
            record, account_login, token_kind, status, expires_at,
            expiration_source, tuple(oauth_scopes))
        record.last_error_code = error_code
        record.last_error_message = error_message
        self._commit(previous)
        return self._to_view(record)

    def set_default(self, key_id: str) -> None:
        """设置默认 Key；空串表示清除默认 Key。"""
        self.load()
        if key_id:
            self._get_record(key_id)
        previous = self._snapshot()
        self._default_key_id = key_id
        self._commit(previous)

    def remove_key(self, key_id: str) -> None:
        """删除指定 Key；默认 Key 被删除时同步清空默认值。"""
        self.load()
        self._get_record(key_id)
        previous = self._snapshot()
        del self._records[key_id]
        if self._default_key_id == key_id:
            self._default_key_id = ""
        self._commit(previous)

    def get_secret(self, key_id: str) -> str:
        """解密并返回指定 Key；仅供凭据解析层调用。"""
        record = self._get_record(key_id)
        return self._vault.decrypt(record.encrypted_token)

    def _read_json(self) -> dict:
        """读取并校验 JSON 顶层结构，损坏时备份并重建。"""
        try:
            with open(self.config_file, "r", encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
                raise ValueError("GitHub Key 配置结构无效")
            return data
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            self._logger.error(get_name(), f"读取 GitHub Key 配置失败，已重建: {exc}")
            self._backup_corrupt_file()
            return {"version": KEY_STORE_SCHEMA_VERSION, "default_key_id": "", "keys": []}

    def _apply_loaded_data(self, data: dict) -> None:
        """把 JSON 数据转换为内部记录并校验唯一性。"""
        records: dict[str, GitHubKeyRecord] = {}
        names: set[str] = set()
        for item in data.get("keys", []):
            record = self._record_from_dict(item)
            name_key = record.name.casefold()
            if record.id in records or name_key in names:
                raise ValueError("GitHub Key 配置包含重复 ID 或名称")
            records[record.id] = record
            names.add(name_key)
        self._records = records
        default_id = str(data.get("default_key_id", ""))
        self._default_key_id = default_id if default_id in records else ""

    def _record_from_dict(self, item: dict) -> GitHubKeyRecord:
        """从单个 JSON 条目构造记录。"""
        if not isinstance(item, dict):
            raise ValueError("GitHub Key 条目必须是对象")
        return GitHubKeyRecord(
            id=str(item["id"]),
            name=str(item["name"]),
            encrypted_token=str(item["encrypted_token"]),
            account_login=str(item.get("account_login", "")),
            token_kind=GitHubTokenKind(item.get("token_kind", "unknown")),
            status=GitHubKeyStatus(item.get("status", "untested")),
            expires_at=item.get("expires_at"),
            expiration_source=GitHubExpirationSource(
                item.get("expiration_source", "unavailable")),
            oauth_scopes=tuple(item.get("oauth_scopes", [])),
            created_at=str(item.get("created_at", "")),
            updated_at=str(item.get("updated_at", "")),
            last_verified_at=str(item.get("last_verified_at", "")),
            last_error_code=str(item.get("last_error_code", "")),
            last_error_message=str(item.get("last_error_message", "")),
        )

    def _save(self) -> None:
        """原子保存所有 Key 元数据与密文。"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "version": KEY_STORE_SCHEMA_VERSION,
            "default_key_id": self._default_key_id,
            "keys": [self._record_to_dict(record)
                     for record in sorted(self._records.values(), key=lambda r: r.name.casefold())],
        }
        temp_file = self.config_file.with_suffix(".json.tmp")
        try:
            with open(temp_file, "w", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=4)
            os.replace(temp_file, self.config_file)
        except (OSError, TypeError, ValueError) as exc:
            self._cleanup_temp_file(temp_file)
            raise GitHubCredentialVaultError("保存 GitHub Key 配置失败") from exc

    def _snapshot(self) -> tuple[dict[str, GitHubKeyRecord], str]:
        """复制当前内存状态，供保存失败时回滚。"""
        return deepcopy(self._records), self._default_key_id

    def _commit(self, previous) -> None:
        """保存状态；失败时恢复内存快照并重新抛出异常。"""
        try:
            self._save()
        except Exception:
            self._records, self._default_key_id = previous
            raise

    def _backup_corrupt_file(self) -> None:
        """以时间戳备份损坏配置文件。"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup = self.config_file.with_name(
            f"{self.config_file.name}.corrupt-{timestamp}.bak")
        try:
            os.replace(self.config_file, backup)
        except OSError as exc:
            self._logger.error(get_name(), f"备份损坏 GitHub Key 配置失败: {exc}")

    def _validate_name(self, name: str, exclude_id: str = "") -> str:
        """校验 Key 名称非空且不与其他 Key 重名。"""
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("GitHub Key 名称不能为空")
        if len(clean_name) > MAX_GITHUB_KEY_NAME_LENGTH:
            raise ValueError(
                f"GitHub Key 名称不能超过 {MAX_GITHUB_KEY_NAME_LENGTH} 个字符")
        for record in self._records.values():
            if record.id != exclude_id and record.name.casefold() == clean_name.casefold():
                raise ValueError("GitHub Key 名称已存在")
        return clean_name

    @staticmethod
    def _validate_token(token: str) -> None:
        """校验 Token 非空且不超过安全长度上限。"""
        clean_token = token.strip()
        if not clean_token:
            raise GitHubCredentialVaultError("GitHub Token 不能为空")
        if len(clean_token) > MAX_GITHUB_TOKEN_LENGTH:
            raise GitHubCredentialVaultError("GitHub Token 长度异常")

    def _validate_schema_version(self, data: dict) -> None:
        """拒绝用旧代码覆盖未来版本的 Key 配置。"""
        try:
            version = int(data.get("version", KEY_STORE_SCHEMA_VERSION))
        except (TypeError, ValueError) as exc:
            raise GitHubCredentialVaultError("GitHub Key schema 版本无效") from exc
        if version > KEY_STORE_SCHEMA_VERSION:
            raise GitHubCredentialVaultError(
                "GitHub Key 配置由更高版本程序创建，已拒绝覆盖")

    def _get_record(self, key_id: str) -> GitHubKeyRecord:
        """按 ID 获取内部记录。"""
        self.load()
        try:
            return self._records[key_id]
        except KeyError as exc:
            raise GitHubKeyNotFoundError(f"GitHub Key 不存在: {key_id}") from exc

    def _apply_verification(
        self,
        record: GitHubKeyRecord,
        account_login: str,
        token_kind: GitHubTokenKind,
        status: GitHubKeyStatus,
        expires_at: Optional[str],
        expiration_source: GitHubExpirationSource,
        oauth_scopes: tuple[str, ...],
    ) -> None:
        """把一次验证结果写入记录。"""
        now = self._now()
        record.account_login = account_login
        record.token_kind = token_kind
        record.status = status
        record.expires_at = expires_at
        record.expiration_source = expiration_source
        record.oauth_scopes = oauth_scopes
        record.updated_at = now
        record.last_verified_at = now

    def _to_view(self, record: GitHubKeyRecord) -> GitHubKeyView:
        """把内部记录转换为无敏感字段的 UI 模型。"""
        return GitHubKeyView(
            id=record.id,
            name=record.name,
            account_login=record.account_login,
            token_kind=record.token_kind,
            status=record.status,
            expires_at=record.expires_at,
            expiration_source=record.expiration_source,
            oauth_scopes=record.oauth_scopes,
            last_verified_at=record.last_verified_at,
            last_error_code=record.last_error_code,
            last_error_message=record.last_error_message,
            is_default=record.id == self._default_key_id,
        )

    @staticmethod
    def _record_to_dict(record: GitHubKeyRecord) -> dict:
        """把内部记录转换为 JSON 条目。"""
        return {
            "id": record.id,
            "name": record.name,
            "encrypted_token": record.encrypted_token,
            "account_login": record.account_login,
            "token_kind": record.token_kind.value,
            "status": record.status.value,
            "expires_at": record.expires_at,
            "expiration_source": record.expiration_source.value,
            "oauth_scopes": list(record.oauth_scopes),
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "last_verified_at": record.last_verified_at,
            "last_error_code": record.last_error_code,
            "last_error_message": record.last_error_message,
        }

    @staticmethod
    def _cleanup_temp_file(temp_file: Path) -> None:
        """尽力清理保存失败留下的临时文件。"""
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            return

    @staticmethod
    def _now() -> str:
        """返回当前 UTC 时间字符串。"""
        return datetime.now(timezone.utc).strftime(_TIME_FORMAT)
