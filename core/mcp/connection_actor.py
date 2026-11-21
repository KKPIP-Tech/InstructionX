"""单连接 coroutine owner，统一 MCP 传输开启、调用与退出栈生命周期。"""

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, Optional, Tuple

from .client_support import (
    ClientSession,
    StdioServerParameters,
    create_http_client,
    ensure_mcp_sdk,
    get_default_environment,
    stdio_client,
    streamable_http_client,
)
from .config import MCPRemoteServerConfig

logger = logging.getLogger(__name__)

DEFAULT_CONNECTION_TIMEOUT = 60.0
_COMMAND_CALL = "call"
_COMMAND_STOP = "stop"


class ConnectionActor:
    """在单一 Task 中创建并关闭 AsyncExitStack，命令经队列串行执行。"""

    def __init__(
        self,
        config: MCPRemoteServerConfig,
        timeout: float = DEFAULT_CONNECTION_TIMEOUT,
    ) -> None:
        self.config = config
        self._timeout = timeout
        self._commands: Optional[asyncio.Queue] = None
        self._owner_task: Optional[asyncio.Task] = None
        self._ready = asyncio.Event()
        self._done = asyncio.Event()
        self._session = None
        self._stack: Optional[AsyncExitStack] = None
        self._tools_result = None
        self._startup_error: Optional[BaseException] = None
        self._cleanup_error: Optional[BaseException] = None
        self._stopping = False

    async def start(self) -> Tuple[Any, Any]:
        """启动连接 owner 并返回 ``(session, tools_result)``。"""
        if self._owner_task is not None:
            raise RuntimeError("MCP ConnectionActor 不可重复启动")
        self._commands = asyncio.Queue()
        self._owner_task = asyncio.create_task(
            self._run(), name=f"mcp-connection-{self.config.server_id}"
        )
        try:
            await self._ready.wait()
        except asyncio.CancelledError:
            self._request_stop()
            raise
        if self._startup_error is not None:
            await self._done.wait()
            raise self._startup_error
        return self._session, self._tools_result

    async def stop(self) -> None:
        """请求停止 owner，并在同一 Task 中关闭退出栈。"""
        if self._commands is not None and not self._done.is_set():
            self._request_stop()
            await self._done.wait()
        if self._cleanup_error is not None:
            raise RuntimeError("MCP 连接退出栈清理失败") from self._cleanup_error

    async def call_tool(
        self, original_tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """经 owner 调用工具；超时由 owner 取消调用并关闭会话。"""
        if self._commands is None or self._done.is_set() or self._stopping:
            raise RuntimeError("MCP 连接尚未启动或正在关闭")
        future = asyncio.get_running_loop().create_future()
        await self._commands.put(
            (_COMMAND_CALL, (original_tool_name, arguments), future)
        )
        return await future

    def _request_stop(self) -> None:
        """以幂等方式提交停止命令，不等待 owner。"""
        if self._commands is None or self._done.is_set() or self._stopping:
            return
        self._stopping = True
        self._commands.put_nowait((_COMMAND_STOP, None, None))

    async def _run(self) -> None:
        """持有全部异步上下文，并保证异常路径也完成清理通知。"""
        try:
            opened = await asyncio.wait_for(
                self._open_transport(), timeout=self._timeout
            )
            self._session, self._stack, self._tools_result = opened
            self._ready.set()
            await self._serve_commands()
        except Exception as exc:
            self._record_runtime_error(exc)
        finally:
            await self._finish()

    async def _serve_commands(self) -> None:
        """串行处理工具调用；调用超时后退出 owner 并触发关闭。"""
        while not self._stopping:
            command, payload, future = await self._commands.get()
            if command == _COMMAND_STOP:
                break
            try:
                result = await asyncio.wait_for(
                    self._session.call_tool(*payload), timeout=self._timeout
                )
            except Exception as exc:
                if not future.done():
                    future.set_exception(exc)
                if isinstance(exc, asyncio.TimeoutError):
                    break
            else:
                if not future.done():
                    future.set_result(result)

    def _record_runtime_error(self, exc: Exception) -> None:
        """区分启动失败与运行期异常，避免启动调用永久等待。"""
        if not self._ready.is_set():
            self._startup_error = exc
            self._ready.set()
            return
        logger.error("MCP 连接 owner 异常退出: %s", exc)

    async def _finish(self) -> None:
        """关闭退出栈并始终释放 done 等待者。"""
        try:
            await self._close_stack()
        except Exception as exc:
            self._cleanup_error = exc
            logger.error("MCP 连接退出栈清理失败: %s", exc)
        finally:
            self._done.set()

    async def _close_stack(self) -> None:
        """幂等关闭当前退出栈。"""
        stack = self._stack
        self._stack = None
        if stack is not None:
            await stack.aclose()

    async def _open_transport(self) -> Tuple[Any, AsyncExitStack, Any]:
        """打开配置的传输并返回 session、exit stack 和 tools_result。"""
        ensure_mcp_sdk()
        self._stack = AsyncExitStack()
        if self.config.transport == "stdio":
            return await self._open_stdio(self._stack)
        if self.config.transport == "streamable-http":
            return await self._open_http(self._stack)
        raise ValueError(f"Unsupported transport: {self.config.transport}")

    async def _open_stdio(self, stack: AsyncExitStack) -> Tuple[Any, AsyncExitStack, Any]:
        """在 owner Task 中建立 stdio 传输与 MCP 会话。"""
        env = None
        if self.config.env:
            env = get_default_environment()
            env.update(self.config.env)
        params = StdioServerParameters(
            command=self.config.command, args=self.config.args, env=env
        )
        read, write = await stack.enter_async_context(stdio_client(params))
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools = await session.list_tools()
        return session, stack, tools

    async def _open_http(self, stack: AsyncExitStack) -> Tuple[Any, AsyncExitStack, Any]:
        """在 owner Task 中建立 HTTP 传输与 MCP 会话。"""
        http_client = None
        if self.config.auth_token:
            http_client = await stack.enter_async_context(
                create_http_client(
                    headers={"Authorization": f"Bearer {self.config.auth_token}"},
                    follow_redirects=True,
                )
            )
        read, write, _ = await stack.enter_async_context(
            streamable_http_client(self.config.url, http_client=http_client)
        )
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        tools = await session.list_tools()
        return session, stack, tools
