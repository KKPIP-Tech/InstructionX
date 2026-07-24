"""
MCP 双向桥接

桥接应用内插件 API 系统和 MCP Server/Client。
- 同步 PluginManager 的 API 注册到 MCP Server
- 同步外部 MCP Server 的工具到 ToolRegistry（通过 MCPClientManager）
"""

import logging
import threading
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

# core.plugin.manager 对 core.mcp 的引用为函数级，此处顶部导入不构成循环依赖
from core.plugin.manager import get_plugin_manager
from core.plugin.tool_name import sanitize_tool_name

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
        """初始化桥接器

        Args:
            manager: MCPManager 单例实例，用于获取 MCP Server 实例
                     与 Server 配置（插件暴露白名单等）
        """
        self._manager = manager
        # 已同步工具的簿记。key 为 pair key "{plugin_id}.{method_name}"
        # （仅内部使用，与历史行为兼容）；实际注册到 MCP Server 的
        # 工具名为 sanitize_tool_name(f"{plugin_id}__{method_name}")。
        self._synced_tools: Dict[str, bool] = {}
        # 保护 _synced_tools 的 check-then-act 路径
        self._lock = threading.Lock()

    @staticmethod
    def _pair_key(plugin_id: str, method_name: str) -> str:
        """内部簿记用的 (plugin_id, method_name) 对 key"""
        return f"{plugin_id}.{method_name}"

    def _get_exposed_plugins(self) -> Optional[List[str]]:
        """读取 Server 配置中的插件暴露白名单

        返回值语义（注意 None 与 [] 的区别）：
            - None：未配置白名单（或配置值非列表类型，如测试中的 Mock），
              表示暴露全部插件（向后兼容默认行为）；
            - []：配置读取失败，**失败关闭**——一个插件都不暴露，
              避免配置异常时静默放大 MCP 暴露面；
            - 非空列表：仅暴露白名单内的插件。
        """
        try:
            config = self._manager.get_server_config()
            exposed = getattr(config, "exposed_plugins", None)
        except Exception as e:
            logger.error(
                f"读取 MCP 插件暴露白名单失败，按失败关闭处理（不暴露任何插件）: {e}"
            )
            return []
        if isinstance(exposed, (list, tuple, set, frozenset)):
            return list(exposed)
        return None

    @staticmethod
    def _parse_tool_name(name: str) -> Optional[Tuple[str, str]]:
        """从工具名解析 (plugin_id, method_name)

        新规则名为 sanitize_tool_name(f"{plugin_id}__{method_name}")，
        plugin_id 为 UUID（含连字符、不含双下划线），按 "__" 分割安全；
        兼容旧的 "plugin_id.method_name" 点分格式。
        """
        if "__" in name:
            parts = name.split("__", 1)
        elif "." in name:
            parts = name.split(".", 1)
        else:
            return None
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        return parts[0], parts[1]

    def sync_plugin_api_to_mcp_server(self) -> None:
        """将所有已注册的插件 API 同步到 MCP Server

        在 MCP Server 启动时调用，将当前已存在的插件 API
        全部注册为 MCP 工具。受 MCPServerConfig.exposed_plugins
        白名单过滤（None 表示全部暴露）。
        """
        server: "MCPHostServer" = self._manager.get_server()
        if server is None:
            logger.warning("MCP Server not initialized, skipping sync")
            return

        try:
            pm = get_plugin_manager()

            exposed_plugins = self._get_exposed_plugins()

            # 获取所有插件 API 描述
            all_tools = pm.get_all_function_tools()

            synced_count = 0
            for tool in all_tools:
                func_def = tool.get("function", {})
                name = func_def.get("name", "")

                # 解析 (plugin_id, method_name)
                parsed = self._parse_tool_name(name)
                if parsed is None:
                    continue
                plugin_id, method_name = parsed

                # 白名单过滤（None 表示不过滤）
                if exposed_plugins is not None and plugin_id not in exposed_plugins:
                    continue

                # 工具名与 PluginManager.get_all_function_tools 规则一致
                tool_name = sanitize_tool_name(name)
                pair_key = self._pair_key(plugin_id, method_name)

                # 跳过已同步的工具（check-then-act 加锁）
                with self._lock:
                    if self._synced_tools.get(pair_key):
                        continue
                    self._synced_tools[pair_key] = True

                server.add_tool(
                    name=tool_name,
                    description=func_def.get("description", ""),
                    parameters=func_def.get("parameters", {}),
                    plugin_id=plugin_id,
                    method_name=method_name,
                )
                synced_count += 1
                logger.debug(f"Synced plugin tool to MCP: {tool_name}")

            logger.info(
                f"MCP Bridge synced {synced_count}/{len(all_tools)} "
                f"plugin tools to MCP Server"
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
        工具名规则与 PluginManager.get_all_function_tools 一致：
        sanitize_tool_name(f"{plugin_id}__{method_name}")。

        Args:
            plugin_id: 插件 ID
            method_name: 方法名称
            description: 方法描述
            parameters: JSON Schema 参数定义
        """
        server: "MCPHostServer" = self._manager.get_server()
        if server is None:
            return

        # 白名单过滤
        exposed_plugins = self._get_exposed_plugins()
        if exposed_plugins is not None and plugin_id not in exposed_plugins:
            logger.debug(
                f"Plugin {plugin_id} not in exposed_plugins, skipping sync"
            )
            return

        tool_name = sanitize_tool_name(f"{plugin_id}__{method_name}")
        pair_key = self._pair_key(plugin_id, method_name)

        with self._lock:
            if self._synced_tools.get(pair_key):
                return
            self._synced_tools[pair_key] = True

        try:
            server.add_tool(
                name=tool_name,
                description=description,
                parameters=parameters,
                plugin_id=plugin_id,
                method_name=method_name,
            )
            logger.debug(f"MCP Bridge synced new tool: {tool_name}")
        except Exception as e:
            with self._lock:
                self._synced_tools.pop(pair_key, None)
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

        tool_name = sanitize_tool_name(f"{plugin_id}__{method_name}")
        pair_key = self._pair_key(plugin_id, method_name)

        try:
            server.remove_tool(tool_name)
            with self._lock:
                self._synced_tools.pop(pair_key, None)
            logger.debug(f"MCP Bridge removed tool: {tool_name}")
        except Exception as e:
            logger.error(f"Failed to remove tool {tool_name}: {e}")

    def get_synced_tool_count(self) -> int:
        """返回已同步的工具数量"""
        with self._lock:
            return len(self._synced_tools)
