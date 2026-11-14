"""协作式任务取消契约，区分取消请求与实际停止。"""

import threading
from dataclasses import dataclass
from typing import Optional

from core.interfaces.i_task_manager import TaskStatus


class TaskCancelled(Exception):
    """任务函数通过取消令牌主动确认停止时抛出。"""


class CancellationToken:
    """线程安全的协作取消令牌，由任务函数主动检查。"""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        """发出取消请求，不代表任务函数已经停止。"""
        self._event.set()

    @property
    def is_cancelled(self) -> bool:
        """返回是否已收到取消请求。"""
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        """收到请求时抛出 TaskCancelled，由任务管理器确认最终状态。"""
        if self.is_cancelled:
            raise TaskCancelled("任务已响应取消请求")


@dataclass(frozen=True, slots=True)
class CancellationResult:
    """取消请求处理结果，status 反映任务当前真实生命周期。"""

    task_id: str
    accepted: bool
    status: Optional[TaskStatus]
    message: str = ""


class ScheduledOverlapPolicy:
    """定时任务重入策略，避免慢任务形成无界积压。"""

    SKIP = "skip"
    QUEUE_ONE = "queue_one"
    COALESCE = "coalesce"
    ALL = frozenset((SKIP, QUEUE_ONE, COALESCE))


class TaskPriority:
    """短任务优先级，HIGH 使用独立执行池。"""

    HIGH = "high"
    NORMAL = "normal"


@dataclass(frozen=True, slots=True)
class QueueFullError(Exception):
    """有界队列已满的结构化异常，包含拒绝原因。"""

    pool: str
    capacity: int
    message: Optional[str] = None

    def __str__(self) -> str:
        return self.message or f"任务队列 {self.pool} 已满（容量 {self.capacity}），拒绝新任务"
