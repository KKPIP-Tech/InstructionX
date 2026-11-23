"""Task 0 故障矩阵门禁：验证真实采集、失败证据与安全隔离边界。"""

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_IMPORT_TEMP_ROOT = _PROJECT_ROOT / "temp"
_IMPORT_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
_IMPORT_LOG_DIRECTORY = Path(tempfile.mkdtemp(
    prefix="foundation-pytest-import-logs-", dir=_IMPORT_TEMP_ROOT
))
_PREVIOUS_LOG_DIRECTORY = os.environ.get("INSTRUCTIONX_LOG_DIR")
os.environ["INSTRUCTIONX_LOG_DIR"] = str(_IMPORT_LOG_DIRECTORY)

import pytest


def _close_module_import_log_handlers() -> None:
    """只关闭属于本测试模块导入目录的日志 handler。"""
    manager_module = sys.modules.get("utils.logging_tools")
    if manager_module is None:
        return
    manager = manager_module.LoggerManager._instance
    logger = getattr(manager, "_logger", None)
    if logger is None:
        return
    for handler in list(logger.handlers):
        filename = getattr(handler, "baseFilename", None)
        if filename and Path(filename).resolve().is_relative_to(_IMPORT_LOG_DIRECTORY):
            logger.removeHandler(handler)
            handler.close()


def _restore_module_log_environment() -> None:
    """恢复测试模块导入前的日志目录环境。"""
    if _PREVIOUS_LOG_DIRECTORY is None:
        os.environ.pop("INSTRUCTIONX_LOG_DIR", None)
    else:
        os.environ["INSTRUCTIONX_LOG_DIR"] = _PREVIOUS_LOG_DIRECTORY


def _cleanup_module_import_logging() -> None:
    """清理 benchmark 与本模块导入日志，任何清理错误均显式抛出。"""
    cleanup_error = None
    benchmark_module = sys.modules.get("benchmark_foundation")
    if benchmark_module is not None:
        try:
            benchmark_module._cleanup_import_logging()
        except Exception as error:
            cleanup_error = error
    try:
        _close_module_import_log_handlers()
    except Exception as error:
        cleanup_error = cleanup_error or error
    try:
        if _IMPORT_LOG_DIRECTORY.exists():
            shutil.rmtree(_IMPORT_LOG_DIRECTORY)
    except Exception as error:
        cleanup_error = cleanup_error or error
    _restore_module_log_environment()
    if cleanup_error is not None:
        raise cleanup_error


_ORIGINAL_SYS_PATH = sys.path.copy()
_ORIGINAL_MCP_MODULES = {
    name: module for name, module in sys.modules.items()
    if name == "mcp" or name.startswith("mcp.")
}
_TEST_DIRECTORY = Path(__file__).resolve().parent
_IMPORT_COMPLETED = False
try:
    for module_name in _ORIGINAL_MCP_MODULES:
        sys.modules.pop(module_name, None)
    from scripts import _foundation_benchmark_common as common  # noqa: E402

    _SCRIPTS_DIRECTORY = str(Path(common.__file__).resolve().parent)
    sys.path[:] = [
        entry for entry in sys.path
        if not entry or Path(entry).resolve() != _TEST_DIRECTORY
    ]
    if _SCRIPTS_DIRECTORY not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIRECTORY)

    import _foundation_faults as faults  # noqa: E402
    import _foundation_workloads as workloads  # noqa: E402
    import benchmark_foundation as benchmark  # noqa: E402
    from core.data.data_provider import DataProvider  # noqa: E402
    from core.llm.llm_provider import LLMProvider  # noqa: E402
    from core.task.background_task import BackgroundTaskManager  # noqa: E402
    from core.task.task_storage import TaskStorage  # noqa: E402

    _TASK0_SYS_PATH = sys.path.copy()
    _TASK0_MCP_MODULES = {
        name: module for name, module in sys.modules.items()
        if name == "mcp" or name.startswith("mcp.")
    }
    _IMPORT_COMPLETED = True
finally:
    sys.path[:] = _ORIGINAL_SYS_PATH
    for module_name in tuple(sys.modules):
        if module_name == "mcp" or module_name.startswith("mcp."):
            sys.modules.pop(module_name, None)
    sys.modules.update(_ORIGINAL_MCP_MODULES)
    if not _IMPORT_COMPLETED:
        _cleanup_module_import_logging()


@contextmanager
def _task0_runtime_imports() -> Iterator[None]:
    """仅在真实采集期间安装外部 MCP 模块，结束后恢复调用前状态。"""
    previous_path = sys.path.copy()
    previous_modules = {
        name: module for name, module in sys.modules.items()
        if name == "mcp" or name.startswith("mcp.")
    }
    try:
        for module_name in previous_modules:
            sys.modules.pop(module_name, None)
        sys.path[:] = _TASK0_SYS_PATH
        sys.modules.update(_TASK0_MCP_MODULES)
        yield
    finally:
        sys.path[:] = previous_path
        for module_name in tuple(sys.modules):
            if module_name == "mcp" or module_name.startswith("mcp."):
                sys.modules.pop(module_name, None)
        sys.modules.update(previous_modules)


FAULT_SEVERITIES = {
    "database_corruption": "P0",
    "database_locked": "P1",
    "database_readonly": "P1",
    "disk_full": "P0",
    "process_kill": "P0",
    "provider_timeout": "P1",
    "mcp_disconnect": "P1",
    "slow_subscriber": "P1",
    "plugin_exception": "P1",
}
EXPECTED_FAULT_STATUSES = {
    "database_corruption": "PASS",
    "database_locked": "PASS",
    "database_readonly": "PASS",
    "disk_full": "PASS",
    "process_kill": "PASS",
    "provider_timeout": "PASS",
    "mcp_disconnect": "PASS",
    "slow_subscriber": "PASS",
    "plugin_exception": "PASS",
}
EXPECTED_FAILURE_SEVERITIES = {
    item_id: severity
    for item_id, severity in FAULT_SEVERITIES.items()
    if EXPECTED_FAULT_STATUSES[item_id] == "FAIL"
}
NOT_RUN_CAPABILITIES = {
    "real_gui_chart",
    "full_gui_startup_shutdown",
    "external_provider_network",
    "physical_disk_full",
    "endurance_72h",
}
STATISTIC_KEYS = {"p50", "p95", "p99", "max", "sample_count"}
PROVIDER_CALL_COUNT = faults.PROVIDER_TIMEOUT_SAMPLES + 1
FAULT_SAMPLE_COUNT = 5
SLOW_SUBSCRIBER_SLO_MS = 10.0
FULL_REPORT_ENVIRONMENT_KEYS = (
    "INSTRUCTIONX_LOG_DIR",
    "INSTRUCTIONX_DATAPROVIDER_BACKEND",
)
IMPORT_PROBE_TIMEOUT_SECONDS = 30.0
IMPORT_PROBE_SOURCE = '''
import logging.handlers
import os
import sys
from pathlib import Path

project_root = Path({project_root!r}).resolve()
real_logs = Path({real_logs!r}).resolve()
temp_root = Path({temp_root!r}).resolve()
opened = []
original_makedirs = os.makedirs
original_handler = logging.handlers.RotatingFileHandler

def guarded_makedirs(path, *args, **kwargs):
    if Path(path).resolve().is_relative_to(real_logs):
        raise RuntimeError("导入期创建真实日志目录")
    return original_makedirs(path, *args, **kwargs)

class GuardHandler(original_handler):
    def __init__(self, filename, *args, **kwargs):
        path = Path(filename).resolve()
        if path.is_relative_to(real_logs):
            raise RuntimeError("导入期打开真实日志")
        opened.append(path)
        super().__init__(filename, *args, **kwargs)

os.makedirs = guarded_makedirs
logging.handlers.RotatingFileHandler = GuardHandler
sys.path.insert(0, str(project_root / "scripts"))
sys.path.insert(0, str(project_root))
import benchmark_foundation as benchmark

assert opened, "导入探针未捕获日志 handler"
assert all(path.is_relative_to(temp_root) for path in opened)
benchmark._cleanup_import_logging()
assert all(not path.parent.exists() for path in opened), "导入期日志目录未清理"
assert os.environ.get("INSTRUCTIONX_LOG_DIR") is None
print("IMPORT_PROBE_OK")
'''


def _make_contract_report() -> dict[str, Any]:
    """构造包含固定 ID 的最小合法报告，用于纯逻辑边界测试。"""
    metric = common.make_metric("latency_ms", [1.0, 2.0, 3.0], 5.0, "门禁固定样本")
    workloads = [
        common.make_workload(item_id, "CONTROLLED_CONTRACT", [metric])
        for item_id in common.WORKLOAD_IDS
    ]
    fault_items = [
        common.make_fault(item_id, FAULT_SEVERITIES[item_id], "FAIL", [metric])
        for item_id in common.FAULT_IDS
    ]
    not_run = [{"id": "real_gui_chart", "status": "NOT_RUN", "reason": "门禁占位"}]
    return common.build_report({}, {}, workloads, fault_items, not_run)


def _replace_idle_metric(report: dict[str, Any], metric: dict[str, Any]) -> None:
    """替换空闲负载指标，同时让项目状态由新指标重新派生。"""
    report["workloads"][0] = common.make_workload("idle", "CONTROLLED_CONTRACT", [metric])


def _idle_difference(comparison: dict[str, Any]) -> dict[str, Any]:
    """提取空闲负载的指标差异。"""
    return next(
        item for item in comparison["metric_differences"]
        if item["id"] == "workload:idle:latency_ms"
    )


def _fault(report: dict[str, Any], fault_id: str) -> dict[str, Any]:
    """从真实报告中提取指定故障。"""
    return next(item for item in report["fault_matrix"] if item["id"] == fault_id)


def _workload(report: dict[str, Any], workload_id: str) -> dict[str, Any]:
    """从真实报告中提取指定负载。"""
    return next(item for item in report["workloads"] if item["id"] == workload_id)


def _assert_metric_contract(metric: dict[str, Any]) -> None:
    """独立核对原始样本、统计、测量方法和 SLO 的一致性。"""
    statistics = metric["statistics"]
    assert STATISTIC_KEYS <= statistics.keys()
    assert statistics["sample_count"] == len(metric["samples"])
    assert metric["measurement_method"]
    assert metric["slo"]["operator"] == "<="
    if statistics["sample_count"] == 0:
        assert statistics["p95"] is None
        assert metric["status"] != "PASS"
    else:
        assert statistics["p50"] is not None
        assert statistics["p95"] is not None
        assert statistics["p99"] is not None
        assert statistics["max"] == max(metric["samples"])


def _restore_environment(previous: dict[str, str | None], logging_disable: int) -> None:
    """恢复采集器修改的环境变量与全局日志屏蔽级别。"""
    for name, value in previous.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    logging.disable(logging_disable)


def _restore_singletons() -> None:
    """清理完整采集涉及的单例，避免影响后续既有测试。"""
    manager = BackgroundTaskManager._instance
    if manager is not None:
        manager.shutdown()
    BackgroundTaskManager._instance = None
    DataProvider._instance = None
    TaskStorage._instance = None


@pytest.fixture(scope="module", autouse=True)
def _module_import_log_cleanup() -> Iterator[None]:
    """模块测试结束后关闭并删除收集期日志目录。"""
    try:
        yield
    finally:
        _cleanup_module_import_logging()


@pytest.fixture(scope="module")
def real_report() -> Iterator[dict[str, Any]]:
    """执行一次真实完整采集，所有运行时数据限制在项目 temp。"""
    previous_environment = {name: os.environ.get(name) for name in FULL_REPORT_ENVIRONMENT_KEYS}
    previous_logging_disable = logging.root.manager.disable
    try:
        with common.isolated_workspace("pytest-real-gate") as workspace:
            output = workspace / "report.json"
            with _task0_runtime_imports():
                report = benchmark.run_benchmark(output)
            assert json.loads(output.read_text(encoding="utf-8")) == report
            yield report
    finally:
        _restore_singletons()
        _restore_environment(previous_environment, previous_logging_disable)


def test_nearest_rank_statistics_and_empty_samples() -> None:
    """最近秩统计应保留样本数，空样本不得产生零值或伪通过。"""
    statistics = common.summarize_samples([4.0, 1.0, 3.0, 2.0])
    assert statistics == {"p50": 2.0, "p95": 4.0, "p99": 4.0, "max": 4.0, "sample_count": 4}
    empty = common.summarize_samples([])
    assert empty["sample_count"] == 0
    assert all(empty[key] is None for key in ("p50", "p95", "p99", "max"))


@pytest.mark.parametrize("invalid_sample", [float("nan"), float("inf")])
def test_non_finite_samples_are_rejected(invalid_sample: float) -> None:
    """NaN 和无穷大不得进入延迟统计。"""
    with pytest.raises(ValueError, match="有限数值"):
        common.summarize_samples([1.0, invalid_sample])


def test_metric_and_item_status_priority() -> None:
    """指标应区分 PASS、FAIL、NOT_RUN，项目状态按失败优先派生。"""
    passed = common.make_metric("passed", [5.0], 5.0, "边界值")
    failed = common.make_metric("failed", [5.1], 5.0, "越界值")
    missing = common.make_metric("missing", [], 5.0, "不可读")
    assert (passed["status"], failed["status"], missing["status"]) == ("PASS", "FAIL", "NOT_RUN")
    assert common.derive_item_status([passed, missing]) == "NOT_RUN"
    assert common.derive_item_status([missing, failed]) == "FAIL"
    assert common.derive_fault_status(False, [passed]) == "FAIL"
    assert common.derive_fault_status(True, [passed], not_run=True) == "NOT_RUN"


def test_empty_metric_list_cannot_pass() -> None:
    """空指标列表必须 NOT_RUN，历史报告的 PASS 空指标必须校验失败。"""
    assert common.derive_item_status([]) == "NOT_RUN"
    assert common.derive_fault_status(True, []) == "NOT_RUN"
    assert common.make_workload("idle", "CONTROLLED", [])["status"] == "NOT_RUN"
    report = _make_contract_report()
    report["workloads"][0]["metrics"] = []
    report["workloads"][0]["status"] = "PASS"
    with pytest.raises(ValueError, match="空指标列表不得标记 PASS"):
        common.validate_report(report)


def test_report_qualification_is_independent_from_collection() -> None:
    """采集完成不代表系统合格，总判定应覆盖通过、未执行和失败。"""
    passed = common.make_metric("latency", [1.0], 2.0, "固定样本")
    missing = common.make_metric("latency", [], 2.0, "无样本")
    failed = common.make_fault("disk_full", "P0", "FAIL", [passed])
    passing_workload = [common.make_workload("idle", "CONTROLLED", [passed])]
    missing_workload = [common.make_workload("idle", "CONTROLLED", [missing])]
    pass_report = common.build_report({}, {}, passing_workload, [], [])
    not_run_report = common.build_report({}, {}, missing_workload, [], [])
    fail_report = common.build_report({}, {}, passing_workload, [failed], [])
    assert pass_report["qualification_status"] == "PASS"
    assert not_run_report["qualification_status"] == "NOT_RUN"
    assert fail_report["qualification_status"] == "FAIL"
    assert fail_report["collection_status"] == "COMPLETED"


def test_failed_metric_cannot_be_hidden_by_passing_item() -> None:
    """历史项目误标 PASS 时，内部 FAIL 指标仍必须进入当前失败清单。"""
    failed = common.make_metric("mcp_roundtrip", [500.0], 100.0, "延迟越界")
    fault = common.make_fault("mcp_disconnect", "P1", "PASS", [failed])
    failures = common._current_failures([], [fault])
    assert len(failures) == 1
    assert failures[0]["id"] == "mcp_disconnect"
    assert "mcp_roundtrip" in failures[0]["observed"]


def test_collection_error_with_empty_samples_is_fail() -> None:
    """采集器异常没有样本时也应判 FAIL，不得派生为 NOT_RUN。"""
    result = faults._fault_collection_error("mcp_disconnect", "P1", RuntimeError("受控采集异常"))
    assert result["status"] == "FAIL"
    assert result["execution_scope"] == "COLLECTION_ERROR"
    assert result["metrics"][0]["status"] == "FAIL"
    assert result["metrics"][0]["statistics"]["sample_count"] == 0


def test_real_report_preserves_known_failures_and_not_run(real_report: dict[str, Any]) -> None:
    """故障项通过后仍须保留五项安全边界外能力的 NOT_RUN 判定。"""
    actual_failures = {
        item["id"]: item["severity"]
        for item in real_report["current_failures"]
        if item["source"] == "fault_matrix"
    }
    assert real_report["collection_status"] == "COMPLETED"
    assert real_report["qualification_status"] == "NOT_RUN"
    assert actual_failures == EXPECTED_FAILURE_SEVERITIES
    assert len(real_report["current_failures"]) == len(EXPECTED_FAILURE_SEVERITIES), _workload(
        real_report, "typical_desktop"
    ).get("mcp_error")
    assert {item["id"] for item in real_report["not_run"]} == NOT_RUN_CAPABILITIES
    assert benchmark._not_run_summary(real_report) == {"top_level": 5, "items": 0, "metrics": 0}


def test_five_real_workloads_and_measurement_contract(real_report: dict[str, Any]) -> None:
    """五类固定负载应实际执行，数据规模与统计字段不得缺失。"""
    expected_scales = {
        "idle": {"new_databases": 12},
        "typical_desktop": {"seed_keys": 100, "payload_bytes_per_key": 1024},
        "long_running_32": {"long_running_tasks": 32, "async_tasks": 12},
        "chart_1khz": {"frames": 1000, "input_samples": 60000},
        "slow_io": {"operations_per_metric": 12, "disk_payload_bytes": 4096},
    }
    assert tuple(item["id"] for item in real_report["workloads"]) == common.WORKLOAD_IDS
    for workload_id, expected_scale in expected_scales.items():
        workload = _workload(real_report, workload_id)
        assert workload["status"] == "PASS"
        assert workload["execution_scope"] != "COLLECTION_ERROR"
        assert expected_scale.items() <= workload["data_scale"].items()
        for metric in workload["metrics"]:
            _assert_metric_contract(metric)
    chart = _workload(real_report, "chart_1khz")
    assert chart["execution_scope"] == "ALGORITHM_ONLY_NO_QT_GUI"
    assert "fps" not in chart["data_scale"]


def test_nine_real_faults_and_status_contract(real_report: dict[str, Any]) -> None:
    """九项故障应具备完整证据，并保持当前真实失败而非全员通过。"""
    assert tuple(item["id"] for item in real_report["fault_matrix"]) == common.FAULT_IDS
    for fault_id, severity in FAULT_SEVERITIES.items():
        fault = _fault(real_report, fault_id)
        assert fault["severity"] == severity
        assert fault["status"] == EXPECTED_FAULT_STATUSES[fault_id]
        assert fault["execution_scope"] != "COLLECTION_ERROR"
        assert fault["expected"] and fault["observed"]
        assert isinstance(fault["details"], dict)
        for metric in fault["metrics"]:
            _assert_metric_contract(metric)


def test_database_corruption_preserves_original_as_pass(tmp_path: Path) -> None:
    """修复后损坏原库逐字节保留且显式报错，采集器必须判真实 PASS。"""
    result = faults.fault_database_corruption(tmp_path)
    database = tmp_path / "fault-corruption" / "data.db"
    original_preserved = database.exists() and database.read_bytes() == faults.CORRUPTION_PAYLOAD
    assert original_preserved is True
    assert result["status"] == "PASS"
    assert result["details"]["original_preserved"] is True
    assert result["details"]["error_type"].startswith("SQLiteBackendError:")
    assert "不得删除或替换" in result["expected"]


def test_database_lock_and_readonly_expose_public_api_errors(real_report: dict[str, Any]) -> None:
    """锁定和只读必须统一为 DataProviderError，且锁释放后可恢复。"""
    locked = _fault(real_report, "database_locked")
    readonly = _fault(real_report, "database_readonly")
    assert locked["status"] == "PASS"
    assert locked["details"]["error_type"].startswith("DataProviderError")
    assert locked["details"]["recovered"] is True
    assert readonly["status"] == "PASS"
    assert readonly["details"]["error_type"].startswith("DataProviderError")
    assert readonly["details"]["platform_enforced"] is True


def test_disk_full_reports_false_persistence_success(tmp_path: Path) -> None:
    """ENOSPC 必须返回 False 并保留脏标记，检测通过不等于物理磁盘满已验收。"""
    result = faults.fault_disk_full(tmp_path)
    assert result["status"] == "PASS"
    assert result["details"]["save_receipt"] is False
    assert result["details"]["cache_dirty"] is True
    assert result["metrics"][0]["statistics"]["sample_count"] == 1
    assert "不得表现为持久化成功" in result["expected"]


def test_owned_abrupt_child_preserves_committed_row(real_report: dict[str, Any]) -> None:
    """自愿退出子进程只验证 SQLite 提交持久性和完整性。"""
    result = _fault(real_report, "process_kill")
    assert result["status"] == "PASS"
    assert result["details"]["returncode"] == faults.VOLUNTARY_EXIT_CODE
    assert result["details"]["integrity"] == "ok"
    assert result["details"]["committed_rows"] == 1
    assert result["execution_scope"] == "VOLUNTARY_CHILD_ABRUPT_EXIT_REAL_SQLITE"


def test_provider_fault_uses_actual_llm_provider_chat_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """受控适配器必须经 LLMProvider.check_model 到 chat，并验证恢复证据。"""
    original_chat = LLMProvider.chat
    chat_calls: list[LLMProvider] = []

    def recording_chat(self: LLMProvider, *args: Any, **kwargs: Any) -> Any:
        chat_calls.append(self)
        return original_chat(self, *args, **kwargs)

    monkeypatch.setattr(LLMProvider, "chat", recording_chat)
    result = faults.fault_provider_timeout(tmp_path)
    assert len(chat_calls) == PROVIDER_CALL_COUNT
    assert all(isinstance(manager, LLMProvider) for manager in chat_calls)
    assert result["details"]["check_model_calls"] == PROVIDER_CALL_COUNT
    assert result["execution_scope"] == "REAL_LLM_PROVIDER_CONTROLLED_ADAPTER"
    assert result["details"]["timeout_restored"] is True
    assert result["details"]["recovery_succeeded"] is True
    assert result["status"] == "PASS"


def test_real_mcp_disconnect_is_bounded_and_clean(real_report: dict[str, Any]) -> None:
    """真实回环断连应有显式异常、有限耗时和无清理异常。"""
    result = _fault(real_report, "mcp_disconnect")
    metric = result["metrics"][0]
    assert result["status"] == "PASS"
    assert result["execution_scope"] == "REAL_LOOPBACK_MCP"
    assert result["details"]["cleanup_error"] is None
    assert result["details"]["error_type"] != "无"
    assert metric["statistics"]["sample_count"] == 1
    assert metric["statistics"]["p95"] <= faults.MCP_DISCONNECT_SLO_MS


class StopRecorder:
    """记录 Server.stop 调用并提供受控停止异常。"""

    def __init__(self, stop_error: Exception | None = None) -> None:
        self.stop_calls = 0
        self.is_running = True
        self._stop_error = stop_error

    def stop(self) -> None:
        """记录停止请求，随后按配置抛出异常。"""
        self.stop_calls += 1
        self.is_running = False
        if self._stop_error is not None:
            raise self._stop_error


@pytest.mark.parametrize("failure_kind", ["cancel_error", "timeout"])
def test_watcher_cancel_failure_or_timeout_still_stops_server(
    failure_kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """取消异常与超时均继续 stop，并分别保留取消和停止错误。"""
    cancel_error = (
        TimeoutError("受控取消超时") if failure_kind == "timeout"
        else RuntimeError("受控取消异常")
    )
    stop_error = RuntimeError("受控停止异常") if failure_kind == "timeout" else None
    server = StopRecorder(stop_error)
    lifecycle = workloads.McpServerLifecycle(server)

    def fail_cancel() -> None:
        raise cancel_error

    monkeypatch.setattr(lifecycle, "_cancel_watchers", fail_cancel)
    with pytest.raises(workloads.McpServerStopError) as caught:
        lifecycle.stop()
    assert server.stop_calls == 1
    assert server.is_running is False
    assert caught.value.cancel_error is cancel_error
    assert caught.value.stop_error is stop_error


class ControlledTransport:
    """可控 MCP 传输替身，用于进入与清理异常分支。"""

    def __init__(self, enter_error: bool = False, cleanup_error: bool = False) -> None:
        self.enter_error = enter_error
        self.cleanup_error = cleanup_error

    async def __aenter__(self) -> tuple[object, object, None]:
        """按配置在进入传输时抛出异常。"""
        if self.enter_error:
            raise RuntimeError("受控传输进入异常")
        return object(), object(), None

    async def __aexit__(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        """按配置在退出传输时抛出异常。"""
        if self.cleanup_error:
            raise RuntimeError("受控传输清理异常")


class ControlledSession:
    """可控 MCP Session，用于准备失败与预期断连分支。"""

    def __init__(self, initialize_error: bool = False) -> None:
        self.initialize_error = initialize_error

    async def __aenter__(self) -> "ControlledSession":
        """返回当前会话。"""
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        """会话自身不增加清理异常。"""

    async def initialize(self) -> None:
        """按配置模拟初始化失败。"""
        if self.initialize_error:
            raise RuntimeError("受控初始化异常")

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> None:
        """模拟 Server 停止后的显式断连异常。"""
        raise TimeoutError("受控断连")


class ControlledServer:
    """可控本地 Server，记录运行状态且不打开任何 socket。"""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.is_running = False

    def _register_tool_direct(self, *args: Any, **kwargs: Any) -> None:
        """注册接口在此替身中无需实际动作。"""

    def run_http(self) -> None:
        """进入已运行状态。"""
        self.is_running = True

    def stop(self) -> None:
        """进入已停止状态。"""
        self.is_running = False


@pytest.mark.parametrize("failure_stage", ["initialize", "transport"])
def test_mcp_preparation_failures_are_collection_failures(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Session 初始化和传输进入失败均不得误报 NOT_RUN 或 PASS。"""
    transport = ControlledTransport(enter_error=failure_stage == "transport")
    session = ControlledSession(initialize_error=failure_stage == "initialize")
    monkeypatch.setattr(faults, "streamablehttp_client", lambda url: transport)
    monkeypatch.setattr(faults, "ClientSession", lambda *args: session)
    evidence = asyncio.run(faults._call_after_server_stop(1, ControlledServer()))
    result = faults._mcp_preparation_failure(evidence)
    assert evidence["prepared"] is False
    assert evidence["preparation_error"] is not None
    assert evidence["elapsed_ms"] is None
    assert result["status"] == "FAIL"
    assert result["execution_scope"] == "COLLECTION_ERROR"
    assert result["metrics"][0]["status"] == "FAIL"


def test_mcp_cleanup_exception_is_preserved_and_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """预期断连异常之外，传输清理异常也必须进入证据并使故障失败。"""
    monkeypatch.setattr(faults, "MCPHostServer", ControlledServer)
    monkeypatch.setattr(faults, "_available_loopback_port", lambda: 1)
    monkeypatch.setattr(
        faults, "streamablehttp_client", lambda url: ControlledTransport(cleanup_error=True)
    )
    monkeypatch.setattr(faults, "ClientSession", lambda *args: ControlledSession())
    result = faults.fault_mcp_disconnect(Path("unused"))
    assert result["status"] == "FAIL"
    assert "受控断连" in result["observed"]
    assert "受控传输清理异常" in result["details"]["cleanup_error"]
    assert result["metrics"][0]["statistics"]["sample_count"] == 1


def test_async_slow_subscriber_does_not_block_fast_delivery(real_report: dict[str, Any]) -> None:
    """500ms 异步慢订阅者不得阻塞发布，快订阅者必须实际全部送达。"""
    result = _fault(real_report, "slow_subscriber")
    metric = result["metrics"][0]
    assert result["status"] == "PASS"
    assert metric["statistics"]["sample_count"] == FAULT_SAMPLE_COUNT
    assert metric["statistics"]["p95"] <= SLOW_SUBSCRIBER_SLO_MS
    assert result["details"]["fast_subscriber_events"] == FAULT_SAMPLE_COUNT
    assert result["details"]["fast_delivered"] == FAULT_SAMPLE_COUNT


def test_plugin_exception_isolated_from_healthy_subscriber(real_report: dict[str, Any]) -> None:
    """插件回调异常不得传播或阻断健康订阅者。"""
    result = _fault(real_report, "plugin_exception")
    assert result["status"] == "PASS"
    assert result["details"]["healthy_subscriber_events"] == FAULT_SAMPLE_COUNT
    assert result["details"]["publish_error"] == "无"
    assert result["metrics"][0]["statistics"]["sample_count"] == FAULT_SAMPLE_COUNT


@pytest.mark.parametrize("none_side", ["baseline", "current"])
def test_baseline_none_values_are_not_arithmetic(none_side: str) -> None:
    """old/new 任一侧为 None 时不得算术，状态迁移仍决定回归。"""
    baseline = _make_contract_report()
    current = _make_contract_report()
    valid = common.make_metric("latency_ms", [10.0], 50.0, "有效样本")
    missing = common.make_metric("latency_ms", [], 50.0, "空样本")
    _replace_idle_metric(baseline, missing if none_side == "baseline" else valid)
    _replace_idle_metric(current, missing if none_side == "current" else valid)
    comparison = common.compare_reports(baseline, current)
    difference = _idle_difference(comparison)
    assert difference["numeric_comparable"] is False
    assert difference["delta"] is None
    assert difference["delta_percent"] is None
    if none_side == "current":
        assert difference["regression"] is True
        idle_change = next(
            item for item in comparison["workload_status_changes"] if item["id"] == "idle"
        )
        assert (idle_change["baseline"], idle_change["current"]) == ("PASS", "NOT_RUN")


def test_baseline_zero_and_relative_thresholds() -> None:
    """零基线保留绝对差，10% 边界外才标记回归或改善。"""
    baseline = _make_contract_report()
    current = _make_contract_report()
    _replace_idle_metric(baseline, common.make_metric("latency_ms", [0.0], 50.0, "零基线"))
    _replace_idle_metric(current, common.make_metric("latency_ms", [1.0], 50.0, "当前"))
    zero_difference = _idle_difference(common.compare_reports(baseline, current))
    assert zero_difference["delta"] == 1.0
    assert zero_difference["delta_percent"] is None
    assert zero_difference["regression"] is False
    _replace_idle_metric(baseline, common.make_metric("latency_ms", [100.0], 500.0, "基线"))
    _replace_idle_metric(current, common.make_metric("latency_ms", [111.0], 500.0, "回归"))
    regression = _idle_difference(common.compare_reports(baseline, current))
    _replace_idle_metric(current, common.make_metric("latency_ms", [89.0], 500.0, "改善"))
    improvement = _idle_difference(common.compare_reports(baseline, current))
    assert regression["regression"] is True and regression["delta_percent"] == 11.0
    assert improvement["improvement"] is True and improvement["delta_percent"] == -11.0


def test_baseline_outside_temp_rejected_before_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """baseline 路径校验必须先于任何文件打开，真实 data 不得被读取。"""
    def forbidden_open(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("路径校验前不得打开文件")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(ValueError, match="路径必须位于"):
        benchmark._read_baseline(Path("data/data.db"))


def test_report_output_temp_isolation_and_cleanup() -> None:
    """输出只能落在项目 temp，合法报告可读且隔离目录自动清理。"""
    report = _make_contract_report()
    with common.isolated_workspace("pytest-output-gate") as workspace:
        output = workspace / "report.json"
        common.write_report(report, output)
        loaded = json.loads(output.read_text(encoding="utf-8"))
        common.validate_report(loaded)
        assert loaded == report
        assert output.resolve().is_relative_to(common.TEMP_ROOT.resolve())
        marker = workspace / "marker.txt"
        marker.write_text("隔离数据", encoding="utf-8")
    assert not workspace.exists()
    assert not marker.exists()
    for invalid in (Path("data/report.json"), Path("temp/../data/report.json")):
        with pytest.raises(ValueError, match="路径必须位于"):
            benchmark._temp_path(invalid)


def test_benchmark_import_logging_never_touches_real_logs() -> None:
    """内存探针验证导入日志只进 temp，handler 关闭且目录可清理。"""
    source = IMPORT_PROBE_SOURCE.format(
        project_root=str(_PROJECT_ROOT),
        real_logs=str(_PROJECT_ROOT / "logs"),
        temp_root=str(_IMPORT_TEMP_ROOT),
    )
    environment = os.environ.copy()
    environment.pop("INSTRUCTIONX_LOG_DIR", None)
    environment.pop("PYTHONPATH", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", source],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=IMPORT_PROBE_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "IMPORT_PROBE_OK" in result.stdout
    assert _IMPORT_LOG_DIRECTORY.is_relative_to(_IMPORT_TEMP_ROOT)
    assert not _IMPORT_LOG_DIRECTORY.is_relative_to(_PROJECT_ROOT / "logs")


def test_not_run_summary_includes_internal_details() -> None:
    """NOT_RUN 汇总应分别统计顶层、项目和指标，并保留内部明细。"""
    report = _make_contract_report()
    _replace_idle_metric(report, common.make_metric("latency_ms", [], 5.0, "不可读"))
    report["fault_matrix"][0]["status"] = "NOT_RUN"
    assert benchmark._not_run_summary(report) == {"top_level": 1, "items": 2, "metrics": 1}
    details = benchmark._internal_not_run_details(report)
    assert "workload:idle" in details
    assert "workload:idle:latency_ms" in details
    assert "fault:database_corruption" in details
