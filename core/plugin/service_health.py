"""插件核心服务健康注册表，负责聚合并发状态而非吞掉初始化失败。"""

import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from core.interfaces.health import (
    HealthErrorCode,
    HealthSnapshot,
    HealthStatus,
    sanitize_health_message,
)


_SEVERITY = {
    HealthStatus.UNKNOWN: 0,
    HealthStatus.HEALTHY: 1,
    HealthStatus.DEGRADED: 2,
    HealthStatus.UNAVAILABLE: 3,
}
_RECOVERY_SUGGESTIONS = {
    HealthErrorCode.CONFIGURATION: "检查相关配置项后重新加载插件。",
    HealthErrorCode.RESOURCE: "检查磁盘、内存和线程资源，释放资源后重试。",
    HealthErrorCode.NETWORK: "检查网络地址、凭据和远端服务状态后重试。",
    HealthErrorCode.PERMISSION: "检查文件与目录访问权限后重试。",
    HealthErrorCode.PERSISTENCE: "检查数据库与备份状态，确认可写后重新加载插件。",
    HealthErrorCode.PLUGIN_CODE: "检查插件异常堆栈并联系插件开发者修复。",
    HealthErrorCode.INTERNAL: "查看应用日志中的关联 ID 和异常上下文后重试。",
}


class PluginServiceHealth:
    """按插件和能力保存健康快照，以最严重状态作为插件整体状态。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshots: Dict[str, Dict[str, HealthSnapshot]] = {}

    def report(
        self,
        plugin_id: str,
        capability: str,
        status: HealthStatus,
        error_code: Optional[HealthErrorCode] = None,
        message: str = "",
        correlation_id: str = "",
    ) -> HealthSnapshot:
        """记录一个能力的最新状态并返回快照，便于日志复用关联 ID。"""
        snapshot = HealthSnapshot(
            status=status,
            error_code=error_code,
            message=sanitize_health_message(message),
            timestamp=datetime.now(timezone.utc),
            correlation_id=correlation_id or uuid4().hex,
        )
        with self._lock:
            self._snapshots.setdefault(plugin_id, {})[capability] = snapshot
        return snapshot

    def get_service_health(self, plugin_id: str) -> HealthSnapshot:
        """返回插件最严重能力的快照；从未上报时返回 UNKNOWN。"""
        with self._lock:
            snapshots = dict(self._snapshots.get(plugin_id, {}))
        if not snapshots:
            return self._unknown_snapshot()
        capability, snapshot = max(
            snapshots.items(), key=lambda item: _SEVERITY[item[1].status]
        )
        message = f"{capability}: {snapshot.message}" if snapshot.message else capability
        return HealthSnapshot(
            status=snapshot.status,
            error_code=snapshot.error_code,
            message=sanitize_health_message(message),
            timestamp=snapshot.timestamp,
            correlation_id=snapshot.correlation_id,
        )

    def get_unavailable_capabilities(self, plugin_id: str) -> List[str]:
        """返回完全不可用的能力名称，DEGRADED 不计入完全不可用。"""
        with self._lock:
            snapshots = dict(self._snapshots.get(plugin_id, {}))
        return [
            capability
            for capability, snapshot in snapshots.items()
            if snapshot.status is HealthStatus.UNAVAILABLE
        ]

    def get_health_issues(self) -> Dict[str, HealthSnapshot]:
        """返回所有降级或不可用插件的快照，供启动提示集中展示。"""
        with self._lock:
            plugin_ids = list(self._snapshots)
        issues = {}
        for plugin_id in plugin_ids:
            snapshot = self.get_service_health(plugin_id)
            if snapshot.status in (HealthStatus.DEGRADED, HealthStatus.UNAVAILABLE):
                issues[plugin_id] = snapshot
        return issues

    def clear(self, plugin_id: str) -> None:
        """插件卸载时清理其全部健康记录。"""
        with self._lock:
            self._snapshots.pop(plugin_id, None)

    @staticmethod
    def get_recovery_suggestion(error_code: Optional[HealthErrorCode]) -> str:
        """根据错误类别返回不含敏感信息的用户恢复建议。"""
        return _RECOVERY_SUGGESTIONS.get(
            error_code, _RECOVERY_SUGGESTIONS[HealthErrorCode.INTERNAL]
        )

    @staticmethod
    def _unknown_snapshot() -> HealthSnapshot:
        return HealthSnapshot(
            status=HealthStatus.UNKNOWN,
            error_code=None,
            message="尚未上报核心服务健康状态",
            timestamp=datetime.now(timezone.utc),
            correlation_id=uuid4().hex,
        )
