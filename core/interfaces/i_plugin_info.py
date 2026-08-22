"""
PluginInfo 插件元数据接口

定义插件元数据的抽象基类，规范插件信息管理。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, TYPE_CHECKING

# 仅类型检查时导入，避免接口层在运行时牵入 core.plugin 与 PySide6
if TYPE_CHECKING:
    from core.plugin.plugin_version import PluginVersion
    from core.plugin.plugin_icon import PluginIcon


class IPluginInfo(ABC):
    """
    插件元数据接口基类
    所有插件的 information.py 都应包含继承此类的类
    """

    @property
    @abstractmethod
    def version(self) -> "PluginVersion":
        """插件版本号"""
        pass

    @property
    @abstractmethod
    def developer(self) -> str:
        """开发者名称"""
        pass

    @property
    @abstractmethod
    def developer_email(self) -> str:
        """开发者邮箱"""
        pass

    @property
    @abstractmethod
    def developer_website(self) -> str:
        """开发者网站"""
        pass

    @property
    @abstractmethod
    def is_free(self) -> bool:
        """是否免费"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """插件详细描述"""
        pass

    @property
    @abstractmethod
    def service_api(self) -> Dict[str, Any]:
        """Service API 文档"""
        pass

    @property
    @abstractmethod
    def skill_icon(self) -> "PluginIcon":
        """插件图标"""
        pass

    @property
    @abstractmethod
    def skill_description(self) -> str:
        """插件简短描述（用于 UI 展示）"""
        pass

    @property
    @abstractmethod
    def plugin_type_id(self) -> str:
        """
        插件类型标识符
        用于代码层面的插件识别，应保持稳定不随显示名称变化。
        建议使用小写字母、数字、连字符格式，如 "string-tools"。
        """
        pass

    @property
    def dependencies(self) -> Optional[Dict[str, str]]:
        """依赖项"""
        return None

    @property
    def tags(self) -> Optional[list[str]]:
        """插件标签"""
        return None

    @property
    def default_language(self) -> Optional[str]:
        """插件默认语言（ISO 639-1 语言代码，对应 text/<代码>.xml 文件名）

        插件取词时有效语言缺失的键会回退到本语言；返回 None（默认实现）
        表示跟随框架默认语言。插件声明了本属性但未提供对应语言文件时，
        按框架默认语言回退。
        """
        return None
