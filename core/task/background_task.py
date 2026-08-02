"""
BackgroundTaskManager - 后台任务管理器

负责管理插件提交的后台任务和定时任务。
支持同步/异步任务执行、回调机制、任务状态查询和定时任务调度。
"""

import threading
# 注意：shutdown 中的线程池等待线程使用模块级导入的 Thread，
# 保证其创建路径与调度线程（threading.Thread）解耦。
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any

from core.interfaces.i_task_manager import ITaskManager
from .task_model import (
    BackgroundTask, ScheduledTask, LongRunningTask, TaskType, TaskStatus
)
from .task_storage import TaskStorage
from .scheduler import TaskScheduler, SchedulerCallback

from utils.logging_tools import LoggerManager, get_name


# 长期任务状态字符串（模块级常量；值与持久化 JSON 中的字符串严格一致，不可改动）
LONG_TASK_STATUS_RUNNING = "running"
LONG_TASK_STATUS_COMPLETED = "completed"
LONG_TASK_STATUS_FAILED = "failed"
LONG_TASK_STATUS_RESTARTING = "restarting"
LONG_TASK_STATUS_STOPPED = "stopped"


class BackgroundTaskManager(ITaskManager):
    """
    后台任务管理器

    采用单例模式，负责管理所有后台任务和定时任务。
    支持同步任务、异步任务和定时任务的注册、执行和查询。

    注意：所有任务回调（callback/stop_callback/status_callback）均在线程池
    worker 线程或调度线程中执行。插件如需在回调中操作 Qt UI，请使用信号槽
    或 QMetaObject.invokeMethod 编组到主线程。

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

    # ==================== 可配常量 ====================

    # 优雅停止单个长期任务的等待上限（秒）
    LONG_TASK_STOP_TIMEOUT = 3.0
    # 关闭时等待线程池结束的总上限（秒）
    EXECUTOR_SHUTDOWN_TIMEOUT = 10.0
    # 长期任务自动重启的初始退避间隔（秒）
    AUTO_RESTART_INITIAL_DELAY = 5.0
    # 长期任务自动重启的最大退避间隔（秒）
    AUTO_RESTART_MAX_DELAY = 300.0
    # 长期任务最大自动重启次数
    MAX_AUTO_RESTARTS = 10
    # 过期任务记录保留天数
    TASK_RECORD_MAX_AGE_DAYS = 30
    # 异步任务线程池默认工作线程数
    DEFAULT_MAX_WORKERS = 4
    # 定时任务检查线程的轮询间隔（秒）
    SCHEDULE_CHECK_INTERVAL = 1.0
    # 关闭时等待定时任务检查线程退出的上限（秒）
    CHECK_THREAD_JOIN_TIMEOUT = 2.0

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

        # 日志管理器
        self._logger = LoggerManager()

        # 线程池（用于异步任务执行）
        self._executor = ThreadPoolExecutor(
            max_workers=self.DEFAULT_MAX_WORKERS, thread_name_prefix="BackgroundTask"
        )

        # 运行时任务存储（不持久化 func 和 callback）
        self._running_tasks: Dict[str, BackgroundTask] = {}
        self._running_scheduled_tasks: Dict[str, ScheduledTask] = {}
        self._running_long_running_tasks: Dict[str, LongRunningTask] = {}
        self._futures: Dict[str, Future] = {}  # task_id -> Future

        # 定时任务工厂注册表（双级键，同插件多个工厂函数互不覆盖）
        # {plugin_id: {"func": 最近注册的 func, "callback": 最近注册的 callback,
        #              "funcs": {func_name: {"func": callable, "callback": callable}}}}
        self._scheduled_task_factories: Dict[str, Dict[str, Any]] = {}

        # 长期任务工厂注册表（双级键，结构同上，条目额外包含
        # stop_callback/status_callback/restore_callback）
        self._long_running_task_factories: Dict[str, Dict[str, Any]] = {}

        # 长期任务待重启定时器 {task_id: threading.Timer}
        self._restart_timers: Dict[str, threading.Timer] = {}

        # 已警告过"缺少工厂函数"的定时任务（同任务只警告一次）
        self._warned_no_func_tasks: set = set()

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

        # 清理过期的任务记录（默认保留 30 天），失败不影响启动
        try:
            self._storage.cleanup_old_tasks(self.TASK_RECORD_MAX_AGE_DAYS)
        except Exception as e:
            self._logger.warning(get_name(), f'Cleanup of old task records failed: {e}')

    # ==================== 工厂注册辅助 ====================

    @staticmethod
    def _func_key(func: Callable) -> str:
        """
        获取可调用对象的稳定标识（用于工厂双级键归档）

        优先使用 __qualname__，取不到时退化为 __name__ / str(func)。
        """
        key = getattr(func, "__qualname__", None)
        if not isinstance(key, str) or not key:
            key = getattr(func, "__name__", None)
        if not isinstance(key, str) or not key:
            key = str(func)
        return key

    def _archive_scheduled_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable]
    ) -> None:
        """归档定时任务工厂（双级键；顶层 func/callback 保留最近注册值以兼容旧结构）"""
        factory = self._scheduled_task_factories.setdefault(
            plugin_id, {"func": None, "callback": None, "funcs": {}}
        )
        factory.setdefault("funcs", {})
        factory["func"] = func
        factory["callback"] = callback
        factory["funcs"][self._func_key(func)] = {"func": func, "callback": callback}

    def _archive_long_running_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable],
        stop_callback: Optional[Callable],
        status_callback: Optional[Callable],
        restore_callback: Optional[Callable]
    ) -> None:
        """归档长期任务工厂（双级键；顶层保留最近注册值以兼容旧结构）"""
        factory = self._long_running_task_factories.setdefault(
            plugin_id, {
                "func": None, "callback": None, "stop_callback": None,
                "status_callback": None, "restore_callback": None, "funcs": {}
            }
        )
        factory.setdefault("funcs", {})
        entry = {
            "func": func,
            "callback": callback,
            "stop_callback": stop_callback,
            "status_callback": status_callback,
            "restore_callback": restore_callback,
        }
        factory.update(entry)
        factory["funcs"][self._func_key(func)] = entry

    def _resolve_factory_entry(
        self,
        registry: Dict[str, Dict[str, Any]],
        plugin_id: str,
        func_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        按 plugin_id + func_name 解析工厂条目

        解析顺序：
        1. funcs 双级键精确匹配；
        2. 旧记录（无 func_name）回退：该插件只有一个工厂时用之，
           多个时记 warning 并使用第一个；
        3. 兼容旧版单工厂结构（顶层 "func" 键）。

        Returns:
            工厂条目字典，找不到时返回 None
        """
        factory = registry.get(plugin_id)
        if not factory:
            return None

        funcs_map = factory.get("funcs") or {}

        # 精确匹配
        if func_name and func_name in funcs_map:
            return funcs_map[func_name]

        if func_name:
            self._logger.warning(
                get_name(),
                f'No factory found for func {func_name} of plugin {plugin_id}, falling back'
            )

        entries = list(funcs_map.values())
        if not entries and factory.get("func") is not None:
            # 兼容旧版单工厂结构 {"func": ..., "callback": ...}
            entries = [factory]

        if not entries:
            return None

        if len(entries) > 1:
            self._logger.warning(
                get_name(),
                f'Plugin {plugin_id} has {len(entries)} factories, using the first for task without func_name'
            )

        return entries[0]

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
        """
        注册并立即执行同步任务

        注意：callback 在调用方线程中同步执行；如需操作 Qt UI，
        请使用信号槽或 QMetaObject.invokeMethod 编组到主线程。
        """
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
    ) -> Optional[str]:
        """
        注册异步任务

        注意：callback 在线程池 worker 线程中执行；如需操作 Qt UI，
        请使用信号槽或 QMetaObject.invokeMethod 编组到主线程。

        Returns:
            任务 ID；管理器已关闭时返回 None
        """
        if kwargs is None:
            kwargs = {}
        with self._task_lock:
            # 先检查关闭标志再持久化，避免产生幽灵任务
            if self._is_shutdown:
                return None

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

            with self._task_lock:
                # 取消竞态防护：已取消的任务不再覆盖为完成
                if task.status != TaskStatus.CANCELLED:
                    task.mark_completed(result)

        except Exception as e:
            with self._task_lock:
                # 取消竞态防护：已取消的任务不再覆盖为失败
                if task.status != TaskStatus.CANCELLED:
                    task.mark_failed(str(e))

        finally:
            with self._task_lock:
                # 已取消状态已由 cancel_task 落盘，此处不覆盖
                if task.status != TaskStatus.CANCELLED:
                    self._storage.save_task(task)

                self._running_tasks.pop(task.task_id, None)
                self._futures.pop(task.task_id, None)

            self._execute_callback(task)

    def _execute_callback(self, task: BackgroundTask) -> None:
        """执行任务回调函数（在任务执行线程中调用，UI 操作请编组到主线程）"""
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
            self._logger.error(get_name(), f'Error executing callback for task {task.task_id}: {e}')

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
    ) -> Optional[str]:
        """
        注册定时任务

        注意：func 与 callback 在线程池 worker 线程中执行；如需操作 Qt UI，
        请使用信号槽或 QMetaObject.invokeMethod 编组到主线程。

        Args:
            plugin_id: 插件 UUID
            name: 任务名称
            func: 任务执行函数
            interval: 执行间隔（秒）
            callback: 可选的完成回调
            args: 函数位置参数
            kwargs: 函数关键字参数

        Returns:
            任务 ID；管理器已关闭时记 WARNING 并返回 None（与其他注册方法一致）
        """
        if kwargs is None:
            kwargs = {}
        with self._task_lock:
            # 先检查关闭标志再持久化，避免产生幽灵任务（与 register_async_task 对齐）
            if self._is_shutdown:
                self._logger.warning(
                    get_name(),
                    f'Rejecting scheduled task registration after shutdown: {plugin_id}/{name}'
                )
                return None
        task = ScheduledTask(
            plugin_id=plugin_id,
            name=name,
            func=func,
            callback=callback,
            interval=interval,
            args=args,
            kwargs=kwargs
        )
        # 记录函数标识，用于重启后按 plugin_id + func_name 精确匹配工厂
        task.func_name = self._func_key(func)

        task.calculate_next_run()
        self._storage.save_scheduled_task(task)

        with self._task_lock:
            self._running_scheduled_tasks[task.task_id] = task

        # 归档工厂函数（同插件注册多个不同函数互不覆盖）
        self._archive_scheduled_factory(plugin_id, func, callback)

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
        插件应该在 on_plugin_loaded 中调用此方法注册工厂。
        同一插件可注册多个不同函数，按 func.__qualname__ 归档，互不覆盖。

        Args:
            plugin_id: 插件 UUID
            func: 任务执行函数
            callback: 可选的回调函数
        """
        self._archive_scheduled_factory(plugin_id, func, callback)

        # 尝试恢复该插件的定时任务
        self.restore_scheduled_tasks(plugin_id)

    def restore_scheduled_tasks(self, plugin_id: str) -> int:
        """恢复指定插件的定时任务

        Args:
            plugin_id: 插件 UUID

        Returns:
            成功恢复的任务数量
        """
        factory = self._scheduled_task_factories.get(plugin_id)
        if not factory:
            return 0

        stored_tasks = self._storage.get_scheduled_tasks_by_plugin(plugin_id)
        restored_count = 0

        for stored_task in stored_tasks:
            # 已持有运行时函数（本进程内注册的任务），无需恢复
            if stored_task.func is not None:
                continue

            # 检查任务是否已经在运行
            if stored_task.task_id in self._running_scheduled_tasks:
                continue

            # 按 plugin_id + func_name 精确查找工厂；旧记录（无 func_name）
            # 回退到该插件唯一工厂（多个时记 warning 用第一个）
            entry = self._resolve_factory_entry(
                self._scheduled_task_factories,
                plugin_id,
                getattr(stored_task, "func_name", "") or ""
            )
            if not entry:
                continue

            # 恢复 func 和 callback
            stored_task.func = entry.get("func")
            stored_task.callback = entry.get("callback")

            # 重新计算下次执行时间
            if stored_task.next_run and datetime.now() > stored_task.next_run:
                stored_task.calculate_next_run()

            with self._task_lock:
                self._running_scheduled_tasks[stored_task.task_id] = stored_task

            restored_count += 1

        return restored_count

    def unregister_scheduled_task(self, task_id: str) -> bool:
        """注销定时任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功注销（存储中不存在该任务记录时返回 False）
        """
        with self._task_lock:
            # 运行表与持久化存储是两套登记：禁用/未恢复的任务不在运行表，
            # 但存储记录仍在，注销必须以存储删除为准（否则禁用态任务
            # 永远无法注销，形成僵尸记录）
            self._running_scheduled_tasks.pop(task_id, None)

        return self._storage.delete_scheduled_task(task_id)

    def enable_scheduled_task(self, task_id: str) -> bool:
        """启用定时任务（重算下次执行时间并加入运行列表）

        Args:
            task_id: 任务 ID

        Returns:
            是否成功启用（任务不存在时返回 False）
        """
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
        """禁用定时任务（保留存储记录，从运行列表移除）

        Args:
            task_id: 任务 ID

        Returns:
            是否成功禁用（任务不存在时返回 False）
        """
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
                            entry = self._resolve_factory_entry(
                                self._scheduled_task_factories,
                                task.plugin_id,
                                getattr(task, "func_name", "") or ""
                            )
                            if entry:
                                task.func = entry.get("func")
                                task.callback = entry.get("callback")

                        if task.func is None:
                            # 同一任务只警告一次，避免每秒刷日志
                            if task_id not in self._warned_no_func_tasks:
                                self._warned_no_func_tasks.add(task_id)
                                self._logger.warning(get_name(), f'Scheduled task {task.task_id} ({task.name}) has no func - did you forget to register a factory?')
                            continue

                        self._warned_no_func_tasks.discard(task_id)

                        if self._scheduler_callback.should_run(task):
                            tasks_to_run.append(task)

                    for task in tasks_to_run:
                        self._execute_scheduled_task(task)

            except Exception as e:
                self._logger.error(get_name(), f'Error checking scheduled tasks: {e}')

            # 等待一个轮询间隔或直到停止事件被设置
            self._stop_event.wait(self.SCHEDULE_CHECK_INTERVAL)

    def _execute_scheduled_task(self, task: ScheduledTask) -> None:
        """执行定时任务"""
        if self._is_shutdown:
            return

        if task.func is None:
            self._logger.warning(get_name(), f'Scheduled task {task.task_id} has no func, skipping')
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
        except RuntimeError:
            # 线程池关闭后 submit 会抛 RuntimeError；仅在已关闭时忽略，
            # 其他情况继续抛出（避免用脆弱的字符串匹配判断关闭原因）
            if not self._is_shutdown:
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
    ) -> Optional[str]:
        """
        注册长期任务

        长期任务会持续运行直到被显式停止，支持优雅停止和自动重启
        （指数退避 + 最大次数限制，见类常量 AUTO_RESTART_* / MAX_AUTO_RESTARTS）。

        注意：所有回调均在线程池 worker 线程或定时器线程中执行；
        如需操作 Qt UI，请使用信号槽或 QMetaObject.invokeMethod 编组到主线程。

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
            任务 ID；管理器已关闭时返回 None
        """
        if kwargs is None:
            kwargs = {}
        with self._task_lock:
            # 先检查关闭标志再持久化，避免产生幽灵任务
            if self._is_shutdown:
                return None

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
            # 记录函数标识，用于重启后按 plugin_id + func_name 精确匹配工厂
            task.func_name = self._func_key(func)

            self._storage.save_long_running_task(task)

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
        同一插件可注册多个不同函数，按 func.__qualname__ 归档，互不覆盖。

        Args:
            plugin_id: 插件 UUID
            func: 任务执行函数
            callback: 可选的回调函数
            stop_callback: 可选的停止回调
            status_callback: 可选的状态更新回调
            restore_callback: 可选的恢复回调，任务恢复时调用
        """
        self._archive_long_running_factory(
            plugin_id, func, callback, stop_callback, status_callback, restore_callback
        )

        # 尝试恢复该插件的长期任务
        self.restore_long_running_tasks(plugin_id)

    def restore_long_running_tasks(self, plugin_id: str) -> int:
        """
        恢复指定插件的长期任务

        仅恢复"崩溃中断"的任务（enabled=True 且状态非 completed/failed/stopped）：
        - 正常退出（shutdown）会把运行中任务标记为 stopped，恢复时不自动重启；
        - 被用户禁用的任务（enabled=False）保留记录、不启动；
        - 崩溃中断的任务（状态仍为 running/restarting 等）自动重启。
        """
        factory = self._long_running_task_factories.get(plugin_id)
        if not factory:
            return 0

        stored_tasks = self._storage.get_long_running_tasks_by_plugin(plugin_id)
        restored_count = 0

        for stored_task in stored_tasks:
            # 已持有运行时函数（本进程内注册的任务），无需恢复
            if stored_task.func is not None:
                continue

            # 禁用的任务保留记录、不启动（用户显式禁用，与 disable_scheduled_task 语义一致）
            if not stored_task.enabled:
                continue

            # 正常停止/已完成/已失败的任务保留记录、不自动重启
            if stored_task.current_status in (
                LONG_TASK_STATUS_COMPLETED, LONG_TASK_STATUS_FAILED, LONG_TASK_STATUS_STOPPED
            ):
                continue

            # 检查任务是否已经在运行
            if stored_task.task_id in self._running_long_running_tasks:
                continue

            # 按 plugin_id + func_name 精确查找工厂；旧记录（无 func_name）
            # 回退到该插件唯一工厂（多个时记 warning 用第一个）
            entry = self._resolve_factory_entry(
                self._long_running_task_factories,
                plugin_id,
                getattr(stored_task, "func_name", "") or ""
            )
            if not entry:
                continue

            # 恢复 func 和回调
            stored_task.func = entry.get("func")
            stored_task.callback = entry.get("callback")
            stored_task.stop_callback = entry.get("stop_callback")
            stored_task.status_callback = entry.get("status_callback")

            # 新的运行会话，重启计数清零
            stored_task.restart_count = 0

            with self._task_lock:
                if self._is_shutdown:
                    break
                self._running_long_running_tasks[stored_task.task_id] = stored_task
                future = self._executor.submit(self._execute_long_running_task, stored_task)
                self._futures[stored_task.task_id] = future

            # 调用恢复回调
            restore_callback = entry.get("restore_callback") or factory.get("restore_callback")
            if restore_callback:
                try:
                    restore_callback(stored_task.task_id, stored_task)
                except Exception as e:
                    self._logger.error(get_name(), f'Error calling restore_callback: {e}')

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

            # 取消待重启定时器
            timer = self._restart_timers.pop(task_id, None)
            if timer:
                timer.cancel()

            # 调用停止回调
            if task.stop_callback:
                try:
                    task.stop_callback()
                except Exception as e:
                    self._logger.error(get_name(), f'Error calling stop_callback for task {task_id}: {e}')

            # 取消 future（对运行中任务无效，仅取消排队任务）
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
        """
        执行长期任务（单次执行）

        失败后的自动重启由定时器调度（指数退避），不会在
        线程池 worker 中睡眠等待，避免占满线程池。
        """
        task.last_started_at = datetime.now()
        task.error = None
        task.current_status = LONG_TASK_STATUS_RUNNING
        self._storage.save_long_running_task(task)

        try:
            if task.args or task.kwargs:
                result = task.func(*task.args, **task.kwargs)
            else:
                result = task.func()

        except Exception as e:
            self._handle_long_running_failure(task, e)
            return

        # 函数返回了（正常情况下长期任务不会返回），任务完成
        task.current_status = LONG_TASK_STATUS_COMPLETED
        self._storage.save_long_running_task(task)

        self._invoke_long_running_callback(task, TaskStatus.COMPLETED, result, None)

        # 任务完成后删除存储中的记录，并移出运行时表
        self._storage.delete_long_running_task(task.task_id)
        with self._task_lock:
            self._running_long_running_tasks.pop(task.task_id, None)
            self._futures.pop(task.task_id, None)

    def _handle_long_running_failure(self, task: LongRunningTask, error: Exception) -> None:
        """
        处理长期任务失败

        - 回调异常只记 warning，不影响任务状态机；
        - auto_restart 时按指数退避重启（初始 AUTO_RESTART_INITIAL_DELAY 秒，
          翻倍至 AUTO_RESTART_MAX_DELAY 秒上限）；
        - 超过 MAX_AUTO_RESTARTS 次后标记失败、停止重启并记 error；
        - 重启等待由 threading.Timer 调度，不占线程池 worker。
        """
        task.error = str(error)
        task.current_status = LONG_TASK_STATUS_FAILED

        self._invoke_long_running_callback(task, TaskStatus.FAILED, None, str(error))

        if not task.auto_restart:
            self._storage.save_long_running_task(task)
            # 任务失败且不自动重启时，删除存储中的记录
            self._storage.delete_long_running_task(task.task_id)
            with self._task_lock:
                self._running_long_running_tasks.pop(task.task_id, None)
                self._futures.pop(task.task_id, None)
            return

        if task.restart_count >= self.MAX_AUTO_RESTARTS:
            # 超过最大重启次数：标记失败、停止重启，保留记录以便排查
            task.current_status = LONG_TASK_STATUS_FAILED
            self._storage.save_long_running_task(task)
            self._logger.error(
                get_name(),
                f'Long-running task {task.task_id} ({task.name}) exceeded max auto-restarts ({self.MAX_AUTO_RESTARTS}), giving up'
            )
            with self._task_lock:
                self._running_long_running_tasks.pop(task.task_id, None)
                self._futures.pop(task.task_id, None)
            return

        # 自动重启：指数退避
        task.restart_count += 1
        task.current_status = LONG_TASK_STATUS_RESTARTING
        delay = min(
            self.AUTO_RESTART_INITIAL_DELAY * (2 ** (task.restart_count - 1)),
            self.AUTO_RESTART_MAX_DELAY
        )
        self._storage.save_long_running_task(task)

        # 用定时器延迟重启，避免占住线程池 worker 睡眠
        timer = threading.Timer(delay, self._restart_long_running_task, args=(task,))
        timer.daemon = True
        with self._task_lock:
            self._restart_timers[task.task_id] = timer
        timer.start()

    def _restart_long_running_task(self, task: LongRunningTask) -> None:
        """定时器触发：把长期任务重新提交到线程池"""
        with self._task_lock:
            self._restart_timers.pop(task.task_id, None)

            if self._is_shutdown:
                return

            # 已被停止（用户主动停止或 shutdown）
            if task.task_id not in self._running_long_running_tasks:
                return

            try:
                future = self._executor.submit(self._execute_long_running_task, task)
            except RuntimeError:
                # 线程池已关闭
                return
            self._futures[task.task_id] = future

    def _invoke_long_running_callback(
        self,
        task: LongRunningTask,
        status: TaskStatus,
        result: Any,
        error: Optional[str]
    ) -> None:
        """
        安全调用长期任务回调

        回调异常仅记 warning，不影响任务状态机（避免回调异常被当作
        任务失败而触发无限自动重启）。
        """
        if not task.callback:
            return

        try:
            task.callback(task.task_id, status, result, error)
        except Exception as e:
            self._logger.warning(get_name(), f'Callback of long-running task {task.task_id} raised: {e}')

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
                    self._logger.error(get_name(), f'Error calling status_callback for task {task_id}: {e}')

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

    def is_long_task_running(self, task_id: str) -> bool:
        """判断长期任务当前是否在运行时表中（真正在执行/等待重启）。

        ``current_status`` 字段同时承载生命周期状态与插件自由文本
        （``update_long_running_task_status`` 的语义即为状态描述），
        不能作为「是否在运行」的判定依据；运行时表才是唯一可靠来源。

        Args:
            task_id: 任务 ID

        Returns:
            任务在运行时表中返回 True，否则 False
        """
        with self._task_lock:
            return task_id in self._running_long_running_tasks

    # ==================== 任务查询 ====================

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """获取指定任务（优先查运行时列表，再查持久化存储）

        Args:
            task_id: 任务 ID

        Returns:
            任务对象，不存在时返回 None
        """
        with self._task_lock:
            if task_id in self._running_tasks:
                return self._running_tasks[task_id]

        return self._storage.get_task(task_id)

    def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]:
        """获取指定插件的所有任务（不包括长期任务）

        Args:
            plugin_id: 插件 UUID

        Returns:
            该插件的任务列表
        """
        return self._storage.get_tasks_by_plugin(plugin_id)

    def get_all_tasks(self) -> List[BackgroundTask]:
        """获取所有任务（不包括长期任务）

        Returns:
            运行时任务与持久化任务合并去重后的任务列表
        """
        with self._task_lock:
            running_tasks = list(self._running_tasks.values())

        stored_tasks = self._storage.get_all_tasks()

        all_tasks = {}
        for task in running_tasks + stored_tasks:
            all_tasks[task.task_id] = task

        return list(all_tasks.values())

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态枚举，任务不存在时返回 None
        """
        task = self.get_task(task_id)
        return task.status if task else None

    def get_scheduled_tasks(self, plugin_id: Optional[str] = None) -> List[ScheduledTask]:
        """获取定时任务列表

        Args:
            plugin_id: 可选的插件 UUID，为 None 时返回全部定时任务

        Returns:
            定时任务列表
        """
        if plugin_id:
            return self._storage.get_scheduled_tasks_by_plugin(plugin_id)
        return self._storage.get_all_scheduled_tasks()

    # ==================== 任务控制 ====================

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        对已运行的任务 future.cancel() 无效，但会标记 CANCELLED 并落盘；
        工作线程执行完毕落盘前会检查该状态，不会用完成/失败覆盖取消状态。

        Returns:
            是否成功取消（任务不在运行列表中时返回 False）
        """
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
        """清理已完成/失败/已取消的任务记录

        Args:
            plugin_id: 可选，指定插件的任务才清理；为 None 时清理全部

        Returns:
            清理的任务数量
        """
        return self._storage.clear_completed_tasks(plugin_id)

    def cleanup_old_tasks(self, max_age_days: int = TASK_RECORD_MAX_AGE_DAYS) -> int:
        """
        清理过期的任务记录

        清理已完成/失败/已取消超过 max_age_days 天的后台任务记录。

        Args:
            max_age_days: 记录保留天数，默认 30 天

        Returns:
            清理的记录数量
        """
        return self._storage.cleanup_old_tasks(max_age_days)

    # ==================== 生命周期管理 ====================

    def shutdown(self) -> None:
        """
        关闭任务管理器（限时优雅停止，保证在有限时间内返回）

        流程：
        1. 设置关闭标志，拒绝新任务提交；
        2. 停止定时任务检查线程，取消所有待重启定时器；
        3. 调用各长期任务的 stop_callback，并限时（每任务 LONG_TASK_STOP_TIMEOUT 秒）
           等待其退出；运行中的长期任务标记为 stopped 并保留存储记录
           （重启后不自动恢复，仅"崩溃中断"的任务会在下次启动时恢复）；
        4. 关闭线程池：cancel_futures 取消排队任务，并在独立线程中等待
           运行中任务结束，总上限 EXECUTOR_SHUTDOWN_TIMEOUT 秒，
           超时放弃等待并记 warning（不响应 stop 的任务不会卡死应用退出）。
        """
        with self._task_lock:
            if self._is_shutdown:
                return
            # 设置关闭标志，防止新任务提交
            self._is_shutdown = True

        # 停止定时任务检查线程
        self._stop_event.set()
        check_thread = getattr(self, '_schedule_check_thread', None)
        if check_thread is not None and check_thread.is_alive():
            check_thread.join(timeout=self.CHECK_THREAD_JOIN_TIMEOUT)

        # 取消所有待重启定时器
        with self._task_lock:
            timers = list(self._restart_timers.values())
            self._restart_timers.clear()
        for timer in timers:
            timer.cancel()

        # 停止所有长期任务：先统一调用 stop_callback（让任务尽快收到停止信号）
        with self._task_lock:
            long_tasks = list(self._running_long_running_tasks.items())

        for task_id, task in long_tasks:
            if task.stop_callback:
                try:
                    task.stop_callback()
                except Exception as e:
                    self._logger.error(get_name(), f'Error calling stop_callback for task {task_id}: {e}')

        # 再逐个限时等待退出，并标记为"已停止"（正常退出语义，保留存储记录）
        for task_id, task in long_tasks:
            future = self._futures.get(task_id)
            if future is not None and not future.done():
                try:
                    future.result(timeout=self.LONG_TASK_STOP_TIMEOUT)
                except Exception:
                    # 超时/已取消/执行异常：任务不响应停止，放弃等待
                    self._logger.warning(
                        get_name(),
                        f'Long-running task {task_id} did not stop within {self.LONG_TASK_STOP_TIMEOUT}s, giving up'
                    )
                    future.cancel()

            task.current_status = LONG_TASK_STATUS_STOPPED
            task.last_stopped_at = datetime.now()
            try:
                self._storage.save_long_running_task(task)
            except Exception as e:
                self._logger.warning(get_name(), f'Failed to persist stopped state for task {task_id}: {e}')

        # 清理运行时表
        with self._task_lock:
            self._running_long_running_tasks.clear()
            self._running_tasks.clear()
            self._futures.clear()

        # 停止调度器
        self._scheduler.stop()

        # 关闭线程池：取消排队任务，并在独立线程中限时等待运行中任务结束
        def _wait_executor() -> None:
            self._executor.shutdown(wait=True, cancel_futures=True)

        waiter = Thread(target=_wait_executor, daemon=True, name="BackgroundTaskExecutorShutdown")
        waiter.start()
        waiter.join(timeout=self.EXECUTOR_SHUTDOWN_TIMEOUT)
        if waiter.is_alive():
            self._logger.warning(
                get_name(),
                f'Thread pool did not finish within {self.EXECUTOR_SHUTDOWN_TIMEOUT}s, giving up waiting'
            )

        BackgroundTaskManager._instance = None

    def __del__(self):
        """析构函数"""
        try:
            scheduler = getattr(self, '_scheduler', None)
            if scheduler is not None:
                scheduler.stop()
        except Exception as e:
            # 豁免说明：析构期间解释器可能已拆除日志设施，日志调用本身也可能失败，
            # 因此日志写入需再套一层防护，实在无法记录时只能放弃
            try:
                self._logger.debug(get_name(), f'析构时停止调度器出错（已忽略）: {e}')
            except Exception:
                pass
