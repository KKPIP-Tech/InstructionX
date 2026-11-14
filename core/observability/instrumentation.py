"""共享测量工具，保持业务异常原样传播。"""

import time
from contextlib import contextmanager
from typing import Iterator, Optional

from .metrics import get_metrics_registry
from .names import DB_WRITE_FAILURES, DB_WRITE_LATENCY_MS


@contextmanager
def measure_db_write(operation: str, plugin_id: Optional[str] = None) -> Iterator[None]:
    """测量数据库写入耗时并记录失败，原异常不被替换或吞掉。"""
    labels = {"operation": operation}
    if plugin_id:
        labels["plugin_id"] = plugin_id
    started = time.perf_counter()
    try:
        yield
    except Exception:
        get_metrics_registry().counter(DB_WRITE_FAILURES, labels).inc()
        raise
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        get_metrics_registry().histogram(DB_WRITE_LATENCY_MS, labels).observe(elapsed_ms)
