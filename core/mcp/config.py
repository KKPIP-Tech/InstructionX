"""
MCP 配置管理

定义 MCP Server 和外部 MCP Server 连接的配置数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Literal


@dataclass
class MCPServerConfig:
    """MCP Server 配置（暴露本地工具给外部 MCP Client）"""
    host: str = "127.0.0.1"
    port: int = 8765
    transport: Literal["stdio", "streamable-http"] = "stdio"
    enabled: bool = True

    def to_dict(self) -> Dict:
        return {
            "host": self.host,
            "port": self.port,
            "transport": self.transport,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPServerConfig":
        return cls(
            host=data.get("host", "127.0.0.1"),
            port=data.get("port", 8765),
            transport=data.get("transport", "stdio"),
            enabled=data.get("enabled", True),
        )


@dataclass
class MCPRemoteServerConfig:
    """外部 MCP Server 连接配置（MCP Client 模式）"""
    server_id: str
    name: str
    transport: Literal["stdio", "streamable-http"] = "streamable-http"
    # stdio 方式
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    # streamable-http 方式
    url: Optional[str] = None
    # 认证
    auth_token: Optional[str] = None
    enabled: bool = True

    def to_dict(self) -> Dict:
        return {
            "server_id": self.server_id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "auth_token": self.auth_token,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPRemoteServerConfig":
        return cls(
            server_id=data["server_id"],
            name=data["name"],
            transport=data.get("transport", "streamable-http"),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env"),
            url=data.get("url"),
            auth_token=data.get("auth_token"),
            enabled=data.get("enabled", True),
        )


@dataclass
class MCPConfig:
    """MCP 整体配置"""
    server: MCPServerConfig = field(default_factory=MCPServerConfig)
    remote_servers: List[MCPRemoteServerConfig] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "server": self.server.to_dict(),
            "remote_servers": [s.to_dict() for s in self.remote_servers],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPConfig":
        return cls(
            server=MCPServerConfig.from_dict(data.get("server", {})),
            remote_servers=[
                MCPRemoteServerConfig.from_dict(s)
                for s in data.get("remote_servers", [])
            ],
        )
