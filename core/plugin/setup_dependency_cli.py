"""为原生 Setup TUI 提供插件依赖安装与更新检查的结构化后端。"""

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .github_plugin_installer import GitHubPluginInstaller
from .plugin_startup import PluginDependencyPreparer, read_plugin_descriptor
from .plugin_version import PluginVersion


def _plugin_directories(root: Path) -> List[Path]:
    """返回官方与第三方插件的一级目录，顺序稳定。"""
    directories: List[Path] = []
    for scope in ("plugin", "custom_plugin"):
        parent = root / scope
        if not parent.is_dir():
            continue
        directories.extend(
            path for path in sorted(parent.iterdir())
            if path.is_dir() and not path.name.startswith("_")
        )
    return directories


def install_all_plugins(
    root: Path,
    preparer_factory: Optional[Callable[[], PluginDependencyPreparer]] = None,
) -> List[Dict[str, Any]]:
    """逐个安装插件依赖，单插件失败不阻断后续插件。"""
    factory = preparer_factory or PluginDependencyPreparer
    results: List[Dict[str, Any]] = []
    for plugin_dir in _plugin_directories(root):
        descriptor = read_plugin_descriptor(plugin_dir)
        if descriptor is None:
            results.append(_dependency_result(plugin_dir, True, "无描述文件，按旧插件兼容"))
            continue
        preparation = factory().prepare(descriptor)
        results.append(_dependency_result(
            plugin_dir,
            preparation.ready,
            preparation.detail,
            list(preparation.missing_dependencies),
        ))
    return results


def _dependency_result(
    plugin_dir: Path,
    success: bool,
    detail: str = "",
    missing: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """构造单插件依赖结果。"""
    return {
        "plugin_dir": str(plugin_dir),
        "plugin_name": plugin_dir.name,
        "success": success,
        "detail": detail,
        "missing_dependencies": missing or [],
    }


def check_plugin_updates(
    root: Path,
    installer: Optional[GitHubPluginInstaller] = None,
) -> List[Dict[str, Any]]:
    """使用现有安装器检查各插件 Release 版本，不自动安装。"""
    updater = installer or GitHubPluginInstaller()
    registry = _load_registry(root)
    results: List[Dict[str, Any]] = []
    for plugin_dir in _plugin_directories(root):
        descriptor = read_plugin_descriptor(plugin_dir)
        if descriptor is None:
            continue
        record = _registry_record(registry, descriptor.descriptor_id)
        results.append(_check_single_plugin(updater, descriptor, record))
    return results


def _check_single_plugin(
    installer: GitHubPluginInstaller,
    descriptor: Any,
    record: Dict[str, Any],
) -> Dict[str, Any]:
    """检查一个插件并返回更新状态和错误信息。"""
    result = _update_result(descriptor, record)
    source_url = record.get("source_url", "")
    if not source_url:
        result["error"] = "没有可用的来源仓库"
        return result
    try:
        source_path = record.get("source_path", "")
        descriptor_path = f"{source_path}/IXPlugin.json" if source_path else "IXPlugin.json"
        releases = installer.get_available_versions(
            source_url, descriptor_path, record.get("source_key_id", ""))
    except Exception as exc:
        result["error"] = str(exc)
        return result
    return _apply_release_result(result, descriptor.version, releases)


def _apply_release_result(
    result: Dict[str, Any],
    current_version: str,
    releases: List[Any],
) -> Dict[str, Any]:
    """比较安装器版本列表并填充最新版本。"""
    current = PluginVersion.from_string(current_version)
    for release in releases:
        try:
            latest = PluginVersion.from_string(release.version)
        except ValueError:
            continue
        result["latest_version"] = release.version
        result["update_available"] = latest > current
        return result
    result["error"] = "未找到可识别的 Release 版本"
    return result


def _load_registry(root: Path) -> Dict[str, Dict[str, Any]]:
    """读取插件注册表；文件缺失时返回空表。"""
    path = root / "config" / "plugin_registry.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data.get("plugins", {}) if isinstance(data, dict) else {}


def _registry_record(registry: Dict[str, Dict[str, Any]], descriptor_id: str) -> Dict[str, Any]:
    """按描述 ID 查找来源记录。"""
    for record in registry.values():
        if record.get("descriptor_id") == descriptor_id:
            return record
    return {}


def _update_result(descriptor: Any, record: Dict[str, Any]) -> Dict[str, Any]:
    """创建不包含网络结果的更新信息。"""
    return {
        "descriptor_id": descriptor.descriptor_id,
        "current_version": descriptor.version,
        "latest_version": "",
        "update_available": False,
        "developer_url": record.get("source_url", ""),
        "error": "",
    }


def main() -> int:
    """通过 JSON 向原生 TUI 返回结果，不渲染任何终端界面。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("install", "check-updates"))
    parser.add_argument("--root", type=Path, default=Path("."))
    arguments = parser.parse_args()
    if arguments.command == "install":
        result = install_all_plugins(arguments.root)
    else:
        result = check_plugin_updates(arguments.root)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
