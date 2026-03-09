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
    BackgroundTask, ScheduledTask, LongRunningTask, TaskType, TaskStatus
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
        self._running_long_running_tasks: Dict[str, LongRunningTask] = {}
        self._futures: Dict[str, Future] = {}  # task_id -> Future

        # 定时任务工厂注册表 {plugin_id: {"func": callable, "callback": callable}}
        self._scheduled_task_factories: Dict[str, Dict[str, Callable]] = {}

        # 长期任务工厂注册表 {plugin_id: {"func": callable, "callback": callable, "stop_callback": callable, "status_callback": callable}}
        self._long_running_task_factories: Dict[str, Dict[str, Callable]] = {}

        # 调度器
        self._scheduler = TaskScheduler()
        self._scheduler_callback = SchedulerCallback()

        # 线程安全锁
        self._task_lock = threading.RLock()

        # 停止事件（用于优雅关闭检查线程）
        self._stop_event = threading.Event()

        # 关闭标志（防止关闭后提交新任务）
        self._is_shutdown = False

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
            if self._is_shutdown:
                return None
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
        while not self._stop_event.is_set():
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

            # 等待 1 秒或直到停止事件被设置
            self._stop_event.wait(1.0)

    def _execute_scheduled_task(self, task: ScheduledTask) -> None:
        """执行定时任务"""
        if self._is_shutdown:
            return

        if task.func is None:
            print(f"Warning: Scheduled task {task.task_id} has no func, skipping")
            return

        task.last_run = datetime.now()
        task.calculate_next_run()

        self._storage.update_scheduled_task(task)

        try:
            self._executor.submit(
                self._scheduler_callback.execute_scheduled_task,
                task,
                task.func,
                task.callback
            )
        except RuntimeError as e:
            if "shutdown" in str(e).lower():
                pass  # 忽略关闭后的提交错误
            else:
                raise

    # ==================== 长期任务 ====================

    def register_long_running_task(
        self,
        plugin_id: str,
        name: str,
        func: Callable,
        callback: Optional[Callable] = None,
        stop_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        auto_restart: bool = True,
        args: tuple = (),
        kwargs: dict = None
    ) -> str:
        """
        注册长期任务

        长期任务会持续运行直到被显式停止，支持优雅停止和自动重启。

        Args:
            plugin_id: 插件 UUID
            name: 任务名称
            func: 任务执行函数（阻塞函数，会持续运行）
            callback: 可选的完成回调
            stop_callback: 可选的停止回调，用于优雅停止
            status_callback: 可选的状态更新回调
            auto_restart: 失败后是否自动重启，默认 True
            args: 函数位置参数
            kwargs: 函数关键字参数

        Returns:
            任务 ID
        """
        if kwargs is None:
            kwargs = {}
        task = LongRunningTask(
            plugin_id=plugin_id,
            name=name,
            func=func,
            callback=callback,
            stop_callback=stop_callback,
            status_callback=status_callback,
            auto_restart=auto_restart,
            args=args,
            kwargs=kwargs
        )

        self._storage.save_long_running_task(task)

        with self._task_lock:
            if self._is_shutdown:
                return None
            self._running_long_running_tasks[task.task_id] = task
            future = self._executor.submit(self._execute_long_running_task, task)
            self._futures[task.task_id] = future

        return task.task_id

    def register_long_running_task_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable] = None,
        stop_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        restore_callback: Optional[Callable] = None
    ) -> None:
        """
        注册长期任务工厂函数

        用于在应用启动时恢复长期任务。
        插件应该在 on_plugin_loaded 中调用此方法注册工厂。

        Args:
            plugin_id: 插件 UUID
            func: 任务执行函数
            callback: 可选的回调函数
            stop_callback: 可选的停止回调
            status_callback: 可选的状态更新回调
            restore_callback: 可选的恢复回调，任务恢复时调用
        """
        self._long_running_task_factories[plugin_id] = {
            "func": func,
            "callback": callback,
            "stop_callback": stop_callback,
            "status_callback": status_callback,
            "restore_callback": restore_callback
        }

        # 尝试恢复该插件的长期任务
        self.restore_long_running_tasks(plugin_id)

    def restore_long_running_tasks(self, plugin_id: str) -> int:
        """恢复指定插件的长期任务"""
        factory = self._long_running_task_factories.get(plugin_id)
        if not factory:
            return 0

        func = factory.get("func")
        callback = factory.get("callback")
        stop_callback = factory.get("stop_callback")
        status_callback = factory.get("status_callback")
        restore_callback = factory.get("restore_callback")  # 新增：恢复回调

        stored_tasks = self._storage.get_long_running_tasks_by_plugin(plugin_id)
        restored_count = 0

        for stored_task in stored_tasks:
            # 如果任务已经有 func，跳过
            if stored_task.func is not None:
                continue

            # 只恢复 enabled=True 的任务
            if not stored_task.enabled:
                # 如果任务被禁用，删除存储中的任务记录
                self._storage.delete_long_running_task(stored_task.task_id)
                continue

            # 检查任务状态，不恢复已完成/失败的任务
            if stored_task.current_status in ("completed", "failed", "stopped"):
                # 删除已完成的任务记录
                self._storage.delete_long_running_task(stored_task.task_id)
                continue

            # 检查任务是否已经在运行
            if stored_task.task_id in self._running_long_running_tasks:
                continue

            # 恢复 func 和回调
            stored_task.func = func
            stored_task.callback = callback
            stored_task.stop_callback = stop_callback
            stored_task.status_callback = status_callback

            with self._task_lock:
                if self._is_shutdown:
                    break
                self._running_long_running_tasks[stored_task.task_id] = stored_task
                future = self._executor.submit(self._execute_long_running_task, stored_task)
                self._futures[stored_task.task_id] = future

            # 调用恢复回调
            if restore_callback:
                try:
                    restore_callback(stored_task.task_id, stored_task)
                except Exception as e:
                    print(f"Error calling restore_callback: {e}")

            restored_count += 1

        return restored_count

    def stop_long_running_task(self, task_id: str, delete_from_storage: bool = True) -> bool:
        """
        停止长期任务

        Args:
            task_id: 任务 ID
            delete_from_storage: 是否从存储中删除任务（默认True，用户主动停止时删除）

        Returns:
            是否成功停止
        """
        with self._task_lock:
            task = self._running_long_running_tasks.get(task_id)
            if not task:
                return False

            # 调用停止回调
            if task.stop_callback:
                try:
                    task.stop_callback()
                except Exception as e:
                    print(f"Error calling stop_callback for task {task_id}: {e}")

            # 取消 future
            future = self._futures.get(task_id)
            if future and not future.done():
                future.cancel()

            # 从存储中删除任务（用户主动停止）
            if delete_from_storage:
                self._storage.delete_long_running_task(task_id)
            else:
                # 仅更新任务状态
                task.last_stopped_at = datetime.now()
                task.enabled = False
                self._storage.save_long_running_task(task)

            # 从运行中移除
            self._running_long_running_tasks.pop(task_id, None)
            self._futures.pop(task_id, None)

            return True

    def _execute_long_running_task(self, task: LongRunningTask) -> None:
        """执行长期任务"""
        task.last_started_at = datetime.now()
        task.error = None
        task.current_status = "running"
        self._storage.save_long_running_task(task)

        while True:
            try:
                if task.args or task.kwargs:
                    result = task.func(*task.args, **task.kwargs)
                else:
                    task.func()

                # 如果函数返回了（正常情况下不会），任务完成
                task.current_status = "completed"
                self._storage.save_long_running_task(task)

                if task.callback:
                    task.callback(task.task_id, TaskStatus.COMPLETED, result, None)

                # 任务完成后删除存储中的记录
                self._storage.delete_long_running_task(task.task_id)
                break

            except Exception as e:
                task.error = str(e)
                task.current_status = "failed"

                if task.callback:
                    task.callback(task.task_id, TaskStatus.FAILED, None, str(e))

                if task.auto_restart:
                    # 自动重启
                    task.restart_count += 1
                    task.current_status = "restarting"
                    self._storage.save_long_running_task(task)

                    # 等待一段时间后重启
                    import time
                    time.sleep(5)  # 5秒后重试

                    # 检查是否被取消
                    future = self._futures.get(task.task_id)
                    if future and future.cancelled():
                        break

                    # 重新提交任务
                    with self._task_lock:
                        if self._is_shutdown:
                            break
                        if task.task_id in self._running_long_running_tasks:
                            future = self._executor.submit(self._execute_long_running_task, task)
                            self._futures[task.task_id] = future
                    break
                else:
                    self._storage.save_long_running_task(task)
                    # 任务失败且不自动重启时，删除存储中的记录
                    self._storage.delete_long_running_task(task.task_id)
                    break

    def update_long_running_task_status(self, task_id: str, status: str) -> bool:
        """
        更新长期任务的状态

        Args:
            task_id: 任务 ID
            status: 状态描述

        Returns:
            是否成功更新
        """
        with self._task_lock:
            task = self._running_long_running_tasks.get(task_id)
            if not task:
                return False

            task.current_status = status
            self._storage.save_long_running_task(task)

            # 调用状态回调
            if task.status_callback:
                try:
                    task.status_callback(task_id, status)
                except Exception as e:
                    print(f"Error calling status_callback for task {task_id}: {e}")

            return True

    def get_long_running_tasks(self, plugin_id: Optional[str] = None) -> List[LongRunningTask]:
        """
        获取长期任务列表

        Args:
            plugin_id: 可选的插件 ID

        Returns:
            长期任务列表
        """
        if plugin_id:
            return self._storage.get_long_running_tasks_by_plugin(plugin_id)
        return self._storage.get_all_long_running_tasks()

    # ==================== 任务查询 ====================

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """获取指定任务"""
        with self._task_lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]

        return self._storage.get_task(task_id)

    def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]:
        """获取指定插件的所有任务（不包括长期任务）"""
        return self._storage.get_tasks_by_plugin(plugin_id)

    def get_all_tasks(self) -> List[BackgroundTask]:
        """获取所有任务（不包括长期任务）"""
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
        import time

        # 设置关闭标志，防止新任务提交
        self._is_shutdown = True

        # 停止所有长期任务
        with self._task_lock:
            # 首先尝试优雅停止
            for task_id in list(self._running_long_running_tasks.keys()):
                task = self._running_long_running_tasks.get(task_id)
                if task:
                    # 调用停止回调
                    if task.stop_callback:
                        try:
                            task.stop_callback()
                        except Exception as e:
                            print(f"Error calling stop_callback for task {task_id}: {e}")

                # 取消 future
                future = self._futures.get(task_id)
                if future:
                    future.cancel()

                # 删除存储中的任务记录
                self._storage.delete_long_running_task(task_id)

            # 清理
            self._running_long_running_tasks.clear()
            self._futures.clear()

        # 停止定时任务检查线程
        self._stop_event.set()

        self._scheduler.stop()

        # 关闭线程池，不等待任务完成
        self._executor.shutdown(wait=False, cancel_futures=True)

        # 等待一小段时间让线程退出
        time.sleep(0.5)

        BackgroundTaskManager._instance = None

    def __del__(self):
        """析构函数"""
        try:
            self._scheduler.stop()
        except Exception:
            pass
