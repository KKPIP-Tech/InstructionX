"""
插件标识符管理模块
负责生成、保存和加载插件的 UUID
"""

import uuid
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from utils.logging_tools import LoggerManager, get_name


class PluginIdentity:
    """
    插件标识符管理类
    负责生成、保存和加载插件的 UUID

    UUID 优先持久化在插件自身目录的 .plugin_info.json 中；
    当插件目录只读/写入失败时，回退到应用数据目录
    data/plugin_identity/{plugin_dir_name}.json，读取时按
    "插件目录 → 数据目录回退" 顺序查找，避免每次启动生成新 UUID。
    """
    
    def __init__(self, plugin_dir: Path):
        """
        初始化插件标识符管理器
        
        Args:
            plugin_dir: 插件目录路径
        """
        self.plugin_dir = plugin_dir
        self.info_file = plugin_dir / ".plugin_info.json"
        # 回退存储位置（应用数据目录），用于插件目录不可写的场景
        self.fallback_dir = Path(__file__).parent.parent.parent / "data" / "plugin_identity"
        self.fallback_file = self.fallback_dir / f"{plugin_dir.name}.json"
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
        # 按 "插件目录 → 数据目录回退" 顺序查找已有 UUID
        for info_path in (self.info_file, self.fallback_file):
            if info_path.exists():
                self._load_from_file(info_path)
                if self._plugin_id:
                    return self._plugin_id
        
        # 生成新的 UUID
        self._plugin_id = str(uuid.uuid4())
        self._registered_at = datetime.now(timezone.utc)
        self._save_to_file()
        
        return self._plugin_id
    
    def _load_from_file(self, info_path: Optional[Path] = None):
        """从文件加载插件信息"""
        if info_path is None:
            info_path = self.info_file
        try:
            with open(info_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._plugin_id = data.get("plugin_id")
                registered_at = data.get("registered_at")
                if registered_at:
                    self._registered_at = datetime.fromisoformat(registered_at)
        except (json.JSONDecodeError, ValueError, IOError) as e:
            self._logger.warning(get_name(), f'Failed to load plugin info from {info_path}: {e}')
            self._plugin_id = None
            self._registered_at = None
    
    def _save_to_file(self):
        """保存插件信息到文件（优先插件目录，失败时回退到数据目录）"""
        data = {
            "plugin_id": self._plugin_id,
            "registered_at": self._registered_at.isoformat() if self._registered_at else None
        }
        try:
            with open(self.info_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return
        except IOError as e:
            self._logger.debug(
                get_name(),
                f'Failed to save plugin info to {self.info_file}: {e}，尝试回退到数据目录'
            )
        # 回退：插件目录不可写时写入应用数据目录，保证 UUID 稳定
        try:
            self.fallback_dir.mkdir(parents=True, exist_ok=True)
            with open(self.fallback_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self._logger.error(get_name(), f'Failed to save plugin info to {self.fallback_file}: {e}')
    
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
        self._registered_at = datetime.now(timezone.utc)
        self._save_to_file()
        return self._plugin_id

    def delete(self) -> None:
        """
        删除插件 UUID 持久化文件（插件卸载时调用）

        同时清理插件目录内的 .plugin_info.json 与数据目录回退文件，
        删除失败仅记录告警，不阻断卸载流程。
        """
        for path in (self.info_file, self.fallback_file):
            try:
                if path.exists():
                    path.unlink()
            except OSError as e:
                self._logger.warning(get_name(), f'删除插件标识文件失败 {path}: {e}')