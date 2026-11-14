"""InstructionX 本地可观测性能力，无外部监控服务运行前提。"""

from .context import CorrelationContext, correlation_scope, current_context
from .events import FrameworkEventType, get_framework_event_journal
from .health_registry import HealthRegistry, get_health_registry
from .metrics import MetricsRegistry, get_metrics_registry
from .plugin_facade import PluginObservability
from .sanitize import register_sensitive_fields, sanitize_text, sanitize_value

__all__ = [
    "CorrelationContext",
    "FrameworkEventType",
    "HealthRegistry",
    "MetricsRegistry",
    "PluginObservability",
    "correlation_scope",
    "current_context",
    "get_framework_event_journal",
    "get_health_registry",
    "get_metrics_registry",
    "register_sensitive_fields",
    "sanitize_text",
    "sanitize_value",
]
