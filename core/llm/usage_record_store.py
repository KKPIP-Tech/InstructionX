"""LLM 用量记录持久化存储模块

基于 JSON 的原子写入单例存储，用于记录每一次 LLM API 请求的用量信息。
遵循 task_storage.py 的原子写入模式（临时文件 + os.replace）。

写入策略:
    单后台写线程 + 防抖合并（debounce）：连续高频记录只触发一次全量写入，
    避免每条记录都 spawn 新线程全量重写文件。

存储文件: data/llm_usage.json
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

from .types import UsageRecord

logger = logging.getLogger(__name__)


def _normalize_dt(value: Any) -> datetime:
    """将时间戳归一化为 UTC aware datetime

    兼容历史数据中的 naive datetime（视为 UTC）与 ISO 字符串，
    避免 naive/aware 混合比较抛出 TypeError。

    Args:
        value: datetime 或 ISO 格式字符串

    Returns:
        datetime: UTC aware 的 datetime 对象
    """
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        # 历史 naive 时间戳视为 UTC
        return value.replace(tzinfo=timezone.utc)
    return value


class UsageRecordStore:
    """LLM 用量记录存储单例

    线程安全的 JSON 持久化存储，采用原子写入保证数据一致性。
    使用单后台写线程 + 防抖合并异步写入，避免阻塞主线程和频繁全量重写。

    Example:
        >>> store = get_usage_record_store()
        >>> record = UsageRecord(...)
        >>> store.record(record)
        >>> records = store.get_records(provider="minimax")
    """

    _instance: Optional["UsageRecordStore"] = None
    _lock = threading.Lock()

    # 防抖合并窗口（秒）：窗口内的连续写入合并为一次磁盘写入
    DEBOUNCE_SECONDS = 0.2
    # 自动 prune 阈值：超过 MAX_RECORDS 条时仅保留最近 PRUNE_KEEP 条
    MAX_RECORDS = 10000
    PRUNE_KEEP = 8000

    def __new__(cls) -> "UsageRecordStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        self._file_lock = threading.RLock()
        self._pending_write = False

        # 单后台写线程（防抖合并）
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_wake = threading.Event()

        # 数据目录和文件路径
        self._data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._records_file = self._data_dir / "llm_usage.json"

        # 内存缓存
        self._cache: Dict[str, Any] = {"version": 1, "records": []}
        self._cache_dirty = False

        self._ensure_data_file()
        self._load_from_disk()

    def _ensure_data_file(self) -> None:
        """确保数据文件存在"""
        if not self._records_file.exists():
            with open(self._records_file, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "records": []}, f, ensure_ascii=False, indent=2)

    def _load_from_disk(self) -> None:
        """从磁盘加载数据到内存缓存"""
        try:
            with open(self._records_file, "r", encoding="utf-8") as f:
                self._cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._cache = {"version": 1, "records": []}

    def _write_to_disk(self, data: Dict[str, Any]) -> None:
        """原子写入数据到磁盘（临时文件 + os.replace）"""
        temp_file = self._records_file.with_suffix(".json.tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        os.replace(temp_file, self._records_file)

    def _async_save(self) -> None:
        """触发后台异步保存（单写线程 + 防抖合并）

        标记有待写入数据并唤醒后台写线程；写线程在防抖窗口后
        将窗口内累计的所有变更一次性写入磁盘。
        """
        with self._file_lock:
            self._pending_write = True
            if self._writer_thread is None or not self._writer_thread.is_alive():
                self._writer_thread = threading.Thread(
                    target=self._writer_loop,
                    daemon=True,
                    name="UsageRecordStore-writer",
                )
                self._writer_thread.start()
            self._writer_wake.set()

    def _writer_loop(self) -> None:
        """后台写线程主循环

        等待唤醒 -> 防抖窗口等待（合并连续写入）-> 原子写入。
        窗口期内若有新记录到来，自动进入下一轮合并写入。
        """
        while True:
            self._writer_wake.wait()
            self._writer_wake.clear()
            # 防抖窗口：合并短时间内的连续写入
            time.sleep(self.DEBOUNCE_SECONDS)
            with self._file_lock:
                if self._cache_dirty:
                    try:
                        self._write_to_disk(self._cache)
                    except Exception:
                        logger.exception("UsageRecordStore 写入磁盘失败")
                    self._cache_dirty = False
                # 窗口期内又来了新记录 -> 保持 pending，继续下一轮写入
                self._pending_write = self._writer_wake.is_set()

    # ==================== 公开 API ====================

    def record(self, usage_record: UsageRecord) -> None:
        """记录一次 LLM API 请求

        Args:
            usage_record: 用量记录
        """
        record_dict = usage_record.to_dict()
        if "id" not in record_dict or not record_dict["id"]:
            record_dict["id"] = uuid.uuid4().hex

        with self._file_lock:
            self._cache["records"].append(record_dict)
            # 自动 prune：超过阈值时仅保留最近的记录
            if len(self._cache["records"]) > self.MAX_RECORDS:
                self._cache["records"] = self._cache["records"][-self.PRUNE_KEEP:]
            self._cache_dirty = True

        self._async_save()

    def get_records(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        conversation_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[UsageRecord]:
        """查询用量记录

        Args:
            start_time: 起始时间（包含）
            end_time: 结束时间（包含）
            provider: Provider 名称（精确匹配）
            model: Model 名称（精确匹配）
            conversation_id: 对话 ID（精确匹配）
            limit: 最大返回条数
            offset: 跳过条数

        Returns:
            List[UsageRecord]: 符合条件的记录列表
        """
        # 归一化查询时间范围，兼容 naive/aware 混合比较
        if start_time is not None:
            start_time = _normalize_dt(start_time)
        if end_time is not None:
            end_time = _normalize_dt(end_time)

        with self._file_lock:
            records = self._cache["records"][:]
            # 深拷贝避免外部修改缓存
            records = [r.copy() for r in records]

        results = []
        for r in records:
            # 时间过滤（时间戳归一化为 UTC aware 后比较）
            if start_time or end_time:
                ts = _normalize_dt(r["timestamp"])
                if start_time and ts < start_time:
                    continue
                if end_time and ts > end_time:
                    continue

            # 精确匹配过滤
            if provider and r.get("provider") != provider:
                continue
            if model and r.get("model") != model:
                continue
            if conversation_id and r.get("conversation_id") != conversation_id:
                continue

            results.append(UsageRecord.from_dict(r))

        # 分页
        total = len(results)
        results = results[offset:]
        if limit is not None:
            results = results[:limit]

        return results

    def aggregate(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        group_by: str = "provider",
    ) -> Dict[str, Any]:
        """聚合统计

        Args:
            start_time: 起始时间
            end_time: 结束时间
            group_by: 分组字段 ("provider" | "model" | "day")

        Returns:
            Dict: 聚合结果
        """
        records = self.get_records(start_time=start_time, end_time=end_time)

        groups: Dict[str, Dict[str, Any]] = {}
        for r in records:
            if group_by == "provider":
                key = r.provider
            elif group_by == "model":
                key = r.model
            elif group_by == "day":
                key = r.timestamp.strftime("%Y-%m-%d")
            else:
                key = "all"

            if key not in groups:
                groups[key] = {
                    "group_key": key,
                    "total_requests": 0,
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tokens": 0,
                    "total_cached_tokens": 0,
                    "cache_hits": 0,
                    "total_duration_ms": 0.0,
                }

            g = groups[key]
            g["total_requests"] += 1
            g["total_input_tokens"] += r.input_tokens
            g["total_output_tokens"] += r.output_tokens
            g["total_tokens"] += r.total_tokens
            g["total_cached_tokens"] += r.cached_tokens
            if r.cache_hit:
                g["cache_hits"] += 1
            g["total_duration_ms"] += r.duration_ms

        # 计算派生指标
        for g in groups.values():
            g["cache_hit_rate"] = g["cache_hits"] / g["total_requests"] if g["total_requests"] > 0 else 0.0
            g["avg_duration_ms"] = g["total_duration_ms"] / g["total_requests"] if g["total_requests"] > 0 else 0.0

        return {"groups": list(groups.values())}

    def get_total_stats(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取总计统计

        Args:
            start_time: 起始时间
            end_time: 结束时间

        Returns:
            Dict: 总计统计
        """
        records = self.get_records(start_time=start_time, end_time=end_time)

        total_requests = len(records)
        total_input = sum(r.input_tokens for r in records)
        total_output = sum(r.output_tokens for r in records)
        total_tokens = sum(r.total_tokens for r in records)
        total_cached = sum(r.cached_tokens for r in records)
        cache_hits = sum(1 for r in records if r.cache_hit)
        total_duration = sum(r.duration_ms for r in records)

        return {
            "total_requests": total_requests,
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_tokens": total_tokens,
            "total_cached_tokens": total_cached,
            "cache_hits": cache_hits,
            "cache_hit_rate": cache_hits / total_requests if total_requests > 0 else 0.0,
            "total_duration_ms": total_duration,
            "avg_duration_ms": total_duration / total_requests if total_requests > 0 else 0.0,
        }

    def prune(self, before: datetime) -> int:
        """删除指定时间之前的记录

        Args:
            before: 删除此时间之前的记录

        Returns:
            int: 删除的记录数
        """
        before = _normalize_dt(before)
        with self._file_lock:
            original_count = len(self._cache["records"])
            self._cache["records"] = [
                r for r in self._cache["records"]
                if _normalize_dt(r["timestamp"]) >= before
            ]
            removed = original_count - len(self._cache["records"])
            if removed > 0:
                self._cache_dirty = True
                self._async_save()
            return removed


# ==================== 单例访问函数 ====================

def get_usage_record_store() -> UsageRecordStore:
    """获取 UsageRecordStore 单例

    Returns:
        UsageRecordStore: 用量记录存储单例
    """
    return UsageRecordStore()
