"""插件核心服务健康模型与显式故障测试。"""

import ast
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.interfaces.health import (
    HealthErrorCode,
    HealthSnapshot,
    HealthStatus,
    classify_exception,
    sanitize_health_message,
)
from core.plugin.manager import PluginManager
from core.plugin.service_health import PluginServiceHealth
from ui.main_window import InstructionXMainWindow


def _patch_optional_dependencies(mocker, manager):
    """隔离 LLM、MCP、字体和国际化，避免读取真实配置。"""
    mocker.patch("core.llm.get_llm_plugin_service", return_value=MagicMock())
    mocker.patch.object(manager, "_get_mcp_manager", return_value=MagicMock())
    mocker.patch.object(manager, "_get_mcp_client", return_value=MagicMock())
    mocker.patch("core.plugin.manager.get_font_manager", return_value=MagicMock())
    mocker.patch("core.plugin.manager.get_language_manager", return_value=MagicMock())
    mocker.patch("core.plugin.manager.PluginI18nFacade", return_value=MagicMock())


def test_health_snapshot_contract_and_unknown_state():
    """健康快照包含约定字段，未上报服务应处于 UNKNOWN。"""
    registry = PluginServiceHealth()
    snapshot = registry.get_service_health("missing")
    assert snapshot.status is HealthStatus.UNKNOWN
    assert snapshot.error_code is None
    assert snapshot.timestamp.tzinfo is not None
    assert snapshot.correlation_id


def test_registry_uses_most_severe_service_state():
    """任一核心服务不可用，整体状态不得被后续健康服务覆盖。"""
    registry = PluginServiceHealth()
    registry.report("p1", "data_provider", HealthStatus.UNAVAILABLE, HealthErrorCode.PERSISTENCE, "数据库不可用")
    registry.report("p1", "task_manager", HealthStatus.HEALTHY)
    snapshot = registry.get_service_health("p1")
    assert snapshot.status is HealthStatus.UNAVAILABLE
    assert snapshot.error_code is HealthErrorCode.PERSISTENCE
    assert "data_provider" in snapshot.message
    assert registry.get_unavailable_capabilities("p1") == ["data_provider"]


def test_degraded_service_is_visible_but_not_fatal():
    """可选 MCP 失败应形成 DEGRADED，而不是静默成功或错误放大。"""
    registry = PluginServiceHealth()
    registry.report("p1", "data_provider", HealthStatus.HEALTHY)
    registry.report("p1", "mcp_client", HealthStatus.DEGRADED, HealthErrorCode.NETWORK, "连接失败")
    snapshot = registry.get_service_health("p1")
    assert snapshot.status is HealthStatus.DEGRADED
    assert snapshot.error_code is HealthErrorCode.NETWORK


def test_data_provider_failure_marks_plugin_unavailable(mocker):
    """DataProvider 初始化失败必须显式可见，不得创建 MagicMock。"""
    manager = PluginManager()
    _patch_optional_dependencies(mocker, manager)
    mocker.patch("core.plugin.manager.DataProvider", side_effect=OSError("磁盘不可用"))
    mocker.patch("core.plugin.manager.BackgroundTaskManager", return_value=MagicMock())
    services = manager._create_plugin_services("plugin-data-error")
    snapshot = manager.get_service_health("plugin-data-error")
    assert services.data_provider is None
    assert snapshot.status is HealthStatus.UNAVAILABLE
    assert snapshot.error_code is HealthErrorCode.PERSISTENCE
    assert manager.get_unavailable_capabilities("plugin-data-error") == ["data_provider"]


def test_llm_failure_is_unavailable_and_log_is_redacted(mocker):
    """LLM 初始化失败应显式不可用，日志与健康信息均不得泄露密钥。"""
    manager = PluginManager()
    _patch_optional_dependencies(mocker, manager)
    mocker.patch("core.plugin.manager.DataProvider", return_value=MagicMock())
    mocker.patch("core.plugin.manager.BackgroundTaskManager", return_value=MagicMock())
    mocker.patch(
        "core.llm.get_llm_plugin_service",
        side_effect=ValueError("api_key=very-secret-key 配置错误"),
    )
    services = manager._create_plugin_services("plugin-llm-error")
    snapshot = manager.get_service_health("plugin-llm-error")
    assert services.llm_facade is None
    assert snapshot.status is HealthStatus.UNAVAILABLE
    assert snapshot.error_code is HealthErrorCode.CONFIGURATION
    assert "very-secret-key" not in snapshot.message
    log_text = "".join(str(call.args) for call in manager._logger.error.call_args_list)
    assert "very-secret-key" not in log_text


def test_task_manager_failure_marks_plugin_unavailable(mocker):
    """任务管理器失败应返回资源错误并保留旧 None 注入兼容。"""
    manager = PluginManager()
    _patch_optional_dependencies(mocker, manager)
    mocker.patch("core.plugin.manager.DataProvider", return_value=MagicMock())
    mocker.patch("core.plugin.manager.BackgroundTaskManager", side_effect=RuntimeError("线程池创建失败"))
    services = manager._create_plugin_services("plugin-task-error")
    snapshot = manager.get_service_health("plugin-task-error")
    assert services.task_manager is None
    assert snapshot.status is HealthStatus.UNAVAILABLE
    assert snapshot.error_code is HealthErrorCode.RESOURCE


def test_mcp_failure_marks_degraded_and_logs_reason(mocker):
    """MCP 初始化失败必须记录原因并形成降级状态。"""
    manager = PluginManager()
    _patch_optional_dependencies(mocker, manager)
    mocker.patch("core.plugin.manager.DataProvider", return_value=MagicMock())
    mocker.patch("core.plugin.manager.BackgroundTaskManager", return_value=MagicMock())
    mocker.patch.object(manager, "_get_mcp_manager", side_effect=ConnectionError("MCP 地址不可达"))
    services = manager._create_plugin_services("plugin-mcp-error")
    snapshot = manager.get_service_health("plugin-mcp-error")
    assert services.mcp_manager is None
    assert snapshot.status is HealthStatus.DEGRADED
    assert snapshot.error_code is HealthErrorCode.NETWORK


def test_exception_classification_and_secret_redaction():
    """异常分类明确，健康信息不得泄露令牌、API Key 或密码。"""
    assert classify_exception(PermissionError("拒绝")) is HealthErrorCode.PERMISSION
    assert classify_exception(OSError("磁盘")) is HealthErrorCode.RESOURCE
    message = sanitize_health_message(
        "Authorization: Bearer abcdef api_key=secret123 token:abcd password = xyz"
    )
    for secret in ("abcdef", "secret123", "abcd", "xyz"):
        assert secret not in message
    assert "[已脱敏]" in message


def test_production_manager_does_not_import_magicmock():
    """生产插件管理器不得再导入 MagicMock 作为服务降级替身。"""
    manager_path = Path(__file__).resolve().parents[3] / "core" / "plugin" / "manager.py"
    tree = ast.parse(manager_path.read_text(encoding="utf-8"))
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "unittest.mock"
        for alias in node.names
    }
    assert "MagicMock" not in imported_names


def test_health_issue_ui_contains_capability_and_recovery():
    """启动提示应包含受影响能力、原因和恢复建议，并执行脱敏。"""
    snapshot = HealthSnapshot(
        status=HealthStatus.UNAVAILABLE,
        error_code=HealthErrorCode.PERSISTENCE,
        message="data_provider: token=secret-value 数据库不可用",
        timestamp=datetime.now(timezone.utc),
        correlation_id="corr-1",
    )
    text = InstructionXMainWindow._format_service_health_issue(
        "示例插件", snapshot, ["data_provider"]
    )
    assert "示例插件" in text
    assert "data_provider" in text
    assert "恢复建议" in text
    assert "secret-value" not in text


def test_unknown_plugin_health_is_not_healthy():
    """未注册插件不得被默认当成健康。"""
    manager = PluginManager()
    snapshot = manager.get_service_health("not-registered")
    assert snapshot.status is HealthStatus.UNKNOWN
