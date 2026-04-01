"""
插件服务聚合对象

将插件所需的所有核心服务聚合到一个对象中，
通过依赖注入传递给插件。

插件开发者应通过 services.llm_facade 访问 LLM 能力，
而不是直接 import get_llm_provider()。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.llm.plugin_service import LLMPluginService
    from core.data import DataProvider
    from core.task import BackgroundTaskManager
    from utils.i_logger import ILogger


@dataclass
class PluginServices:
    """
    插件服务依赖注入容器

    框架在创建插件实例时会自动注入。
    插件开发者应通过 services.llm_facade 访问 LLM 能力，
    而不是直接 import get_llm_provider()。

    用法：

        class MyPlugin(IPlugin):
            def __init__(self, services: PluginServices | None = None):
                super().__init__()
                self._llm = (services.llm_facade
                             if services
                             else get_llm_plugin_service())

            def on_plugin_loaded(self):
                # self._services 已由 PluginManager 注入（通过实例属性）
                # self.plugin_id 已由 PluginManager 设置
                # self._services.logger 可用于日志记录（类型为 ILogger，实际为 LoggerManager 单例）
                ...
    """

    llm_facade: "LLMPluginService"
    data_provider: "DataProvider"
    task_manager: "BackgroundTaskManager"
    logger: "ILogger"
