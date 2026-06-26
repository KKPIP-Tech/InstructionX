"""SQLite schema 版本迁移注册表。

该模块维护数据库 schema 的链式升级脚本注册表。
DataProvider 初始化时通过 SQLiteBackend.ensure_database() 调用此处定义的
TARGET_SCHEMA_VERSION 与 MIGRATIONS，完成数据库创建或链式升级。

用法示例（未来新增 schema 版本时）：

    def upgrade_1_to_2(conn: sqlite3.Connection) -> None:
        conn.execute("ALTER TABLE plugins ADD COLUMN description TEXT DEFAULT '';")

    MIGRATIONS[2] = upgrade_1_to_2
    TARGET_SCHEMA_VERSION = 2

注意：
- 迁移函数签名为 ``Callable[[sqlite3.Connection], None]``。
- 框架会为每次迁移开启独立事务并在成功后统一写入 schema_version，
  迁移函数内部不要再手动提交/回滚。
"""

from typing import Callable, Dict
import sqlite3


MigrationFunc = Callable[[sqlite3.Connection], None]

# 迁移脚本注册表：key 为目标版本号，value 为从 key-1 升级到 key 的函数。
MIGRATIONS: Dict[int, MigrationFunc] = {
    # 1 -> 2: 示例未来升级（新增插件描述字段）
    # 2: upgrade_1_to_2,
}

# 当前代码期望的最新 schema 版本。
TARGET_SCHEMA_VERSION = 1
