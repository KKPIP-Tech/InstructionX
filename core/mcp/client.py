"""
MCP Client 管理器

管理到外部 MCP Server 的连接，并将它们的工具注册到 ToolRegistry。
支持 stdio 和 streamable-http 两种连接方式。
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

# 向后兼容：MCPRemoteServerConfig 实际定义在 core.mcp.config，
# 历史上插件代码从 core.mcp.client 导入，这里保留 re-export。
from core.mcp.async_cleanup import cancel_pending_tasks
from core.mcp.client_support import ensure_mcp_sdk
from core.mcp.config import MCPRemoteServerConfig  # noqa: F401
from core.mcp.connection_actor import ConnectionActor
from core.plugin.tool_name import sanitize_tool_name

logger = logging.getLogger(__name__)

# 连接/调用/断开的统一默认超时（秒）
DEFAULT_MCP_CLIENT_TIMEOUT = 60.0
# shutdown 时等待事件循环线程退出的超时（秒）
LOOP_THREAD_JOIN_TIMEOUT = 5.0


def _ensure_mcp_sdk() -> None:
    """保留历史内部入口，统一执行 MCP SDK 依赖检查。"""
    ensure_mcp_sdk()


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
    actor: Optional[ConnectionActor] = None


class MCPClientManager:
    """管理所有外部 MCP Server 连接

    将外部 MCP 工具注册到应用内的 ToolRegistry，
    使 LLM 可以透明地调用外部 MCP 工具。

    Args:
        tool_registry: 应用内的 ToolRegistry 实例
        timeout: 连接/调用/断开的统一超时（秒）
    """

    def __init__(self, tool_registry: Any, timeout: float = DEFAULT_MCP_CLIENT_TIMEOUT):
        self._connections: Dict[str, MCPServerConnection] = {}
        # 保护 _connections 在 UI 线程与工作线程间的并发读写
        self._conn_lock = threading.Lock()
        self._tool_registry = tool_registry
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._timeout = timeout
        self._lifecycle_errors: List[str] = []

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
        actor: Optional[ConnectionActor] = None,
    ) -> Callable:
        """创建调用外部 MCP 工具的 handler"""
        def handler(**kwargs: Any) -> Any:
            loop = self._ensure_loop()
            future = None
            try:
                if actor is not None:
                    coroutine = actor.call_tool(original_tool_name, kwargs or {})
                else:
                    coroutine = session.call_tool(original_tool_name, kwargs or {})
                future = asyncio.run_coroutine_threadsafe(coroutine, loop)
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
                if future is not None:
                    future.cancel()
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
        """通过单一 coroutine owner 异步连接，禁止跨 Task 关闭退出栈。"""
        actor = ConnectionActor(config, timeout=self._timeout)
        try:
            session, tools_result = await actor.start()
            return self._create_connection(
                server_id, config, session, tools_result, actor=actor
            )
        except Exception:
            await actor.stop()
            raise

    def _create_connection(
        self,
        server_id: str,
        config: Any,
        session: Any,
        tools_result: Any,
        exit_stack: Any = None,
        actor: Optional[ConnectionActor] = None,
    ) -> MCPServerConnection:
        """创建连接对象并注册工具

        工具命名空间：sanitize_tool_name(f"mcp__{server_id}__{tool_name}")，
        符合 OpenAI function 命名规范 ^[a-zA-Z0-9_-]{1,64}$。
        单个工具注册失败只记 warning，不中断整个连接。
        """
        tools = list(tools_result.tools) if tools_result.tools else []
        conn = MCPServerConnection(
            server_id=server_id,
            name=config.name,
            config=config,
            session=session,
            tools=tools,
            exit_stack=exit_stack,
            actor=actor,
        )

        for tool in tools:
            namespaced_name = sanitize_tool_name(
                f"mcp__{server_id}__{tool.name}"
            )
            description = f"[MCP/{config.name}] {tool.description or ''}"
            parameters = tool.inputSchema or {}
            handler = self._make_handler(server_id, session, tool.name, actor)

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

        with self._conn_lock:
            self._connections[server_id] = conn
        return conn

    async def _async_disconnect(self, server_id: str) -> None:
        """注销工具并关闭连接，异常在清理连接表后统一上报。"""
        with self._conn_lock:
            conn = self._connections.get(server_id)
        if conn is None:
            return
        errors = self._unregister_connection_tools(conn)
        try:
            if conn.actor is not None:
                await conn.actor.stop()
            elif conn.exit_stack is not None:
                await conn.exit_stack.aclose()
        except Exception as exc:
            errors.append(f"关闭会话失败: {exc}")
        finally:
            with self._conn_lock:
                self._connections.pop(server_id, None)
        if errors:
            raise RuntimeError(f"MCP 连接 {server_id} 清理不完整: {'; '.join(errors)}")
        logger.info(f"Disconnected from MCP server: {server_id}")

    def _unregister_connection_tools(self, conn: MCPServerConnection) -> List[str]:
        """注销连接的全部工具并返回失败列表。"""
        errors = []
        for namespaced_name in list(conn.tool_name_map.keys()):
            try:
                self._tool_registry.unregister(namespaced_name)
            except Exception as exc:
                logger.warning(
                    f"Failed to unregister MCP tool {namespaced_name}: {exc}"
                )
                errors.append(f"注销工具 {namespaced_name} 失败: {exc}")
        return errors

    def connect(self, config: Any) -> str:
        """同步连接到外部 MCP Server

        Args:
            config: MCPRemoteServerConfig 实例

        Returns:
            server_id
        """
        with self._conn_lock:
            already_connected = config.server_id in self._connections
        if already_connected:
            logger.info(
                f"MCP server {config.server_id} already connected, "
                f"disconnecting before reconnect"
            )
            self.disconnect(config.server_id)

        actor = ConnectionActor(config, timeout=self._timeout)
        loop = self._ensure_loop()
        future = None
        try:
            future = asyncio.run_coroutine_threadsafe(actor.start(), loop)
            session, tools_result = future.result(timeout=self._timeout)
            self._create_connection(
                config.server_id, config, session, tools_result, actor=actor
            )
        except Exception as e:
            if future is not None:
                future.cancel()
            self._cleanup_failed_connect(actor, loop)
            logger.error(f"MCP connect failed for {config.server_id}: {e}")
            raise

        return config.server_id

    def _cleanup_failed_connect(self, actor: ConnectionActor, loop: asyncio.AbstractEventLoop) -> None:
        """连接或注册失败时关闭已打开的 actor，保留原始异常继续抛出。"""
        try:
            cleanup = asyncio.run_coroutine_threadsafe(actor.stop(), loop)
            cleanup.result(timeout=self._timeout)
        except Exception as cleanup_error:
            logger.error(f"MCP 连接失败后的 actor 清理失败: {cleanup_error}")

    def disconnect(self, server_id: str) -> None:
        """同步断开连接"""
        with self._conn_lock:
            connected = server_id in self._connections
        if not connected:
            return
        loop = self._ensure_loop()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self._async_disconnect(server_id),
                loop,
            )
            future.result(timeout=self._timeout)
        except Exception as e:
            self._lifecycle_errors.append(f"{server_id}: {e}")
            logger.error(f"MCP disconnect failed for {server_id}: {e}")

    def list_connected_servers(self) -> List[str]:
        """返回已连接的 server_id 列表"""
        with self._conn_lock:
            return list(self._connections.keys())

    def list_tools(self, server_id: str) -> List[str]:
        """列出指定 Server 上的工具名称列表（净化后的命名空间名）"""
        with self._conn_lock:
            conn = self._connections.get(server_id)
        if conn is None:
            return []
        return list(conn.tool_name_map.keys())

    def get_connection(self, server_id: str) -> Optional[MCPServerConnection]:
        """获取指定连接的信息"""
        with self._conn_lock:
            return self._connections.get(server_id)

    def shutdown(self) -> tuple[str, ...]:
        """关闭全部连接和事件循环，返回未忽略的清理错误列表。"""
        self._lifecycle_errors = []
        with self._conn_lock:
            server_ids = list(self._connections.keys())
        for server_id in server_ids:
            try:
                self.disconnect(server_id)
            except Exception as exc:
                self._lifecycle_errors.append(f"{server_id}: {exc}")
                logger.warning(f"Error during shutdown for {server_id}: {exc}")
        self._close_loop()
        self._async_loop = None
        self._loop_thread = None
        return tuple(self._lifecycle_errors)

    def _close_loop(self) -> None:
        """停止事件循环；线程未退出时不得关闭仍在运行的 loop。"""
        loop = self._async_loop
        if loop is None or loop.is_closed():
            return
        try:
            cleanup = asyncio.run_coroutine_threadsafe(cancel_pending_tasks(), loop)
            cleanup.result(timeout=LOOP_THREAD_JOIN_TIMEOUT)
        except Exception as exc:
            self._lifecycle_errors.append(f"清理事件循环任务失败: {exc}")
        try:
            loop.call_soon_threadsafe(loop.stop)
        except Exception as exc:
            self._lifecycle_errors.append(f"停止事件循环失败: {exc}")
        if self._loop_thread is not None:
            self._loop_thread.join(timeout=LOOP_THREAD_JOIN_TIMEOUT)
            if self._loop_thread.is_alive():
                self._lifecycle_errors.append("MCP client 事件循环线程未在截止期内退出")
                return
        try:
            loop.close()
        except Exception as exc:
            self._lifecycle_errors.append(f"关闭事件循环失败: {exc}")
