"""
UI/工作线程编组工具

框架中的任务回调（core.task）与数据订阅回调（core.data）在工作线程执行，
插件若在这些回调里直接操作 Qt UI 会跨线程崩溃。本模块提供将调用编组
（marshal）到 UI 线程执行的工具：

- is_ui_thread: 判断当前线程是否为 UI 线程
- run_in_ui_thread: 异步投递到 UI 线程执行（立即返回）
- run_in_ui_thread_sync: 投递到 UI 线程并阻塞等待返回结果

典型场景::

    # 插件在后台任务回调中更新界面
    def on_task_finished(result):
        run_in_ui_thread(self.label.setText, f"完成: {result}")

注意：本模块仅提供编组工具，不改变 core.task / core.data 的回调线程语义。
无 QApplication 实例时安全降级为在当前线程直接执行并记录 warning。
"""

from __future__ import annotations

import functools
import threading
from typing import Any, Callable

# 驻留 UI 线程的调用投递器（惰性创建）
_invoker = None
_invoker_lock = threading.Lock()


def _log_warning(message: str) -> None:
    """记录警告日志（日志系统不可用时静默忽略）。"""
    try:
        from utils.logging_tools import LoggerManager
        LoggerManager().warning('thread_utils', message)
    except Exception:
        pass


def _get_app():
    """获取当前 QApplication 实例（无实例或 PySide6 不可用时返回 None）。"""
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:
        return None
    return QApplication.instance()


def is_ui_thread() -> bool:
    """
    判断当前线程是否为 Qt UI（主）线程

    返回:
        bool: 当前线程是 UI 线程时为 True；无 QApplication 实例时为 False
    """
    app = _get_app()
    if app is None:
        return False
    from PySide6.QtCore import QThread
    return QThread.currentThread() == app.thread()


def _get_invoker():
    """
    获取驻留 UI 线程的调用投递器（惰性创建）

    通过 QObject Signal + Qt.QueuedConnection 将可调用对象投递到
    UI 线程事件循环执行（等价于 QMetaObject.invokeMethod 的 QueuedConnection）。
    """
    global _invoker
    with _invoker_lock:
        if _invoker is None:
            from PySide6.QtCore import QObject, Signal, Qt

            class _Invoker(QObject):
                """调用投递器：submitted 信号携带可调用对象，在 UI 线程执行。"""

                submitted = Signal(object)

                def __init__(self):
                    super().__init__()
                    self.submitted.connect(self._execute, Qt.QueuedConnection)

                def _execute(self, callable_obj):
                    callable_obj()

            invoker = _Invoker()
            app = _get_app()
            if app is not None:
                # 确保投递器归属于 UI 线程
                invoker.moveToThread(app.thread())
            _invoker = invoker
    return _invoker


def run_in_ui_thread(func: Callable, *args: Any, **kwargs: Any) -> None:
    """
    在 UI 线程执行 func(*args, **kwargs)（异步投递，立即返回）

    - 当前已是 UI 线程：直接同步执行；
    - 其他线程：通过 QObject Signal + Qt.QueuedConnection 投递到 UI 线程事件循环；
    - 无 QApplication 实例：降级为在当前线程直接执行并记录 warning。

    参数:
        func: 要在 UI 线程执行的可调用对象
        args/kwargs: 传递给 func 的参数
    """
    app = _get_app()
    if app is None:
        _log_warning(
            f'无 QApplication 实例，{getattr(func, "__name__", repr(func))} '
            f'在当前线程直接执行（降级）'
        )
        func(*args, **kwargs)
        return
    if is_ui_thread():
        func(*args, **kwargs)
        return
    _get_invoker().submitted.emit(functools.partial(func, *args, **kwargs))


def run_in_ui_thread_sync(func: Callable, *args: Any, timeout: float | None = None, **kwargs: Any) -> Any:
    """
    在 UI 线程执行 func(*args, **kwargs) 并阻塞等待返回结果

    - 当前已是 UI 线程：直接执行（避免 BlockingQueuedConnection 造成的自死锁）；
    - 无 QApplication 实例：降级为在当前线程直接执行并记录 warning；
    - func 抛出的异常会在调用线程重新抛出。

    参数:
        func: 要在 UI 线程执行的可调用对象
        timeout: 最长等待秒数，None 表示无限等待；超时抛 TimeoutError

    返回:
        func 的返回值
    """
    app = _get_app()
    if app is None:
        _log_warning(
            f'无 QApplication 实例，{getattr(func, "__name__", repr(func))} '
            f'在当前线程直接执行（降级）'
        )
        return func(*args, **kwargs)
    if is_ui_thread():
        return func(*args, **kwargs)

    done = threading.Event()
    box: dict = {}

    def _wrapper():
        try:
            box['result'] = func(*args, **kwargs)
        except BaseException as exc:
            box['error'] = exc
        finally:
            done.set()

    _get_invoker().submitted.emit(_wrapper)
    if not done.wait(timeout):
        raise TimeoutError(
            f'等待 UI 线程执行 {getattr(func, "__name__", repr(func))} 超时'
        )
    if 'error' in box:
        raise box['error']
    return box.get('result')
