"""应用统一生命周期与插件资源回收测试。"""

import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.application_lifecycle import ApplicationLifecycle, LifecycleServices
from core.plugin.manager import PluginManager


EXPECTED_ORDER = [
    "stop_external_calls",
    "stop_new_tasks",
    "cancel_plugin_tasks",
    "close_mcp",
    "unload_plugins",
    "stop_task_manager",
    "close_llm",
    "flush_usage",
    "close_data_provider",
    "close_ui",
]


def _services(recorder):
    """按统一顺序记录各关闭步骤的测试依赖。"""
    return LifecycleServices(
        task_manager=SimpleNamespace(
            stop_accepting_tasks=lambda: recorder.append("stop_new_tasks"),
            shutdown=lambda: recorder.append("stop_task_manager"),
        ),
        plugin_manager=SimpleNamespace(
            cancel_all_plugin_tasks=lambda: recorder.append("cancel_plugin_tasks"),
            shutdown_plugins=lambda: recorder.append("unload_plugins"),
        ),
        mcp_manager=SimpleNamespace(
            stop_server=lambda: recorder.append("stop_external_calls"),
            shutdown=lambda: recorder.append("close_mcp"),
        ),
        llm_provider=SimpleNamespace(close=lambda: recorder.append("close_llm")),
        usage_store=SimpleNamespace(flush=lambda: recorder.append("flush_usage")),
        data_provider=SimpleNamespace(close=lambda: recorder.append("close_data_provider")),
        close_ui=lambda: recorder.append("close_ui"),
    )


def test_shutdown_order_and_report_are_complete():
    """所有资源按固定顺序关闭，报告包含每一步耗时与成功状态。"""
    recorder = []
    report = ApplicationLifecycle(_services(recorder)).shutdown()
    assert recorder == EXPECTED_ORDER
    assert [step.name for step in report.steps] == EXPECTED_ORDER
    assert report.success
    assert all(step.elapsed_ms >= 0 for step in report.steps)


def test_step_failure_does_not_skip_remaining_cleanup():
    """MCP 和 DataProvider 失败仍继续 LLM、存储和 UI 清理。"""
    recorder = []
    services = _services(recorder)
    def fail_mcp():
        recorder.append("close_mcp")
        raise RuntimeError("MCP 不响应")
    def fail_data():
        recorder.append("close_data_provider")
        raise OSError("磁盘写失败")
    services.mcp_manager.shutdown = fail_mcp
    services.data_provider.close = fail_data
    report = ApplicationLifecycle(services).shutdown()
    assert recorder == EXPECTED_ORDER
    assert not report.success
    failed_names = {step.name for step in report.steps if step.error}
    assert failed_names == {"close_mcp", "close_data_provider"}


def test_shutdown_global_deadline_is_enforced():
    """外部服务阻塞超过全局截止期时返回 TIMEOUT，并继续后续步骤。"""
    recorder = []
    services = _services(recorder)

    def blocking_stop():
        recorder.append("stop_external_calls")
        time.sleep(0.1)

    services.mcp_manager.stop_server = blocking_stop
    started = time.monotonic()
    report = ApplicationLifecycle(services).shutdown(timeout=0.02)
    assert time.monotonic() - started < 0.09
    assert report.timed_out
    assert not report.success
    assert recorder[-1] == "close_ui"
    assert report.steps[0].status == "timeout"


def test_repeated_shutdown_is_idempotent():
    """第二次关闭不得重复释放资源。"""
    recorder = []
    lifecycle = ApplicationLifecycle(_services(recorder))
    first = lifecycle.shutdown()
    second = lifecycle.shutdown()
    assert first.success and second.success
    assert recorder == EXPECTED_ORDER
    assert all(step.status == "skipped" for step in second.steps)


def test_release_plugin_resources_cancels_tasks_and_unregisters(mocker):
    """插件卸载必须回收任务、订阅和 API，并返回结构化回收结果。"""
    manager = PluginManager()
    plugin = SimpleNamespace(
        plugin_id="plugin-1",
        plugin_name="示例插件",
        on_plugin_unloaded=lambda: None,
        _plugin_dir=None,
        _cached_widget=None,
        _cached_parent=None,
    )
    task_manager = MagicMock()
    task_manager.cancel_tasks_by_plugin.return_value = {"cancelled": 2, "unfinished": 0}
    plugin._services = SimpleNamespace(task_manager=task_manager)
    manager._plugin_registry[plugin.plugin_id] = plugin
    manager._plugin_name_to_id[plugin.plugin_name] = plugin.plugin_id
    manager._thirdparty_plugins.append(plugin)
    manager._api_registry[plugin.plugin_id] = SimpleNamespace(api_methods={})
    data_provider = MagicMock()
    mocker.patch("core.plugin.manager.DataProvider", return_value=data_provider)
    mocker.patch("core.plugin.manager.get_language_manager")
    report = manager.release_plugin_resources(plugin.plugin_id)
    assert report.success
    task_manager.cancel_tasks_by_plugin.assert_called_once_with("plugin-1")
    data_provider._remove_subscriptions_for_plugin.assert_called_once_with("plugin-1")
    assert plugin.plugin_id not in manager._api_registry
