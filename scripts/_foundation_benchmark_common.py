# -*- coding: utf-8 -*-
"""Task 0 基线采集的统计、报告、环境信息与基线比较工具。"""

import ctypes
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from ctypes import wintypes
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Any, Iterator, Sequence

from PySide6.QtCore import qVersion

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMP_ROOT = PROJECT_ROOT / "temp"
REPORT_TYPE = "instructionx_foundation_baseline"
SCHEMA_VERSION = 1
VALID_STATUSES = {"PASS", "FAIL", "NOT_RUN"}
WORKLOAD_IDS = (
    "idle",
    "typical_desktop",
    "long_running_32",
    "chart_1khz",
    "slow_io",
)
FAULT_IDS = (
    "database_corruption",
    "database_locked",
    "database_readonly",
    "disk_full",
    "process_kill",
    "provider_timeout",
    "mcp_disconnect",
    "slow_subscriber",
    "plugin_exception",
)
STATISTIC_KEYS = ("p50", "p95", "p99", "max", "sample_count")
REGRESSION_RELATIVE_THRESHOLD = 0.10
PERCENT_SCALE = 100.0
MILLISECONDS_PER_SECOND = 1000.0
ROUND_DIGITS = 6
POWER_QUERY_TIMEOUT_SECONDS = 3.0
EXIT_CODE_SEMANTICS = "退出 0 仅表示采集完成，不表示系统合格；FAIL 与 NOT_RUN 不被改写为通过。"


def summarize_samples(samples: Sequence[float]) -> dict[str, Any]:
    """按最近秩法计算 p50/p95/p99/最大值及样本数，拒绝非有限数。"""
    ordered = sorted(float(value) for value in samples)
    if any(not math.isfinite(value) for value in ordered):
        raise ValueError("样本必须全部为有限数值")
    result: dict[str, Any] = {"sample_count": len(ordered)}
    for name, percentile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
        result[name] = round(_nearest_rank(ordered, percentile), ROUND_DIGITS) if ordered else None
    result["max"] = round(ordered[-1], ROUND_DIGITS) if ordered else None
    return result


def _nearest_rank(ordered: Sequence[float], percentile: float) -> float:
    """返回已排序样本的最近秩百分位。"""
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def make_metric(
    name: str,
    samples: Sequence[float],
    threshold: float,
    method: str,
    unit: str = "ms",
    statistic: str = "p95",
) -> dict[str, Any]:
    """生成带 SLO、原始样本、统计值和测量方法的指标记录。"""
    stats = summarize_samples(samples)
    observed = stats[statistic]
    status = "NOT_RUN" if observed is None else "PASS" if observed <= threshold else "FAIL"
    return {
        "name": name,
        "unit": unit,
        "status": status,
        "samples": [round(float(value), ROUND_DIGITS) for value in samples],
        "statistics": stats,
        "measurement_method": method,
        "slo": {"statistic": statistic, "operator": "<=", "threshold": threshold},
    }


def derive_item_status(metrics: list[dict[str, Any]]) -> str:
    """统一派生项目状态：空指标 NOT_RUN，FAIL 优先，其次 NOT_RUN。"""
    if not metrics:
        return "NOT_RUN"
    if any(item["status"] == "FAIL" for item in metrics):
        return "FAIL"
    if any(item["status"] == "NOT_RUN" for item in metrics):
        return "NOT_RUN"
    return "PASS"


def derive_fault_status(
    behavior_passed: bool,
    metrics: list[dict[str, Any]],
    not_run: bool = False,
) -> str:
    """故障必须同时满足行为断言和全部指标 SLO，未执行优先标 NOT_RUN。"""
    if not_run:
        return "NOT_RUN"
    if not behavior_passed:
        return "FAIL"
    return derive_item_status(metrics)


def make_workload(
    workload_id: str,
    scope: str,
    metrics: list[dict[str, Any]],
    data_scale: dict[str, Any] | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """生成负载记录，状态由完整指标列表统一派生或显式标记错误。"""
    return {
        "id": workload_id,
        "status": status or derive_item_status(metrics),
        "execution_scope": scope,
        "data_scale": data_scale or {},
        "metrics": metrics,
    }


def make_fault(
    fault_id: str,
    severity: str,
    status: str,
    metrics: list[dict[str, Any]],
    expected: str = "故障应被检测且不得破坏数据或其他组件",
    observed: str = "自检构造的当前失败",
    scope: str = "CONTROLLED_FAKE",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """生成包含预期、实测、范围和统计信息的故障矩阵记录。"""
    return {
        "id": fault_id,
        "severity": severity,
        "status": status,
        "execution_scope": scope,
        "expected": expected,
        "observed": observed,
        "details": details or {},
        "metrics": metrics,
    }


def build_report(
    environment: dict[str, Any],
    configuration: dict[str, Any],
    workloads: list[dict[str, Any]],
    faults: list[dict[str, Any]],
    not_run: list[dict[str, Any]],
) -> dict[str, Any]:
    """汇总机器报告，分开表达采集完成与系统 qualification。"""
    failures = _current_failures(workloads, faults)
    has_not_run = bool(not_run) or any(
        item["status"] == "NOT_RUN" for item in workloads + faults
    )
    qualification = "FAIL" if failures else "NOT_RUN" if has_not_run else "PASS"
    return {
        "schema_version": SCHEMA_VERSION,
        "report_type": REPORT_TYPE,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "collection_status": "COMPLETED",
        "qualification_status": qualification,
        "exit_code_semantics": EXIT_CODE_SEMANTICS,
        "environment": environment,
        "configuration": configuration,
        "workloads": workloads,
        "fault_matrix": faults,
        "not_run": not_run,
        "current_failures": failures,
        "comparison": None,
    }


def _current_failures(
    workloads: list[dict[str, Any]], faults: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """提取项目或任一指标失败，兼容项目误标 PASS 的历史报告。"""
    workload_failures = [
        {
            "id": item["id"],
            "source": "workload",
            "severity": "P1",
            "status": "FAIL",
            "observed": _failed_metric_names(item),
        }
        for item in workloads
        if _has_failure(item)
    ]
    fault_failures = [
        {
            "id": item["id"],
            "source": "fault_matrix",
            "severity": item["severity"],
            "status": "FAIL",
            "observed": _fault_failure_observed(item),
        }
        for item in faults
        if _has_failure(item)
    ]
    return workload_failures + fault_failures


def _has_failure(item: dict[str, Any]) -> bool:
    """项目状态或任一指标为 FAIL 即存在当前失败。"""
    return item["status"] == "FAIL" or any(
        metric["status"] == "FAIL" for metric in item["metrics"]
    )


def _failed_metric_names(workload: dict[str, Any]) -> str:
    """列出触发负载失败的指标。"""
    names = [item["name"] for item in workload["metrics"] if item["status"] == "FAIL"]
    return "未通过指标：" + "、".join(names) if names else "负载执行失败"


def _fault_failure_observed(fault: dict[str, Any]) -> str:
    """在行为证据外补充被误标 PASS 项目的失败指标。"""
    failed_names = _failed_metric_names(fault)
    if failed_names == "负载执行失败":
        return fault["observed"]
    return f"{fault['observed']}；{failed_names}"


def validate_report(report: dict[str, Any]) -> None:
    """校验报告契约，结构不合法时抛出 ValueError。"""
    if report.get("report_type") != REPORT_TYPE or report.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("报告类型或 schema_version 不匹配")
    if report.get("collection_status") != "COMPLETED":
        raise ValueError("采集状态必须为 COMPLETED")
    _validate_ids(report.get("workloads", []), WORKLOAD_IDS, "负载")
    _validate_ids(report.get("fault_matrix", []), FAULT_IDS, "故障")
    for item in report["workloads"] + report["fault_matrix"]:
        _validate_item(item)
    for item in report.get("not_run", []):
        if item.get("status") != "NOT_RUN" or not item.get("reason"):
            raise ValueError("未执行项必须包含 NOT_RUN 与原因")


def _validate_ids(items: list[dict[str, Any]], expected: Sequence[str], label: str) -> None:
    """校验固定 ID 无缺失、无多余。"""
    actual = tuple(item.get("id") for item in items)
    if actual != tuple(expected):
        raise ValueError(f"{label} ID 或顺序不符合固定契约：{actual}")


def _validate_item(item: dict[str, Any]) -> None:
    """校验单个负载或故障的状态与指标统计。"""
    if item.get("status") not in VALID_STATUSES or not item.get("execution_scope"):
        raise ValueError(f"项目状态或执行范围非法：{item.get('id')}")
    if not item.get("metrics") and item["status"] == "PASS":
        raise ValueError(f"空指标列表不得标记 PASS：{item.get('id')}")
    for metric in item.get("metrics", []):
        stats = metric.get("statistics", {})
        if any(key not in stats for key in STATISTIC_KEYS):
            raise ValueError(f"指标统计字段不完整：{metric.get('name')}")
        if not metric.get("measurement_method") or "slo" not in metric:
            raise ValueError(f"指标缺少测量方法或 SLO：{metric.get('name')}")


def write_report(report: dict[str, Any], output: Path) -> None:
    """校验后以 UTF-8 原子写入机器可读 JSON 报告。"""
    validate_report(report)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, output)


@contextmanager
def isolated_workspace(label: str) -> Iterator[Path]:
    """在 temp 下建立自动清理的隔离目录，禁止默认数据目录落入运行时路径。"""
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"foundation-{label}-", dir=TEMP_ROOT) as directory:
        yield Path(directory)


def collect_environment() -> dict[str, Any]:
    """采集 CPU、内存、磁盘、Python、Qt 和可读取的电源模式。"""
    disk = shutil.disk_usage(TEMP_ROOT if TEMP_ROOT.exists() else PROJECT_ROOT)
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": {"processor": platform.processor() or "未公开", "logical_count": os.cpu_count()},
        "memory": _memory_info(),
        "disk": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free},
        "python": {"version": sys.version, "implementation": platform.python_implementation()},
        "qt": {"qt_version": qVersion(), "pyside6_version": _pyside_version()},
        "power_mode": _read_power_mode(),
    }


def _memory_info() -> dict[str, Any]:
    """返回当前进程 RSS；不支持时显式标记不可读。"""
    rss = process_rss_bytes()
    return {"process_rss_bytes": rss, "readable": rss is not None}


class ProcessMemoryCounters(ctypes.Structure):
    """Windows PROCESS_MEMORY_COUNTERS 的完整布局，用于读取工作集。"""

    _fields_ = (
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def process_rss_bytes() -> int | None:
    """在 Windows 通过系统 API 读取当前进程工作集，其他平台返回 None。"""
    if os.name != "nt":
        return None
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_process = ctypes.windll.kernel32.GetCurrentProcess
    get_process.restype = wintypes.HANDLE
    get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
    get_memory_info.restype = wintypes.BOOL
    process = get_process()
    ok = get_memory_info(process, ctypes.byref(counters), ctypes.sizeof(counters))
    return int(counters.WorkingSetSize) if ok else None


def _pyside_version() -> str:
    """读取 PySide6 包版本而不实例化 Qt GUI。"""
    return version("PySide6")


def _read_power_mode() -> dict[str, Any]:
    """使用本地 powercfg 读取活动电源方案，失败时记录不可读。"""
    if os.name != "nt":
        return {"readable": False, "scheme": "当前平台无 powercfg"}
    try:
        result = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=POWER_QUERY_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"readable": False, "scheme": str(error)}
    return {"readable": result.returncode == 0, "scheme": result.stdout.strip() or result.stderr.strip()}


def compare_reports(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """逐项比较统计值与状态，保留全部差异并标记回归。"""
    validate_report(baseline)
    validate_report(current)
    baseline_metrics = _metric_map(baseline)
    current_metrics = _metric_map(current)
    differences = [
        _metric_difference(key, baseline_metrics.get(key), current_metrics.get(key))
        for key in sorted(set(baseline_metrics) | set(current_metrics))
    ]
    workload_changes = _status_changes(baseline, current, "workloads")
    fault_changes = _status_changes(baseline, current, "fault_matrix")
    changes = differences + workload_changes + fault_changes
    regressions = sum(1 for item in changes if item["regression"])
    improvements = sum(1 for item in changes if item["improvement"])
    return {
        "baseline_generated_at": baseline["generated_at"],
        "current_generated_at": current["generated_at"],
        "status": "REGRESSION" if regressions else "NO_REGRESSION",
        "relative_regression_threshold": REGRESSION_RELATIVE_THRESHOLD,
        "regression_count": regressions,
        "improvement_count": improvements,
        "unchanged_count": len(changes) - regressions - improvements,
        "metric_differences": differences,
        "workload_status_changes": workload_changes,
        "fault_status_changes": fault_changes,
    }


def _metric_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """以来源、项目 ID 和指标名建立无冲突索引。"""
    result = {}
    for source, items in (("workload", report["workloads"]), ("fault", report["fault_matrix"])):
        for item in items:
            for metric in item["metrics"]:
                key = f"{source}:{item['id']}:{metric['name']}"
                result[key] = {"metric": metric, "item_status": item["status"]}
    return result


def _metric_difference(
    key: str, baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> dict[str, Any]:
    """生成单项差异；缺失指标或统计值均明确标为不可数值比较。"""
    if baseline is None or current is None:
        return _missing_metric_difference(key, baseline, current)
    old_metric, new_metric = baseline["metric"], current["metric"]
    statistic = new_metric["slo"]["statistic"]
    old_value = old_metric["statistics"][statistic]
    new_value = new_metric["statistics"][statistic]
    if old_value is None or new_value is None:
        return _non_numeric_metric_difference(key, statistic, old_value, new_value, baseline, current)
    delta = new_value - old_value
    relative = delta / old_value if old_value else None
    return {
        "id": key,
        "statistic": statistic,
        "baseline": old_value,
        "current": new_value,
        "delta": round(delta, ROUND_DIGITS),
        "delta_percent": round(relative * PERCENT_SCALE, ROUND_DIGITS) if relative is not None else None,
        "numeric_comparable": True,
        "regression": relative is not None and relative > REGRESSION_RELATIVE_THRESHOLD,
        "improvement": relative is not None and relative < -REGRESSION_RELATIVE_THRESHOLD,
    }


def _non_numeric_metric_difference(
    key: str,
    statistic: str,
    old_value: float | None,
    new_value: float | None,
    baseline: dict[str, Any],
    current: dict[str, Any],
) -> dict[str, Any]:
    """None 不参与算术，回归和改善完全由项目状态迁移决定。"""
    old_status = baseline["item_status"]
    new_status = current["item_status"]
    return {
        "id": key,
        "statistic": statistic,
        "baseline": old_value,
        "current": new_value,
        "delta": None,
        "delta_percent": None,
        "numeric_comparable": False,
        "regression": _status_regression(old_status, new_status),
        "improvement": _status_improvement(old_status, new_status),
        "reason": "任一侧统计值为 None，不能进行数值比较",
    }


def _missing_metric_difference(
    key: str, baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> dict[str, Any]:
    """将新增或缺失指标标为不可比较，而非当作无差异。"""
    old_status = baseline["item_status"] if baseline else "MISSING"
    new_status = current["item_status"] if current else "MISSING"
    return {
        "id": key,
        "statistic": None,
        "baseline": baseline is not None,
        "current": current is not None,
        "delta": None,
        "delta_percent": None,
        "numeric_comparable": False,
        "regression": _status_regression(old_status, new_status),
        "improvement": _status_improvement(old_status, new_status),
        "reason": "基线或当前报告缺少该指标，无法计算差异",
    }


def _status_changes(
    baseline: dict[str, Any], current: dict[str, Any], section: str
) -> list[dict[str, Any]]:
    """列出全部状态迁移，并将 PASS 后退化为 FAIL/NOT_RUN 标为回归。"""
    old = {item["id"]: item["status"] for item in baseline[section]}
    new = {item["id"]: item["status"] for item in current[section]}
    return [_status_change(item_id, old, new) for item_id in sorted(set(old) | set(new))]


def _status_regression(baseline_status: str, current_status: str) -> bool:
    """判断状态是否退化为 FAIL，或由 PASS 退化为 NOT_RUN。"""
    return (current_status == "FAIL" and baseline_status != "FAIL") or (
        baseline_status == "PASS" and current_status == "NOT_RUN"
    )


def _status_improvement(baseline_status: str, current_status: str) -> bool:
    """判断状态是否由 FAIL 恢复为 PASS。"""
    return baseline_status == "FAIL" and current_status == "PASS"


def _status_change(item_id: str, old: dict[str, str], new: dict[str, str]) -> dict[str, Any]:
    """计算单项目的回归和改善，不省略未变化项。"""
    baseline_status = old.get(item_id, "MISSING")
    current_status = new.get(item_id, "MISSING")
    return {
        "id": item_id,
        "baseline": baseline_status,
        "current": current_status,
        "regression": _status_regression(baseline_status, current_status),
        "improvement": _status_improvement(baseline_status, current_status),
    }


def process_cpu_seconds() -> float:
    """返回当前进程已消耗 CPU 秒数，用于采集过程环境补充。"""
    return time.process_time()
