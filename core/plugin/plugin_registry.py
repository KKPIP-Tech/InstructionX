"""
已安装插件注册表

记录每个已安装插件的当前版本、来源与安装路径，
用于升级/降级判断与更新检查。持久化到 config/plugin_registry.json。
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from utils.logging_tools import LoggerManager, get_name

from .plugin_startup import PluginDescriptorSnapshot, read_plugin_descriptor

SOURCE_VISIBILITY_PUBLIC = "public"
SOURCE_VISIBILITY_PRIVATE = "private"
SOURCE_VISIBILITY_UNKNOWN = "unknown"
SOURCE_VISIBILITIES = {
    SOURCE_VISIBILITY_PUBLIC,
    SOURCE_VISIBILITY_PRIVATE,
    SOURCE_VISIBILITY_UNKNOWN,
}
_REGISTRY_BACKUP_SUFFIX = ".migrated-v1.bak"


class PluginRegistry:
    """
    已安装插件注册表

    以插件 UUID 为键，记录：
    - descriptor_id：IXPlugin.json 中的 id（决定目录名与升级匹配）
    - name / scope / version：显示名、归属目录、当前版本
    - source_type / source_url / source_path：来源类型（github/local_zip/unknown）、
      来源仓库 URL、多插件仓库中的相对路径
    - installed_at：最近一次安装/升级时间

    老版本无此文件时，由 PluginManager 在加载后扫描插件目录自动回填。
    """

    SCHEMA_VERSION = 2
    DESCRIPTOR_FILE = "IXPlugin.json"

    def __init__(self, config_dir: Optional[Path] = None):
        """初始化注册表

        Args:
            config_dir: 配置文件目录，默认为项目根目录下 config/
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent.parent / "config"
        self.config_dir = config_dir
        self.config_file = self.config_dir / "plugin_registry.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._logger = LoggerManager()
        self._data: Optional[Dict] = None

    # ==================== 读写 ====================

    def _load(self) -> Dict:
        """加载注册表数据（惰性，损坏时备份并重建）"""
        if self._data is not None:
            return self._data
        if not self.config_file.exists():
            self._data = {"version": self.SCHEMA_VERSION, "plugins": {}}
            return self._data
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or not isinstance(data.get("plugins"), dict):
                raise ValueError("注册表结构无效")
            self._data = data
            self._data = self._migrate_loaded_data(data)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            self._logger.error(get_name(), f"读取插件注册表失败，已重建: {e}")
            self._backup_corrupt_file()
            self._data = {"version": self.SCHEMA_VERSION, "plugins": {}}
        return self._data

    def _migrate_loaded_data(self, data: Dict) -> Dict:
        """把旧版注册表无损迁移到当前 schema。

        v1 记录只补默认来源字段，不在启动阶段联网探测仓库可见性。
        """
        version = data.get("version", 1)
        if version >= self.SCHEMA_VERSION:
            return data
        self._backup_before_migration()
        for record in data["plugins"].values():
            if isinstance(record, dict):
                record.setdefault(
                    "source_visibility", SOURCE_VISIBILITY_UNKNOWN)
                record.setdefault("source_key_id", "")
        data["version"] = self.SCHEMA_VERSION
        if self._save():
            self._logger.info(get_name(), "插件注册表已迁移至 schema v2")
        else:
            self._logger.warning(
                get_name(), "插件注册表已内存迁移，但写回磁盘失败")
        return data

    def _backup_before_migration(self) -> None:
        """迁移前保留一次原始注册表备份。"""
        backup = self.config_file.with_name(
            self.config_file.name + _REGISTRY_BACKUP_SUFFIX)
        if backup.exists():
            return
        try:
            shutil.copy2(self.config_file, backup)
        except OSError as exc:
            self._logger.warning(
                get_name(), f"备份插件注册表迁移前版本失败: {exc}")

    def _save(self) -> bool:
        """原子写注册表到磁盘"""
        if self._data is None:
            return True
        try:
            temp_file = self.config_file.with_suffix(".json.tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
            os.replace(temp_file, self.config_file)
            return True
        except (OSError, TypeError, ValueError) as e:
            self._logger.error(get_name(), f"保存插件注册表失败: {e}")
            return False

    def _backup_corrupt_file(self) -> None:
        """备份损坏的注册表文件（覆盖旧备份）"""
        try:
            backup = self.config_file.with_suffix(".json.corrupt.bak")
            os.replace(self.config_file, backup)
        except OSError as e:
            self._logger.warning(get_name(), f"备份损坏注册表失败: {e}")

    # ==================== 查询与更新 ====================

    def get(self, plugin_id: str) -> Optional[Dict]:
        """获取指定 UUID 的插件记录，不存在返回 None"""
        return self._load()["plugins"].get(plugin_id)

    def all(self) -> Dict[str, Dict]:
        """获取全部注册记录（uuid -> record）"""
        return dict(self._load()["plugins"])

    def find_by_source_key(self, key_id: str) -> List[Tuple[str, Dict]]:
        """查找绑定指定 GitHub Key 的所有插件。

        Args:
            key_id: 本地 GitHub Key UUID。

        Returns:
            List[Tuple[str, Dict]]: (插件 UUID, 注册记录) 列表。
        """
        if not key_id:
            return []
        return [
            (plugin_id, record)
            for plugin_id, record in self._load()["plugins"].items()
            if record.get("source_key_id") == key_id
        ]

    def find_by_descriptor(self, scope: str, descriptor_id: str) -> Optional[Tuple[str, Dict]]:
        """按 scope + descriptor_id 查找已安装插件

        Args:
            scope: "official" 或 "thirdparty"
            descriptor_id: IXPlugin.json 中的 id

        Returns:
            (uuid, record) 元组，未找到返回 None
        """
        for uuid, record in self._load()["plugins"].items():
            if record.get("scope") == scope and record.get("descriptor_id") == descriptor_id:
                return uuid, record
        return None

    def upsert(self, plugin_id: str, *, descriptor_id: str, name: str, scope: str,
               version: str, source_type: str = "unknown",
               source_url: str = "", source_path: str = "",
               source_visibility: str = SOURCE_VISIBILITY_UNKNOWN,
               source_key_id: str = "") -> bool:
        """写入或更新插件记录（安装/升级后调用）

        Args:
            plugin_id: 插件 UUID
            descriptor_id: IXPlugin.json 中的 id
            name: 插件显示名
            scope: "official" 或 "thirdparty"
            version: 当前版本字符串（如 release.1.0.0）
            source_type: 来源类型（github/local_zip/unknown）
            source_url: 来源仓库 URL（GitHub 来源时记录）
            source_path: 多插件仓库中的相对路径（单插件仓库为空）
            source_visibility: 来源可见性 public/private/unknown
            source_key_id: 私有 GitHub 来源绑定的本地 Key UUID

        Returns:
            保存是否成功
        """
        self._validate_visibility(source_visibility)
        record = self._build_record(
            descriptor_id, name, scope, version, source_type,
            source_url, source_path, source_visibility, source_key_id,
        )
        # 保留首次安装时间：已有记录时沿用原 installed_at 之外的字段不可考，
        # 这里 installed_at 语义为“最近一次安装/升级时间”，直接覆盖即可
        # 清理同一 scope + descriptor_id 的旧记录（升级时 UUID 曾变化的遗留）
        plugins = self._load()["plugins"]
        self._remove_stale_records(plugins, plugin_id, scope, descriptor_id)
        plugins[plugin_id] = record
        return self._save()

    @staticmethod
    def _remove_stale_records(
        plugins: Dict, plugin_id: str, scope: str, descriptor_id: str
    ) -> None:
        """删除同 scope + descriptor_id 的历史 UUID 记录。"""
        stale = [
            key for key, value in plugins.items()
            if key != plugin_id
            and value.get("scope") == scope
            and value.get("descriptor_id") == descriptor_id
        ]
        for key in stale:
            del plugins[key]

    @staticmethod
    def _build_record(
        descriptor_id: str,
        name: str,
        scope: str,
        version: str,
        source_type: str,
        source_url: str,
        source_path: str,
        source_visibility: str,
        source_key_id: str,
    ) -> Dict:
        """构造一条安装记录。"""
        return {
            "descriptor_id": descriptor_id,
            "name": name,
            "scope": scope,
            "version": version,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source_type": source_type,
            "source_url": source_url,
            "source_path": source_path,
            "source_visibility": source_visibility,
            "source_key_id": source_key_id,
        }

    def set_source_binding(
        self,
        plugin_id: str,
        *,
        source_visibility: str,
        source_key_id: str,
    ) -> bool:
        """更新插件的 GitHub 来源可见性与 Key 绑定。

        Args:
            plugin_id: 插件 UUID。
            source_visibility: public/private/unknown。
            source_key_id: 绑定 Key UUID；公共来源为空串。

        Returns:
            bool: 记录存在且保存成功时返回 True。
        """
        self._validate_visibility(source_visibility)
        data = self._load()
        record = data["plugins"].get(plugin_id)
        if record is None:
            return False
        previous = (
            record.get("source_visibility", SOURCE_VISIBILITY_UNKNOWN),
            record.get("source_key_id", ""),
        )
        record["source_visibility"] = source_visibility
        record["source_key_id"] = source_key_id
        if self._save():
            return True
        record["source_visibility"], record["source_key_id"] = previous
        return False

    def clear_source_binding(self, plugin_id: str) -> bool:
        """清除插件 Key 绑定并标记来源可见性未知。"""
        return self.set_source_binding(
            plugin_id,
            source_visibility=SOURCE_VISIBILITY_UNKNOWN,
            source_key_id="",
        )

    def remove(self, plugin_id: str) -> bool:
        """移除插件记录（卸载时调用）"""
        data = self._load()
        if plugin_id in data["plugins"]:
            del data["plugins"][plugin_id]
            return self._save()
        return True

    def set_scope(self, plugin_id: str, scope: str) -> bool:
        """更新插件记录的分类（插件在官方 ↔ 第三方目录之间移动时调用）

        只改 ``scope`` 字段：版本、来源与安装时间随插件目录一起保持不变。

        Args:
            plugin_id: 插件 UUID
            scope: 新的分类（"official" / "thirdparty"）

        Returns:
            记录存在且保存成功返回 True；记录不存在返回 False
        """
        record = self._load()["plugins"].get(plugin_id)
        if record is None:
            self._logger.warning(get_name(), f"移动插件分类失败：注册表无记录 {plugin_id}")
            return False
        record["scope"] = scope
        return self._save()

    # ==================== 回填 ====================

    def backfill(self, entries: List[Tuple[str, str, Path]]) -> int:
        """扫描已加载插件，为缺失记录的插件回填版本信息

        Args:
            entries: (uuid, scope, 插件目录) 三元组列表

        Returns:
            新回填的记录数量
        """
        data = self._load()
        added = 0
        for uuid, scope, plugin_dir in entries:
            if not uuid or uuid in data["plugins"]:
                continue
            record = self._read_descriptor_record(scope, plugin_dir)
            if record is None:
                continue
            data["plugins"][uuid] = record
            added += 1
        if added:
            self._save()
            self._logger.info(get_name(), f"插件注册表回填 {added} 条记录")
        return added

    def reconcile(self, entries: List[Tuple[str, str, Path]]) -> int:
        """以插件目录中的描述文件校准已安装记录。

        与 :meth:`backfill` 只补缺失记录不同，本方法会更新已有记录的
        ``version``、``name``、``descriptor_id`` 与 ``scope``，用于识别用户
        绕过插件管理器手动替换目录后的实际版本。来源 URL、可见性与 Key
        绑定等安装元数据保持不变。

        Args:
            entries: ``(插件 UUID, scope, 插件目录)`` 三元组列表。

        Returns:
            int: 新增、更新或清理旧记录的数量。
        """
        data = self._load()
        changed = 0
        for plugin_id, scope, plugin_dir in entries:
            snapshot = read_plugin_descriptor(plugin_dir)
            if snapshot is None or not plugin_id:
                continue
            changed += self._reconcile_entry(
                data["plugins"], plugin_id, scope, snapshot)
        if changed:
            if self._save():
                self._logger.info(
                    get_name(),
                    f"插件注册表已按插件文件校准 {changed} 条记录",
                )
            else:
                self._logger.warning(
                    get_name(), "插件注册表校准已更新内存，但写回磁盘失败")
        return changed

    def _reconcile_entry(
        self,
        plugins: Dict,
        plugin_id: str,
        scope: str,
        snapshot: PluginDescriptorSnapshot,
    ) -> int:
        """校准单条插件记录并清理同描述 ID 的历史 UUID。"""
        stale = self._find_stale_records(
            plugins, plugin_id, scope, snapshot.descriptor_id)
        current = plugins.get(plugin_id)
        if current is None:
            record = self._descriptor_record_from_snapshot(scope, snapshot)
            self._copy_source_fields(
                record, self._latest_stale(plugins, stale))
            plugins[plugin_id] = record
            self._delete_records(plugins, stale)
            return 1
        changed = self._update_descriptor_fields(current, scope, snapshot)
        self._delete_records(plugins, stale)
        return 1 if changed or stale else 0

    @staticmethod
    def _find_stale_records(
        plugins: Dict,
        plugin_id: str,
        scope: str,
        descriptor_id: str,
    ) -> List[str]:
        """查找同范围、同描述 ID 但 UUID 已变化的历史记录。"""
        return [
            key for key, value in plugins.items()
            if key != plugin_id
            and value.get("scope") == scope
            and value.get("descriptor_id") == descriptor_id
        ]

    @staticmethod
    def _delete_records(plugins: Dict, keys: List[str]) -> None:
        """删除指定注册表记录。"""
        for key in keys:
            plugins.pop(key, None)

    @staticmethod
    def _latest_stale(plugins: Dict, keys: List[str]) -> Optional[Dict]:
        """获取最近安装的历史记录，用于继承来源绑定。"""
        records = [
            plugins[key]
            for key in keys
            if key in plugins
        ]
        return max(
            records,
            key=lambda item: item.get("installed_at", ""),
            default=None,
        )

    @staticmethod
    def _copy_source_fields(target: Dict, source: Optional[Dict]) -> None:
        """把历史来源元数据复制到 UUID 变化后的新记录。"""
        if source is None:
            return
        for field in (
            "source_type",
            "source_url",
            "source_path",
            "source_visibility",
            "source_key_id",
        ):
            target[field] = source.get(field, target[field])

    def _update_descriptor_fields(
        self,
        record: Dict,
        scope: str,
        snapshot: PluginDescriptorSnapshot,
    ) -> bool:
        """用描述文件更新现有记录的展示与版本字段。"""
        before = (
            record.get("descriptor_id"),
            record.get("name"),
            record.get("version"),
            record.get("scope"),
        )
        after = (
            snapshot.descriptor_id,
            snapshot.name,
            snapshot.version,
            scope,
        )
        if before == after:
            return False
        (
            record["descriptor_id"],
            record["name"],
            record["version"],
            record["scope"],
        ) = after
        if before[2] != after[2]:
            self._logger.info(
                get_name(),
                f"插件 {after[0]} 版本已由 {before[2]} 校准为 {after[2]}",
            )
        return True

    def _read_descriptor_record(self, scope: str, plugin_dir: Path) -> Optional[Dict]:
        """从插件目录的 IXPlugin.json 构建回填记录"""
        snapshot = read_plugin_descriptor(plugin_dir)
        if snapshot is None:
            return None
        return self._descriptor_record_from_snapshot(scope, snapshot)

    @staticmethod
    def _descriptor_record_from_snapshot(
        scope: str, snapshot: PluginDescriptorSnapshot
    ) -> Dict:
        """把描述快照转换为新的注册表记录。"""
        return {
            "descriptor_id": snapshot.descriptor_id,
            "name": snapshot.name,
            "scope": scope,
            "version": snapshot.version,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "source_type": "unknown",
            "source_url": "",
            "source_path": "",
            "source_visibility": SOURCE_VISIBILITY_UNKNOWN,
            "source_key_id": "",
        }

    @staticmethod
    def _validate_visibility(value: str) -> None:
        """拒绝未知来源可见性。"""
        if value not in SOURCE_VISIBILITIES:
            raise ValueError(f"不支持的插件来源可见性: {value}")
