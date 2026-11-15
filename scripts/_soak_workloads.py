"""长稳真实组件负载、GUI 突发入图和系统资源采样。"""

import ctypes
import math
import time
from collections import deque
from ctypes import wintypes
from pathlib import Path
from typing import Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from _foundation_workloads import (
    _available_loopback_port,
    _make_task_manager,
    _register_long_tasks,
    process_rss_bytes,
)
from core.data.data_provider import DataProvider
from core.mcp.client import MCPClientManager
from core.mcp.config import MCPRemoteServerConfig
from core.mcp.server import MCPHostServer
from core.observability.sanitize import sanitize_text
from core.task.background_task import BackgroundTaskManager
from core.task.task_storage import TaskStorage
import ui.uikit_bootstrap  # noqa: F401
from InstructionX_UIKit.charts import ChartWidget

GUI_POINTS_PER_BURST = 1000
GUI_WINDOW_POINTS = 20000
GUI_INTERVAL_SECONDS = 1.0 / 120.0
SOAK_MCP_REQUESTS_PER_MINUTE = 100000
COMPLETED_TASK_CLEANUP_INTERVAL = 100
PRECISE_WAIT_REMAINDER_SECONDS = 0.002


def _wait_until(deadline: float) -> None:
    """用短睡眠加有界自旋降低 Windows 定时器分辨率造成的速率偏差。"""
    remaining = deadline - time.perf_counter()
    if remaining > PRECISE_WAIT_REMAINDER_SECONDS:
        time.sleep(remaining - PRECISE_WAIT_REMAINDER_SECONDS)
    while time.perf_counter() < deadline:
        pass


def process_handle_count() -> int | None:
    """通过 Windows API 读取当前进程句柄数。"""
    try:
        count = wintypes.DWORD()
        if ctypes.windll.kernel32.GetProcessHandleCount(
            wintypes.HANDLE(-1), ctypes.byref(count)
        ):
            return int(count.value)
    except (AttributeError, OSError):
        return None
    return None


class SoakSeries:
    """有界延迟样本，防止长稳报告自身无限增长。"""

    def __init__(self, capacity: int = 4096):
        self._samples: Dict[str, deque] = {}
        self._capacity = capacity

    def add(self, name: str, value: float) -> None:
        if math.isfinite(value) and value >= 0:
            self._samples.setdefault(name, deque(maxlen=self._capacity)).append(value)

    def snapshot(self) -> Dict[str, Dict[str, float]]:
        result = {}
        for name, values in self._samples.items():
            ordered = sorted(values)
            result[name] = {
                "sample_count": len(ordered),
                "p50": self._percentile(ordered, 0.50),
                "p95": self._percentile(ordered, 0.95),
                "p99": self._percentile(ordered, 0.99),
                "max": ordered[-1],
            }
        return result

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        rank = max(1, math.ceil(percentile * len(values)))
        return values[rank - 1]


class _Registry:
    def __init__(self):
        self.tools = {}

    def register(self, name, description, parameters, handler):
        self.tools[name] = handler

    def unregister(self, name):
        self.tools.pop(name, None)


async def _soak_echo() -> str:
    return "ok"


class SoakComponents:
    """持有长稳真实存储、事件、任务和 MCP 组件并负责清理。"""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.errors = []
        self._provider = self._create_provider()
        self._task_manager = self._create_tasks()
        self._server = None
        self._client = None
        self._mcp_handler = None
        self._create_mcp()

    def _create_provider(self) -> DataProvider:
        DataProvider._instance = None
        provider = DataProvider(str(self.workspace / "data"), "data.json")
        provider.register_plugin("soak", "soak")
        provider.subscribe("slow", "soak", "event", self._slow_subscriber)
        provider.subscribe("fast", "soak", "event", lambda *args: None)
        return provider

    def _create_tasks(self) -> BackgroundTaskManager:
        TaskStorage._instance = None
        manager = _make_task_manager(self.workspace / "tasks")
        _register_long_tasks(manager)
        return manager

    def _create_mcp(self) -> None:
        port = _available_loopback_port()
        self._server = MCPHostServer(
            name="soak", host="127.0.0.1", port=port,
            max_requests_per_minute=SOAK_MCP_REQUESTS_PER_MINUTE,
        )
        self._server._register_tool_direct("soak_echo", "长稳回显", {}, _soak_echo)
        self._server.run_http()
        registry = _Registry()
        self._client = MCPClientManager(registry, timeout=2.0)
        self._mcp_config = MCPRemoteServerConfig(
            server_id="soak", name="Soak", transport="streamable-http",
            url=f"http://127.0.0.1:{port}/mcp",
        )
        self._client.connect(self._mcp_config)
        self._mcp_handler = registry.tools["mcp__soak__soak_echo"]

    @staticmethod
    def _slow_subscriber(*args) -> None:
        time.sleep(0.5)

    def cycle(self, index: int) -> Dict[str, float]:
        """执行一轮混合负载并返回各项毫秒延迟。"""
        if index % COMPLETED_TASK_CLEANUP_INTERVAL == 0:
            self._task_manager.clear_completed_tasks("soak")
        metrics = {}
        metrics["db_write"] = self._time_call(
            "db_write", lambda: self._provider.set_plugin_data("soak", "key", index)
        )
        metrics["db_read"] = self._time_call(
            "db_read", lambda: self._provider.get_plugin_data("soak", "key")
        )
        metrics["event_publish"] = self._time_call(
            "event_publish", lambda: self._provider.publish_async("soak", "event", index)
        )
        metrics["high_task"] = self._time_call("high_task", self._run_high_task)
        metrics["normal_task"] = self._time_call("normal_task", self._run_normal_task)
        metrics["mcp_roundtrip"] = self._time_call(
            "mcp_roundtrip", lambda: self._mcp_handler()
        )
        return metrics

    def _run_high_task(self) -> None:
        task_id = self._task_manager.register_priority_task("soak", "high", lambda: None)
        self._task_manager._futures[task_id].result(timeout=2)

    def _run_normal_task(self) -> None:
        task_id = self._task_manager.register_async_task("soak", "normal", lambda: None)
        self._task_manager._futures[task_id].result(timeout=2)

    def _time_call(self, name: str, operation) -> float:
        started = time.perf_counter()
        try:
            operation()
        except Exception as error:
            self.errors.append(f"{name}: {type(error).__name__}: {sanitize_text(error)}")
            if name == "mcp_roundtrip":
                self._reconnect_mcp()
        return (time.perf_counter() - started) * 1000

    def _reconnect_mcp(self) -> None:
        """断连后重建客户端 owner，失败继续保留显式错误。"""
        try:
            self._client.connect(self._mcp_config)
            self._mcp_handler = self._client._tool_registry.tools["mcp__soak__soak_echo"]
        except Exception as error:
            self.errors.append(f"mcp_reconnect: {type(error).__name__}: {sanitize_text(error)}")

    def queue_snapshot(self) -> Dict[str, int]:
        stats = self._task_manager._pools.supervisor.snapshot()
        return {
            "event_slow": self._provider.get_event_delivery_stats("slow").queued,
            **{f"task_{pool}": depth for pool, depth in stats["queue_depth"].items()},
        }

    def close(self) -> None:
        """按外部调用、任务、MCP、存储顺序清理，保留全部异常。"""
        for name, operation in (
            ("task", self._task_manager.shutdown),
            ("mcp_client", self._client.shutdown),
            ("mcp_server", self._server.stop),
            ("provider", self._provider.close),
        ):
            try:
                operation()
            except Exception as error:
                self.errors.append(f"close_{name}: {sanitize_text(error)}")
        DataProvider._instance = None
        BackgroundTaskManager._instance = None
        TaskStorage._instance = None


class GuiChartWorkload:
    """真实 Qt 20,000 点窗口的 1kHz 突发入图负载。"""

    def __init__(self):
        self.application = QApplication.instance() or QApplication([])
        self.chart = ChartWidget()
        self.chart.set_option({
            "xAxis": {"type": "value"}, "yAxis": {"type": "value"},
            "series": [{"type": "line", "name": "signal", "data": [], "gpuDirect": True}],
        })
        self.chart.show()
        self.session = self.chart.stream(
            "signal", window=GUI_WINDOW_POINTS,
            interval=GUI_INTERVAL_SECONDS, auto_scale=False,
        )
        self.session._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.application.processEvents()

    def burst(self) -> Dict[str, list[float]]:
        """执行一秒 1000 点输入并采集实际入图和帧间隔。"""
        # 只评价活跃突发，避免把两次负载之间的空闲等待误算成渲染帧间隔。
        self.session._apply_intervals.clear()
        self.session._last_apply_at = 0.0
        started = time.perf_counter()
        apply_samples = []
        seen_apply_times = set()
        for index in range(GUI_POINTS_PER_BURST):
            self.session.write(float(index))
            if index % 10 == 0:
                self.application.processEvents()
                self._capture_apply_sample(apply_samples, seen_apply_times)
            target = started + (index + 1) / GUI_POINTS_PER_BURST
            _wait_until(target)
        self.application.processEvents()
        self._capture_apply_sample(apply_samples, seen_apply_times)
        intervals = [value * 1000 for value in self.session._apply_intervals]
        return {
            "chart_apply_ms": apply_samples,
            "chart_interval_ms": intervals,
            "chart_interval_p99_ms": intervals,
        }

    def _capture_apply_sample(self, samples: list, seen_times: set) -> None:
        """按实际入图时间戳保留每次计算耗时，避免只取最后一次。"""
        timestamp = self.session._last_apply_at
        if timestamp and timestamp not in seen_times:
            seen_times.add(timestamp)
            samples.append(self.session.last_apply_seconds * 1000)

    def close(self) -> None:
        self.session.close()
        self.chart.close()
        self.chart.deleteLater()
        self.application.processEvents()
