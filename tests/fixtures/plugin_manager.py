"""
PluginManager fixture

提供 PluginManager 实例用于插件系统测试。
"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_plugin_dir(tmp_path):
    """
    创建临时的插件目录

    返回包含官方和第三方插件目录的字典
    """
    plugin_dir = tmp_path / "plugins"
    official_dir = plugin_dir / "official"
    thirdparty_dir = plugin_dir / "thirdparty"

    official_dir.mkdir(parents=True)
    thirdparty_dir.mkdir(parents=True)

    # 创建空的 plugin_order.json
    order_file = plugin_dir / "plugin_order.json"
    order_data = {
        "official_plugins": [],
        "thirdparty_plugins": [],
    }
    order_file.write_text(json.dumps(order_data, indent=2), encoding="utf-8")

    return {
        "root": plugin_dir,
        "official": official_dir,
        "thirdparty": thirdparty_dir,
        "order_file": order_file,
    }


@pytest.fixture
def mock_plugin_manager(temp_plugin_dir):
    """
    创建模拟的 PluginManager

    使用临时目录，不加载真实插件
    """
    with patch("core.plugin.manager.DataProvider") as mock_dp, \
         patch("core.plugin.manager.PluginManager._load_plugin_order") as mock_order:

        mock_dp_instance = MagicMock()
        mock_dp.return_value = mock_dp_instance
        mock_order.return_value = {"official_plugins": [], "thirdparty_plugins": []}

        # 延迟导入避免加载真实插件
        from core.plugin.manager import PluginManager

        manager = PluginManager.__new__(PluginManager)
        manager._plugins = {}
        manager._plugin_order = {"official_plugins": [], "thirdparty_plugins": []}
        manager._data_provider = mock_dp_instance

        yield manager


@pytest.fixture
def sample_plugin_module():
    """
    返回一个示例插件模块代码

    可以写入临时文件来测试插件加载
    """
    return '''
"""Sample test plugin"""
from core.plugin.plugin_interface import IPlugin
from core.plugin.plugin_info_interface import IPluginInfo
from PySide6.QtWidgets import QLabel


class SamplePlugin(IPlugin):
    """A sample plugin for testing"""

    @property
    def plugin_name(self) -> str:
        return "SamplePlugin"

    @property
    def plugin_version(self) -> str:
        return "1.0.0"

    @property
    def plugin_info(self) -> IPluginInfo:
        return None

    def _create_widget(self, parent=None):
        return QLabel("Sample Plugin Widget", parent)

    def enable(self):
        pass

    def disable(self):
        pass

    @property
    def is_enabled(self) -> bool:
        return True


# 插件入口函数
def get_plugin() -> IPlugin:
    return SamplePlugin()
'''


@pytest.fixture
def plugin_with_deps(temp_plugin_dir, sample_plugin_module):
    """
    创建一个带依赖的测试插件

    返回插件路径和依赖信息
    """
    plugin_dir = temp_plugin_dir["official"] / "test_plugin"
    plugin_dir.mkdir()

    # 写入插件代码
    (plugin_dir / "main.py").write_text(sample_plugin_module, encoding="utf-8")

    # 写入插件信息
    info = {
        "uuid": "test-plugin-with-deps",
        "name": "TestPluginWithDeps",
        "version": "1.0.0",
        "description": "Test plugin with dependencies",
        "author": "Test",
        "entry": "main",
        "dependencies": ["core"],
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(info), encoding="utf-8")

    return {
        "path": plugin_dir,
        "info": info,
    }
