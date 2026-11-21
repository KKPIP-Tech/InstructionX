"""进程内线程安全指标注册表，序列与样本均有明确上限。"""

import math
import threading
from collections import deque
from typing import Dict, Optional, Tuple

from .sanitize import sanitize_text

_COUNTER = "counter"
_HISTOGRAM = "histogram"
_GAUGE = "gauge"
_NOOP = "noop"
DEFAULT_MAX_SERIES_PER_METRIC = 1024
DEFAULT_HISTOGRAM_SAMPLES = 1024
MAX_LABEL_COUNT = 8
MAX_LABEL_TEXT = 128


def _finite(value: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class _Instrument:
    """单项指标的数据容器，错误通过布尔返回值显式暴露。"""

    def __init__(self, kind: str, on_error):
        self.kind = kind
        self._on_error = on_error
        self._lock = threading.Lock()

    def _invalid(self) -> bool:
        self._on_error()
        return False


class CounterMetric(_Instrument):
    """单调递增计数器。"""

    def __init__(self, on_error):
        super().__init__(_COUNTER, on_error)
        self._value = 0.0

    def inc(self, amount: float = 1.0) -> bool:
        """增加非负有限值，成功返回 True。"""
        if not _finite(amount) or amount < 0:
            return self._invalid()
        with self._lock:
            self._value += amount
        return True

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {"value": self._value}


class GaugeMetric(_Instrument):
    """瞬时值指标。"""

    def __init__(self, on_error):
        super().__init__(_GAUGE, on_error)
        self._value = 0.0

    def set(self, value: float) -> bool:
        """设置有限瞬时值，成功返回 True。"""
        if not _finite(value):
            return self._invalid()
        with self._lock:
            self._value = value
        return True

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {"value": self._value}


class HistogramMetric(_Instrument):
    """保存有限样本并计算本地百分位的直方图。"""

    def __init__(self, on_error, max_samples: int):
        super().__init__(_HISTOGRAM, on_error)
        self._samples = deque(maxlen=max_samples)
        self._count = 0
        self._sum = 0.0

    def observe(self, value: float) -> bool:
        """记录非负有限观测值，成功返回 True。"""
        if not _finite(value) or value < 0:
            return self._invalid()
        with self._lock:
            self._samples.append(float(value))
            self._count += 1
            self._sum += value
        return True

    def snapshot(self) -> Dict[str, float]:
        with self._lock:
            samples = sorted(self._samples)
            return {
                "count": self._count,
                "sum": self._sum,
                "p50": self._percentile(samples, 0.50),
                "p95": self._percentile(samples, 0.95),
                "p99": self._percentile(samples, 0.99),
            }

    @staticmethod
    def _percentile(samples, percentile: float) -> float:
        if not samples:
            return 0.0
        rank = max(1, math.ceil(percentile * len(samples)))
        return samples[rank - 1]


class _NoopMetric:
    """超出基数或类型冲突时的有限降级对象。"""

    kind = _NOOP

    def inc(self, amount: float = 1.0) -> bool:
        return False

    def set(self, value: float) -> bool:
        return False

    def observe(self, value: float) -> bool:
        return False


class MetricsRegistry:
    """按名称和标签创建指标；超出基数时返回 no-op 并记录丢弃数。"""

    def __init__(self, max_series_per_metric: int = DEFAULT_MAX_SERIES_PER_METRIC):
        self._max_series = max_series_per_metric
        self._lock = threading.Lock()
        self._series: Dict[str, Dict[Tuple, _Instrument]] = {}
        self._dropped_series = 0
        self._errors = 0

    def counter(self, name: str, labels: Optional[Dict] = None) -> CounterMetric:
        """获取或创建计数器。"""
        return self._get_or_create(_COUNTER, name, labels)

    def histogram(self, name: str, labels: Optional[Dict] = None) -> HistogramMetric:
        """获取或创建直方图。"""
        return self._get_or_create(_HISTOGRAM, name, labels)

    def gauge(self, name: str, labels: Optional[Dict] = None) -> GaugeMetric:
        """获取或创建瞬时值指标。"""
        return self._get_or_create(_GAUGE, name, labels)

    def _get_or_create(self, kind: str, name: str, labels: Optional[Dict]):
        try:
            safe_name, safe_labels = self._identity(name, labels)
        except (TypeError, ValueError):
            self._record_error()
            return _NoopMetric()
        with self._lock:
            named = self._series.setdefault(safe_name, {})
            existing = named.get(safe_labels)
            if existing is not None and existing.kind == kind:
                return existing
            if existing is not None or len(named) >= self._max_series:
                self._dropped_series += 1
                return _NoopMetric()
            named[safe_labels] = self._create(kind)
            return named[safe_labels]

    def _create(self, kind: str) -> _Instrument:
        if kind == _COUNTER:
            return CounterMetric(self._record_error)
        if kind == _GAUGE:
            return GaugeMetric(self._record_error)
        return HistogramMetric(self._record_error, DEFAULT_HISTOGRAM_SAMPLES)

    @staticmethod
    def _identity(name: str, labels: Optional[Dict]) -> Tuple[str, Tuple]:
        safe_name = sanitize_text(name).strip()
        if not safe_name:
            raise ValueError("指标名称不能为空")
        items = dict(labels or {}).items()
        if len(items) > MAX_LABEL_COUNT:
            raise ValueError("指标标签数量超限")
        safe_labels = tuple(sorted(
            (sanitize_text(key)[:MAX_LABEL_TEXT], sanitize_text(value)[:MAX_LABEL_TEXT])
            for key, value in items
        ))
        return safe_name, safe_labels

    def _record_error(self) -> None:
        with self._lock:
            self._errors += 1

    def snapshot(self) -> Dict:
        """返回本地只读副本，不共享内部可变样本。"""
        with self._lock:
            series = [(name, labels, metric) for name, items in self._series.items()
                      for labels, metric in items.items()]
            dropped, errors = self._dropped_series, self._errors
        return {
            "series": [
                {"name": name, "kind": metric.kind, "labels": dict(labels), **metric.snapshot()}
                for name, labels, metric in series
            ],
            "dropped_series": dropped,
            "errors": errors,
        }

    def clear(self) -> None:
        """清空本地指标，供隔离测试或重新初始化使用。"""
        with self._lock:
            self._series.clear()
            self._dropped_series = 0
            self._errors = 0


_registry = MetricsRegistry()


def get_metrics_registry() -> MetricsRegistry:
    """返回进程内指标注册表。"""
    return _registry
