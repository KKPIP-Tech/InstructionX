"""GitHub 私有仓库真实环境验收脚本。

运行前在本机设置：
    INSTRUCTIONX_TEST_GITHUB_PRIVATE_TOKEN=<PAT>
    INSTRUCTIONX_TEST_GITHUB_PRIVATE_REPO=<owner/repo>

脚本只在 temp/ 下创建临时 Key、插件目录和注册表，完成后清理；
Token 不会打印到控制台或写入项目正式配置。
"""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from core.github import (
    DpapiSecretVault,
    GitHubApiClient,
    GitHubKeyManager,
    GitHubKeyStatus,
    GitHubKeyStore,
    GitHubKeyUnavailableReason,
    GitHubRepositoryVisibility,
    PluginSourceKeyBinder,
)
from core.plugin.github_plugin_installer import GitHubPluginInstaller
from core.plugin.plugin_registry import PluginRegistry

TOKEN_ENV = "INSTRUCTIONX_TEST_GITHUB_PRIVATE_TOKEN"
EXPIRED_TOKEN_ENV = "INSTRUCTIONX_TEST_GITHUB_PRIVATE_EXPIRED_TOKEN"
REPO_ENV = "INSTRUCTIONX_TEST_GITHUB_PRIVATE_REPO"
SMOKE_ROOT = Path(__file__).resolve().parent.parent / "temp" / "github-private-live"


def require(condition: bool, message: str) -> None:
    """断言真实验收条件。"""
    if not condition:
        raise AssertionError(message)


def parse_repo(value: str):
    """解析 owner/repo 或 GitHub URL。"""
    text = value.strip().rstrip("/")
    if text.startswith("https://github.com/"):
        text = text[len("https://github.com/"):]
    parts = text.split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise ValueError("私有仓库参数应为 owner/repo 或 GitHub URL")
    return parts[0], parts[1].removesuffix(".git")


def build_context(tmp_path: Path):
    """创建临时 Key 管理器和插件管理器。"""
    GitHubKeyManager._instance = None
    config_dir = tmp_path / "config"
    store = GitHubKeyStore(config_dir, DpapiSecretVault())
    manager = GitHubKeyManager(store=store, api_client=GitHubApiClient())
    official = tmp_path / "plugin"
    thirdparty = tmp_path / "custom_plugin"
    official.mkdir()
    thirdparty.mkdir()
    registry = PluginRegistry(config_dir)
    plugin_manager = SimpleNamespace(
        official_plugin_dir=official,
        thirdparty_plugin_dir=thirdparty,
        registry=registry,
    )
    return manager, plugin_manager, registry, store


def inspect_private(installer, owner: str, repo: str, key_id: str):
    """检查私有仓库并断言真实可见性。"""
    inspection = installer.inspect_repository(
        f"https://github.com/{owner}/{repo}", key_id=key_id)
    require(inspection.repo_type != "invalid", inspection.error_message or "")
    require(
        inspection.repository.visibility is GitHubRepositoryVisibility.PRIVATE,
        "目标仓库不是私有仓库或当前 Key 无权访问",
    )
    return inspection


def install_private(installer, plugin_manager, inspection, owner, repo, key_id):
    """实际安装全部私有插件并检查绑定。"""
    results = installer.install_from_url(
        f"https://github.com/{owner}/{repo}",
        selected_plugins=[plugin.path for plugin in inspection.plugins],
        official_dir=plugin_manager.official_plugin_dir,
        thirdparty_dir=plugin_manager.thirdparty_plugin_dir,
        key_id=key_id,
    )
    require(bool(results) and all(result.success for result in results),
            "私有插件实际安装失败")
    records = plugin_manager.registry.all().values()
    require(all(record.get("source_key_id") == key_id for record in records),
            "私有插件来源 Key 未持久化")
    return results


def install_latest_release(installer, plugin_manager, inspection, owner, repo, key_id):
    """存在 Release 时执行一次真实升级/重装下载。"""
    plugin_path = inspection.plugins[0].path
    descriptor = f"{plugin_path}/IXPlugin.json" if plugin_path else ""
    versions = installer.get_available_versions(
        f"https://github.com/{owner}/{repo}", descriptor, key_id)
    if not versions:
        return False
    record = next(iter(plugin_manager.registry.all().values()))
    target = (
        plugin_manager.official_plugin_dir
        if record.get("scope") == "official"
        else plugin_manager.thirdparty_plugin_dir
    )
    selected = [plugin_path] if plugin_path else None
    results = installer.install_release(
        owner, repo, versions[0].tag, target, selected, key_id=key_id)
    require(bool(results) and all(result.success for result in results),
            "私有 Release 实际下载/安装失败")
    return True


def rebind_first_plugin(
    manager,
    plugin_manager,
    second_key_id: str,
) -> str:
    """用第二个真实 Key 重新绑定首个插件。"""
    plugin_id = next(iter(plugin_manager.registry.all()))
    binder = PluginSourceKeyBinder(plugin_manager.registry, manager)
    resolution = binder.rebind(plugin_id, second_key_id)
    require(resolution.available, resolution.error_message or "真实重新绑定失败")
    record = plugin_manager.registry.get(plugin_id) or {}
    require(record.get("source_key_id") == second_key_id,
            "重新绑定后 Key ID 未持久化")
    return plugin_id


def exercise_expired_rebind(
    store: GitHubKeyStore,
    manager: GitHubKeyManager,
    plugin_manager,
    expired_token: str,
    valid_key_id: str,
) -> bool:
    """使用真实失效 Token 验证 KEY_INVALID 到新 Key 的恢复。"""
    if not expired_token:
        return False
    expired = store.add_key(
        "Expired live key",
        expired_token,
        status=GitHubKeyStatus.INVALID,
    )
    plugin_id = next(iter(plugin_manager.registry.all()))
    plugin_manager.registry.set_source_binding(
        plugin_id,
        source_visibility="private",
        source_key_id=expired.id,
    )
    binder = PluginSourceKeyBinder(plugin_manager.registry, manager)
    resolution = binder.resolve(plugin_id)
    require(
        resolution.reason is GitHubKeyUnavailableReason.KEY_INVALID,
        "失效 Key 未被识别为 KEY_INVALID",
    )
    rebound = binder.rebind(plugin_id, valid_key_id)
    require(rebound.available, rebound.error_message or "失效 Key 重绑失败")
    return True


def run_live_smoke(token: str, repository: str, expired_token: str = "") -> None:
    """执行真实私有仓库检查、安装和 Release 下载。"""
    SMOKE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SMOKE_ROOT) as directory:
        manager, plugin_manager, _registry, store = build_context(Path(directory))
        key = manager.add_key("Live smoke", token)
        rebound_key = manager.add_key("Live smoke rebound", token)
        manager.set_default_key(key.id)
        owner, repo = parse_repo(repository)
        installer = GitHubPluginInstaller(
            plugin_manager, key_manager=manager, api_client=GitHubApiClient())
        inspection = inspect_private(installer, owner, repo, key.id)
        results = install_private(
            installer, plugin_manager, inspection, owner, repo, key.id)
        expired_rebind = exercise_expired_rebind(
            store, manager, plugin_manager, expired_token, rebound_key.id)
        if not expired_rebind:
            rebind_first_plugin(manager, plugin_manager, rebound_key.id)
        release_tested = install_latest_release(
            installer, plugin_manager, inspection, owner, repo, rebound_key.id)
        print(json.dumps({
            "repository": f"{owner}/{repo}",
            "visibility": "private",
            "plugins": len(results),
            "keys": 2,
            "rebind_tested": True,
            "expired_token_rebind": expired_rebind,
            "release_tested": release_tested,
            "key_storage": "DPAPI temporary",
        }, ensure_ascii=False))


def main() -> int:
    """读取环境变量并运行真实验收。"""
    token = os.environ.get(TOKEN_ENV, "").strip()
    expired_token = os.environ.get(EXPIRED_TOKEN_ENV, "").strip()
    repository = os.environ.get(REPO_ENV, "").strip()
    if not token or not repository:
        print(f"SKIP: set {TOKEN_ENV} and {REPO_ENV}")
        return 2
    try:
        run_live_smoke(token, repository, expired_token)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        shutil.rmtree(SMOKE_ROOT, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
