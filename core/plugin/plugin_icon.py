"""
插件图标管理模块
提供多种图标类型的加载和管理功能
"""

from enum import Enum
from pathlib import Path
from typing import Optional
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QStyle, QStyleFactory
from PySide6.QtCore import QByteArray


class IconType(Enum):
    """图标类型枚举"""
    BUILTIN = "builtin"        # 内置系统图标
    FILE = "file"              # 图标文件路径
    RESOURCE = "resource"      # Qt 资源路径
    BASE64 = "base64"          # Base64 编码
    NONE = "none"              # 无图标（使用默认）


class PluginIcon:
    """
    插件图标管理类
    支持多种图标类型和加载方式
    """
    
    def __init__(
        self,
        icon_type: IconType,
        value: Optional[str] = None
    ):
        """
        初始化插件图标
        
        Args:
            icon_type: 图标类型
            value: 图标值（根据类型不同而不同）
                  - builtin: 系统图标名称，如 "SP_FileIcon"
                  - file: 图标文件相对路径，如 "icons/icon.png"
                  - resource: Qt 资源路径，如 ":/icons/icon.png"
                  - base64: Base64 编码的图片数据
                  - none: 无需提供值
        """
        self.icon_type = icon_type
        self.value = value
    
    def load_icon(self, plugin_dir: Optional[Path] = None) -> Optional[QIcon]:
        """
        加载图标
        
        Args:
            plugin_dir: 插件目录路径（用于相对路径解析）
            
        Returns:
            QIcon 对象，如果加载失败则返回 None
        """
        try:
            if self.icon_type == IconType.NONE:
                return None
            
            elif self.icon_type == IconType.BUILTIN:
                # 加载系统内置图标
                if self.value:
                    from PySide6.QtWidgets import QStyle, QStyleFactory
                    app = QApplication.instance()
                    if not app or not isinstance(app, QApplication):
                        # 如果没有应用实例，使用默认样式
                        style = QStyleFactory.create('windows')
                        if not style:
                            return None
                    else:
                        style = app.style()
                    
                    # 尝试获取标准图标
                    try:
                        if hasattr(QStyle.StandardPixmap, self.value):
                            standard_pixmap = getattr(QStyle.StandardPixmap, self.value)
                            return style.standardIcon(standard_pixmap)
                    except (AttributeError, ValueError):
                        # 如果指定的图标不存在，返回 None
                        return None
            
            elif self.icon_type == IconType.FILE:
                # 从文件加载图标
                if self.value and plugin_dir:
                    icon_path = plugin_dir / self.value
                    if icon_path.exists():
                        return QIcon(str(icon_path))
            
            elif self.icon_type == IconType.RESOURCE:
                # 从 Qt 资源加载图标
                if self.value:
                    return QIcon(self.value)
            
            elif self.icon_type == IconType.BASE64:
                # 从 Base64 编码加载图标
                if self.value:
                    import base64
                    from PySide6.QtGui import QPixmap
                    
                    # 解码 Base64
                    image_data = base64.b64decode(self.value)
                    qba = QByteArray(image_data)
                    pixmap = QPixmap()
                    if pixmap.loadFromData(qba):
                        return QIcon(pixmap)
            
            return None
            
        except Exception as e:
            print(f"Error loading icon: {e}")
            return None
    
    @classmethod
    def builtin(cls, icon_name: str) -> 'PluginIcon':
        """
        创建内置系统图标
        
        Args:
            icon_name: 系统图标名称，如 "SP_FileIcon"
            
        Returns:
            PluginIcon 实例
        """
        return cls(IconType.BUILTIN, icon_name)
    
    @classmethod
    def from_file(cls, relative_path: str) -> 'PluginIcon':
        """
        从文件创建图标
        
        Args:
            relative_path: 相对于插件目录的图标文件路径
            
        Returns:
            PluginIcon 实例
        """
        return cls(IconType.FILE, relative_path)
    
    @classmethod
    def from_resource(cls, resource_path: str) -> 'PluginIcon':
        """
        从 Qt 资源创建图标
        
        Args:
            resource_path: Qt 资源路径，如 ":/icons/icon.png"
            
        Returns:
            PluginIcon 实例
        """
        return cls(IconType.RESOURCE, resource_path)
    
    @classmethod
    def from_base64(cls, base64_data: str) -> 'PluginIcon':
        """
        从 Base64 数据创建图标
        
        Args:
            base64_data: Base64 编码的图片数据
            
        Returns:
            PluginIcon 实例
        """
        return cls(IconType.BASE64, base64_data)
    
    @classmethod
    def none(cls) -> 'PluginIcon':
        """
        创建无图标（使用默认图标）
        
        Returns:
            PluginIcon 实例
        """
        return cls(IconType.NONE)