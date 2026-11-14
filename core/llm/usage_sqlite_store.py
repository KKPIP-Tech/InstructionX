"""LLM 用量记录的 SQLite 增量存储，提供事务、迁移与恢复语义。"""

import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, List

from core.data.schema_migrations import LLM_STORAGE_SCHEMA_VERSION


logger = logging.getLogger(__name__)


class UsageStorageError(Exception):
    """用量数据库初始化、迁移或写入失败。"""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_records (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    conversation_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cached_tokens INTEGER NOT NULL DEFAULT 0,
    cache_hit INTEGER NOT NULL DEFAULT 0,
    is_stream INTEGER NOT NULL DEFAULT 0,
    duration_ms REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_records(timestamp);
CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_records(provider);
CREATE INDEX IF NOT EXISTS idx_usage_conversation ON usage_records(conversation_id);
CREATE TABLE IF NOT EXISTS usage_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
_INSERT = """
INSERT OR REPLACE INTO usage_records (
    id, timestamp, conversation_id, provider, model, input_tokens,
    output_tokens, total_tokens, cached_tokens, cache_hit, is_stream, duration_ms
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""
_FIELDS = (
    "id", "timestamp", "conversation_id", "provider", "model",
    "input_tokens", "output_tokens", "total_tokens", "cached_tokens",
    "cache_hit", "is_stream", "duration_ms",
)


class UsageSQLiteStore:
    """以单连接和可重入锁执行逐条事务，durable 模式使用 FULL 同步。"""

    def __init__(self, db_path, durable: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        try:
            self._initialize(durable)
        except Exception as exc:
            self._conn.close()
            if isinstance(exc, UsageStorageError):
                raise
            raise UsageStorageError(f"用量数据库初始化失败: {exc}") from exc

    def _initialize(self, durable: bool) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=" + ("FULL" if durable else "NORMAL"))
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR REPLACE INTO usage_metadata(key, value) VALUES('schema_version', ?)",
            (str(LLM_STORAGE_SCHEMA_VERSION),),
        )

    def append(self, record: Dict) -> None:
        """在独立事务中追加一条记录，失败回滚并抛出 UsageStorageError。"""
        values = self._record_values(record)
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(_INSERT, values)
                self._conn.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback()
                raise UsageStorageError(f"用量记录写入失败: {exc}") from exc

    def import_records(self, records: List[Dict]) -> None:
        """在一个事务中导入旧 JSON 全部记录，任何失败均整体回滚。"""
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                for record in records:
                    self._conn.execute(_INSERT, self._record_values(record))
                self._conn.execute("COMMIT")
            except sqlite3.Error as exc:
                self._rollback()
                raise UsageStorageError(f"旧用量记录迁移失败: {exc}") from exc

    def load_records(self) -> List[Dict]:
        """按插入顺序返回全部记录字典。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, timestamp, conversation_id, provider, model, "
                "input_tokens, output_tokens, total_tokens, cached_tokens, "
                "cache_hit, is_stream, duration_ms FROM usage_records ORDER BY rowid"
            ).fetchall()
        return [dict(zip(_FIELDS, row)) for row in rows]

    def delete_before(self, timestamp: str) -> int:
        """删除早于指定时间戳的记录并返回删除数。"""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM usage_records WHERE timestamp < ?", (timestamp,)
            )
            return cursor.rowcount

    def flush(self) -> None:
        """执行 WAL 被动检查点和快速完整性检查，失败显式抛出。"""
        with self._lock:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                result = self._conn.execute("PRAGMA quick_check").fetchone()
            except sqlite3.Error as exc:
                raise UsageStorageError(f"用量数据库冲刷失败: {exc}") from exc
        if result and result[0] != "ok":
            raise UsageStorageError(f"用量数据库完整性异常: {result[0]}")

    def close(self) -> None:
        """幂等关闭连接。"""
        with self._lock:
            self._conn.close()

    def _rollback(self) -> None:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error as exc:
            logger.warning("用量事务回滚失败: %s", exc)

    @staticmethod
    def _record_values(record: Dict) -> tuple:
        return (
            record["id"], record["timestamp"], record.get("conversation_id", ""),
            record["provider"], record["model"], record.get("input_tokens", 0),
            record.get("output_tokens", 0), record.get("total_tokens", 0),
            record.get("cached_tokens", 0), int(bool(record.get("cache_hit", False))),
            int(bool(record.get("is_stream", False))), record.get("duration_ms", 0.0),
        )
