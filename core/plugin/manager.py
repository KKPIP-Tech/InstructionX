
import os
import sys
import importlib
import importlib.util
from pathlib import Path
from typing import List, Dict, Optional, Any
from abc import ABC, abstractmethod

from .plugin_interface import IPlugin
from .config_manager import PluginConfigManager
from .plugin_identity import PluginIdentity


class PluginManager:
    """
    插件管理器
    负责加载、管理和提供插件
    """
    
    def __init__(self) -> None:
        self._official_plugins: List[IPlugin] = []
        self._thirdparty_plugins: List[IPlugin] = []
        self._plugin_registry: Dict[str, IPlugin] = {}  # plugin_id -> plugin
        self._plugin_name_to_id: Dict[str, str] = {}    # plugin_name -> plugin_id
        
        # 插件目录配置
        self.official_plugin_dir = Path(__file__).parent.parent.parent / "plugin"
        self.thirdparty_plugin_dir = Path(__file__).parent.parent.parent / "custom_plugin"
        
        # 配置管理器
        self.config_manager = PluginConfigManager()
    
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
                print(f"Warning: No entrance.py found in {plugin_dir}")
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
                print(f"Warning: Could not load spec for {entrance_file}")
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
                print(f"Warning: No IPlugin subclass found in {entrance_file}")
                return None
            
            # 实例化插件
            plugin_instance = plugin_class()
            
            # 生成或加载 UUID
            identity = PluginIdentity(plugin_dir)
            plugin_id = identity.load_or_create_id()
            plugin_instance._plugin_id = plugin_id
            
            # 存储映射关系
            plugin_instance._plugin_name = plugin_instance.plugin_name
            self._plugin_registry[plugin_id] = plugin_instance
            self._plugin_name_to_id[plugin_instance.plugin_name] = plugin_id
            
            return plugin_instance
            
        except Exception as e:
            print(f"Error loading plugin from {plugin_dir}: {e}")
            import traceback
            traceback.print_exc()
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
