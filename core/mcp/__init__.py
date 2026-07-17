"""
MCP (Model Context Protocol) 模块

提供真正的 MCP 协议支持，包括：

- MCP Server: 将 InstructionX 的插件工具暴露给外部 MCP Client
- MCP Client: 连接外部 MCP Server，将它们的工具引入本地 LLM
- 插件开发者 API: 简洁的接口供插件注册 MCP 工具和连接外部 Server

核心类:

- MCPManager: 单例协调器，管理 Server 和 Client 生命周期
- MCPHostServer: MCP Server 封装（基于 FastMCP）
- MCPClientManager: 外部 MCP Server 连接管理器
- MCPBridge: 插件 API ↔ MCP Server 双向桥接

配置:

- MCPServerConfig: MCP Server 配置
- MCPRemoteServerConfig: 外部 MCP Server 连接配置

插件开发者接口:

- IMCPTool: 定义 MCP 工具的抽象基类
- IMCPClient: 连接外部 MCP Server 的抽象接口

用法::

    from core.mcp import get_mcp_manager, MCPRemoteServerConfig

    # 获取 MCP Manager
    mcp = get_mcp_manager()

    # 启动 MCP Server（stdio 方式）
    mcp.start_server(transport="stdio")

    # 或 HTTP 方式
    mcp.start_server(transport="streamable-http")

    # 连接外部 MCP Server
    config = MCPRemoteServerConfig(
        server_id="filesystem",
        name="Filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    )
    mcp.connect(config, tool_registry)

插件内访问（通过 PluginServices）::

    class MyPlugin(IPlugin):
        def __init__(self, services=None):
            super().__init__()
            self._mcp_manager = services.mcp_manager if services else None

        def use_mcp_tools(self):
            config = MCPRemoteServerConfig(...)
            # connect() 是同步方法（内部桥接异步事件循环）
            self._mcp_manager.connect(config)
"""

from core.mcp.manager import MCPManager, get_mcp_manager
from core.mcp.config import (
    MCPConfig,
    MCPServerConfig,
    MCPRemoteServerConfig,
)
from core.mcp.server import MCPHostServer
from core.mcp.client import MCPClientManager, MCPServerConnection
from core.mcp.bridge import MCPBridge
from core.mcp.plugin_interface import IMCPTool, IMCPClient

__all__ = [
    # 核心管理器
    "MCPManager",
    "get_mcp_manager",
    # 配置
    "MCPConfig",
    "MCPServerConfig",
    "MCPRemoteServerConfig",
    # Server
    "MCPHostServer",
    # Client
    "MCPClientManager",
    "MCPServerConnection",
    # 桥接
    "MCPBridge",
    # 插件接口
    "IMCPTool",
    "IMCPClient",
]
