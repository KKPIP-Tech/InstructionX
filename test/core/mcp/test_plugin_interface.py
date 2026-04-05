"""pytest tests for core/mcp/plugin_interface.py"""

import pytest
from unittest.mock import MagicMock


class TestIMCPTool:
    """Tests for IMCPTool abstract interface."""

    def test_abstract_methods_require_override(self):
        """Verify IMCPTool cannot be instantiated without implementing abstract methods."""
        from core.mcp.plugin_interface import IMCPTool

        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            IMCPTool()

    def test_concrete_implementation(self):
        """Verify a proper subclass with all methods implemented can be instantiated."""
        from core.mcp.plugin_interface import IMCPTool

        class ConcreteMCPTool(IMCPTool):
            @property
            def mcp_tool_name(self) -> str:
                return "test_tool"

            @property
            def mcp_tool_description(self) -> str:
                return "A test tool"

            @property
            def mcp_tool_parameters(self) -> dict:
                return {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string"},
                    },
                }

            async def mcp_invoke(self, **kwargs):
                return f"result: {kwargs.get('input')}"

        tool = ConcreteMCPTool()
        assert tool.mcp_tool_name == "test_tool"
        assert tool.mcp_tool_description == "A test tool"
        assert "input" in tool.mcp_tool_parameters["properties"]


class TestIMCPClient:
    """Tests for IMCPClient abstract interface."""

    def test_abstract_methods_require_override(self):
        """Verify IMCPClient cannot be instantiated without implementing abstract methods."""
        from core.mcp.plugin_interface import IMCPClient

        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            IMCPClient()

    def test_concrete_implementation(self):
        """Verify a proper subclass with all methods implemented can be instantiated."""
        from core.mcp.plugin_interface import IMCPClient

        class ConcreteMCPClient(IMCPClient):
            def __init__(self):
                self._connected_servers = []
                self._tools = {}

            async def connect(self, config):
                self._connected_servers.append(config.server_id)
                return config.server_id

            async def disconnect(self, server_id: str):
                if server_id in self._connected_servers:
                    self._connected_servers.remove(server_id)

            def list_connected_servers(self):
                return self._connected_servers

            def list_tools(self, server_id: str):
                return self._tools.get(server_id, [])

        client = ConcreteMCPClient()
        # Verify abstract methods are implemented
        assert hasattr(client, "connect")
        assert hasattr(client, "disconnect")
        assert hasattr(client, "list_connected_servers")
        assert hasattr(client, "list_tools")
