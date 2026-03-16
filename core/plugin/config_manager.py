"""
插件配置管理器
负责管理插件顺序等配置
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from utils.logging_tools import LoggerManager, get_name


class PluginConfigManager:
    """插件配置管理器"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录，默认为项目根目录下的 config/
        """
        if config_dir is None:
            # 默认配置目录
            config_dir = Path(__file__).parent.parent.parent / "config"
        
        self.config_dir = config_dir
        self.config_file = self.config_dir / "plugin_order.json"
        
        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 日志管理器
        self._logger = LoggerManager()
    
    def load_plugin_order(self) -> Dict[str, List[str]]:
        """
        加载插件顺序配置
        
        Returns:
            包含 'official_plugins' 和 'thirdparty_plugins' 的字典
            如果配置文件不存在，返回空字典
        """
        if not self.config_file.exists():
            return {
                "official_plugins": [],
                "thirdparty_plugins": []
            }
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 确保返回的格式正确
            if not isinstance(data, dict):
                return {
                    "official_plugins": [],
                    "thirdparty_plugins": []
                }
            
            # 确保 'official_plugins' 和 'thirdparty_plugins' 键存在
            if "official_plugins" not in data:
                data["official_plugins"] = []
            if "thirdparty_plugins" not in data:
                data["thirdparty_plugins"] = []
            
            return data
        
        except Exception as e:
            self._logger.error(get_name(), f'Error loading plugin order config: {e}')
            return {
                "official_plugins": [],
                "thirdparty_plugins": []
            }
    
    def save_plugin_order(self, official_plugins: List[str], thirdparty_plugins: List[str]) -> bool:
        """
        保存插件顺序配置
        
        Args:
            official_plugins: 官方插件名称列表
            thirdparty_plugins: 第三方插件名称列表
            
        Returns:
            保存是否成功
        """
        try:
            data = {
                "official_plugins": official_plugins,
                "thirdparty_plugins": thirdparty_plugins
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            return True
        
        except Exception as e:
            self._logger.error(get_name(), f'Error saving plugin order config: {e}')
            return False
    
    def update_official_order(self, plugin_names: List[str]) -> bool:
        """
        更新官方插件顺序
        
        Args:
            plugin_names: 官方插件名称列表
            
        Returns:
            更新是否成功
        """
        config = self.load_plugin_order()
        config["official_plugins"] = plugin_names
        return self.save_plugin_order(config["official_plugins"], config["thirdparty_plugins"])
    
    def update_thirdparty_order(self, plugin_names: List[str]) -> bool:
        """
        更新第三方插件顺序
        
        Args:
            plugin_names: 第三方插件名称列表
            
        Returns:
            更新是否成功
        """
        config = self.load_plugin_order()
        config["thirdparty_plugins"] = plugin_names
        return self.save_plugin_order(config["official_plugins"], config["thirdparty_plugins"])