# -*- coding: utf-8 -*-
"""Task 0 固定故障矩阵；所有副作用限定在 temp 与自愿退出子进程。"""

import asyncio
import errno
import os
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from contextlib import AsyncExitStack
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from unittest.mock import patch

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from core.data.data_provider import DataProvider, DataProviderError
from core.data.sqlite_backend import SQLiteBackend
from core.llm.exceptions import TimeoutError as LLMTimeoutError
from core.llm.llm_provider import LLMProvider
from core.llm.provider_interface import ChatResponse
from core.mcp.server import MCPHostServer
from core.task.task_storage import TaskStorage
from _foundation_benchmark_common import (
    MILLISECONDS_PER_SECOND,
    derive_fault_status,
    make_fault,
    make_metric,
)
from _foundation_workloads import (
    McpServerLifecycle,
    _available_loopback_port,
    _provider_session,
    benchmark_echo,
)

FAULT_SAMPLES = 5
PROVIDER_TIMEOUT_SAMPLES = 12
PROVIDER_ORIGINAL_TIMEOUT_SECONDS = 60.0
LOCK_BUSY_TIMEOUT_MS = 50
FAULT_DETECTION_SLO_MS = 200.0
READONLY_DETECTION_SLO_MS = 500.0
PROCESS_EXIT_SLO_MS = 5000.0
PROVIDER_TIMEOUT_SECONDS = 0.02
PROVIDER_TIMEOUT_SLO_MS = 100.0
MCP_DISCONNECT_TIMEOUT_SECONDS = 1.5
MCP_DISCONNECT_SLO_MS = 2000.0
SLOW_SUBSCRIBER_DELAY_SECONDS = 0.05
SLOW_SUBSCRIBER_SLO_MS = 10.0
PLUGIN_PUBLISH_SLO_MS = 5.0
VOLUNTARY_EXIT_CODE = 42
CHILD_TIMEOUT_SECONDS = 10.0
CORRUPTION_PAYLOAD = b"not-a-sqlite-database" * 8
BENCHMARK_SCRIPT = Path(__file__).resolve().with_name("benchmark_foundation.py")
PROVIDER_ID = "benchmark-provider"
MODEL_ID = "benchmark-model"


def run_faults(workspace: Path) -> list[dict[str, Any]]:
    """按固定顺序执行九项故障并保留当前失败证据。"""
    builders: tuple[tuple[str, str, Callable[[Path], dict[str, Any]]], ...] = (
        ("database_corruption", "P0", fault_database_corruption),
        ("database_locked", "P1", fault_database_locked),
        ("database_readonly", "P1", fault_database_readonly),
        ("disk_full", "P0", fault_disk_full),
        ("process_kill", "P0", fault_process_kill),
        ("provider_timeout", "P1", fault_provider_timeout),
        ("mcp_disconnect", "P1", fault_mcp_disconnect),
        ("slow_subscriber", "P1", fault_slow_subscriber),
        ("plugin_exception", "P1", fault_plugin_exception),
    )
    results = []
    for fault_id, severity, builder in builders:
        try:
            results.append(builder(workspace))
        except Exception as error:
            results.append(_fault_collection_error(fault_id, severity, error))
    return results


def _fault_collection_error(fault_id: str, severity: str, error: Exception) -> dict[str, Any]:
    """记录采集器自身异常，不把无样本写成通过。"""
    metric = make_metric("fault_collection", [], FAULT_DETECTION_SLO_MS, "故障采集异常，无有效样本")
    metric["status"] = "FAIL"
    return make_fault(
        fault_id, severity, "FAIL", [metric],
        observed=f"故障采集器异常：{type(error).__name__}: {error}", scope="COLLECTION_ERROR",
    )


def fault_database_corruption(workspace: Path) -> dict[str, Any]:
    """注入非 SQLite 字节，检查显式报错、检测 SLO 与原始文件保留。"""
    directory = workspace / "fault-corruption"
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / "data.db"
    database.write_bytes(CORRUPTION_PAYLOAD)
    backend = SQLiteBackend(str(directory), "data.json")
    started = time.perf_counter()
    error = None
    try:
        backend.ensure_database()
    except Exception as caught:
        error = caught
    finally:
        backend.close()
    elapsed_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    preserved = database.exists() and database.read_bytes() == CORRUPTION_PAYLOAD
    metric = make_metric("corruption_detection", [elapsed_ms], FAULT_DETECTION_SLO_MS, "对损坏 data.db 调用 SQLiteBackend.ensure_database")
    status = derive_fault_status(error is not None and preserved, [metric])
    observed = f"异常={_error_name(error)}；损坏原库保留={preserved}；原库仍存在={database.exists()}"
    return make_fault(
        "database_corruption", "P0", status, [metric],
        expected="显式报告数据库损坏、满足检测 SLO，且不得删除或替换原始文件",
        observed=observed, scope="REAL_SQLITE",
        details={"error_type": _error_name(error), "original_preserved": preserved},
    )


def fault_database_locked(workspace: Path) -> dict[str, Any]:
    """用第二连接持有写事务，检查错误契约、检测 SLO 与解锁恢复。"""
    with _provider_session(workspace / "fault-locked") as provider:
        provider.register_plugin("benchmark", "benchmark")
        provider._backend._connect().execute(f"PRAGMA busy_timeout={LOCK_BUSY_TIMEOUT_MS}")
        locker = sqlite3.connect(provider._backend.db_file)
        try:
            elapsed_ms, error = _attempt_locked_write(provider, locker)
        finally:
            _close_locker(locker)
        recovered = _lock_recovery_succeeded(provider)
    metric = make_metric("lock_detection", [elapsed_ms], FAULT_DETECTION_SLO_MS, "另一连接 BEGIN IMMEDIATE 时执行公共 set_plugin_data")
    behavior = isinstance(error, DataProviderError) and recovered
    return make_fault(
        "database_locked", "P1", derive_fault_status(behavior, [metric]), [metric],
        expected="200ms 内抛出 DataProviderError，锁释放后可继续写入",
        observed=f"异常={_error_name(error)}；锁释放恢复={recovered}", scope="REAL_DATAPROVIDER",
        details={"error_type": _error_name(error), "recovered": recovered},
    )


def _close_locker(locker: sqlite3.Connection) -> None:
    """回滚失败也继续关闭锁连接，原始异常继续抛出。"""
    try:
        locker.rollback()
    finally:
        locker.close()


def _attempt_locked_write(
    provider: DataProvider, locker: sqlite3.Connection
) -> tuple[float, Exception | None]:
    """在持锁状态下测量公共写入并保留异常。"""
    locker.execute("BEGIN IMMEDIATE")
    started = time.perf_counter()
    error = None
    try:
        provider.set_plugin_data("benchmark", "locked", "value")
    except Exception as caught:
        error = caught
    return (time.perf_counter() - started) * MILLISECONDS_PER_SECOND, error


def _lock_recovery_succeeded(provider: DataProvider) -> bool:
    """确认锁释放后的真实写入恢复，失败由 recovered=False 上报。"""
    try:
        provider.set_plugin_data("benchmark", "locked", "recovered")
        return provider.get_plugin_data("benchmark", "locked") == "recovered"
    except Exception:
        return False


def fault_database_readonly(workspace: Path) -> dict[str, Any]:
    """设置真实文件只读位，检查错误契约与 SLO；平台不强制时记 NOT_RUN。"""
    database, original_mode = _prepare_readonly_database(workspace / "fault-readonly")
    os.chmod(database, stat.S_IREAD)
    started = time.perf_counter()
    error = None
    try:
        with _provider_session(database.parent) as readonly_provider:
            readonly_provider.set_plugin_data("benchmark", "readonly", "value")
    except Exception as caught:
        error = caught
    finally:
        os.chmod(database, original_mode)
    elapsed_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    metric = make_metric("readonly_detection", [elapsed_ms], READONLY_DETECTION_SLO_MS, "对设置只读位的真实数据库执行公共写入")
    behavior = isinstance(error, DataProviderError)
    status = derive_fault_status(behavior, [metric], not_run=error is None)
    return make_fault(
        "database_readonly", "P1", status, [metric],
        expected="500ms 内抛出 DataProviderError，不把只读故障当作写入成功",
        observed=f"异常={_error_name(error)}；只读位已恢复", scope="REAL_DATAPROVIDER_READONLY_FILE",
        details={"error_type": _error_name(error), "platform_enforced": error is not None},
    )


def _prepare_readonly_database(directory: Path) -> tuple[Path, int]:
    """创建只读场景数据库并在所有路径关闭其初始连接。"""
    with _provider_session(directory) as provider:
        provider.register_plugin("benchmark", "benchmark")
        database = provider._backend.db_file
        return database, database.stat().st_mode


def fault_disk_full(workspace: Path) -> dict[str, Any]:
    """注入 ENOSPC，检查调用者失败信号、脏标志和检测 SLO。"""
    TaskStorage._instance = None
    try:
        storage = TaskStorage(str(workspace / "fault-disk-full"))
        storage.load_data()
        error = None
        started = time.perf_counter()
        with patch("builtins.open", side_effect=OSError(errno.ENOSPC, "受控磁盘满")):
            try:
                storage.save_data()
            except Exception as caught:
                error = caught
        elapsed_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
        dirty = bool(storage._cache_dirty)
    finally:
        TaskStorage._instance = None
    metric = make_metric("disk_full_detection", [elapsed_ms], FAULT_DETECTION_SLO_MS, "patch builtins.open 抛出 ENOSPC 后调用 TaskStorage.save_data")
    status = derive_fault_status(error is not None and dirty, [metric])
    return make_fault(
        "disk_full", "P0", status, [metric],
        expected="写入失败必须通知调用者并保留脏标志，不得表现为持久化成功",
        observed=f"异常={_error_name(error)}；返回后 cache_dirty={dirty}",
        scope="REAL_TASK_STORAGE_CONTROLLED_ENOSPC",
        details={"error_type": _error_name(error), "cache_dirty": dirty},
    )


def fault_process_kill(workspace: Path) -> dict[str, Any]:
    """让专属子进程自愿 os._exit，验证提交持久性、完整性与耗时 SLO。"""
    database = workspace / "fault-process" / "abrupt.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = subprocess.run(
        [sys.executable, str(BENCHMARK_SCRIPT), "--abrupt-child", "--child-db", str(database)],
        capture_output=True, text=True, timeout=CHILD_TIMEOUT_SECONDS, check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND
    integrity, committed_rows = _inspect_abrupt_database(database)
    behavior = result.returncode == VOLUNTARY_EXIT_CODE and integrity == "ok" and committed_rows == 1
    metric = make_metric("abrupt_child_exit", [elapsed_ms], PROCESS_EXIT_SLO_MS, "子进程提交一行后在未提交事务中自愿 os._exit(42)")
    observed = f"returncode={result.returncode}；integrity={integrity}；已提交行数={committed_rows}"
    return make_fault(
        "process_kill", "P0", derive_fault_status(behavior, [metric]), [metric],
        expected="自愿 abrupt-exit 子进程退出码 42，已提交一行保留、integrity_check=ok 且满足耗时 SLO",
        observed=observed, scope="VOLUNTARY_CHILD_ABRUPT_EXIT_REAL_SQLITE",
        details={"returncode": result.returncode, "integrity": integrity, "committed_rows": committed_rows},
    )


def _inspect_abrupt_database(database: Path) -> tuple[str, int | None]:
    """重新打开子进程数据库并读取完整性与已提交行数，显式关闭连接。"""
    connection = sqlite3.connect(database)
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        rows = connection.execute("SELECT COUNT(*) FROM foundation_commit").fetchone()[0]
        return str(integrity), int(rows)
    except sqlite3.Error as error:
        return f"{type(error).__name__}: {error}", None
    finally:
        connection.close()


class ControlledChatProvider:
    """受控聊天适配器，按 LLMProvider 下发的 timeout 模拟超时并可恢复。"""

    def __init__(self) -> None:
        """初始化固定模型、原始超时和调用证据。"""
        self.timeout = PROVIDER_ORIGINAL_TIMEOUT_SECONDS
        self.chat_model = MODEL_ID
        self.fail = True
        self.calls = 0
        self.observed_timeouts = []

    def chat(self, messages: list, **kwargs: Any) -> ChatResponse:
        """经过真实 LLMProvider.chat 调用；失败时等待并抛框架超时异常。"""
        self.calls += 1
        self.observed_timeouts.append(self.timeout)
        if not self.fail:
            return ChatResponse(content="ok", model=MODEL_ID)
        threading.Event().wait(self.timeout)
        raise LLMTimeoutError("受控 Provider 超时", provider=PROVIDER_ID)


def fault_provider_timeout(workspace: Path) -> dict[str, Any]:
    """经过 LLMProvider.check_model/chat 验证异常、超时恢复与成功恢复。"""
    adapter = ControlledChatProvider()
    manager = _make_llm_manager(adapter)
    results = [
        manager.check_model(PROVIDER_ID, MODEL_ID, timeout=PROVIDER_TIMEOUT_SECONDS)
        for _ in range(PROVIDER_TIMEOUT_SAMPLES)
    ]
    timeout_restored = adapter.timeout == PROVIDER_ORIGINAL_TIMEOUT_SECONDS
    adapter.fail = False
    recovery = manager.check_model(PROVIDER_ID, MODEL_ID, timeout=PROVIDER_TIMEOUT_SECONDS)
    metrics = _provider_metrics(results, recovery.latency_ms)
    behavior = _provider_behavior(results, recovery, adapter, manager, timeout_restored)
    details = _provider_details(adapter, timeout_restored, recovery)
    observed = f"check_model 超时={len(results)}/{PROVIDER_TIMEOUT_SAMPLES}；恢复={recovery.ok}；timeout 恢复={timeout_restored}"
    return make_fault(
        "provider_timeout", "P1", derive_fault_status(behavior, metrics), metrics,
        expected="真实 LLMProvider 路径返回超时错误、恢复原始 timeout，随后探测成功且全部指标满足 SLO",
        observed=observed, scope="REAL_LLM_PROVIDER_CONTROLLED_ADAPTER", details=details,
    )


def _make_llm_manager(adapter: ControlledChatProvider) -> LLMProvider:
    """构造不读配置、不联网、不写用量的隔离 LLMProvider 实例。"""
    manager = object.__new__(LLMProvider)
    manager._config = SimpleNamespace(version=0)
    manager._loaded_config_version = 0
    manager._providers = {PROVIDER_ID: adapter}
    manager._models_cache = {PROVIDER_ID: []}
    manager._health = {}
    manager._record_usage = lambda **kwargs: None
    return manager


def _provider_metrics(results: list, recovery_latency: float | None) -> list[dict[str, Any]]:
    """生成真实 check_model 超时与恢复延迟指标。"""
    timeout_samples = [item.latency_ms for item in results if item.latency_ms is not None]
    recovery_samples = [] if recovery_latency is None else [recovery_latency]
    return [
        make_metric("provider_timeout_detection", timeout_samples, PROVIDER_TIMEOUT_SLO_MS, "LLMProvider.check_model 经 chat 调用受控超时适配器"),
        make_metric("provider_recovery", recovery_samples, PROVIDER_TIMEOUT_SLO_MS, "超时后恢复适配器并再次执行 LLMProvider.check_model"),
    ]


def _provider_behavior(
    results: list,
    recovery: Any,
    adapter: ControlledChatProvider,
    manager: LLMProvider,
    timeout_restored: bool,
) -> bool:
    """要求全部超时被归类、恢复成功、健康状态恢复且 timeout 复原。"""
    timeouts_ok = all(not item.ok and item.error and "超时" in item.error for item in results)
    health_ok = manager._health.get(PROVIDER_ID) == (True, None)
    timeout_ok = adapter.observed_timeouts[-1] == PROVIDER_TIMEOUT_SECONDS
    recovery_ok = recovery.ok and recovery.error is None and health_ok and timeout_ok
    return bool(timeouts_ok and recovery_ok and timeout_restored)


def _provider_details(
    adapter: ControlledChatProvider, timeout_restored: bool, recovery: Any
) -> dict[str, Any]:
    """返回实际调用次数、恢复结果与 timeout 证据。"""
    return {
        "check_model_calls": adapter.calls,
        "timeout_restored": timeout_restored,
        "recovery_succeeded": bool(recovery.ok and recovery.error is None),
        "original_timeout_seconds": PROVIDER_ORIGINAL_TIMEOUT_SECONDS,
        "probe_timeout_seconds": PROVIDER_TIMEOUT_SECONDS,
    }


def fault_mcp_disconnect(workspace: Path) -> dict[str, Any]:
    """停止真实本地 MCP Server，检查断连、清理异常和检测 SLO。"""
    port = _available_loopback_port()
    server = MCPHostServer(name="foundation-disconnect", host="127.0.0.1", port=port)
    server._register_tool_direct("benchmark_echo", "断连回显", {}, benchmark_echo)
    lifecycle = McpServerLifecycle(server)
    evidence: dict[str, Any] = {}
    try:
        lifecycle.start()
        evidence = asyncio.run(_call_after_server_stop(port, server, lifecycle))
    finally:
        _stop_server_with_evidence(server, evidence, lifecycle)
    if evidence.get("preparation_error") is not None:
        return _mcp_preparation_failure(evidence)
    elapsed = evidence.get("elapsed_ms")
    samples = [] if elapsed is None else [elapsed]
    metric = make_metric("mcp_disconnect_detection", samples, MCP_DISCONNECT_SLO_MS, "真实 MCP 会话中停止本地 Server 后调用工具并清理传输")
    behavior = evidence.get("error") is not None and evidence.get("cleanup_error") is None
    observed = f"调用异常={_error_name(evidence.get('error'))}；cleanup_error={evidence.get('cleanup_error') or '无'}"
    return make_fault(
        "mcp_disconnect", "P1", derive_fault_status(behavior, [metric]), [metric],
        expected="断连调用 2s 内显式失败，Session/传输清理无异常，不无限等待或伪装成功",
        observed=observed, scope="REAL_LOOPBACK_MCP",
        details={
            "error_type": _error_name(evidence.get("error")),
            "cleanup_error": evidence.get("cleanup_error"),
        },
    )


def _mcp_preparation_failure(evidence: dict[str, Any]) -> dict[str, Any]:
    """把 Session/传输准备错误显式转为采集失败并保留清理证据。"""
    result = _fault_collection_error("mcp_disconnect", "P1", evidence["preparation_error"])
    cleanup_error = evidence.get("cleanup_error")
    result["details"]["cleanup_error"] = cleanup_error
    result["observed"] += f"；cleanup_error={cleanup_error or '无'}"
    return result


async def _call_after_server_stop(
    port: int,
    server: Any,
    lifecycle: McpServerLifecycle | None = None,
) -> dict[str, Any]:
    """区分准备错误与预期断连调用错误，同时保留清理异常。"""
    evidence = {
        "elapsed_ms": None,
        "error": None,
        "preparation_error": None,
        "cleanup_error": None,
        "prepared": False,
    }
    stack = AsyncExitStack()
    try:
        await _execute_disconnect_call(stack, port, server, evidence, lifecycle)
    except Exception as error:
        key = "error" if evidence["prepared"] else "preparation_error"
        evidence[key] = error
    try:
        await stack.aclose()
    except Exception as error:
        evidence["cleanup_error"] = _error_name(error)
    return evidence


async def _execute_disconnect_call(
    stack: AsyncExitStack,
    port: int,
    server: Any,
    evidence: dict[str, Any],
    lifecycle: McpServerLifecycle | None,
) -> None:
    """进入真实传输和 Session，协调 watcher 后停止 Server 并调用工具。"""
    url = f"http://127.0.0.1:{port}/mcp"
    read_stream, write_stream, _ = await stack.enter_async_context(streamablehttp_client(url))
    session = await stack.enter_async_context(ClientSession(read_stream, write_stream))
    await session.initialize()
    if lifecycle is None:
        server.stop()
    else:
        lifecycle.stop()
    evidence["prepared"] = True
    started = time.perf_counter()
    try:
        await asyncio.wait_for(session.call_tool("benchmark_echo", {}), MCP_DISCONNECT_TIMEOUT_SECONDS)
    except Exception as error:
        evidence["error"] = error
    finally:
        evidence["elapsed_ms"] = (time.perf_counter() - started) * MILLISECONDS_PER_SECOND


def _stop_server_with_evidence(
    server: MCPHostServer,
    evidence: dict[str, Any],
    lifecycle: McpServerLifecycle | None = None,
) -> None:
    """外层停止与 watcher 检查失败也写入 cleanup_error。"""
    if lifecycle is None and not server.is_running:
        return
    try:
        if lifecycle is None:
            server.stop()
        else:
            lifecycle.stop()
    except Exception as error:
        evidence["cleanup_error"] = _error_name(error)


def fault_slow_subscriber(workspace: Path) -> dict[str, Any]:
    """注入 50ms 同步订阅者，联合检查发布 SLO 与快订阅者交付。"""
    received = []
    with _provider_session(workspace / "fault-slow-subscriber") as provider:
        provider.register_plugin("benchmark", "benchmark")
        provider.subscribe("slow", "benchmark", "event", _slow_subscriber)
        provider.subscribe("fast", "benchmark", "event", lambda *args: received.append(args))
        samples = _measure_publishes(provider)
    metric = make_metric("slow_subscriber_publish", samples, SLOW_SUBSCRIBER_SLO_MS, "50ms 慢订阅者与快订阅者并存时测量 DataProvider.publish")
    behavior = len(received) == FAULT_SAMPLES
    observed = f"publish p95={metric['statistics']['p95']}ms；快订阅者收到={len(received)}"
    return make_fault(
        "slow_subscriber", "P1", derive_fault_status(behavior, [metric]), [metric],
        expected="慢订阅者不阻塞发布者（p95<=10ms），快订阅者收到全部事件",
        observed=observed, scope="REAL_DATAPROVIDER_CONTROLLED_SLEEPER",
        details={"fast_subscriber_events": len(received)},
    )


def _measure_publishes(provider: DataProvider) -> list[float]:
    """测量固定次数真实发布，异常继续抛出并由上下文清理连接。"""
    samples = []
    for index in range(FAULT_SAMPLES):
        started = time.perf_counter()
        provider.publish("benchmark", "event", index)
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples


def _slow_subscriber(publisher_id: str, key: str, old_value: Any, new_value: Any) -> None:
    """本地慢订阅者固定等待 50ms。"""
    threading.Event().wait(SLOW_SUBSCRIBER_DELAY_SECONDS)


def fault_plugin_exception(workspace: Path) -> dict[str, Any]:
    """让订阅回调抛出插件异常，联合检查隔离、交付和发布 SLO。"""
    received = []
    publish_error = None
    with _provider_session(workspace / "fault-plugin-exception") as provider:
        provider.register_plugin("benchmark", "benchmark")
        provider.subscribe("broken", "benchmark", "event", _broken_subscriber)
        provider.subscribe("healthy", "benchmark", "event", lambda *args: received.append(args))
        samples, publish_error = _measure_exception_publishes(provider)
    metric = make_metric("plugin_exception_publish", samples, PLUGIN_PUBLISH_SLO_MS, "异常订阅者与正常订阅者并存时执行真实 publish")
    behavior = publish_error is None and len(received) == FAULT_SAMPLES
    return make_fault(
        "plugin_exception", "P1", derive_fault_status(behavior, [metric]), [metric],
        expected="单个插件回调异常不传播、不阻断其他订阅者且满足发布 SLO",
        observed=f"发布异常={_error_name(publish_error)}；正常订阅者收到={len(received)}",
        scope="REAL_DATAPROVIDER_CONTROLLED_PLUGIN_EXCEPTION",
        details={"healthy_subscriber_events": len(received), "publish_error": _error_name(publish_error)},
    )


def _measure_exception_publishes(
    provider: DataProvider,
) -> tuple[list[float], Exception | None]:
    """测量异常订阅场景的发布并保留首个传播异常。"""
    samples = []
    publish_error = None
    for index in range(FAULT_SAMPLES):
        started = time.perf_counter()
        try:
            provider.publish("benchmark", "event", index)
        except Exception as error:
            publish_error = publish_error or error
        samples.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
    return samples, publish_error


def _broken_subscriber(publisher_id: str, key: str, old_value: Any, new_value: Any) -> None:
    """模拟插件回调抛出可预期异常。"""
    raise RuntimeError("受控插件异常")


def _error_name(error: Any) -> str:
    """将异常类型与消息压缩为报告文本，None 表示无异常。"""
    return "无" if error is None else f"{type(error).__name__}: {error}"


def run_abrupt_child(database: Path) -> None:
    """专属子进程提交一行后自愿 abrupt-exit；绝不终止其他进程。"""
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE foundation_commit (value TEXT)")
    connection.execute("INSERT INTO foundation_commit VALUES ('committed')")
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    connection.execute("INSERT INTO foundation_commit VALUES ('uncommitted')")
    connection.execute("SELECT 1")
    os._exit(VOLUNTARY_EXIT_CODE)
