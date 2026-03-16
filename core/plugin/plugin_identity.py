"""
插件标识符管理模块
负责生成、保存和加载插件的 UUID
"""

import uuid
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

from utils.logging_tools import LoggerManager, get_name


class PluginIdentity:
    """
    插件标识符管理类
    负责生成、保存和加载插件的 UUID
    """
    
    def __init__(self, plugin_dir: Path):
        """
        初始化插件标识符管理器
        
        Args:
            plugin_dir: 插件目录路径
        """
        self.plugin_dir = plugin_dir
        self.info_file = plugin_dir / ".plugin_info.json"
        self._plugin_id: Optional[str] = None
        self._registered_at: Optional[datetime] = None
        self._logger = LoggerManager()
    
    def load_or_create_id(self) -> str:
        """
        加载或创建插件 UUID
        
        如果插件目录中没有 UUID 文件，则生成新的 UUID 并保存
        如果存在，则读取已有的 UUID
        
        Returns:
            插件的 UUID 字符串
        """
        if self.info_file.exists():
            # 加载已有的 UUID
            self._load_from_file()
            if self._plugin_id:
                return self._plugin_id
        
        # 生成新的 UUID
        self._plugin_id = str(uuid.uuid4())
        self._registered_at = datetime.now()
        self._save_to_file()
        
        return self._plugin_id
    
    def _load_from_file(self):
        """从文件加载插件信息"""
        try:
            with open(self.info_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._plugin_id = data.get("plugin_id")
                registered_at = data.get("registered_at")
                if registered_at:
                    self._registered_at = datetime.fromisoformat(registered_at)
        except (json.JSONDecodeError, ValueError, IOError) as e:
            self._logger.warning(get_name(), f'Failed to load plugin info from {self.info_file}: {e}')
            self._plugin_id = None
            self._registered_at = None
    
    def _save_to_file(self):
        """保存插件信息到文件"""
        try:
            data = {
                "plugin_id": self._plugin_id,
                "registered_at": self._registered_at.isoformat() if self._registered_at else None
            }
            with open(self.info_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self._logger.error(get_name(), f'Failed to save plugin info to {self.info_file}: {e}')
    
    @property
    def plugin_id(self) -> Optional[str]:
        """
        获取插件 UUID
        
        Returns:
            UUID 字符串，如果未加载或生成则返回 None
        """
        return self._plugin_id
    
    @property
    def registered_at(self) -> Optional[datetime]:
        """
        获取插件注册时间
        
        Returns:
            注册时间，如果未加载则返回 None
        """
        return self._registered_at
    
    def regenerate_id(self) -> str:
        """
        重新生成插件 UUID（慎用）
        
        Returns:
            新生成的 UUID 字符串
        """
        self._plugin_id = str(uuid.uuid4())
        self._registered_at = datetime.now()
        self._save_to_file()
        return self._plugin_id