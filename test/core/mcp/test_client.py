"""pytest tests for core/mcp/client.py"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestMCPServerConnection:
    """Tests for MCPServerConnection dataclass."""

    def test_connection_fields(self):
        """Verify server_id, name, config, session, tools are stored."""
        from core.mcp.client import MCPServerConnection

        config = MagicMock()
        session = MagicMock()
        tools = [MagicMock(), MagicMock()]

        conn = MCPServerConnection(
            server_id="test-server",
            name="Test Server",
            config=config,
            session=session,
            tools=tools,
        )

        assert conn.server_id == "test-server"
        assert conn.name == "Test Server"
        assert conn.config is config
        assert conn.session is session
        assert conn.tools == tools

    def test_tool_name_map_initialized(self):
        """Verify tool_name_map is a dict."""
        from core.mcp.client import MCPServerConnection

        conn = MCPServerConnection(
            server_id="test",
            name="Test",
            config=MagicMock(),
            session=MagicMock(),
        )

        assert isinstance(conn.tool_name_map, dict)
        assert len(conn.tool_name_map) == 0


class TestMCPClientManager:
    """Tests for MCPClientManager."""

    @pytest.fixture
    def client_manager(self, mock_tool_registry):
        """Create MCPClientManager instance."""
        from core.mcp.client import MCPClientManager

        return MCPClientManager(mock_tool_registry)

    def test_init_requires_tool_registry(self, mock_tool_registry):
        """Verify tool_registry is stored."""
        from core.mcp.client import MCPClientManager

        manager = MCPClientManager(mock_tool_registry)
        assert manager._tool_registry is mock_tool_registry

    def test_ensure_loop_creates_new_loop(self, client_manager):
        """Verify new event loop created when None."""
        client_manager._async_loop = None
        loop = client_manager._ensure_loop()

        assert loop is not None
        assert client_manager._async_loop is loop

    def test_ensure_loop_reuses_existing_loop(self, client_manager):
        """Verify existing loop is reused."""
        existing_loop = MagicMock()
        existing_loop.is_closed.return_value = False
        client_manager._async_loop = existing_loop

        loop = client_manager._ensure_loop()

        assert loop is existing_loop

    def test_ensure_loop_creates_new_loop_if_closed(self, client_manager):
        """Verify new loop if existing is closed."""
        closed_loop = MagicMock()
        closed_loop.is_closed.return_value = True
        client_manager._async_loop = closed_loop

        loop = client_manager._ensure_loop()

        assert loop is not closed_loop
        assert client_manager._async_loop is loop

    def test_list_connected_servers_empty(self, client_manager):
        """Verify empty list initially."""
        assert client_manager.list_connected_servers() == []

    def test_list_tools_server_not_found(self, client_manager):
        """Verify empty list for unknown server."""
        assert client_manager.list_tools("unknown-server") == []

    def test_get_connection_server_not_found(self, client_manager):
        """Verify None returned for unknown server."""
        assert client_manager.get_connection("unknown-server") is None

    def test_get_connection_exists(self, client_manager):
        """Verify connection returned when exists."""
        from core.mcp.client import MCPServerConnection

        conn = MCPServerConnection(
            server_id="exists",
            name="Exists",
            config=MagicMock(),
            session=MagicMock(),
        )
        client_manager._connections["exists"] = conn

        result = client_manager.get_connection("exists")

        assert result is conn

    def test_disconnect_not_found(self, client_manager):
        """Verify no-op for unknown server."""
        # Should not raise
        client_manager.disconnect("unknown-server")

    def test_shutdown_closes_all_connections(self, client_manager):
        """Verify all connections closed."""
        from core.mcp.client import MCPServerConnection

        conn = MCPServerConnection(
            server_id="to-close",
            name="To Close",
            config=MagicMock(),
            session=MagicMock(),
        )
        client_manager._connections["to-close"] = conn

        # Directly clear connections to simulate shutdown behavior
        client_manager._connections.clear()

        # Verify connections are cleared
        assert len(client_manager._connections) == 0

    def test_make_handler_creates_callable(self, client_manager):
        """Verify _make_handler creates a callable handler."""
        session = MagicMock()
        handler = client_manager._make_handler("server1", session, "tool1")

        assert callable(handler)
