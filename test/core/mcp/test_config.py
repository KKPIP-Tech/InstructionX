"""pytest tests for core/mcp/config.py"""

import pytest


class TestMCPServerConfig:
    """Tests for MCPServerConfig.to_dict / from_dict."""

    def test_default_values(self):
        """Verify default values: host, port, transport, enabled."""
        from core.mcp.config import MCPServerConfig

        config = MCPServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8765
        assert config.transport == "stdio"
        assert config.enabled is True

    def test_to_dict(self):
        """to_dict() produces correct dict."""
        from core.mcp.config import MCPServerConfig

        config = MCPServerConfig(
            host="0.0.0.0",
            port=9000,
            transport="streamable-http",
            enabled=False,
        )
        d = config.to_dict()
        assert d["host"] == "0.0.0.0"
        assert d["port"] == 9000
        assert d["transport"] == "streamable-http"
        assert d["enabled"] is False

    def test_from_dict(self):
        """from_dict() correctly deserializes."""
        from core.mcp.config import MCPServerConfig

        data = {
            "host": "192.168.1.1",
            "port": 8080,
            "transport": "stdio",
            "enabled": True,
        }
        config = MCPServerConfig.from_dict(data)
        assert config.host == "192.168.1.1"
        assert config.port == 8080
        assert config.transport == "stdio"
        assert config.enabled is True

    def test_from_dict_with_overrides(self):
        """from_dict() uses defaults for missing keys."""
        from core.mcp.config import MCPServerConfig

        data = {"host": "localhost"}
        config = MCPServerConfig.from_dict(data)
        assert config.host == "localhost"
        assert config.port == 8765  # default
        assert config.transport == "stdio"  # default
        assert config.enabled is True  # default

    def test_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves all fields."""
        from core.mcp.config import MCPServerConfig

        original = MCPServerConfig(
            host="10.0.0.1",
            port=9999,
            transport="streamable-http",
            enabled=False,
        )
        restored = MCPServerConfig.from_dict(original.to_dict())
        assert restored.host == original.host
        assert restored.port == original.port
        assert restored.transport == original.transport
        assert restored.enabled == original.enabled


class TestMCPRemoteServerConfig:
    """Tests for MCPRemoteServerConfig.to_dict / from_dict."""

    def test_required_fields(self):
        """Verify server_id and name are required (no defaults)."""
        from core.mcp.config import MCPRemoteServerConfig

        # server_id and name are required positional args
        config = MCPRemoteServerConfig(
            server_id="test-server",
            name="Test Server",
        )
        assert config.server_id == "test-server"
        assert config.name == "Test Server"

    def test_default_values(self):
        """Verify defaults: transport, enabled, args."""
        from core.mcp.config import MCPRemoteServerConfig

        config = MCPRemoteServerConfig(
            server_id="test",
            name="Test",
        )
        assert config.transport == "streamable-http"
        assert config.enabled is True
        assert config.args == []

    def test_to_dict_stdio(self):
        """to_dict() preserves stdio fields."""
        from core.mcp.config import MCPRemoteServerConfig

        config = MCPRemoteServerConfig(
            server_id="stdio-server",
            name="Stdio Server",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem"],
            env={"HOME": "/Users/test"},
        )
        d = config.to_dict()
        assert d["server_id"] == "stdio-server"
        assert d["transport"] == "stdio"
        assert d["command"] == "npx"
        assert d["args"] == ["-y", "@modelcontextprotocol/server-filesystem"]
        assert d["env"] == {"HOME": "/Users/test"}

    def test_to_dict_http(self):
        """to_dict() preserves HTTP fields."""
        from core.mcp.config import MCPRemoteServerConfig

        config = MCPRemoteServerConfig(
            server_id="http-server",
            name="HTTP Server",
            transport="streamable-http",
            url="https://mcp.example.com",
            auth_token="secret-token",
        )
        d = config.to_dict()
        assert d["url"] == "https://mcp.example.com"
        assert d["auth_token"] == "secret-token"

    def test_to_dict_excludes_none_url(self):
        """to_dict() omits None values from output."""
        from core.mcp.config import MCPRemoteServerConfig

        config = MCPRemoteServerConfig(
            server_id="test",
            name="Test",
            url=None,
        )
        d = config.to_dict()
        assert "url" not in d or d.get("url") is None

    def test_from_dict(self):
        """from_dict() correctly deserializes all fields."""
        from core.mcp.config import MCPRemoteServerConfig

        data = {
            "server_id": "from-dict-server",
            "name": "From Dict Server",
            "transport": "stdio",
            "command": "python",
            "args": ["-m", "server"],
            "env": {"DEBUG": "1"},
            "url": None,
            "auth_token": None,
            "enabled": False,
        }
        config = MCPRemoteServerConfig.from_dict(data)
        assert config.server_id == "from-dict-server"
        assert config.transport == "stdio"
        assert config.command == "python"
        assert config.enabled is False

    def test_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves all fields."""
        from core.mcp.config import MCPRemoteServerConfig

        original = MCPRemoteServerConfig(
            server_id="roundtrip",
            name="Roundtrip",
            transport="stdio",
            command="npx",
            args=["-y", "server"],
            env={"KEY": "value"},
            url=None,
            auth_token=None,
            enabled=True,
        )
        restored = MCPRemoteServerConfig.from_dict(original.to_dict())
        assert restored.server_id == original.server_id
        assert restored.name == original.name
        assert restored.transport == original.transport
        assert restored.command == original.command
        assert restored.args == original.args
        assert restored.env == original.env
        assert restored.enabled == original.enabled


class TestMCPConfig:
    """Tests for MCPConfig.to_dict / from_dict."""

    def test_default_server(self):
        """Verify default MCPServerConfig is created."""
        from core.mcp.config import MCPConfig

        config = MCPConfig()
        assert config.server is not None
        assert config.server.host == "127.0.0.1"
        assert config.server.port == 8765

    def test_default_remote_servers(self):
        """Verify empty list by default."""
        from core.mcp.config import MCPConfig

        config = MCPConfig()
        assert config.remote_servers == []

    def test_to_dict(self):
        """to_dict() produces nested serialization."""
        from core.mcp.config import MCPConfig, MCPServerConfig, MCPRemoteServerConfig

        config = MCPConfig(
            server=MCPServerConfig(host="0.0.0.0", port=9000),
            remote_servers=[
                MCPRemoteServerConfig(server_id="remote1", name="Remote 1"),
            ],
        )
        d = config.to_dict()
        assert d["server"]["host"] == "0.0.0.0"
        assert d["server"]["port"] == 9000
        assert len(d["remote_servers"]) == 1
        assert d["remote_servers"][0]["server_id"] == "remote1"

    def test_from_dict(self):
        """from_dict() correctly deserializes nested config."""
        from core.mcp.config import MCPConfig

        data = {
            "server": {"host": "localhost", "port": 7000},
            "remote_servers": [
                {"server_id": "r1", "name": "Remote 1"},
                {"server_id": "r2", "name": "Remote 2"},
            ],
        }
        config = MCPConfig.from_dict(data)
        assert config.server.host == "localhost"
        assert config.server.port == 7000
        assert len(config.remote_servers) == 2
        assert config.remote_servers[0].server_id == "r1"

    def test_from_dict_empty_remote_servers(self):
        """from_dict() handles empty remote_servers list."""
        from core.mcp.config import MCPConfig

        data = {"server": {}, "remote_servers": []}
        config = MCPConfig.from_dict(data)
        assert config.remote_servers == []

    def test_roundtrip(self):
        """to_dict -> from_dict roundtrip preserves all fields."""
        from core.mcp.config import MCPConfig, MCPServerConfig, MCPRemoteServerConfig

        original = MCPConfig(
            server=MCPServerConfig(host="1.2.3.4", port=1234),
            remote_servers=[
                MCPRemoteServerConfig(
                    server_id="remote",
                    name="Remote",
                    transport="stdio",
                    command="npx",
                    args=["-y", "server"],
                ),
            ],
        )
        restored = MCPConfig.from_dict(original.to_dict())
        assert restored.server.host == original.server.host
        assert restored.server.port == original.server.port
        assert len(restored.remote_servers) == 1
        assert restored.remote_servers[0].server_id == "remote"
