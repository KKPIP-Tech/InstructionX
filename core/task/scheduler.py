"""
定时任务调度器

负责定时任务的调度和执行。
"""

from datetime import datetime
from typing import Optional, Callable, Any

from .task_model import ScheduledTask, TaskStatus, TaskThreadLocal

from utils.logging_tools import LoggerManager, get_name


class TaskScheduler:
    """
    定时任务调度器（轻量生命周期占位）

    历史版本会在后台线程中周期调用 `_check_and_run_tasks()`（空实现），
    线程每秒空醒一次。实际的定时任务检查由 BackgroundTaskManager 的
    `_check_scheduled_tasks()` daemon 线程承担（配合 SchedulerCallback）。

    当前版本已移除空转线程，仅保留 start()/stop() 生命周期接口以保持兼容。
    """

    def __init__(self):
        self._running = False

        # 日志管理器
        self._logger = LoggerManager()

    def start(self) -> None:
        """启动调度器（不再创建空转线程，仅标记运行状态）"""
        if self._running:
            return

        self._running = True
        self._logger.debug(get_name(), 'TaskScheduler started (scheduling is driven by BackgroundTaskManager)')

    def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._logger.debug(get_name(), 'TaskScheduler stopped')

    @property
    def is_running(self) -> bool:
        """调度器是否处于运行状态"""
        return self._running


class SchedulerCallback:
    """
    调度器回调处理器

    负责处理定时任务的执行和回调。
    """

    def __init__(self):
        # 注：历史版本曾持有 self._lock（threading.Lock），但从未被使用，已作为死代码移除
        self._logger = LoggerManager()

    def execute_scheduled_task(
        self,
        task: ScheduledTask,
        execute_func: Callable,
        callback: Optional[Callable] = None
    ) -> Any:
        """
        执行定时任务

        注意：本方法在线程池 worker 线程中执行（包括 callback）。
        插件如需在回调中操作 Qt UI，请使用信号槽或
        QMetaObject.invokeMethod 编组到主线程。

        Args:
            task: 定时任务
            execute_func: 执行函数
            callback: 回调函数

        Returns:
            任务执行结果
        """
        result = None
        error = None

        try:
            # 设置当前任务到线程本地存储
            TaskThreadLocal.set_current_task(task)

            # 执行任务函数（args 与 kwargs 同时传递，互不排斥）
            result = execute_func(*task.args, **task.kwargs)

        except Exception as e:
            error = str(e)
            self._logger.error(get_name(), f'Error executing scheduled task {task.task_id}: {e}')

        finally:
            TaskThreadLocal.clear_current_task()

        # 执行回调函数
        if callback:
            try:
                # 根据是否有错误确定状态
                status = TaskStatus.FAILED if error else TaskStatus.COMPLETED
                callback(task.task_id, status, result, error)
            except Exception as e:
                self._logger.error(get_name(), f'Error in scheduled task callback: {e}')

        return result

    def should_run(self, task: ScheduledTask) -> bool:
        """
        检查任务是否应该执行

        Args:
            task: 定时任务

        Returns:
            是否应该执行
        """
        if not task.enabled:
            return False

        if task.next_run is None:
            return True

        return datetime.now() >= task.next_run
