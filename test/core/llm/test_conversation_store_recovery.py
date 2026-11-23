"""会话 SQLite 增量持久化、迁移与并发顺序测试。"""

import json
import threading
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.llm.conversation_manager import ConversationManager
from core.llm.conversation_sqlite_store import ConversationStorageError, ConversationStore
from core.llm.provider_interface import ChatResponse
from core.llm.types import Conversation


def _conversation(identifier="c1"):
    now = datetime.now()
    return Conversation(id=identifier, created_at=now, updated_at=now)


def test_incremental_turn_append_and_reload(tmp_path):
    """按轮次追加后只读增量消息，统计与消息顺序在重载后保持。"""
    store = ConversationStore(tmp_path / "conversations.db")
    conversation = _conversation()
    store.create_conversation(conversation)
    conversation.add_message("user", "你好")
    conversation.add_message("assistant", "您好")
    receipt = store.append_turn(conversation.id, {
        "conversation": conversation.to_dict(),
        "messages": conversation.messages,
    })
    assert receipt.message_count == 2
    loaded = store.load_conversations()["c1"]
    assert [message["content"] for message in loaded.messages] == ["你好", "您好"]
    assert loaded.total_tokens == 0
    store.close()


def test_json_migration_backup_and_no_full_rewrite(tmp_path):
    """旧会话 JSON 迁移后保留备份，后续写轮次不再全量写 JSON。"""
    json_file = tmp_path / "conversations.json"
    conversation = _conversation("old")
    json_file.write_text(json.dumps({"version": 1, "conversations": [conversation.to_dict()]}), encoding="utf-8")
    manager = ConversationManager(storage_path=json_file)
    assert manager.get_conversation("old") is not None
    assert list(tmp_path.glob("conversations.migrated-*.bak"))
    manager._llm = MagicMock()
    manager._llm.chat.return_value = ChatResponse(content="回复", model="m")
    manager.send_message("old", "新消息")
    assert not json_file.exists()
    assert manager.get_conversation("old").messages[-1]["content"] == "回复"


def test_concurrent_same_conversation_keeps_turn_order(tmp_path):
    """同会话并发发送必须按完整用户/助手轮次串行，不得交叉历史。"""
    manager = ConversationManager(storage_path=tmp_path / "conversations.json")
    conversation_id = manager.create_conversation()
    manager._llm = MagicMock()

    def chat(messages, **kwargs):
        content = messages[-1].content
        return ChatResponse(content=f"回复-{content}", model="m")

    manager._llm.chat.side_effect = chat
    threads = [
        threading.Thread(target=manager.send_message, args=(conversation_id, f"问题-{index}"))
        for index in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    messages = manager.get_conversation(conversation_id).messages
    assert len(messages) == 16
    for index in range(0, 16, 2):
        user = messages[index]["content"]
        assert user.startswith("问题-")
        assert messages[index + 1]["content"] == f"回复-{user}"


def test_corrupted_conversation_json_fails_closed(tmp_path):
    """损坏会话文件不得被当成空会话覆盖，必须显式进入恢复错误。"""
    json_file = tmp_path / "conversations.json"
    json_file.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ConversationStorageError):
        ConversationManager(storage_path=json_file)
    assert json_file.exists()
    assert list(tmp_path.glob("conversations.corrupt-*.bak"))


def test_failed_conversation_migration_rolls_back_new_database(tmp_path):
    """整批会话迁移失败时保留原 JSON 并清理本次新库，允许完整重试。"""
    json_file = tmp_path / "conversations.json"
    json_file.write_text(json.dumps({"version": 1, "conversations": [_conversation("old").to_dict()]}), encoding="utf-8")
    with patch.object(ConversationStore, "import_conversations", side_effect=ConversationStorageError("迁移中断")):
        with pytest.raises(ConversationStorageError):
            ConversationManager(storage_path=json_file)
    assert json_file.exists()
    assert not (tmp_path / "conversations.db").exists()
    manager = ConversationManager(storage_path=json_file)
    assert manager.get_conversation("old") is not None


def test_storage_failure_is_not_silent(tmp_path):
    """轮次写库失败必须向调用方抛出，不能只记录日志后伪装保存成功。"""
    manager = ConversationManager(storage_path=tmp_path / "conversations.json")
    conversation_id = manager.create_conversation()
    manager._llm = MagicMock()
    manager._llm.chat.return_value = ChatResponse(content="回复", model="m")
    manager._store.append_turn = MagicMock(side_effect=OSError("磁盘满"))
    with pytest.raises(OSError, match="磁盘满"):
        manager.send_message(conversation_id, "问题")
