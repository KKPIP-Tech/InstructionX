"""pytest tests for core/mcp/server.py"""

import pytest
from unittest.mock import MagicMock, patch


class TestMCPHostServer:
    """Tests for MCPHostServer initialization."""

    def test_init_default_values(self):
        """Verify name='InstructionX', host='127.0.0.1', port=8765."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()

        assert server._name == "InstructionX"
        assert server._host == "127.0.0.1"
        assert server._port == 8765
        assert server._session_idle_timeout == 1800.0
        assert server._max_sessions == 10000

    def test_init_stores_parameters(self):
        """Verify parameters are stored."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer(
            name="TestServer",
            host="0.0.0.0",
            port=9000,
            session_idle_timeout=60.0,
            max_sessions=12,
        )

        assert server._name == "TestServer"
        assert server._host == "0.0.0.0"
        assert server._port == 9000
        assert server._session_idle_timeout == 60.0
        assert server._max_sessions == 12

    def test_init_fastmcp_passes_session_limits(self, mocker):
        """FastMCP 必须接收明确配置的会话回收和数量限制。"""
        from core.mcp.server import MCPHostServer

        fastmcp = mocker.patch("core.mcp.server.FastMCP")
        server = MCPHostServer(
            name="LimitedServer",
            host="127.0.0.1",
            port=8788,
            session_idle_timeout=45.0,
            max_sessions=8,
        )

        server._init_fastmcp()

        fastmcp.assert_called_once_with(
            "LimitedServer",
            host="127.0.0.1",
            port=8788,
            session_idle_timeout=45.0,
            max_sessions=8,
        )

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"session_idle_timeout": 0}, "session_idle_timeout"),
            ({"session_idle_timeout": "bad"}, "session_idle_timeout"),
            ({"max_sessions": -1}, "max_sessions"),
            ({"max_sessions": 1.5}, "max_sessions"),
        ],
    )
    def test_init_rejects_non_positive_session_limits(
        self, kwargs, message
    ):
        """启用资源限制时，非正数必须在构造阶段拒绝。"""
        from core.mcp.server import MCPHostServer

        with pytest.raises(ValueError, match=message):
            MCPHostServer(**kwargs)

    def test_init_running_false(self):
        """Verify _running is False initially."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()

        assert server._running is False

    def test_init_tool_registry_empty(self):
        """Verify _tool_registry is empty dict."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()

        assert isinstance(server._tool_registry, dict)
        assert len(server._tool_registry) == 0

    def test_init_fastmcp_none(self):
        """Verify _fastmcp is None (lazy init)."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()

        assert server._fastmcp is None


class TestMCPHostServerToolManagement:
    """Tests for MCPHostServer tool management."""

    def test_add_tool_records_in_registry_directly(self):
        """Verify tool is added to _tool_registry without FastMCP."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        # Manually add tool info to registry (simulating what add_tool does)
        server._tool_registry["test-tool"] = {
            "plugin_id": "test-plugin",
            "method_name": "test-method",
        }

        assert "test-tool" in server._tool_registry
        assert server._tool_registry["test-tool"]["plugin_id"] == "test-plugin"
        assert server._tool_registry["test-tool"]["method_name"] == "test-method"

    def test_remove_tool_removes_from_registry(self):
        """Verify tool removed from _tool_registry."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        # Manually add tool info to registry
        server._tool_registry["to-remove"] = {
            "plugin_id": "test-plugin",
            "method_name": "test-method",
        }
        assert "to-remove" in server._tool_registry

        server.remove_tool("to-remove")

        assert "to-remove" not in server._tool_registry

    def test_remove_tool_not_found(self):
        """Verify no error when tool not found."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        # Should not raise
        server.remove_tool("nonexistent-tool")

    def test_registered_tools_returns_copy(self):
        """Verify returns dict copy, not reference."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        server._tool_registry["test-tool"] = {
            "plugin_id": "test-plugin",
            "method_name": "test-method",
        }

        tools = server.registered_tools
        tools["modified"] = True

        # Original should be unchanged
        assert "modified" not in server._tool_registry


class TestMCPHostServerLifecycle:
    """Tests for MCPHostServer lifecycle."""

    def test_run_stdio_already_running(self):
        """Verify warning and no-op if already running."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        server._running = True

        # Should not raise, just warn
        server.run_stdio()

        # _running should still be True
        assert server._running is True

    def test_run_http_already_running(self):
        """Verify warning and no-op if already running."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        server._running = True

        # Should not raise, just warn
        server.run_http()

        # Thread should not be started when already running
        assert server._thread is None

    def test_stop_sets_running_false(self):
        """Verify _running is False after stop."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        server._running = True

        server.stop()

        assert server._running is False

    def test_is_running_property(self):
        """Verify property returns _running status."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        assert server.is_running is False

        server._running = True
        assert server.is_running is True


class TestMCPHostServerDeferredRegistration:
    """Tests for deferred tool registration."""

    def test_tool_registry_stores_deferred_info(self):
        """Verify deferred tools info is stored in registry."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        # Simulate deferred tool registration
        server._tool_registry["deferred-tool"] = {
            "plugin_id": "test-plugin",
            "method_name": "test-method",
            "deferred": {
                "description": "Test",
                "parameters": {},
                "handler": MagicMock(),
            },
        }

        tool_info = server._tool_registry.get("deferred-tool", {})
        assert "deferred" in tool_info
        assert tool_info["deferred"]["description"] == "Test"

    def test_remove_tool_clears_deferred_info(self):
        """Verify deferred info is cleared when tool is removed."""
        from core.mcp.server import MCPHostServer

        server = MCPHostServer()
        server._tool_registry["deferred-tool"] = {
            "plugin_id": "test-plugin",
            "method_name": "test-method",
            "deferred": {},
        }

        server.remove_tool("deferred-tool")

        assert "deferred-tool" not in server._tool_registry
