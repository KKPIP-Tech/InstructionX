"""GitHub PAT 的安全加密存储后端。

Windows 使用 DPAPI，将密文绑定到当前 Windows 用户。测试可注入
``InMemorySecretVault``；任何平台都禁止在 DPAPI 失败时降级为 Base64。
"""

import base64
import ctypes
import os
from ctypes import wintypes
from typing import Protocol

from .exceptions import GitHubCredentialVaultError

DPAPI_PREFIX = "dpapi:v1:"
DPAPI_DESCRIPTION = "InstructionX GitHub PAT"
CRYPTPROTECT_UI_FORBIDDEN = 0x01


class SecretVault(Protocol):
    """凭据加密后端协议。"""

    def encrypt(self, plaintext: str) -> str:
        """加密凭据并返回带版本前缀的密文。"""

    def decrypt(self, stored: str) -> str:
        """解密存储值并返回内存明文。"""


class _DataBlob(ctypes.Structure):
    """Windows DPAPI 使用的 DATA_BLOB 结构。"""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


class DpapiSecretVault:
    """基于 Windows DPAPI 的 SecretVault 实现。"""

    def encrypt(self, plaintext: str) -> str:
        """使用当前 Windows 用户上下文加密凭据。

        Args:
            plaintext: GitHub PAT 明文。

        Returns:
            str: ``dpapi:v1:<base64>`` 格式密文。

        Raises:
            GitHubCredentialVaultError: 非 Windows、空凭据或加密失败。
        """
        if not plaintext:
            raise GitHubCredentialVaultError("GitHub Token 不能为空")
        data = plaintext.encode("utf-8")
        encrypted = self._protect(data)
        payload = base64.b64encode(encrypted).decode("ascii")
        return DPAPI_PREFIX + payload

    def decrypt(self, stored: str) -> str:
        """使用当前 Windows 用户上下文解密凭据。

        Args:
            stored: ``dpapi:v1:<base64>`` 格式密文。

        Returns:
            str: GitHub PAT 明文。

        Raises:
            GitHubCredentialVaultError: 前缀错误、Base64 或 DPAPI 解密失败。
        """
        if not stored.startswith(DPAPI_PREFIX):
            raise GitHubCredentialVaultError("不支持的 GitHub 凭据密文格式")
        try:
            encrypted = base64.b64decode(
                stored[len(DPAPI_PREFIX):], validate=True)
        except (ValueError, TypeError) as exc:
            raise GitHubCredentialVaultError("GitHub 凭据密文格式损坏") from exc
        return self._unprotect(encrypted).decode("utf-8")

    def _protect(self, data: bytes) -> bytes:
        """调用 CryptProtectData 加密字节串。"""
        self._require_windows()
        source_buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(
            len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = _DataBlob()
        description = ctypes.create_unicode_buffer(DPAPI_DESCRIPTION)
        result = ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), description, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output))
        if not result:
            raise GitHubCredentialVaultError("Windows DPAPI 加密 GitHub Key 失败")
        return self._copy_and_free(output)

    def _unprotect(self, data: bytes) -> bytes:
        """调用 CryptUnprotectData 解密字节串。"""
        self._require_windows()
        source_buffer = ctypes.create_string_buffer(data)
        source = _DataBlob(
            len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        output = _DataBlob()
        result = ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None,
            CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(output))
        if not result:
            raise GitHubCredentialVaultError(
                "Windows DPAPI 无法解密 GitHub Key，请重新录入 Token")
        return self._copy_and_free(output)

    @staticmethod
    def _copy_and_free(blob: _DataBlob) -> bytes:
        """复制 DPAPI 输出并用 LocalFree 释放系统内存。"""
        try:
            return ctypes.string_at(blob.pbData, blob.cbData)
        finally:
            if blob.pbData:
                ctypes.windll.kernel32.LocalFree(blob.pbData)

    @staticmethod
    def _require_windows() -> None:
        """拒绝在不支持 DPAPI 的平台使用此实现。"""
        if os.name != "nt":
            raise GitHubCredentialVaultError(
                "当前平台不支持 Windows DPAPI，无法安全保存 GitHub Key")


class InMemorySecretVault:
    """仅供测试或显式临时会话使用的内存凭据后端。

    密文使用进程内随机前缀映射，不写入磁盘。
    """

    def __init__(self) -> None:
        """初始化空内存表。"""
        self._values: dict[str, str] = {}
        self._next_id = 0

    def encrypt(self, plaintext: str) -> str:
        """保存内存明文映射并返回测试密文标识。"""
        if not plaintext:
            raise GitHubCredentialVaultError("GitHub Token 不能为空")
        self._next_id += 1
        marker = f"memory:v1:{self._next_id}"
        self._values[marker] = plaintext
        return marker

    def decrypt(self, stored: str) -> str:
        """从内存表恢复明文。"""
        try:
            return self._values[stored]
        except KeyError as exc:
            raise GitHubCredentialVaultError("内存 GitHub 凭据不存在") from exc


def create_default_secret_vault() -> SecretVault:
    """创建生产环境默认 SecretVault。"""
    return DpapiSecretVault()
