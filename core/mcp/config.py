"""
MCP 配置管理

定义 MCP Server 和外部 MCP Server 连接的配置数据结构。

安全说明：
    auth_token 在「配置文件读写边界」使用 core.llm.secure_keys 的
    Base64 混淆机制（``b64:`` 前缀）存储，内存中始终为明文；
    读取时无前缀的值按明文原样返回，向后兼容旧版明文配置。
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Literal

from core.llm.secure_keys import encode_secret, decode_secret

# MCP Server 默认监听地址（仅本机回环）
DEFAULT_MCP_HOST = "127.0.0.1"
# MCP Server 默认监听端口
DEFAULT_MCP_PORT = 8765


@dataclass
class MCPServerConfig:
    """MCP Server 配置（暴露本地工具给外部 MCP Client）

    Attributes:
        auth_token: HTTP 模式下的 Bearer 认证令牌；None 表示不启用认证
                    （仅建议在本机回环地址下使用）。
        exposed_plugins: 允许暴露为 MCP 工具的插件 ID 白名单；
                         None 表示暴露全部插件（向后兼容默认行为）。
        allowed_hosts: 允许的 HTTP Host 头白名单（保留项，暂未强制校验）。
    """
    host: str = DEFAULT_MCP_HOST
    port: int = DEFAULT_MCP_PORT
    transport: Literal["stdio", "streamable-http"] = "stdio"
    enabled: bool = True
    auth_token: Optional[str] = None
    exposed_plugins: Optional[List[str]] = None
    allowed_hosts: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        """序列化为可写入配置文件的 dict

        auth_token 统一以 ``b64:`` 混淆格式输出（防瞥视，非加密）；
        None 保持为 None。

        Returns:
            Dict: 配置字典，可直接 json.dump 写入 mcp_config.json
        """
        return {
            "host": self.host,
            "port": self.port,
            "transport": self.transport,
            "enabled": self.enabled,
            "auth_token": (
                encode_secret(self.auth_token)
                if self.auth_token is not None
                else None
            ),
            "exposed_plugins": self.exposed_plugins,
            "allowed_hosts": self.allowed_hosts,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPServerConfig":
        """从配置文件 dict 反序列化

        auth_token 兼容两种存储格式：``b64:`` 混淆串自动解混淆，
        无前缀的旧版明文配置原样使用（首次保存自动升级为混淆格式）。

        Args:
            data: 从 mcp_config.json 读出的配置字典

        Returns:
            MCPServerConfig: 配置实例（auth_token 为明文）
        """
        stored_token = data.get("auth_token")
        return cls(
            host=data.get("host", DEFAULT_MCP_HOST),
            port=data.get("port", DEFAULT_MCP_PORT),
            transport=data.get("transport", "stdio"),
            enabled=data.get("enabled", True),
            auth_token=(
                decode_secret(stored_token)
                if stored_token is not None
                else None
            ),
            exposed_plugins=data.get("exposed_plugins"),
            allowed_hosts=data.get("allowed_hosts"),
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
        """序列化为可写入配置文件的 dict

        auth_token 统一以 ``b64:`` 混淆格式输出（防瞥视，非加密）；
        None 保持为 None。

        Returns:
            Dict: 配置字典，可直接 json.dump 写入 mcp_config.json
        """
        return {
            "server_id": self.server_id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": self.args,
            "env": self.env,
            "url": self.url,
            "auth_token": (
                encode_secret(self.auth_token)
                if self.auth_token is not None
                else None
            ),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPRemoteServerConfig":
        """从配置文件 dict 反序列化

        auth_token 兼容两种存储格式：``b64:`` 混淆串自动解混淆，
        无前缀的旧版明文配置原样使用（首次保存自动升级为混淆格式）。

        Args:
            data: 从 mcp_config.json 读出的配置字典

        Returns:
            MCPRemoteServerConfig: 配置实例（auth_token 为明文）
        """
        stored_token = data.get("auth_token")
        return cls(
            server_id=data["server_id"],
            name=data["name"],
            transport=data.get("transport", "streamable-http"),
            command=data.get("command"),
            args=data.get("args", []),
            env=data.get("env"),
            url=data.get("url"),
            auth_token=(
                decode_secret(stored_token)
                if stored_token is not None
                else None
            ),
            enabled=data.get("enabled", True),
        )


@dataclass
class MCPConfig:
    """MCP 整体配置"""
    server: MCPServerConfig = field(default_factory=MCPServerConfig)
    remote_servers: List[MCPRemoteServerConfig] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """序列化整体配置为可写入配置文件的 dict

        Returns:
            Dict: 包含 server 与 remote_servers 的配置字典
        """
        return {
            "server": self.server.to_dict(),
            "remote_servers": [s.to_dict() for s in self.remote_servers],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPConfig":
        """从配置文件 dict 反序列化整体配置

        Args:
            data: 从 mcp_config.json 读出的配置字典

        Returns:
            MCPConfig: 整体配置实例
        """
        return cls(
            server=MCPServerConfig.from_dict(data.get("server", {})),
            remote_servers=[
                MCPRemoteServerConfig.from_dict(s)
                for s in data.get("remote_servers", [])
            ],
        )
