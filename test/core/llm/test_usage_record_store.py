"""UsageRecordStore 单元测试

覆盖用量记录的保存、查询、聚合、裁剪及异步持久化行为。
"""

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.llm.types import UsageRecord
from core.llm.usage_record_store import UsageRecordStore, get_usage_record_store


@pytest.fixture
def store(tmp_path, mocker):
    """返回使用临时文件路径的 UsageRecordStore 实例。"""
    records_file = tmp_path / "llm_usage.json"
    records_file.write_text(json.dumps({"version": 1, "records": []}), encoding="utf-8")

    instance = UsageRecordStore()
    instance._data_dir = tmp_path
    instance._records_file = records_file
    instance._cache = {"version": 1, "records": []}
    instance._cache_dirty = False
    instance._pending_write = False
    yield instance


def _wait_for_write(store):
    """等待异步写入线程完成。"""
    for _ in range(50):
        if not store._pending_write:
            break
        time.sleep(0.01)


def _make_record(provider="minimax", model="m1", conversation_id="c1",
                 input_tokens=10, output_tokens=5, total_tokens=15,
                 timestamp=None, record_id="rid"):
    return UsageRecord(
        id=record_id,
        timestamp=timestamp or datetime.now(timezone.utc),
        conversation_id=conversation_id,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_tokens=0,
        cache_hit=False,
        is_stream=False,
        duration_ms=100.0,
    )


class TestSingleton:
    def test_get_usage_record_store_returns_same_instance(self):
        s1 = get_usage_record_store()
        s2 = get_usage_record_store()
        assert s1 is s2


class TestRecord:
    def test_record_appends_to_cache(self, store):
        store.record(_make_record(record_id="r1"))
        assert len(store._cache["records"]) == 1
        assert store._cache["records"][0]["id"] == "r1"

    def test_record_generates_id_when_missing(self, store):
        rec = _make_record(record_id="")
        store.record(rec)
        _wait_for_write(store)
        assert store._cache["records"][0]["id"]

    def test_record_persists_to_disk(self, store):
        store.record(_make_record(record_id="r1"))
        _wait_for_write(store)

        data = json.loads(store._records_file.read_text(encoding="utf-8"))
        assert len(data["records"]) == 1
        assert data["records"][0]["id"] == "r1"


class TestGetRecords:
    def test_get_records_without_filters(self, store):
        store.record(_make_record(record_id="r1"))
        store.record(_make_record(record_id="r2"))
        _wait_for_write(store)

        records = store.get_records()
        assert len(records) == 2

    def test_get_records_filters_by_provider(self, store):
        store.record(_make_record(provider="minimax", record_id="r1"))
        store.record(_make_record(provider="glm", record_id="r2"))
        _wait_for_write(store)

        records = store.get_records(provider="minimax")
        assert len(records) == 1
        assert records[0].provider == "minimax"

    def test_get_records_filters_by_conversation_id(self, store):
        store.record(_make_record(conversation_id="c1", record_id="r1"))
        store.record(_make_record(conversation_id="c2", record_id="r2"))
        _wait_for_write(store)

        records = store.get_records(conversation_id="c1")
        assert len(records) == 1
        assert records[0].conversation_id == "c1"

    def test_get_records_filters_by_time_range(self, store):
        now = datetime.now(timezone.utc)
        old = _make_record(timestamp=now - timedelta(hours=2), record_id="r1")
        new = _make_record(timestamp=now, record_id="r2")
        store.record(old)
        store.record(new)
        _wait_for_write(store)

        records = store.get_records(start_time=now - timedelta(minutes=30))
        assert len(records) == 1
        assert records[0].id == "r2"

    def test_get_records_pagination(self, store):
        for i in range(5):
            store.record(_make_record(record_id=f"r{i}"))
        _wait_for_write(store)

        records = store.get_records(limit=2, offset=1)
        assert len(records) == 2
        assert records[0].id == "r1"
        assert records[1].id == "r2"


class TestAggregate:
    def test_aggregate_by_provider(self, store):
        store.record(_make_record(provider="minimax", input_tokens=10, output_tokens=5, record_id="r1"))
        store.record(_make_record(provider="minimax", input_tokens=20, output_tokens=10, record_id="r2"))
        store.record(_make_record(provider="glm", input_tokens=5, output_tokens=5, record_id="r3"))
        _wait_for_write(store)

        result = store.aggregate(group_by="provider")
        groups = {g["group_key"]: g for g in result["groups"]}
        assert groups["minimax"]["total_requests"] == 2
        assert groups["minimax"]["total_input_tokens"] == 30
        assert groups["glm"]["total_requests"] == 1

    def test_aggregate_by_day(self, store):
        today = datetime.now(timezone.utc)
        yesterday = today - timedelta(days=1)
        store.record(_make_record(timestamp=today, record_id="r1"))
        store.record(_make_record(timestamp=yesterday, record_id="r2"))
        _wait_for_write(store)

        result = store.aggregate(group_by="day")
        assert len(result["groups"]) == 2


class TestTotalStats:
    def test_get_total_stats(self, store):
        store.record(_make_record(input_tokens=10, output_tokens=5, total_tokens=15, record_id="r1"))
        store.record(_make_record(input_tokens=20, output_tokens=10, total_tokens=30, record_id="r2"))
        _wait_for_write(store)

        stats = store.get_total_stats()
        assert stats["total_requests"] == 2
        assert stats["total_input_tokens"] == 30
        assert stats["total_output_tokens"] == 15
        assert stats["total_tokens"] == 45
        assert stats["avg_duration_ms"] == 100.0


class TestPrune:
    def test_prune_removes_old_records(self, store):
        now = datetime.now(timezone.utc)
        old = _make_record(timestamp=now - timedelta(days=2), record_id="r1")
        new = _make_record(timestamp=now, record_id="r2")
        store.record(old)
        store.record(new)
        _wait_for_write(store)

        removed = store.prune(now - timedelta(days=1))
        assert removed == 1
        _wait_for_write(store)
        assert len(store.get_records()) == 1
        assert store.get_records()[0].id == "r2"


class TestCorruptionFallback:
    def test_load_from_disk_returns_default_on_corrupted_json(self, store):
        store._records_file.write_text("{ invalid json }", encoding="utf-8")
        store._load_from_disk()
        assert store._cache == {"version": 1, "records": []}
