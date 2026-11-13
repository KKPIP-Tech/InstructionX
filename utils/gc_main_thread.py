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
禁止任意线程自动触发循环回收，随后由主线程 QTimer 定期 ``gc.collect()``。
只影响循环垃圾；引用计数回收（绝大多数 Qt 对象）不受影响。

**边界**：这是缓解措施，不是已证实的原生根因修复；若长时间运行仍闪退，
需按 docs/utils/gc-main-thread.md 的排查步骤取得原生 dump。
"""

from __future__ import annotations

import gc
import time

from PySide6.QtCore import QObject, QTimer

from utils.logging_tools import LoggerManager, get_name

#: 主线程回收节拍：过短会增加 GUI 线程停顿，过长会让循环垃圾暂存过久
COLLECT_INTERVAL_MS = 30_000
#: 单次回收超过该耗时记 WARNING（用于评估是否需调长节拍）
SLOW_COLLECT_WARN_MS = 100.0

_logger = LoggerManager()


class MainThreadGcGuard(QObject):
    """在主线程周期执行 ``gc.collect()``；安装/卸载幂等。

    典型用法（main.py，进入 ``QApplication.exec()`` 之前）::

        guard = MainThreadGcGuard(application)
        guard.install()
        ...
        guard.shutdown()
    """

    def __init__(self, parent=None) -> None:
        """只创建计时器，不改变全局 GC 状态。"""
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(COLLECT_INTERVAL_MS)
        self._timer.timeout.connect(self.collect_now)
        self._installed = False

    @property
    def installed(self) -> bool:
        """当前是否已接管循环 GC（测试与日志用）。"""
        return self._installed

    def install(self) -> None:
        """冻结启动期对象、关闭自动循环 GC、启动主线程回收节拍（幂等）。"""
        if self._installed:
            return
        gc.collect()
        gc.freeze()
        gc.disable()
        self._installed = True
        self._timer.start()
        _logger.info(
            get_name(),
            f"主线程GC守卫已启用：interval={COLLECT_INTERVAL_MS}ms；"
            "后台线程不再自动触发循环回收")

    def collect_now(self) -> int:
        """在主线程执行一次完整循环回收；返回回收对象数。"""
        started = time.perf_counter()
        collected = gc.collect()
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms >= SLOW_COLLECT_WARN_MS:
            _logger.warning(
                get_name(),
                f"主线程GC回收耗时 {elapsed_ms:.1f}ms（回收 {collected} 个对象），"
                f"超过 {SLOW_COLLECT_WARN_MS:.0f}ms 预警线")
        return collected

    def shutdown(self) -> None:
        """停止节拍并恢复自动循环 GC（幂等；进程退出前调用）。"""
        if not self._installed:
            return
        self._timer.stop()
        gc.enable()
        self._installed = False
        _logger.info(get_name(), "主线程GC守卫已关闭：恢复自动循环回收")
