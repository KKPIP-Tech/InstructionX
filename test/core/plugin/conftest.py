"""
Plugin module test fixtures

提供 Plugin 模块测试所需的 fixtures。
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ─── Plugin Manager Reset ───────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_plugin_manager():
    """
    重置 PluginManager 单例，保证每个测试隔离。

    在测试前重置 `_instance` 和 `_initialized`，测试后再次重置。
    """
    import core.plugin.manager

    # 测试前重置
    core.plugin.manager.PluginManager._instance = None
    core.plugin.manager.PluginManager._initialized = False

    yield

    # 测试后清理
    core.plugin.manager.PluginManager._instance = None
    core.plugin.manager.PluginManager._initialized = False


# ─── Mock Plugin Services ───────────────────────────────────────────────────

@pytest.fixture
def mock_plugin_services():
    """
    Mock PluginServices，用于测试插件初始化时传入 services。

    提供常用的 mock 服务对象。
    """
    services = MagicMock()
    services.data_provider = MagicMock()
    services.task_manager = MagicMock()
    services.llm_provider = MagicMock()
    services.mcp_client = MagicMock()
    services.mcp_server = MagicMock()
    return services
