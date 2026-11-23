"""插件启动依赖准备与显式失败诊断测试。

覆盖启动前自动安装依赖、安装失败、入口导入失败、缺少模块，以及仓库
根目录中的普通资源文件夹不得被误判为插件。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.plugin.dependency_manager import (
    DependencyCheckResult,
    DependencyInstallResult,
)
from core.plugin.manager import PluginManager
from core.plugin.plugin_module_loader import (
    PluginModuleLoadError,
    PluginModuleLoader,
)
from core.plugin.plugin_registry import PluginRegistry
from core.plugin.plugin_startup import (
    FAILURE_DEPENDENCY_CHECK,
    FAILURE_DEPENDENCY_INSTALL,
    FAILURE_INVALID_ENTRY,
    FAILURE_MISSING_MODULE,
    PluginDescriptorSnapshot,
    PluginDependencyPreparer,
    is_plugin_candidate,
    read_plugin_descriptor,
)


@pytest.fixture(autouse=True)
def _mock_startup_logger(mocker):
    """隔离启动诊断模块的日志写入。"""
    mocker.patch("core.plugin.plugin_startup.LoggerManager")


def _write_plugin(
    plugin_dir: Path,
    *,
    version: str = "release.1.0.0",
    dependencies: dict | None = None,
    entrance_code: str | None = None,
) -> None:
    """创建带描述文件的最小测试插件。"""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "IXPlugin.json").write_text(
        json.dumps({
            "id": plugin_dir.name,
            "name": plugin_dir.name,
            "version": version,
            "dependencies": dependencies or {},
        }),
        encoding="utf-8",
    )
    (plugin_dir / "entrance.py").write_text(
        entrance_code or "",
        encoding="utf-8",
    )


class TestPluginCandidateDetection:
    """验证插件候选目录识别，避免 docs 等目录触发启动误报。"""

    @pytest.mark.parametrize(
        "filename",
        ["IXPlugin.json", "entrance.py", ".plugin_info.json"],
    )
    def test_plugin_markers_make_directory_candidate(
        self, tmp_path, filename
    ):
        """包含任一插件特征文件的目录应视为插件候选。"""
        plugin_dir = tmp_path / "candidate"
        plugin_dir.mkdir()
        (plugin_dir / filename).write_text("{}", encoding="utf-8")

        assert is_plugin_candidate(plugin_dir) is True

    @pytest.mark.parametrize("dirname", ["docs", "assets", ".github"])
    def test_plain_resource_directory_is_not_candidate(
        self, tmp_path, dirname
    ):
        """普通资源目录不是插件候选。"""
        resource_dir = tmp_path / dirname
        resource_dir.mkdir()
        (resource_dir / "README.md").write_text("resource", encoding="utf-8")

        assert is_plugin_candidate(resource_dir) is False

    def test_manager_ignores_plain_resource_directories(self, tmp_path):
        """普通资源目录不得进入失败列表或触发提示框。"""
        manager = PluginManager()
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "README.md").write_text("docs", encoding="utf-8")

        assert manager._load_plugin_from_directory(docs_dir) is None
        assert manager.get_plugin_load_failures() == []


class TestPluginDependencyPreparer:
    """验证插件启动前的依赖准备逻辑。"""

    def test_satisfied_dependencies_skip_installation(self):
        """依赖已满足时不得调用安装。"""
        manager = MagicMock()
        manager.check_dependencies.return_value = DependencyCheckResult(
            True, [])
        preparer = PluginDependencyPreparer(manager)
        descriptor = PluginDescriptorSnapshot(
            "demo", "Demo", "release.1.0.0", {"demo": ">=1"})

        result = preparer.prepare(descriptor)

        assert result.ready is True
        manager.install_dependencies.assert_not_called()

    def test_missing_dependencies_are_installed_and_verified(self):
        """缺失依赖应先安装，并在安装后再次检查。"""
        manager = MagicMock()
        manager.check_dependencies.side_effect = [
            DependencyCheckResult(False, ["demo"]),
            DependencyCheckResult(True, []),
        ]
        manager.install_dependencies.return_value = (
            DependencyInstallResult(True))
        preparer = PluginDependencyPreparer(manager)
        descriptor = PluginDescriptorSnapshot(
            "demo", "Demo", "release.1.0.0", {"demo": ">=1"})

        result = preparer.prepare(descriptor)

        assert result.ready is True
        manager.install_dependencies.assert_called_once()
        assert manager.check_dependencies.call_count == 2

    def test_install_failure_returns_structured_result(self):
        """安装失败应保留原因和缺失依赖，供界面提示。"""
        manager = MagicMock()
        manager.check_dependencies.return_value = DependencyCheckResult(
            False, ["demo"])
        manager.install_dependencies.return_value = (
            DependencyInstallResult(
                False, "network failed", ["demo"]))
        preparer = PluginDependencyPreparer(manager)
        descriptor = PluginDescriptorSnapshot(
            "demo", "Demo", "release.1.0.0", {"demo": ">=1"})

        result = preparer.prepare(descriptor)

        assert result.ready is False
        assert result.reason == FAILURE_DEPENDENCY_INSTALL
        assert result.detail == "network failed"
        assert result.missing_dependencies == ("demo",)

    def test_post_install_verification_failure_is_not_accepted(self):
        """安装命令成功但复查仍缺依赖时不得继续导入插件。"""
        manager = MagicMock()
        manager.check_dependencies.side_effect = [
            DependencyCheckResult(False, ["demo"]),
            DependencyCheckResult(False, ["demo"]),
        ]
        manager.install_dependencies.return_value = (
            DependencyInstallResult(True))
        preparer = PluginDependencyPreparer(manager)
        descriptor = PluginDescriptorSnapshot(
            "demo", "Demo", "release.1.0.0", {"demo": ">=1"})

        result = preparer.prepare(descriptor)

        assert result.ready is False
        assert result.reason == FAILURE_DEPENDENCY_INSTALL
        assert result.missing_dependencies == ("demo",)

    def test_check_exception_returns_structured_result(self):
        """依赖检查异常应转换为可展示失败，而不是静默跳过插件。"""
        manager = MagicMock()
        manager.check_dependencies.side_effect = RuntimeError("check failed")
        preparer = PluginDependencyPreparer(manager)
        descriptor = PluginDescriptorSnapshot(
            "demo", "Demo", "release.1.0.0", {"demo": ">=1"})

        result = preparer.prepare(descriptor)

        assert result.ready is False
        assert result.reason == FAILURE_DEPENDENCY_CHECK
        assert "check failed" in result.detail


class TestPluginStartupFailures:
    """验证依赖、入口与导入失败均形成结构化记录。"""

    def test_reload_syncs_manually_replaced_plugin_version(
        self, tmp_path, mocker
    ):
        """重载时应以被手动替换目录中的实际版本更新注册表。"""
        official_dir = tmp_path / "plugin"
        thirdparty_dir = tmp_path / "custom_plugin"
        thirdparty_dir.mkdir()
        plugin_dir = official_dir / "manual-plugin"
        entrance_code = (
            "from core.plugin.plugin_interface import IPlugin\n"
            "class ManualPlugin(IPlugin):\n"
            "    @property\n"
            "    def plugin_name(self):\n"
            "        return 'Manual Plugin'\n"
            "    def _create_widget(self, parent=None, "
            "data_provider=None):\n"
            "        return None\n"
        )
        _write_plugin(
            plugin_dir,
            version="release.1.0.0",
            entrance_code=entrance_code,
        )
        manager = PluginManager()
        manager.official_plugin_dir = official_dir
        manager.thirdparty_plugin_dir = thirdparty_dir
        manager.registry = PluginRegistry(tmp_path / "config")
        mocker.patch.object(
            manager, "_create_plugin_services", return_value=MagicMock())
        mocker.patch("core.plugin.manager.get_language_manager")
        manager.load_plugins()
        plugin_id = manager.get_all_plugins()[0].plugin_id
        assert manager.registry.get(plugin_id)["version"] == "release.1.0.0"

        _write_plugin(
            plugin_dir,
            version="release.2.0.0",
            entrance_code=entrance_code,
        )
        manager.reload_plugins()

        assert manager.registry.get(plugin_id)["version"] == "release.2.0.0"

    def test_load_plugins_installs_dependencies_before_import(
        self, tmp_path, mocker
    ):
        """完整加载链路应先准备依赖，再导入插件并校准注册表版本。"""
        official_dir = tmp_path / "plugin"
        thirdparty_dir = tmp_path / "custom_plugin"
        thirdparty_dir.mkdir()
        plugin_dir = official_dir / "recoverable-plugin"
        _write_plugin(
            plugin_dir,
            version="release.5.0.0",
            dependencies={"demo": ">=1"},
            entrance_code=(
                "from core.plugin.plugin_interface import IPlugin\n"
                "class RecoverablePlugin(IPlugin):\n"
                "    @property\n"
                "    def plugin_name(self):\n"
                "        return 'Recoverable Plugin'\n"
                "    def _create_widget(self, parent=None, "
                "data_provider=None):\n"
                "        return None\n"
            ),
        )
        dependency_manager = MagicMock()
        dependency_manager.check_dependencies.side_effect = [
            DependencyCheckResult(False, ["demo"]),
            DependencyCheckResult(True, []),
        ]
        dependency_manager.install_dependencies.return_value = (
            DependencyInstallResult(True))
        manager = PluginManager()
        manager.official_plugin_dir = official_dir
        manager.thirdparty_plugin_dir = thirdparty_dir
        manager.registry = PluginRegistry(tmp_path / "config")
        manager._dependency_preparer = PluginDependencyPreparer(
            dependency_manager)
        mocker.patch.object(
            manager, "_create_plugin_services", return_value=MagicMock())
        mocker.patch("core.plugin.manager.get_language_manager")

        manager.load_plugins()

        plugins = manager.get_all_plugins()
        assert [plugin.plugin_name for plugin in plugins] == [
            "Recoverable Plugin"]
        assert manager.get_plugin_load_failures() == []
        dependency_manager.install_dependencies.assert_called_once()
        record = manager.registry.get(plugins[0].plugin_id)
        assert record["version"] == "release.5.0.0"

    def test_dependency_failure_prevents_import_and_is_recorded(
        self, tmp_path
    ):
        """依赖准备失败时不应继续导入，并记录缺失依赖。"""
        plugin_dir = tmp_path / "broken-dependency"
        _write_plugin(
            plugin_dir,
            dependencies={"demo": ">=1"},
            entrance_code="raise AssertionError('must not import')\n",
        )
        manager = PluginManager()
        manager._dependency_preparer = MagicMock()
        manager._dependency_preparer.prepare.return_value = MagicMock(
            ready=False,
            reason=FAILURE_DEPENDENCY_INSTALL,
            detail="install failed",
            missing_dependencies=("demo",),
        )

        result = manager._load_plugin_from_directory(plugin_dir)

        failures = manager.get_plugin_load_failures()
        assert result is None
        assert len(failures) == 1
        assert failures[0].reason == FAILURE_DEPENDENCY_INSTALL
        assert failures[0].missing_dependencies == ("demo",)

    def test_missing_module_import_is_recorded(self, tmp_path):
        """入口导入缺少模块时应记录具体模块名。"""
        plugin_dir = tmp_path / "missing-module"
        _write_plugin(
            plugin_dir,
            entrance_code=(
                "import instructionx_definitely_missing_module\n"),
        )
        manager = PluginManager()

        result = manager._load_plugin_from_directory(plugin_dir)

        failures = manager.get_plugin_load_failures()
        assert result is None
        assert len(failures) == 1
        assert failures[0].reason == FAILURE_MISSING_MODULE
        assert failures[0].missing_module == (
            "instructionx_definitely_missing_module")

    def test_missing_entrance_on_descriptor_directory_is_recorded(
        self, tmp_path
    ):
        """带描述文件但缺少入口的目录应提示入口无效。"""
        plugin_dir = tmp_path / "invalid-entry"
        plugin_dir.mkdir()
        (plugin_dir / "IXPlugin.json").write_text(
            json.dumps({
                "id": "invalid-entry",
                "name": "Invalid Entry",
                "version": "release.1.0.0",
            }),
            encoding="utf-8",
        )
        manager = PluginManager()

        result = manager._load_plugin_from_directory(plugin_dir)

        failures = manager.get_plugin_load_failures()
        assert result is None
        assert failures[0].reason == FAILURE_INVALID_ENTRY


class TestPluginModuleLoader:
    """验证独立入口模块加载器的失败分类。"""

    def test_missing_entrance_raises_invalid_entry(self, tmp_path):
        """入口不存在时分类为入口无效。"""
        with pytest.raises(PluginModuleLoadError) as exc_info:
            PluginModuleLoader().load(tmp_path)

        assert exc_info.value.reason == FAILURE_INVALID_ENTRY


class TestPluginDescriptorReading:
    """验证启动阶段描述文件读取与依赖归一化。"""

    def test_multilingual_name_and_dependencies_are_parsed(self, tmp_path):
        """多语言名称按默认语言解析，依赖原样读取。"""
        plugin_dir = tmp_path / "descriptor"
        plugin_dir.mkdir()
        (plugin_dir / "IXPlugin.json").write_text(
            json.dumps({
                "id": "descriptor",
                "name": {"zh": "中文名称", "en": "English Name"},
                "version": "release.4.5.6",
                "dependencies": {"demo": ">=2"},
            }),
            encoding="utf-8",
        )

        snapshot = read_plugin_descriptor(plugin_dir)

        assert snapshot.name == "中文名称"
        assert snapshot.version == "release.4.5.6"
        assert snapshot.dependencies == {"demo": ">=2"}

    def test_invalid_dependency_entries_are_ignored(self, tmp_path):
        """非字符串依赖项不得进入安装参数。"""
        plugin_dir = tmp_path / "descriptor"
        plugin_dir.mkdir()
        (plugin_dir / "IXPlugin.json").write_text(
            json.dumps({
                "id": "descriptor",
                "name": "Descriptor",
                "version": "release.1.0.0",
                "dependencies": {
                    "valid": ">=1",
                    "invalid": 123,
                },
            }),
            encoding="utf-8",
        )

        snapshot = read_plugin_descriptor(plugin_dir)

        assert snapshot.dependencies == {"valid": ">=1"}

    def test_missing_descriptor_returns_none_for_legacy_plugin(self, tmp_path):
        """旧插件没有描述文件时应返回 None 并继续兼容加载。"""
        plugin_dir = tmp_path / "legacy"
        plugin_dir.mkdir()
        (plugin_dir / "entrance.py").write_text("", encoding="utf-8")

        assert read_plugin_descriptor(plugin_dir) is None
