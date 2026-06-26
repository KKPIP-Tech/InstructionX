"""SQL 指令版本管理器。

本模块通过 ``SQLMap`` 类按数据库 schema 版本组织所有 SQL 语句。
每个版本以嵌套类的形式存在，例如：

    from core.data.sql_map import SQLMap

    SQLMap.v1.CREATE_TABLES_SCRIPT
    SQLMap.v1.SELECT_SCHEMA_VERSION
    SQLMap.v1.UPSERT_PLUGIN_DATA

当需要新增 schema 版本时，在 ``SQLMap`` 中添加对应的嵌套类（如 ``v2``），
并在 ``core.data.schema_migrations`` 中注册从 ``v1 -> v2`` 的升级函数。

注意：
- ``SQLMap`` 管理的是"SQL 指令集"版本，与数据库中 ``db_metadata.schema_version``
  存储的运行时 schema 版本语义不同，但通常一一对应。
- 修改 SQL 指令时应同步更新 ``SQLMap.CURRENT_VERSION`` 与相关版本的注释。
"""


class SQLMap:
    """SQL 指令版本管理类。

    每个嵌套类（v1 / v2 / ...）对应一个数据库 schema 版本，集中存放该版本
    所需的 PRAGMA、DDL、DML 等 SQL 语句。
    """

    # 当前 SQL 指令集版本号，与 TARGET_SCHEMA_VERSION 保持一致
    CURRENT_VERSION = 1

    class v1:
        """Schema v1 的 SQL 指令集。

        对应 JSON -> SQLite 迁移完成后的基础表结构：
        plugins、plugin_data、active_instances、db_metadata。
        """

        # ------------------------------------------------------------------
        # PRAGMA
        # ------------------------------------------------------------------

        # 启用外键约束，使 plugin_data / active_instances 在父表记录删除时
        # 通过 ON DELETE CASCADE 自动级联清理。
        PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys = ON;"

        # 启用 WAL（Write-Ahead Logging）模式，提升并发读性能并避免写操作阻塞读操作。
        PRAGMA_JOURNAL_MODE_WAL = "PRAGMA journal_mode = WAL;"

        # 设置同步级别为 NORMAL，在性能与持久化之间取得平衡。
        PRAGMA_SYNCHRONOUS_NORMAL = "PRAGMA synchronous = NORMAL;"

        # ------------------------------------------------------------------
        # DDL
        # ------------------------------------------------------------------

        # 创建插件实例主表：每个插件实例有唯一的 instance_id，并记录类型与活跃状态。
        CREATE_TABLE_PLUGINS = """
CREATE TABLE IF NOT EXISTS plugins (
    instance_id TEXT PRIMARY KEY,
    plugin_type TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
);
"""

        # 创建插件键值数据表：每个 (instance_id, namespace, key) 唯一，
        # value_json 存储 orjson 序列化后的 JSON 文本，updated_at 记录更新时间戳。
        CREATE_TABLE_PLUGIN_DATA = """
CREATE TABLE IF NOT EXISTS plugin_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    namespace   TEXT NOT NULL CHECK (namespace IN ('private', 'public')),
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE,
    UNIQUE (instance_id, namespace, key)
);
"""

        # 创建活跃实例映射表：每个 plugin_type 只有一个活跃 instance_id。
        CREATE_TABLE_ACTIVE_INSTANCES = """
CREATE TABLE IF NOT EXISTS active_instances (
    plugin_type TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE
);
"""

        # 创建数据库元数据表：存储 schema_version、migrated_from、migrated_at 等键值对。
        CREATE_TABLE_DB_METADATA = """
CREATE TABLE IF NOT EXISTS db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

        # 创建插件类型索引：加速按 plugin_type 查询插件列表。
        CREATE_INDEX_PLUGINS_TYPE = """
CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);
"""

        # 完整的建表脚本：用于 SQLiteBackend._create_tables() 一次性执行所有 DDL。
        CREATE_TABLES_SCRIPT = """
CREATE TABLE IF NOT EXISTS plugins (
    instance_id TEXT PRIMARY KEY,
    plugin_type TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
);

CREATE TABLE IF NOT EXISTS plugin_data (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    instance_id TEXT NOT NULL,
    namespace   TEXT NOT NULL CHECK (namespace IN ('private', 'public')),
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    updated_at  INTEGER NOT NULL DEFAULT (strftime('%s', 'now')),
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE,
    UNIQUE (instance_id, namespace, key)
);

CREATE TABLE IF NOT EXISTS active_instances (
    plugin_type TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);
"""

        # ------------------------------------------------------------------
        # DML - 元数据
        # ------------------------------------------------------------------

        # 读取当前数据库 schema_version。
        SELECT_SCHEMA_VERSION = """
SELECT value FROM db_metadata WHERE key='schema_version';
"""

        # 插入或更新 db_metadata 中的键值对（用于写入 schema_version / migrated_from 等）。
        UPSERT_METADATA = """
INSERT INTO db_metadata (key, value) VALUES (?, ?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
"""

        # ------------------------------------------------------------------
        # DML - 插件管理
        # ------------------------------------------------------------------

        # 注册新插件实例。
        INSERT_PLUGIN = """
INSERT INTO plugins (instance_id, plugin_type, active) VALUES (?, ?, ?);
"""

        # 查询指定 instance_id 的插件是否存在。
        SELECT_PLUGIN_EXISTS = """
SELECT 1 FROM plugins WHERE instance_id=?;
"""

        # 查询指定 instance_id 的插件类型。
        SELECT_PLUGIN_TYPE = """
SELECT plugin_type FROM plugins WHERE instance_id=?;
"""

        # 删除指定插件实例；外键级联会自动清理其 plugin_data 与 active_instances。
        DELETE_PLUGIN = """
DELETE FROM plugins WHERE instance_id=?;
"""

        # ------------------------------------------------------------------
        # DML - 活跃实例
        # ------------------------------------------------------------------

        # 将某个插件注册为某类型的活跃实例（迁移或初始化时使用）。
        INSERT_ACTIVE_INSTANCE = """
INSERT INTO active_instances (plugin_type, instance_id) VALUES (?, ?);
"""

        # 查询某 plugin_type 当前活跃的 instance_id。
        SELECT_ACTIVE_INSTANCE = """
SELECT instance_id FROM active_instances WHERE plugin_type=?;
"""

        # 将同类型下除目标实例外的其他实例设为非活跃。
        UPDATE_PLUGINS_INACTIVE_BY_TYPE = """
UPDATE plugins SET active=0 WHERE plugin_type=? AND instance_id!=?;
"""

        # 将指定实例设为活跃。
        UPDATE_PLUGIN_ACTIVE = """
UPDATE plugins SET active=1 WHERE instance_id=?;
"""

        # 插入或更新活跃实例映射：同一 plugin_type 只保留一个活跃 instance_id。
        UPSERT_ACTIVE_INSTANCE = """
INSERT INTO active_instances (plugin_type, instance_id) VALUES (?, ?)
ON CONFLICT(plugin_type) DO UPDATE SET instance_id=excluded.instance_id;
"""

        # ------------------------------------------------------------------
        # DML - 插件数据
        # ------------------------------------------------------------------

        # 插入一条插件键值数据（迁移或全量保存时使用）。
        INSERT_PLUGIN_DATA = """
INSERT INTO plugin_data (instance_id, namespace, key, value_json)
VALUES (?, ?, ?, ?);
"""

        # 按 (instance_id, namespace, key) 点查单个 value_json。
        SELECT_PLUGIN_DATA = """
SELECT value_json FROM plugin_data
WHERE instance_id=? AND namespace=? AND key=?;
"""

        # 插入或更新插件键值数据；冲突时更新 value_json 与 updated_at。
        UPSERT_PLUGIN_DATA = """
INSERT INTO plugin_data (instance_id, namespace, key, value_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(instance_id, namespace, key)
DO UPDATE SET value_json=excluded.value_json, updated_at=strftime('%s','now');
"""

        # 查询某插件在指定命名空间下的全部 key-value，按 id 排序以保持写入顺序。
        SELECT_ALL_PLUGIN_DATA = """
SELECT key, value_json FROM plugin_data
WHERE instance_id=? AND namespace=? ORDER BY id;
"""

        # ------------------------------------------------------------------
        # DML - 全量加载
        # ------------------------------------------------------------------

        # 全量加载所有插件实例，按 rowid 排序以保持原始插入顺序。
        SELECT_ALL_PLUGINS = """
SELECT instance_id, plugin_type, active FROM plugins ORDER BY rowid;
"""

        # 全量加载所有插件键值数据，按 rowid 排序。
        SELECT_ALL_PLUGIN_DATA_FOR_LOAD = """
SELECT instance_id, namespace, key, value_json FROM plugin_data ORDER BY rowid;
"""

        # 全量加载所有活跃实例映射，按 rowid 排序。
        SELECT_ALL_ACTIVE_INSTANCES = """
SELECT plugin_type, instance_id FROM active_instances ORDER BY rowid;
"""

        # ------------------------------------------------------------------
        # DML - 全量保存 / 重置
        # ------------------------------------------------------------------

        # 清空 plugin_data 表（save_data / reset_all_data 使用）。
        DELETE_ALL_PLUGIN_DATA = "DELETE FROM plugin_data;"

        # 清空 active_instances 表（save_data / reset_all_data 使用）。
        DELETE_ALL_ACTIVE_INSTANCES = "DELETE FROM active_instances;"

        # 清空 plugins 表（save_data / reset_all_data 使用）。
        DELETE_ALL_PLUGINS = "DELETE FROM plugins;"

        # ------------------------------------------------------------------
        # 事务控制
        # ------------------------------------------------------------------

        # 以 IMMEDIATE 模式开启事务，防止并发写入冲突。
        BEGIN_IMMEDIATE = "BEGIN IMMEDIATE;"

        # 提交事务。
        COMMIT = "COMMIT;"

        # 回滚事务。
        ROLLBACK = "ROLLBACK;"

        # ------------------------------------------------------------------
        # Schema 校验与 introspection
        # ------------------------------------------------------------------

        # 查询 sqlite_master，判断核心业务表（plugins / plugin_data / active_instances）是否已创建。
        SELECT_CORE_TABLES = """
SELECT name FROM sqlite_master WHERE type='table' AND name IN ('plugins', 'plugin_data', 'active_instances');
"""

        # 查询指定表的列定义（用于 _validate_table_schema 校验表结构完整性）。
        # 使用时通过 .format(table=table_name) 替换 {table} 占位符。
        SELECT_TABLE_INFO = "PRAGMA table_info({table});"

    class v2:
        """Schema v2 的 SQL 指令集（示例）。

        当需要升级 schema 时，在此处添加 v1 -> v2 所需的 DDL/DML，
        并在 ``core.data.schema_migrations.MIGRATIONS`` 中注册升级函数。
        """

        # 示例：为 plugins 表新增 description 字段，用于存储插件描述。
        ALTER_PLUGINS_ADD_DESCRIPTION = """
ALTER TABLE plugins ADD COLUMN description TEXT DEFAULT '';
"""
