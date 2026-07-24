"""
任务持久化存储

负责后台任务和定时任务数据的持久化存储。
"""

import copy
import os
import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from .task_model import BackgroundTask, ScheduledTask, LongRunningTask, TaskStatus

from utils.logging_tools import LoggerManager, get_name


class TaskStorage:
    """
    任务存储类

    负责从磁盘读写任务数据，采用单例模式确保全局唯一实例。
    """

    _instance: Optional['TaskStorage'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式实现"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, data_dir: Optional[str] = None):
        """
        初始化任务存储

        Args:
            data_dir: 数据文件存储目录，默认为项目根目录下的 data 文件夹
        """
        # 避免重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        # 设置数据文件路径
        if data_dir is None:
            self.data_dir = Path(__file__).parent.parent.parent / "data"
        else:
            self.data_dir = Path(data_dir)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_file = self.data_dir / "tasks.json"

        # 线程安全锁
        self._file_lock = threading.RLock()

        # 日志管理器
        self._logger = LoggerManager()

        # 内存缓存
        self._cache: Optional[Dict[str, Any]] = None
        self._cache_dirty = True

        # 是否成功读取过磁盘数据（防护：读损后不允许直接拿空数据覆盖有效文件）
        self._read_ok = True

        # 标记初始化完成
        self._initialized = True

        # 确保数据文件存在
        self._ensure_data_file()

    def _ensure_data_file(self) -> None:
        """确保数据文件存在"""
        if not self.tasks_file.exists():
            default_data = {
                "tasks": {},
                "scheduled_tasks": {},
                "long_running_tasks": {}
            }
            self._write_to_disk(default_data)

    def _read_from_disk(self) -> Dict[str, Any]:
        """
        从磁盘读取数据

        读取失败（如 JSON 损坏）时先将损坏文件备份为 tasks.json.corrupt.bak
        （数据可追查），再返回空数据启动；同时清除 _read_ok 标志，
        防止后续 save 在未重读的情况下用空数据覆盖磁盘。

        Returns:
            数据字典
        """
        with self._file_lock:
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._read_ok = True
                return data
            except FileNotFoundError:
                # 文件不存在不算损坏（后续 save 会重新创建）
                return {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}
            except json.JSONDecodeError as e:
                self._logger.warning(get_name(), f'JSON 解析失败, 返回默认数据: {e}')
                self._backup_corrupt_file()
                self._read_ok = False
                return {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}
            except Exception as e:
                self._logger.warning(get_name(), f'读取任务数据失败: {e}')
                self._backup_corrupt_file()
                self._read_ok = False
                return {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}

    def _backup_corrupt_file(self) -> None:
        """把无法解析的数据文件备份为 tasks.json.corrupt.bak（覆盖旧备份）"""
        try:
            if self.tasks_file.exists():
                backup_file = self.tasks_file.with_suffix('.json.corrupt.bak')
                os.replace(self.tasks_file, backup_file)
                self._logger.warning(get_name(), f'损坏的任务数据已备份到: {backup_file}')
        except Exception as e:
            self._logger.warning(get_name(), f'备份损坏任务数据失败: {e}')

    def _write_to_disk(self, data: Dict[str, Any]) -> None:
        """
        原子写入数据到磁盘

        失败语义：写入失败时记录 error 日志、设置 _cache_dirty=True 以便后续
        save 重试，但不抛出异常（避免影响任务主流程）。调用方不应把本方法的
        正常返回视为“数据已落盘”的强保证。

        Args:
            data: 要写入的数据字典
        """
        with self._file_lock:
            temp_file = self.tasks_file.with_suffix('.json.tmp')
            try:
                # 写入临时文件
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                # 原子重命名
                os.replace(temp_file, self.tasks_file)

                # 写盘成功后文件内容与本缓存一致，解除读损防护标志
                self._read_ok = True

            except Exception as e:
                self._logger.error(get_name(), f'写入任务数据失败: {e}')
                # 标记缓存为脏，后续 save 操作会基于磁盘状态重试
                self._cache_dirty = True
                # 尝试删除临时文件
                if temp_file.exists():
                    temp_file.unlink()

    def load_data(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        从磁盘加载数据到缓存

        Args:
            force_reload: 是否强制重新加载

        Returns:
            数据字典
        """
        # 缓存命中判断与 deepcopy 都在锁内完成，避免并发写入修改嵌套结构时
        # deepcopy 抛出 RuntimeError（与 DataProvider.load_data 同款防护）
        with self._file_lock:
            if self._cache is None or force_reload or self._cache_dirty:
                self._cache = self._read_from_disk()
                self._cache_dirty = False
            if self._cache:
                return copy.deepcopy(self._cache)
            return {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}

    def save_data(self) -> None:
        """
        将当前缓存数据保存到磁盘

        防护：若磁盘文件存在但从未成功解析（_read_ok=False，如启动时读损），
        先尝试重读一次并与内存缓存合并，避免直接用空数据覆盖有效数据。
        """
        if self._cache is None:
            self._cache = {"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}

        if not self._read_ok and self.tasks_file.exists():
            data = self._read_from_disk()
            if self._read_ok:
                # 重读成功：以磁盘数据为基础，叠加内存中的新记录
                for section in ("tasks", "scheduled_tasks", "long_running_tasks"):
                    merged = data.get(section, {})
                    merged.update(self._cache.get(section, {}))
                    self._cache[section] = merged

        self._write_to_disk(self._cache)
        self._cache_dirty = False

    # ==================== 任务操作 ====================

    def save_task(self, task: BackgroundTask) -> None:
        """
        保存任务到存储

        Args:
            task: 背景任务对象
        """
        data = self.load_data()
        data["tasks"][task.task_id] = task.to_dict()
        self._cache = data
        self.save_data()

    def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """
        获取指定任务

        Args:
            task_id: 任务 ID

        Returns:
            任务对象，如果不存在则返回 None
        """
        data = self.load_data()
        task_data = data.get("tasks", {}).get(task_id)
        if task_data:
            return BackgroundTask.from_dict(task_data)
        return None

    def get_all_tasks(self) -> List[BackgroundTask]:
        """
        获取所有任务

        Returns:
            任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("tasks", {}).values():
            tasks.append(BackgroundTask.from_dict(task_data))
        return tasks

    def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]:
        """
        获取指定插件的所有任务

        Args:
            plugin_id: 插件 ID

        Returns:
            任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("tasks", {}).values():
            if task_data.get("plugin_id") == plugin_id:
                tasks.append(BackgroundTask.from_dict(task_data))
        return tasks

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功删除
        """
        data = self.load_data()
        if task_id in data.get("tasks", {}):
            del data["tasks"][task_id]
            self._cache = data
            self.save_data()
            return True
        return False

    def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int:
        """
        清理已完成的任务

        Args:
            plugin_id: 可选，指定插件的任务才清理

        Returns:
            清理的任务数量
        """
        data = self.load_data()
        tasks_to_delete = []

        for task_id, task_data in data.get("tasks", {}).items():
            # 检查状态是否为已完成/失败/已取消
            status = task_data.get("status")
            if status in (TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value):
                # 如果指定了 plugin_id，则只清理该插件的任务
                if plugin_id is None or task_data.get("plugin_id") == plugin_id:
                    tasks_to_delete.append(task_id)

        for task_id in tasks_to_delete:
            del data["tasks"][task_id]

        self._cache = data
        self.save_data()
        return len(tasks_to_delete)

    # ==================== 定时任务操作 ====================

    def save_scheduled_task(self, task: ScheduledTask) -> None:
        """
        保存定时任务

        Args:
            task: 定时任务对象
        """
        data = self.load_data()
        data["scheduled_tasks"][task.task_id] = task.to_dict()
        self._cache = data
        self.save_data()

    def get_scheduled_task(self, task_id: str) -> Optional[ScheduledTask]:
        """
        获取指定定时任务

        Args:
            task_id: 任务 ID

        Returns:
            定时任务对象，如果不存在则返回 None
        """
        data = self.load_data()
        task_data = data.get("scheduled_tasks", {}).get(task_id)
        if task_data:
            return ScheduledTask.from_dict(task_data)
        return None

    def get_all_scheduled_tasks(self) -> List[ScheduledTask]:
        """
        获取所有定时任务

        Returns:
            定时任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("scheduled_tasks", {}).values():
            tasks.append(ScheduledTask.from_dict(task_data))
        return tasks

    def get_scheduled_tasks_by_plugin(self, plugin_id: str) -> List[ScheduledTask]:
        """
        获取指定插件的定时任务

        Args:
            plugin_id: 插件 ID

        Returns:
            定时任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("scheduled_tasks", {}).values():
            if task_data.get("plugin_id") == plugin_id:
                tasks.append(ScheduledTask.from_dict(task_data))
        return tasks

    def delete_scheduled_task(self, task_id: str) -> bool:
        """
        删除定时任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功删除
        """
        data = self.load_data()
        if task_id in data.get("scheduled_tasks", {}):
            del data["scheduled_tasks"][task_id]
            self._cache = data
            self.save_data()
            return True
        return False

    def update_scheduled_task(self, task: ScheduledTask) -> None:
        """
        更新定时任务

        Args:
            task: 定时任务对象
        """
        self.save_scheduled_task(task)

    # ==================== 长期任务操作 ====================

    def save_long_running_task(self, task: LongRunningTask) -> None:
        """
        保存长期任务

        Args:
            task: 长期任务对象
        """
        data = self.load_data()
        if "long_running_tasks" not in data:
            data["long_running_tasks"] = {}
        data["long_running_tasks"][task.task_id] = task.to_dict()
        self._cache = data
        self.save_data()

    def get_long_running_task(self, task_id: str) -> Optional[LongRunningTask]:
        """
        获取指定长期任务

        Args:
            task_id: 任务 ID

        Returns:
            长期任务对象，如果不存在则返回 None
        """
        data = self.load_data()
        task_data = data.get("long_running_tasks", {}).get(task_id)
        if task_data:
            return LongRunningTask.from_dict(task_data)
        return None

    def get_all_long_running_tasks(self) -> List[LongRunningTask]:
        """
        获取所有长期任务

        Returns:
            长期任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("long_running_tasks", {}).values():
            tasks.append(LongRunningTask.from_dict(task_data))
        return tasks

    def get_long_running_tasks_by_plugin(self, plugin_id: str) -> List[LongRunningTask]:
        """
        获取指定插件的长期任务

        Args:
            plugin_id: 插件 ID

        Returns:
            长期任务列表
        """
        data = self.load_data()
        tasks = []
        for task_data in data.get("long_running_tasks", {}).values():
            if task_data.get("plugin_id") == plugin_id:
                tasks.append(LongRunningTask.from_dict(task_data))
        return tasks

    def delete_long_running_task(self, task_id: str) -> bool:
        """
        删除长期任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功删除
        """
        data = self.load_data()
        if task_id in data.get("long_running_tasks", {}):
            del data["long_running_tasks"][task_id]
            self._cache = data
            self.save_data()
            return True
        self._logger.debug(get_name(), f'Task not found: {task_id}')
        return False

    def update_long_running_task(self, task: LongRunningTask) -> None:
        """
        更新长期任务

        Args:
            task: 长期任务对象
        """
        self.save_long_running_task(task)

    def cleanup_old_tasks(self, max_age_days: int = 30) -> int:
        """
        清理过期的任务记录

        清理已完成/失败/已取消且完成时间（无完成时间则按创建时间）超过
        max_age_days 天的后台任务记录；定时任务与长期任务记录不在清理范围。

        Args:
            max_age_days: 记录保留天数，默认 30 天

        Returns:
            清理的记录数量
        """
        cutoff = datetime.now() - timedelta(days=max_age_days)
        data = self.load_data()
        tasks_to_delete = []

        for task_id, task_data in data.get("tasks", {}).items():
            if task_data.get("status") not in (
                TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value
            ):
                continue

            timestamp = task_data.get("finished_at") or task_data.get("created_at")
            if not timestamp:
                continue

            try:
                finished_at = datetime.fromisoformat(timestamp)
            except (ValueError, TypeError):
                continue

            if finished_at < cutoff:
                tasks_to_delete.append(task_id)

        for task_id in tasks_to_delete:
            del data["tasks"][task_id]

        if tasks_to_delete:
            self._cache = data
            self.save_data()
            self._logger.info(get_name(), f'清理了 {len(tasks_to_delete)} 条过期任务记录')

        return len(tasks_to_delete)

    def clear_cache(self) -> None:
        """清除缓存"""
        with self._file_lock:
            self._cache = None
            self._cache_dirty = True
