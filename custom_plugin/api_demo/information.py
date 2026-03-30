"""
API 调用演示插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any

class ApiDemoPluginInfo(IPluginInfo):
    """API 调用演示插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        """开发者名称"""
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        """开发者邮箱"""
        return "support@example.com"
    
    @property
    def developer_website(self) -> str:
        """开发者网站"""
        return "https://github.com/KKPIP-Tech/InstructionX"
    
    @property
    def is_free(self) -> bool:
        """是否免费"""
        return True
    
    @property
    def description(self) -> str:
        """插件详细描述"""
        return """
        API 调用演示插件展示如何使用 PluginManager 的 API 调用功能。
        
        演示内容包括：
        - 如何通过 PluginManager 调用其他插件的方法
        - 如何获取插件 ID
        - 如何查询可用的 API 方法
        - 如何处理 API 调用错误
        - 如何获取 Function Tools 定义
        
        这个插件会调用字符串工具插件的 API 方法来展示功能。
        适合开发者学习如何实现插件间的协作。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        """Service API 定义（此插件不提供 API）"""
        return {}
    
    @property
    def skill_icon(self) -> PluginIcon:
        """插件图标配置"""
        return PluginIcon.builtin("SP_MessageBoxQuestion")
    
    @property
    def skill_description(self) -> str:
        """插件简短描述"""
        return "演示插件间 API 调用"
    
    @property
    def tags(self) -> list[str]:
        """插件标签"""
        return ["demo", "api", "tutorial", "example"]
    
    @property
    def dependencies(self) -> None:
        """依赖项"""
        return None

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符"""
        return "api-demo"