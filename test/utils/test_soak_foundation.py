"""长稳采集器预热、资源峰值与异常完成状态测试。"""

import sys
import time
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIRECTORY))

import scripts.soak_foundation as soak_module
from scripts.soak_foundation import METRIC_LIMITS, SoakRunner


class _Components:
    """提供长稳采集器需要的最小组件边界。"""

    def __init__(self, _workspace):
        self.errors = []

    def cycle(self, _index):
        return {}

    def queue_snapshot(self):
        return {}

    def close(self):
        return None


class _Gui:
    """记录真实采集器是否请求了 GUI 突发。"""

    def __init__(self):
        self.burst_count = 0

    def burst(self):
        self.burst_count += 1
        return {"chart_interval_ms": [1.0]}


def _runner(tmp_path, hours=1.0, warmup_seconds=300.0):
    return SoakRunner(
        hours, 60.0, tmp_path / "soak.json", skip_gui=True,
        warmup_seconds=warmup_seconds,
    )


def test_run_separates_warmup_from_measurement(tmp_path, monkeypatch):
    """预热和测量分别计时，预热样本不进入正式指标。"""
    calls = []
    runner = _runner(tmp_path, hours=1 / 3600, warmup_seconds=123.0)
    monkeypatch.setattr(soak_module, "SoakComponents", _Components)

    def run_cycles(_started, duration, collect):
        calls.append((duration, collect))
        if collect:
            for name in METRIC_LIMITS:
                if not name.startswith("chart_"):
                    runner.series.add(name, 0.0)
        return duration

    monkeypatch.setattr(runner, "_run_cycles", run_cycles)
    monkeypatch.setattr(runner, "_cleanup", lambda _started: 1.0)
    report = runner.run()

    assert calls == [(123.0, False), (1.0, True)]
    assert report["warmup_completed"] is True
    assert report["completed"] is True
    assert report["elapsed_seconds"] == 1.0


def test_warmup_exception_cannot_complete(tmp_path, monkeypatch):
    """预热失败时即使异常清理耗时很长也不得视为完成。"""
    runner = _runner(tmp_path, hours=1 / 3600)
    monkeypatch.setattr(soak_module, "SoakComponents", _Components)

    def fail_warmup(_started, _duration, collect):
        assert collect is False
        raise RuntimeError("预热失败")

    monkeypatch.setattr(runner, "_run_cycles", fail_warmup)
    monkeypatch.setattr(runner, "_cleanup", lambda _started: 7200.0)
    report = runner.run()

    assert report["warmup_completed"] is False
    assert report["completed"] is False
    assert report["elapsed_seconds"] == 0.0
    assert report["qualification_status"] == "FAIL"
    assert "预热失败" in report["errors"][0]


def test_warmup_executes_gui_without_collecting_samples(tmp_path):
    """预热执行同样的 GUI 突发，但不污染正式测量序列。"""
    runner = _runner(tmp_path)
    runner.interval = 1.0
    runner._gui = _Gui()

    runner._collect_metrics(1, {"db_write": 2.0}, collect=False)
    assert runner._gui.burst_count == 1
    assert runner.series.snapshot() == {}

    runner._collect_metrics(1, {"db_write": 2.0}, collect=True)
    assert runner._gui.burst_count == 2
    assert runner.series.snapshot()["db_write"]["sample_count"] == 1
    assert runner.series.snapshot()["chart_interval_ms"]["sample_count"] == 1


def test_resource_and_queue_peaks_remain_failures_after_recovery(tmp_path):
    """资源和队列曾越界即失败，末尾回落不得清除失败证据。"""
    runner = _runner(tmp_path)
    runner.system_samples = [
        {"rss_bytes": 100, "handle_count": 100, "queues": {"event_slow": 0}},
        {"rss_bytes": 111, "handle_count": 106, "queues": {"event_slow": 257}},
        {"rss_bytes": 100, "handle_count": 100, "queues": {"event_slow": 0}},
    ]

    resource_failures = runner._resource_failures(100, 100)
    queue_failures = runner._queue_failures()

    assert any("内存增长比例 1.1100" in failure for failure in resource_failures)
    assert any("句柄增长比例 1.0600" in failure for failure in resource_failures)
    assert queue_failures == ["event_slow 队列 257 > 256"]


def test_incomplete_measurement_is_not_completed(tmp_path):
    """未完成预热或测量时长不足时完成标志必须为假。"""
    runner = _runner(tmp_path)
    runner._overall_started = time.perf_counter()

    warmup_report = runner._report(0.0, 7200.0, None, None)
    runner._warmup_completed = True
    partial_report = runner._report(0.0, 1.0, 100, 100)

    assert warmup_report["completed"] is False
    assert partial_report["completed"] is False
