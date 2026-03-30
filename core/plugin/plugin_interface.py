"""
插件系统抽象基类

定义所有插件必须实现的接口规范，包括：
- 插件名称属性
- 控件创建方法
- 缓存机制
- 技能图标和描述获取
- 生命周期回调

注意：此文件已迁移至 core/interfaces/i_plugin.py。
此处保留作为向后兼容的导入路径，并扩展了带缓存的实现。
"""

import sys
import os
import importlib.util
from abc import ABC, abstractmethod
from typing import Optional, Tuple, TYPE_CHECKING
from pathlib import Path
from PySide6.QtWidgets import QWidget, QApplication, QStyle
from PySide6.QtGui import QIcon

if TYPE_CHECKING:
    from .plugin_info_interface import IPluginInfo

from utils.logging_tools import LoggerManager, get_name


class IPlugin(ABC):
    """
    插件抽象基类

    所有插件必须继承此类并实现抽象方法。该类提供：
    - 插件唯一标识和名称管理
    - 控件缓存机制，避免重复创建
    - 技能图标和描述的动态加载（带缓存）
    - 插件生命周期回调钩子
    """

    _logger = LoggerManager()

    def __init__(self):
        """初始化插件实例的内部状态"""
        self._plugin_id: Optional[str] = None
        self._plugin_name: Optional[str] = None
        self._cached_widget: Optional[QWidget] = None
        self._cached_parent: Optional[QWidget] = None
        self._info_cache: Optional[Tuple[float, 'IPluginInfo']] = None
        self._info_cache_path: Optional[str] = None

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

    def _load_plugin_info(self) -> Optional['IPluginInfo']:
        """
        加载并缓存插件信息

        使用文件 mtime 作为缓存失效依据，当文件被修改时自动重新加载。

        Returns:
            IPluginInfo 实例，加载失败返回 None
        """
        try:
            # 优先使用 _plugin_dir（PluginManager 加载时设置），否则从 sys.modules 查找
            plugin_dir = getattr(self, '_plugin_dir', None)
            if plugin_dir is None:
                plugin_module = sys.modules.get(self.__class__.__module__)
                if plugin_module and hasattr(plugin_module, '__file__') and plugin_module.__file__:
                    plugin_dir = Path(plugin_module.__file__).parent
                else:
                    return None

            info_file = plugin_dir / "information.py"
            if not info_file.exists():
                return None

            current_mtime = os.path.getmtime(info_file)

            # 缓存命中且文件未变化
            if (isinstance(self._info_cache, tuple) and
                self._info_cache_path == str(info_file) and
                self._info_cache[0] == current_mtime):
                return self._info_cache[1]

            # 重新加载
            module_name = f"{plugin_dir.name}_information"
            spec = importlib.util.spec_from_file_location(module_name, info_file)
            if not (spec and spec.loader):
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            from .plugin_info_interface import IPluginInfo
            plugin_info_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, IPluginInfo) and
                    attr is not IPluginInfo):
                    plugin_info_class = attr
                    break

            if not plugin_info_class:
                return None

            plugin_info = plugin_info_class()
            self._info_cache = (current_mtime, plugin_info)
            self._info_cache_path = str(info_file)
            return plugin_info

        except (ImportError, AttributeError, Exception):
            return None

    @property
    def skill_icon(self) -> Optional[QIcon]:
        """
        获取技能面板按钮图标

        从缓存的插件信息中加载图标配置。如果文件不存在或加载失败，
        返回系统默认图标。

        Returns:
            Qt 图标对象，加载失败时返回系统默认文件图标
        """
        plugin_info = self._load_plugin_info()
        if plugin_info is None:
            app = QApplication.instance()
            if app and hasattr(app, 'style'):
                return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            return None

        plugin_dir = getattr(self, '_plugin_dir', None)
        icon = plugin_info.skill_icon.load_icon(plugin_dir) if plugin_dir else None

        if icon is None or icon.isNull():
            app = QApplication.instance()
            if app and hasattr(app, 'style'):
                return app.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)
            return None
        return icon

    @property
    def skill_description(self) -> str:
        """
        获取技能面板按钮的简短描述文本

        从缓存的插件信息中加载描述。如果文件不存在或加载失败，
        返回插件名称作为后备。

        Returns:
            技能描述文本
        """
        plugin_info = self._load_plugin_info()
        if plugin_info:
            return plugin_info.skill_description
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

        从缓存中加载插件信息类实例。如果文件不存在或加载失败，返回 None。

        Returns:
            IPluginInfo 实例，未定义时返回 None
        """
        return self._load_plugin_info()
