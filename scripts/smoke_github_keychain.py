"""macOS Keychain 与 GitHub Key 保存的真实冒烟验证。"""

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from core.github import (
    DpapiSecretVault,
    GitHubCredentialVaultError,
    GitHubExpirationSource,
    GitHubKeyManager,
    GitHubKeyStore,
    GitHubTokenKind,
    create_default_secret_vault,
)
if sys.platform == "darwin":
    import core.github.macos_keychain as keychain_backend
    from core.github.macos_keychain import MacOSKeychainSecretVault


TEST_SERVICE = "KKPIP-Tech.InstructionX.KeychainSmoke"
TEST_ACCOUNT = "default"
TEST_TOKEN = "github_pat_smoke_测试_123"
REPLACEMENT_TOKEN = "github_pat_smoke_替换_456"
HEX_ONLY_TOKEN = "deadbeef"
SMOKE_ROOT = Path(__file__).resolve().parent.parent / "temp" / "github-keychain-smoke"
GUI_SAVE_TIMEOUT_MS = 10000


class _SaveWorker(QObject):
    """在 GUI 工作线程执行真实 GitHubKeyManager 保存。"""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, manager: GitHubKeyManager):
        super().__init__()
        self._manager = manager

    @Slot()
    def run(self) -> None:
        """保存测试 Key，异常通过信号返回主线程。"""
        try:
            view = self._manager.add_key("GUI 测试", TEST_TOKEN)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(view)


def _expect_vault_error(action) -> None:
    """断言指定操作会以凭据后端异常失败。"""
    try:
        action()
    except GitHubCredentialVaultError:
        return
    raise AssertionError("预期 GitHubCredentialVaultError，但操作成功")


def check_native_backend() -> None:
    """要求使用 Security.framework，禁止回退到交互式子进程。"""
    assert not hasattr(keychain_backend, "subprocess"), "仍依赖交互式 security 子进程"
    assert hasattr(keychain_backend, "SecItemAdd"), "缺少 Security.framework SecItemAdd"


def check_vault_roundtrip(vault: "MacOSKeychainSecretVault") -> None:
    """验证原生读写替换、Unicode、纯十六进制 Token 和异常输入。"""
    marker = vault.encrypt(TEST_TOKEN)
    assert marker.startswith("keychain:v1:")
    assert TEST_TOKEN not in marker
    assert vault.decrypt(marker) == TEST_TOKEN
    assert vault.encrypt(REPLACEMENT_TOKEN) == marker
    assert vault.decrypt(marker) == REPLACEMENT_TOKEN
    assert vault.encrypt(HEX_ONLY_TOKEN) == marker
    assert vault.decrypt(marker) == HEX_ONLY_TOKEN
    _expect_vault_error(lambda: vault.decrypt("dpapi:v1:not-keychain"))
    _expect_vault_error(lambda: vault.encrypt(""))


def check_backend_failure(vault: "MacOSKeychainSecretVault") -> None:
    """验证 Security.framework 错误不会泄露 Token。"""
    with patch.object(keychain_backend, "SecItemUpdate", return_value=-50):
        try:
            vault.encrypt(TEST_TOKEN)
        except GitHubCredentialVaultError as exc:
            assert TEST_TOKEN not in str(exc)
        else:
            raise AssertionError("原生后端失败未抛出 GitHubCredentialVaultError")


def _make_manager(store: GitHubKeyStore) -> GitHubKeyManager:
    """创建仅 mock 身份验证的 Key 管理器。"""
    api = MagicMock()
    api.get_authenticated_user.return_value = SimpleNamespace(
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
    )
    GitHubKeyManager._instance = None
    return GitHubKeyManager(
        store=store,
        api_client=api,
        environment_reader=lambda _name: "",
        logger=MagicMock(),
    )


def check_store_integration(vault: "MacOSKeychainSecretVault") -> None:
    """验证 GitHubKeyStore 持久化、Token 读取与删除清理。"""
    SMOKE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SMOKE_ROOT) as directory:
        store = GitHubKeyStore(Path(directory), vault)
        manager = _make_manager(store)
        view = manager.add_key("macOS 测试", TEST_TOKEN)
        config_file = Path(directory) / "github_keys.json"
        payload = json.loads(config_file.read_text(encoding="utf-8"))
        encrypted = payload["keys"][0]["encrypted_token"]
        assert encrypted.startswith("keychain:v1:")
        assert TEST_TOKEN not in config_file.read_text(encoding="utf-8")
        assert manager.get_credential(view.id).token == TEST_TOKEN
        store.remove_key(view.id)
        _expect_vault_error(lambda: vault.decrypt(encrypted))


def _wait_for_gui_worker(app: QApplication, thread: QThread) -> None:
    """在主事件循环运行期间等待工作线程，避免同步等待自死锁。"""
    timed_out = {"value": False}
    timer = QTimer()
    timer.setSingleShot(True)

    def handle_timeout() -> None:
        timed_out["value"] = True
        app.quit()

    timer.timeout.connect(handle_timeout)
    timer.start(GUI_SAVE_TIMEOUT_MS)
    app.exec()
    timer.stop()
    if timed_out["value"]:
        thread.terminate()
        thread.wait()
        raise AssertionError("GUI 保存线程超时")
    assert thread.wait(1000), "GUI 工作线程未正常退出"


def check_gui_save(vault: "MacOSKeychainSecretVault") -> None:
    """验证 GUI 工作线程保存不再依赖控制台交互。"""
    app = QApplication.instance() or QApplication([])
    SMOKE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SMOKE_ROOT) as directory:
        store = GitHubKeyStore(Path(directory), vault)
        manager = _make_manager(store)
        result = {}
        thread = QThread()
        worker = _SaveWorker(manager)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(app.quit)
        worker.failed.connect(app.quit)
        worker.finished.connect(lambda view: result.update(view=view))
        worker.failed.connect(lambda error: result.update(error=error))
        thread.finished.connect(worker.deleteLater)
        thread.start()
        _wait_for_gui_worker(app, thread)
        app.processEvents()
        assert "error" not in result, result.get("error", "")
        assert manager.get_credential(result["view"].id).token == TEST_TOKEN
        store.remove_key(result["view"].id)


def main() -> int:
    """运行平台工厂与 macOS 真实 Keychain 场景。"""
    if sys.platform != "darwin":
        assert isinstance(create_default_secret_vault(), DpapiSecretVault)
        print("GitHub Keychain smoke skipped on non-macOS; DPAPI factory preserved")
        return 0
    vault = MacOSKeychainSecretVault(service=TEST_SERVICE, account=TEST_ACCOUNT)
    assert isinstance(create_default_secret_vault(), MacOSKeychainSecretVault)
    with patch("core.github.secret_vault.sys.platform", "win32"):
        assert isinstance(create_default_secret_vault(), DpapiSecretVault)
    try:
        check_native_backend()
        check_vault_roundtrip(vault)
        check_backend_failure(vault)
        check_store_integration(vault)
        check_gui_save(vault)
    finally:
        try:
            vault.delete("keychain:v1:default")
        except GitHubCredentialVaultError as exc:
            print(f"WARNING Keychain 测试项清理失败: {exc}")
        shutil.rmtree(SMOKE_ROOT, ignore_errors=True)
        GitHubKeyManager._instance = None
    print("GitHub macOS Keychain smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
