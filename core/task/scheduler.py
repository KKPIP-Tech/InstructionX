"""
定时任务调度器

负责定时任务的调度和执行。
"""

import threading
import time
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from .task_model import ScheduledTask, TaskStatus, TaskThreadLocal

from utils.logging_tools import LoggerManager, get_name


class TaskScheduler:
    """
    定时任务调度器

    负责在后台线程中定期执行已注册的任务。
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # 调度间隔（秒）
        self._check_interval = 1.0

        # 日志管理器
        self._logger = LoggerManager()

    def start(self) -> None:
        """启动调度器"""
        if self._running:
            return

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TaskScheduler")
        self._thread.start()

    def stop(self) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _run_loop(self) -> None:
        """调度器主循环"""
        while self._running and not self._stop_event.is_set():
            try:
                self._check_and_run_tasks()
            except Exception as e:
                self._logger.error(get_name(), f'Scheduler loop error: {e}')

            # 等待下一次检查
            self._stop_event.wait(self._check_interval)

    def _check_and_run_tasks(self) -> None:
        """检查并执行到期的定时任务

        注意：此方法目前为空实现（pass）。实际的定时任务检查由
        BackgroundTaskManager 的 _check_scheduled_tasks() daemon 线程执行，
        该线程使用 SchedulerCallback 类来处理任务执行和回调。
        """
        pass


class SchedulerCallback:
    """
    调度器回调处理器

    负责处理定时任务的执行和回调。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._logger = LoggerManager()

    def execute_scheduled_task(
        self,
        task: ScheduledTask,
        execute_func: Callable,
        callback: Optional[Callable] = None
    ) -> Any:
        """
        执行定时任务

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

            # 执行任务函数
            if task.args:
                result = execute_func(*task.args)
            elif task.kwargs:
                result = execute_func(**task.kwargs)
            else:
                result = execute_func()

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
