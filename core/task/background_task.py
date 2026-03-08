"""
BackgroundTaskManager - 后台任务管理器

负责管理插件提交的后台任务和定时任务。
支持同步/异步任务执行、回调机制、任务状态查询和定时任务调度。
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any

from .task_model import (
    BackgroundTask, ScheduledTask, TaskType, TaskStatus
)
from .task_storage import TaskStorage
from .scheduler import TaskScheduler, SchedulerCallback


class BackgroundTaskManager:
    """
    后台任务管理器

    采用单例模式，负责管理所有后台任务和定时任务。
    支持同步任务、异步任务和定时任务的注册、执行和查询。

    Example:
        ```python
        # 获取实例
        manager = BackgroundTaskManager()

        # 注册异步任务
        task_id = manager.register_async_task(
            plugin_id="plugin-uuid",
            name="my_task",
            func=my_function,
            callback=my_callback,
            args=(arg1, arg2),
            kwargs={"key1": value1}
        )

        # 查询任务状态
        status = manager.get_task_status(task_id)
        ```
    """

    _instance: Optional['BackgroundTaskManager'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """初始化（只执行一次）"""
        if hasattr(self, '_initialized') and self._initialized:
            return

        self._initialized = True

        # 存储层
        self._storage = TaskStorage()

        # 线程池（用于异步任务执行）
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="BackgroundTask")

        # 运行时任务存储（不持久化 func 和 callback）
        self._running_tasks: Dict[str, BackgroundTask] = {}
        self._running_scheduled_tasks: Dict[str, ScheduledTask] = {}
        self._futures: Dict[str, Future] = {}  # task_id -> Future

        # 定时任务工厂注册表 {plugin_id: {"func": callable, "callback": callable}}
        self._scheduled_task_factories: Dict[str, Dict[str, Callable]] = {}

        # 调度器
        self._scheduler = TaskScheduler()
        self._scheduler_callback = SchedulerCallback()

        # 线程安全锁
        self._task_lock = threading.RLock()

        # 启动调度器
        self._scheduler.start()

        # 启动定时任务检查线程
        self._schedule_check_thread = threading.Thread(
            target=self._check_scheduled_tasks,
            daemon=True,
            name="ScheduledTaskChecker"
        )
        self._schedule_check_thread.start()

    def _restore_all_scheduled_tasks(self) -> None:
        """从存储恢复所有定时任务（不检查工厂）"""
        stored_tasks = self._storage.get_all_scheduled_tasks()

        for stored_task in stored_tasks:
            # 检查任务是否已经在运行
            if stored_task.task_id in self._running_scheduled_tasks:
                continue

            # 重新计算下次执行时间（如果已经过期）
            if stored_task.next_run and datetime.now() > stored_task.next_run:
                stored_task.calculate_next_run()

            # 添加到运行任务（不检查 func，等待工厂注册）
            with self._task_lock:
                self._running_scheduled_tasks[stored_task.task_id] = stored_task

    # ==================== 任务注册与执行 ====================

    def register_sync_task(
        self,
        plugin_id: str,
        name: str,
        func: Callable,
        callback: Optional[Callable] = None,
        args: tuple = (),
        kwargs: dict = None
    ) -> str:
        """注册并立即执行同步任务"""
        if kwargs is None:
            kwargs = {}
        task = BackgroundTask(
            plugin_id=plugin_id,
            name=name,
            task_type=TaskType.SYNC,
            func=func,
            callback=callback,
            args=args,
            kwargs=kwargs
        )

        self._execute_sync_task(task)
        return task.task_id

    def register_async_task(
        self,
        plugin_id: str,
        name: str,
        func: Callable,
        callback: Optional[Callable] = None,
        args: tuple = (),
        kwargs: dict = None
    ) -> str:
        """注册异步任务"""
        if kwargs is None:
            kwargs = {}
        task = BackgroundTask(
            plugin_id=plugin_id,
            name=name,
            task_type=TaskType.ASYNC,
            func=func,
            callback=callback,
            args=args,
            kwargs=kwargs
        )

        self._storage.save_task(task)

        with self._task_lock:
            self._running_tasks[task.task_id] = task
            future = self._executor.submit(self._execute_async_task, task)
            self._futures[task.task_id] = future

        return task.task_id

    def _execute_sync_task(self, task: BackgroundTask) -> None:
        """执行同步任务"""
        task.mark_running()

        try:
            if task.args or task.kwargs:
                result = task.func(*task.args, **task.kwargs)
            else:
                result = task.func()

            task.mark_completed(result)

        except Exception as e:
            task.mark_failed(str(e))

        finally:
            self._storage.save_task(task)
            self._execute_callback(task)

    def _execute_async_task(self, task: BackgroundTask) -> None:
        """执行异步任务"""
        task.mark_running()
        self._storage.save_task(task)

        try:
            if task.args or task.kwargs:
                result = task.func(*task.args, **task.kwargs)
            else:
                result = task.func()

            task.mark_completed(result)

        except Exception as e:
            task.mark_failed(str(e))

        finally:
            self._storage.save_task(task)

            with self._task_lock:
                self._running_tasks.pop(task.task_id, None)
                self._futures.pop(task.task_id, None)

            self._execute_callback(task)

    def _execute_callback(self, task: BackgroundTask) -> None:
        """执行任务回调函数"""
        if not task.callback:
            return

        try:
            task.callback(
                task.task_id,
                task.status,
                task.result,
                task.error
            )
        except Exception as e:
            print(f"Error executing callback for task {task.task_id}: {e}")

    # ==================== 定时任务 ====================

    def register_scheduled_task(
        self,
        plugin_id: str,
        name: str,
        func: Callable,
        interval: int,
        callback: Optional[Callable] = None,
        args: tuple = (),
        kwargs: dict = None
    ) -> str:
        """注册定时任务"""
        if kwargs is None:
            kwargs = {}
        task = ScheduledTask(
            plugin_id=plugin_id,
            name=name,
            func=func,
            callback=callback,
            interval=interval,
            args=args,
            kwargs=kwargs
        )

        task.calculate_next_run()
        self._storage.save_scheduled_task(task)

        with self._task_lock:
            self._running_scheduled_tasks[task.task_id] = task

        # 注册工厂函数
        self._scheduled_task_factories[plugin_id] = {
            "func": func,
            "callback": callback
        }

        return task.task_id

    def register_scheduled_task_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable] = None
    ) -> None:
        """
        注册定时任务工厂函数

        用于在应用启动时恢复定时任务。
        插件应该在 _create_widget 中调用此方法注册工厂。

        Args:
            plugin_id: 插件 UUID
            func: 任务执行函数
            callback: 可选的回调函数
        """
        self._scheduled_task_factories[plugin_id] = {
            "func": func,
            "callback": callback
        }

        # 尝试恢复该插件的定时任务
        self.restore_scheduled_tasks(plugin_id)

    def restore_scheduled_tasks(self, plugin_id: str) -> int:
        """恢复指定插件的定时任务"""
        factory = self._scheduled_task_factories.get(plugin_id)
        if not factory:
            return 0

        func = factory.get("func")
        callback = factory.get("callback")

        stored_tasks = self._storage.get_scheduled_tasks_by_plugin(plugin_id)
        restored_count = 0

        for stored_task in stored_tasks:
            # 如果任务已经有 func，跳过
            if stored_task.func is not None:
                continue

            # 检查任务是否已经在运行
            if stored_task.task_id in self._running_scheduled_tasks:
                continue

            # 恢复 func 和 callback
            stored_task.func = func
            stored_task.callback = callback

            # 重新计算下次执行时间
            if stored_task.next_run and datetime.now() > stored_task.next_run:
                stored_task.calculate_next_run()

            with self._task_lock:
                self._running_scheduled_tasks[stored_task.task_id] = stored_task

            restored_count += 1

        return restored_count

    def unregister_scheduled_task(self, task_id: str) -> bool:
        """注销定时任务"""
        with self._task_lock:
            task = self._running_scheduled_tasks.pop(task_id, None)

        if task:
            self._storage.delete_scheduled_task(task_id)
            return True

        return False

    def enable_scheduled_task(self, task_id: str) -> bool:
        """启用定时任务"""
        task = self._storage.get_scheduled_task(task_id)
        if not task:
            return False

        task.enabled = True
        task.calculate_next_run()

        self._storage.update_scheduled_task(task)

        with self._task_lock:
            self._running_scheduled_tasks[task_id] = task

        return True

    def disable_scheduled_task(self, task_id: str) -> bool:
        """禁用定时任务"""
        task = self._storage.get_scheduled_task(task_id)
        if not task:
            return False

        task.enabled = False
        self._storage.update_scheduled_task(task)

        with self._task_lock:
            self._running_scheduled_tasks.pop(task_id, None)

        return True

    def _check_scheduled_tasks(self) -> None:
        """检查并执行到期的定时任务"""
        while True:
            try:
                with self._task_lock:
                    tasks_to_run = []

                    for task_id, task in list(self._running_scheduled_tasks.items()):
                        # 如果 func 为 None，尝试从工厂恢复
                        if task.func is None:
                            factory = self._scheduled_task_factories.get(task.plugin_id)
                            if factory:
                                task.func = factory.get("func")
                                task.callback = factory.get("callback")

                        if self._scheduler_callback.should_run(task):
                            tasks_to_run.append(task)

                    for task in tasks_to_run:
                        self._execute_scheduled_task(task)

            except Exception as e:
                print(f"Error checking scheduled tasks: {e}")

            threading.Event().wait(1.0)

    def _execute_scheduled_task(self, task: ScheduledTask) -> None:
        """执行定时任务"""
        if task.func is None:
            print(f"Warning: Scheduled task {task.task_id} has no func, skipping")
            return

        task.last_run = datetime.now()
        task.calculate_next_run()

        self._storage.update_scheduled_task(task)

        self._executor.submit(
            self._scheduler_callback.execute_scheduled_task,
            task,
            task.func,
            task.callback
        )

    # ==================== 任务查询 ====================

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """获取指定任务"""
        with self._task_lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]

        return self._storage.get_task(task_id)

    def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]:
        """获取指定插件的所有任务"""
        return self._storage.get_tasks_by_plugin(plugin_id)

    def get_all_tasks(self) -> List[BackgroundTask]:
        """获取所有任务"""
        with self._task_lock:
            running_tasks = list(self._running_tasks.values())

        stored_tasks = self._storage.get_all_tasks()

        all_tasks = {}
        for task in running_tasks + stored_tasks:
            all_tasks[task.task_id] = task

        return list(all_tasks.values())

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        task = self.get_task(task_id)
        return task.status if task else None

    def get_scheduled_tasks(self, plugin_id: Optional[str] = None) -> List[ScheduledTask]:
        """获取定时任务列表"""
        if plugin_id:
            return self._storage.get_scheduled_tasks_by_plugin(plugin_id)
        return self._storage.get_all_scheduled_tasks()

    # ==================== 任务控制 ====================

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with self._task_lock:
            if task_id in self._running_tasks:
                future = self._futures.get(task_id)
                if future and not future.done():
                    future.cancel()

                task = self._running_tasks[task_id]
                task.mark_cancelled()
                self._storage.save_task(task)

                self._running_tasks.pop(task_id)
                self._futures.pop(task_id, None)
                return True

        return False

    def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int:
        """清理已完成的任务"""
        return self._storage.clear_completed_tasks(plugin_id)

    # ==================== 生命周期管理 ====================

    def shutdown(self) -> None:
        """关闭任务管理器"""
        self._scheduler.stop()
        self._executor.shutdown(wait=True)
        BackgroundTaskManager._instance = None

    def __del__(self):
        """析构函数"""
        try:
            self._scheduler.stop()
        except Exception:
            pass
