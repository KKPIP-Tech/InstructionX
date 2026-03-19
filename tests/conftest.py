"""
Pytest 配置文件

提供全局 fixtures 和测试配置。
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture(scope="session")
def project_root_path():
    """返回项目根目录路径"""
    return project_root


@pytest.fixture
def temp_dir():
    """返回临时目录 fixture，在测试结束后自动清理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_qapp():
    """
    Mock QApplication fixture，用于不需要真正 GUI 的测试
    注意：需要真正 GUI 的测试使用 fixtures.app.qapp
    """
    from unittest.mock import patch

    mock_app = MagicMock()
    with patch("PySide6.QWidgets.QApplication.instance", return_value=mock_app):
        yield mock_app


@pytest.fixture
def plugin_dirs(temp_dir):
    """
    创建临时的插件目录结构
    """
    official_dir = temp_dir / "official_plugins"
    thirdparty_dir = temp_dir / "thirdparty_plugins"
    official_dir.mkdir()
    thirdparty_dir.mkdir()

    return {
        "official": official_dir,
        "thirdparty": thirdparty_dir,
        "root": temp_dir,
    }


@pytest.fixture
def sample_plugin_info():
    """返回示例插件信息"""
    return {
        "uuid": "test-plugin-uuid-1234",
        "name": "TestPlugin",
        "version": "1.0.0",
        "description": "A test plugin for unit testing",
        "author": "Test Author",
        "entry": "main",
    }


@pytest.fixture
def mock_plugin():
    """创建一个模拟的插件对象"""
    from core.plugin.plugin_interface import IPlugin
    from core.plugin.plugin_info_interface import IPluginInfo
    from PySide6.QtWidgets import QWidget

    class MockPlugin(IPlugin):
        def __init__(self):
            self._name = "MockPlugin"
            self._version = "1.0.0"
            self._enabled = True

        @property
        def plugin_name(self) -> str:
            return self._name

        @property
        def plugin_version(self) -> str:
            return self._version

        @property
        def plugin_info(self) -> IPluginInfo:
            return None

        def _create_widget(self, parent=None):
            return QWidget(parent)

        def enable(self):
            self._enabled = True

        def disable(self):
            self._enabled = False

        @property
        def is_enabled(self) -> bool:
            return self._enabled

    return MockPlugin()


# 测试标记
def pytest_configure(config):
    """注册自定义标记"""
    config.addinivalue_line("markers", "gui: GUI tests requiring Qt application")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "llm: LLM API tests (may incur costs)")
    config.addinivalue_line("markers", "slow: Slow running tests")
