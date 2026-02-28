from abc import ABC, abstractmethod
from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject


class IPlugin(ABC):
    """
    插件抽象基类
    """
    
    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """
        插件名称
        
        Returns:
            插件名称字符串
        """
        pass
    
    @abstractmethod
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        获取插件控件
        
        Args:
            parent: 父控件
            data_provider: 主程序提供的数据对象（DataProvider）
            
        Returns:
            插件的 QWidget 控件
        """
        pass
    
    @property
    def skill_icon(self) -> Optional[QIcon]:
        """
        返回技能按钮的图标
        
        Returns:
            QIcon 对象，默认返回 None（使用默认图标）
        """
        return None
    
    @property
    def skill_description(self) -> str:
        """
        返回技能的简短描述
        
        Returns:
            描述字符串，默认返回插件名称
        """
        return self.plugin_name
    
    @property
    def skill_tooltip(self) -> str:
        """
        返回技能按钮的工具提示
        
        Returns:
            工具提示字符串
        """
        return f"{self.plugin_name}\n{self.skill_description}"
