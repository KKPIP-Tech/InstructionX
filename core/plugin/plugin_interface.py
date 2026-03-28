"""
插件系统抽象基类

定义所有插件必须实现的接口规范，包括：
- 插件名称属性
- 控件创建方法
- 缓存机制
- 技能图标和描述获取
- 生命周期回调
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

from utils.logging_tools import LoggerManager, get_name


class IPlugin(ABC):
    """
    插件抽象基类

    所有插件必须继承此类并实现抽象方法。该类提供：
    - 插件唯一标识和名称管理
    - 控件缓存机制，避免重复创建
    - 技能图标和描述的动态加载
    - 插件生命周期回调钩子
    """

    _logger = LoggerManager()

    def __init__(self):
        """初始化插件实例的内部状态"""
        self._plugin_id: Optional[str] = None
        self._plugin_name: Optional[str] = None
        self._cached_widget: Optional[QWidget] = None
        self._cached_parent: Optional[QWidget] = None

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """
        获取插件显示名称

        Returns:
            插件显示名称，用于界面展示和标识
        """
        pass

    @abstractmethod
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        创建插件用户界面控件

        子类必须实现此方法以创建自己的 Qt 控件。该方法在插件首次激活时调用，
        之后会通过缓存机制复用已创建的控件实例。

        Args:
            parent: 父控件，传递工作区的中心控件作为父容器
            data_provider: 数据提供者实例，用于数据读写和插件间通信

        Returns:
            插件的 Qt 用户界面控件
        """
        pass

    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        获取插件界面控件

        实现缓存机制：首次调用时创建控件并缓存，后续调用直接返回缓存实例。
        如果父控件发生变化，会自动更新控件的父级设置。

        Args:
            parent: 父控件，传递工作区的中心控件作为父容器
            data_provider: 数据提供者实例，用于数据读写和插件间通信

        Returns:
            插件的 Qt 用户界面控件
        """
        # 缓存命中且父控件未变，直接返回缓存的控件
        if self._cached_widget is not None and self._cached_parent is parent:
            return self._cached_widget

        # 缓存存在但父控件改变，更新父控件引用
        if self._cached_widget is not None:
            self._cached_widget.setParent(parent)
            self._cached_parent = parent
            return self._cached_widget

        # 首次创建，创建新控件并缓存
        widget = self._create_widget(parent, data_provider)
        self._cached_widget = widget
        self._cached_parent = parent
        return widget
    
    @property
    def skill_icon(self) -> Optional[QIcon]:
        """
        获取技能面板按钮图标

        动态从插件目录下的 information.py 文件中加载图标配置。
        如果文件不存在或加载失败，返回系统默认图标。

        Returns:
            Qt 图标对象，加载失败时返回系统默认文件图标
        """
        try:
            import importlib.util

            # 获取插件模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件根目录
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"

                # 文件不存在时返回默认图标
                if not info_file.exists():
                    app = QApplication.instance()
                    if app and hasattr(app, 'style'):
                        return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
                    return None

                # 动态加载 information.py 模块
                module_name = f"{plugin_dir.name}_information"
                spec = importlib.util.spec_from_file_location(module_name, info_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)

                    # 查找实现 IPluginInfo 接口的类
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

                        # 图标加载失败时返回默认图标
                        if icon is None or icon.isNull():
                            app = QApplication.instance()
                            if app and hasattr(app, 'style'):
                                return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)

                        return icon

        except (ImportError, AttributeError, Exception) as e:
            self._logger.warning(get_name(), f'Failed to load icon from information.py: {e}')

        # 所有加载失败时返回系统默认图标
        app = QApplication.instance()
        if app and hasattr(app, 'style'):
            return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        return None
    
    @property
    def skill_description(self) -> str:
        """
        获取技能面板按钮的简短描述文本

        动态从插件目录下的 information.py 文件中加载描述。
        如果文件不存在或加载失败，返回插件名称作为后备。

        Returns:
            技能描述文本
        """
        try:
            import importlib.util

            # 获取插件模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件根目录
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"

                # 动态加载 information.py 模块
                if info_file.exists():
                    module_name = f"{plugin_dir.name}_information"
                    spec = importlib.util.spec_from_file_location(module_name, info_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)

                        # 查找实现 IPluginInfo 接口的类
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
            self._logger.warning(get_name(), f'Failed to load description from information.py: {e}')

        # 加载失败时返回插件名称作为后备
        return self.plugin_name
    
    @property
    def skill_tooltip(self) -> str:
        """
        获取技能按钮的悬浮提示文本

        提示文本由插件名称和描述组成，用换行符分隔。

        Returns:
            格式化的提示文本，格式为"名称\n描述"
        """
        return f"{self.plugin_name}\n{self.skill_description}"

    @property
    def plugin_id(self) -> Optional[str]:
        """
        获取插件唯一标识符

        Returns:
            UUID 格式的插件唯一标识，尚未加载时返回 None
        """
        return self._plugin_id

    def on_plugin_loaded(self) -> None:
        """
        插件加载完成回调钩子

        在插件被框架加载且唯一标识符（plugin_id）已设置后调用。
        子类可重写此方法执行初始化逻辑，例如：
        - 注册定时任务工厂
        - 初始化后台服务
        - 订阅其他插件的数据

        注意：此时插件的用户界面尚未创建，禁止在此方法中实例化 QWidget。
        """
        pass

    @property
    def plugin_info(self) -> Optional['IPluginInfo']:
        """
        获取插件信息对象

        动态从插件目录下的 information.py 文件中加载并实例化插件信息类。
        如果文件不存在或加载失败，返回 None。

        Returns:
            IPluginInfo 实例，未定义时返回 None
        """
        try:
            import importlib.util

            # 获取插件模块路径
            plugin_module = sys.modules.get(self.__class__.__module__)
            if plugin_module and hasattr(plugin_module, '__file__'):
                # 获取插件根目录
                plugin_dir = Path(plugin_module.__file__).parent
                info_file = plugin_dir / "information.py"

                # 动态加载 information.py 模块
                if info_file.exists():
                    module_name = f"{plugin_dir.name}_information"
                    spec = importlib.util.spec_from_file_location(module_name, info_file)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[module_name] = module
                        spec.loader.exec_module(module)

                        # 查找实现 IPluginInfo 接口的类
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
            self._logger.warning(get_name(), f'Failed to load plugin info from information.py: {e}')

        return None
