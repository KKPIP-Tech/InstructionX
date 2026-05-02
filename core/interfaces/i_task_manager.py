"""
TaskManager 任务管理器接口

定义后台任务调度、异步/同步任务执行、回调机制和定时任务管理的抽象接口。
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Callable, Any


class TaskType(Enum):
    """任务类型枚举"""
    SYNC = "sync"
    ASYNC = "async"
    SCHEDULED = "scheduled"
    LONG_RUNNING = "long_running"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


class ITaskManager(ABC):
    """
    任务管理器接口

    定义后台任务和定时任务管理的抽象接口。
    插件通过此接口访问任务调度能力，而非直接依赖 BackgroundTaskManager 实现。
    """

    # ==================== 同步/异步任务 ====================

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def register_scheduled_task_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable] = None
    ) -> None:
        """注册定时任务工厂函数（用于应用重启后恢复任务）"""
        pass

    @abstractmethod
    def restore_scheduled_tasks(self, plugin_id: str) -> int:
        """恢复指定插件的定时任务"""
        pass

    @abstractmethod
    def unregister_scheduled_task(self, task_id: str) -> bool:
        """注销定时任务"""
        pass

    @abstractmethod
    def enable_scheduled_task(self, task_id: str) -> bool:
        """启用定时任务"""
        pass

    @abstractmethod
    def disable_scheduled_task(self, task_id: str) -> bool:
        """禁用定时任务"""
        pass

    # ==================== 长期任务 ====================

    @abstractmethod
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
        """注册长期任务"""
        pass

    @abstractmethod
    def register_long_running_task_factory(
        self,
        plugin_id: str,
        func: Callable,
        callback: Optional[Callable] = None,
        stop_callback: Optional[Callable] = None,
        status_callback: Optional[Callable] = None,
        restore_callback: Optional[Callable] = None
    ) -> None:
        """注册长期任务工厂函数"""
        pass

    @abstractmethod
    def restore_long_running_tasks(self, plugin_id: str) -> int:
        """恢复指定插件的长期任务"""
        pass

    @abstractmethod
    def stop_long_running_task(self, task_id: str, delete_from_storage: bool = True) -> bool:
        """停止长期任务"""
        pass

    @abstractmethod
    def get_long_running_tasks(self, plugin_id: Optional[str] = None) -> List[Any]:
        """获取长期任务列表"""
        pass

    @abstractmethod
    def update_long_running_task_status(self, task_id: str, status: str) -> bool:
        """更新长期任务的状态"""
        pass

    # ==================== 任务查询 ====================

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[Any]:
        """获取指定任务"""
        pass

    @abstractmethod
    def get_tasks_by_plugin(self, plugin_id: str) -> List[Any]:
        """获取指定插件的所有任务"""
        pass

    @abstractmethod
    def get_all_tasks(self) -> List[Any]:
        """获取所有任务"""
        pass

    @abstractmethod
    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """获取任务状态"""
        pass

    @abstractmethod
    def get_scheduled_tasks(self, plugin_id: Optional[str] = None) -> List[Any]:
        """获取定时任务列表"""
        pass

    # ==================== 任务控制 ====================

    @abstractmethod
    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        pass

    @abstractmethod
    def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int:
        """清理已完成的任务"""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """关闭任务管理器，释放所有资源"""
        pass
