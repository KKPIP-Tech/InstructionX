"""pytest tests for core/mcp/bridge.py"""

import pytest
from unittest.mock import MagicMock, patch


class TestMCPBridge:
    """Tests for MCPBridge initialization."""

    def test_init_stores_manager(self):
        """Verify manager is stored."""
        from core.mcp.bridge import MCPBridge

        mock_manager = MagicMock()
        bridge = MCPBridge(mock_manager)

        assert bridge._manager is mock_manager

    def test_init_synced_tools_empty(self):
        """Verify _synced_tools is empty dict."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge(MagicMock())

        assert isinstance(bridge._synced_tools, dict)
        assert len(bridge._synced_tools) == 0


class TestMCPBridgeSyncPluginAPI:
    """Tests for MCPBridge.sync_plugin_api_to_mcp_server()."""

    def test_sync_plugin_api_server_not_init(self):
        """Verify graceful handling when server is None."""
        from core.mcp.bridge import MCPBridge

        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None

        bridge = MCPBridge(mock_manager)
        bridge.sync_plugin_api_to_mcp_server()

        # Should not raise, just return

    def test_sync_plugin_api_skips_already_synced(self, mocker):
        """Verify already synced tools are skipped."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge._synced_tools["already-synced"] = True

        # Mock PluginManager
        mock_pm = MagicMock()
        mock_pm.get_all_function_tools.return_value = [
            {"type": "function", "function": {"name": "already-synced"}}
        ]

        with patch("core.mcp.bridge.get_plugin_manager", return_value=mock_pm):
            bridge.sync_plugin_api_to_mcp_server()

        # Should not call add_tool for already synced
        mock_server.add_tool.assert_not_called()

    def test_sync_plugin_api_parses_plugin_id_method_name(self, mocker):
        """Verify 'plugin_id.method_name' parsing."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)

        # Mock PluginManager
        mock_pm = MagicMock()
        mock_pm.get_all_function_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "my-plugin.my-method",
                    "description": "Test",
                    "parameters": {},
                },
            }
        ]

        with patch("core.mcp.bridge.get_plugin_manager", return_value=mock_pm):
            bridge.sync_plugin_api_to_mcp_server()

        mock_server.add_tool.assert_called_once()
        call_kwargs = mock_server.add_tool.call_args[1]
        assert call_kwargs["plugin_id"] == "my-plugin"
        assert call_kwargs["method_name"] == "my-method"

    def test_sync_plugin_api_skips_invalid_name_format(self, mocker):
        """Verify names without '.' are skipped."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)

        # Mock PluginManager
        mock_pm = MagicMock()
        mock_pm.get_all_function_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "invalid-name-no-dot",
                    "description": "Test",
                    "parameters": {},
                },
            }
        ]

        with patch("core.mcp.bridge.get_plugin_manager", return_value=mock_pm):
            bridge.sync_plugin_api_to_mcp_server()

        # Should not call add_tool for invalid format
        mock_server.add_tool.assert_not_called()

    def test_get_synced_tool_count_initial(self):
        """Verify count starts at 0."""
        from core.mcp.bridge import MCPBridge

        bridge = MCPBridge(MagicMock())

        assert bridge.get_synced_tool_count() == 0

    def test_get_synced_tool_count_after_sync(self, mocker):
        """Verify count increases after sync."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)

        # Mock PluginManager
        mock_pm = MagicMock()
        mock_pm.get_all_function_tools.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "plugin.tool1",
                    "description": "Tool 1",
                    "parameters": {},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "plugin.tool2",
                    "description": "Tool 2",
                    "parameters": {},
                },
            },
        ]

        with patch("core.mcp.bridge.get_plugin_manager", return_value=mock_pm):
            bridge.sync_plugin_api_to_mcp_server()

        assert bridge.get_synced_tool_count() == 2


class TestMCPBridgeSyncNewTool:
    """Tests for MCPBridge.sync_new_plugin_tool()."""

    def test_sync_new_plugin_tool_adds_to_server(self):
        """Verify server.add_tool is called."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge.sync_new_plugin_tool(
            plugin_id="test-plugin",
            method_name="test-method",
            description="Test description",
            parameters={"type": "object"},
        )

        mock_server.add_tool.assert_called_once()

    def test_sync_new_plugin_tool_marks_as_synced(self):
        """Verify tool is marked in _synced_tools."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge.sync_new_plugin_tool(
            plugin_id="test-plugin",
            method_name="test-method",
            description="Test",
            parameters={},
        )

        assert bridge._synced_tools.get("test-plugin.test-method") is True

    def test_sync_new_plugin_tool_skips_already_synced(self):
        """Verify duplicate skip."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge._synced_tools["test-plugin.test-method"] = True

        bridge.sync_new_plugin_tool(
            plugin_id="test-plugin",
            method_name="test-method",
            description="Test",
            parameters={},
        )

        # Should not call add_tool again
        mock_server.add_tool.assert_not_called()

    def test_sync_new_plugin_tool_server_not_init(self):
        """Verify no-op when server is None."""
        from core.mcp.bridge import MCPBridge

        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None

        bridge = MCPBridge(mock_manager)
        # Should not raise
        bridge.sync_new_plugin_tool(
            plugin_id="test-plugin",
            method_name="test-method",
            description="Test",
            parameters={},
        )


class TestMCPBridgeRemoveTool:
    """Tests for MCPBridge.remove_plugin_tool()."""

    def test_remove_plugin_tool_calls_server_remove_tool(self):
        """Verify server.remove_tool is called."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge._synced_tools["test-plugin__test-method"] = True

        bridge.remove_plugin_tool("test-plugin", "test-method")

        mock_server.remove_tool.assert_called_once_with("test-plugin__test-method")

    def test_remove_plugin_tool_removes_from_synced_tools(self):
        """Verify tool removed from _synced_tools."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        bridge._synced_tools["test-plugin.test-method"] = True

        bridge.remove_plugin_tool("test-plugin", "test-method")

        assert "test-plugin.test-method" not in bridge._synced_tools

    def test_remove_plugin_tool_server_not_init(self):
        """Verify no-op when server is None."""
        from core.mcp.bridge import MCPBridge

        mock_manager = MagicMock()
        mock_manager.get_server.return_value = None

        bridge = MCPBridge(mock_manager)
        # Should not raise
        bridge.remove_plugin_tool("test-plugin", "test-method")

    def test_remove_plugin_tool_not_in_synced(self):
        """Verify no error when tool not in _synced_tools."""
        from core.mcp.bridge import MCPBridge

        mock_server = MagicMock()
        mock_manager = MagicMock()
        mock_manager.get_server.return_value = mock_server

        bridge = MCPBridge(mock_manager)
        # Tool not in _synced_tools
        # Should not raise
        bridge.remove_plugin_tool("test-plugin", "test-method")
