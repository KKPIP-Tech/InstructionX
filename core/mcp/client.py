"""
MCP Client 管理器

管理到外部 MCP Server 的连接，并将它们的工具注册到 ToolRegistry。
支持 stdio 和 streamable-http 两种连接方式。
"""

import asyncio
import threading
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import logging

# 向后兼容：MCPRemoteServerConfig 实际定义在 core.mcp.config，
# 历史上插件代码从 core.mcp.client 导入，这里保留 re-export。
from core.mcp.config import MCPRemoteServerConfig  # noqa: F401

logger = logging.getLogger(__name__)

# 延迟导入 MCP SDK 类型，避免在模块加载时强依赖
_MCP_SESSION: Any = None
_stdio_client: Any = None
_stdio_params: Any = None
_streamable_http_client: Any = None
_get_default_environment: Any = None


def _ensure_mcp_imports() -> None:
    global _MCP_SESSION, _stdio_client, _stdio_params
    global _streamable_http_client, _get_default_environment
    if _MCP_SESSION is not None:
        return
    from mcp.client.session import ClientSession
    from mcp.client.stdio import (
        stdio_client,
        StdioServerParameters,
        get_default_environment,
    )
    from mcp.client.streamable_http import streamable_http_client
    _MCP_SESSION = ClientSession
    _stdio_client = stdio_client
    _stdio_params = StdioServerParameters
    _streamable_http_client = streamable_http_client
    _get_default_environment = get_default_environment


@dataclass
class MCPServerConnection:
    """单个外部 MCP Server 连接"""
    server_id: str
    name: str
    config: Any  # MCPRemoteServerConfig
    session: Any  # ClientSession
    tools: List[Any] = field(default_factory=list)
    # 净化后的命名空间工具名 -> 原始工具名
    tool_name_map: Dict[str, str] = field(default_factory=dict)
    # 持有传输与 session 上下文管理器的退出栈（disconnect 时关闭）
    exit_stack: Any = None


class MCPClientManager:
    """管理所有外部 MCP Server 连接

    将外部 MCP 工具注册到应用内的 ToolRegistry，
    使 LLM 可以透明地调用外部 MCP 工具。

    Args:
        tool_registry: 应用内的 ToolRegistry 实例
        timeout: 连接/调用/断开的统一超时（秒）
    """

    def __init__(self, tool_registry: Any, timeout: float = 60.0):
        self._connections: Dict[str, MCPServerConnection] = {}
        self._tool_registry = tool_registry
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._timeout = timeout

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """确保有一个在专用 daemon 线程中运行的事件循环

        run_coroutine_threadsafe 需要 loop 处于运行状态，
        因此创建 loop 后立即在专用线程中 run_forever()。
        """
        if self._async_loop is None or self._async_loop.is_closed():
            self._async_loop = asyncio.new_event_loop()
            loop = self._async_loop

            def _run_loop() -> None:
                asyncio.set_event_loop(loop)
                loop.run_forever()

            self._loop_thread = threading.Thread(
                target=_run_loop,
                name="mcp-client-loop",
                daemon=True,
            )
            self._loop_thread.start()
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
                result = future.result(timeout=self._timeout)
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
        """异步连接到外部 MCP Server

        使用 AsyncExitStack 持有传输与 session 的上下文管理器，
        避免 "async with 内 return 导致会话即建即关"；
        exit stack 存入连接对象，disconnect 时统一关闭。
        """
        _ensure_mcp_imports()

        stack = AsyncExitStack()
        try:
            if config.transport == "stdio":
                # env=None 时子进程继承默认环境（含 PATH）；
                # 配置了 env 时与默认环境合并而非替换
                env = None
                if config.env:
                    env = _get_default_environment()
                    env.update(config.env)
                params = _stdio_params(
                    command=config.command,
                    args=config.args,
                    env=env,
                )
                read, write = await stack.enter_async_context(
                    _stdio_client(params)
                )
                session = await stack.enter_async_context(
                    _MCP_SESSION(read, write)
                )
                await session.initialize()
                tools_result = await session.list_tools()
                return self._create_connection(
                    server_id, config, session, tools_result, stack
                )

            elif config.transport == "streamable-http":
                # mcp==1.27.0 的 streamable_http_client 没有 headers 参数，
                # 认证头通过自带 httpx.AsyncClient 传入；
                # 它 yield (read, write, get_session_id) 三元组
                http_client = None
                if config.auth_token:
                    import httpx
                    http_client = await stack.enter_async_context(
                        httpx.AsyncClient(
                            headers={
                                "Authorization": f"Bearer {config.auth_token}"
                            },
                            follow_redirects=True,
                        )
                    )
                read, write, _get_session_id = await stack.enter_async_context(
                    _streamable_http_client(config.url, http_client=http_client)
                )
                session = await stack.enter_async_context(
                    _MCP_SESSION(read, write)
                )
                await session.initialize()
                tools_result = await session.list_tools()
                return self._create_connection(
                    server_id, config, session, tools_result, stack
                )

            else:
                raise ValueError(f"Unsupported transport: {config.transport}")

        except Exception as e:
            logger.error(
                f"Failed to connect to MCP server {server_id}: {e}"
            )
            try:
                await stack.aclose()
            except Exception:
                pass
            raise

    def _create_connection(
        self,
        server_id: str,
        config: Any,
        session: Any,
        tools_result: Any,
        exit_stack: Any = None,
    ) -> MCPServerConnection:
        """创建连接对象并注册工具

        工具命名空间：sanitize_tool_name(f"mcp__{server_id}__{tool_name}")，
        符合 OpenAI function 命名规范 ^[a-zA-Z0-9_-]{1,64}$。
        单个工具注册失败只记 warning，不中断整个连接。
        """
        from core.plugin.manager import sanitize_tool_name

        tools = list(tools_result.tools) if tools_result.tools else []
        conn = MCPServerConnection(
            server_id=server_id,
            name=config.name,
            config=config,
            session=session,
            tools=tools,
            exit_stack=exit_stack,
        )

        for tool in tools:
            namespaced_name = sanitize_tool_name(
                f"mcp__{server_id}__{tool.name}"
            )
            description = f"[MCP/{config.name}] {tool.description or ''}"
            parameters = tool.inputSchema or {}
            handler = self._make_handler(server_id, session, tool.name)

            try:
                self._tool_registry.register(
                    name=namespaced_name,
                    description=description,
                    parameters=parameters,
                    handler=handler,
                )
            except ValueError:
                # 同名冲突（如同 server 重连）：先注销再注册
                try:
                    self._tool_registry.unregister(namespaced_name)
                    self._tool_registry.register(
                        name=namespaced_name,
                        description=description,
                        parameters=parameters,
                        handler=handler,
                    )
                except Exception as e2:
                    logger.warning(
                        f"Failed to register MCP tool {namespaced_name} "
                        f"(after replace attempt): {e2}"
                    )
                    continue
            except Exception as e:
                logger.warning(
                    f"Failed to register MCP tool {namespaced_name}: {e}"
                )
                continue

            conn.tool_name_map[namespaced_name] = tool.name
            logger.debug(
                f"Registered external MCP tool: {namespaced_name}"
            )

        self._connections[server_id] = conn
        return conn

    async def _async_disconnect(self, server_id: str) -> None:
        """异步断开连接"""
        conn = self._connections.get(server_id)
        if conn is None:
            return

        for namespaced_name in list(conn.tool_name_map.keys()):
            try:
                self._tool_registry.unregister(namespaced_name)
            except Exception as e:
                logger.warning(
                    f"Failed to unregister MCP tool {namespaced_name}: {e}"
                )

        # mcp==1.27.0 的 ClientSession 没有 close()，
        # 连接生命周期由 AsyncExitStack 统一关闭
        try:
            if conn.exit_stack is not None:
                await conn.exit_stack.aclose()
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
        if config.server_id in self._connections:
            logger.info(
                f"MCP server {config.server_id} already connected, "
                f"disconnecting before reconnect"
            )
            self.disconnect(config.server_id)

        loop = self._ensure_loop()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_connect(config.server_id, config),
                loop,
            )
            future.result(timeout=self._timeout)
        except Exception as e:
            logger.error(f"MCP connect failed for {config.server_id}: {e}")
            raise

        return config.server_id

    def disconnect(self, server_id: str) -> None:
        """同步断开连接"""
        if server_id not in self._connections:
            return
        loop = self._ensure_loop()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_disconnect(server_id),
                loop,
            )
            future.result(timeout=self._timeout)
        except Exception as e:
            logger.error(f"MCP disconnect failed for {server_id}: {e}")

    def list_connected_servers(self) -> List[str]:
        """返回已连接的 server_id 列表"""
        return list(self._connections.keys())

    def list_tools(self, server_id: str) -> List[str]:
        """列出指定 Server 上的工具名称列表（净化后的命名空间名）"""
        if server_id not in self._connections:
            return []
        conn = self._connections[server_id]
        return list(conn.tool_name_map.keys())

    def get_connection(self, server_id: str) -> Optional[MCPServerConnection]:
        """获取指定连接的信息"""
        return self._connections.get(server_id)

    def shutdown(self) -> None:
        """关闭所有连接并清理

        先串行断开全部连接（每个连接等待时间受 _timeout 约束），
        再停止事件循环线程并关闭 loop。
        """
        server_ids = list(self._connections.keys())
        for server_id in server_ids:
            try:
                self.disconnect(server_id)
            except Exception as e:
                logger.warning(f"Error during shutdown for {server_id}: {e}")

        loop = self._async_loop
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(loop.stop)
            except Exception:
                pass
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=5.0)
                if self._loop_thread.is_alive():
                    logger.warning("MCP client loop thread did not exit in 5s")
            try:
                loop.close()
            except Exception as e:
                logger.warning(f"Error closing MCP client loop: {e}")
        self._async_loop = None
        self._loop_thread = None
