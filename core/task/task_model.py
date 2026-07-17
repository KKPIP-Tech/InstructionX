"""
任务数据模型定义

定义后台任务、定时任务、长期任务的数据结构和状态枚举。
支持任务序列化/反序列化，用于任务持久化存储。
"""

import uuid
import threading
from datetime import datetime
from typing import Any, Optional, Callable, Dict
from dataclasses import dataclass, field

# TaskType/TaskStatus 单一来源在接口层，此处 re-export 以保持
# `from core.task.task_model import TaskType, TaskStatus` 导入路径可用
from ..interfaces.i_task_manager import TaskType, TaskStatus  # noqa: F401


@dataclass
class BackgroundTask:
    """
    后台任务数据模型

    用于存储和管理一次性执行的后台任务。
    包含任务标识、状态、执行参数和结果信息。

    注意：func 和 callback 属性为运行时对象，不参与持久化序列化。
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
        """
        将任务转换为字典格式

        用于任务持久化存储。自动处理不可序列化的结果对象。

        Returns:
            包含任务信息的字典
        """
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
        """
        从字典数据恢复任务实例

        用于从持久化存储加载任务。

        Args:
            data: 任务字典数据

        Returns:
            重建的 BackgroundTask 实例
        """
        task = cls()
        task.task_id = data.get("task_id", task.task_id)
        task.plugin_id = data.get("plugin_id", "")
        task.name = data.get("name", "")
        task.task_type = TaskType(data.get("task_type", "async"))
        task.status = TaskStatus(data.get("status", "pending"))
        task.result = data.get("result")
        task.error = data.get("error")

        # 解析时间戳字符串为 datetime 对象
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
        """
        序列化任务结果

        尝试将结果转换为 JSON 兼容格式。不可序列化时返回类型描述。

        Args:
            result: 任务执行结果

        Returns:
            可序列化结果或类型描述字符串
        """
        # 注：此处先 json.dumps 探测一次，存储层写盘时会再序列化一次，存在双重
        # 序列化开销。但 to_dict 返回的是供调用方使用的普通 dict，无法把“已序列化
        # 的字符串”安全复用给存储层（会改变 result 在 JSON 中的结构），故保留现状。
        try:
            import json
            json.dumps(result)
            return result
        except (TypeError, ValueError):
            # 不可序列化对象，返回类型描述
            return f"<{type(result).__name__}>"

    def mark_running(self) -> None:
        """标记任务为运行中状态，并记录开始时间"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()

    def mark_completed(self, result: Any = None) -> None:
        """标记任务为已完成状态，记录结果和完成时间"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.finished_at = datetime.now()

    def mark_failed(self, error: str) -> None:
        """标记任务为失败状态，记录错误信息和失败时间"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.finished_at = datetime.now()

    def mark_cancelled(self) -> None:
        """标记任务为已取消状态，记录取消时间"""
        self.status = TaskStatus.CANCELLED
        self.finished_at = datetime.now()


@dataclass
class ScheduledTask:
    """
    定时任务数据模型

    用于存储和管理按固定时间间隔重复执行的任务。
    支持任务启用/禁用控制，自动计算下次执行时间。

    注意：func 和 callback 属性为运行时对象，不参与持久化序列化。
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    name: str = ""
    interval: int = 60  # 执行间隔秒数
    func_name: str = ""  # 任务函数标识（func.__qualname__），用于重启后精确匹配工厂函数

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
        """
        将任务转换为字典格式

        用于任务持久化存储。

        Returns:
            包含任务信息的字典
        """
        return {
            "task_id": self.task_id,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "interval": self.interval,
            "func_name": self.func_name,
            "enabled": self.enabled,
            "args": list(self.args) if self.args else [],
            "kwargs": dict(self.kwargs) if self.kwargs else {},
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduledTask':
        """
        从字典数据恢复任务实例

        Args:
            data: 任务字典数据

        Returns:
            重建的 ScheduledTask 实例
        """
        task = cls()
        task.task_id = data.get("task_id", task.task_id)
        task.plugin_id = data.get("plugin_id", "")
        task.name = data.get("name", "")
        task.interval = data.get("interval", 60)
        # 旧版记录没有 func_name 字段，缺省为空串（恢复时回退到插件唯一工厂）
        task.func_name = data.get("func_name", "")
        task.enabled = data.get("enabled", True)

        # 解析参数
        task.args = tuple(data.get("args", []))
        task.kwargs = dict(data.get("kwargs", {}))

        # 解析时间戳字符串为 datetime 对象
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
        """
        计算并设置下次执行时间

        基于当前时间加上间隔秒数计算下一次执行的时间点。
        """
        from datetime import timedelta
        self.next_run = datetime.now() + timedelta(seconds=self.interval)


@dataclass
class LongRunningTask:
    """
    长期任务数据模型

    用于存储和管理持续运行的后台任务。
    任务会持续运行直到被显式停止，支持优雅停止机制和失败自动重启。

    注意：func、callback、stop_callback、status_callback 为运行时对象，不参与持久化。
    """
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    plugin_id: str = ""
    name: str = ""
    enabled: bool = True
    auto_restart: bool = True  # 任务失败后是否自动重启
    func_name: str = ""  # 任务函数标识（func.__qualname__），用于重启后精确匹配工厂函数

    # 运行时属性（不参与序列化）
    func: Optional[Callable] = field(default=None, repr=False)
    callback: Optional[Callable] = field(default=None, repr=False)
    stop_callback: Optional[Callable] = field(default=None, repr=False)  # 优雅停止回调
    status_callback: Optional[Callable] = field(default=None, repr=False)  # 状态更新回调
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)

    # 运行时状态
    current_status: str = ""  # 当前状态描述文字
    error: Optional[str] = None  # 错误信息

    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    last_started_at: Optional[datetime] = None
    last_stopped_at: Optional[datetime] = None
    restart_count: int = 0  # 自动重启次数

    def to_dict(self) -> Dict[str, Any]:
        """
        将任务转换为字典格式

        用于任务持久化存储。

        Returns:
            包含任务信息的字典
        """
        return {
            "task_id": self.task_id,
            "plugin_id": self.plugin_id,
            "name": self.name,
            "enabled": self.enabled,
            "auto_restart": self.auto_restart,
            "func_name": self.func_name,
            "current_status": self.current_status,
            "error": self.error,
            "args": list(self.args) if self.args else [],
            "kwargs": dict(self.kwargs) if self.kwargs else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "last_stopped_at": self.last_stopped_at.isoformat() if self.last_stopped_at else None,
            "restart_count": self.restart_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LongRunningTask':
        """
        从字典数据恢复任务实例

        Args:
            data: 任务字典数据

        Returns:
            重建的 LongRunningTask 实例
        """
        task = cls()
        task.task_id = data.get("task_id", task.task_id)
        task.plugin_id = data.get("plugin_id", "")
        task.name = data.get("name", "")
        task.enabled = data.get("enabled", True)
        task.auto_restart = data.get("auto_restart", True)
        # 旧版记录没有 func_name 字段，缺省为空串（恢复时回退到插件唯一工厂）
        task.func_name = data.get("func_name", "")
        task.current_status = data.get("current_status", "")
        task.error = data.get("error")

        # 解析参数
        task.args = tuple(data.get("args", []))
        task.kwargs = dict(data.get("kwargs", {}))

        # 解析时间戳字符串为 datetime 对象
        created_at = data.get("created_at")
        if created_at:
            task.created_at = datetime.fromisoformat(created_at)

        last_started_at = data.get("last_started_at")
        if last_started_at:
            task.last_started_at = datetime.fromisoformat(last_started_at)

        last_stopped_at = data.get("last_stopped_at")
        if last_stopped_at:
            task.last_stopped_at = datetime.fromisoformat(last_stopped_at)

        task.restart_count = data.get("restart_count", 0)

        return task


class TaskThreadLocal:
    """
    线程本地任务存储

    利用线程本地存储机制，在多线程环境下安全传递当前任务信息。
    用于在任务执行的子线程中获取关联的任务上下文。
    """
    _local = threading.local()

    @classmethod
    def set_current_task(cls, task: BackgroundTask) -> None:
        """设置当前线程的关联任务"""
        cls._local.current_task = task

    @classmethod
    def get_current_task(cls) -> Optional[BackgroundTask]:
        """获取当前线程关联的任务"""
        return getattr(cls._local, 'current_task', None)

    @classmethod
    def clear_current_task(cls) -> None:
        """清除当前线程的任务关联"""
        if hasattr(cls._local, 'current_task'):
            delattr(cls._local, 'current_task')
