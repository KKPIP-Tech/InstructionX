"""SQL 映射模块

该模块用于定义数据库表的 SQL 语句映射，目前为占位实现。

Note:
    实际的数据库操作已通过 DataProvider 的 JSON 文件存储实现。
    该模块可用于未来扩展 SQLite 等数据库时的 SQL 定义。

Classes:
    SQLMap: SQL 语句映射类，提供各版本数据库表的创建语句。
"""

import sys
from typing import TYPE_CHECKING

# 类型检查时导入，避免循环依赖
if TYPE_CHECKING:
    from typing import List, Tuple


class SQLMap:
    """SQL 语句映射类

    负责提供数据库表的 SQL 创建语句，支持版本化管理。
    每个版本对应不同的数据库 schema，用于数据迁移。
    """

    @staticmethod
    def version_1_main_table() -> str:
        """获取版本 1 的主表 SQL 创建语句

        Returns:
            str: 空字符串，当前版本未定义主表
        """
        return ''