"""macOS Keychain 与 GitHub Key 保存兼容性测试。"""

import json
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QObject, QThread, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

from core.github import (
    DpapiSecretVault,
    GitHubCredentialVaultError,
    GitHubExpirationSource,
    GitHubKeyManager,
    GitHubKeyNotFoundError,
    GitHubKeyStore,
    GitHubTokenKind,
    create_default_secret_vault,
)

if sys.platform == "darwin":
    from core.github.macos_keychain import (
        KEYCHAIN_REFERENCE,
        MacOSKeychainSecretVault,
    )


TEST_TOKEN = "github_pat_pytest_测试_123"
REPLACEMENT_TOKEN = "github_pat_pytest_替换_456"
HEX_ONLY_TOKEN = "deadbeef"
GUI_TIMEOUT_MS = 10000


@pytest.fixture(autouse=True)
def _reset_key_manager():
    """隔离 GitHubKeyManager 单例。"""
    GitHubKeyManager._instance = None
    yield
    GitHubKeyManager._instance = None


@pytest.fixture
def keychain_vault():
    """提供随机独立 service，并在测试后清理 Keychain 项。"""
    if sys.platform != "darwin":
        pytest.skip("仅 macOS 支持原生 Keychain 测试")
    service = f"KKPIP-Tech.InstructionX.PyTest.{uuid.uuid4().hex}"
    vault = MacOSKeychainSecretVault(service=service)
    yield vault
    vault.delete(KEYCHAIN_REFERENCE)


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
    return GitHubKeyManager(
        store=store,
        api_client=api,
        environment_reader=lambda _name: "",
        logger=MagicMock(),
    )


class _SaveWorker(QObject):
    """在 GUI 工作线程执行真实 Key 保存。"""

    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, manager: GitHubKeyManager):
        super().__init__()
        self._manager = manager

    @Slot()
    def run(self) -> None:
        """保存测试 Key，异常通过信号返回。"""
        try:
            view = self._manager.add_key("GUI 测试", TEST_TOKEN)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(view)


def _wait_for_worker(app: QApplication, thread: QThread) -> None:
    """在主事件循环运行期间等待工作线程退出。"""
    timed_out = {"value": False}
    timer = QTimer()
    timer.setSingleShot(True)

    def handle_timeout() -> None:
        timed_out["value"] = True
        app.quit()

    timer.timeout.connect(handle_timeout)
    timer.start(GUI_TIMEOUT_MS)
    app.exec()
    timer.stop()
    if timed_out["value"]:
        thread.terminate()
        thread.wait()
        pytest.fail("GUI 保存线程超时")
    assert thread.wait(1000), "GUI 工作线程未正常退出"


def test_factory_preserves_dpapi(mocker) -> None:
    """非 macOS 工厂分支继续选择 DPAPI。"""
    mocker.patch("core.github.secret_vault.sys.platform", "win32")
    assert isinstance(create_default_secret_vault(), DpapiSecretVault)


@pytest.mark.integration
def test_macos_factory_and_roundtrip(keychain_vault) -> None:
    """macOS 使用原生后端，并可保存、读取和替换 Token。"""
    assert isinstance(create_default_secret_vault(), MacOSKeychainSecretVault)
    marker = keychain_vault.encrypt(TEST_TOKEN)
    assert marker.startswith("keychain:v1:")
    assert TEST_TOKEN not in marker
    assert keychain_vault.decrypt(marker) == TEST_TOKEN
    assert keychain_vault.encrypt(REPLACEMENT_TOKEN) == marker
    assert keychain_vault.decrypt(marker) == REPLACEMENT_TOKEN


@pytest.mark.integration
@pytest.mark.parametrize("token", [TEST_TOKEN, HEX_ONLY_TOKEN])
def test_unicode_and_hex_token(keychain_vault, token: str) -> None:
    """Unicode 和纯十六进制 Token 均按原值恢复。"""
    marker = keychain_vault.encrypt(token)
    assert keychain_vault.decrypt(marker) == token


@pytest.mark.integration
def test_delete_and_invalid_input(keychain_vault) -> None:
    """删除、非法引用和空 Token 都有明确失败语义。"""
    marker = keychain_vault.encrypt(TEST_TOKEN)
    keychain_vault.delete(marker)
    with pytest.raises(GitHubCredentialVaultError):
        keychain_vault.decrypt(marker)
    with pytest.raises(GitHubCredentialVaultError):
        keychain_vault.decrypt("dpapi:v1:not-keychain")
    with pytest.raises(GitHubCredentialVaultError):
        keychain_vault.encrypt("")


@pytest.mark.integration
def test_native_failure_is_sanitized(keychain_vault, mocker) -> None:
    """Security.framework 错误不包含 Token 明文。"""
    mocker.patch(
        "core.github.macos_keychain.SecItemUpdate",
        return_value=-50,
    )
    with pytest.raises(GitHubCredentialVaultError) as captured:
        keychain_vault.encrypt(TEST_TOKEN)
    assert TEST_TOKEN not in str(captured.value)


@pytest.mark.integration
def test_manager_save_and_remove(keychain_vault, tmp_path) -> None:
    """GitHubKeyManager 保存链路不写入明文，删除时清理 Keychain。"""
    store = GitHubKeyStore(tmp_path, keychain_vault)
    manager = _make_manager(store)
    view = manager.add_key("macOS 测试", TEST_TOKEN)
    config_file = tmp_path / "github_keys.json"
    payload = json.loads(config_file.read_text(encoding="utf-8"))
    marker = payload["keys"][0]["encrypted_token"]
    assert marker.startswith("keychain:v1:")
    assert TEST_TOKEN not in config_file.read_text(encoding="utf-8")
    assert manager.get_credential(view.id).token == TEST_TOKEN
    store.remove_key(view.id)
    with pytest.raises(GitHubKeyNotFoundError):
        store.get_secret(view.id)
    with pytest.raises(GitHubCredentialVaultError):
        keychain_vault.decrypt(marker)


@pytest.mark.ui
@pytest.mark.integration
def test_gui_worker_save(keychain_vault, tmp_path, qtbot) -> None:
    """GUI 工作线程保存不需要控制台密码输入或固定等待。"""
    app = QApplication.instance()
    store = GitHubKeyStore(tmp_path, keychain_vault)
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
    _wait_for_worker(app, thread)
    app.processEvents()
    assert "error" not in result, result.get("error", "")
    assert manager.get_credential(result["view"].id).token == TEST_TOKEN
    store.remove_key(result["view"].id)
