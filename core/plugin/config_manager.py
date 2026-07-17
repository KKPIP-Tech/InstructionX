"""
插件配置管理器

负责管理和持久化插件相关的配置信息，包括：
- 插件显示顺序配置
- 配置文件读写操作
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from utils.logging_tools import LoggerManager, get_name


class PluginConfigManager:
    """
    插件配置管理器

    管理插件显示顺序等配置信息的持久化。采用 JSON 格式存储配置，
    支持官方插件和第三方插件两组独立的顺序配置。

    注意：此类不是单例，由 PluginManager 在初始化时创建实例，
    主要作为 JSON 配置文件读写工具使用。
    """

    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置管理器

        Args:
            config_dir: 配置文件存储目录，默认为项目根目录下的 config/
        """
        if config_dir is None:
            # 使用项目根目录下的 config 目录
            config_dir = Path(__file__).parent.parent.parent / "config"

        self.config_dir = config_dir
        self.config_file = self.config_dir / "plugin_order.json"

        # 确保配置目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 日志管理器
        self._logger = LoggerManager()

    def load_plugin_order(self) -> Dict[str, List[str]]:
        """
        从磁盘加载插件显示顺序配置

        Returns:
            包含 'official_plugins' 和 'thirdparty_plugins' 键的字典，
            分别存储官方插件和第三方插件的 UUID 列表。
            配置文件不存在或格式错误时返回空字典结构 `{"official_plugins": [], "thirdparty_plugins": []}`。
        """
        if not self.config_file.exists():
            return {
                "official_plugins": [],
                "thirdparty_plugins": []
            }

        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 验证数据格式
            if not isinstance(data, dict):
                return {
                    "official_plugins": [],
                    "thirdparty_plugins": []
                }

            # 补齐可能缺失的键
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
        将插件显示顺序保存到磁盘

        Args:
            official_plugins: 官方插件 UUID 列表
            thirdparty_plugins: 第三方插件 UUID 列表

        Returns:
            保存操作是否成功
        """
        try:
            data = {
                "official_plugins": official_plugins,
                "thirdparty_plugins": thirdparty_plugins
            }

            # 原子写：先写临时文件再 os.replace，避免写入中断产生损坏文件
            temp_file = self.config_file.with_suffix('.json.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, self.config_file)

            return True

        except Exception as e:
            self._logger.error(get_name(), f'Error saving plugin order config: {e}')
            return False

    def update_official_order(self, plugin_uuids: List[str]) -> bool:
        """
        仅更新官方插件的显示顺序

        Args:
            plugin_uuids: 官方插件 UUID 列表

        Returns:
            保存操作是否成功
        """
        config = self.load_plugin_order()
        config["official_plugins"] = plugin_uuids
        return self.save_plugin_order(config["official_plugins"], config["thirdparty_plugins"])

    def update_thirdparty_order(self, plugin_uuids: List[str]) -> bool:
        """
        仅更新第三方插件的显示顺序

        Args:
            plugin_uuids: 第三方插件 UUID 列表

        Returns:
            保存操作是否成功
        """
        config = self.load_plugin_order()
        config["thirdparty_plugins"] = plugin_uuids
        return self.save_plugin_order(config["official_plugins"], config["thirdparty_plugins"])