"""
MCP Client 管理器

管理到外部 MCP Server 的连接，并将它们的工具注册到 ToolRegistry。
支持 stdio 和 streamable-http 两种连接方式。
"""

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# 延迟导入 MCP SDK 类型，避免在模块加载时强依赖
_MCP_SESSION: Any = None
_stdio_client: Any = None
_stdio_params: Any = None
_streamable_http_client: Any = None


def _ensure_mcp_imports() -> None:
    global _MCP_SESSION, _stdio_client, _stdio_params, _streamable_http_client
    if _MCP_SESSION is not None:
        return
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client, StdioServerParameters
    from mcp.client.streamable_http import streamable_http_client
    _MCP_SESSION = ClientSession
    _stdio_client = stdio_client
    _stdio_params = StdioServerParameters
    _streamable_http_client = streamable_http_client


@dataclass
class MCPServerConnection:
    """单个外部 MCP Server 连接"""
    server_id: str
    name: str
    config: Any  # MCPRemoteServerConfig
    session: Any  # ClientSession
    tools: List[Any] = field(default_factory=list)
    # 工具名称 -> (名称空间名, 原始工具名)
    tool_name_map: Dict[str, tuple] = field(default_factory=dict)


class MCPClientManager:
    """管理所有外部 MCP Server 连接

    将外部 MCP 工具注册到应用内的 ToolRegistry，
    使 LLM 可以透明地调用外部 MCP 工具。

    Args:
        tool_registry: 应用内的 ToolRegistry 实例
    """

    def __init__(self, tool_registry: Any):
        self._connections: Dict[str, MCPServerConnection] = {}
        self._tool_registry = tool_registry
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保有一个可用的异步事件循环"""
        if self._async_loop is None or self._async_loop.is_closed():
            self._async_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._async_loop)
        return self._async_loop

    def _make_handler(
        self,
        server_id: str,
        session: Any,
        original_tool_name: str,
    ) -> Callable:
        """创建调用外部 MCP 工具的 handler"""
        def handler(**kwargs: Any) -> Any:
            loop = self._ensure_loop()
            try:
                future = asyncio.run_coroutine_threadsafe(
                    session.call_tool(original_tool_name, kwargs or {}),
                    loop,
                )
                result = future.result(timeout=60)
                # 解析 CallToolResult
                if hasattr(result, "content"):
                    texts = [
                        c.text for c in result.content
                        if hasattr(c, "text")
                    ]
                    return "\n".join(texts) if texts else str(result)
                return str(result)
            except Exception as e:
                logger.error(
                    f"MCP external tool call failed: "
                    f"{server_id}/{original_tool_name}: {e}"
                )
                raise

        return handler

    async def _async_connect(
        self,
        server_id: str,
        config: Any,
    ) -> MCPServerConnection:
        """异步连接到外部 MCP Server"""
        _ensure_mcp_imports()

        session: Optional[Any] = None

        try:
            if config.transport == "stdio":
                params = _stdio_params(
                    command=config.command,
                    args=config.args,
                    env=config.env or {},
                )
                async with _stdio_client(params) as (read, write):
                    async with _MCP_SESSION(read, write) as sess:
                        session = sess
                        await sess.initialize()
                        tools_result = await sess.list_tools()
                        return self._create_connection(
                            server_id, config, sess, tools_result
                        )

            elif config.transport == "streamable-http":
                async with _streamable_http_client(
                    config.url,
                    headers={"Authorization": f"Bearer {config.auth_token}"}
                    if config.auth_token else None,
                ) as sess:
                    session = sess
                    await sess.initialize()
                    tools_result = await sess.list_tools()
                    return self._create_connection(
                        server_id, config, sess, tools_result
                    )

            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

        except Exception as e:
            logger.error(
                f"Failed to connect to MCP server {server_id}: {e}"
            )
            if session is not None:
                try:
                    await session.close()
                except Exception:
                    pass
            raise

    def _create_connection(
        self,
        server_id: str,
        config: Any,
        session: Any,
        tools_result: Any,
    ) -> MCPServerConnection:
        """创建连接对象并注册工具"""
        tools = list(tools_result.tools) if tools_result.tools else []
        conn = MCPServerConnection(
            server_id=server_id,
            name=config.name,
            config=config,
            session=session,
            tools=tools,
        )

        for tool in tools:
            namespaced_name = f"mcp:{server_id}:{tool.name}"
            conn.tool_name_map[tool.name] = (namespaced_name, tool.name)

            self._tool_registry.register(
                name=namespaced_name,
                description=f"[MCP/{config.name}] {tool.description or ''}",
                parameters=tool.inputSchema or {},
                handler=self._make_handler(server_id, session, tool.name),
            )
            logger.debug(
                f"Registered external MCP tool: {namespaced_name}"
            )

        self._connections[server_id] = conn
        return conn

    async def _async_disconnect(self, server_id: str) -> None:
        """异步断开连接"""
        if server_id not in self._connections:
            return

        conn = self._connections[server_id]
        for tool in conn.tools:
            namespaced_name = f"mcp:{server_id}:{tool.name}"
            self._tool_registry.unregister(namespaced_name)

        try:
            await conn.session.close()
        except Exception as e:
            logger.warning(f"Error closing MCP session {server_id}: {e}")

        del self._connections[server_id]
        logger.info(f"Disconnected from MCP server: {server_id}")

    def connect(self, config: Any) -> str:
        """同步连接到外部 MCP Server

        Args:
            config: MCPRemoteServerConfig 实例

        Returns:
            server_id
        """
        loop = self._ensure_loop()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_connect(config.server_id, config),
                loop,
            )
            future.result(timeout=60)
        except Exception as e:
            logger.error(f"MCP connect failed for {config.server_id}: {e}")
            raise

        return config.server_id

    def disconnect(self, server_id: str) -> None:
        """同步断开连接"""
        loop = self._ensure_loop()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_disconnect(server_id),
                loop,
            )
            future.result(timeout=10)
        except Exception as e:
            logger.error(f"MCP disconnect failed for {server_id}: {e}")

    def list_connected_servers(self) -> List[str]:
        """返回已连接的 server_id 列表"""
        return list(self._connections.keys())

    def list_tools(self, server_id: str) -> List[str]:
        """列出指定 Server 上的工具名称列表（带命名空间前缀）"""
        if server_id not in self._connections:
            return []
        conn = self._connections[server_id]
        return [
            f"mcp:{server_id}:{tool.name}"
            for tool in conn.tools
        ]

    def get_connection(self, server_id: str) -> Optional[MCPServerConnection]:
        """获取指定连接的信息"""
        return self._connections.get(server_id)

    def shutdown(self) -> None:
        """关闭所有连接并清理"""
        server_ids = list(self._connections.keys())
        for server_id in server_ids:
            try:
                self.disconnect(server_id)
            except Exception as e:
                logger.warning(f"Error during shutdown for {server_id}: {e}")

        if self._async_loop and not self._async_loop.is_closed():
            self._async_loop.close()
