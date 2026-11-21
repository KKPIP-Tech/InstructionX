"""任务执行与调度指标，提供有界队列和调度延迟的可观测证据。"""

import math
import threading
from typing import Dict, List

from core.observability.metrics import get_metrics_registry
from core.observability.names import TASK_QUEUE_DEPTH, TASK_SCHEDULE_DELAY_MS


class TaskSupervisor:
    """以锁保护轻量计数器和调度延迟样本，不介入任务业务状态机。"""

    MAX_DELAY_SAMPLES = 1024

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._submitted: Dict[str, int] = {}
        self._completed: Dict[str, int] = {}
        self._rejected: Dict[str, int] = {}
        self._queue_depth: Dict[str, int] = {}
        self._schedule_delays_ms: List[float] = []

    def record_submit(self, pool: str) -> None:
        """记录一次成功提交并增加队列深度。"""
        with self._lock:
            self._submitted[pool] = self._submitted.get(pool, 0) + 1
            self._queue_depth[pool] = self._queue_depth.get(pool, 0) + 1
            depth = self._queue_depth[pool]
        get_metrics_registry().gauge(TASK_QUEUE_DEPTH, {"pool": pool}).set(depth)

    def record_completion(self, pool: str) -> None:
        """记录一次执行结束并降低队列深度。"""
        with self._lock:
            self._completed[pool] = self._completed.get(pool, 0) + 1
            self._queue_depth[pool] = max(0, self._queue_depth.get(pool, 1) - 1)
            depth = self._queue_depth[pool]
        get_metrics_registry().gauge(TASK_QUEUE_DEPTH, {"pool": pool}).set(depth)

    def record_rejected(self, pool: str) -> None:
        """记录一次队列满拒绝。"""
        with self._lock:
            self._rejected[pool] = self._rejected.get(pool, 0) + 1

    def record_schedule_delay(self, delay_ms: float) -> None:
        """记录定时任务实际提交相对计划时间的延迟。"""
        with self._lock:
            self._schedule_delays_ms.append(max(0.0, delay_ms))
            self._schedule_delays_ms = self._schedule_delays_ms[-self.MAX_DELAY_SAMPLES:]
        get_metrics_registry().histogram(TASK_SCHEDULE_DELAY_MS).observe(max(0.0, delay_ms))

    def snapshot(self) -> Dict[str, object]:
        """返回计数器、队列深度和调度延迟 p99 的一致性快照。"""
        with self._lock:
            delays = sorted(self._schedule_delays_ms)
            snapshot = {
                "submitted": dict(self._submitted),
                "completed": dict(self._completed),
                "rejected": dict(self._rejected),
                "queue_depth": dict(self._queue_depth),
                "schedule_delay_samples": len(delays),
            }
        snapshot["schedule_delay_p99_ms"] = self._percentile(delays, 0.99)
        return snapshot

    @staticmethod
    def _percentile(sorted_values: List[float], percentile: float) -> float:
        if not sorted_values:
            return 0.0
        rank = max(1, math.ceil(percentile * len(sorted_values)))
        return sorted_values[rank - 1]
