"""框架自身生命周期事件的有界内存日志，不承载领域业务审计。"""

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Optional
from uuid import uuid4

from .context import current_context
from .sanitize import sanitize_value

DEFAULT_EVENT_CAPACITY = 1024


class FrameworkEventType(str, Enum):
    """框架可证明的基础设施事件闭集。"""

    PLUGIN_LOADED = "PLUGIN_LOADED"
    TASK_CANCELLED = "TASK_CANCELLED"
    DATA_RECOVERED = "DATA_RECOVERED"
    MCP_EXPOSED = "MCP_EXPOSED"


@dataclass(frozen=True, slots=True)
class FrameworkEvent:
    """一条脱敏的框架事件。"""

    event_id: str
    event_type: FrameworkEventType
    component: str
    correlation_id: str
    timestamp: str
    details: Dict

    def to_dict(self) -> Dict:
        """返回可安全展示的副本。"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "component": self.component,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "details": sanitize_value(self.details),
        }


class FrameworkEventJournal:
    """线程安全的有界事件日志，仅供本地诊断而非合规审计存储。"""

    def __init__(self, capacity: int = DEFAULT_EVENT_CAPACITY):
        self._events = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def record(
        self,
        event_type: FrameworkEventType,
        component: str,
        correlation_id: str = "",
        details: Optional[Dict] = None,
    ) -> FrameworkEvent:
        """记录框架事件并自动清理详情中的敏感字段。"""
        event = FrameworkEvent(
            event_id=uuid4().hex,
            event_type=event_type,
            component=sanitize_value(component),
            correlation_id=sanitize_value(
                correlation_id or current_context().correlation_id or uuid4().hex
            ),
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=sanitize_value(details or {}),
        )
        with self._lock:
            self._events.append(event)
        return event

    def snapshot(self, limit: int = 100) -> list[Dict]:
        """返回最近事件的只读副本，limit 必须为正数。"""
        if limit <= 0:
            return []
        with self._lock:
            events = list(self._events)[-limit:]
        return [event.to_dict() for event in events]


_journal = FrameworkEventJournal()


def get_framework_event_journal() -> FrameworkEventJournal:
    """返回进程内框架事件日志。"""
    return _journal
