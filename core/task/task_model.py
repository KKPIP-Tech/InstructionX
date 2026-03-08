"""
任务数据模型

定义后台任务和定时任务的数据结构。
"""

import uuid
import threading
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Callable, Dict
from dataclasses import dataclass, field


class TaskType(Enum):
    """任务类型枚举"""
    SYNC = "sync"           # 同步任务
    ASYNC = "async"         # 异步任务
    SCHEDULED = "scheduled" # 定时任务


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"     # 待执行
    RUNNING = "running"    # 执行中
    COMPLETED = "completed" # 已完成
    FAILED = "failed"      # 执行失败
    CANCELLED = "cancelled" # 已取消


@dataclass
class BackgroundTask:
    """
    后台任务数据类

    用于存储和管理单个后台任务的信息。
    注意：func 和 callback 属性不参与序列化。
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    name: str = ""
    task_type: TaskType = TaskType.ASYNC
    status: TaskStatus = TaskStatus.PENDING

    # 运行时属性（不参与序列化）
    func: Optional[Callable] = field(default=None, repr=False)
    callback: Optional[Callable] = field(default=None, repr=False)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    # 结果属性
    result: Any = None
    error: Optional[str] = None

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "task_id": self.task_id,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "task_type": self.task_type.value,
            "status": self.status.value,
            "result": self._serialize_result(self.result),
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BackgroundTask':
        """从字典创建实例（用于反序列化）"""
        task = cls()
        task.task_id = data.get("task_id", task.task_id)
        task.plugin_id = data.get("plugin_id", "")
        task.name = data.get("name", "")
        task.task_type = TaskType(data.get("task_type", "async"))
        task.status = TaskStatus(data.get("status", "pending"))
        task.result = data.get("result")
        task.error = data.get("error")

        # 解析时间戳
        created_at = data.get("created_at")
        if created_at:
            task.created_at = datetime.fromisoformat(created_at)

        started_at = data.get("started_at")
        if started_at:
            task.started_at = datetime.fromisoformat(started_at)

        finished_at = data.get("finished_at")
        if finished_at:
            task.finished_at = datetime.fromisoformat(finished_at)

        return task

    def _serialize_result(self, result: Any) -> Any:
        """序列化结果（处理不可序列化的对象）"""
        try:
            import json
            json.dumps(result)
            return result
        except (TypeError, ValueError):
            # 如果不可序列化，返回字符串描述
            return f"<{type(result).__name__}>"

    def mark_running(self) -> None:
        """标记任务为运行中"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any = None) -> None:
        """标记任务为已完成"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.finished_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """标记任务为失败"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = datetime.now()

    def mark_cancelled(self) -> None:
        """标记任务为已取消"""
        self.status = TaskStatus.CANCELLED
        self.finished_at = datetime.now()


@dataclass
class ScheduledTask:
    """
    定时任务数据类

    用于存储和管理定时任务的信息。
    注意：func 和 callback 属性不参与序列化。
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    name: str = ""
    interval: int = 60  # 间隔（秒）

    # 运行时属性（不参与序列化）
    func: Optional[Callable] = field(default=None, repr=False)
    callback: Optional[Callable] = field(default=None, repr=False)
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    # 控制属性
    enabled: bool = True

    # 时间戳
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "task_id": self.task_id,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "interval": self.interval,
            "enabled": self.enabled,
            "args": list(self.args) if self.args else [],
            "kwargs": dict(self.kwargs) if self.kwargs else {},
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledTask':
        """从字典创建实例（用于反序列化）"""
        task = cls()
        task.task_id = data.get("task_id", task.task_id)
        task.plugin_id = data.get("plugin_id", "")
        task.name = data.get("name", "")
        task.interval = data.get("interval", 60)
        task.enabled = data.get("enabled", True)

        # 解析 args 和 kwargs
        task.args = tuple(data.get("args", []))
        task.kwargs = dict(data.get("kwargs", {}))

        # 解析时间戳
        last_run = data.get("last_run")
        if last_run:
            task.last_run = datetime.fromisoformat(last_run)

        next_run = data.get("next_run")
        if next_run:
            task.next_run = datetime.fromisoformat(next_run)

        created_at = data.get("created_at")
        if created_at:
            task.created_at = datetime.fromisoformat(created_at)

        return task

    def calculate_next_run(self) -> None:
        """计算下次执行时间"""
        from datetime import timedelta
        self.next_run = datetime.now() + timedelta(seconds=self.interval)


class TaskThreadLocal:
    """
    线程本地存储

    用于在子线程中安全地访问当前任务信息。
    """
    _local = threading.local()

    @classmethod
    def set_current_task(cls, task: BackgroundTask) -> None:
        """设置当前任务"""
        cls._local.current_task = task

    @classmethod
    def get_current_task(cls) -> Optional[BackgroundTask]:
        """获取当前任务"""
        return getattr(cls._local, 'current_task', None)

    @classmethod
    def clear_current_task(cls) -> None:
        """清除当前任务"""
        if hasattr(cls._local, 'current_task'):
            delattr(cls._local, 'current_task')
