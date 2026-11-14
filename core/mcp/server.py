"""
MCP Server 封装

基于 FastMCP 构建 MCP Server，将插件工具暴露给外部 MCP Client。
支持 stdio 和 streamable-http 两种传输方式。
"""

import asyncio
import functools
import hmac
import importlib
import inspect
import threading
import time
from typing import Any, Dict, List, Optional, Callable
import logging

from core.plugin.manager import PluginManager
from core.mcp.async_cleanup import cancel_pending_tasks
from core.mcp.config import (
    DEFAULT_MCP_MAX_REQUESTS_PER_MINUTE,
    DEFAULT_MCP_MAX_SESSIONS,
    DEFAULT_MCP_SESSION_IDLE_TIMEOUT,
    MCPServerConfig,
)

# ===== 可选依赖：MCP SDK / uvicorn / anyio（缺失时置 None，运行时检查）=====
_MCP_IMPORT_ERROR = None
try:
    from mcp.server.fastmcp import FastMCP
    from mcp.server.fastmcp.tools import Tool
except ImportError as exc:
    _MCP_IMPORT_ERROR = exc
    FastMCP = None
    Tool = None


def _refresh_mcp_types() -> None:
    """启动时重试暂时失败的 SDK 导入，避免缓存缺失状态污染后续服务。"""
    global FastMCP, Tool, _MCP_IMPORT_ERROR
    if FastMCP is not None and Tool is not None:
        return
    try:
        fastmcp_module = importlib.import_module("mcp.server.fastmcp")
        tools_module = importlib.import_module("mcp.server.fastmcp.tools")
    except ImportError as exc:
        _MCP_IMPORT_ERROR = exc
        return
    FastMCP = fastmcp_module.FastMCP
    Tool = tools_module.Tool
    _MCP_IMPORT_ERROR = None


try:
    import uvicorn
except ImportError:
    uvicorn = None

try:
    import anyio.to_thread
except ImportError:
    anyio = None

logger = logging.getLogger(__name__)

# HTTP Server 启动结果等待超时（秒）
SERVER_START_WAIT_TIMEOUT = 5.0
# 启动确认 watch 协程的轮询间隔（秒）
STARTUP_WATCH_POLL_INTERVAL = 0.05
# 停止 Server 时等待工作线程退出的超时（秒）
SERVER_STOP_JOIN_TIMEOUT = 5.0


class ServerSecurityPolicy:
    """MCP HTTP 暴露安全策略，非法配置在启动前失败关闭。"""

    LOOPBACK_HOSTS = frozenset(("127.0.0.1", "localhost", "::1"))

    @classmethod
    def validate(cls, config) -> None:
        """校验监听地址、认证和 TLS 配置，非法时抛出 ValueError。"""
        if config.transport != "streamable-http":
            return
        if config.host not in cls.LOOPBACK_HOSTS and not config.auth_token:
            raise ValueError("非回环 HTTP 监听必须配置 auth_token，拒绝无认证暴露")
        if bool(config.tls_certfile) != bool(config.tls_keyfile):
            raise ValueError("tls_certfile 与 tls_keyfile 必须成对配置")


class _HostValidationMiddleware:
    """按 allowed_hosts 精确校验 HTTP/WebSocket Host 头。"""

    def __init__(self, app, allowed_hosts):
        self._app = app
        self._allowed = {self._normalize_host(host) for host in allowed_hosts}

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type")
        if scope_type not in ("http", "websocket") or not self._allowed:
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        raw_host = headers.get(b"host", b"").decode("latin-1")
        host = self._normalize_host(raw_host)
        if host in self._allowed:
            await self._app(scope, receive, send)
            return
        if scope_type == "websocket":
            await send({"type": "websocket.close", "code": 4403})
            return
        await send({
            "type": "http.response.start", "status": 403,
            "headers": [(b"content-type", b"application/json")],
        })
        await send({
            "type": "http.response.body", "body": b'{"error":"invalid_host"}',
        })

    @staticmethod
    def _normalize_host(value: str) -> str:
        """去除大小写、末尾点和可选端口，保留 IPv6 地址冒号。"""
        host = value.strip().lower().rstrip(".")
        if host.startswith("["):
            return host[1:].split("]", 1)[0]
        if host.count(":") == 1:
            return host.rsplit(":", 1)[0]
        return host


class _RateLimitMiddleware:
    """按客户端 IP 的滑动窗口限流，并限制跟踪状态的最大基数。"""

    WINDOW_SECONDS = 60.0
    MAX_TRACKED_CLIENTS = 10000

    def __init__(self, app, max_requests_per_minute: int):
        self._app = app
        self._limit = max_requests_per_minute
        self._requests: Dict[str, list] = {}
        self._next_prune = time.monotonic() + self.WINDOW_SECONDS

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and not self._allow(scope):
            await send({
                "type": "http.response.start", "status": 429,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({
                "type": "http.response.body", "body": b'{"error":"rate_limited"}',
            })
            return
        await self._app(scope, receive, send)

    def _allow(self, scope) -> bool:
        client = (scope.get("client") or ("unknown", 0))[0]
        now = time.monotonic()
        self._prune(now)
        recent = [
            stamp for stamp in self._requests.get(client, [])
            if now - stamp < self.WINDOW_SECONDS
        ]
        if len(recent) >= self._limit:
            self._requests[client] = recent
            return False
        if client not in self._requests and len(self._requests) >= self.MAX_TRACKED_CLIENTS:
            return False
        recent.append(now)
        self._requests[client] = recent
        return True

    def _prune(self, now: float) -> None:
        """定期清理空闲客户端，避免限流状态无限增长。"""
        if now < self._next_prune:
            return
        self._requests = {
            client: stamps for client, stamps in self._requests.items()
            if stamps and now - stamps[-1] < self.WINDOW_SECONDS
        }
        self._next_prune = now + self.WINDOW_SECONDS


def _validate_auth_token(token: str) -> None:
    """校验 Bearer 令牌的合法性

    HTTP Authorization 头要求 latin-1 可编码，且令牌中不允许出现
    空白/控制字符；这里统一收紧为 ASCII 可见字符（0x21-0x7E）。

    Args:
        token: 待校验的认证令牌

    Raises:
        ValueError: 令牌包含非法字符时抛出，文案为中文
    """
    if all(0x21 <= ord(char) <= 0x7E for char in token):
        return
    raise ValueError(
        "MCP auth_token 只能包含 ASCII 可见字符（不能包含中文、空格或控制字符），"
        "请检查 MCP 配置中的 auth_token 设置。"
    )

# JSON Schema 类型 → Python 类型（用于伪造 handler 签名）
_JSON_TYPE_MAP: Dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


class _BearerAuthMiddleware:
    """纯 ASGI 的 Bearer Token 校验中间件

    仅校验 http/websocket 请求，lifespan 等其他 scope 直接放行。
    """

    def __init__(self, app: Any, token: str):
        self._app = app
        # token 已在 MCPHostServer 构造时校验为 ASCII 可见字符，此处不会抛编码异常
        self._expected = f"Bearer {token}".encode("latin-1")

    async def __call__(self, scope: Dict, receive: Callable, send: Callable) -> None:
        if scope.get("type") in ("http", "websocket"):
            headers = dict(scope.get("headers") or [])
            # compare_digest 防止时序侧信道泄露令牌内容
            if not hmac.compare_digest(
                headers.get(b"authorization", b""), self._expected
            ):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 4401})
                    return
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"error": "unauthorized"}',
                })
                return
        await self._app(scope, receive, send)


class MCPHostServer:
    """MCP Server 封装

    基于 FastMCP 构建，负责将插件 API 方法暴露为 MCP 工具。

    Args:
        name: Server 名称，默认 "InstructionX"
        host: HTTP 监听地址，默认 "127.0.0.1"
        port: HTTP 监听端口，默认 8765
        auth_token: HTTP 模式 Bearer 认证令牌，默认 None（不启用认证）
        session_idle_timeout: Streamable HTTP 空闲会话超时秒数；
                              None 表示禁用空闲回收
        max_sessions: Streamable HTTP 同时保留的最大会话数；
                      None 表示不限制
    """

    def __init__(
        self,
        name: str = "InstructionX",
        host: str = "127.0.0.1",
        port: int = 8765,
        auth_token: Optional[str] = None,
        session_idle_timeout: Optional[float] = (
            DEFAULT_MCP_SESSION_IDLE_TIMEOUT),
        max_sessions: Optional[int] = DEFAULT_MCP_MAX_SESSIONS,
        allowed_hosts: Optional[List[str]] = None,
        max_requests_per_minute: Optional[int] = DEFAULT_MCP_MAX_REQUESTS_PER_MINUTE,
        tls_certfile: Optional[str] = None,
        tls_keyfile: Optional[str] = None,
    ):
        if auth_token is not None:
            # 启动前校验令牌可编码性，非法时以中文文案 fail-fast
            _validate_auth_token(auth_token)
        self._name = name
        self._host = host
        self._port = port
        self._auth_token = auth_token
        self._session_idle_timeout = self._validate_session_idle_timeout(
            session_idle_timeout)
        self._max_sessions = self._validate_max_sessions(max_sessions)
        self._allowed_hosts = allowed_hosts
        self._max_requests_per_minute = self._validate_max_requests_per_minute(
            max_requests_per_minute)
        self._tls_certfile = tls_certfile
        self._tls_keyfile = tls_keyfile
        self._running = False
        self._thread: Optional[threading.Thread] = None
        # uvicorn Server 实例（HTTP 模式），用于真正的关停
        self._uvicorn_server: Optional[Any] = None
        # 保护 _tool_registry 与 FastMCP 内部工具表的并发访问
        self._lock = threading.Lock()
        # FastMCP 实例，在 start() 时创建（避免在 __init__ 时创建事件循环）
        self._fastmcp = None
        # 记录已注册的工具：tool_name -> {plugin_id, method_name}
        self._tool_registry: Dict[str, Dict[str, str]] = {}

    @staticmethod
    def _validate_session_idle_timeout(value):
        """校验会话空闲超时为可选正数。"""
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
        ):
            raise ValueError(
                "session_idle_timeout 必须是大于 0 的数字，或设置为 None 禁用限制")
        return float(value)

    @staticmethod
    def _validate_max_sessions(value):
        """校验最大会话数为可选正整数。"""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "max_sessions 必须是大于 0 的整数，或设置为 None 禁用限制")
        return value

    @staticmethod
    def _validate_max_requests_per_minute(value):
        """校验每分钟请求上限为正整数，None 表示显式禁用限流。"""
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                "max_requests_per_minute 必须是大于 0 的整数，或设置为 None 禁用限制")
        return value

    def _init_fastmcp(self) -> Any:
        """延迟初始化 FastMCP（避免在主线程事件循环外创建）

        mcp 1.30.0（约束 mcp>=1.30.0,<2） 中 host/port 需传给 FastMCP 构造器，
        FastMCP.run() 只接受 transport/mount_path 参数。

        Raises:
            RuntimeError: MCP SDK 未安装时抛出（中文提示）
        """
        _refresh_mcp_types()
        if FastMCP is None:
            raise RuntimeError(
                "缺少 MCP SDK 依赖（请执行 pip install mcp），无法启动 MCP Server。"
                f"导入异常: {_MCP_IMPORT_ERROR}"
            )
        return FastMCP(
            self._name,
            host=self._host,
            port=self._port,
            session_idle_timeout=self._session_idle_timeout,
            max_sessions=self._max_sessions,
        )

    # ─── 工具注册 ────────────────────────────────────────────────

    def add_tool(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        plugin_id: str,
        method_name: str,
    ) -> None:
        """动态注册一个 MCP 工具

        Args:
            name: 工具名称
            description: 工具描述
            parameters: JSON Schema 格式的参数定义
            plugin_id: 对应的插件 ID
            method_name: 对应的插件 API 方法名
        """
        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        with self._lock:
            # 记录工具映射
            self._tool_registry[name] = {
                "plugin_id": plugin_id,
                "method_name": method_name,
            }

        handler = self._create_tool_handler(name, plugin_id, method_name, parameters)
        self._register_tool_direct(
            name=name,
            description=description,
            parameters=parameters,
            handler=handler,
        )

    def _create_tool_handler(
        self,
        name: str,
        plugin_id: str,
        method_name: str,
        parameters: Dict[str, Any],
    ) -> Callable:
        """创建调用插件方法的异步工具 handler

        - anyio.to_thread.run_sync 不转发 **kwargs，用 functools.partial 包装；
        - 依据 JSON Schema 伪造 __signature__，使 FastMCP 的参数校验模型
          与插件真实参数一致（**kwargs 签名会被 pydantic 误认为必传的
          "kwargs" 字段，导致所有调用校验失败）。

        Raises:
            RuntimeError: anyio 未安装时抛出（中文提示）
        """
        if anyio is None:
            raise RuntimeError(
                "缺少 anyio 依赖（请执行 pip install anyio），无法调用插件工具。"
            )

        async def handler(**kwargs: Any) -> Any:
            # 同步插件方法通过 anyio.to_thread 调用
            try:
                call = functools.partial(
                    PluginManager().call_plugin_method,
                    "",  # caller_id（Server 模式不需要）
                    plugin_id,
                    method_name,
                    **kwargs,
                )
                return await anyio.to_thread.run_sync(call)
            except Exception as e:
                logger.error(f"MCP tool {name} call failed: {e}")
                raise

        # 根据 JSON Schema 伪造函数签名；空 schema 也必须移除 **kwargs 签名。
        handler.__signature__ = inspect.Signature([])  # type: ignore[attr-defined]
        properties = (parameters or {}).get("properties", {})
        if properties:
            required = set((parameters or {}).get("required", []))
            sig_params: List[inspect.Parameter] = []
            for param_name, prop in properties.items():
                annotation = _JSON_TYPE_MAP.get(
                    (prop or {}).get("type", "string"), str
                )
                default = (
                    inspect.Parameter.empty
                    if param_name in required
                    else (prop or {}).get("default", None)
                )
                sig_params.append(
                    inspect.Parameter(
                        name=param_name,
                        kind=inspect.Parameter.KEYWORD_ONLY,
                        default=default,
                        annotation=annotation,
                    )
                )
            handler.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]

        return handler

    def _register_tool_direct(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ) -> None:
        """直接注册工具到 FastMCP

        mcp 1.30.0（约束 mcp>=1.30.0,<2）：ToolManager.add_tool() 内部通过
        Tool.from_function() 构建 Tool 并放入 _tools 字典；
        对外展示的 parameters 可在构建后覆盖为调用方提供的 JSON Schema。
        同名工具会被显式替换并记录 warning，注册失败记录 error。
        """
        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        try:
            if Tool is None:
                raise RuntimeError(
                    "缺少 MCP SDK 依赖（请执行 pip install mcp），无法注册 MCP 工具。"
                )
            tool_manager = getattr(self._fastmcp, "_tool_manager", None)
            tools_table = getattr(tool_manager, "_tools", None)
            if tool_manager is None or not isinstance(tools_table, dict):
                raise RuntimeError("FastMCP ToolManager not accessible")

            tool = Tool.from_function(
                handler, name=name, description=description or ""
            )
            # 用调用方提供的 JSON Schema 覆盖派生 schema（对外展示的参数定义）
            if parameters:
                tool.parameters = parameters

            with self._lock:
                if name in tools_table:
                    logger.warning(
                        f"MCP tool {name} already registered, replacing"
                    )
                    tools_table.pop(name, None)
                tools_table[name] = tool
            logger.info(f"MCP tool registered: {name}")
        except Exception as e:
            logger.error(f"Failed to register MCP tool {name}: {e}")
            # 记录为延迟注册，run 时重试
            with self._lock:
                if name in self._tool_registry:
                    self._tool_registry[name]["deferred"] = {
                        "description": description,
                        "parameters": parameters,
                        "handler": handler,
                    }

    def remove_tool(self, name: str) -> None:
        """注销一个 MCP 工具"""
        with self._lock:
            removed = self._tool_registry.pop(name, None)
        if removed is not None:
            logger.info(f"MCP tool unregistered: {name}")

        # 从 FastMCP 工具管理器中移除
        if self._fastmcp is not None:
            try:
                tool_manager = getattr(self._fastmcp, "_tool_manager", None)
                tools_table = getattr(tool_manager, "_tools", None)
                if isinstance(tools_table, dict):
                    with self._lock:
                        if name in tools_table:
                            if hasattr(tool_manager, "remove_tool"):
                                tool_manager.remove_tool(name)
                            else:
                                tools_table.pop(name, None)
            except Exception as e:
                logger.error(f"Failed to unregister MCP tool {name}: {e}")

    def _register_all_deferred_tools(self) -> None:
        """注册所有延迟注册的工具（在 run 之前调用）"""
        if self._fastmcp is None:
            return

        with self._lock:
            deferred = [
                (name, dict(info["deferred"]))
                for name, info in self._tool_registry.items()
                if info.get("deferred")
            ]

        for name, deferred_info in deferred:
            self._register_tool_direct(
                name=name,
                description=deferred_info["description"],
                parameters=deferred_info["parameters"],
                handler=deferred_info["handler"],
            )
            # 清除 deferred 标记
            with self._lock:
                if name in self._tool_registry:
                    self._tool_registry[name].pop("deferred", None)

    # ─── 生命周期 ────────────────────────────────────────────────

    def run_stdio(self) -> None:
        """启动 MCP Server（stdio 传输）

        直接在当前进程 stdin/stdout 上运行 MCP 协议，**会阻塞当前线程**
        直到 Server 退出。请勿在 Qt 主线程直接调用（应放入工作线程）。
        适用于 Claude Code MCP Client 连接。
        """
        if self._running:
            logger.warning("MCP Server is already running")
            return

        if threading.current_thread() is threading.main_thread():
            logger.warning(
                "run_stdio() 将阻塞当前线程，而当前是主线程；"
                "建议在工作线程中启动 stdio MCP Server。"
            )

        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        self._register_all_deferred_tools()

        self._running = True
        try:
            # mcp 1.30.0（约束 mcp>=1.30.0,<2）：run() 只接受 transport/mount_path，
            # host/port 已在构造器传入
            self._fastmcp.run(transport="stdio")
        except Exception as e:
            logger.error(f"MCP stdio server error: {e}")
        finally:
            self._running = False

    def run_http(self) -> None:
        """启动 MCP Server（streamable-http 传输）

        在后台线程中通过 uvicorn 启动 HTTP 服务器。
        启动失败会抛出 RuntimeError，不会静默。
        """
        if self._running:
            logger.warning("MCP Server is already running")
            return
        ServerSecurityPolicy.validate(MCPServerConfig(
            host=self._host,
            transport="streamable-http",
            auth_token=self._auth_token,
            tls_certfile=self._tls_certfile,
            tls_keyfile=self._tls_keyfile,
        ))

        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        self._register_all_deferred_tools()

        started = threading.Event()
        error_holder: Dict[str, Any] = {}

        def _run_in_thread() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if uvicorn is None:
                    raise RuntimeError(
                        "缺少 uvicorn 依赖（请执行 pip install uvicorn），"
                        "无法以 HTTP 模式启动 MCP Server。"
                    )
                app = self._fastmcp.streamable_http_app()
                if self._allowed_hosts:
                    app = _HostValidationMiddleware(app, self._allowed_hosts)
                if self._max_requests_per_minute is not None:
                    app = _RateLimitMiddleware(app, self._max_requests_per_minute)
                if self._auth_token:
                    app = _BearerAuthMiddleware(app, self._auth_token)

                config = uvicorn.Config(
                    app,
                    host=self._host,
                    port=self._port,
                    log_level="info",
                    ssl_certfile=self._tls_certfile,
                    ssl_keyfile=self._tls_keyfile,
                )
                server = uvicorn.Server(config)
                self._uvicorn_server = server

                async def _serve() -> None:
                    async def _watch_started() -> None:
                        while not server.started:
                            await asyncio.sleep(STARTUP_WATCH_POLL_INTERVAL)
                        started.set()

                    watcher = asyncio.ensure_future(_watch_started())
                    try:
                        await server.serve()
                    finally:
                        watcher.cancel()
                        await cancel_pending_tasks()

                loop.run_until_complete(_serve())
            except Exception as e:
                error_holder["error"] = e
                logger.error(f"MCP HTTP server error: {e}")
            finally:
                self._running = False
                self._uvicorn_server = None
                loop.close()

        self._running = True
        self._thread = threading.Thread(target=_run_in_thread, daemon=True)
        self._thread.start()

        # 等待启动结果（最多 SERVER_START_WAIT_TIMEOUT 秒），启动失败不静默
        if not started.wait(timeout=SERVER_START_WAIT_TIMEOUT):
            if not self._thread.is_alive() or "error" in error_holder:
                self._running = False
                err = error_holder.get("error")
                logger.error(
                    f"MCP HTTP Server failed to start on "
                    f"{self._host}:{self._port}: {err}"
                )
                raise RuntimeError(f"MCP HTTP Server failed to start: {err}")
            logger.warning(
                f"MCP HTTP Server startup not confirmed within "
                f"{SERVER_START_WAIT_TIMEOUT}s on {self._host}:{self._port}"
            )
        else:
            logger.info(
                f"MCP HTTP Server started on {self._host}:{self._port}"
            )

    def stop(self) -> None:
        """停止 MCP Server

        HTTP 模式：通过 uvicorn Server.should_exit 触发真正的关停并等待线程退出。
        stdio 模式：anyio 无法从外部线程取消阻塞中的 run，仅复位状态标志
        （stdio Server 通常随进程/会话结束而退出）。
        """
        if self._uvicorn_server is not None:
            self._uvicorn_server.should_exit = True
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=SERVER_STOP_JOIN_TIMEOUT)
            if self._thread.is_alive():
                self._running = True
                raise RuntimeError(
                    f"MCP Server 线程未在 {SERVER_STOP_JOIN_TIMEOUT}s 内退出，"
                    "不能报告停止成功"
                )
        self._uvicorn_server = None
        self._thread = None
        self._running = False
        logger.info("MCP Server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def registered_tools(self) -> Dict[str, Dict[str, str]]:
        """返回所有已注册的工具映射"""
        with self._lock:
            return dict(self._tool_registry)
