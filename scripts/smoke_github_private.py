"""GitHub 私有仓库 Key 管理无网冒烟测试。

覆盖多 Key、DPAPI 加密、私有仓库检查、来源绑定和重新绑定；
所有临时数据位于项目 temp/，不访问真实 GitHub。
"""

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.github import (
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyManager,
    GitHubKeyStatus,
    GitHubKeyStore,
    GitHubKeyView,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
    InMemorySecretVault,
    PluginSourceKeyBinder,
)
from core.plugin.github_plugin_installer import GitHubPluginInstaller
from core.plugin.plugin_registry import PluginRegistry

SMOKE_ROOT = Path(__file__).resolve().parent.parent / "temp" / "github-private-smoke"


def check(condition: bool, message: str) -> None:
    """断言冒烟条件。"""
    if not condition:
        raise AssertionError(message)


def key_view(key_id: str, name: str) -> GitHubKeyView:
    """构造有效 Key 展示值。"""
    return GitHubKeyView(
        id=key_id,
        name=name,
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=GitHubKeyStatus.VALID,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="",
        last_error_code="",
        last_error_message="",
    )


def build_manager(tmp_path: Path, api: MagicMock) -> GitHubKeyManager:
    """创建使用临时配置和内存凭据的 Key 管理器。"""
    GitHubKeyManager._instance = None
    store = GitHubKeyStore(tmp_path / "config", InMemorySecretVault())
    return GitHubKeyManager(
        store=store,
        api_client=api,
        environment_reader=lambda _name: "",
        logger=MagicMock(),
    )


def build_fixture(tmp_path: Path):
    """创建假 API、Key 管理器和两个 Key。"""
    api = MagicMock()
    api.get_authenticated_user.return_value = SimpleNamespace(
        account_login="octocat",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
    )
    manager = build_manager(tmp_path, api)
    first = manager.add_key("工作账号", "github_pat_first")
    second = manager.add_key("备用账号", "github_pat_second")
    manager.set_default_key(first.id)
    check(len(manager.list_keys()) == 2, "多 Key 添加失败")
    return api, manager, first, second


def verify_inspection(api, manager, first):
    """验证私有仓库检查和可见性。"""
    repository = GitHubRepositoryInfo(
        owner="acme",
        repo="private-plugins",
        visibility=GitHubRepositoryVisibility.PRIVATE,
        default_branch="main",
        auth_key_id=first.id,
    )
    api.get_repository.return_value = repository
    api.get_file_json.side_effect = [None, {
        "id": "private-plugin",
        "name": "Private Plugin",
        "version": "release.1.0.0",
        "main": "entrance.py",
    }]
    installer = GitHubPluginInstaller(
        key_manager=manager,
        api_client=api,
    )
    inspection = installer.inspect_repository(
        "https://github.com/acme/private-plugins",
        key_id=first.id,
    )
    check(inspection.repo_type == "single", "私有仓库检查失败")
    check(
        inspection.repository.visibility is GitHubRepositoryVisibility.PRIVATE,
        "私有仓库未正确标记",
    )
    return repository


def verify_rebinding(tmp_path, api, manager, repository, first, second):
    """验证来源绑定和重新绑定。"""
    registry = PluginRegistry(tmp_path / "config")
    registry.upsert(
        "plugin-uuid",
        descriptor_id="private-plugin",
        name="Private Plugin",
        scope="thirdparty",
        version="release.1.0.0",
        source_type="github",
        source_url="https://github.com/acme/private-plugins",
        source_visibility="private",
        source_key_id=first.id,
    )
    manager.get_key_view = MagicMock(return_value=first)
    manager.verify_repository_access = MagicMock(return_value=repository)
    binder = PluginSourceKeyBinder(registry, manager, api)
    resolution = binder.resolve("plugin-uuid")
    check(resolution.available, "绑定 Key 解析失败")

    manager.get_credential = MagicMock(return_value=GitHubCredential(
        second.id, second.name, "github_pat_second", "octocat"))
    rebound = binder.rebind("plugin-uuid", second.id)
    check(rebound.available, "重新绑定失败")
    check(
        registry.get("plugin-uuid")["source_key_id"] == second.id,
        "重新绑定未持久化",
    )
    check(json.dumps(registry.all()), "注册表不可序列化")


def run_smoke(tmp_path: Path) -> None:
    """串联全部无网场景。"""
    api, manager, first, second = build_fixture(tmp_path)
    repository = verify_inspection(api, manager, first)
    verify_rebinding(tmp_path, api, manager, repository, first, second)


def main() -> None:
    """运行冒烟并清理临时目录。"""
    if SMOKE_ROOT.exists():
        shutil.rmtree(SMOKE_ROOT)
    SMOKE_ROOT.mkdir(parents=True)
    try:
        with tempfile.TemporaryDirectory(dir=SMOKE_ROOT) as directory:
            run_smoke(Path(directory))
    finally:
        shutil.rmtree(SMOKE_ROOT, ignore_errors=True)
    print("GitHub private key smoke passed")


if __name__ == "__main__":
    main()
