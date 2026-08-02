"""
MCP Manager 单例

核心协调器，管理 MCP Server 和 MCP Client 的生命周期，
提供统一的配置管理和工具同步入口。
"""

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from core.mcp.config import (
    MCPConfig,
    MCPServerConfig,
    MCPRemoteServerConfig,
)
from core.mcp.server import MCPHostServer
from core.mcp.client import MCPClientManager
from core.mcp.bridge import MCPBridge

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 核心管理器

    提供 MCP Server 和 MCP Client 的统一管理接口。

    MCP Server 模式：暴露本地插件工具给外部 MCP Client（如 Claude Code）
    MCP Client 模式：连接外部 MCP Server，将它们的工具引入本地 LLM

    用法::

        mcp = get_mcp_manager()

        # 启动 MCP Server
        mcp.start_server(transport="stdio")

        # 连接外部 MCP Server
        config = MCPRemoteServerConfig(
            server_id="filesystem",
            name="Filesystem",
            transport="stdio",
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        )
        mcp.connect(config)
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._config: MCPConfig = MCPConfig()
        # 基于项目根推导配置路径（不依赖 CWD），环境变量可覆盖
        self._config_file = self._resolve_config_file()

        # MCP Server
        self._server: Optional[MCPHostServer] = None

        # MCP Client
        # ToolRegistry 会在 init_client() 中注入
        self._client_manager: Optional[MCPClientManager] = None

        # 桥接器
        self._bridge: Optional[MCPBridge] = None

        # 加载配置
        self._load_config()

    # ─── 配置管理 ────────────────────────────────────────────────

    @staticmethod
    def _resolve_config_file() -> Path:
        """解析配置文件路径

        默认基于项目根（core/mcp/manager.py 上溯两级）推导，
        环境变量 INSTRUCTIONX_MCP_CONFIG 可覆盖。
        """
        env_path = os.environ.get("INSTRUCTIONX_MCP_CONFIG")
        if env_path:
            return Path(env_path)
        return Path(__file__).resolve().parents[2] / "config" / "mcp_config.json"

    def _load_config(self) -> None:
        """从配置文件加载 MCP 配置"""
        if not self._config_file.exists():
            self._config = MCPConfig()
            self._save_config()
            return

        try:
            with open(self._config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._config = MCPConfig.from_dict(data)
            logger.info(f"MCP config loaded from {self._config_file}")
        except Exception as e:
            logger.warning(f"Failed to load MCP config: {e}, using defaults")
            self._config = MCPConfig()

    def _save_config(self) -> None:
        """保存 MCP 配置到文件"""
        try:
            self._config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(self._config.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save MCP config: {e}")

    def get_config(self) -> MCPConfig:
        """返回当前 MCP 配置"""
        return self._config

    def update_server_config(self, config: MCPServerConfig) -> None:
        """更新 MCP Server 配置"""
        with self._lock:
            self._config.server = config
            self._save_config()

    def add_remote_server(self, config: MCPRemoteServerConfig) -> None:
        """添加外部 MCP Server 配置"""
        with self._lock:
            # 避免重复
            for i, existing in enumerate(self._config.remote_servers):
                if existing.server_id == config.server_id:
                    self._config.remote_servers[i] = config
                    break
            else:
                self._config.remote_servers.append(config)
            self._save_config()

    def remove_remote_server(self, server_id: str) -> bool:
        """移除外部 MCP Server 配置"""
        with self._lock:
            original = len(self._config.remote_servers)
            self._config.remote_servers = [
                s for s in self._config.remote_servers
                if s.server_id != server_id
            ]
            if len(self._config.remote_servers) != original:
                self._save_config()
                return True
            return False

    # ─── MCP Server ──────────────────────────────────────────────

    def _init_server(self) -> MCPHostServer:
        """初始化 MCP Server"""
        if self._server is None:
            with self._lock:
                if self._server is None:
                    self._server = MCPHostServer(
                        name="InstructionX",
                        host=self._config.server.host,
                        port=self._config.server.port,
                        auth_token=self._config.server.auth_token,
                    )
                    # 初始化桥接器
                    self._bridge = MCPBridge(self)
        return self._server

    def start_server(self, transport: Optional[str] = None) -> None:
        """启动 MCP Server

        Args:
            transport: 传输方式，"stdio" 或 "streamable-http"。
                       如果为 None，使用配置中的默认值。
        """
        if not self._config.server.enabled:
            logger.info("MCP Server is disabled in config, skipping start")
            return

        if self._server is None:
            self._init_server()

        trans = transport or self._config.server.transport
        if trans not in ("stdio", "streamable-http"):
            raise ValueError(f"Unsupported transport: {trans}")

        # 同步现有插件工具到 MCP Server（必须在 run 之前：
        # stdio 模式的 run_stdio() 会阻塞，之后同步永远不会执行）
        if self._bridge:
            self._bridge.sync_plugin_api_to_mcp_server()

        if trans == "stdio":
            # 注意：run_stdio() 会阻塞直到 Server 退出，不应在 Qt 主线程调用
            logger.info("MCP Server starting with transport: stdio (blocking)")
            self._server.run_stdio()
            logger.info("MCP stdio Server exited")
        else:
            self._server.run_http()
            if self._server.is_running:
                logger.info(f"MCP Server started with transport: {trans}")
            else:
                logger.error(
                    f"MCP Server failed to start with transport: {trans}"
                )

    def stop_server(self) -> None:
        """停止 MCP Server"""
        if self._server:
            self._server.stop()
            logger.info("MCP Server stopped")

    def is_server_running(self) -> bool:
        """MCP Server 是否正在运行"""
        return self._server is not None and self._server.is_running

    def get_server_url(self) -> str:
        """返回 MCP Server 的 HTTP 地址（Server 已初始化即返回，不看传输模式；未初始化返回空串）"""
        if self._server is None:
            return ""
        return f"http://{self._config.server.host}:{self._config.server.port}"

    def get_server(self) -> Optional[MCPHostServer]:
        """返回 MCPHostServer 实例（可能为 None）"""
        return self._server

    def get_server_config(self) -> MCPServerConfig:
        """返回当前 Server 配置"""
        return self._config.server

    # ─── MCP Client ──────────────────────────────────────────────

    def _init_client(self, tool_registry: Any) -> MCPClientManager:
        """初始化 MCP Client Manager"""
        if self._client_manager is None:
            with self._lock:
                if self._client_manager is None:
                    self._client_manager = MCPClientManager(tool_registry)
        return self._client_manager

    def get_client_manager(
        self,
        tool_registry: Optional[Any] = None,
    ) -> MCPClientManager:
        """获取 MCPClientManager 实例

        Args:
            tool_registry: 如果尚未初始化，需要传入 ToolRegistry 实例
        """
        if self._client_manager is None:
            if tool_registry is None:
                raise ValueError(
                    "tool_registry required on first call to get_client_manager"
                )
            self._init_client(tool_registry)
        return self._client_manager

    def connect(
        self,
        config: MCPRemoteServerConfig,
        tool_registry: Optional[Any] = None,
    ) -> str:
        """连接到外部 MCP Server

        Args:
            config: 外部 Server 配置
            tool_registry: ToolRegistry 实例（首次调用时必需）

        Returns:
            server_id
        """
        if not config.enabled:
            logger.info(
                f"Remote MCP server {config.server_id} is disabled, "
                f"skipping connect"
            )
            return config.server_id
        client = self.get_client_manager(tool_registry)
        client.connect(config)
        return config.server_id

    def disconnect(self, server_id: str) -> None:
        """断开与外部 MCP Server 的连接"""
        if self._client_manager:
            self._client_manager.disconnect(server_id)

    def list_connected_servers(self) -> List[str]:
        """返回已连接的 server_id 列表"""
        if self._client_manager is None:
            return []
        return self._client_manager.list_connected_servers()

    def list_remote_tools(self, server_id: str) -> List[str]:
        """列出指定外部 Server 上的工具"""
        if self._client_manager is None:
            return []
        return self._client_manager.list_tools(server_id)

    # ─── 桥接 ────────────────────────────────────────────────────

    def get_bridge(self) -> Optional[MCPBridge]:
        """返回 MCPBridge 实例"""
        return self._bridge

    def sync_plugin_tool(
        self,
        plugin_id: str,
        method_name: str,
        description: str,
        parameters: Dict[str, Any],
    ) -> None:
        """通知 MCP 系统有新插件工具注册

        由 PluginManager 在注册新 API 时调用。
        """
        if self._bridge:
            self._bridge.sync_new_plugin_tool(
                plugin_id=plugin_id,
                method_name=method_name,
                description=description,
                parameters=parameters,
            )

    def remove_plugin_tool(self, plugin_id: str, method_name: str) -> None:
        """通知 MCP 系统有插件工具被注销"""
        if self._bridge:
            self._bridge.remove_plugin_tool(plugin_id, method_name)

    # ─── 生命周期 ────────────────────────────────────────────────

    def shutdown(self) -> None:
        """关闭 MCP Manager，清理所有资源"""
        self.stop_server()
        if self._client_manager:
            self._client_manager.shutdown()
        logger.info("MCP Manager shutdown complete")


# ─── 模块级便捷函数 ───────────────────────────────────────────

_module_lock = threading.Lock()
_module_instance: Optional["MCPManager"] = None


def get_mcp_manager() -> "MCPManager":
    """获取 MCPManager 全局单例"""
    global _module_instance
    if _module_instance is None:
        with _module_lock:
            if _module_instance is None:
                _module_instance = MCPManager()
    return _module_instance
