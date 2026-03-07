"""
插件抽象基类
"""

import sys
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
from pathlib import Path
from PySide6.QtWidgets import QWidget, QApplication, QStyle
from PySide6.QtGui import QIcon
from PySide6.QtCore import QObject

if TYPE_CHECKING:
    from .plugin_info_interface import IPluginInfo


class IPlugin(ABC):
    """
    插件抽象基类
    """

    def __init__(self):
        """初始化插件"""
        self._plugin_id: Optional[str] = None
        self._plugin_name: Optional[str] = None
        self._cached_widget: Optional[QWidget] = None
        self._cached_parent: Optional[QWidget] = None

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
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        创建插件控件的内部方法

        Args:
            parent: 父控件
            data_provider: 主程序提供的数据对象（DataProvider）

        Returns:
            插件的 QWidget 控件
        """
        pass

    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        获取插件控件（带缓存）

        首次调用时创建 Widget 并缓存，后续调用返回缓存的实例
        如果传入了不同的 parent，会重新设置 Widget 的 parent

        Args:
            parent: 父控件
            data_provider: 主程序提供的数据对象（DataProvider）

        Returns:
            插件的 QWidget 控件
        """
        # 如果有缓存的 widget 且 parent 相同，直接返回
        if self._cached_widget is not None and self._cached_parent is parent:
            return self._cached_widget

        # 如果有缓存的 widget 但 parent 不同，更新 parent
        if self._cached_widget is not None:
            self._cached_widget.setParent(parent)
            self._cached_parent = parent
            return self._cached_widget

        # 创建新的 widget
        widget = self._create_widget(parent, data_provider)
        self._cached_widget = widget
        self._cached_parent = parent
        return widget
    
    @property
    def skill_icon(self) -> Optional[QIcon]:
        """
        返回技能按钮的图标
        从 information.py 中获取
        
        Returns:
            QIcon 对象，如果未定义则返回默认图标
        """
        try:
            import importlib.util
            
            # 获取插件实例的模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件目录（entrance.py 所在的目录）
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"
                
                # 如果 information.py 不存在，返回默认图标
                if not info_file.exists():
                    app = QApplication.instance()
                    if app and hasattr(app, 'style'):
                        return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                    return None
                
                # 使用 importlib.util 导入模块
                # 使用唯一的模块名避免冲突
                module_name = f"{plugin_dir.name}_information"
                spec = importlib.util.spec_from_file_location(module_name, info_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
                    
                    # 查找实现了 IPluginInfo 接口的类
                    from .plugin_info_interface import IPluginInfo
                    plugin_info_class = None
                    
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, IPluginInfo) and 
                            attr is not IPluginInfo):
                            plugin_info_class = attr
                            break
                    
                    if plugin_info_class:
                        icon = plugin_info_class().skill_icon.load_icon(plugin_dir)
                        
                        # 如果图标加载失败，返回默认图标
                        if icon is None or icon.isNull():
                            app = QApplication.instance()
                            if app and hasattr(app, 'style'):
                                return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                        
                        return icon
            
        except (ImportError, AttributeError, Exception) as e:
            print(f"Warning: Failed to load icon from information.py: {e}")
            import traceback
            traceback.print_exc()
        
        # 返回默认图标
        app = QApplication.instance()
        if app and hasattr(app, 'style'):
            return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        return None
    
    @property
    def skill_description(self) -> str:
        """
        返回技能的简短描述
        从 information.py 中获取
        
        Returns:
            描述字符串
        """
        try:
            import importlib.util
            
            # 获取插件实例的模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件目录（entrance.py 所在的目录）
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"
                
                # 如果 information.py 存在
                if info_file.exists():
                    # 使用 importlib.util 导入模块
                    module_name = f"{plugin_dir.name}_information"
                    spec = importlib.util.spec_from_file_location(module_name, info_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        
                        # 查找实现了 IPluginInfo 接口的类
                        from .plugin_info_interface import IPluginInfo
                        plugin_info_class = None
                        
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and 
                                issubclass(attr, IPluginInfo) and 
                                attr is not IPluginInfo):
                                plugin_info_class = attr
                                break
                        
                        if plugin_info_class:
                            return plugin_info_class().skill_description
            
        except (ImportError, AttributeError, Exception) as e:
            print(f"Warning: Failed to load description from information.py: {e}")
        
        # 返回默认描述
        return self.plugin_name
    
    @property
    def skill_tooltip(self) -> str:
        """
        返回技能按钮的工具提示
        
        Returns:
            工具提示字符串
        """
        return f"{self.plugin_name}\n{self.skill_description}"
    
    @property
    def plugin_id(self) -> Optional[str]:
        """
        返回插件的唯一标识符 (UUID)
        
        Returns:
            UUID 字符串，如果未设置则返回 None
        """
        return self._plugin_id
    
    @property
    def plugin_info(self) -> Optional['IPluginInfo']:
        """
        返回插件信息对象
        
        Returns:
            IPluginInfo 实例，如果插件未提供 information.py 则返回 None
        """
        try:
            import importlib.util
            
            # 获取插件实例的模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件目录（entrance.py 所在的目录）
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"
                
                # 如果 information.py 存在
                if info_file.exists():
                    # 使用 importlib.util 导入模块
                    module_name = f"{plugin_dir.name}_information"
                    spec = importlib.util.spec_from_file_location(module_name, info_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)
                        
                        # 查找实现了 IPluginInfo 接口的类
                        from .plugin_info_interface import IPluginInfo
                        plugin_info_class = None
                        
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if (isinstance(attr, type) and 
                                issubclass(attr, IPluginInfo) and 
                                attr is not IPluginInfo):
                                plugin_info_class = attr
                                break
                        
                        if plugin_info_class:
                            return plugin_info_class()
            
        except (ImportError, AttributeError, Exception) as e:
            print(f"Warning: Failed to load plugin info from information.py: {e}")
        
        return None
