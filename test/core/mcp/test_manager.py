"""pytest tests for core/mcp/manager.py"""

import json
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mcp_manager(mocker):
    """Create MCPManager with mocked dependencies."""
    # Ensure module-level singleton is reset
    import core.mcp.manager as mcp_module
    mcp_module._module_instance = None

    # Mock the config file operations
    mocker.patch("pathlib.Path.exists", return_value=False)
    mocker.patch("pathlib.Path.mkdir")
    mocker.patch("builtins.open", mocker.mock_open())

    from core.mcp.manager import MCPManager

    return MCPManager()


class TestMCPManagerSingleton:
    """Tests for MCPManager singleton behavior."""

    def test_get_mcp_manager_returns_same_instance(self, mocker):
        """Verify repeated calls return same instance."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import get_mcp_manager, MCPManager

        mcp_module._module_instance = None
        inst1 = get_mcp_manager()
        inst2 = get_mcp_manager()
        assert inst1 is inst2


class TestMCPManagerConfig:
    """Tests for MCPManager config management."""

    def test_load_config_creates_default_if_missing(self, mocker):
        """Verify default config when file missing."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mock_open = mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        # Should have default config
        assert manager.get_config() is not None
        assert manager.get_config().server.host == "127.0.0.1"
        assert manager.get_config().server.port == 8765

    def test_load_config_from_file(self, mocker, tmp_path):
        """Verify loading existing config file."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        config_file = tmp_path / "mcp_config.json"
        config_data = {
            "server": {"host": "0.0.0.0", "port": 9000},
            "remote_servers": [],
        }
        config_file.write_text(json.dumps(config_data))

        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("pathlib.Path.mkdir")

        from core.mcp.manager import MCPManager

        # Patch the _config_file to use our temp path
        manager = MCPManager()
        manager._config_file = config_file
        manager._load_config()

        assert manager.get_config().server.host == "0.0.0.0"
        assert manager.get_config().server.port == 9000

    def test_load_config_handles_corrupt_file(self, mocker, tmp_path):
        """Verify graceful fallback on JSON error."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        config_file = tmp_path / "mcp_config.json"
        config_file.write_text("invalid json content")

        mocker.patch("pathlib.Path.exists", return_value=True)
        mocker.patch("pathlib.Path.mkdir")

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._config_file = config_file
        manager._load_config()

        # Should fall back to defaults
        assert manager.get_config().server.host == "127.0.0.1"
        assert manager.get_config().server.port == 8765

    def test_update_server_config(self, mocker):
        """Verify server config update and save."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager, MCPServerConfig

        manager = MCPManager()
        new_config = MCPServerConfig(host="192.168.1.1", port=8000)
        manager.update_server_config(new_config)

        assert manager.get_config().server.host == "192.168.1.1"
        assert manager.get_config().server.port == 8000

    def test_add_remote_server(self, mocker):
        """Verify adding new remote server."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager, MCPRemoteServerConfig

        manager = MCPManager()
        config = MCPRemoteServerConfig(
            server_id="new-remote",
            name="New Remote",
        )
        manager.add_remote_server(config)

        assert len(manager.get_config().remote_servers) == 1
        assert manager.get_config().remote_servers[0].server_id == "new-remote"

    def test_add_remote_server_duplicate_id_replaces(self, mocker):
        """Verify duplicate server_id replaces existing."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager, MCPRemoteServerConfig

        manager = MCPManager()
        config1 = MCPRemoteServerConfig(server_id="dup", name="First")
        config2 = MCPRemoteServerConfig(server_id="dup", name="Second")
        manager.add_remote_server(config1)
        manager.add_remote_server(config2)

        assert len(manager.get_config().remote_servers) == 1
        assert manager.get_config().remote_servers[0].name == "Second"

    def test_remove_remote_server(self, mocker):
        """Verify removal returns True."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager, MCPRemoteServerConfig

        manager = MCPManager()
        config = MCPRemoteServerConfig(server_id="to-remove", name="Remove Me")
        manager.add_remote_server(config)
        result = manager.remove_remote_server("to-remove")

        assert result is True
        assert len(manager.get_config().remote_servers) == 0

    def test_remove_remote_server_not_found(self, mocker):
        """Verify removal returns False for missing id."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        result = manager.remove_remote_server("nonexistent")

        assert result is False


class TestMCPManagerServerLifecycle:
    """Tests for MCPManager server lifecycle."""

    def test_init_server_creates_mcp_host_server(self, mocker, mock_mcp_sdk):
        """Verify server is created."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        server = manager._init_server()

        assert server is not None
        assert manager.get_server() is server

    def test_init_server_creates_bridge(self, mocker, mock_mcp_sdk):
        """Verify bridge is created."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        assert manager.get_bridge() is not None

    def test_start_server_invalid_transport(self, mocker, mock_mcp_sdk):
        """Verify ValueError for unknown transport."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        with pytest.raises(ValueError, match="Unsupported transport"):
            manager.start_server(transport="invalid-transport")

    def test_stop_server_when_not_running(self, mocker, mock_mcp_sdk):
        """Verify no-op when server not running."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        # stop_server should not raise even when not running
        manager.stop_server()

    def test_is_server_running(self, mocker, mock_mcp_sdk):
        """Verify status check."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.is_server_running() is False

    def test_get_server_url_when_not_started(self, mocker, mock_mcp_sdk):
        """Verify empty string when server None."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.get_server_url() == ""

    def test_get_server_config(self, mocker):
        """Verify returns MCPServerConfig."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        config = manager.get_server_config()

        assert config.host == "127.0.0.1"
        assert config.port == 8765


class TestMCPManagerClientLifecycle:
    """Tests for MCPManager client lifecycle."""

    def test_get_client_manager_requires_tool_registry_on_first_call(self, mocker):
        """Verify ValueError if no tool_registry."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()

        with pytest.raises(ValueError, match="tool_registry required"):
            manager.get_client_manager()

    def test_get_client_manager_returns_same_instance(self, mocker, mock_tool_registry):
        """Verify client manager is singleton."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        client1 = manager.get_client_manager(mock_tool_registry)
        client2 = manager.get_client_manager()

        assert client1 is client2

    def test_list_connected_servers_empty(self, mocker):
        """Verify empty list when no client."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.list_connected_servers() == []

    def test_list_remote_tools_empty(self, mocker):
        """Verify empty list when no client."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.list_remote_tools("any-server") == []


class TestMCPManagerBridge:
    """Tests for MCPManager bridge coordination."""

    def test_get_bridge_returns_none_before_init(self, mocker):
        """Verify bridge is None before server init."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        assert manager.get_bridge() is None

    def test_get_bridge_returns_bridge_after_init(self, mocker, mock_mcp_sdk):
        """Verify bridge exists after server init."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        assert manager.get_bridge() is not None

    def test_sync_plugin_tool_delegates_to_bridge(self, mocker, mock_mcp_sdk):
        """Verify sync_plugin_tool calls bridge."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        bridge = manager.get_bridge()
        bridge.sync_new_plugin_tool = MagicMock()

        manager.sync_plugin_tool(
            plugin_id="test-plugin",
            method_name="test-method",
            description="Test description",
            parameters={"type": "object"},
        )

        bridge.sync_new_plugin_tool.assert_called_once()

    def test_remove_plugin_tool_delegates_to_bridge(self, mocker, mock_mcp_sdk):
        """Verify remove_plugin_tool calls bridge."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        bridge = manager.get_bridge()
        bridge.remove_plugin_tool = MagicMock()

        manager.remove_plugin_tool("test-plugin", "test-method")

        bridge.remove_plugin_tool.assert_called_once_with(
            "test-plugin", "test-method"
        )


class TestMCPManagerShutdown:
    """Tests for MCPManager shutdown."""

    def test_shutdown_stops_server(self, mocker, mock_mcp_sdk):
        """Verify stop_server is called."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        manager._init_server()

        # Mock the server's stop method
        manager._server.stop = MagicMock()

        manager.shutdown()

        manager._server.stop.assert_called_once()

    def test_shutdown_calls_client_manager_shutdown(self, mocker, mock_tool_registry):
        """Verify client manager shutdown."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        client = manager.get_client_manager(mock_tool_registry)
        client.shutdown = MagicMock()

        manager.shutdown()

        client.shutdown.assert_called_once()

    def test_shutdown_when_not_started(self, mocker):
        """Verify no-op when components not initialized."""
        import core.mcp.manager as mcp_module
        mcp_module._module_instance = None

        mocker.patch("pathlib.Path.exists", return_value=False)
        mocker.patch("pathlib.Path.mkdir")
        mocker.patch("builtins.open", mocker.mock_open())

        from core.mcp.manager import MCPManager

        manager = MCPManager()
        # Should not raise
        manager.shutdown()
