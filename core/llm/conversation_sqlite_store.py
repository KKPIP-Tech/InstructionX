"""会话与消息的 SQLite 增量存储，按轮次提交并保留明确写回执。"""

import json
import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from core.data.schema_migrations import LLM_STORAGE_SCHEMA_VERSION
from .types import Conversation


logger = logging.getLogger(__name__)


class ConversationStorageError(Exception):
    """会话数据库初始化、迁移或轮次写入失败。"""


@dataclass(frozen=True, slots=True)
class WriteReceipt:
    """会话轮次写回执。"""

    conversation_id: str
    message_count: int
    durable: bool


_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    system_prompt TEXT,
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content_json TEXT NOT NULL,
    FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation
ON conversation_messages(conversation_id, id);
CREATE TABLE IF NOT EXISTS conversation_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""
_UPSERT = """
INSERT INTO conversations (
    id, created_at, updated_at, system_prompt, provider, model,
    metadata_json, total_tokens, total_cost
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(id) DO UPDATE SET
    updated_at=excluded.updated_at,
    system_prompt=excluded.system_prompt,
    provider=excluded.provider,
    model=excluded.model,
    metadata_json=excluded.metadata_json,
    total_tokens=excluded.total_tokens,
    total_cost=excluded.total_cost
"""


class ConversationStore:
    """以事务维护会话元数据和有序消息，durable 模式使用 FULL 同步。"""

    def __init__(self, db_path, durable: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.durable = durable
        self._lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        try:
            self._initialize(durable)
        except Exception as exc:
            self._conn.close()
            raise ConversationStorageError(f"会话数据库初始化失败: {exc}") from exc

    def _initialize(self, durable: bool) -> None:
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=" + ("FULL" if durable else "NORMAL"))
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR REPLACE INTO conversation_metadata(key, value) VALUES('schema_version', ?)",
            (str(LLM_STORAGE_SCHEMA_VERSION),),
        )

    def create_conversation(self, conversation: Conversation) -> None:
        """创建或更新不含新增消息的会话元数据。"""
        self._upsert(conversation.to_dict())

    def import_conversations(self, conversations: List[Conversation]) -> None:
        """在单个事务中迁移全部旧会话，任何失败均整体回滚。"""
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                for conversation in conversations:
                    data = conversation.to_dict()
                    self._upsert(data)
                    for message in conversation.messages:
                        self._conn.execute(
                            "INSERT INTO conversation_messages(conversation_id, role, content_json) VALUES (?, ?, ?)",
                            (conversation.id, message.get("role", ""), json.dumps(message, ensure_ascii=False)),
                        )
                self._conn.execute("COMMIT")
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self._rollback()
                raise ConversationStorageError(f"旧会话批量迁移失败: {exc}") from exc

    def append_turn(self, conversation_id: str, turn: Dict) -> WriteReceipt:
        """在一个事务中更新会话统计并追加完整轮次消息。"""
        data = turn["conversation"]
        messages = turn.get("messages", [])
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._upsert(data)
                for message in messages:
                    self._conn.execute(
                        "INSERT INTO conversation_messages(conversation_id, role, content_json) VALUES (?, ?, ?)",
                        (conversation_id, message.get("role", ""), json.dumps(message, ensure_ascii=False)),
                    )
                self._conn.execute("COMMIT")
            except (sqlite3.Error, TypeError, ValueError) as exc:
                self._rollback()
                raise ConversationStorageError(f"会话轮次写入失败: {exc}") from exc
        return WriteReceipt(conversation_id, len(messages), self.durable)

    def load_conversations(self) -> Dict[str, Conversation]:
        """从数据库恢复全部会话及有序消息。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, created_at, updated_at, system_prompt, provider, model, "
                "metadata_json, total_tokens, total_cost FROM conversations ORDER BY created_at"
            ).fetchall()
            result = {}
            for row in rows:
                data = self._conversation_dict(row)
                messages = self._conn.execute(
                    "SELECT content_json FROM conversation_messages WHERE conversation_id=? ORDER BY id",
                    (data["id"],),
                ).fetchall()
                data["messages"] = [json.loads(item[0]) for item in messages]
                result[data["id"]] = Conversation.from_dict(data)
        return result

    def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话及级联消息，返回是否存在删除记录。"""
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM conversations WHERE id=?", (conversation_id,)
            )
            return cursor.rowcount > 0

    def flush(self) -> None:
        """执行 WAL 被动检查点和快速完整性检查。"""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            result = self._conn.execute("PRAGMA quick_check").fetchone()
        if result and result[0] != "ok":
            raise ConversationStorageError(f"会话数据库完整性异常: {result[0]}")

    def close(self) -> None:
        """幂等关闭数据库连接。"""
        with self._lock:
            if self._closed:
                return
            self._conn.close()
            self._closed = True

    def _upsert(self, data: Dict) -> None:
        self._conn.execute(_UPSERT, self._conversation_values(data))

    def _rollback(self) -> None:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.Error as exc:
            logger.warning("会话事务回滚失败: %s", exc)

    @staticmethod
    def _conversation_values(data: Dict) -> tuple:
        return (
            data["id"], data["created_at"], data["updated_at"],
            data.get("system_prompt"), data.get("provider", ""), data.get("model", ""),
            json.dumps(data.get("metadata", {}), ensure_ascii=False),
            data.get("total_tokens", 0), data.get("total_cost", 0.0),
        )

    @staticmethod
    def _conversation_dict(row: tuple) -> Dict:
        return {
            "id": row[0], "created_at": row[1], "updated_at": row[2],
            "system_prompt": row[3], "provider": row[4], "model": row[5],
            "metadata": json.loads(row[6]), "total_tokens": row[7], "total_cost": row[8],
        }
