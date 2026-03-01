"""
插件元数据接口模块
定义插件元数据的抽象基类，规范插件信息管理
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .plugin_version import PluginVersion
from .plugin_icon import PluginIcon


class IPluginInfo(ABC):
    """
    插件元数据接口基类
    所有插件的 information.py 都应包含继承此类的类
    """
    
    @property
    @abstractmethod
    def version(self) -> PluginVersion:
        """
        插件版本号
        格式: <版本类型>.<大版本号>.<分支版本号>.<小版本号>
        示例: release.1.0.0, beta.1.2.0
        
        Returns:
            PluginVersion 对象
        """
        pass
    
    @property
    @abstractmethod
    def developer(self) -> str:
        """
        开发者名称（必填）
        
        Returns:
            开发者名称
        """
        pass
    
    @property
    @abstractmethod
    def developer_email(self) -> str:
        """
        开发者邮箱（必填）
        
        Returns:
            开发者邮箱地址
        """
        pass
    
    @property
    @abstractmethod
    def developer_website(self) -> str:
        """
        开发者网站（必填）
        
        Returns:
            开发者网站 URL
        """
        pass
    
    @property
    @abstractmethod
    def is_free(self) -> bool:
        """
        是否免费
        
        Returns:
            True 表示免费插件，False 表示付费插件
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        插件详细描述（用于 MCP 使用或其他用途）
        
        Returns:
            插件的详细功能描述文本
        """
        pass
    
    @property
    @abstractmethod
    def service_api(self) -> Dict[str, Any]:
        """
        Service API 文档（必填）
        
        返回 service.py 中所有公开方法的详细说明，格式：
        {
            "method_name": {
                "description": "方法描述",
                "parameters": {
                    "param_name": {
                        "type": "类型",
                        "description": "参数描述",
                        "required": True/False,
                        "default": "默认值（可选）"
                    }
                },
                "returns": {
                    "type": "返回类型",
                    "description": "返回值描述"
                }
            }
        }
        
        Returns:
            API 文档字典
        """
        pass
    
    @property
    @abstractmethod
    def skill_icon(self) -> PluginIcon:
        """
        插件图标（必填）
        
        Returns:
            PluginIcon 对象，定义插件的图标
        """
        pass
    
    @property
    @abstractmethod
    def skill_description(self) -> str:
        """
        插件简短描述（必填）
        用于在 UI 中显示的简短说明
        
        Returns:
            简短描述字符串
        """
        pass
    
    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        """
        依赖项（可选）
        
        Returns:
            依赖字典，如 {"numpy": ">=1.20.0", "pandas": ">=1.3.0"}
            如果无依赖则返回 None
        """
        return None
    
    @property
    def tags(self) -> Optional[list[str]]:
        """
        插件标签（可选）
        
        Returns:
            标签列表，如 ["text", "formatting", "utility"]
            如果无标签则返回 None
        """
        return None
    
    def get_summary(self) -> str:
        """
        获取插件摘要信息
        
        Returns:
            格式化的插件摘要字符串
        """
        version_str = self.version.get_display_version()
        summary = f"{self.developer} - {version_str}"
        if not self.is_free:
            summary += " [付费]"
        return summary