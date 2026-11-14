# -*- coding: utf-8 -*-
"""InstructionX Task 0 基线采集入口；退出 0 只表示采集流程完成。"""

import argparse
import atexit
import json
import logging
import os
import shutil
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Any, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
_IMPORT_TEMP_ROOT = PROJECT_ROOT / "temp"
_IMPORT_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
_IMPORT_LOG_DIRECTORY = Path(tempfile.mkdtemp(prefix="foundation-import-logs-", dir=_IMPORT_TEMP_ROOT))
_PREVIOUS_LOG_DIRECTORY = os.environ.get("INSTRUCTIONX_LOG_DIR")
os.environ["INSTRUCTIONX_LOG_DIR"] = str(_IMPORT_LOG_DIRECTORY)

from _foundation_benchmark_common import (  # noqa: E402
    TEMP_ROOT,
    build_report,
    collect_environment,
    compare_reports,
    isolated_workspace,
    process_cpu_seconds,
    write_report,
)
from _foundation_faults import run_abrupt_child, run_faults  # noqa: E402
from _foundation_workloads import (  # noqa: E402
    CHART_FRAMES,
    CHART_POINTS_PER_FRAME,
    LATENCY_SAMPLES,
    LONG_TASK_COUNT,
    SEED_KEY_COUNT,
    run_workloads,
)

DEFAULT_OUTPUT = Path("temp/foundation-baseline.json")


def create_parser() -> argparse.ArgumentParser:
    """创建命令行解析器，隐藏子进程参数仅供父采集器调用。"""
    parser = argparse.ArgumentParser(description="采集 InstructionX 五类负载与九项故障的当前基线")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="temp 下的 JSON 输出路径")
    parser.add_argument("--baseline", type=Path, help="用于逐项差异与回归比较的历史 JSON 报告")
    parser.add_argument("--abrupt-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--child-db", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行采集并保证导入期日志在退出时完成清理。"""
    try:
        args = create_parser().parse_args(argv)
        if args.abrupt_child:
            return _run_child_mode(args.child_db)
        try:
            run_benchmark(args.output, args.baseline)
        except Exception as error:
            print(f"基线采集失败：{type(error).__name__}: {error}", file=sys.stderr)
            traceback.print_exc()
            return 2
        return 0
    finally:
        _cleanup_import_logging()


def _run_child_mode(child_db: Path | None) -> int:
    """校验路径，并在 os._exit 前显式清理导入期日志。"""
    if child_db is None:
        print("自愿退出子进程缺少 --child-db。", file=sys.stderr)
        return 2
    database = _temp_path(child_db)
    _cleanup_import_logging()
    run_abrupt_child(database)
    return 0


def run_benchmark(output: Path, baseline: Path | None = None) -> dict[str, Any]:
    """执行完整采集，写出报告并打印中文摘要；预期故障不改变退出语义。"""
    output_path = _temp_path(output)
    baseline_report = _read_baseline(baseline) if baseline is not None else None
    with isolated_workspace("baseline") as workspace:
        _configure_runtime(workspace)
        report = _collect_report(workspace)
        if baseline_report is not None:
            report["comparison"] = compare_reports(baseline_report, report)
        write_report(report, output_path)
    _print_summary(report, output_path)
    return report


def _temp_path(path: Path) -> Path:
    """将输入与输出限制在项目 temp 内，防止访问真实运行目录。"""
    resolved = path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()
    if not resolved.is_relative_to(TEMP_ROOT.resolve()):
        raise ValueError(f"路径必须位于 {TEMP_ROOT} 内：{resolved}")
    return resolved


def _configure_runtime(workspace: Path) -> None:
    """隔离框架日志；SDK 预期断连错误以报告证据为准，不刷控制台。"""
    os.environ["INSTRUCTIONX_LOG_DIR"] = str(workspace / "logs")
    os.environ["INSTRUCTIONX_DATAPROVIDER_BACKEND"] = "sqlite"
    logging.disable(logging.CRITICAL)


def _collect_report(workspace: Path) -> dict[str, Any]:
    """采集环境、固定负载与故障矩阵，并补充过程开销。"""
    environment = collect_environment()
    started_wall = time.perf_counter()
    started_cpu = process_cpu_seconds()
    workloads = run_workloads(workspace / "workloads")
    faults = run_faults(workspace / "faults")
    configuration = _configuration(time.perf_counter() - started_wall, process_cpu_seconds() - started_cpu)
    return build_report(environment, configuration, workloads, faults, _not_run_items())


def _configuration(wall_seconds: float, cpu_seconds: float) -> dict[str, Any]:
    """返回固定样本配置、计时方法和采集过程资源消耗。"""
    return {
        "latency_samples": LATENCY_SAMPLES,
        "seed_keys": SEED_KEY_COUNT,
        "long_running_tasks": LONG_TASK_COUNT,
        "chart_frames": CHART_FRAMES,
        "chart_points_per_frame": CHART_POINTS_PER_FRAME,
        "clock": "time.perf_counter 墙钟；CPU 使用 time.process_time",
        "percentile_method": "最近秩法：rank=ceil(p*N)，从升序样本取第 rank 项",
        "collection_wall_seconds": round(wall_seconds, 6),
        "collection_process_cpu_seconds": round(cpu_seconds, 6),
        "workspace_policy": "全部临时数据、日志和子进程数据库均位于 temp，退出自动清理",
    }


def _not_run_items() -> list[dict[str, str]]:
    """列出本次安全边界外或未执行的验收能力。"""
    return [
        {
            "id": "real_gui_chart",
            "capability": "真实 Qt 1kHz 图表渲染与 fps",
            "status": "NOT_RUN",
            "reason": "本采集不创建 QApplication；纯算法结果不得冒充真实 GUI fps，需在有显示环境另行验收",
        },
        {
            "id": "full_gui_startup_shutdown",
            "capability": "真实主窗口启动与关闭",
            "status": "NOT_RUN",
            "reason": "当前启动/关闭指标仅覆盖 SQLite 与任务管理器，不覆盖 Qt 主窗口",
        },
        {
            "id": "external_provider_network",
            "capability": "真实外部 Provider 网络与超时恢复",
            "status": "NOT_RUN",
            "reason": "任务禁止访问真实网络；Provider 项仅覆盖 LLMProvider 下的本地受控适配器",
        },
        {
            "id": "physical_disk_full",
            "capability": "真实物理磁盘耗尽",
            "status": "NOT_RUN",
            "reason": "为避免破坏本机，磁盘满使用受控 ENOSPC 替身",
        },
        {
            "id": "endurance_72h",
            "capability": "72 小时稳定性、内存趋势与长期任务运行",
            "status": "NOT_RUN",
            "reason": "Task 0 仅执行短时基线，不把短时采集解释为 72 小时通过",
        },
    ]


def _read_baseline(path: Path) -> dict[str, Any]:
    """在 temp 边界内读取历史报告，路径校验先于文件打开。"""
    with _temp_path(path).open("r", encoding="utf-8") as stream:
        report = json.load(stream)
    if not isinstance(report, dict):
        raise ValueError("历史基线顶层必须为 JSON 对象")
    return report


def _not_run_summary(report: dict[str, Any]) -> dict[str, int]:
    """分别统计顶层能力、负载/故障项目和指标级 NOT_RUN。"""
    items = report["workloads"] + report["fault_matrix"]
    return {
        "top_level": len(report["not_run"]),
        "items": sum(item["status"] == "NOT_RUN" for item in items),
        "metrics": sum(
            metric["status"] == "NOT_RUN"
            for item in items
            for metric in item["metrics"]
        ),
    }


def _internal_not_run_details(report: dict[str, Any]) -> list[str]:
    """列出内部 NOT_RUN 项目和指标，避免只有数量而漏掉明细。"""
    details = []
    for source, items in (("workload", report["workloads"]), ("fault", report["fault_matrix"])):
        for item in items:
            if item["status"] == "NOT_RUN":
                details.append(f"{source}:{item['id']}")
            details.extend(
                f"{source}:{item['id']}:{metric['name']}"
                for metric in item["metrics"]
                if metric["status"] == "NOT_RUN"
            )
    return details


def _print_summary(report: dict[str, Any], output: Path) -> None:
    """输出当前失败及顶层、项目、指标三个层级的 NOT_RUN。"""
    failures = report["current_failures"]
    p0 = sum(item["severity"] == "P0" for item in failures)
    p1 = sum(item["severity"] == "P1" for item in failures)
    not_run = _not_run_summary(report)
    print(f"基线采集完成：{output}")
    print(f"系统判定：{report['qualification_status']}；当前失败 P0={p0}、P1={p1}")
    print(f"NOT_RUN：顶层能力={not_run['top_level']}；负载/故障项目={not_run['items']}；指标={not_run['metrics']}")
    for detail in _internal_not_run_details(report):
        print(f"[NOT_RUN] {detail}")
    for failure in failures:
        print(f"[{failure['severity']}/FAIL] {failure['source']}:{failure['id']}：{failure['observed']}")
    comparison = report.get("comparison")
    if comparison:
        print(f"基线比较：{comparison['status']}；回归={comparison['regression_count']}；改善={comparison['improvement_count']}")
    print("退出 0 仅表示采集完成，不表示系统合格。")


def _cleanup_import_logging() -> None:
    """关闭导入期 handler、清理目录并恢复环境，清理错误显式抛出。"""
    cleanup_error = None
    try:
        _close_import_log_handlers()
    except Exception as error:
        cleanup_error = error
    try:
        if _IMPORT_LOG_DIRECTORY.exists():
            shutil.rmtree(_IMPORT_LOG_DIRECTORY)
    except Exception as error:
        cleanup_error = cleanup_error or error
    _restore_log_environment()
    if cleanup_error is not None:
        raise cleanup_error


def _close_import_log_handlers() -> None:
    """只关闭属于本模块导入目录的 LoggerManager handler。"""
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


def _restore_log_environment() -> None:
    """恢复导入前日志环境，避免污染同进程后续调用。"""
    if _PREVIOUS_LOG_DIRECTORY is None:
        os.environ.pop("INSTRUCTIONX_LOG_DIR", None)
    else:
        os.environ["INSTRUCTIONX_LOG_DIR"] = _PREVIOUS_LOG_DIRECTORY


atexit.register(_cleanup_import_logging)

if __name__ == "__main__":
    sys.exit(main())
