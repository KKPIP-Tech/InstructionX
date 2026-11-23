"""用量 SQLite 持久化、迁移和写失败恢复测试。"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from core.llm.types import UsageRecord
from core.llm.usage_record_store import UsageRecordStore
from core.llm.usage_sqlite_store import UsageSQLiteStore, UsageStorageError


@pytest.fixture(autouse=True)
def reset_usage_store_singleton():
    """每个用例前后重置用量单例，避免临时目录和初始化状态串扰。"""
    UsageRecordStore._instance = None
    yield
    UsageRecordStore._instance = None


def _record(index=0):
    return UsageRecord(
        id=f"r{index}", timestamp=datetime.now(timezone.utc),
        conversation_id="c1", provider="test", model="m1",
        input_tokens=1, output_tokens=2, total_tokens=3,
        cached_tokens=0, cache_hit=False, is_stream=False, duration_ms=1.0,
    )


def _seed_json(path: Path, count=2):
    path.write_text(json.dumps({
        "version": 1,
        "records": [_record(index).to_dict() for index in range(count)],
    }), encoding="utf-8")


def test_sqlite_migration_preserves_json_backup_and_appends(tmp_path):
    """旧 JSON 原子迁移后保留备份，后续记录只增量写 SQLite。"""
    json_file = tmp_path / "llm_usage.json"
    _seed_json(json_file)
    store = UsageRecordStore(data_dir=tmp_path)
    assert len(store.get_records()) == 2
    assert not json_file.exists()
    assert list(tmp_path.glob("llm_usage.migrated-*.bak"))
    store.record(_record(9)
    )
    backend = UsageSQLiteStore(tmp_path / "llm_usage.db")
    assert len(backend.load_records()) == 3
    backend.close()


def test_ten_thousand_records_never_rewrite_json(tmp_path):
    """一万条记录追加不得调用 JSON 全量序列化写回。"""
    store = UsageRecordStore(data_dir=tmp_path)
    with patch("json.dump", side_effect=AssertionError("禁止全量 JSON 写回")):
        for index in range(10000):
            store.record(_record(index))
    assert len(store.get_records()) == 10000
    assert (tmp_path / "llm_usage.db").exists()


def test_sqlite_write_failure_is_not_reported_as_success(tmp_path):
    """SQLite 写失败必须抛出且不得向内存缓存伪装成功，恢复后可重试。"""
    store = UsageRecordStore(data_dir=tmp_path)
    with patch.object(store._sqlite_store, "append", side_effect=OSError("磁盘满")):
        with pytest.raises(OSError, match="磁盘满"):
            store.record(_record(1)
            )
    assert not store.get_records()
    store.record(_record(1))
    assert len(store.get_records()) == 1


def test_json_writer_failure_keeps_dirty_and_flush_retries(tmp_path):
    """旧 JSON 兼容路径写失败后保留脏标记，flush 能再次尝试并成功。"""
    store = UsageRecordStore(data_dir=tmp_path)
    store._records_file = tmp_path / "legacy-custom.json"
    attempts = []
    original = store._write_to_disk

    def fail_once(data):
        attempts.append(data)
        if len(attempts) == 1:
            raise OSError("模拟写盘失败")
        original(data)

    store._write_to_disk = fail_once
    store.record(_record(2))
    store.flush(timeout=2)
    assert attempts
    assert store._cache_dirty is False
    assert json.loads(store._records_file.read_text(encoding="utf-8"))["records"][0]["id"] == "r2"
    assert store.flush_detailed().success


def test_corrupted_json_is_preserved_and_migration_fails_closed(tmp_path):
    """损坏 JSON 不得被当成空用量覆盖，原文件保留且初始化显式失败。"""
    json_file = tmp_path / "llm_usage.json"
    json_file.write_text("{broken", encoding="utf-8")
    with pytest.raises(UsageStorageError):
        UsageRecordStore(data_dir=tmp_path)
    assert json_file.exists()
    assert list(tmp_path.glob("llm_usage.corrupt-*.bak"))


def test_failed_migration_can_retry_from_original_json(tmp_path):
    """新建库迁移失败后必须可读取原 JSON 重试，不得留下部分新库。"""
    json_file = tmp_path / "llm_usage.json"
    _seed_json(json_file)
    with patch.object(UsageSQLiteStore, "import_records", side_effect=UsageStorageError("迁移中断")):
        with pytest.raises(UsageStorageError):
            UsageRecordStore(data_dir=tmp_path)
    assert json_file.exists()
    assert not (tmp_path / "llm_usage.db").exists()
    UsageRecordStore._instance = None
    store = UsageRecordStore(data_dir=tmp_path)
    assert len(store.get_records()) == 2


def test_flush_detailed_reports_success(tmp_path):
    """结构化 flush 报告包含成功、待写数量和错误字段。"""
    store = UsageRecordStore(data_dir=tmp_path)
    store.record(_record(3))
    report = store.flush_detailed()
    assert report.success
    assert report.pending == 0
    assert report.error == ""
