"""MCP 配置模型，覆盖连接、暴露边界、TLS 和 DPAPI 凭据存储。"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Literal

from core.github.secret_vault import DPAPI_PREFIX, create_default_secret_vault
from core.llm.secure_keys import decode_secret

# MCP Server 默认监听地址（仅本机回环）
DEFAULT_MCP_HOST = "127.0.0.1"
# MCP Server 默认监听端口
DEFAULT_MCP_PORT = 8765
# Streamable HTTP 无活动请求会话的最大空闲时间（秒）
DEFAULT_MCP_SESSION_IDLE_TIMEOUT = 1800.0
# Streamable HTTP 同时保留的最大会话数
DEFAULT_MCP_MAX_SESSIONS = 10000
# 每客户端每分钟默认最大请求数
DEFAULT_MCP_MAX_REQUESTS_PER_MINUTE = 60


@dataclass
class MCPServerConfig:
    """MCP Server 配置（暴露本地工具给外部 MCP Client）

    Attributes:
        auth_token: HTTP 模式下的 Bearer 认证令牌；None 表示不启用认证
                    （仅建议在本机回环地址下使用）。
        exposed_plugins: 允许暴露为 MCP 工具的插件 ID 白名单；
                         None 表示暴露全部插件（向后兼容默认行为）。
        allowed_hosts: 允许的 HTTP/WebSocket Host 头白名单；None 表示不限制。
        session_idle_timeout: Streamable HTTP 无活动请求会话的空闲超时秒数；
                              None 表示禁用空闲回收。
        max_sessions: Streamable HTTP 最大并发保留会话数；
                      None 表示不限制。
        max_requests_per_minute: 每客户端每分钟请求上限；None 表示禁用限流。
        tls_certfile/tls_keyfile: 对外 HTTP 的 TLS 证书与私钥，必须成对配置。
    """
    host: str = DEFAULT_MCP_HOST
    port: int = DEFAULT_MCP_PORT
    transport: Literal["stdio", "streamable-http"] = "stdio"
    enabled: bool = True
    auth_token: Optional[str] = None
    exposed_plugins: Optional[List[str]] = None
    allowed_hosts: Optional[List[str]] = None
    session_idle_timeout: Optional[float] = DEFAULT_MCP_SESSION_IDLE_TIMEOUT
    max_sessions: Optional[int] = DEFAULT_MCP_MAX_SESSIONS
    max_requests_per_minute: Optional[int] = DEFAULT_MCP_MAX_REQUESTS_PER_MINUTE
    tls_certfile: Optional[str] = None
    tls_keyfile: Optional[str] = None

    def to_dict(self) -> Dict:
        """序列化配置；token 使用 Windows DPAPI，不采用 Base64 作为安全边界。"""
        return {
            "host": self.host,
            "port": self.port,
            "transport": self.transport,
            "enabled": self.enabled,
            "auth_token": (
                create_default_secret_vault().encrypt(self.auth_token)
                if self.auth_token is not None
                else None
            ),
            "exposed_plugins": self.exposed_plugins,
            "allowed_hosts": self.allowed_hosts,
            "session_idle_timeout": self.session_idle_timeout,
            "max_sessions": self.max_sessions,
            "max_requests_per_minute": self.max_requests_per_minute,
            "tls_certfile": self.tls_certfile,
            "tls_keyfile": self.tls_keyfile,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPServerConfig":
        """从配置文件 dict 反序列化

        auth_token 优先按 ``dpapi:v1:`` 密文解密，兼容旧 ``b64:`` 混淆串；
        无前缀的旧版明文配置原样使用，首次保存自动升级为 DPAPI 密文。

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
                create_default_secret_vault().decrypt(stored_token)
                if stored_token is not None and stored_token.startswith(DPAPI_PREFIX)
                else decode_secret(stored_token)
            ),
            exposed_plugins=data.get("exposed_plugins"),
            allowed_hosts=data.get("allowed_hosts"),
            session_idle_timeout=data.get(
                "session_idle_timeout", DEFAULT_MCP_SESSION_IDLE_TIMEOUT),
            max_sessions=data.get("max_sessions", DEFAULT_MCP_MAX_SESSIONS),
            max_requests_per_minute=data.get(
                "max_requests_per_minute", DEFAULT_MCP_MAX_REQUESTS_PER_MINUTE),
            tls_certfile=data.get("tls_certfile"),
            tls_keyfile=data.get("tls_keyfile"),
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

        auth_token 使用 Windows DPAPI 加密输出；None 保持为 None。

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
                create_default_secret_vault().encrypt(self.auth_token)
                if self.auth_token is not None
                else None
            ),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MCPRemoteServerConfig":
        """从配置文件 dict 反序列化

        auth_token 优先按 ``dpapi:v1:`` 密文解密，兼容旧 ``b64:`` 混淆串；
        无前缀的旧版明文配置原样使用，首次保存自动升级为 DPAPI 密文。

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
                create_default_secret_vault().decrypt(stored_token)
                if stored_token is not None and stored_token.startswith(DPAPI_PREFIX)
                else decode_secret(stored_token)
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
