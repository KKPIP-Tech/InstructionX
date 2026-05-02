"""
MCP Server 封装

基于 FastMCP 构建 MCP Server，将插件工具暴露给外部 MCP Client。
支持 stdio 和 streamable-http 两种传输方式。
"""

import asyncio
import threading
from typing import Any, Dict, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class MCPHostServer:
    """MCP Server 封装

    基于 FastMCP 构建，负责将插件 API 方法暴露为 MCP 工具。

    Args:
        name: Server 名称，默认 "InstructionX"
        host: HTTP 监听地址，默认 "127.0.0.1"
        port: HTTP 监听端口，默认 8765
    """

    def __init__(
        self,
        name: str = "InstructionX",
        host: str = "127.0.0.1",
        port: int = 8765,
    ):
        self._name = name
        self._host = host
        self._port = port
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._server_ready = asyncio.Event()
        # FastMCP 实例，在 start() 时创建（避免在 __init__ 时创建事件循环）
        self._fastmcp = None
        # 记录已注册的工具：tool_name -> {plugin_id, method_name}
        self._tool_registry: Dict[str, Dict[str, str]] = {}

    def _init_fastmcp(self) -> Any:
        """延迟初始化 FastMCP（避免在主线程事件循环外创建）"""
        from mcp.server.fastmcp import FastMCP
        return FastMCP(self._name)

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

        # 记录工具映射
        self._tool_registry[name] = {
            "plugin_id": plugin_id,
            "method_name": method_name,
        }

        # 使用 FastMCP 的 tool 装饰器动态注册
        # 注意：FastMCP 的 add_tool 内部机制通过 mcp.tool() 装饰器实现，
        # 我们需要在装饰器下包装插件方法调用
        from core.plugin.manager import PluginManager

        def create_handler(p_id: str, m_name: str) -> Callable:
            async def handler(**kwargs: Any) -> Any:
                # 同步插件方法通过 anyio.to_thread 调用
                try:
                    import anyio.to_thread
                    result = await anyio.to_thread.run_sync(
                        PluginManager().call_plugin_method,
                        "",  # caller_id（Server 模式不需要）
                        p_id,
                        m_name,
                        **kwargs,
                    )
                    return result
                except Exception as e:
                    logger.error(f"MCP tool {name} call failed: {e}")
                    raise

            return handler

        # 为每个工具参数创建一个内部 handler 注册到 FastMCP
        # 由于 FastMCP 1.x 的 add_tool 是内部 API，我们使用替代方案：
        # 通过 _register_tool_direct 方法注册
        self._register_tool_direct(
            name=name,
            description=description,
            parameters=parameters,
            handler=create_handler(plugin_id, method_name),
        )

    def _register_tool_direct(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        handler: Callable,
    ) -> None:
        """直接注册工具到 FastMCP

        FastMCP 1.x 中，通过添加方法到 _tool_manager 来实现动态注册。
        """
        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        try:
            # 尝试使用 FastMCP 的工具管理器直接注册
            tool_manager = getattr(self._fastmcp, "_tool_manager", None)
            if tool_manager is not None:
                from mcp.server.fastmcp.tools import ToolManager, Tool
                from mcp.types import Tool as ToolType, TextContent
                import inspect

                # 构建 Tool 对象
                tool = Tool(
                    name=name,
                    description=description or "",
                    input_schema=parameters,
                    fn=handler,
                    annotations=None,
                )

                # 注册到工具管理器
                tool_manager._tools[name] = tool
                tool_manager._tool_functions[name] = handler
                logger.info(f"MCP tool registered: {name}")
                return

            # 备用方案：使用 @mcp.tool() 装饰器
            # 由于装饰器只能在类定义时使用，这里记录工具信息，
            # 在 run() 启动时统一注册
            logger.warning(
                f"ToolManager not accessible, recording tool {name} for deferred registration"
            )
            self._tool_registry[name]["deferred"] = {
                "description": description,
                "parameters": parameters,
                "handler": handler,
            }
        except Exception as e:
            logger.error(f"Failed to register MCP tool {name}: {e}")

    def remove_tool(self, name: str) -> None:
        """注销一个 MCP 工具"""
        if name in self._tool_registry:
            del self._tool_registry[name]
            logger.info(f"MCP tool unregistered: {name}")

        # 从 FastMCP 工具管理器中移除
        if self._fastmcp is not None:
            try:
                tool_manager = getattr(self._fastmcp, "_tool_manager", None)
                if tool_manager is not None and hasattr(tool_manager, "_tools"):
                    tool_manager._tools.pop(name, None)
                    tool_manager._tool_functions.pop(name, None)
            except Exception as e:
                logger.error(f"Failed to unregister MCP tool {name}: {e}")

    def _register_all_deferred_tools(self) -> None:
        """注册所有延迟注册的工具（在 run 之前调用）"""
        if self._fastmcp is None:
            return

        deferred = [
            (name, info)
            for name, info in self._tool_registry.items()
            if info.get("deferred")
        ]

        for name, info in deferred:
            deferred_info = info["deferred"]
            self._register_tool_direct(
                name=name,
                description=deferred_info["description"],
                parameters=deferred_info["parameters"],
                handler=deferred_info["handler"],
            )
            # 清除 deferred 标记
            self._tool_registry[name].pop("deferred", None)

    def run_stdio(self) -> None:
        """启动 MCP Server（stdio 传输）

        直接在当前进程 stdin/stdout 上运行 MCP 协议。
        适用于 Claude Code MCP Client 连接。
        """
        if self._running:
            logger.warning("MCP Server is already running")
            return

        if self._fastmcp is None:
            self._fastmcp = self._init_fastmcp()

        self._register_all_deferred_tools()

        try:
            self._fastmcp.run(transport="stdio")
        except Exception as e:
            logger.error(f"MCP stdio server error: {e}")
            self._running = False

    def run_http(self) -> None:
        """启动 MCP Server（streamable-http 传输）

        在后台线程中启动 HTTP 服务器。
        """
        if self._running:
            logger.warning("MCP Server is already running")
            return

        self._running = True

        def _run_in_thread() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                if self._fastmcp is None:
                    self._fastmcp = self._init_fastmcp()

                self._register_all_deferred_tools()

                self._fastmcp.run(
                    transport="streamable-http",
                    host=self._host,
                    port=self._port,
                )
            except Exception as e:
                logger.error(f"MCP HTTP server error: {e}")
                self._running = False
            finally:
                loop.close()

        self._thread = threading.Thread(target=_run_in_thread, daemon=True)
        self._thread.start()
        self._running = True
        logger.info(
            f"MCP HTTP Server starting on {self._host}:{self._port}"
        )

    def stop(self) -> None:
        """停止 MCP Server"""
        self._running = False
        logger.info("MCP Server stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def registered_tools(self) -> Dict[str, Dict[str, str]]:
        """返回所有已注册的工具映射"""
        return dict(self._tool_registry)
