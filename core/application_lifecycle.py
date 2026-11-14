"""应用级生命周期协调器，统一记录关闭顺序、异常和全局截止期。"""

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from core.data import DataProvider
from core.llm.llm_provider import LLMProvider
from core.llm.usage_record_store import get_usage_record_store
from core.plugin.manager import PluginManager
from core.task import BackgroundTaskManager


_STEP_NAMES = (
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
)


@dataclass(frozen=True, slots=True)
class LifecycleStepResult:
    """单个关闭步骤的结构化结果。"""

    name: str
    status: str
    elapsed_ms: float
    error: str = ""


@dataclass(frozen=True, slots=True)
class ShutdownReport:
    """完整关闭报告，success 仅在无失败和超时时为真。"""

    steps: List[LifecycleStepResult]
    timed_out: bool
    success: bool


@dataclass(slots=True)
class LifecycleServices:
    """生命周期依赖容器，测试可注入受控替身。"""

    task_manager: Any = None
    plugin_manager: Any = None
    mcp_manager: Any = None
    llm_provider: Any = None
    usage_store: Any = None
    data_provider: Any = None
    close_ui: Optional[Callable[[], None]] = None


class ApplicationLifecycle:
    """按固定顺序关闭应用资源，单步异常不阻断后续清理。"""

    DEFAULT_TIMEOUT = 15.0

    def __init__(self, services: Optional[LifecycleServices] = None):
        self._services = services or self._default_services()
        self._completed = False

    def shutdown(self, timeout: float = DEFAULT_TIMEOUT) -> ShutdownReport:
        """在全局截止期内执行关闭；重复调用只返回 skipped 报告。"""
        if self._completed:
            return self._skipped_report()
        started = time.monotonic()
        deadline = started + timeout
        steps = [
            self._run_step("stop_external_calls", self._stop_external, deadline),
            self._run_step("stop_new_tasks", self._stop_new_tasks, deadline),
            self._run_step("cancel_plugin_tasks", self._cancel_plugin_tasks, deadline),
            self._run_step("close_mcp", self._close_mcp, deadline),
            self._run_step("unload_plugins", self._unload_plugins, deadline, direct=True),
            self._run_step("stop_task_manager", self._stop_task_manager, deadline),
            self._run_step("close_llm", self._close_llm, deadline),
            self._run_step("flush_usage", self._flush_usage, deadline),
            self._run_step("close_data_provider", self._close_data_provider, deadline),
            self._run_step("close_ui", self._close_ui, deadline, direct=True),
        ]
        self._completed = True
        timed_out = any(step.status == "timeout" for step in steps)
        success = all(step.status in ("success", "skipped") for step in steps)
        return ShutdownReport(steps, timed_out, success)

    def _run_step(self, name, action, deadline, direct=False) -> LifecycleStepResult:
        """执行一步并隔离异常；UI 步骤在主线程，其他步骤受线程截止期约束。"""
        started = time.monotonic()
        if action is None:
            return LifecycleStepResult(name, "skipped", 0.0)
        remaining = max(0.0, deadline - started)
        if remaining == 0 and not direct:
            return LifecycleStepResult(name, "timeout", 0.0, "全局关闭截止期已耗尽")
        if direct:
            return self._run_direct_step(name, action, started)
        return self._run_bounded_step(name, action, started, remaining)

    @staticmethod
    def _run_direct_step(name, action, started) -> LifecycleStepResult:
        try:
            actual_action = action()
            if callable(actual_action):
                actual_action()
        except Exception as exc:
            return LifecycleStepResult(name, "failed", (time.monotonic() - started) * 1000, str(exc))
        return LifecycleStepResult(name, "success", (time.monotonic() - started) * 1000)

    def _run_bounded_step(self, name, action, started, timeout) -> LifecycleStepResult:
        outcome: Dict[str, str] = {}
        def invoke() -> None:
            try:
                actual_action = action()
                if callable(actual_action):
                    actual_action()
            except Exception as exc:
                outcome["error"] = str(exc)
        worker = threading.Thread(target=invoke, daemon=True, name=f"Lifecycle-{name}")
        worker.start()
        worker.join(timeout=timeout)
        elapsed = (time.monotonic() - started) * 1000
        if worker.is_alive():
            return LifecycleStepResult(name, "timeout", elapsed, "步骤超过全局截止期")
        if outcome:
            return LifecycleStepResult(name, "failed", elapsed, outcome["error"])
        return LifecycleStepResult(name, "success", elapsed)

    def _skipped_report(self) -> ShutdownReport:
        steps = [LifecycleStepResult(name, "skipped", 0.0) for name in _STEP_NAMES]
        return ShutdownReport(steps, False, True)

    def _stop_external(self):
        manager = self._services.mcp_manager
        return manager.stop_server if manager else None

    def _stop_new_tasks(self):
        manager = self._services.task_manager
        return manager.stop_accepting_tasks if manager else None

    def _cancel_plugin_tasks(self):
        manager = self._services.plugin_manager
        return manager.cancel_all_plugin_tasks if manager else None

    def _close_mcp(self):
        manager = self._services.mcp_manager
        return manager.shutdown if manager else None

    def _unload_plugins(self):
        manager = self._services.plugin_manager
        return manager.shutdown_plugins if manager else None

    def _stop_task_manager(self):
        manager = self._services.task_manager
        return manager.shutdown if manager else None

    def _close_llm(self):
        provider = self._services.llm_provider
        return provider.close if provider else None

    def _flush_usage(self):
        store = self._services.usage_store
        return store.flush if store else None

    def _close_data_provider(self):
        provider = self._services.data_provider
        return provider.close if provider else None

    def _close_ui(self):
        return self._services.close_ui

    @staticmethod
    def _default_services() -> LifecycleServices:
        # 延迟读取 MCP 单例，避免 core.plugin ↔ core.mcp 的既有循环依赖在应用入口提前触发
        from core.mcp.manager import _module_instance as mcp_instance
        return LifecycleServices(
            task_manager=BackgroundTaskManager._instance,
            plugin_manager=PluginManager._instance,
            mcp_manager=mcp_instance,
            llm_provider=LLMProvider._instance,
            usage_store=get_usage_record_store(),
            data_provider=DataProvider._instance,
        )
