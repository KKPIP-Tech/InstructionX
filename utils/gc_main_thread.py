# -*- coding: utf-8 -*-
"""主线程循环垃圾回收守卫：把 Python 循环 GC 收敛到 GUI 线程。

**背景（2026-11-04 现场证据）**：应用崩溃日志与 Windows 事件查看器记录到
同一原生崩溃签名（``python314.dll`` / ``0xc0000005`` / 偏移 ``0x91cc9``）。
其中一段转储的当前线程正在后台任务中执行 ``Garbage-collecting``，同进程
主线程正在 Qt 图表 ``paint_axes``；另两段发生在主线程绘制时，签名相同。
CPython 的循环 GC 会在任意分配线程触发；若被回收的是 PySide6/Qt 包装
对象，其 C++ 析构会在非 GUI 线程执行，可能导致原生访问违例。该签名在
多个版本、不同业务插件下反复出现，与具体业务功能无关。

**做法**：启动完成后 ``gc.freeze()`` 把启动期对象移出扫描，``gc.disable()``
禁止任意线程自动触发循环回收，随后由主线程 QTimer 分代执行 ``gc.collect()``。
年轻代高频、中代低频、完整回收更低频，避免每 30 秒都扫描完整堆。所有回收
仍在 GUI 线程，只影响循环垃圾；引用计数回收（绝大多数 Qt 对象）不受影响。

**边界**：这是缓解措施，不是已证实的原生根因修复；若长时间运行仍闪退，
需按 docs/utils/gc-main-thread.md 的排查步骤取得原生 dump。
"""

from __future__ import annotations

import gc
import time

from PySide6.QtCore import QObject, QTimer

from utils.logging_tools import LoggerManager, get_name

#: 主线程定时器与年轻代回收节拍：及时清理高频短生命周期引用环
COLLECT_INTERVAL_MS = 2_000
#: 中代回收节拍：处理熬过年轻代的对象，避免年轻代回收无法覆盖长期引用环
MIDDLE_COLLECT_INTERVAL_MS = 30_000
#: 完整回收节拍：完整堆扫描成本最高，仅低频兜底，不作为常规回收手段
FULL_COLLECT_INTERVAL_MS = 300_000
#: 单次回收超过该耗时记 WARNING（用于评估是否需调整分代节拍）
SLOW_COLLECT_WARN_MS = 100.0

_GENERATION_YOUNG = 0
_GENERATION_MIDDLE = 1
_GENERATION_FULL = 2
_MS_PER_SEC = 1000.0

_logger = LoggerManager()


class MainThreadGcGuard(QObject):
    """在 GUI 线程分代执行循环 GC；安装/卸载幂等。

    定时器默认每 2 秒回收年轻代、每 30 秒回收中代、每 5 分钟完整回收。
    手动 :meth:`collect_now` 仍执行完整回收，并重置自动调度截止时间。

    典型用法（main.py，进入 ``QApplication.exec()`` 之前）::

        guard = MainThreadGcGuard(application)
        guard.install()
        ...
        guard.shutdown()
    """

    def __init__(self, parent=None) -> None:
        """只创建计时器与调度状态，不改变全局 GC 状态。"""
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(COLLECT_INTERVAL_MS)
        self._timer.timeout.connect(self._collect_scheduled)
        self._installed = False
        self._reset_schedule()

    @property
    def installed(self) -> bool:
        """当前是否已接管循环 GC（测试与日志用）。"""
        return self._installed

    def install(self) -> None:
        """冻结启动期对象、关闭自动循环 GC、启动主线程分代回收（幂等）。"""
        if self._installed:
            return
        gc.collect(_GENERATION_FULL)
        gc.freeze()
        gc.disable()
        self._reset_schedule()
        self._installed = True
        self._timer.start()
        _logger.info(
            get_name(),
            f"主线程GC守卫已启用：young={COLLECT_INTERVAL_MS}ms，"
            f"middle={MIDDLE_COLLECT_INTERVAL_MS}ms，"
            f"full={FULL_COLLECT_INTERVAL_MS}ms；后台线程不再自动触发循环回收")

    def collect_now(self) -> int:
        """立即完整回收并重置自动调度；返回回收对象数。"""
        collected = self._collect_generation(_GENERATION_FULL)
        self._reset_schedule()
        return collected

    def _reset_schedule(self) -> None:
        """以当前单调时钟重建中代与完整回收的截止时间。"""
        now = time.monotonic()
        self._last_middle_at = now
        self._last_full_at = now

    def _collect_scheduled(self) -> None:
        """执行一次到期的分代回收，完整回收同时覆盖较低代际。"""
        now = time.monotonic()
        generation = self._scheduled_generation(now)
        self._collect_generation(generation)
        self._mark_collected_at(now, generation)

    def _scheduled_generation(self, now: float) -> int:
        """按到期顺序选择完整、中代或年轻代回收。"""
        full_elapsed_ms = (now - self._last_full_at) * _MS_PER_SEC
        if full_elapsed_ms >= FULL_COLLECT_INTERVAL_MS:
            return _GENERATION_FULL
        middle_elapsed_ms = (now - self._last_middle_at) * _MS_PER_SEC
        if middle_elapsed_ms >= MIDDLE_COLLECT_INTERVAL_MS:
            return _GENERATION_MIDDLE
        return _GENERATION_YOUNG

    def _mark_collected_at(self, now: float, generation: int) -> None:
        """回收完成后更新时间基准，避免同一拍重复触发多个代际。"""
        if generation == _GENERATION_FULL:
            self._last_full_at = now
            self._last_middle_at = now
        elif generation == _GENERATION_MIDDLE:
            self._last_middle_at = now

    def _collect_generation(self, generation: int) -> int:
        """在调用方线程执行指定代际回收，并记录耗时与对象数。"""
        started = time.perf_counter()
        collected = gc.collect(generation)
        elapsed_ms = (time.perf_counter() - started) * _MS_PER_SEC
        self._log_collection(generation, collected, elapsed_ms)
        return collected

    def _log_collection(self, generation: int, collected: int,
                        elapsed_ms: float) -> None:
        """常规分代信息记 DEBUG，慢回收记 WARNING 供现场对账。"""
        _logger.debug(
            get_name(),
            f"主线程GC分代回收：generation={generation}，耗时 {elapsed_ms:.1f}ms，"
            f"回收 {collected} 个对象")
        if elapsed_ms < SLOW_COLLECT_WARN_MS:
            return
        _logger.warning(
            get_name(),
            f"主线程GC回收耗时 {elapsed_ms:.1f}ms（generation={generation}，"
            f"回收 {collected} 个对象），超过 {SLOW_COLLECT_WARN_MS:.0f}ms 预警线")

    def shutdown(self) -> None:
        """停止节拍并恢复自动循环 GC（幂等；进程退出前调用）。"""
        if not self._installed:
            return
        self._timer.stop()
        gc.enable()
        self._installed = False
        _logger.info(get_name(), "主线程GC守卫已关闭：恢复自动循环回收")
