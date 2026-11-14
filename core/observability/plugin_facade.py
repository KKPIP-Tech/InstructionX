"""绑定插件身份的可观测性门面，不定义任何领域业务审计格式。"""

from contextlib import contextmanager
from typing import Dict, Optional

from core.interfaces.health import HealthErrorCode, HealthSnapshot, HealthStatus

from .context import correlation_scope
from .health_registry import get_health_registry
from .metrics import get_metrics_registry


class PluginObservability:
    """插件上报自身健康与指标的稳定入口，自动绑定 plugin_id。"""

    def __init__(self, plugin_id: str) -> None:
        self._plugin_id = plugin_id

    def report_health(
        self,
        status: HealthStatus,
        message: str = "",
        error_code: Optional[HealthErrorCode] = None,
        capability: str = "plugin",
        correlation_id: str = "",
    ) -> HealthSnapshot:
        """上报插件某能力的健康状态并返回脱敏快照。"""
        return get_health_registry().report(
            component=capability,
            status=status,
            error_code=error_code,
            message=message,
            correlation_id=correlation_id,
            plugin_id=self._plugin_id,
        )

    def counter(self, name: str, labels: Optional[Dict] = None):
        """创建绑定当前插件的计数器。"""
        return get_metrics_registry().counter(name, self._labels(labels))

    def histogram(self, name: str, labels: Optional[Dict] = None):
        """创建绑定当前插件的直方图。"""
        return get_metrics_registry().histogram(name, self._labels(labels))

    def gauge(self, name: str, labels: Optional[Dict] = None):
        """创建绑定当前插件的瞬时值指标。"""
        return get_metrics_registry().gauge(name, self._labels(labels))

    @contextmanager
    def context(self, **overrides: str):
        """在插件调用范围内自动注入关联 ID 和耗时。"""
        overrides.pop("plugin_id", None)
        with correlation_scope(plugin_id=self._plugin_id, **overrides) as context:
            yield context

    def _labels(self, labels: Optional[Dict]) -> Dict:
        merged = dict(labels or {})
        merged["plugin_id"] = self._plugin_id
        return merged
