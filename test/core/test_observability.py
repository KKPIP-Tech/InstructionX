"""Task 9 可观测性内核、日志脱敏与框架集成验收。"""

import asyncio
import logging
import queue
import time
from types import SimpleNamespace

import pytest

from core.data.event_dispatcher import BackpressurePolicy, EventDispatcher
from core.interfaces.health import HealthStatus
from core.mcp.client import MCPClientManager
from core.observability import (
    FrameworkEventType,
    PluginObservability,
    correlation_scope,
    current_context,
    get_health_registry,
    get_metrics_registry,
    register_sensitive_fields,
    sanitize_text,
    sanitize_value,
)
from core.observability.context import current_log_fields
from core.observability.events import FrameworkEventJournal
from core.observability.instrumentation import measure_db_write
from core.observability.metrics import MetricsRegistry
from core.observability.names import (
    DB_WRITE_FAILURES,
    DB_WRITE_LATENCY_MS,
    EVENT_DROPPED,
    MCP_SESSIONS,
    TASK_QUEUE_DEPTH,
    TASK_SCHEDULE_DELAY_MS,
    UI_CHART_INGEST_MS,
)
from core.plugin.service_health import PluginServiceHealth
from core.task.supervisor import TaskSupervisor
from ui.usage_panel.trend_chart import TrendPanel
from utils.logging_tools import (
    DEGRADED_MEMORY_CAPACITY,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LoggerManager,
    _BoundedMemoryHandler,
    _ObservabilityFilter,
    _ObservabilityFormatter,
)


def test_correlation_scope_propagates_ids_duration_and_restores_parent():
    """嵌套调用继承关联 ID，退出后恢复父上下文。"""
    with correlation_scope(plugin_id="plugin-a", request_id="request-1") as parent:
        with correlation_scope(task_id="task-1", conversation_id="conversation-1"):
            time.sleep(0.001)
            context = current_context()
            assert context.correlation_id == "request-1"
            assert context.task_id == "task-1"
            assert context.conversation_id == "conversation-1"
            assert current_log_fields()["duration_ms"] >= 1
        assert current_context() is parent


def test_sanitize_handles_bearer_nested_and_custom_sensitive_fields():
    """Authorization、API Key、token 和自定义患者字段必须全部脱敏。"""
    register_sensitive_fields("hospital_case_number")
    text = "Authorization: Bearer secret-token api_key=abc123 token='xyz'"
    sanitized = sanitize_text(text)
    assert "secret-token" not in sanitized
    assert "abc123" not in sanitized
    assert "xyz" not in sanitized
    value = sanitize_value({
        "patient_id": "patient-1",
        "hospital_case_number": "case-1",
        "nested": {"safe": "visible"},
    })
    assert value["patient_id"] == "[已脱敏]"
    assert value["hospital_case_number"] == "[已脱敏]"
    assert value["nested"]["safe"] == "visible"


def test_metrics_counter_histogram_gauge_and_bounded_cardinality():
    """三类指标可本地读取，标签序列超限必须有限降级并计数。"""
    registry = MetricsRegistry(max_series_per_metric=2)
    assert registry.counter("requests", {"pool": "normal"}).inc(2)
    assert registry.histogram("latency").observe(1)
    assert registry.histogram("latency").observe(3)
    assert registry.gauge("queue").set(4)
    registry.counter("requests", {"pool": "high"}).inc()
    overflow = registry.counter("requests", {"pool": "overflow"})
    assert overflow.inc() is False
    snapshot = registry.snapshot()
    assert snapshot["dropped_series"] == 1
    series = {(item["name"], item["kind"]): item for item in snapshot["series"]}
    request_total = sum(
        item["value"] for item in snapshot["series"] if item["name"] == "requests"
    )
    assert request_total == 3
    assert series[("latency", "histogram")]["p95"] == 3
    assert series[("queue", "gauge")]["value"] == 4


def test_metric_invalid_values_return_failure_without_throwing():
    """非法数值不得拖垮业务路径，错误必须可观测。"""
    registry = MetricsRegistry()
    assert registry.counter("counter").inc(-1) is False
    assert registry.histogram("histogram").observe(float("nan")) is False
    assert registry.gauge("gauge").set(float("inf")) is False
    assert registry.snapshot()["errors"] == 3


def test_health_registry_sanitizes_and_clears_plugin_records():
    """健康快照不得包含敏感消息，卸载后插件记录清零。"""
    registry = get_health_registry()
    registry.report(
        "database",
        HealthStatus.DEGRADED,
        message="token=health-secret",
        correlation_id="token=correlation-secret",
        plugin_id="plugin-health",
    )
    snapshot = registry.snapshot()
    record = snapshot["components"]["plugin:plugin-health:database"]
    assert "health-secret" not in record["message"]
    assert "correlation-secret" not in record["correlation_id"]
    registry.clear_plugin("plugin-health")
    assert "plugin:plugin-health:database" not in registry.snapshot()["components"]


def test_framework_event_journal_is_bounded_and_sanitized():
    """框架事件有界且仅保存脱敏基础设施详情。"""
    journal = FrameworkEventJournal(capacity=2)
    for index in range(3):
        journal.record(
            FrameworkEventType.PLUGIN_LOADED,
            "plugin-events",
            details={"token": "event-secret", "index": index},
        )
    events = journal.snapshot()
    assert len(events) == 2
    assert events[-1]["details"]["index"] == 2
    assert events[-1]["details"]["token"] == "[已脱敏]"
    assert events[-1]["event_type"] == "PLUGIN_LOADED"


def test_plugin_observability_binds_identity_to_health_metrics_and_context():
    """插件门面自动绑定身份，不能由调用标签覆盖。"""
    get_metrics_registry().clear()
    facade = PluginObservability("plugin-facade")
    facade.counter("plugin_calls", {"plugin_id": "spoofed", "kind": "test"}).inc()
    facade.report_health(HealthStatus.HEALTHY, capability="ready")
    with facade.context(task_id="plugin-task") as context:
        assert context.plugin_id == "plugin-facade"
        assert context.task_id == "plugin-task"
    series = get_metrics_registry().snapshot()["series"]
    assert series[0]["labels"] == {"kind": "test", "plugin_id": "plugin-facade"}
    components = get_health_registry().snapshot()["components"]
    assert components["plugin:plugin-facade:ready"]["status"] == "healthy"



def test_log_record_contains_correlation_context_and_is_sanitized():
    """日志自动携带关联 ID、插件、任务和耗时，敏感文本不得落盘。"""
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "token=log-secret", (), None
    )
    with correlation_scope(
        plugin_id="plugin-log", task_id="task-log", request_id="request-log"
    ):
        _ObservabilityFilter().filter(record)
        formatted = _ObservabilityFormatter(LOG_FORMAT, LOG_DATE_FORMAT).format(record)
    assert "trace=request-log" in formatted
    assert "plugin=plugin-log" in formatted
    assert "task=task-log" in formatted
    assert "duration_ms=" in formatted
    assert "log-secret" not in formatted


def test_logging_write_failure_is_bounded_and_does_not_raise(monkeypatch, tmp_path):
    """模拟写盘失败时有界降级，业务日志调用与非法级别语义保持明确。"""
    def fail_file_handler(*args, **kwargs):
        raise OSError("模拟磁盘满")

    monkeypatch.setattr("utils.logging_tools._SafeRotatingFileHandler", fail_file_handler)
    handler = LoggerManager._create_file_handler(str(tmp_path))
    assert isinstance(handler, _BoundedMemoryHandler)
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "message", (), None)
    for _ in range(DEGRADED_MEMORY_CAPACITY + 1):
        handler.emit(record)
    assert len(handler.records) == DEGRADED_MEMORY_CAPACITY

    manager = object.__new__(LoggerManager)
    manager._write_failures = 0
    manager._logger = SimpleNamespace(log=fail_file_handler)
    manager.log("INFO", "test", "message")
    assert manager._write_failures == 1
    with pytest.raises(AttributeError):
        manager.log("INVALID", "test", "message")


def test_task_supervisor_publishes_queue_depth_and_schedule_delay():
    """既有任务监督器必须向统一注册表发布队列与调度指标。"""
    get_metrics_registry().clear()
    supervisor = TaskSupervisor()
    supervisor.record_submit("normal")
    supervisor.record_schedule_delay(12.5)
    supervisor.record_completion("normal")
    snapshot = get_metrics_registry().snapshot()
    queue_metric = _metric(snapshot, TASK_QUEUE_DEPTH)
    delay_metric = _metric(snapshot, TASK_SCHEDULE_DELAY_MS)
    assert queue_metric["value"] == 0
    assert delay_metric["count"] == 1
    assert delay_metric["p99"] == 12.5


def test_event_backpressure_publishes_drop_metric():
    """邮箱满拒绝事件时既有计数与统一指标必须同时增加。"""
    get_metrics_registry().clear()
    dispatcher = EventDispatcher()
    mailbox = SimpleNamespace(
        queue=queue.Queue(maxsize=1), dropped=0, coalesced=0
    )
    event = SimpleNamespace()
    assert dispatcher._offer(mailbox, event, BackpressurePolicy.REJECT)
    assert not dispatcher._offer(mailbox, event, BackpressurePolicy.REJECT)
    assert mailbox.dropped == 1
    assert _metric(get_metrics_registry().snapshot(), EVENT_DROPPED)["value"] == 1


def test_db_write_metrics_cover_success_and_failure():
    """数据库写入耗时覆盖成功和异常，失败异常原样抛出。"""
    get_metrics_registry().clear()
    with measure_db_write("unit_test"):
        pass
    with pytest.raises(RuntimeError, match="写入失败"):
        with measure_db_write("unit_test"):
            raise RuntimeError("写入失败")
    snapshot = get_metrics_registry().snapshot()
    assert _metric(snapshot, DB_WRITE_LATENCY_MS)["count"] == 2
    assert _metric(snapshot, DB_WRITE_FAILURES)["value"] == 1


def test_plugin_service_health_forwards_to_local_snapshot():
    """既有插件健康上报必须汇入本地只读健康快照。"""
    service = PluginServiceHealth()
    service.report("plugin-forward", "database", HealthStatus.DEGRADED, message="degraded")
    components = get_health_registry().snapshot()["components"]
    assert components["plugin:plugin-forward:database"]["status"] == "degraded"


def _metric(snapshot, name):
    """按唯一名称读取测试指标。"""
    return next(item for item in snapshot["series"] if item["name"] == name)



def test_chart_stream_ingest_publishes_elapsed_metric():
    """真实图表流式入口必须产生入图耗时观测。"""
    get_metrics_registry().clear()
    chart = SimpleNamespace(set_stream_data=lambda data, series: True)
    panel = SimpleNamespace(_chart=chart)
    assert TrendPanel._push_series_data(panel, [["2026-01-01", 1]])
    metric = _metric(get_metrics_registry().snapshot(), UI_CHART_INGEST_MS)
    assert metric["count"] == 1
    assert metric["p99"] >= 0


def test_mcp_connection_table_publishes_session_gauge():
    """远程 MCP 连接建立与断开必须同步统一会话数。"""
    get_metrics_registry().clear()

    class Registry:
        def __init__(self):
            self.tools = {}

        def register(self, name, description, parameters, handler):
            self.tools[name] = handler

        def unregister(self, name):
            self.tools.pop(name, None)

    manager = MCPClientManager(Registry())
    config = SimpleNamespace(server_id="remote", name="Remote")
    tool = SimpleNamespace(name="echo", description="", inputSchema={})
    manager._create_connection(
        "remote", config, object(), SimpleNamespace(tools=[tool])
    )
    assert _metric(get_metrics_registry().snapshot(), MCP_SESSIONS)["value"] == 1
    asyncio.run(manager._async_disconnect("remote"))
    assert _metric(get_metrics_registry().snapshot(), MCP_SESSIONS)["value"] == 0
    assert manager.shutdown() == ()
