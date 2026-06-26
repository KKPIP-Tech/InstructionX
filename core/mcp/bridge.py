"""
MCP 双向桥接

桥接应用内插件 API 系统和 MCP Server/Client。
- 同步 PluginManager 的 API 注册到 MCP Server
- 同步外部 MCP Server 的工具到 ToolRegistry（通过 MCPClientManager）
"""

import logging
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from core.mcp.manager import MCPManager
    from core.mcp.server import MCPHostServer

logger = logging.getLogger(__name__)


class MCPBridge:
    """MCP 协议与插件系统的双向桥接器

    负责将 PluginManager 中注册的插件 API 同步到 MCP Server，
    使外部 MCP Client 可以调用 InstructionX 的插件工具。
    """

    def __init__(self, manager: "MCPManager"):
        self._manager = manager
        self._synced_tools: Dict[str, bool] = {}

    def sync_plugin_api_to_mcp_server(self) -> None:
        """将所有已注册的插件 API 同步到 MCP Server

        在 MCP Server 启动时调用，将当前已存在的插件 API
        全部注册为 MCP 工具。
        """
        server: "MCPHostServer" = self._manager.get_server()
        if server is None:
            logger.warning("MCP Server not initialized, skipping sync")
            return

        try:
            from core.plugin.manager import get_plugin_manager
            pm = get_plugin_manager()

            # 获取所有插件 API 描述
            all_tools = pm.get_all_function_tools()

            for tool in all_tools:
                func_def = tool.get("function", {})
                name = func_def.get("name", "")

                # 跳过已同步的工具
                if self._synced_tools.get(name):
                    continue

                # 解析 plugin_id.method_name 格式
                parts = name.split(".", 1)
                if len(parts) != 2:
                    continue

                plugin_id, method_name = parts

                server.add_tool(
                    name=name,
                    description=func_def.get("description", ""),
                    parameters=func_def.get("parameters", {}),
                    plugin_id=plugin_id,
                    method_name=method_name,
                )
                self._synced_tools[name] = True
                logger.debug(f"Synced plugin tool to MCP: {name}")

            logger.info(
                f"MCP Bridge synced {len(all_tools)} plugin tools to MCP Server"
            )

        except Exception as e:
            logger.error(f"Failed to sync plugin API to MCP Server: {e}")

    def sync_new_plugin_tool(
        self,
        plugin_id: str,
        method_name: str,
        description: str,
        parameters: Dict[str, Any],
    ) -> None:
        """同步单个新注册的插件工具到 MCP Server

        在新插件加载或 API 注册时调用。

        Args:
            plugin_id: 插件 ID
            method_name: 方法名称
            description: 方法描述
            parameters: JSON Schema 参数定义
        """
        server: "MCPHostServer" = self._manager.get_server()
        if server is None:
            return

        tool_name = f"{plugin_id}.{method_name}"

        if self._synced_tools.get(tool_name):
            return

        try:
            server.add_tool(
                name=tool_name,
                description=description,
                parameters=parameters,
                plugin_id=plugin_id,
                method_name=method_name,
            )
            self._synced_tools[tool_name] = True
            logger.debug(f"MCP Bridge synced new tool: {tool_name}")
        except Exception as e:
            logger.error(f"Failed to sync new tool {tool_name}: {e}")

    def remove_plugin_tool(self, plugin_id: str, method_name: str) -> None:
        """从 MCP Server 注销一个插件工具

        Args:
            plugin_id: 插件 ID
            method_name: 方法名称
        """
        server: "MCPHostServer" = self._manager.get_server()
        if server is None:
            return

        tool_name = f"{plugin_id}.{method_name}"

        try:
            server.remove_tool(tool_name)
            self._synced_tools.pop(tool_name, None)
            logger.debug(f"MCP Bridge removed tool: {tool_name}")
        except Exception as e:
            logger.error(f"Failed to remove tool {tool_name}: {e}")

    def get_synced_tool_count(self) -> int:
        """返回已同步的工具数量"""
        return len(self._synced_tools)
