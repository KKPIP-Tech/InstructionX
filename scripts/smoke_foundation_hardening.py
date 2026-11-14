# -*- coding: utf-8 -*-
"""Task 0 基线采集器快速自检；只写 temp，失败时退出非零。"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / "temp"
os.environ["INSTRUCTIONX_LOG_DIR"] = str(TEMP_ROOT / "foundation-smoke-logs")

import _foundation_benchmark_common as common  # noqa: E402
import _foundation_faults as faults  # noqa: E402
import _foundation_workloads as workloads  # noqa: E402
import benchmark_foundation as benchmark  # noqa: E402
from _foundation_benchmark_common import (  # noqa: E402
    FAULT_IDS,
    WORKLOAD_IDS,
    build_report,
    compare_reports,
    isolated_workspace,
    make_fault,
    make_metric,
    make_workload,
    summarize_samples,
    validate_report,
    write_report,
)
from _foundation_faults import (  # noqa: E402
    _call_after_server_stop,
    fault_database_locked,
    fault_database_readonly,
    fault_plugin_exception,
    fault_provider_timeout,
    fault_slow_subscriber,
)
from _foundation_workloads import _provider_session, run_typical_desktop  # noqa: E402
from core.data.data_provider import DataProvider  # noqa: E402


CheckFunction = Callable[[], None]

IMPORT_PROBE_SOURCE = '''
import logging.handlers
from pathlib import Path

opened = []
real_logs = Path({real_logs!r}).resolve()
temp_root = Path({temp_root!r}).resolve()
original_handler = logging.handlers.RotatingFileHandler

class GuardHandler(original_handler):
    def __init__(self, filename, *args, **kwargs):
        path = Path(filename).resolve()
        if path.is_relative_to(real_logs):
            raise RuntimeError(f"导入期打开真实日志: {{path}}")
        opened.append(path)
        super().__init__(filename, *args, **kwargs)

logging.handlers.RotatingFileHandler = GuardHandler
import benchmark_foundation as benchmark

assert opened, "导入探针未捕获日志 handler"
benchmark._cleanup_import_logging()
assert all(path.is_relative_to(temp_root) for path in opened)
assert all(not path.parent.exists() for path in opened), "导入期日志目录未清理"
print("IMPORT_PROBE_OK")
'''


def check_statistics() -> None:
    """校验最近秩百分位、空样本和非法样本处理。"""
    stats = summarize_samples([1.0, 2.0, 3.0, 4.0])
    assert stats == {"p50": 2.0, "p95": 4.0, "p99": 4.0, "max": 4.0, "sample_count": 4}
    empty = summarize_samples([])
    assert empty["sample_count"] == 0 and empty["p50"] is None
    try:
        summarize_samples([float("nan")])
    except ValueError:
        return
    raise AssertionError("NaN 样本必须被拒绝")


def check_empty_metrics() -> None:
    """空指标列表必须 NOT_RUN，报告不得接受其 PASS 状态。"""
    assert common.derive_item_status([]) == "NOT_RUN"
    assert common.derive_fault_status(True, []) == "NOT_RUN"
    report = make_contract_report()
    report["workloads"][0]["metrics"] = []
    report["workloads"][0]["status"] = "PASS"
    try:
        validate_report(report)
    except ValueError:
        return
    raise AssertionError("空指标列表为 PASS 时报告校验必须失败")


def make_contract_report() -> dict:
    """构造覆盖全部固定负载与故障 ID 的最小合法报告。"""
    metric = make_metric("latency_ms", [1.0, 2.0, 3.0], 5.0, "自检固定样本")
    workloads = [make_workload(item, "REAL_CORE", [metric]) for item in WORKLOAD_IDS]
    faults = [
        make_fault(item, "P0" if item == "database_corruption" else "P1", "FAIL", [metric])
        for item in FAULT_IDS
    ]
    return build_report(
        environment={"python": {"version": sys.version}},
        configuration={"latency_samples": 3},
        workloads=workloads,
        faults=faults,
        not_run=[{"id": "real_gui_chart", "status": "NOT_RUN", "reason": "自检占位"}],
    )


def check_status_aggregation() -> None:
    """校验 MCP 后派生、行为与 SLO 联合判定和失败汇总。"""
    failed = make_metric("mcp_roundtrip", [500.0], 100.0, "行为正常但延迟越界")
    with isolated_workspace("smoke-status") as workspace:
        with patch("_foundation_workloads._measure_local_mcp", return_value=[failed]):
            workload = run_typical_desktop(workspace)
    assert workload["status"] == "FAIL"
    assert common.derive_fault_status(True, [failed]) == "FAIL"
    passed = make_metric("latency", [1.0], 5.0, "正常指标")
    assert common.derive_fault_status(False, [passed]) == "FAIL"
    report = make_contract_report()
    report["fault_matrix"][0] = make_fault("database_corruption", "P0", "PASS", [failed])
    failures = common._current_failures(report["workloads"], report["fault_matrix"])
    assert any(item["id"] == "database_corruption" for item in failures)


def check_comparison() -> None:
    """校验数值、状态以及 old/new 分别为 None 的比较。"""
    baseline = make_contract_report()
    current = make_contract_report()
    _replace_idle_metric(baseline, make_metric("latency_ms", [5.0, 15.0], 50.0, "基线"))
    _replace_idle_metric(current, make_metric("latency_ms", [10.0, 30.0], 50.0, "当前"))
    changed = _idle_difference(compare_reports(baseline, current))
    assert changed["regression"] is True and changed["delta_percent"] == 100.0
    _replace_idle_metric(baseline, make_metric("latency_ms", [], 50.0, "空基线"))
    old_none = _idle_difference(compare_reports(baseline, current))
    assert old_none["delta"] is None and old_none["numeric_comparable"] is False
    _replace_idle_metric(baseline, make_metric("latency_ms", [10.0, 30.0], 50.0, "有效基线"))
    _replace_idle_metric(current, make_metric("latency_ms", [], 50.0, "空当前"))
    new_none = _idle_difference(compare_reports(baseline, current))
    assert new_none["delta"] is None and new_none["numeric_comparable"] is False
    assert new_none["regression"] is True


def _idle_difference(comparison: dict) -> dict:
    """提取空闲负载的差异，避免排序影响自检。"""
    return next(
        item for item in comparison["metric_differences"]
        if item["id"] == "workload:idle:latency_ms"
    )


def _replace_idle_metric(report: dict, metric: dict) -> None:
    """替换空闲负载指标以构造比较边界。"""
    report["workloads"][0] = make_workload("idle", "REAL_CORE", [metric])


def check_provider_path() -> None:
    """校验 Provider 故障经过 LLMProvider 异常与恢复路径。"""
    with isolated_workspace("smoke-provider") as workspace:
        result = fault_provider_timeout(workspace)
    assert result["execution_scope"] == "REAL_LLM_PROVIDER_CONTROLLED_ADAPTER"
    assert result["status"] == "PASS"
    assert result["details"]["timeout_restored"] is True
    assert result["details"]["recovery_succeeded"] is True
    assert result["details"]["check_model_calls"] >= 2


class CleanupFailTransport:
    """模拟传输退出时发生清理异常。"""

    async def __aenter__(self):
        return object(), object(), None

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        raise RuntimeError("受控传输清理异常")


class DisconnectSession:
    """模拟已初始化会话在断连调用时超时。"""

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        return None

    async def initialize(self) -> None:
        """模拟初始化成功。"""

    async def call_tool(self, name: str, arguments: dict) -> None:
        """模拟断连调用超时。"""
        raise TimeoutError("受控断连")


class RunningServer:
    """模拟可被停止的本地 Server。"""

    def stop(self) -> None:
        """模拟停止成功。"""


async def _shutdown_watcher() -> None:
    """模拟 sse_starlette 的永久 watcher，名称必须与生产任务一致。"""
    await asyncio.Event().wait()


class LoopBackedServer:
    """模拟 core Server.stop 的 loop.stop/join/close 时序。"""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self.is_running = True
        self.thread = None

    def stop(self) -> None:
        """停止并关闭所属事件循环。"""
        self.is_running = False
        self._loop.call_soon_threadsafe(self._loop.stop)
        self.thread.join(timeout=2.0)
        self._loop.close()


async def _cancel_all_tasks(loop: asyncio.AbstractEventLoop) -> None:
    """在自检失败清理时取消并等待 loop 内全部任务。"""
    tasks = list(asyncio.all_tasks(loop))
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def check_mcp_watcher_cleanup() -> None:
    """真实创建 pending watcher，验证停止前取消、完成与关闭后无遗留。"""
    lifecycle_class = workloads.McpServerLifecycle
    loop = asyncio.new_event_loop()
    server = LoopBackedServer(loop)
    lifecycle = lifecycle_class(server)
    lifecycle._loop = loop
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    server.thread = thread
    holder = {}
    ready = threading.Event()
    thread.start()
    loop.call_soon_threadsafe(lambda: (holder.setdefault("task", loop.create_task(_shutdown_watcher())), ready.set()))
    try:
        assert ready.wait(timeout=2.0)
        assert lifecycle.pending_watchers()
        lifecycle.stop()
        assert holder["task"].done()
        assert not lifecycle.pending_watchers()
    finally:
        _cleanup_test_loop(loop, thread)


def _cleanup_test_loop(loop: asyncio.AbstractEventLoop, thread: threading.Thread) -> None:
    """即使断言失败也清理自检 loop，避免引入额外 pending 输出。"""
    if loop.is_closed():
        return
    asyncio.run_coroutine_threadsafe(_cancel_all_tasks(loop), loop).result(timeout=2.0)
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=2.0)
    loop.close()


class StopRecorder:
    """记录 stop 调用并可注入后续停止错误。"""

    def __init__(self, stop_error: Exception | None = None) -> None:
        self.stop_calls = 0
        self.is_running = True
        self._stop_error = stop_error

    def stop(self) -> None:
        self.stop_calls += 1
        self.is_running = False
        if self._stop_error is not None:
            raise self._stop_error


def check_watcher_stop_errors() -> None:
    """取消失败和超时也必须 stop，并保留取消与停止错误。"""
    cancel_error = RuntimeError("受控取消异常")
    server = StopRecorder()
    error = _stop_with_cancel_error(server, cancel_error)
    assert server.stop_calls == 1 and error.cancel_error is cancel_error
    timeout_error = TimeoutError("受控取消超时")
    stop_error = RuntimeError("受控停止异常")
    failing_server = StopRecorder(stop_error)
    combined = _stop_with_cancel_error(failing_server, timeout_error)
    assert failing_server.stop_calls == 1
    assert combined.cancel_error is timeout_error
    assert combined.stop_error is stop_error


def _stop_with_cancel_error(server: StopRecorder, cancel_error: Exception) -> Exception:
    """注入 watcher 取消错误并捕获生命周期停止异常。"""
    lifecycle = workloads.McpServerLifecycle(server)
    with patch.object(lifecycle, "_cancel_watchers", side_effect=cancel_error):
        try:
            lifecycle.stop()
        except Exception as error:
            return error
    raise AssertionError("取消失败必须产生可观测的停止异常")


class WorkingTransport:
    """模拟可正常进入和退出的传输。"""

    async def __aenter__(self):
        return object(), object(), None

    async def __aexit__(self, exc_type, exc_value, exc_tb):
        return None


class EnterFailTransport(WorkingTransport):
    """模拟进入传输上下文失败。"""

    async def __aenter__(self):
        raise RuntimeError("受控传输进入异常")


class InitializeFailSession(DisconnectSession):
    """模拟 Session 初始化失败。"""

    async def initialize(self) -> None:
        raise RuntimeError("受控初始化异常")


def check_mcp_preparation_errors() -> None:
    """校验 initialize 与传输进入失败均形成 COLLECTION_ERROR/FAIL。"""
    with patch("_foundation_faults.streamablehttp_client", return_value=WorkingTransport()):
        with patch("_foundation_faults.ClientSession", return_value=InitializeFailSession()):
            initialize_evidence = asyncio.run(_call_after_server_stop(1, RunningServer()))
    _assert_mcp_preparation_failure(initialize_evidence)
    with patch("_foundation_faults.streamablehttp_client", return_value=EnterFailTransport()):
        transport_evidence = asyncio.run(_call_after_server_stop(1, RunningServer()))
    _assert_mcp_preparation_failure(transport_evidence)


def _assert_mcp_preparation_failure(evidence: dict) -> None:
    """准备错误不得进入 NOT_RUN 或 PASS。"""
    assert evidence.get("preparation_error") is not None
    result = faults._mcp_preparation_failure(evidence)
    assert result["status"] == "FAIL"
    assert result["execution_scope"] == "COLLECTION_ERROR"
    assert result["metrics"][0]["status"] == "FAIL"


def check_mcp_cleanup() -> None:
    """校验主调用异常和传输清理异常均被保留。"""
    with patch("_foundation_faults.streamablehttp_client", return_value=CleanupFailTransport()):
        with patch("_foundation_faults.ClientSession", return_value=DisconnectSession()):
            evidence = asyncio.run(_call_after_server_stop(1, RunningServer()))
    assert evidence["error"] is not None
    assert evidence["cleanup_error"] is not None
    assert "受控传输清理异常" in str(evidence["cleanup_error"])


def check_import_log_isolation() -> None:
    """子进程探针证明导入期日志只进 temp，关闭后可删除目录。"""
    source = IMPORT_PROBE_SOURCE.format(
        real_logs=str(PROJECT_ROOT / "logs"),
        temp_root=str(TEMP_ROOT),
    )
    with isolated_workspace("smoke-import-log") as workspace:
        probe = workspace / "import_probe.py"
        probe.write_text(source, encoding="utf-8")
        environment = os.environ.copy()
        environment.pop("INSTRUCTIONX_LOG_DIR", None)
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(PROJECT_ROOT), str(PROJECT_ROOT / "scripts"))
        )
        result = subprocess.run(
            [sys.executable, str(probe)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            timeout=30.0,
            check=False,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT_PROBE_OK" in result.stdout


def check_baseline_path_isolation() -> None:
    """校验 baseline 在打开文件前即拒绝 temp 外路径。"""
    with patch("pathlib.Path.open", side_effect=AssertionError("禁止打开 temp 外文件")):
        try:
            benchmark._read_baseline(Path("data/data.db"))
        except ValueError:
            return
    raise AssertionError("temp 外 baseline 必须被拒绝")


def check_provider_cleanup() -> None:
    """校验 DataProvider 初始化后异常也关闭连接并清空单例。"""
    operations = (
        run_typical_desktop,
        fault_database_locked,
        fault_database_readonly,
        fault_slow_subscriber,
        fault_plugin_exception,
    )
    with isolated_workspace("smoke-provider-cleanup") as workspace:
        for index, operation in enumerate(operations):
            _check_one_provider_cleanup(operation, workspace / str(index))
        _check_close_failure_clears_singleton(workspace / "close-failure")
    _check_locker_close()


class RollbackFailLocker:
    """模拟回滚失败但可记录关闭的锁连接。"""

    def __init__(self) -> None:
        self.closed = False

    def rollback(self) -> None:
        raise RuntimeError("受控回滚异常")

    def close(self) -> None:
        self.closed = True


def _check_locker_close() -> None:
    """回滚异常不得跳过锁连接关闭。"""
    locker = RollbackFailLocker()
    try:
        faults._close_locker(locker)
    except RuntimeError as error:
        assert "受控回滚异常" in str(error)
    else:
        raise AssertionError("回滚异常必须继续抛出")
    assert locker.closed is True


def _check_close_failure_clears_singleton(directory: Path) -> None:
    """连接关闭自身失败时也必须清空单例并传播异常。"""
    DataProvider._instance = None
    provider = None
    with patch("core.data.sqlite_backend.SQLiteBackend.close", side_effect=RuntimeError("受控关闭异常")):
        try:
            with _provider_session(directory) as current_provider:
                provider = current_provider
        except RuntimeError as error:
            assert "受控关闭异常" in str(error)
        else:
            raise AssertionError("关闭异常必须继续抛出")
    leaked = DataProvider._instance
    if provider is not None:
        provider._backend.close()
    DataProvider._instance = None
    assert leaked is None


def _check_one_provider_cleanup(operation: Callable[[Path], dict], directory: Path) -> None:
    """对单个 DataProvider 场景注入注册异常并检查清理。"""
    DataProvider._instance = None
    with patch.object(DataProvider, "register_plugin", side_effect=RuntimeError("受控注册异常")):
        try:
            operation(directory)
        except RuntimeError as error:
            assert "受控注册异常" in str(error)
        else:
            raise AssertionError("注册异常必须继续抛出")
    leaked = DataProvider._instance
    backend = getattr(leaked, "_backend", None)
    if backend is not None:
        backend.close()
    DataProvider._instance = None
    assert leaked is None


def check_not_run_summary() -> None:
    """校验控制台汇总分别覆盖顶层、项目和指标 NOT_RUN。"""
    report = make_contract_report()
    missing = make_metric("unreadable", [], 1.0, "不可读")
    report["workloads"][0] = make_workload("idle", "REAL_CORE", [missing])
    report["fault_matrix"][0]["status"] = "NOT_RUN"
    summary = benchmark._not_run_summary(report)
    assert summary["top_level"] == 1
    assert summary["items"] == 2
    assert summary["metrics"] == 1


def check_json_and_temp() -> None:
    """校验机器可读输出、临时目录隔离与自动清理。"""
    report = make_contract_report()
    with isolated_workspace("smoke-output") as workspace:
        output = workspace / "report.json"
        write_report(report, output)
        validate_report(json.loads(output.read_text(encoding="utf-8")))
        marker = workspace / "marker.txt"
        marker.write_text("隔离数据", encoding="utf-8")
        assert output.is_relative_to(TEMP_ROOT) and marker.exists()
    assert not workspace.exists() and not marker.exists()


def check_fault_matrix_contract() -> None:
    """校验故障矩阵 ID、严重度、观察结果与统计字段完整。"""
    report = make_contract_report()
    assert {item["id"] for item in report["fault_matrix"]} == set(FAULT_IDS)
    for fault in report["fault_matrix"]:
        assert fault["severity"] in {"P0", "P1"}
        assert fault["observed"] and fault["expected"]
        assert fault["metrics"][0]["statistics"]["sample_count"] == 3


def run_check(name: str, function: CheckFunction) -> bool:
    """执行单项自检并输出中文结果。"""
    try:
        function()
    except Exception as error:
        print(f"[失败] {name}: {error}")
        traceback.print_exc()
        return False
    print(f"[通过] {name}")
    return True


def main() -> int:
    """运行全部快速自检，任何失败均返回 1。"""
    checks = [
        ("统计计算", check_statistics),
        ("空指标列表状态", check_empty_metrics),
        ("导入期日志隔离探针", check_import_log_isolation),
        ("状态聚合与失败汇总", check_status_aggregation),
        ("基线差异与 None 比较", check_comparison),
        ("LLMProvider 超时与恢复路径", check_provider_path),
        ("MCP 准备错误分类", check_mcp_preparation_errors),
        ("MCP watcher 完成与 pending 检测", check_mcp_watcher_cleanup),
        ("MCP 取消异常与停止保证", check_watcher_stop_errors),
        ("MCP 清理异常记录", check_mcp_cleanup),
        ("baseline 路径隔离", check_baseline_path_isolation),
        ("DataProvider 异常清理", check_provider_cleanup),
        ("NOT_RUN 分类汇总", check_not_run_summary),
        ("机器报告与临时目录", check_json_and_temp),
        ("故障矩阵记录", check_fault_matrix_contract),
    ]
    results = [run_check(name, function) for name, function in checks]
    print(f"自检完成：{sum(results)}/{len(results)} 项通过。")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
