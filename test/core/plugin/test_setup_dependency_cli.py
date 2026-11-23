"""Setup 原生 TUI 的插件依赖与更新后端测试。"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from core.plugin.setup_dependency_cli import install_all_plugins, check_plugin_updates
from core.plugin.plugin_startup import PluginDependencyPreparation
from core.plugin.github_plugin_installer import ReleaseInfo


def _plugin(root: Path, scope: str, directory: str, plugin_id: str, version: str) -> None:
    plugin_dir = root / scope / directory
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "IXPlugin.json").write_text(json.dumps({
        "id": plugin_id,
        "name": {"en": plugin_id},
        "version": version,
        "description": {"en": "demo"},
        "homepage": "https://github.com/example/demo",
        "dependencies": {},
    }), encoding="utf-8")


def test_install_continues_after_single_plugin_failure(tmp_path):
    """一个插件依赖失败时仍处理后续插件并返回逐项结果。"""
    _plugin(tmp_path, "plugin", "broken", "broken", "release.1.0.0")
    _plugin(tmp_path, "custom_plugin", "working", "working", "release.1.0.0")
    preparer = MagicMock()
    preparer.prepare.side_effect = [
        PluginDependencyPreparation(
            ready=False,
            reason="dependency_install_failed",
            detail="simulated failure",
            missing_dependencies=("bad-package",),
        ),
        PluginDependencyPreparation(ready=True),
    ]

    results = install_all_plugins(tmp_path, preparer_factory=lambda: preparer)

    assert len(results) == 2
    assert not results[0]["success"]
    assert results[0]["detail"] == "simulated failure"
    assert results[0]["missing_dependencies"] == ["bad-package"]
    assert results[1]["success"]


def test_update_check_uses_release_versions_and_source(tmp_path):
    """更新检查使用安装器返回的 Release 版本，并标记可更新项。"""
    _plugin(tmp_path, "plugin", "demo", "demo", "release.1.0.0")
    (tmp_path / "config").mkdir()
    (tmp_path / "config/plugin_registry.json").write_text(json.dumps({
        "version": 2,
        "plugins": {
            "uuid": {
                "descriptor_id": "demo",
                "source_url": "https://github.com/example/demo",
                "source_path": "plugins/demo",
                "source_key_id": "key",
            }
        },
    }), encoding="utf-8")
    installer = MagicMock()
    installer.get_available_versions.return_value = [
        ReleaseInfo(tag="release-v1.1.0", name="1.1", version="release.1.1.0"),
        ReleaseInfo(tag="release-v1.0.0", name="1.0", version="release.1.0.0"),
    ]

    results = check_plugin_updates(tmp_path, installer=installer)

    assert len(results) == 1
    assert results[0]["update_available"]
    assert results[0]["latest_version"] == "release.1.1.0"
    installer.get_available_versions.assert_called_once_with(
        "https://github.com/example/demo", "plugins/demo/IXPlugin.json", "key")
