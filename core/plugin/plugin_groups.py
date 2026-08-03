"""
插件自定义分组存储

在官方/第三方两个大分类之下维护用户自定义分组、
以及「分组 + 未分组插件」的统一面板顺序。
持久化到 config/plugin_groups.json（schema v2）。
"""

import json
import os
import uuid as uuid_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logging_tools import LoggerManager, get_name

# 分组默认图标（emoji，直接作为按钮文本前缀渲染，无主题适配成本）
DEFAULT_GROUP_ICON = "📁"

# 分组可选图标集（管理对话框中供用户选择）
GROUP_ICON_CHOICES = [
    "📁", "🛠", "🎨", "📊", "🔧", "📝",
    "🖼", "🎵", "🤖", "🌐", "📦", "⭐",
]

# 面板顺序条目类型
ITEM_TYPE_GROUP = "group"
ITEM_TYPE_PLUGIN = "plugin"


@dataclass
class PluginGroup:
    """插件分组数据类

    Attributes:
        id: 分组 UUID
        name: 分组显示名
        icon_key: 分组图标（emoji 字符）
        plugins: 组内插件 UUID 列表（顺序即组内显示顺序）
    """
    id: str
    name: str
    icon_key: str = DEFAULT_GROUP_ICON
    plugins: List[str] = field(default_factory=list)

    @staticmethod
    def new(name: str) -> "PluginGroup":
        """创建新分组（自动生成 UUID）"""
        return PluginGroup(id=str(uuid_module.uuid4()), name=name)


class PluginGroupStore:
    """
    插件分组存储（schema v2）

    管理 config/plugin_groups.json 的读写：
    - official / thirdparty 两个 scope 各自维护：
      - groups：分组数组（定义分组的名称/图标/组内插件）
      - order：面板统一顺序，条目为 ("group"|"plugin", id)，
        决定分组与未分组插件在技能面板中的混排位置
    - v1（分组数组、分组总在未分组插件之前）自动迁移为 v2
    - 原子写，损坏时备份并重建
    """

    SCHEMA_VERSION = 2
    SCOPES = ("official", "thirdparty")

    def __init__(self, config_dir: Optional[Path] = None):
        """初始化分组存储

        Args:
            config_dir: 配置文件目录，默认为项目根目录下 config/
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = config_dir
        self.config_file = self.config_dir / "plugin_groups.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._logger = LoggerManager()
        self._data: Optional[Dict] = None

    # ==================== 读写 ====================

    def _load(self) -> Dict:
        """加载分组数据（惰性，含 v1 → v2 迁移，损坏时备份重建）"""
        if self._data is not None:
            return self._data
        if not self.config_file.exists():
            self._data = self._empty_data()
            return self._data
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("分组配置结构无效")
            self._data = self._migrate(data)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            self._logger.error(get_name(), f"读取插件分组配置失败，已重建: {e}")
            self._backup_corrupt_file()
            self._data = self._empty_data()
        return self._data

    def _migrate(self, data: Dict) -> Dict:
        """将 v1 结构（scope 直接为分组数组）迁移为 v2 结构"""
        if data.get("version") == self.SCHEMA_VERSION:
            for scope in self.SCOPES:
                data.setdefault(scope, {"groups": [], "order": []})
            return data

        migrated = {"version": self.SCHEMA_VERSION}
        for scope in self.SCOPES:
            old = data.get(scope, [])
            groups = old if isinstance(old, list) else []
            # v1 语义为「分组在前、未分组插件在后」，
            # 迁移后 order 仅包含分组条目，未分组插件由排序逻辑追加在后，行为一致
            order = [
                {"type": ITEM_TYPE_GROUP, "id": g.get("id", "")}
                for g in groups if isinstance(g, dict) and g.get("id")
            ]
            migrated[scope] = {"groups": groups, "order": order}
        self._logger.info(get_name(), "插件分组配置已从 v1 迁移到 v2")
        return migrated

    def _save(self) -> bool:
        """原子写分组配置到磁盘"""
        if self._data is None:
            return True
        try:
            temp_file = self.config_file.with_suffix(".json.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, self.config_file)
            return True
        except (OSError, TypeError, ValueError) as e:
            self._logger.error(get_name(), f"保存插件分组配置失败: {e}")
            return False

    def _empty_data(self) -> Dict:
        """构造空分组配置（v2 结构）"""
        return {
            "version": self.SCHEMA_VERSION,
            "official": {"groups": [], "order": []},
            "thirdparty": {"groups": [], "order": []},
        }

    def _backup_corrupt_file(self) -> None:
        """备份损坏的分组配置文件（覆盖旧备份）"""
        try:
            backup = self.config_file.with_suffix(".json.corrupt.bak")
            os.replace(self.config_file, backup)
        except OSError as e:
            self._logger.warning(get_name(), f"备份损坏分组配置失败: {e}")

    # ==================== 分组操作 ====================

    def load(self, scope: str) -> List[PluginGroup]:
        """加载指定 scope 的分组列表

        Args:
            scope: "official" 或 "thirdparty"

        Returns:
            PluginGroup 列表；scope 非法时返回空列表
        """
        scope_data = self._scope_data(scope)
        if scope_data is None:
            return []
        groups = []
        for entry in scope_data["groups"]:
            if not isinstance(entry, dict):
                continue
            groups.append(PluginGroup(
                id=entry.get("id", ""),
                name=entry.get("name", "未命名分组"),
                icon_key=entry.get("icon_key", DEFAULT_GROUP_ICON),
                plugins=list(entry.get("plugins", [])),
            ))
        return groups

    def load_order(self, scope: str) -> List[Tuple[str, str]]:
        """加载指定 scope 的面板统一顺序

        Args:
            scope: "official" 或 "thirdparty"

        Returns:
            (条目类型, id) 元组列表，类型为 "group" 或 "plugin"
        """
        scope_data = self._scope_data(scope)
        if scope_data is None:
            return []
        order = []
        for entry in scope_data["order"]:
            if not isinstance(entry, dict):
                continue
            item_type = entry.get("type", "")
            item_id = entry.get("id", "")
            if item_type in (ITEM_TYPE_GROUP, ITEM_TYPE_PLUGIN) and item_id:
                order.append((item_type, item_id))
        return order

    def save(self, scope: str, groups: List[PluginGroup],
             order: Optional[List[Tuple[str, str]]] = None) -> bool:
        """保存指定 scope 的分组与面板统一顺序

        Args:
            scope: "official" 或 "thirdparty"
            groups: PluginGroup 列表
            order: 面板统一顺序 [("group"|"plugin", id), ...]；
                   为 None 时保留已有顺序（过滤失效条目后追加新分组）

        Returns:
            保存是否成功
        """
        scope_data = self._scope_data(scope)
        if scope_data is None:
            return False
        scope_data["groups"] = [
            {
                "id": g.id,
                "name": g.name,
                "icon_key": g.icon_key or DEFAULT_GROUP_ICON,
                "plugins": list(g.plugins),
            }
            for g in groups
        ]
        scope_data["order"] = self._build_order_entries(scope, groups, order)
        return self._save()

    def _build_order_entries(self, scope: str, groups: List[PluginGroup],
                             order: Optional[List[Tuple[str, str]]]) -> List[Dict]:
        """构造待保存的 order 条目；order 为 None 时保留旧顺序并追加新分组"""
        group_ids = {g.id for g in groups}
        if order is not None:
            return [{"type": t, "id": i} for t, i in order]

        # 兼容旧调用：保留旧 order 中仍有效的条目，新分组追加在后
        existing = [
            {"type": t, "id": i} for t, i in self.load_order(scope)
            if t == ITEM_TYPE_PLUGIN or i in group_ids
        ]
        known = {e["id"] for e in existing if e["type"] == ITEM_TYPE_GROUP}
        for g in groups:
            if g.id not in known:
                existing.append({"type": ITEM_TYPE_GROUP, "id": g.id})
        return existing

    def remove_plugin(self, plugin_id: str) -> bool:
        """从所有分组与面板顺序中移除指定插件 UUID（插件卸载时调用）

        Returns:
            有变更且保存成功返回 True；无变更也返回 True
        """
        changed = False
        for scope in self.SCOPES:
            scope_data = self._scope_data(scope)
            for entry in scope_data["groups"]:
                plugins = entry.get("plugins", [])
                if plugin_id in plugins:
                    entry["plugins"] = [p for p in plugins if p != plugin_id]
                    changed = True
            order = scope_data["order"]
            new_order = [
                e for e in order
                if not (e.get("type") == ITEM_TYPE_PLUGIN and e.get("id") == plugin_id)
            ]
            if len(new_order) != len(order):
                scope_data["order"] = new_order
                changed = True
        if changed:
            return self._save()
        return True

    # ==================== 内部工具 ====================

    def _scope_data(self, scope: str) -> Optional[Dict]:
        """获取指定 scope 的数据字典，非法 scope 记录告警并返回 None"""
        if scope not in self.SCOPES:
            self._logger.warning(get_name(), f"非法的分组 scope: {scope}")
            return None
        return self._load()[scope]
