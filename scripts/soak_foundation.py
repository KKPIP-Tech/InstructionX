"""手动混合负载长稳采集；周期落盘且未完成明确 NOT_RUN。"""

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict

from _soak_workloads import (
    GuiChartWorkload,
    SoakComponents,
    SoakSeries,
    process_handle_count,
    process_rss_bytes,
)
from core.observability.sanitize import sanitize_text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("temp/foundation-soak.json")
DEFAULT_SAMPLE_INTERVAL_SECONDS = 60.0
DEFAULT_WARMUP_SECONDS = 300.0
MIXED_CYCLE_INTERVAL_SECONDS = 0.1
MEBIBYTE = 1024 * 1024
MEMORY_GROWTH_LIMIT = 1.10
HANDLE_GROWTH_LIMIT = 1.05
CLEANUP_MARKERS = ("cancel scope", "task was destroyed", "resourcewarning", "unclosed")
QUEUE_LIMITS = {"event_slow": 256, "task_normal": 256, "task_high": 64, "task_long": 128}
METRIC_LIMITS = {
    "db_write": ("p95", 20.0), "db_read": ("p95", 5.0),
    "event_publish": ("p99", 10.0), "high_task": ("p99", 100.0),
    "normal_task": ("p99", 1000.0), "mcp_roundtrip": ("p95", 100.0),
    "chart_apply_ms": ("p95", 16.7), "chart_interval_ms": ("p95", 16.7),
    "chart_interval_p99_ms": ("p99", 33.0),
}


class _CleanupGate(logging.Handler):
    """把清理警告计入长稳失败，不依赖人工阅读日志。"""

    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        message = record.getMessage().lower()
        if any(marker in message for marker in CLEANUP_MARKERS):
            self.messages.append(sanitize_text(record.getMessage()))


class SoakRunner:
    """执行有截止期的真实混合负载，周期生成机器可读证据。"""

    def __init__(
        self, hours: float, interval: float, output: Path, skip_gui: bool,
        warmup_seconds: float = DEFAULT_WARMUP_SECONDS,
    ):
        self.hours = hours
        self.interval = interval
        self.output = output
        self.skip_gui = skip_gui
        self.warmup_seconds = warmup_seconds
        self.series = SoakSeries()
        self.errors = []
        self.system_samples = []
        self.cleanup_gate = _CleanupGate()
        self._components = None
        self._gui = None
        self.gui_error = ""
        self._baseline_rss = None
        self._baseline_handles = None
        self._warmup_completed = False
        self._overall_started = 0.0

    def run(self) -> Dict:
        """先以真实负载预热，再独立计时测量并周期生成证据。"""
        overall_started = time.perf_counter()
        self._overall_started = overall_started
        measurement_started = None
        logging.getLogger().addHandler(self.cleanup_gate)
        workspace = Path(tempfile.mkdtemp(prefix="foundation-soak-", dir=PROJECT_ROOT / "temp"))
        log_directory = self.output.with_suffix(".logs")
        os.environ["INSTRUCTIONX_LOG_DIR"] = str(log_directory)
        try:
            self._components = SoakComponents(workspace)
            if not self.skip_gui:
                try:
                    self._gui = GuiChartWorkload()
                except Exception as error:
                    self.gui_error = sanitize_text(error)
            self._run_cycles(overall_started, self.warmup_seconds, collect=False)
            measurement_started = time.perf_counter()
            self._warmup_completed = True
            self._components.cycle(0)
            if self._gui is not None:
                self._gui.burst()
            self._baseline_rss, self._baseline_handles = self._system_sample(measurement_started)
            elapsed = self._run_cycles(
                measurement_started, self.hours * 3600, collect=True
            )
        except Exception as error:
            self.errors.append(f"runner: {sanitize_text(error)}")
        finally:
            cleanup_started = measurement_started or overall_started
            cleanup_elapsed = self._cleanup(cleanup_started)
            elapsed = cleanup_elapsed if measurement_started is not None else 0.0
            report = self._report(
                cleanup_started, elapsed, self._baseline_rss, self._baseline_handles
            )
            self._write(report)
            logging.getLogger().removeHandler(self.cleanup_gate)
            shutil.rmtree(workspace, ignore_errors=True)
        return report

    def _run_cycles(self, started: float, duration: float, collect: bool) -> float:
        """运行指定时长的混合负载，预热阶段不污染测量样本。"""
        index = 0
        next_sample = started + self.interval
        with ThreadPoolExecutor(max_workers=1) as executor:
            while time.perf_counter() - started < duration:
                index += 1
                future = executor.submit(self._components.cycle, index)
                while not future.done():
                    if self._gui is not None:
                        self._gui.application.processEvents()
                    time.sleep(0.001)
                metrics = future.result()
                self._collect_metrics(index, metrics, collect)
                now = time.perf_counter()
                if collect and now >= next_sample:
                    self._system_sample(started)
                    self._write(self._report(
                        started, now - started, self._baseline_rss, self._baseline_handles
                    ))
                    next_sample = now + self.interval
                time.sleep(MIXED_CYCLE_INTERVAL_SECONDS)
        return time.perf_counter() - started

    def _collect_metrics(
        self, index: int, metrics: Dict[str, float], collect: bool
    ) -> None:
        """预热和测量都施加 GUI 突发，仅测量阶段保存样本。"""
        if collect:
            for name, value in metrics.items():
                self.series.add(name, value)
        if self._gui is None or index % max(1, int(self.interval)) != 0:
            return
        gui_metrics = self._gui.burst()
        if not collect:
            return
        for name, values in gui_metrics.items():
            for value in values:
                self.series.add(name, value)

    def _cleanup(self, started: float) -> float:
        if self._gui is not None:
            self._gui.close()
        if self._components is not None:
            self._components.close()
            self.errors.extend(self._components.errors)
        self._system_sample(started)
        return time.perf_counter() - started

    def _system_sample(self, started: float):
        rss = process_rss_bytes()
        handles = process_handle_count()
        sample = {
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "rss_bytes": rss,
            "handle_count": handles,
            "queues": self._components.queue_snapshot() if self._components else {},
        }
        self.system_samples.append(sample)
        return rss, handles

    def _report(self, started, elapsed, baseline_rss, baseline_handles) -> Dict:
        completed = self._warmup_completed and elapsed >= self.hours * 3600
        failures = self._failures(baseline_rss, baseline_handles, completed)
        status = "FAIL" if failures else "PASS" if completed else "NOT_RUN"
        return {
            "qualification_status": status,
            "requested_hours": self.hours,
            "warmup_seconds": self.warmup_seconds,
            "warmup_completed": self._warmup_completed,
            "elapsed_seconds": round(elapsed, 6),
            "total_elapsed_seconds": round(time.perf_counter() - self._overall_started, 6),
            "completed": completed,
            "failures": failures,
            "metrics": self.series.snapshot(),
            "system_samples": self.system_samples,
            "errors": (
                self.errors
                + (self._components.errors if self._components is not None else [])
                + self.cleanup_gate.messages
            ),
            "gui_status": "NOT_RUN" if self._gui is None else "EXECUTED",
            "gui_error": self.gui_error,
            "limits": {
                "memory_growth": MEMORY_GROWTH_LIMIT,
                "handle_growth": HANDLE_GROWTH_LIMIT,
                "queues": QUEUE_LIMITS,
                "metrics": METRIC_LIMITS,
            },
        }

    def _failures(self, baseline_rss, baseline_handles, completed: bool) -> list[str]:
        failures = list(self.errors) + self.cleanup_gate.messages
        if self._components is not None:
            failures.extend(self._components.errors)
        failures.extend(self._metric_failures(completed))
        failures.extend(self._resource_failures(baseline_rss, baseline_handles))
        failures.extend(self._queue_failures())
        return failures

    def _metric_failures(self, completed: bool) -> list[str]:
        failures = []
        metrics = self.series.snapshot()
        for name, (statistic, limit) in METRIC_LIMITS.items():
            metric = metrics.get(name)
            if metric is None:
                if name.startswith("chart_") and (self._gui is None or not completed):
                    continue
                failures.append(f"{name}: 无有效样本")
                continue
            if metric[statistic] > limit:
                failures.append(f"{name} {statistic}={metric[statistic]:.4f}ms > {limit}ms")
        return failures

    def _resource_failures(self, baseline_rss, baseline_handles) -> list[str]:
        """检查全部测量采样，禁止结束清理后的回落掩盖中途增长。"""
        failures = []
        rss_values = [sample["rss_bytes"] for sample in self.system_samples if sample["rss_bytes"]]
        handle_values = [
            sample["handle_count"] for sample in self.system_samples if sample["handle_count"]
        ]
        if baseline_rss and rss_values:
            ratio = max(rss_values) / baseline_rss
            if ratio > MEMORY_GROWTH_LIMIT:
                failures.append(f"内存增长比例 {ratio:.4f} > {MEMORY_GROWTH_LIMIT}")
        if baseline_handles and handle_values:
            ratio = max(handle_values) / baseline_handles
            if ratio > HANDLE_GROWTH_LIMIT:
                failures.append(f"句柄增长比例 {ratio:.4f} > {HANDLE_GROWTH_LIMIT}")
        return failures

    def _queue_failures(self) -> list[str]:
        failures = []
        for name, limit in QUEUE_LIMITS.items():
            depth = max(
                (sample["queues"].get(name, 0) for sample in self.system_samples),
                default=0,
            )
            if depth > limit:
                failures.append(f"{name} 队列 {depth} > {limit}")
        return failures

    def _write(self, report: Dict) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.output.with_suffix(self.output.suffix + ".tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.output)


def _output_path(value: Path) -> Path:
    resolved = (PROJECT_ROOT / value).resolve() if not value.is_absolute() else value.resolve()
    if not resolved.is_relative_to((PROJECT_ROOT / "temp").resolve()):
        raise ValueError("报告路径必须位于项目 temp 内")
    return resolved


def main() -> int:
    """执行长稳采集；FAIL 返回 1，未完成返回 2。"""
    parser = argparse.ArgumentParser(description="运行混合负载长稳并输出周期资源与延迟证据")
    parser.add_argument("--hours", type=float, default=72.0)
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL_SECONDS)
    parser.add_argument("--warmup-seconds", type=float, default=DEFAULT_WARMUP_SECONDS)
    parser.add_argument("--skip-gui", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.hours <= 0 or args.sample_interval <= 0:
        parser.error("hours 与 sample-interval 必须大于 0")
    if args.warmup_seconds < 0:
        parser.error("warmup-seconds 不得小于 0")
    report = SoakRunner(
        args.hours, args.sample_interval, _output_path(args.output), args.skip_gui,
        warmup_seconds=args.warmup_seconds,
    ).run()
    status = report["qualification_status"]
    print(f"长稳采集：{status}；报告：{_output_path(args.output)}")
    return 1 if status == "FAIL" else 2 if status == "NOT_RUN" else 0


if __name__ == "__main__":
    sys.exit(main())
