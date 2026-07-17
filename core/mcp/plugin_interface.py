"""
MCP 插件开发者 API

提供插件开发者使用的高层 MCP 接口：
- IMCPTool: 定义 MCP 工具的抽象基类
- IMCPClient: 连接到外部 MCP Server 的抽象接口
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    # MCPRemoteServerConfig 实际定义在 core.mcp.config
    # （core.mcp.client 保留了向后兼容的 re-export）
    from core.mcp.config import MCPRemoteServerConfig


class IMCPTool(ABC):
    """MCP 工具定义接口

    插件开发者可继承此类定义一个 MCP 工具。
    注意：当前框架不会自动扫描并注册 IMCPTool 实例；如需暴露为 MCP 工具，
    请通过 information.py 的 service_api 声明，或在 on_plugin_loaded() 中手动通过
    self._services.mcp_manager 注册。

    用法::

        from core.mcp.plugin_interface import IMCPTool

        class MyMCPTool(IMCPTool):
            @property
            def mcp_tool_name(self) -> str:
                return "my_tool"

            @property
            def mcp_tool_description(self) -> str:
                return "执行某个操作"

            @property
            def mcp_tool_parameters(self) -> Dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "输入文本"}
                    },
                    "required": ["input"]
                }

            async def mcp_invoke(self, **kwargs) -> Any:
                return f"处理了: {kwargs.get('input')}"
    """

    @property
    @abstractmethod
    def mcp_tool_name(self) -> str:
        """工具名称，必须唯一"""
        ...

    @property
    @abstractmethod
    def mcp_tool_description(self) -> str:
        """工具描述，LLM 会看到此描述"""
        ...

    @property
    @abstractmethod
    def mcp_tool_parameters(self) -> Dict[str, Any]:
        """JSON Schema 格式的参数定义"""
        ...

    @abstractmethod
    async def mcp_invoke(self, **kwargs: Any) -> Any:
        """执行工具逻辑（必须是 async）

        Args:
            **kwargs: 由 LLM 根据 mcp_tool_parameters 生成的参数

        Returns:
            工具执行结果，会被返回给调用方
        """
        ...


class IMCPClient(ABC):
    """MCP Client 访问接口（预留接口）

    供插件开发者连接外部 MCP Server 并调用其工具。
    通过 PluginServices.mcp_client 注入。

    注意：这是预留的抽象接口，当前框架注入的是具体类
    MCPClientManager，其 connect()/disconnect() 为**同步方法**
    （内部通过专用事件循环线程桥接异步 MCP SDK），调用时请勿加 await。

    用法::

        class MyPlugin(IPlugin):
            def __init__(self, services=None):
                super().__init__()
                self._mcp_client = services.mcp_client if services else None

            def connect_to_external(self):
                from core.mcp.config import MCPRemoteServerConfig
                config = MCPRemoteServerConfig(
                    server_id="filesystem",
                    name="Filesystem",
                    transport="stdio",
                    command="npx",
                    args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                )
                self._mcp_client.connect(config)  # 同步方法
    """

    @abstractmethod
    async def connect(
        self,
        config: "MCPRemoteServerConfig",
    ) -> str:
        """连接到外部 MCP Server，返回 server_id"""
        ...

    @abstractmethod
    async def disconnect(self, server_id: str) -> None:
        """断开与指定外部 MCP Server 的连接"""
        ...

    @abstractmethod
    def list_connected_servers(self) -> List[str]:
        """返回已连接的 server_id 列表"""
        ...

    @abstractmethod
    def list_tools(self, server_id: str) -> List[str]:
        """列出指定 Server 上的工具名称列表"""
        ...
