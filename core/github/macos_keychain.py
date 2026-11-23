"""使用 macOS Security.framework 保存 GitHub PAT 的凭据后端。

Token 直接以 NSData 写入当前用户 Keychain，不经过命令行参数、stdin
或交互式 security 子进程；配置文件只保存 ``keychain:v1:`` 引用。
"""

import ctypes
import hmac
import sys

from Foundation import NSData, NSMutableDictionary, NSNumber, NSString
from PySide6.QtWidgets import QApplication

from utils.thread_utils import run_in_ui_thread_sync

from .exceptions import GitHubCredentialVaultError


KEYCHAIN_PREFIX = "keychain:v1:"
KEYCHAIN_REFERENCE = f"{KEYCHAIN_PREFIX}default"
KEYCHAIN_PAYLOAD_PREFIX = "InstructionX:PAT:v1:"
KEYCHAIN_SERVICE = "KKPIP-Tech.InstructionX.GitHubPAT"
KEYCHAIN_ACCOUNT = "default"
SECURITY_FRAMEWORK = "/System/Library/Frameworks/Security.framework/Security"
CORE_FOUNDATION = "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
SEC_CLASS = "class"
SEC_CLASS_GENERIC_PASSWORD = "genp"
SEC_ATTR_SERVICE = "srv"
SEC_ATTR_ACCOUNT = "acct"
SEC_VALUE_DATA = "v_Data"
SEC_RETURN_DATA = "r_Data"
SEC_MATCH_LIMIT = "m_Limit"
SEC_MATCH_LIMIT_ONE = "m_One"
ERR_SEC_ITEM_NOT_FOUND = -25300


def _ns(value: str):
    """把 Python 字符串显式转换为 Security 接受的 NSString。"""
    return NSString.stringWithString_(value)


_security = ctypes.CDLL(SECURITY_FRAMEWORK)
_core_foundation = ctypes.CDLL(CORE_FOUNDATION)
SecItemAdd = _security.SecItemAdd
SecItemUpdate = _security.SecItemUpdate
SecItemCopyMatching = _security.SecItemCopyMatching
SecItemDelete = _security.SecItemDelete
SecItemAdd.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
SecItemUpdate.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
SecItemCopyMatching.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
SecItemDelete.argtypes = [ctypes.c_void_p]
for _function in (SecItemAdd, SecItemUpdate, SecItemCopyMatching, SecItemDelete):
    _function.restype = ctypes.c_int32
CFDataGetBytePtr = _core_foundation.CFDataGetBytePtr
CFDataGetLength = _core_foundation.CFDataGetLength
CFRelease = _core_foundation.CFRelease
CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
CFDataGetBytePtr.restype = ctypes.c_void_p
CFDataGetLength.argtypes = [ctypes.c_void_p]
CFDataGetLength.restype = ctypes.c_long
CFRelease.argtypes = [ctypes.c_void_p]
CFRelease.restype = None


class MacOSKeychainSecretVault:
    """基于 Security.framework 的 SecretVault 实现。

    Args:
        service: Keychain service；测试可传入独立名称隔离真实凭据。
        account: Keychain account，默认 ``default``。
    """

    def __init__(
        self,
        service: str = KEYCHAIN_SERVICE,
        account: str = KEYCHAIN_ACCOUNT,
    ) -> None:
        if not service or not account:
            raise ValueError("Keychain service 和 account 不能为空")
        self._service = service
        self._account = account

    def encrypt(self, plaintext: str) -> str:
        """新增或更新 Keychain 凭据，并在读回校验后返回版本化引用。"""
        if not plaintext:
            raise GitHubCredentialVaultError("GitHub Token 不能为空")
        self._require_macos()
        payload = self._payload_data(plaintext)
        query = self._base_query()
        attributes = self._update_attributes(payload)
        status = self._run_on_main(
            lambda: SecItemUpdate(
                query.__c_void_p__(), attributes.__c_void_p__()
            )
        )
        if status == ERR_SEC_ITEM_NOT_FOUND:
            query[_ns(SEC_VALUE_DATA)] = payload
            status = self._run_on_main(
                lambda: SecItemAdd(query.__c_void_p__(), None)
            )
        self._require_success(status, "保存 GitHub Key")
        actual = self.decrypt(KEYCHAIN_REFERENCE).encode("utf-8")
        if not hmac.compare_digest(actual, plaintext.encode("utf-8")):
            raise GitHubCredentialVaultError("macOS Keychain 写入校验失败")
        return KEYCHAIN_REFERENCE

    def decrypt(self, stored: str) -> str:
        """从当前用户 Keychain 读取 PAT，拒绝其他密文格式。"""
        self._require_reference(stored)
        self._require_macos()
        payload = self._run_on_main(self._read_native)
        return self._decode_payload(payload)

    def delete(self, stored: str) -> None:
        """删除 Keychain 凭据；项目不存在时按已删除处理。"""
        self._require_reference(stored)
        self._require_macos()
        query = self._base_query()
        status = self._run_on_main(
            lambda: SecItemDelete(query.__c_void_p__())
        )
        if status not in (0, ERR_SEC_ITEM_NOT_FOUND):
            self._require_success(status, "删除 GitHub Key")

    def _read_native(self) -> bytes:
        """在调用方指定线程读取并释放 CFData。"""
        result = ctypes.c_void_p()
        query = self._read_query()
        status = SecItemCopyMatching(
            query.__c_void_p__(), ctypes.byref(result)
        )
        self._require_success(status, "读取 GitHub Key")
        if not result:
            raise GitHubCredentialVaultError("macOS Keychain 未返回凭据数据")
        try:
            length = CFDataGetLength(result)
            return ctypes.string_at(CFDataGetBytePtr(result), length)
        finally:
            CFRelease(result)

    def _base_query(self):
        """创建 service/account 唯一定位的 generic password 查询。"""
        query = NSMutableDictionary.alloc().init()
        query[_ns(SEC_CLASS)] = _ns(SEC_CLASS_GENERIC_PASSWORD)
        query[_ns(SEC_ATTR_SERVICE)] = _ns(self._service)
        query[_ns(SEC_ATTR_ACCOUNT)] = _ns(self._account)
        return query

    def _read_query(self):
        """创建只返回一项 NSData 的读取查询。"""
        query = self._base_query()
        query[_ns(SEC_RETURN_DATA)] = NSNumber.numberWithBool_(True)
        query[_ns(SEC_MATCH_LIMIT)] = _ns(SEC_MATCH_LIMIT_ONE)
        return query

    @staticmethod
    def _update_attributes(payload):
        """创建 SecItemUpdate 所需的密码数据属性。"""
        attributes = NSMutableDictionary.alloc().init()
        attributes[_ns(SEC_VALUE_DATA)] = payload
        return attributes

    @staticmethod
    def _payload_data(plaintext: str):
        """把带版本前缀的 UTF-8 载荷转换为 NSData。"""
        data = (KEYCHAIN_PAYLOAD_PREFIX + plaintext).encode("utf-8")
        return NSData.dataWithBytes_length_(data, len(data))

    @staticmethod
    def _decode_payload(payload: bytes) -> str:
        """解码 UTF-8 载荷并校验版本前缀。"""
        try:
            decoded = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GitHubCredentialVaultError("macOS Keychain 凭据格式损坏") from exc
        if not decoded.startswith(KEYCHAIN_PAYLOAD_PREFIX):
            raise GitHubCredentialVaultError("macOS Keychain 凭据格式不匹配")
        return decoded[len(KEYCHAIN_PAYLOAD_PREFIX):]

    @staticmethod
    def _run_on_main(operation):
        """GUI 场景在主线程执行 Keychain 调用，命令行直接执行。"""
        if QApplication.instance() is None:
            return operation()
        # 系统解锁/授权可能需要用户操作，不设置人为超时；主事件循环仍可响应。
        return run_in_ui_thread_sync(operation, timeout=None)

    @staticmethod
    def _require_success(status: int, operation: str) -> None:
        """把 Security.framework 非零状态转换为脱敏领域异常。"""
        if status != 0:
            raise GitHubCredentialVaultError(
                f"macOS Keychain {operation}失败（状态码 {status}）"
            )

    @staticmethod
    def _require_reference(stored: str) -> None:
        """只接受本后端的版本化 Keychain 引用。"""
        if stored != KEYCHAIN_REFERENCE:
            raise GitHubCredentialVaultError("不支持的 GitHub Keychain 凭据引用")

    @staticmethod
    def _require_macos() -> None:
        """拒绝在非 macOS 平台调用 Keychain。"""
        if sys.platform != "darwin":
            raise GitHubCredentialVaultError("当前平台不支持 macOS Keychain")
