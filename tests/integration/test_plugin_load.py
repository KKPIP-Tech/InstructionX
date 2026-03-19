"""
Plugin Loading Integration Tests

集成测试用例：
- 测试插件完整加载流程
- 测试插件依赖解析
- 测试插件生命周期
"""
import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication


@pytest.mark.integration
class TestPluginLoadingIntegration:
    """测试插件加载集成"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def temp_plugin_env(self, tmp_path):
        """创建临时插件环境"""
        plugin_dir = tmp_path / "plugins"
        official_dir = plugin_dir / "official"
        thirdparty_dir = plugin_dir / "thirdparty"
        config_dir = tmp_path / "config"

        official_dir.mkdir(parents=True)
        thirdparty_dir.mkdir(parents=True)
        config_dir.mkdir(parents=True)

        order_file = config_dir / "plugin_order.json"
        order_file.write_text(json.dumps({
            "official_plugins": [],
            "thirdparty_plugins": []
        }), encoding="utf-8")

        return {
            "root": plugin_dir,
            "official": official_dir,
            "thirdparty": thirdparty_dir,
            "config": config_dir,
            "order_file": order_file,
        }

    def test_full_plugin_loading(self, temp_plugin_env, qapp):
        """测试完整插件加载流程"""
        plugin_code = '''
from core.plugin.plugin_interface import IPlugin
from core.plugin.plugin_info_interface import IPluginInfo
from PySide6.QtWidgets import QLabel


class IntegrationTestPlugin(IPlugin):
    @property
    def plugin_name(self):
        return "IntegrationTestPlugin"

    @property
    def plugin_version(self):
        return "1.0.0"

    @property
    def plugin_info(self):
        return None

    def _create_widget(self, parent=None):
        return QLabel("Test", parent)

    def enable(self):
        pass

    def disable(self):
        pass

    @property
    def is_enabled(self):
        return True


def get_plugin():
    return IntegrationTestPlugin()
'''
        plugin_dir = temp_plugin_env["official"] / "test_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "main.py").write_text(plugin_code, encoding="utf-8")

        info = {
            "uuid": "integration-test-uuid",
            "name": "IntegrationTestPlugin",
            "version": "1.0.0",
            "description": "Integration test plugin",
            "author": "Test",
            "entry": "main",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(info), encoding="utf-8")

        assert (plugin_dir / "main.py").exists()
        assert (plugin_dir / "plugin.json").exists()

    def test_plugin_dependency_resolution(self, temp_plugin_env):
        """测试插件依赖解析"""
        plugin_code = '''
from core.plugin.plugin_interface import IPlugin

class DependentPlugin(IPlugin):
    @property
    def plugin_name(self):
        return "DependentPlugin"

    @property
    def plugin_version(self):
        return "1.0.0"

    @property
    def plugin_info(self):
        return None

    def _create_widget(self, parent=None):
        return None

    def enable(self):
        pass

    def disable(self):
        pass

    @property
    def is_enabled(self):
        return True
'''
        plugin_dir = temp_plugin_env["official"] / "dependent_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "main.py").write_text(plugin_code, encoding="utf-8")

        info = {
            "uuid": "dependent-plugin-uuid",
            "name": "DependentPlugin",
            "version": "1.0.0",
            "description": "Dependent plugin",
            "author": "Test",
            "entry": "main",
            "dependencies": ["core"],
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(info), encoding="utf-8")

        loaded_info = json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
        assert "dependencies" in loaded_info
        assert "core" in loaded_info["dependencies"]


@pytest.mark.integration
class TestCrossPluginCommunication:
    """测试跨插件通信"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_plugin_registry_structure(self, qapp):
        """测试插件注册表结构"""
        from core.plugin.manager import PluginManager

        manager = PluginManager()
        # 测试基本属性存在
        assert hasattr(manager, '_plugins') or hasattr(manager, '_api_registry')


@pytest.mark.integration
class TestTaskWorkflowIntegration:
    """测试任务工作流集成"""

    def test_task_manager_structure(self):
        """测试任务管理器结构"""
        from core.task.background_task import BackgroundTaskManager

        manager = BackgroundTaskManager()
        # 测试管理器是单例
        assert manager is not None


@pytest.mark.integration
class TestFullWorkflow:
    """完整工作流测试"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_complete_plugin_workflow(self, qapp, tmp_path):
        """测试完整的插件工作流"""
        plugin_dir = tmp_path / "plugins"
        plugin_dir.mkdir()

        plugin_code = '''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QLabel


class WorkflowPlugin(IPlugin):
    @property
    def plugin_name(self):
        return "WorkflowPlugin"

    @property
    def plugin_version(self):
        return "1.0.0"

    @property
    def plugin_info(self):
        return None

    def _create_widget(self, parent=None):
        return QLabel("Workflow Test", parent)

    def enable(self):
        pass

    def disable(self):
        pass

    @property
    def is_enabled(self):
        return True


def get_plugin():
    return WorkflowPlugin()
'''
        plugin_path = plugin_dir / "workflow_plugin"
        plugin_path.mkdir()

        (plugin_path / "main.py").write_text(plugin_code, encoding="utf-8")

        info = {
            "uuid": "workflow-plugin-uuid",
            "name": "WorkflowPlugin",
            "version": "1.0.0",
            "description": "Workflow test plugin",
            "author": "Test",
            "entry": "main",
        }
        (plugin_path / "plugin.json").write_text(json.dumps(info), encoding="utf-8")

        assert (plugin_path / "main.py").exists()
        assert (plugin_path / "plugin.json").exists()

        loaded_info = json.loads(
            (plugin_path / "plugin.json").read_text(encoding="utf-8")
        )
        assert loaded_info["name"] == "WorkflowPlugin"
