"""
插件元数据接口模块

定义插件元数据的抽象基类，规范插件信息管理。

注意：此文件已迁移至 core/interfaces/i_plugin_info.py。
此处保留作为向后兼容的导入路径。
"""

# 向后兼容导入
from core.interfaces.i_plugin_info import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

__all__ = ["IPluginInfo", "PluginVersion", "PluginIcon"]
