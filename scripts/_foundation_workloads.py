# -*- coding: utf-8 -*-
"""Task 0 五类固定负载的真实组件与受控算法测量。"""

import asyncio
import gc
import math
import os
import socket
import threading
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from core.data.data_provider import DataProvider
from core.data.sqlite_backend import SQLiteBackend
from core.mcp.server import MCPHostServer
from core.task.background_task import BackgroundTaskManager
from core.task.task_storage import TaskStorage
from _foundation_benchmark_common import (
    MILLISECONDS_PER_SECOND,
    make_metric,
    make_workload,
    process_rss_bytes,
)

LATENCY_SAMPLES = 12
SEED_KEY_COUNT = 100
PAYLOAD_BYTES = 1024
LONG_TASK_COUNT = 32
CHART_FRAMES = 1000
CHART_POINTS_PER_FRAME = 60
CHART_WINDOW_POINTS = 600
CHART_BUCKETS = 100
CHART_PHASE_STEP = 0.01
SLOW_DISK_BYTES = 4096
SLOW_NETWORK_DELAY_SECONDS = 0.02
SLOW_DISK_DELAY_SECONDS = 0.01
MCP_CALL_TIMEOUT_SECONDS = 5.0
STARTUP_SLO_MS = 2000.0
SQLITE_WRITE_SLO_MS = 20.0
SQLITE_READ_SLO_MS = 5.0
EVENT_PUBLISH_SLO_MS = 5.0
TASK_SUBMIT_SLO_MS = 50.0
LONG_TASK_REGISTER_SLO_MS = 100.0
SHUTDOWN_SLO_MS = 15000.0
MEMORY_SLO_MIB = 512.0
CHART_ALGORITHM_SLO_MS = 1.0
MCP_CALL_SLO_MS = 100.0
MCP_LIFECYCLE_SLO_MS = 5000.0
MCP_WATCHER_CANCEL_TIMEOUT_SECONDS = 2.0
MCP_WATCHER_CORO_NAME = "_shutdown_watcher"
SLOW_IO_SLO_MS = 100.0
MEBIBYTE = 1024 * 1024


def run_workloads(workspace: Path) -> list[dict[str, Any]]:
    """按固定顺序执行五类负载，单个采集异常不会中断其余项目。"""
    builders = (
        ("idle", run_idle),
        ("typical_desktop", run_typical_desktop),
        ("long_running_32", run_long_running_tasks),
        ("chart_1khz", run_chart_algorithm),
        ("slow_io", run_slow_io),
    )
    results = []
    for workload_id, builder in builders:
        try:
            results.append(builder(workspace))
        except Exception as error:
            results.append(_failed_workload(workload_id, error))
    return results


def _failed_workload(workload_id: str, error: Exception) -> dict[str, Any]:
    """把采集异常明确记为失败，不伪造样本。"""
    metric = make_metric("collection_latency", [], STARTUP_SLO_MS, "采集器执行异常，无有效样本")
    metric["status"] = "FAIL"
    result = make_workload(workload_id, "COLLECTION_ERROR", [metric], status="FAIL")
    result["error"] = f"{type(error).__name__}: {error}"
    return result


def run_idle(workspace: Path) -> dict[str, Any]:
    """测量隔离目录中的真实 SQLite 初始化与进程常驻内存。"""
    samples = []
    for index in range(LATENCY_SAMPLES):
        samples.append(_measure_backend_startup(workspace / "idle" / str(index)))
    gc.collect()
    rss_samples = _memory_samples()
    metrics = [
        make_metric("core_data_startup", samples, STARTUP_SLO_MS, "新建 SQLiteBackend 并完成 ensure_database 的墙钟时间"),
        make_metric("idle_process_rss", rss_samples, MEMORY_SLO_MIB, "空闲采集点 Windows 进程工作集", "MiB"),
    ]
    return make_workload("idle", "REAL_SQLITE_NON_GUI", metrics, {"new_databases": LATENCY_SAMPLES})


def _measure_backend_startup(directory: Path) -> float:
    """测量一次真实数据库创建并确保关闭连接。"""
    backend = SQLiteBackend(str(directory), "data.json")
    started = time.perf_counter()
    try:
        backend.ensure_database()
        return (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    finally:
        backend.close()


def _memory_samples() -> list[float]:
    """内存不可读时返回空样本，禁止用零值伪造成通过。"""
    rss = process_rss_bytes()
    return [] if rss is None else [rss / MEBIBYTE]


def run_typical_desktop(workspace: Path) -> dict[str, Any]:
    """测量真实 DataProvider 与 MCP，全部指标就绪后统一派生状态。"""
    with _provider_session(workspace / "typical") as provider:
        provider.register_plugin("benchmark-plugin", "benchmark")
        _seed_provider(provider)
        writes = _measure_calls(lambda index: provider.set_plugin_data("benchmark-plugin", "key", index))
        reads = _measure_calls(lambda index: provider.get_plugin_data("benchmark-plugin", f"seed-{index % SEED_KEY_COUNT}"))
        provider.subscribe("benchmark-subscriber", "benchmark-plugin", "event", _noop_subscriber)
        events = _measure_calls(lambda index: provider.publish("benchmark-plugin", "event", index))
    metrics = _typical_storage_metrics(writes, reads, events)
    mcp_metrics, mcp_error = _collect_mcp_metrics()
    metrics.extend(mcp_metrics)
    workload = make_workload("typical_desktop", "REAL_CORE_AND_LOOPBACK_MCP", metrics, _typical_scale())
    if mcp_error is not None:
        workload["mcp_error"] = mcp_error
    return workload


def _make_provider(directory: Path) -> DataProvider:
    """在指定隔离目录创建新的 DataProvider 单例。"""
    DataProvider._instance = None
    return DataProvider(str(directory), "data.json")


@contextmanager
def _provider_session(directory: Path) -> Iterator[DataProvider]:
    """在所有异常路径关闭完整或半初始化连接并清空单例。"""
    try:
        yield _make_provider(directory)
    finally:
        provider = DataProvider._instance
        backend = getattr(provider, "_backend", None)
        try:
            if backend is not None:
                backend.close()
        finally:
            DataProvider._instance = None


def _seed_provider(provider: DataProvider) -> None:
    """写入固定规模、固定长度的确定性数据。"""
    payload = "x" * PAYLOAD_BYTES
    for index in range(SEED_KEY_COUNT):
        provider.set_plugin_data("benchmark-plugin", f"seed-{index}", payload)


def _noop_subscriber(publisher_id: str, key: str, old_value: Any, new_value: Any) -> None:
    """空订阅者用于隔离发布分发开销。"""


def _measure_calls(operation: Callable[[int], Any], count: int = LATENCY_SAMPLES) -> list[float]:
    """以 perf_counter 测量同步调用墙钟毫秒。"""
    samples = []
    for index in range(count):
        started = time.perf_counter()
        operation(index)
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples


def _typical_storage_metrics(writes: list[float], reads: list[float], events: list[float]) -> list[dict[str, Any]]:
    """生成典型桌面的存储和事件指标。"""
    return [
        make_metric("sqlite_write", writes, SQLITE_WRITE_SLO_MS, "DataProvider.set_plugin_data 单键私有写入"),
        make_metric("sqlite_read", reads, SQLITE_READ_SLO_MS, "DataProvider.get_plugin_data 固定键读取"),
        make_metric("event_publish", events, EVENT_PUBLISH_SLO_MS, "DataProvider.publish 同步通知一个空订阅者"),
    ]


def _typical_scale() -> dict[str, Any]:
    """返回典型桌面固定数据规模。"""
    return {
        "seed_keys": SEED_KEY_COUNT,
        "payload_bytes_per_key": PAYLOAD_BYTES,
        "operations_per_metric": LATENCY_SAMPLES,
        "mcp_tool_calls": LATENCY_SAMPLES,
    }


def _collect_mcp_metrics() -> tuple[list[dict[str, Any]], str | None]:
    """返回完整 MCP 指标和错误证据，不提前修改负载状态。"""
    try:
        return _measure_local_mcp(), None
    except Exception as error:
        metric = make_metric("mcp_lifecycle", [], MCP_LIFECYCLE_SLO_MS, "本地 MCP 执行失败，无有效样本")
        metric["status"] = "FAIL"
        return [metric], f"{type(error).__name__}: {error}"


class McpServerStopError(RuntimeError):
    """保留 watcher 取消错误与随后 Server 停止错误的复合异常。"""

    def __init__(
        self,
        cancel_error: Exception | None,
        stop_error: Exception | None,
    ) -> None:
        """分别保存两类错误，避免后续 stop 覆盖原始取消失败。"""
        self.cancel_error = cancel_error
        self.stop_error = stop_error
        super().__init__(
            f"watcher 取消错误={cancel_error}; Server 停止错误={stop_error}"
        )


class McpServerLifecycle:
    """在 Task 0 内协调 Server loop 的 SSE watcher 与停止时序。"""

    def __init__(self, server: MCPHostServer) -> None:
        """保存 Server、loop 和 watcher 证据，不修改 core 生命周期。"""
        self._server = server
        self._loop = None
        self._loop_factory = None
        self._watcher_tasks = []

    def start(self) -> None:
        """短暂捕获 Server 后台线程创建的 loop，启动后立即恢复工厂。"""
        self._loop_factory = asyncio.new_event_loop
        asyncio.new_event_loop = self._new_event_loop
        try:
            self._server.run_http()
        finally:
            asyncio.new_event_loop = self._loop_factory

    def _new_event_loop(self) -> asyncio.AbstractEventLoop:
        """只记录属于当前 Server 线程的 loop。"""
        loop = self._loop_factory()
        if threading.current_thread() is self._server._thread:
            self._loop = loop
        return loop

    def stop(self) -> None:
        """取消失败也继续停止 Server，并分别保留取消与停止错误。"""
        cancel_error = None
        try:
            self._cancel_watchers()
        except Exception as error:
            cancel_error = error
        stop_error = None
        try:
            self._server.stop()
        except Exception as error:
            stop_error = error
        if cancel_error is not None or stop_error is not None:
            raise McpServerStopError(cancel_error, stop_error) from (
                cancel_error or stop_error
            )
        self.assert_no_pending_watchers()

    def _cancel_watchers(self) -> None:
        """在 watcher 所属 loop 执行取消和 gather，禁止跨 loop 关闭。"""
        if self._loop is None or self._loop.is_closed():
            return
        future = asyncio.run_coroutine_threadsafe(
            self._cancel_watchers_on_loop(), self._loop
        )
        future.result(timeout=MCP_WATCHER_CANCEL_TIMEOUT_SECONDS)

    async def _cancel_watchers_on_loop(self) -> None:
        """取消当前 loop 的 SSE watcher 并等待完成回调。"""
        tasks = _pending_shutdown_watchers(self._loop)
        self._watcher_tasks.extend(
            task for task in tasks if task not in self._watcher_tasks
        )
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def pending_watchers(self) -> list[asyncio.Task]:
        """返回已跟踪及 loop 内尚未完成的 watcher，供自检和停止判定。"""
        candidates = list(self._watcher_tasks)
        if self._loop is not None and not self._loop.is_closed():
            candidates.extend(_pending_shutdown_watchers(self._loop))
        return [task for task in dict.fromkeys(candidates) if not task.done()]

    def assert_no_pending_watchers(self) -> None:
        """停止后仍有 watcher 时显式失败，不能只看 cleanup_error。"""
        pending = self.pending_watchers()
        if pending:
            raise RuntimeError(f"MCP Server 停止后仍有 {len(pending)} 个 SSE watcher pending")


def _pending_shutdown_watchers(loop: asyncio.AbstractEventLoop) -> list[asyncio.Task]:
    """枚举指定 loop 中的 SSE shutdown watcher。"""
    return [
        task for task in asyncio.all_tasks(loop)
        if getattr(task.get_coro(), "__qualname__", "") == MCP_WATCHER_CORO_NAME
    ]


def _measure_local_mcp() -> list[dict[str, Any]]:
    """测量 MCPHostServer 真实回环启动、工具调用与停止。"""
    port = _available_loopback_port()
    server = MCPHostServer(name="foundation-benchmark", host="127.0.0.1", port=port)
    server._register_tool_direct("benchmark_echo", "基线回显", {}, benchmark_echo)
    lifecycle = McpServerLifecycle(server)
    started = time.perf_counter()
    try:
        lifecycle.start()
        startup_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
        calls = asyncio.run(_measure_mcp_calls(f"http://127.0.0.1:{port}/mcp"))
    finally:
        started = time.perf_counter()
        lifecycle.stop()
        shutdown_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    return [
        make_metric("mcp_startup", [startup_ms], MCP_LIFECYCLE_SLO_MS, "MCPHostServer.run_http 等待启动确认"),
        make_metric("mcp_roundtrip", calls, MCP_CALL_SLO_MS, "MCP ClientSession 经 127.0.0.1 调用 benchmark_echo"),
        make_metric("mcp_shutdown", [shutdown_ms], MCP_LIFECYCLE_SLO_MS, "MCPHostServer.stop 至工作线程退出"),
    ]


async def benchmark_echo() -> str:
    """本地 MCP 基准工具，不调用插件或外部服务。"""
    return "ok"


def _available_loopback_port() -> int:
    """从操作系统获取临时回环端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _measure_mcp_calls(url: str) -> list[float]:
    """通过真实 MCP SDK 测量固定次数工具调用。"""
    async with streamablehttp_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await _timed_mcp_calls(session)


async def _timed_mcp_calls(session: ClientSession) -> list[float]:
    """在已初始化会话中测量工具调用并检查协议错误。"""
    samples = []
    for _ in range(LATENCY_SAMPLES):
        started = time.perf_counter()
        result = await asyncio.wait_for(session.call_tool("benchmark_echo", {}), MCP_CALL_TIMEOUT_SECONDS)
        if result.isError:
            raise RuntimeError(f"MCP 工具返回错误：{result.content}")
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples


_LONG_TASK_STOP_EVENT = threading.Event()


def run_long_running_tasks(workspace: Path) -> dict[str, Any]:
    """以真实管理器注册 32 个协作退出的长期任务并测量关闭。"""
    manager = _make_task_manager(workspace / "tasks")
    _LONG_TASK_STOP_EVENT.clear()
    try:
        async_samples = _measure_async_submissions(manager)
        long_samples = _register_long_tasks(manager)
        rss_samples = _memory_samples()
        started = time.perf_counter()
        manager.shutdown()
        shutdown_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    finally:
        if BackgroundTaskManager._instance is not None:
            manager.shutdown()
        TaskStorage._instance = None
    metrics = [
        make_metric("async_task_submit", async_samples, TASK_SUBMIT_SLO_MS, "BackgroundTaskManager.register_async_task 提交并等待完成"),
        make_metric("long_task_register", long_samples, LONG_TASK_REGISTER_SLO_MS, "注册 32 个长期任务的单次墙钟时间"),
        make_metric("long_task_process_rss", rss_samples, MEMORY_SLO_MIB, "32 个长期任务注册后的进程工作集", "MiB"),
        make_metric("task_manager_shutdown", [shutdown_ms], SHUTDOWN_SLO_MS, "协作停止 32 个长期任务并关闭线程池"),
    ]
    scale = {"long_running_tasks": LONG_TASK_COUNT, "async_tasks": LATENCY_SAMPLES, "executor_workers": manager.DEFAULT_MAX_WORKERS}
    return make_workload("long_running_32", "REAL_BACKGROUND_TASK_MANAGER", metrics, scale)


def _make_task_manager(directory: Path) -> BackgroundTaskManager:
    """把任务存储单例定向到隔离目录后创建真实管理器。"""
    TaskStorage._instance = None
    BackgroundTaskManager._instance = None
    TaskStorage._instance = TaskStorage(str(directory))
    return BackgroundTaskManager()


def _measure_async_submissions(manager: BackgroundTaskManager) -> list[float]:
    """测量异步任务提交并等待对应 Future 完成。"""
    samples = []
    for index in range(LATENCY_SAMPLES):
        started = time.perf_counter()
        task_id = manager.register_async_task("benchmark", f"async-{index}", _noop_task)
        if task_id is None:
            raise RuntimeError("异步任务注册被拒绝")
        manager._futures[task_id].result(timeout=MCP_CALL_TIMEOUT_SECONDS)
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples


def _noop_task() -> None:
    """空调用用于测量调度而不是业务计算。"""


def _register_long_tasks(manager: BackgroundTaskManager) -> list[float]:
    """注册固定数量长期任务，模块级回调可安全序列化。"""
    samples = []
    for index in range(LONG_TASK_COUNT):
        started = time.perf_counter()
        task_id = manager.register_long_running_task(
            "benchmark", f"long-{index}", _long_task_body,
            stop_callback=_release_long_tasks, auto_restart=False,
        )
        if task_id is None:
            raise RuntimeError("长期任务注册被拒绝")
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples


def _release_long_tasks() -> None:
    """通知全部基准长期任务协作退出。"""
    _LONG_TASK_STOP_EVENT.set()


def _long_task_body() -> None:
    """长期任务阻塞等待协作退出，不执行忙循环。"""
    _LONG_TASK_STOP_EVENT.wait()


def run_chart_algorithm(workspace: Path) -> dict[str, Any]:
    """仅测量 1kHz 数据更新与降采样算法，不创建 Qt GUI、不报告 fps。"""
    retained = deque(maxlen=CHART_FRAMES * CHART_POINTS_PER_FRAME)
    samples = []
    for frame in range(CHART_FRAMES):
        started = time.perf_counter()
        _append_chart_frame(retained, frame)
        _downsample_minmax(list(retained)[-CHART_WINDOW_POINTS:], CHART_BUCKETS)
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    metric = make_metric("chart_algorithm_update", samples, CHART_ALGORITHM_SLO_MS, "每帧追加 60 点并对最近 600 点做 100 桶 min/max 降采样；非 GUI")
    scale = {
        "frames": CHART_FRAMES,
        "input_samples": CHART_FRAMES * CHART_POINTS_PER_FRAME,
        "points_per_frame": CHART_POINTS_PER_FRAME,
        "downsample_window": CHART_WINDOW_POINTS,
        "buckets": CHART_BUCKETS,
    }
    return make_workload("chart_1khz", "ALGORITHM_ONLY_NO_QT_GUI", [metric], scale)


def _append_chart_frame(retained: deque[float], frame: int) -> None:
    """追加确定性的正弦波输入点。"""
    for offset in range(CHART_POINTS_PER_FRAME):
        position = frame * CHART_POINTS_PER_FRAME + offset
        retained.append(math.sin(position * CHART_PHASE_STEP))


def _downsample_minmax(values: Sequence[float], bucket_count: int) -> list[float]:
    """执行确定性的分桶最小/最大降采样。"""
    bucket_size = max(1, math.ceil(len(values) / bucket_count))
    result = []
    for start in range(0, len(values), bucket_size):
        bucket = values[start:start + bucket_size]
        result.extend((min(bucket), max(bucket)))
    return result


def run_slow_io(workspace: Path) -> dict[str, Any]:
    """以本地 sleeper 和真实临时文件测量慢网络/慢盘模型。"""
    network = _measure_calls(lambda index: threading.Event().wait(SLOW_NETWORK_DELAY_SECONDS))
    disk_directory = workspace / "slow-disk"
    disk_directory.mkdir(parents=True, exist_ok=True)
    disk = _measure_calls(lambda index: _slow_file_write(disk_directory / "payload.bin"))
    metrics = [
        make_metric("slow_network_response", network, SLOW_IO_SLO_MS, "本地 Event.wait 固定等待 20ms；不访问网络"),
        make_metric("slow_disk_write", disk, SLOW_IO_SLO_MS, "固定等待 10ms 后写 4KiB、flush 并 fsync 到 temp"),
    ]
    scale = {"operations_per_metric": LATENCY_SAMPLES, "disk_payload_bytes": SLOW_DISK_BYTES}
    return make_workload("slow_io", "CONTROLLED_SLEEPER_AND_REAL_TEMP_FILE", metrics, scale)


def _slow_file_write(path: Path) -> None:
    """执行受控慢盘写入，数据只落在隔离目录。"""
    threading.Event().wait(SLOW_DISK_DELAY_SECONDS)
    with path.open("wb") as stream:
        stream.write(b"x" * SLOW_DISK_BYTES)
        stream.flush()
        os.fsync(stream.fileno())
