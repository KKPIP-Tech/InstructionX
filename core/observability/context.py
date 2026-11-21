"""基于 ContextVar 的调用关联上下文与耗时采集。"""

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from typing import Dict, Iterator, Optional
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    """一次调用链的只读关联信息，跨线程时需显式捕获并重新激活。"""

    plugin_id: str = ""
    task_id: str = ""
    request_id: str = ""
    conversation_id: str = ""

    @property
    def correlation_id(self) -> str:
        """返回链路标识，优先使用请求 ID。"""
        return self.request_id or self.task_id or self.plugin_id

    def merged(self, **overrides: str) -> "CorrelationContext":
        """合并非空覆盖项，保留当前调用链身份。"""
        values = {key: value for key, value in overrides.items() if value is not None}
        return replace(self, **values)


_CURRENT_CONTEXT: ContextVar[CorrelationContext] = ContextVar(
    "instructionx_correlation_context", default=CorrelationContext()
)
_STARTED_AT: ContextVar[Optional[float]] = ContextVar(
    "instructionx_correlation_started_at", default=None
)


def current_context() -> CorrelationContext:
    """返回当前上下文的不可变值，调用方修改不会影响原上下文。"""
    return _CURRENT_CONTEXT.get()


@contextmanager
def correlation_scope(
    context: Optional[CorrelationContext] = None, **overrides: str
) -> Iterator[CorrelationContext]:
    """激活调用链并自动记录耗时；新链路缺少请求 ID 时生成一个。"""
    base = (context or current_context()).merged(**overrides)
    if not base.correlation_id:
        base = base.merged(request_id=uuid4().hex)
    context_token = _CURRENT_CONTEXT.set(base)
    started_token = _STARTED_AT.set(time.perf_counter())
    try:
        yield base
    finally:
        _STARTED_AT.reset(started_token)
        _CURRENT_CONTEXT.reset(context_token)


def current_log_fields() -> Dict[str, object]:
    """生成日志过滤器所需字段，耗时保留三位毫秒。"""
    context = current_context()
    started_at = _STARTED_AT.get()
    duration: object = "-"
    if started_at is not None:
        duration = round((time.perf_counter() - started_at) * 1000, 3)
    return {
        "correlation_id": context.correlation_id or "-",
        "plugin_id": context.plugin_id or "-",
        "task_id": context.task_id or "-",
        "request_id": context.request_id or "-",
        "conversation_id": context.conversation_id or "-",
        "duration_ms": duration,
    }
