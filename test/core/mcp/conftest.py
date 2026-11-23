"""
MCP module test fixtures

提供 MCP 模块测试所需的全部 fixtures。
"""
import pytest
from unittest.mock import MagicMock, AsyncMock


# ─── MCP Manager Singleton Reset ────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_mcp_manager():
    """Reset the MCPManager module-level singleton before and after each test."""
    import core.mcp.manager as mcp_manager_module

    # Reset module-level singleton before test
    mcp_manager_module._module_instance = None

    yield

    # Cleanup after test
    mcp_manager_module._module_instance = None


# ─── Mock Tool Registry ──────────────────────────────────────────────────────

@pytest.fixture
def mock_tool_registry():
    """Mock ToolRegistry for client tests."""
    registry = MagicMock()
    registry.register = MagicMock()
    registry.unregister = MagicMock()
    return registry


# ─── Mock MCP SDK ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_mcp_sdk(mocker):
    """
    Mock MCP SDK imports (FastMCP, ClientSession, stdio_client, etc.).

    These are expensive imports that require the actual MCP package.
    """
    # Mock FastMCP
    mock_fastmcp = MagicMock()
    mock_fastmcp.run = MagicMock()
    mock_fastmcp._tool_manager = MagicMock()
    mock_fastmcp._tool_manager._tools = {}
    mock_fastmcp._tool_manager._tool_functions = {}

    try:
        mocker.patch("mcp.server.fastmcp.FastMCP", return_value=mock_fastmcp)
    except Exception:
        pass

    # Mock ClientSession
    mock_session = MagicMock()
    mock_session.initialize = AsyncMock()
    mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
    mock_session.call_tool = AsyncMock(return_value=MagicMock(content=[]))
    mock_session.close = AsyncMock()

    try:
        mocker.patch("mcp.client.session.ClientSession", return_value=mock_session)
        mocker.patch("mcp.client.stdio.stdio_client")
        mocker.patch("mcp.client.stdio.StdioServerParameters")
        mocker.patch("mcp.client.streamable_http.streamable_http_client")
    except Exception:
        pass

    return {
        "fastmcp": mock_fastmcp,
        "session": mock_session,
    }


# ─── Mock MCPHostServer (avoid actual server startup) ────────────────────────

@pytest.fixture
def mock_mcp_host_server():
    """Mock MCPHostServer to avoid actual server startup in tests."""
    mock_server = MagicMock()
    mock_server.is_running = False
    mock_server.run_stdio = MagicMock()
    mock_server.run_http = MagicMock()
    mock_server.stop = MagicMock()
    mock_server.add_tool = MagicMock()
    mock_server.remove_tool = MagicMock()
    mock_server.get_server_url = MagicMock(return_value="http://127.0.0.1:8765")
    mock_server.registered_tools = {}
    return mock_server
