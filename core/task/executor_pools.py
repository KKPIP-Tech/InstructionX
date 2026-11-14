"""长期、普通和高优先级任务的独立有界执行池。"""

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional

from .cancellation import QueueFullError
from .supervisor import TaskSupervisor


class BoundedExecutor:
    """在线程池外层用信号量限制运行加排队总量，防止无界积压。"""

    def __init__(self, name, workers, capacity, supervisor, executor_factory=ThreadPoolExecutor):
        self.name = name
        self.capacity = capacity
        self._supervisor = supervisor
        self._executor = executor_factory(max_workers=workers, thread_name_prefix=name)
        self._slots = threading.BoundedSemaphore(capacity)

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        """提交任务；队列满时抛出 QueueFullError 并记录拒绝。"""
        if not self._slots.acquire(blocking=False):
            self._supervisor.record_rejected(self.name)
            raise QueueFullError(self.name, self.capacity)
        self._supervisor.record_submit(self.name)
        try:
            future = self._executor.submit(func, *args, **kwargs)
        except Exception:
            self._slots.release()
            self._supervisor.record_completion(self.name)
            raise
        future.add_done_callback(self._release_slot)
        return future

    def _release_slot(self, _future: Future) -> None:
        self._slots.release()
        self._supervisor.record_completion(self.name)

    def shutdown(self, wait: bool = False, cancel_futures: bool = True) -> None:
        """关闭底层线程池，等待策略由统一生命周期决定。"""
        self._executor.shutdown(wait=wait, cancel_futures=cancel_futures)


class ExecutorPools:
    """集中持有三类执行池，避免长期任务饿死普通和高优先级任务。"""

    NORMAL_WORKERS = 4
    HIGH_WORKERS = 2
    LONG_WORKERS = 32
    NORMAL_CAPACITY = 256
    HIGH_CAPACITY = 64
    LONG_CAPACITY = 128

    def __init__(self, supervisor=None, executor_factory=ThreadPoolExecutor):
        self.supervisor = supervisor or TaskSupervisor()
        self._pools: Dict[str, BoundedExecutor] = {
            "normal": BoundedExecutor(
                "normal", self.NORMAL_WORKERS, self.NORMAL_CAPACITY,
                self.supervisor, executor_factory,
            ),
            "high": BoundedExecutor(
                "high", self.HIGH_WORKERS, self.HIGH_CAPACITY,
                self.supervisor, executor_factory,
            ),
            "long": BoundedExecutor(
                "long", self.LONG_WORKERS, self.LONG_CAPACITY,
                self.supervisor, executor_factory,
            ),
        }

    @property
    def normal(self) -> BoundedExecutor:
        return self._pools["normal"]

    @property
    def high(self) -> BoundedExecutor:
        return self._pools["high"]

    @property
    def long(self) -> BoundedExecutor:
        return self._pools["long"]

    def for_priority(self, priority: str) -> BoundedExecutor:
        """按 TaskPriority 值选择短任务执行池。"""
        return self.high if priority == "high" else self.normal

    def shutdown(self, wait: bool = False, cancel_futures: bool = True) -> None:
        """统一关闭全部执行池，任一池失败仍继续关闭其余池。"""
        first_error = None
        unique_pools = {id(pool._executor): pool for pool in self._pools.values()}
        for pool in unique_pools.values():
            try:
                pool.shutdown(wait=wait, cancel_futures=cancel_futures)
            except Exception as exc:
                first_error = first_error or exc
        if first_error is not None:
            raise first_error
