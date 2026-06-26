"""SQL 指令版本管理器。

本模块通过 ``SQLMap`` 类按数据库 schema 版本组织所有 SQL 指令。
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
        PRAGMA_FOREIGN_KEYS = "PRAGMA foreign_keys = ON;"
        PRAGMA_JOURNAL_MODE_WAL = "PRAGMA journal_mode = WAL;"
        PRAGMA_SYNCHRONOUS_NORMAL = "PRAGMA synchronous = NORMAL;"

        # ------------------------------------------------------------------
        # DDL
        # ------------------------------------------------------------------
        CREATE_TABLE_PLUGINS = """
CREATE TABLE IF NOT EXISTS plugins (
    instance_id TEXT PRIMARY KEY,
    plugin_type TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0 CHECK (active IN (0, 1))
);
"""

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

        CREATE_TABLE_ACTIVE_INSTANCES = """
CREATE TABLE IF NOT EXISTS active_instances (
    plugin_type TEXT PRIMARY KEY,
    instance_id TEXT NOT NULL,
    FOREIGN KEY (instance_id) REFERENCES plugins(instance_id) ON DELETE CASCADE
);
"""

        CREATE_TABLE_DB_METADATA = """
CREATE TABLE IF NOT EXISTS db_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

        CREATE_INDEX_PLUGINS_TYPE = """
CREATE INDEX IF NOT EXISTS idx_plugins_type ON plugins(plugin_type);
"""

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
        SELECT_SCHEMA_VERSION = """
SELECT value FROM db_metadata WHERE key='schema_version';
"""

        UPSERT_METADATA = """
INSERT INTO db_metadata (key, value) VALUES (?, ?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value;
"""

        # ------------------------------------------------------------------
        # DML - 插件管理
        # ------------------------------------------------------------------
        INSERT_PLUGIN = """
INSERT INTO plugins (instance_id, plugin_type, active) VALUES (?, ?, ?);
"""

        SELECT_PLUGIN_EXISTS = """
SELECT 1 FROM plugins WHERE instance_id=?;
"""

        SELECT_PLUGIN_TYPE = """
SELECT plugin_type FROM plugins WHERE instance_id=?;
"""

        DELETE_PLUGIN = """
DELETE FROM plugins WHERE instance_id=?;
"""

        # ------------------------------------------------------------------
        # DML - 活跃实例
        # ------------------------------------------------------------------
        INSERT_ACTIVE_INSTANCE = """
INSERT INTO active_instances (plugin_type, instance_id) VALUES (?, ?);
"""

        SELECT_ACTIVE_INSTANCE = """
SELECT instance_id FROM active_instances WHERE plugin_type=?;
"""

        UPDATE_PLUGINS_INACTIVE_BY_TYPE = """
UPDATE plugins SET active=0 WHERE plugin_type=? AND instance_id!=?;
"""

        UPDATE_PLUGIN_ACTIVE = """
UPDATE plugins SET active=1 WHERE instance_id=?;
"""

        UPSERT_ACTIVE_INSTANCE = """
INSERT INTO active_instances (plugin_type, instance_id) VALUES (?, ?)
ON CONFLICT(plugin_type) DO UPDATE SET instance_id=excluded.instance_id;
"""

        # ------------------------------------------------------------------
        # DML - 插件数据
        # ------------------------------------------------------------------
        INSERT_PLUGIN_DATA = """
INSERT INTO plugin_data (instance_id, namespace, key, value_json)
VALUES (?, ?, ?, ?);
"""

        SELECT_PLUGIN_DATA = """
SELECT value_json FROM plugin_data
WHERE instance_id=? AND namespace=? AND key=?;
"""

        UPSERT_PLUGIN_DATA = """
INSERT INTO plugin_data (instance_id, namespace, key, value_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(instance_id, namespace, key)
DO UPDATE SET value_json=excluded.value_json, updated_at=strftime('%s','now');
"""

        SELECT_ALL_PLUGIN_DATA = """
SELECT key, value_json FROM plugin_data
WHERE instance_id=? AND namespace=? ORDER BY id;
"""

        # ------------------------------------------------------------------
        # DML - 全量加载
        # ------------------------------------------------------------------
        SELECT_ALL_PLUGINS = """
SELECT instance_id, plugin_type, active FROM plugins ORDER BY rowid;
"""

        SELECT_ALL_PLUGIN_DATA_FOR_LOAD = """
SELECT instance_id, namespace, key, value_json FROM plugin_data ORDER BY rowid;
"""

        SELECT_ALL_ACTIVE_INSTANCES = """
SELECT plugin_type, instance_id FROM active_instances ORDER BY rowid;
"""

        # ------------------------------------------------------------------
        # DML - 全量保存 / 重置
        # ------------------------------------------------------------------
        DELETE_ALL_PLUGIN_DATA = "DELETE FROM plugin_data;"
        DELETE_ALL_ACTIVE_INSTANCES = "DELETE FROM active_instances;"
        DELETE_ALL_PLUGINS = "DELETE FROM plugins;"

        # ------------------------------------------------------------------
        # 事务控制
        # ------------------------------------------------------------------
        BEGIN_IMMEDIATE = "BEGIN IMMEDIATE;"
        COMMIT = "COMMIT;"
        ROLLBACK = "ROLLBACK;"

        # ------------------------------------------------------------------
        # Schema 校验与 introspection
        # ------------------------------------------------------------------
        SELECT_CORE_TABLES = """
SELECT name FROM sqlite_master WHERE type='table' AND name IN ('plugins', 'plugin_data', 'active_instances');
"""

        SELECT_TABLE_INFO = "PRAGMA table_info({table});"

    class v2:
        """Schema v2 的 SQL 指令集（示例）。

        当需要升级 schema 时，在此处添加 v1 -> v2 所需的 DDL/DML，
        并在 ``core.data.schema_migrations.MIGRATIONS`` 中注册升级函数。
        """

        # 示例：为 plugins 表新增 description 字段
        ALTER_PLUGINS_ADD_DESCRIPTION = """
ALTER TABLE plugins ADD COLUMN description TEXT DEFAULT '';
"""
