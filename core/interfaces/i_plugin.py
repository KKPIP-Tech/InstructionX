"""
Plugin 插件抽象基类接口

定义所有插件必须实现的接口规范，包括：
- 插件名称属性
- 控件创建方法
- 缓存机制
- 技能图标和描述获取
- 生命周期回调
- LLM 工具注册
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QIcon

if TYPE_CHECKING:
    from .i_plugin_info import IPluginInfo
    from .plugin_services import PluginServices


class IPlugin(ABC):
    """
    插件抽象基类

    所有插件必须继承此类并实现抽象方法。该类提供：
    - 插件唯一标识和名称管理
    - 控件缓存机制，避免重复创建
    - 技能图标和描述的动态加载（带缓存）
    - 插件生命周期回调钩子
    """

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """获取插件显示名称"""
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

    @property
    def skill_icon(self) -> Optional[QIcon]:
        """获取技能面板按钮图标"""
        return None

    @property
    def skill_description(self) -> str:
        """获取技能面板按钮的简短描述文本"""
        return self.plugin_name

    @property
    def skill_tooltip(self) -> str:
        """获取技能按钮的悬浮提示文本"""
        return f"{self.plugin_name}\n{self.skill_description}"

    @property
    def plugin_id(self) -> Optional[str]:
        """获取插件唯一标识符"""
        return None

    def on_plugin_loaded(self, plugin_id: Optional[str] = None, **kwargs) -> None:
        """
        插件加载完成回调钩子

        在插件被框架加载且唯一标识符（plugin_id）已设置后调用。
        子类可重写此方法执行初始化逻辑。

        新版插件可通过 self._services 访问注入的服务容器，
        包括 self._services.llm_facade、self._services.data_provider 等。

        Args:
            plugin_id: 插件唯一标识符
            **kwargs: 预留参数（services 等通过实例属性 self._services 访问）
        """
        pass

    @property
    def plugin_info(self) -> Optional['IPluginInfo']:
        """获取插件信息对象"""
        return None

    @property
    def llm_tools(self) -> List[Dict[str, Any]]:
        """获取插件暴露的 LLM 工具列表

        返回符合 OpenAI function calling 规范的工具定义列表。
        插件可通过重写此属性来声明自己暴露的工具。
        """
        return []
