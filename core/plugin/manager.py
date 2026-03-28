
"""
插件管理器

提供插件的加载、注册、查询、排序和 API 调用功能。
采用单例模式确保全局只有一个管理器实例。
"""

import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from abc import ABC, abstractmethod

from .plugin_interface import IPlugin
from .config_manager import PluginConfigManager
from .plugin_identity import PluginIdentity

from utils.logging_tools import LoggerManager, get_name


class PluginAPI:
    """插件 API 信息容器"""

    def __init__(self, plugin_id: str, plugin_name: str, plugin_type: str):
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type
        self.api_methods: Dict[str, Callable] = {}
        self.api_descriptions: Dict[str, Dict[str, Any]] = {}


class PluginManager:
    """
    插件管理器（单例模式）

    核心功能：
    - 动态加载官方插件和第三方插件
    - 维护插件注册表和名称映射
    - 提供插件 API 注册和跨插件调用
    - 管理插件显示顺序配置

    单例访问方式：PluginManager()
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        """单例模式：确保全局只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化插件管理器（仅执行一次）"""
        if PluginManager._initialized:
            return

        PluginManager._initialized = True
        self._official_plugins: List[IPlugin] = []
        self._thirdparty_plugins: List[IPlugin] = []
        self._plugin_registry: Dict[str, IPlugin] = {}  # plugin_id -> plugin
        self._plugin_name_to_id: Dict[str, str] = {}    # plugin_name -> plugin_id

        # API 注册表：存储插件暴露的方法
        self._api_registry: Dict[str, PluginAPI] = {}

        # 插件目录路径
        self.official_plugin_dir = Path(__file__).parent.parent.parent / "plugin"
        self.thirdparty_plugin_dir = Path(__file__).parent.parent.parent / "custom_plugin"

        # 配置管理器
        self.config_manager = PluginConfigManager()

        # 日志管理器
        self._logger = LoggerManager()
    
    def load_plugins(self):
        """加载所有插件（包括官方插件和第三方插件）"""
        self.load_official_plugins()
        self.load_thirdparty_plugins()

    def load_official_plugins(self) -> List[IPlugin]:
        """
        扫描并加载 plugin 目录下的所有官方插件

        Returns:
            已加载的官方插件列表
        """
        self._official_plugins.clear()

        if not self.official_plugin_dir.exists():
            self.official_plugin_dir.mkdir(parents=True, exist_ok=True)
            return self._official_plugins

        # 遍历目录，加载每个子目录中的插件
        for plugin_path in self.official_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._official_plugins.append(plugin)

        return self._official_plugins

    def load_thirdparty_plugins(self) -> List[IPlugin]:
        """
        扫描并加载 custom_plugin 目录下的所有第三方插件

        Returns:
            已加载的第三方插件列表
        """
        self._thirdparty_plugins.clear()

        if not self.thirdparty_plugin_dir.exists():
            self.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
            return self._thirdparty_plugins

        # 遍历目录，加载每个子目录中的插件
        for plugin_path in self.thirdparty_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._thirdparty_plugins.append(plugin)

        return self._thirdparty_plugins

    def _load_plugin_from_directory(self, plugin_dir: Path) -> Optional[IPlugin]:
        """
        从指定目录动态加载插件

        加载流程：
        1. 检查并创建 __init__.py 使目录成为 Python 包
        2. 动态导入 entrance.py 模块
        3. 查找并实例化继承自 IPlugin 的类
        4. 生成或加载插件唯一标识符
        5. 调用插件生命周期回调

        Args:
            plugin_dir: 插件目录路径

        Returns:
            插件实例，加载失败时返回 None
        """
        try:
            # 检查入口文件是否存在
            entrance_file = plugin_dir / "entrance.py"

            if not entrance_file.exists():
                self._logger.warning(get_name(), f'No entrance.py found in {plugin_dir}')
                return None

            # 确保插件目录有 __init__.py 文件
            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")

            # 将插件目录添加到 Python 模块搜索路径
            parent_dir = str(plugin_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            # 动态导入 entrance.py 模块
            module_name = f"{plugin_dir.name}.entrance"
            spec = importlib.util.spec_from_file_location(module_name, entrance_file)
            if spec is None or spec.loader is None:
                self._logger.warning(get_name(), f'Could not load spec for {entrance_file}')
                return None

            # 设置包上下文
            module = importlib.util.module_from_spec(spec)
            module.__package__ = plugin_dir.name
            module.__path__ = [str(plugin_dir)]

            sys.modules[module_name] = module
            sys.modules[plugin_dir.name] = importlib.import_module(plugin_dir.name)

            spec.loader.exec_module(module)

            # 在模块中查找 IPlugin 的子类
            plugin_class = None
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, IPlugin) and
                    attr is not IPlugin):
                    plugin_class = attr
                    break

            if plugin_class is None:
                self._logger.warning(get_name(), f'No IPlugin subclass found in {entrance_file}')
                return None

            # 实例化插件
            plugin_instance = plugin_class()

            # 生成或加载唯一标识符
            identity = PluginIdentity(plugin_dir)
            plugin_id = identity.load_or_create_id()
            plugin_instance._plugin_id = plugin_id

            # 调用插件加载完成回调
            plugin_instance.on_plugin_loaded()

            # 维护注册表映射
            plugin_instance._plugin_name = plugin_instance.plugin_name
            self._plugin_registry[plugin_id] = plugin_instance
            self._plugin_name_to_id[plugin_instance.plugin_name] = plugin_id

            # 尝试自动注册插件 API
            self._auto_register_plugin_api(plugin_dir, plugin_id)

            return plugin_instance

        except Exception as e:
            self._logger.error(get_name(), f'Error loading plugin from {plugin_dir}: {e}')
            return None
    
    def get_official_plugins(self) -> List[IPlugin]:
        """获取所有官方插件实例列表"""
        return self._official_plugins.copy()

    def get_thirdparty_plugins(self) -> List[IPlugin]:
        """获取所有第三方插件实例列表"""
        return self._thirdparty_plugins.copy()

    def get_all_plugins(self) -> List[IPlugin]:
        """获取所有已加载的插件（官方 + 第三方）"""
        return self._official_plugins + self._thirdparty_plugins

    def get_plugin_by_name(self, name: str) -> Optional[IPlugin]:
        """
        通过插件名称查询插件实例

        Args:
            name: 插件名称

        Returns:
            插件实例，未找到时返回 None
        """
        return self._plugin_registry.get(name)

    def reload_plugins(self):
        """重新加载所有插件（清空注册表后重新扫描目录）"""
        self._official_plugins.clear()
        self._thirdparty_plugins.clear()
        self._plugin_registry.clear()
        self._plugin_name_to_id.clear()
        self.load_plugins()

    def get_plugin_by_id(self, plugin_id: str) -> Optional[IPlugin]:
        """
        通过唯一标识符查询插件实例

        Args:
            plugin_id: 插件 UUID

        Returns:
            插件实例，未找到时返回 None
        """
        return self._plugin_registry.get(plugin_id)

    def get_plugin_id_by_name(self, plugin_name: str) -> Optional[str]:
        """
        通过插件名称查询其唯一标识符

        Args:
            plugin_name: 插件名称

        Returns:
            UUID 字符串，未找到时返回 None
        """
        return self._plugin_name_to_id.get(plugin_name)

    def register_plugin(self, plugin: IPlugin, is_official: bool = False):
        """
        手动注册插件到管理器

        Args:
            plugin: 插件实例
            is_official: 是否属于官方插件
        """
        self._plugin_registry[plugin.plugin_name] = plugin
        if is_official:
            self._official_plugins.append(plugin)
        else:
            self._thirdparty_plugins.append(plugin)

    def unregister_plugin(self, plugin_name: str):
        """
        从管理器中移除插件

        Args:
            plugin_name: 插件名称
        """
        plugin = self._plugin_registry.pop(plugin_name, None)
        if plugin:
            if plugin in self._official_plugins:
                self._official_plugins.remove(plugin)
            if plugin in self._thirdparty_plugins:
                self._thirdparty_plugins.remove(plugin)

    def apply_custom_order(self):
        """从配置文件加载并应用用户自定义的插件显示顺序"""
        config = self.config_manager.load_plugin_order()

        # 对官方插件按照配置文件的 UUID 顺序排序
        if config["official_plugins"]:
            ordered_plugins = []
            for plugin_id in config["official_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._official_plugins:
                    ordered_plugins.append(plugin)

            # 追加未在配置中的新增插件
            for plugin in self._official_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)

            self._official_plugins = ordered_plugins

        # 对第三方插件按照配置文件的 UUID 顺序排序
        if config["thirdparty_plugins"]:
            ordered_plugins = []
            for plugin_id in config["thirdparty_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._thirdparty_plugins:
                    ordered_plugins.append(plugin)

            # 追加未在配置中的新增插件
            for plugin in self._thirdparty_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)

            self._thirdparty_plugins = ordered_plugins

    def save_plugin_order(self, official_plugin_ids: List[str], thirdparty_plugin_ids: List[str]) -> bool:
        """
        将插件显示顺序持久化到配置文件

        Args:
            official_plugin_ids: 官方插件 UUID 列表
            thirdparty_plugin_ids: 第三方插件 UUID 列表

        Returns:
            保存操作是否成功
        """
        return self.config_manager.save_plugin_order(official_plugin_ids, thirdparty_plugin_ids)

    def get_official_plugin_ids(self) -> List[str]:
        """获取当前顺序下所有官方插件的 UUID 列表"""
        return [plugin.plugin_id for plugin in self._official_plugins if plugin.plugin_id]

    def get_thirdparty_plugin_ids(self) -> List[str]:
        """获取当前顺序下所有第三方插件的 UUID 列表"""
        return [plugin.plugin_id for plugin in self._thirdparty_plugins if plugin.plugin_id]

    # ==================== API 管理功能 ====================

    def _auto_register_plugin_api(self, plugin_dir: Path, plugin_id: str) -> None:
        """
        自动扫描并注册插件的公开方法作为 API

        扫描插件目录下的 information.py 和 service.py 文件，
        从 information.py 获取 API 方法描述，从 service.py 获取实际方法引用。

        Args:
            plugin_dir: 插件目录路径
            plugin_id: 插件唯一标识符
        """
        try:
            # 检查必要文件是否存在
            info_file = plugin_dir / "information.py"
            if not info_file.exists():
                return

            service_file = plugin_dir / "service.py"
            if not service_file.exists():
                return


            # 动态导入模块
            module_name = plugin_dir.name

            # 确保父目录在搜索路径中
            parent_dir = str(plugin_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)

            try:
                # 清理可能缓存的模块以获取最新定义
                if f"{module_name}.information" in sys.modules:
                    del sys.modules[f"{module_name}.information"]
                if f"{module_name}.service" in sys.modules:
                    del sys.modules[f"{module_name}.service"]

                info_module = importlib.import_module(f"{module_name}.information")
                service_module = importlib.import_module(f"{module_name}.service")
            except Exception as e:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): {e}')
                return

            # 获取 PluginInfo 类
            plugin_info_class = None
            from .plugin_info_interface import IPluginInfo
            for attr_name in dir(info_module):
                attr = getattr(info_module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, IPluginInfo) and
                    attr is not IPluginInfo):
                    plugin_info_class = attr
                    break

            if not plugin_info_class:
                return

            # 实例化 PluginInfo
            plugin_info = plugin_info_class()

            # 获取 service_api 方法描述
            api_descriptions = plugin_info.service_api
            if not api_descriptions:
                return

            # 获取 Service 类
            service_class = None
            for attr_name in dir(service_module):
                attr = getattr(service_module, attr_name)
                if isinstance(attr, type) and attr.__name__ == 'Service':
                    service_class = attr
                    break

            if not service_class:
                return

            # 实例化 Service
            service_instance = service_class()

            # 注册 API 方法
            self.register_plugin_api(plugin_id, service_instance, api_descriptions)

        except Exception as e:
            self._logger.error(get_name(), f'API auto registration failed: {e}')

    def register_plugin_api(self,
                          plugin_id: str,
                          service_instance: Any,
                          api_descriptions: Dict[str, Dict[str, Any]]) -> None:
        """
        注册插件的公开方法到 API 注册表

        Args:
            plugin_id: 插件唯一标识符
            service_instance: Service 类实例
            api_descriptions: API 方法描述字典（来自 information.py 的 service_api）
        """
        # 获取插件信息
        plugin = self.get_plugin_by_id(plugin_id)
        if not plugin:
            raise ValueError(f"插件 {plugin_id} 不存在")

        # 创建 API 容器
        plugin_api = PluginAPI(
            plugin_id=plugin_id,
            plugin_name=plugin.plugin_name,
            plugin_type=plugin.__class__.__name__
        )

        # 遍历方法描述，绑定实际方法到 API 容器
        for method_name, desc in api_descriptions.items():
            if hasattr(service_instance, method_name):
                method = getattr(service_instance, method_name)
                if callable(method):
                    plugin_api.api_methods[method_name] = method
                    plugin_api.api_descriptions[method_name] = desc

        # 存入注册表
        self._api_registry[plugin_id] = plugin_api
            
    def unregister_plugin_api(self, plugin_id: str) -> None:
        """
        移除插件的 API 注册

        Args:
            plugin_id: 插件唯一标识符
        """
        if plugin_id in self._api_registry:
            del self._api_registry[plugin_id]

    def get_plugin_api(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取指定插件的 API 信息

        Args:
            plugin_id: 插件唯一标识符

        Returns:
            包含插件 ID、名称、类型和方法的字典，不存在时返回 None
        """
        plugin_api = self._api_registry.get(plugin_id)
        if not plugin_api:
            return None

        return {
            "plugin_id": plugin_api.plugin_id,
            "plugin_name": plugin_api.plugin_name,
            "plugin_type": plugin_api.plugin_type,
            "methods": list(plugin_api.api_methods.keys()),
            "descriptions": plugin_api.api_descriptions
        }

    def get_all_apis(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有已注册的插件 API

        Returns:
            以插件 ID 为键的 API 信息字典
        """
        result = {}
        for plugin_id, plugin_api in self._api_registry.items():
            result[plugin_id] = {
                "plugin_id": plugin_api.plugin_id,
                "plugin_name": plugin_api.plugin_name,
                "plugin_type": plugin_api.plugin_type,
                "methods": list(plugin_api.api_methods.keys()),
                "descriptions": plugin_api.api_descriptions
            }
        return result

    def call_plugin_method(self,
                         caller_id: str,
                         plugin_id: str,
                         method_name: str,
                         **kwargs) -> Any:
        """
        跨插件调用方法

        允许一个插件通过唯一标识符调用另一个插件的公开方法。
        用于实现插件间的功能协作。

        Args:
            caller_id: 调用方插件的唯一标识符（用于日志记录）
            plugin_id: 目标插件的唯一标识符
            method_name: 要调用的方法名
            **kwargs: 传递给目标方法的参数

        Returns:
            方法的返回值

        Raises:
            ValueError: 目标插件或方法不存在时抛出
            RuntimeError: 方法执行失败时抛出
        """
        plugin_api = self._api_registry.get(plugin_id)

        if plugin_api is None:
            raise ValueError(f"插件 {plugin_id} 未注册 API")

        if method_name not in plugin_api.api_methods:
            available = ", ".join(plugin_api.api_methods.keys())
            raise ValueError(f"插件 {plugin_id} 没有方法 '{method_name}'。可用方法: {available}")

        method = plugin_api.api_methods[method_name]

        try:
            # 执行方法调用
            return method(**kwargs)
        except Exception as e:
            raise RuntimeError(f"调用插件 {plugin_id} 的方法 {method_name} 失败: {e}")

    def get_api_description(self,
                         plugin_id: str,
                         method_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 API 的结构化描述（适用于 MCP 或函数工具）

        Args:
            plugin_id: 插件唯一标识符
            method_name: 可选，指定方法名。None 时返回所有方法的描述

        Returns:
            API 描述字典，包含方法名、参数、返回值等信息
        """
        plugin_api = self._api_registry.get(plugin_id)

        if plugin_api is None:
            return {}

        if method_name is None:
            # 返回所有方法的描述
            return {
                name: {
                    "plugin_id": plugin_id,
                    "plugin_name": plugin_api.plugin_name,
                    "plugin_type": plugin_api.plugin_type,
                    "description": desc.get("description", ""),
                    "parameters": desc.get("parameters", {}),
                    "returns": desc.get("returns", {})
                }
                for name, desc in plugin_api.api_descriptions.items()
            }
        else:
            # 返回指定方法的描述
            desc = plugin_api.api_descriptions.get(method_name)
            if desc is None:
                return {}

            return {
                "plugin_id": plugin_id,
                "plugin_name": plugin_api.plugin_name,
                "plugin_type": plugin_api.plugin_type,
                "name": method_name,
                "description": desc.get("description", ""),
                "parameters": desc.get("parameters", {}),
                "returns": desc.get("returns", {})
            }

    def get_all_function_tools(self) -> List[Dict[str, Any]]:
        """
        获取所有可用的函数工具（适用于 MCP 集成）

        将所有插件 API 转换为符合 MCP/OpenAI 函数调用规范的格式。

        Returns:
            函数工具列表，每个元素包含类型、函数名、描述和参数定义
        """

        tools = []

        for plugin_id, plugin_api in self._api_registry.items():
            for method_name, desc in plugin_api.api_descriptions.items():
                # 提取必需参数
                parameters = desc.get("parameters", {})
                required_params = [
                    k for k, v in parameters.items()
                    if v.get("required", False)
                ]

                tool = {
                    "type": "function",
                    "function": {
                        "name": f"{plugin_id}.{method_name}",
                        "description": f"[{plugin_api.plugin_name}] {desc.get('description', '')}",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                k: {
                                    "type": v.get("type", "string"),
                                    "description": v.get("description", "")
                                }
                                for k, v in parameters.items()
                            },
                            "required": required_params
                        }
                    }
                }
                tools.append(tool)

        return tools
