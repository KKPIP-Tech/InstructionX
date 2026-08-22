"""
插件服务聚合对象

将插件所需的所有核心服务聚合到一个对象中，
通过依赖注入传递给插件。

插件开发者应通过 services.llm_facade 访问 LLM 能力，
通过 services.mcp_manager 管理 MCP Server，
通过 services.mcp_client 连接外部 MCP Server。
"""

from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .i_llm_service import ILLMService
    from core.data import DataProvider
    from core.task import BackgroundTaskManager
    from utils.i_logger import ILogger
    from core.mcp.manager import MCPManager
    from core.mcp.client import MCPClientManager
    from core.font import FontManager
    from .i_localization import ILocalizationFacade


@dataclass
class PluginServices:
    """
    插件服务依赖注入容器

    框架在创建插件实例时会自动注入。
    插件开发者应通过 services.llm_facade 访问 LLM 能力，
    通过 services.mcp_manager 管理 MCP Server，
    通过 services.mcp_client 连接外部 MCP Server，
    通过 services.localization 访问多语言取词门面。

    用法：

        class MyPlugin(IPlugin):
            def __init__(self, services: PluginServices | None = None):
                super().__init__()
                self._llm = (services.llm_facade
                             if services
                             else get_llm_plugin_service())
                self._mcp_manager = services.mcp_manager if services else None

            def on_plugin_loaded(self):
                # self._services 已由 PluginManager 注入（通过实例属性）
                # self.plugin_id 已由 PluginManager 设置
                # self._services.logger 可用于日志记录（类型为 ILogger，实际为 LoggerManager 单例）
                ...
    """

    llm_facade: "ILLMService"
    data_provider: "DataProvider"
    task_manager: "BackgroundTaskManager"
    logger: "ILogger"
    mcp_manager: Optional["MCPManager"] = field(default=None)
    mcp_client: Optional["MCPClientManager"] = field(default=None)
    # 字体管理器（安装/卸载/回退解析），无降级保护、始终注入
    font_manager: Optional["FontManager"] = field(default=None)
    # 多语言取词门面（绑定插件 UUID），无降级保护、始终注入
    localization: Optional["ILocalizationFacade"] = field(default=None)
