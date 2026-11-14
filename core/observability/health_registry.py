"""本地组件健康注册表，输出脱敏的只读快照。"""

import threading
from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import uuid4

from core.interfaces.health import HealthErrorCode, HealthSnapshot, HealthStatus

from .sanitize import sanitize_text

_SEVERITY = {
    HealthStatus.UNKNOWN: 0,
    HealthStatus.HEALTHY: 1,
    HealthStatus.DEGRADED: 2,
    HealthStatus.UNAVAILABLE: 3,
}
_MAX_MESSAGE_LENGTH = 300


class HealthRegistry:
    """按组件保存最新健康状态，以最严重状态聚合整体健康。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: Dict[str, HealthSnapshot] = {}

    def report(
        self,
        component: str,
        status: HealthStatus,
        error_code: Optional[HealthErrorCode] = None,
        message: str = "",
        correlation_id: str = "",
        plugin_id: str = "",
    ) -> HealthSnapshot:
        """记录组件状态并返回不可变快照。"""
        safe_component = sanitize_text(component)
        safe_plugin_id = sanitize_text(plugin_id)
        key = f"plugin:{safe_plugin_id}:{safe_component}" if safe_plugin_id else safe_component
        snapshot = HealthSnapshot(
            status=status,
            error_code=error_code,
            message=sanitize_text(message)[:_MAX_MESSAGE_LENGTH],
            timestamp=datetime.now(timezone.utc),
            correlation_id=sanitize_text(correlation_id) or uuid4().hex,
        )
        with self._lock:
            self._records[key] = snapshot
        return snapshot

    def clear_plugin(self, plugin_id: str) -> None:
        """插件卸载时清理其全部组件记录。"""
        prefix = f"plugin:{sanitize_text(plugin_id)}:"
        with self._lock:
            for key in list(self._records):
                if key.startswith(prefix):
                    self._records.pop(key, None)

    def snapshot(self) -> Dict:
        """返回整体状态及各组件快照，所有文本均已脱敏。"""
        with self._lock:
            records = dict(self._records)
        overall = max(
            (record.status for record in records.values()),
            key=lambda status: _SEVERITY[status],
            default=HealthStatus.UNKNOWN,
        )
        return {
            "status": overall.value,
            "components": {
                key: self._snapshot_record(record) for key, record in records.items()
            },
        }

    @staticmethod
    def _snapshot_record(record: HealthSnapshot) -> Dict:
        return {
            "status": record.status.value,
            "error_code": record.error_code.value if record.error_code else None,
            "message": sanitize_text(record.message)[:_MAX_MESSAGE_LENGTH],
            "timestamp": record.timestamp.isoformat(),
            "correlation_id": record.correlation_id,
        }


_registry = HealthRegistry()


def get_health_registry() -> HealthRegistry:
    """返回进程内健康注册表。"""
    return _registry
