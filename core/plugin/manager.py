
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
    """插件 API 信息"""
    
    def __init__(self, plugin_id: str, plugin_name: str, plugin_type: str):
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type
        self.api_methods: Dict[str, Callable] = {}
        self.api_descriptions: Dict[str, Dict[str, Any]] = {}


class PluginManager:
    """
    插件管理器
    负责加载、管理和提供插件
    同时提供插件 API 注册和调用功能
    
    单例模式：整个应用程序只有一个 PluginManager 实例
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        """单例模式：确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self) -> None:
        """初始化（只执行一次）"""
        if PluginManager._initialized:
            return
        
        PluginManager._initialized = True
        self._official_plugins: List[IPlugin] = []
        self._thirdparty_plugins: List[IPlugin] = []
        self._plugin_registry: Dict[str, IPlugin] = {}  # plugin_id -> plugin
        self._plugin_name_to_id: Dict[str, str] = {}    # plugin_name -> plugin_id
        
        # API 注册表
        self._api_registry: Dict[str, PluginAPI] = {}  # plugin_id -> PluginAPI
        
        # 插件目录配置
        self.official_plugin_dir = Path(__file__).parent.parent.parent / "plugin"
        self.thirdparty_plugin_dir = Path(__file__).parent.parent.parent / "custom_plugin"
        
        # 配置管理器
        self.config_manager = PluginConfigManager()

        # 日志管理器
        self._logger = LoggerManager()
    
    def load_plugins(self):
        """加载所有插件（官方和第三方）"""
        self.load_official_plugins()
        self.load_thirdparty_plugins()
    
    def load_official_plugins(self) -> List[IPlugin]:
        """
        加载官方插件
        
        Returns:
            官方插件列表
        """
        self._official_plugins.clear()
        
        if not self.official_plugin_dir.exists():
            self.official_plugin_dir.mkdir(parents=True, exist_ok=True)
            return self._official_plugins
        
        # 扫描官方插件目录
        for plugin_path in self.official_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._official_plugins.append(plugin)
        
        return self._official_plugins
    
    def load_thirdparty_plugins(self) -> List[IPlugin]:
        """
        加载第三方插件
        
        Returns:
            第三方插件列表
        """
        self._thirdparty_plugins.clear()
        
        if not self.thirdparty_plugin_dir.exists():
            self.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
            return self._thirdparty_plugins
        
        # 扫描第三方插件目录
        for plugin_path in self.thirdparty_plugin_dir.iterdir():
            if plugin_path.is_dir() and not plugin_path.name.startswith('_'):
                plugin = self._load_plugin_from_directory(plugin_path)
                if plugin:
                    self._thirdparty_plugins.append(plugin)
        
        return self._thirdparty_plugins
    
    def _load_plugin_from_directory(self, plugin_dir: Path) -> Optional[IPlugin]:
        """
        从目录加载插件
        
        Args:
            plugin_dir: 插件目录路径
            
        Returns:
            插件实例，如果加载失败则返回 None
        """
        try:
            # 查找插件的主文件（必须是 entrance.py）
            entrance_file = plugin_dir / "entrance.py"
            
            if not entrance_file.exists():
                self._logger.warning(get_name(), f'No entrance.py found in {plugin_dir}')
                return None
            
            # 确保插件目录有 __init__.py 文件，使其成为包
            init_file = plugin_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("")
            
            # 将插件目录添加到 sys.path 临时路径中
            parent_dir = str(plugin_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            # 动态导入模块（作为包的子模块）
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
            
            # 查找插件类
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
            
            # 生成或加载 UUID
            identity = PluginIdentity(plugin_dir)
            plugin_id = identity.load_or_create_id()
            plugin_instance._plugin_id = plugin_id

            # 调用插件加载完成回调
            plugin_instance.on_plugin_loaded()

            # 存储映射关系
            plugin_instance._plugin_name = plugin_instance.plugin_name
            self._plugin_registry[plugin_id] = plugin_instance
            self._plugin_name_to_id[plugin_instance.plugin_name] = plugin_id
            
            # 尝试自动注册 API
            self._auto_register_plugin_api(plugin_dir, plugin_id)
            
            return plugin_instance
            
        except Exception as e:
            self._logger.error(get_name(), f'Error loading plugin from {plugin_dir}: {e}')
            return None
    
    def get_official_plugins(self) -> List[IPlugin]:
        """获取所有官方插件"""
        return self._official_plugins.copy()
    
    def get_thirdparty_plugins(self) -> List[IPlugin]:
        """获取所有第三方插件"""
        return self._thirdparty_plugins.copy()
    
    def get_all_plugins(self) -> List[IPlugin]:
        """获取所有插件（官方 + 第三方）"""
        return self._official_plugins + self._thirdparty_plugins
    
    def get_plugin_by_name(self, name: str) -> Optional[IPlugin]:
        """
        根据名称获取插件
        
        Args:
            name: 插件名称
            
        Returns:
            插件实例，如果不存在则返回 None
        """
        return self._plugin_registry.get(name)
    
    def reload_plugins(self):
        """重新加载所有插件"""
        self._official_plugins.clear()
        self._thirdparty_plugins.clear()
        self._plugin_registry.clear()
        self._plugin_name_to_id.clear()
        self.load_plugins()
    
    def get_plugin_by_id(self, plugin_id: str) -> Optional[IPlugin]:
        """
        根据 UUID 获取插件
        
        Args:
            plugin_id: 插件的 UUID
            
        Returns:
            插件实例，如果不存在则返回 None
        """
        return self._plugin_registry.get(plugin_id)
    
    def get_plugin_id_by_name(self, plugin_name: str) -> Optional[str]:
        """
        根据插件名称获取 UUID

        Args:
            plugin_name: 插件名称

        Returns:
            UUID 字符串，如果不存在则返回 None
        """
        return self._plugin_name_to_id.get(plugin_name)
    
    def register_plugin(self, plugin: IPlugin, is_official: bool = False):
        """
        手动注册插件
        
        Args:
            plugin: 插件实例
            is_official: 是否为官方插件
        """
        self._plugin_registry[plugin.plugin_name] = plugin
        if is_official:
            self._official_plugins.append(plugin)
        else:
            self._thirdparty_plugins.append(plugin)
    
    def unregister_plugin(self, plugin_name: str):
        """
        注销插件
        
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
        """应用自定义插件顺序（从配置文件加载）"""
        config = self.config_manager.load_plugin_order()
        
        # 对官方插件排序（使用 UUID）
        if config["official_plugins"]:
            ordered_plugins = []
            for plugin_id in config["official_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._official_plugins:
                    ordered_plugins.append(plugin)
            
            # 添加未在配置中的插件（新插件）
            for plugin in self._official_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)
            
            self._official_plugins = ordered_plugins
        
        # 对第三方插件排序（使用 UUID）
        if config["thirdparty_plugins"]:
            ordered_plugins = []
            for plugin_id in config["thirdparty_plugins"]:
                plugin = self._plugin_registry.get(plugin_id)
                if plugin and plugin in self._thirdparty_plugins:
                    ordered_plugins.append(plugin)
            
            # 添加未在配置中的插件（新插件）
            for plugin in self._thirdparty_plugins:
                if plugin not in ordered_plugins:
                    ordered_plugins.append(plugin)
            
            self._thirdparty_plugins = ordered_plugins
    
    def save_plugin_order(self, official_plugin_ids: List[str], thirdparty_plugin_ids: List[str]) -> bool:
        """
        保存插件顺序到配置文件
        
        Args:
            official_plugin_ids: 官方插件 UUID 列表
            thirdparty_plugin_ids: 第三方插件 UUID 列表
            
        Returns:
            保存是否成功
        """
        return self.config_manager.save_plugin_order(official_plugin_ids, thirdparty_plugin_ids)
    
    def get_official_plugin_ids(self) -> List[str]:
        """获取所有官方插件 UUID（按当前顺序）"""
        return [plugin.plugin_id for plugin in self._official_plugins if plugin.plugin_id]
    
    def get_thirdparty_plugin_ids(self) -> List[str]:
        """获取所有第三方插件 UUID（按当前顺序）"""
        return [plugin.plugin_id for plugin in self._thirdparty_plugins if plugin.plugin_id]
    
    # ==================== API 管理功能 ====================
    
    def _auto_register_plugin_api(self, plugin_dir: Path, plugin_id: str) -> None:
        """
        自动注册插件的 API 方法
        
        Args:
            plugin_dir: 插件目录路径
            plugin_id: 插件 ID
        """
        try:
            # 尝试导入 information.py
            info_file = plugin_dir / "information.py"
            if not info_file.exists():
                                return

            # 尝试导入 service.py
            service_file = plugin_dir / "service.py"
            if not service_file.exists():
                                return

            
            # 动态导入模块
            module_name = plugin_dir.name
            
            # 添加父目录到 sys.path（如果需要）
            parent_dir = str(plugin_dir.parent)
            if parent_dir not in sys.path:
                sys.path.insert(0, parent_dir)
            
            try:
                # 先清理可能已缓存的模块
                if f"{module_name}.information" in sys.modules:
                    del sys.modules[f"{module_name}.information"]
                if f"{module_name}.service" in sys.modules:
                    del sys.modules[f"{module_name}.service"]
                
                info_module = importlib.import_module(f"{module_name}.information")
                service_module = importlib.import_module(f"{module_name}.service")
            except Exception as e:
                self._logger.warning(get_name(), f'Skipping API registration ({plugin_dir.name}): {e}')
                return
            
            # 获取 PluginInfo 实例
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
            
            # 创建 PluginInfo 实例
            plugin_info = plugin_info_class()
            
            # 获取 service_api 定义
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
            
            # 创建 Service 实例
            service_instance = service_class()
            
            # 注册 API
            self.register_plugin_api(plugin_id, service_instance, api_descriptions)
            
        except Exception as e:
            self._logger.error(get_name(), f'API auto registration failed: {e}')
    
    def register_plugin_api(self, 
                          plugin_id: str,
                          service_instance: Any,
                          api_descriptions: Dict[str, Dict[str, Any]]) -> None:
        """
        注册插件的 API 方法
        
        Args:
            plugin_id: 插件实例 ID
            service_instance: Service 类实例
            api_descriptions: API 描述字典（来自 information.py 的 service_api）
        """
        # 获取插件信息
        plugin = self.get_plugin_by_id(plugin_id)
        if not plugin:
            raise ValueError(f"插件 {plugin_id} 不存在")
        
        # 创建 PluginAPI 对象
        plugin_api = PluginAPI(
            plugin_id=plugin_id,
            plugin_name=plugin.plugin_name,
            plugin_type=plugin.__class__.__name__
        )
        
        # 从 service_instance 获取所有公开方法
        for method_name, desc in api_descriptions.items():
            # 获取方法
            if hasattr(service_instance, method_name):
                method = getattr(service_instance, method_name)
                if callable(method):
                    plugin_api.api_methods[method_name] = method
                    plugin_api.api_descriptions[method_name] = desc
        
        # 存储到注册表
        self._api_registry[plugin_id] = plugin_api
            
    def unregister_plugin_api(self, plugin_id: str) -> None:
        """
        注销插件的 API 方法
        
        Args:
            plugin_id: 插件实例 ID
        """
        if plugin_id in self._api_registry:
            del self._api_registry[plugin_id]
                
    def get_plugin_api(self, plugin_id: str) -> Optional[Dict[str, Any]]:
        """
        获取插件的 API 信息
        
        Args:
            plugin_id: 插件实例 ID
            
        Returns:
            插件 API 信息字典，如果不存在则返回 None
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
        获取所有已注册的 API
        
        Returns:
            所有 API 信息字典 {plugin_id: {plugin_id, plugin_name, plugin_type, methods, descriptions}}
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
        
        Args:
            caller_id: 调用者插件 ID（用于日志）
            plugin_id: 目标插件 ID
            method_name: 方法名
            **kwargs: 方法参数
            
        Returns:
            方法返回值
            
        Raises:
            ValueError: 插件或方法不存在时抛出
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
            # 调用方法
            return method(**kwargs)
        except Exception as e:
            raise RuntimeError(f"调用插件 {plugin_id} 的方法 {method_name} 失败: {e}")
    
    def get_api_description(self,
                         plugin_id: str,
                         method_name: Optional[str] = None) -> Dict[str, Any]:
        """
        获取 API 描述（用于 MCP/function tools）
        
        Args:
            plugin_id: 插件 ID
            method_name: 可选，方法名。如果为 None，则返回所有方法的描述
            
        Returns:
            API 描述字典
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
            # 返回特定方法的描述
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
        获取所有可用的 function tools（用于 MCP）
        
        Returns:
            function tools 列表，格式符合 MCP/OpenAI function calling 规范
        """
        tools = []
        
        for plugin_id, plugin_api in self._api_registry.items():
            for method_name, desc in plugin_api.api_descriptions.items():
                # 提取参数
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
