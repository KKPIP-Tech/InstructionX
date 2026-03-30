"""
插件服务聚合对象

将插件所需的所有核心服务聚合到一个对象中，
通过依赖注入传递给插件。

注意：这是框架预留的依赖注入设计。当前所有插件均直接导入单例
（如 DataProvider() / BackgroundTaskManager()），而非通过 PluginServices 注入。
此设计为未来插件隔离和测试提供基础。
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .i_data_provider import IDataProvider
    from .i_task_manager import ITaskManager
    from .i_llm_facade import ILLMFacade
    from .i_logger import ILogger


@dataclass
class PluginServices:
    """
    插件服务聚合对象

    通过依赖注入传递给插件，包含所有插件可能需要访问的核心服务。
    插件通过 services.data_provider、services.task_manager 等访问服务，
    而非直接实例化或访问全局单例。

    当前状态：此设计为预留架构。当前所有插件均直接导入单例，
    未使用 PluginServices 进行依赖注入。

    Example:
        class MyPlugin(IPlugin):
            def _create_widget(self, parent=None, data_provider=None):
                dp = data_provider if data_provider else DataProvider()
                tm = BackgroundTaskManager()
                ...
    """

    data_provider: 'IDataProvider'
    task_manager: 'ITaskManager'
    llm_facade: 'ILLMFacade' = None
    logger: 'ILogger' = None
