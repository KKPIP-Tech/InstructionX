"""SQLite 后端：连接、DDL、事务、版本管理、CRUD、序列化、LRU 缓存。

本模块为 DataProvider 提供基于 SQLite 的持久化实现，对插件层完全透明。
"""

import copy
import datetime as dt
import math
import os
import sqlite3
import threading
from collections import OrderedDict, deque
from contextlib import contextmanager
from collections.abc import Mapping, Sequence
from enum import Enum, IntEnum, IntFlag
from pathlib import Path
from typing import Any, Dict, Generator, Optional, Tuple
from uuid import UUID

import orjson

from .schema_migrations import MIGRATIONS, TARGET_SCHEMA_VERSION
from . import sql_map


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class SQLiteBackendError(Exception):
    """SQLite 后端内部异常，通常会被 DataProvider 包装为 DataProviderError。"""
    pass


# ---------------------------------------------------------------------------
# LRU 反序列化缓存
# ---------------------------------------------------------------------------

class _LRUCache:
    """带容量上限的 LRU 缓存。

    注意：本类不是线程安全的，所有 get/put/invalidate/clear 操作
    必须在 DataProvider 的 _file_lock（RLock）保护下进行。
    """

    # 用于区分"缓存未命中"与"缓存值为 None/False/空"
    MISSING = object()

    def __init__(self, capacity: int = 4096):
        self.capacity = capacity
        self._data: "OrderedDict[Tuple[str, str, str], Any]" = OrderedDict()

    def get(self, key: Tuple[str, str, str]) -> Any:
        value = self._data.get(key, self.MISSING)
        if value is self.MISSING:
            return self.MISSING
        self._data.move_to_end(key)
        return value

    def put(self, key: Tuple[str, str, str], value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self.capacity:
            self._data.popitem(last=False)

    def invalidate(self, key: Tuple[str, str, str]) -> None:
        self._data.pop(key, None)

    def invalidate_plugin(self, instance_id: str) -> None:
        keys = [k for k in self._data if k[0] == instance_id]
        for k in keys:
            self._data.pop(k, None)

    def clear(self) -> None:
        self._data.clear()


# ---------------------------------------------------------------------------
# 序列化与反序列化
# ---------------------------------------------------------------------------

def _raise_non_serializable(obj: Any) -> None:
    """用于 orjson default 钩子，拒绝所有无法识别的类型。"""
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _scan_non_json_types(obj: Any) -> None:
    """
    递归扫描标准库 json 无法序列化、或 orjson 行为与标准库不一致的类型，
    保持与当前 json 行为一致：
    - datetime / date / time
    - NaN / Inf
    - UUID
    - dataclass 实例
    - bytes / bytearray
    - set / frozenset
    - deque
    - 普通 Enum 实例（IntEnum / IntFlag 与 int 行为一致，不拒绝）
    """
    if isinstance(obj, (dt.datetime, dt.date, dt.time)):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        raise ValueError("Out of range float values are not JSON compliant")
    if isinstance(obj, UUID):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, (set, frozenset, bytearray, bytes)):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, Enum) and not isinstance(obj, (IntEnum, IntFlag)):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, deque):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if hasattr(type(obj), '__dataclass_fields__') and not isinstance(
        obj, (str, bytes, bytearray, Mapping, Sequence, set, frozenset, deque)
    ):
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if isinstance(k, tuple):
                raise TypeError(f"Object of type {type(k).__name__} is not JSON serializable")
            _scan_non_json_types(k)
            _scan_non_json_types(v)
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        for item in obj:
            _scan_non_json_types(item)


def _serialize(value: Any) -> str:
    """将 Python 对象序列化为 JSON 文本（使用 orjson），行为与标准库 json 一致。"""
    try:
        _scan_non_json_types(value)
        return orjson.dumps(
            value,
            option=(
                orjson.OPT_NON_STR_KEYS
                | orjson.OPT_PASSTHROUGH_DATETIME
                | orjson.OPT_PASSTHROUGH_DATACLASS
            ),
            default=_raise_non_serializable,
        ).decode('utf-8')
    except (TypeError, ValueError, orjson.JSONEncodeError) as e:
        raise SQLiteBackendError(f"数据序列化失败: {e}")


def _deserialize(text: str) -> Any:
    """将 JSON 文本反序列化为 Python 对象（使用 orjson）。"""
    try:
        return orjson.loads(text)
    except (orjson.JSONDecodeError, TypeError, ValueError) as e:
        raise SQLiteBackendError(f"数据反序列化失败: {e}")


# ---------------------------------------------------------------------------
# 迁移专用清洗
# ---------------------------------------------------------------------------

def _sanitize_for_migration(obj: Any, path: str = "") -> Any:
    """迁移专用：递归将 NaN/Inf 替换为 None，同时处理 dict key。"""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        new_dict: Dict[Any, Any] = {}
        for k, v in obj.items():
            new_k = _sanitize_for_migration(k, f"{path}.{k}(key)")
            if not isinstance(new_k, (str, int, float, bool, type(None))):
                new_k = str(new_k)
            new_dict[new_k] = _sanitize_for_migration(v, f"{path}.{k}")
        return new_dict
    if isinstance(obj, list):
        return [_sanitize_for_migration(item, f"{path}[{i}]") for i, item in enumerate(obj)]
    return obj


# ---------------------------------------------------------------------------
# SQLite 后端
# ---------------------------------------------------------------------------

class SQLiteBackend:
    """SQLite 持久化后端。

    负责数据库连接、DDL、事务、版本调度、序列化/反序列化。
    所有公共方法假设调用方已持有 DataProvider._file_lock。
    """

    def __init__(self, data_dir: Optional[str], data_filename: str = "data.json"):
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        # 数据库文件路径推导：.json -> .db，否则追加 .db
        if data_filename.lower().endswith('.json'):
            db_filename = data_filename[:-5] + ".db"
        else:
            db_filename = data_filename + ".db"
        self.db_file = self.data_dir / db_filename

        self.json_file = self.data_dir / data_filename
        self.temp_json_file = self.data_dir / f"{data_filename}.tmp"

        self._conn: Optional[sqlite3.Connection] = None
        self._value_cache = _LRUCache(capacity=4096)

    # -----------------------------------------------------------------------
    # 连接与 PRAGMA
    # -----------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        """创建或复用数据库连接。"""
        if self._conn is None:
            self._conn = sqlite3.connect(
                str(self.db_file),
                check_same_thread=False,
                isolation_level=None,  # 使用手动事务控制
            )
            self._execute_pragmas()
        return self._conn

    def _execute_pragmas(self) -> None:
        conn = self._conn
        if conn is None:
            return
        conn.execute(sql_map.SQLMap.v1.PRAGMA_FOREIGN_KEYS)
        conn.execute(sql_map.SQLMap.v1.PRAGMA_JOURNAL_MODE_WAL)
        conn.execute(sql_map.SQLMap.v1.PRAGMA_SYNCHRONOUS_NORMAL)

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # -----------------------------------------------------------------------
    # 事务上下文
    # -----------------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """返回一个使用 BEGIN IMMEDIATE 的事务上下文。

        注意：不支持嵌套事务。已处于事务中时抛出 SQLiteBackendError，
        调用方需避免在 transaction() 上下文内再次进入 transaction()
        （包括间接调用内部使用了 transaction() 的方法）。
        """
        conn = self._connect()
        if conn.in_transaction:
            raise SQLiteBackendError("transaction() 不支持嵌套调用：已处于事务中")
        try:
            conn.execute(sql_map.SQLMap.v1.BEGIN_IMMEDIATE)
            yield conn
            conn.execute(sql_map.SQLMap.v1.COMMIT)
        except Exception:
            try:
                conn.execute(sql_map.SQLMap.v1.ROLLBACK)
            except Exception:
                pass
            raise

    # -----------------------------------------------------------------------
    # DDL
    # -----------------------------------------------------------------------

    def _create_tables(self, conn: sqlite3.Connection) -> None:
        conn.executescript(sql_map.SQLMap.v1.CREATE_TABLES_SCRIPT)

    # -----------------------------------------------------------------------
    # 版本与元数据
    # -----------------------------------------------------------------------

    @staticmethod
    def _get_schema_version(conn: sqlite3.Connection) -> int:
        """读取当前 schema 版本。若表或键不存在返回 0；值损坏则抛异常。"""
        try:
            cur = conn.execute(sql_map.SQLMap.v1.SELECT_SCHEMA_VERSION)
            row = cur.fetchone()
            if row is None:
                return 0
            return int(row[0])
        except sqlite3.OperationalError as e:
            # db_metadata 表不存在（早期无版本数据库）时按文档约定返回 0
            if "no such table" in str(e).lower():
                return 0
            raise SQLiteBackendError(f"数据库 schema_version 读取或解析失败: {e}") from e
        except ValueError as e:
            raise SQLiteBackendError(f"数据库 schema_version 读取或解析失败: {e}") from e

    @staticmethod
    def _set_metadata(conn: sqlite3.Connection, **items: str) -> None:
        for key, value in items.items():
            conn.execute(sql_map.SQLMap.v1.UPSERT_METADATA, (key, value))

    def _upgrade_schema(self, conn: sqlite3.Connection) -> None:
        current = self._get_schema_version(conn)
        target = TARGET_SCHEMA_VERSION
        if current > target:
            raise SQLiteBackendError(
                f"数据库版本 {current} 高于当前代码目标版本 {target}，请升级应用版本"
            )
        while current < target:
            next_version = current + 1
            migration = MIGRATIONS.get(next_version)
            if migration is None:
                raise SQLiteBackendError(f"缺少升级到版本 {next_version} 的迁移脚本")
            # 连接处于 autocommit 模式（isolation_level=None），`with conn:` 不会开启事务；
            # 显式 BEGIN IMMEDIATE ... COMMIT / ROLLBACK，保证每次迁移是独立事务，
            # 中途失败不会留下半截 schema
            conn.execute(sql_map.SQLMap.v1.BEGIN_IMMEDIATE)
            try:
                migration(conn)
                self._set_metadata(conn, schema_version=str(next_version))
                conn.execute(sql_map.SQLMap.v1.COMMIT)
            except Exception as e:
                try:
                    conn.execute(sql_map.SQLMap.v1.ROLLBACK)
                except Exception:
                    pass
                raise SQLiteBackendError(f"数据库升级到版本 {next_version} 失败: {e}") from e
            current = next_version

    # -----------------------------------------------------------------------
    # 数据库初始化入口
    # -----------------------------------------------------------------------

    def ensure_database(self) -> None:
        """确保数据库已创建、schema 正确、版本最新，并完成 JSON 迁移。"""
        self._remove_temp_json_file_if_exists()

        db_exists = self.db_file.exists() and self.db_file.stat().st_size > 0
        has_core_tables = db_exists and self._has_core_tables()

        if not has_core_tables:
            # 新建数据库：先解析 JSON（如果存在），再创建数据库
            json_data = None
            if self.json_file.exists():
                json_data = self._parse_json_file()

            try:
                # DDL 会隐式提交 SQLite 事务，因此先单独执行 DDL
                conn = self._connect()
                self._create_tables(conn)

                # 数据迁移与元数据写入在同一个显式事务中，失败可整体回滚
                with self.transaction() as txn:
                    if json_data is not None:
                        self._migrate_json_to_sqlite(txn, json_data)
                    now = dt.datetime.now(dt.timezone.utc).isoformat()
                    self._set_metadata(
                        txn,
                        schema_version=str(TARGET_SCHEMA_VERSION),
                        migrated_from=self.json_file.name if json_data is not None else "created",
                        migrated_at=now,
                    )

                # SQLite 事务提交成功后，才重命名 JSON 备份
                if json_data is not None:
                    self.migrate_json_file_with_backup()
            except Exception as e:
                # 任何失败都关闭连接并删除不完整的数据库文件，
                # 确保下次启动时仍可从原始 data.json 重试迁移
                self.close()
                self._delete_db_files()
                if isinstance(e, SQLiteBackendError):
                    raise
                raise SQLiteBackendError(f"数据库初始化失败: {e}") from e
        else:
            conn = self._connect()
            self._create_tables(conn)
            current = self._get_schema_version(conn)
            if current == 0:
                # 早期无版本数据库，补齐到版本 1
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                self._set_metadata(
                    conn,
                    schema_version=str(TARGET_SCHEMA_VERSION),
                    migrated_from="legacy",
                    migrated_at=now,
                )
            elif current < TARGET_SCHEMA_VERSION:
                self._upgrade_schema(conn)
            elif current > TARGET_SCHEMA_VERSION:
                raise SQLiteBackendError(
                    f"数据库版本 {current} 高于代码目标版本 {TARGET_SCHEMA_VERSION}"
                )
            self._validate_table_schema(conn)

    # -----------------------------------------------------------------------
    # 辅助方法
    # -----------------------------------------------------------------------

    def _has_core_tables(self) -> bool:
        """检查数据库是否已包含核心业务表（不含 db_metadata）。

        注意：db_metadata 可能在早期数据库中不存在，因此只检查 plugins、
        plugin_data、active_instances 三张表是否存在。
        """
        if not self.db_file.exists():
            return False
        try:
            conn = self._connect()
            cur = conn.execute(sql_map.SQLMap.v1.SELECT_CORE_TABLES)
            return len(cur.fetchall()) == 3
        except Exception:
            return False

    def _remove_temp_json_file_if_exists(self) -> None:
        try:
            if self.temp_json_file.exists():
                self.temp_json_file.unlink()
        except Exception:
            pass

    def _delete_db_files(self) -> None:
        """删除数据库文件及其 WAL/SHM 附属文件。"""
        base_name = self.db_file.name
        for suffix in ("", "-wal", "-shm"):
            path = self.db_file.parent / (base_name + suffix)
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass

    def _parse_json_file(self) -> Dict[str, Any]:
        import json as _json
        try:
            # utf-8-sig 兼容带 BOM 与不带 BOM 的 UTF-8 文件
            with open(self.json_file, 'r', encoding='utf-8-sig') as f:
                return _json.load(f)
        except _json.JSONDecodeError as e:
            raise SQLiteBackendError(f"JSON 解析失败: {e}")
        except Exception as e:
            raise SQLiteBackendError(f"读取数据文件失败: {e}")

    def _validate_table_schema(self, conn: sqlite3.Connection) -> None:
        """校验核心表结构是否完整（CREATE TABLE IF NOT EXISTS 无法检测列缺失）。"""
        expected = {
            'plugins': {
                ('instance_id', 'TEXT', 0, None, 1),
                ('plugin_type', 'TEXT', 1, None, 0),
                ('active', 'INTEGER', 1, '0', 0),
            },
            'plugin_data': {
                ('id', 'INTEGER', 0, None, 1),
                ('instance_id', 'TEXT', 1, None, 0),
                ('namespace', 'TEXT', 1, None, 0),
                ('key', 'TEXT', 1, None, 0),
                ('value_json', 'TEXT', 1, None, 0),
                ('updated_at', 'INTEGER', 1, "strftime('%s', 'now')", 0),
            },
            'active_instances': {
                ('plugin_type', 'TEXT', 0, None, 1),
                ('instance_id', 'TEXT', 1, None, 0),
            },
            'db_metadata': {
                ('key', 'TEXT', 0, None, 1),
                ('value', 'TEXT', 1, None, 0),
            },
        }
        for table, expected_cols in expected.items():
            cur = conn.execute(sql_map.SQLMap.v1.table_info_sql(table))
            actual_cols = {(row[1], row[2], row[3], row[4], row[5]) for row in cur.fetchall()}
            missing = expected_cols - actual_cols
            if missing:
                raise SQLiteBackendError(
                    f"表 {table} 结构异常，缺少或类型不匹配列: {missing}"
                )


    # -----------------------------------------------------------------------
    # JSON → SQLite 迁移
    # -----------------------------------------------------------------------

    def _migrate_json_to_sqlite(
        self, conn: sqlite3.Connection, data: Dict[str, Any]
    ) -> None:
        """将解析后的 JSON 数据导入到 SQLite。"""
        plugins = data.get("plugins", {})
        active_instances = data.get("active_instances", {})

        for instance_id, plugin_info in plugins.items():
            plugin_type = plugin_info.get("type", "")
            active = 1 if plugin_info.get("active", False) else 0
            conn.execute(
                sql_map.SQLMap.v1.INSERT_PLUGIN,
                (instance_id, plugin_type, active),
            )
            private = plugin_info.get("private", {})
            public = plugin_info.get("public", {})
            for namespace, ns_data in (("private", private), ("public", public)):
                for key, value in ns_data.items():
                    cleaned = _sanitize_for_migration(value, f"{instance_id}.{namespace}.{key}")
                    value_json = _serialize(cleaned)
                    conn.execute(
                        sql_map.SQLMap.v1.INSERT_PLUGIN_DATA,
                        (instance_id, namespace, key, value_json),
                    )

        for plugin_type, instance_id in active_instances.items():
            if instance_id in plugins:
                conn.execute(
                    sql_map.SQLMap.v1.INSERT_ACTIVE_INSTANCE,
                    (plugin_type, instance_id),
                )

    def migrate_json_file_with_backup(self) -> None:
        """迁移成功后，将 data.json 重命名为带时间戳的备份。"""
        if not self.json_file.exists():
            return
        now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S.%f")
        backup_name = f"{self.json_file.stem}.migrated-{now}.bak"
        backup_path = self.data_dir / backup_name
        os.replace(self.json_file, backup_path)

    # -----------------------------------------------------------------------
    # CRUD：插件管理
    # -----------------------------------------------------------------------

    def plugin_exists(self, instance_id: str) -> bool:
        conn = self._connect()
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_PLUGIN_EXISTS, (instance_id,))
        return cur.fetchone() is not None

    def register_plugin(self, instance_id: str, plugin_type: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                sql_map.SQLMap.v1.INSERT_PLUGIN,
                (instance_id, plugin_type, 0),
            )
        except sqlite3.IntegrityError as e:
            raise SQLiteBackendError(f"插件 {instance_id} 已存在") from e

    def unregister_plugin(self, instance_id: str) -> None:
        conn = self._connect()
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_PLUGIN_EXISTS, (instance_id,))
        if cur.fetchone() is None:
            raise SQLiteBackendError(f"插件 {instance_id} 不存在")
        # 外键级联会自动清理 plugin_data 和 active_instances
        conn.execute(sql_map.SQLMap.v1.DELETE_PLUGIN, (instance_id,))
        self._value_cache.invalidate_plugin(instance_id)

    def get_plugin_type(self, instance_id: str) -> Optional[str]:
        conn = self._connect()
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_PLUGIN_TYPE, (instance_id,))
        row = cur.fetchone()
        return row[0] if row else None

    # -----------------------------------------------------------------------
    # CRUD：活跃实例
    # -----------------------------------------------------------------------

    def get_active_instance(self, plugin_type: str) -> Optional[str]:
        conn = self._connect()
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ACTIVE_INSTANCE, (plugin_type,))
        row = cur.fetchone()
        return row[0] if row else None

    def set_active_instance(self, instance_id: str) -> None:
        plugin_type = self.get_plugin_type(instance_id)
        if plugin_type is None:
            raise SQLiteBackendError(f"插件 {instance_id} 不存在")

        conn = self._connect()
        with self.transaction() as txn:
            txn.execute(
                sql_map.SQLMap.v1.UPDATE_PLUGINS_INACTIVE_BY_TYPE,
                (plugin_type, instance_id),
            )
            txn.execute(
                sql_map.SQLMap.v1.UPDATE_PLUGIN_ACTIVE,
                (instance_id,),
            )
            txn.execute(
                sql_map.SQLMap.v1.UPSERT_ACTIVE_INSTANCE,
                (plugin_type, instance_id),
            )

    # -----------------------------------------------------------------------
    # CRUD：插件数据
    # -----------------------------------------------------------------------

    def get_plugin_data(
        self, instance_id: str, namespace: str, key: str, default: Any = None
    ) -> Any:
        cache_key = (instance_id, namespace, key)
        cached = self._value_cache.get(cache_key)
        if cached is not _LRUCache.MISSING:
            return copy.deepcopy(cached)

        conn = self._connect()
        cur = conn.execute(
            sql_map.SQLMap.v1.SELECT_PLUGIN_DATA,
            (instance_id, namespace, key),
        )
        row = cur.fetchone()
        if row is None:
            return default
        value = _deserialize(row[0])
        self._value_cache.put(cache_key, value)
        return copy.deepcopy(value)

    def set_plugin_data(
        self, instance_id: str, namespace: str, key: str, value: Any
    ) -> None:
        value_json = _serialize(value)
        conn = self._connect()
        conn.execute(
            sql_map.SQLMap.v1.UPSERT_PLUGIN_DATA,
            (instance_id, namespace, key, value_json),
        )
        self._value_cache.invalidate((instance_id, namespace, key))

    def get_all_plugin_data(self, instance_id: str, namespace: str) -> Dict[str, Any]:
        conn = self._connect()
        cur = conn.execute(
            sql_map.SQLMap.v1.SELECT_ALL_PLUGIN_DATA,
            (instance_id, namespace),
        )
        result: Dict[str, Any] = {}
        for key, value_json in cur.fetchall():
            cache_key = (instance_id, namespace, key)
            cached = self._value_cache.get(cache_key)
            if cached is not _LRUCache.MISSING:
                result[key] = copy.deepcopy(cached)
            else:
                value = _deserialize(value_json)
                self._value_cache.put(cache_key, value)
                result[key] = copy.deepcopy(value)
        return result

    # -----------------------------------------------------------------------
    # 工具：全量加载/保存
    # -----------------------------------------------------------------------

    def load_data(self) -> Dict[str, Any]:
        """从 SQLite 重建完整字典结构，同时填充 LRU 缓存。"""
        conn = self._connect()
        data: Dict[str, Any] = {"plugins": {}, "active_instances": {}}

        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ALL_PLUGINS)
        for instance_id, plugin_type, active in cur.fetchall():
            data["plugins"][instance_id] = {
                "type": plugin_type,
                "active": bool(active),
                "private": {},
                "public": {},
            }

        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ALL_PLUGIN_DATA_FOR_LOAD)
        for instance_id, namespace, key, value_json in cur.fetchall():
            value = _deserialize(value_json)
            self._value_cache.put((instance_id, namespace, key), value)
            if instance_id in data["plugins"]:
                data["plugins"][instance_id][namespace][key] = copy.deepcopy(value)

        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ALL_ACTIVE_INSTANCES)
        for plugin_type, instance_id in cur.fetchall():
            data["active_instances"][plugin_type] = instance_id

        return data

    def save_data(self, data: Dict[str, Any]) -> None:
        """将完整字典结构写回 SQLite。"""
        conn = self._connect()
        with self.transaction() as txn:
            # 先清空子表，再清空父表
            txn.execute(sql_map.SQLMap.v1.DELETE_ALL_PLUGIN_DATA)
            txn.execute(sql_map.SQLMap.v1.DELETE_ALL_ACTIVE_INSTANCES)
            txn.execute(sql_map.SQLMap.v1.DELETE_ALL_PLUGINS)

            plugins = data.get("plugins", {})
            active_instances = data.get("active_instances", {})

            for instance_id, plugin_info in plugins.items():
                plugin_type = plugin_info.get("type", "")
                active = 1 if plugin_info.get("active", False) else 0
                txn.execute(
                    sql_map.SQLMap.v1.INSERT_PLUGIN,
                    (instance_id, plugin_type, active),
                )
                for namespace in ("private", "public"):
                    ns_data = plugin_info.get(namespace, {})
                    for key, value in ns_data.items():
                        value_json = _serialize(value)
                        txn.execute(
                            sql_map.SQLMap.v1.INSERT_PLUGIN_DATA,
                            (instance_id, namespace, key, value_json),
                        )

            for plugin_type, instance_id in active_instances.items():
                txn.execute(
                    sql_map.SQLMap.v1.INSERT_ACTIVE_INSTANCE,
                    (plugin_type, instance_id),
                )

        self._value_cache.clear()

    def get_all_plugins(self) -> Dict[str, Dict[str, Any]]:
        """查询所有插件的完整信息（专用查询，不经 load_data 全量重建与 LRU 缓存）。"""
        conn = self._connect()
        plugins: Dict[str, Dict[str, Any]] = {}

        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ALL_PLUGINS)
        for instance_id, plugin_type, active in cur.fetchall():
            plugins[instance_id] = {
                "type": plugin_type,
                "active": bool(active),
                "private": {},
                "public": {},
            }

        cur = conn.execute(sql_map.SQLMap.v1.SELECT_ALL_PLUGIN_DATA_FOR_LOAD)
        for instance_id, namespace, key, value_json in cur.fetchall():
            if instance_id in plugins:
                # _deserialize 返回全新对象，返回值不与缓存共享引用
                plugins[instance_id][namespace][key] = _deserialize(value_json)

        return plugins

    def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """按 instance_id 查询单个插件的完整信息（点查，避免全表扫描）。"""
        conn = self._connect()
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_PLUGIN_BY_ID, (instance_id,))
        row = cur.fetchone()
        if row is None:
            return None
        _, plugin_type, active = row
        info: Dict[str, Any] = {
            "type": plugin_type,
            "active": bool(active),
            "private": {},
            "public": {},
        }
        cur = conn.execute(sql_map.SQLMap.v1.SELECT_PLUGIN_DATA_BY_ID, (instance_id,))
        for namespace, key, value_json in cur.fetchall():
            info[namespace][key] = _deserialize(value_json)
        return info

    def clear_caches(self) -> None:
        """清空后端内部缓存（当前为 LRU 反序列化缓存）。"""
        self._value_cache.clear()

    def reset_all_data(self) -> None:
        self.save_data({"plugins": {}, "active_instances": {}})
        self._value_cache.clear()
