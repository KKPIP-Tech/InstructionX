"""
后台任务演示器服务层

提供可以被其他插件调用的 API。
"""

import time
from typing import Dict, List, Any, Optional

from core.task import BackgroundTaskManager, TaskStatus


class Service:
    """后台任务演示器服务"""

    def __init__(self):
        self._task_manager = BackgroundTaskManager()

    def get_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有后台任务

        Returns:
            任务列表
        """
        tasks = self._task_manager.get_all_tasks()
        return [task.to_dict() for task in tasks]

    def get_tasks_by_plugin(self, plugin_id: str) -> List[Dict[str, Any]]:
        """
        按插件 UUID 获取任务

        Args:
            plugin_id: 插件 UUID

        Returns:
            任务列表
        """
        tasks = self._task_manager.get_tasks_by_plugin(plugin_id)
        return [task.to_dict() for task in tasks]

    def get_scheduled_tasks(self, plugin_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取定时任务

        Args:
            plugin_id: 可选，按插件 UUID 过滤

        Returns:
            定时任务列表
        """
        tasks = self._task_manager.get_scheduled_tasks(plugin_id)
        return [task.to_dict() for task in tasks]

    def get_task_status(self, task_id: str) -> Optional[str]:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务状态字符串
        """
        status = self._task_manager.get_task_status(task_id)
        return status.value if status else None

    def create_sync_task(
        self,
        plugin_id: str,
        name: str,
        duration: int = 1
    ) -> str:
        """
        创建同步任务

        Args:
            plugin_id: 插件 UUID
            name: 任务名称
            duration: 执行时长（秒）

        Returns:
            任务 ID
        """

        def sync_task():
            time.sleep(duration)
            return f"同步任务 {name} 完成"

        return self._task_manager.register_sync_task(
            plugin_id=plugin_id,
            name=name,
            func=sync_task
        )

    def create_async_task(
        self,
        plugin_id: str,
        name: str,
        duration: int = 1,
        callback: Optional[callable] = None
    ) -> str:
        """
        创建异步任务

        Args:
            plugin_id: 插件 UUID
            name: 任务名称
            duration: 执行时长（秒）
            callback: 回调函数

        Returns:
            任务 ID
        """

        def async_task():
            time.sleep(duration)
            return f"异步任务 {name} 完成"

        return self._task_manager.register_async_task(
            plugin_id=plugin_id,
            name=name,
            func=async_task,
            callback=callback
        )

    def create_scheduled_task(
        self,
        plugin_id: str,
        name: str,
        interval: int,
        duration: int = 1
    ) -> str:
        """
        创建定时任务

        Args:
            plugin_id: 插件 UUID
            name: 任务名称
            interval: 执行间隔（秒）
            duration: 每次执行时长（秒）

        Returns:
            任务 ID
        """

        def scheduled_task():
            time.sleep(duration)
            return f"定时任务 {name} 执行"

        return self._task_manager.register_scheduled_task(
            plugin_id=plugin_id,
            name=name,
            func=scheduled_task,
            interval=interval
        )

    def cancel_task(self, task_id: str) -> bool:
        """
        取消任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功取消
        """
        return self._task_manager.cancel_task(task_id)

    def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int:
        """
        清理已完成的任务

        Args:
            plugin_id: 可选，按插件 UUID 过滤

        Returns:
            清理的任务数量
        """
        return self._task_manager.clear_completed_tasks(plugin_id)

    def enable_scheduled_task(self, task_id: str) -> bool:
        """启用定时任务"""
        return self._task_manager.enable_scheduled_task(task_id)

    def disable_scheduled_task(self, task_id: str) -> bool:
        """禁用定时任务"""
        return self._task_manager.disable_scheduled_task(task_id)
