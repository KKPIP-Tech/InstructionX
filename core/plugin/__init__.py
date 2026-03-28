"""Plugin 模块 - 插件系统核心接口

该模块提供插件系统的核心接口定义，包括插件基类、插件信息接口等。
采用依赖注入设计，插件通过继承 IPlugin 基类实现自定义功能。

主要类和接口:
    - IPlugin: 插件抽象基类，定义所有插件必须实现的接口
    - IPluginInfo: 插件信息接口，定义插件元数据
    - PluginManager: 插件管理器（从 manager 模块导入）
    - PluginConfigManager: 插件配置管理器（从 config_manager 模块导入）

模块依赖:
    - PySide6.QtWidgets: Qt 控件库
    - utils.logging_tools: 日志工具

使用示例:
    >>> from core.plugin import IPlugin, PluginManager
    >>> # 创建自定义插件
    >>> class MyPlugin(IPlugin):
    ...     @property
    ...     def plugin_name(self) -> str:
    ...         return "我的插件"
"""

# 插件系统模块导出
from .plugin_interface import IPlugin
from .plugin_info_interface import IPluginInfo
from .manager import PluginManager
from .config_manager import PluginConfigManager


__all__ = [
    "IPlugin",
    "IPluginInfo",
    "PluginManager",
    "PluginConfigManager",
]