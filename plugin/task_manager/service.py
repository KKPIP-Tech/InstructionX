"""
任务管理器服务
"""

import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from core.data.data_provider import DataProvider, DataProviderError, DataNamespace


class TaskService:
    """任务管理服务"""
    
    def __init__(self, plugin_id: str):
        """
        初始化任务服务
        
        Args:
            plugin_id: 插件ID
        """
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
    
    def add_task(self, title: str, description: str = "", priority: str = "normal") -> Dict[str, Any]:
        """
        添加新任务
        
        Args:
            title: 任务标题
            description: 任务描述
            priority: 优先级 (low, normal, high)
            
        Returns:
            任务信息字典
        """
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        task = {
            "id": task_id,
            "title": title,
            "description": description,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # 获取现有任务列表
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id, 
            "tasks", 
            DataNamespace.PRIVATE, 
            []
        )
        
        tasks.append(task)
        
        # 保存任务列表
        self.data_provider.set_plugin_data(
            self.plugin_id,
            "tasks",
            tasks,
            DataNamespace.PRIVATE
        )
        
        # 更新公共统计信息
        self._update_statistics()
        
        # 发布任务添加事件
        self.data_provider.publish(
            self.plugin_id,
            "last_event",
            {
                "type": "task_added",
                "task_id": task_id,
                "timestamp": datetime.now().isoformat()
            },
            DataNamespace.PUBLIC
        )
        
        return task
    
    def update_task_status(self, task_id: str, status: str) -> bool:
        """
        更新任务状态
        
        Args:
            task_id: 任务ID
            status: 新状态 (pending, in_progress, completed, cancelled)
            
        Returns:
            是否成功
        """
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id,
            "tasks",
            DataNamespace.PRIVATE,
            []
        )
        
        for task in tasks:
            if task["id"] == task_id:
                old_status = task["status"]
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                
                # 保存更新
                self.data_provider.set_plugin_data(
                    self.plugin_id,
                    "tasks",
                    tasks,
                    DataNamespace.PRIVATE
                )
                
                # 更新统计信息
                self._update_statistics()
                
                # 发布状态变更事件
                self.data_provider.publish(
                    self.plugin_id,
                    "last_event",
                    {
                        "type": "status_changed",
                        "task_id": task_id,
                        "old_status": old_status,
                        "new_status": status,
                        "timestamp": datetime.now().isoformat()
                    },
                    DataNamespace.PUBLIC
                )
                
                return True
        
        return False
    
    def get_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取任务列表
        
        Args:
            status: 可选，筛选特定状态的任务
            
        Returns:
            任务列表
        """
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id,
            "tasks",
            DataNamespace.PRIVATE,
            []
        )
        
        if status:
            return [task for task in tasks if task["status"] == status]
        
        return tasks
    
    def delete_task(self, task_id: str) -> bool:
        """
        删除任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功
        """
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id,
            "tasks",
            DataNamespace.PRIVATE,
            []
        )
        
        original_count = len(tasks)
        tasks = [task for task in tasks if task["id"] != task_id]
        
        if len(tasks) < original_count:
            # 保存更新
            self.data_provider.set_plugin_data(
                self.plugin_id,
                "tasks",
                tasks,
                DataNamespace.PRIVATE
            )
            
            # 更新统计信息
            self._update_statistics()
            
            # 发布删除事件
            self.data_provider.publish(
                self.plugin_id,
                "last_event",
                {
                    "type": "task_deleted",
                    "task_id": task_id,
                    "timestamp": datetime.now().isoformat()
                },
                DataNamespace.PUBLIC
            )
            
            return True
        
        return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取任务统计信息
        
        Returns:
            统计信息字典
        """
        return self.data_provider.get_plugin_data(
            self.plugin_id,
            "statistics",
            DataNamespace.PUBLIC,
            {
                "total": 0,
                "pending": 0,
                "in_progress": 0,
                "completed": 0,
                "cancelled": 0
            }
        )
    
    def _update_statistics(self) -> None:
        """更新任务统计信息"""
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id,
            "tasks",
            DataNamespace.PRIVATE,
            []
        )
        
        stats = {
            "total": len(tasks),
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
            "cancelled": 0
        }
        
        for task in tasks:
            status = task["status"]
            if status in stats:
                stats[status] += 1
        
        # 更新统计信息到公共数据
        self.data_provider.publish(
            self.plugin_id,
            "statistics",
            stats,
            DataNamespace.PUBLIC
        )
    
    def save_task_attachment(self, task_id: str, filename: str, content: bytes) -> str:
        """
        保存任务附件
        
        Args:
            task_id: 任务ID
            filename: 文件名
            content: 文件内容
            
        Returns:
            附件相对路径
        """
        attachment_filename = f"{task_id}_{filename}"
        return self.data_provider.save_asset(
            self.plugin_id,
            attachment_filename,
            content
        )
    
    def export_tasks(self, format: str = "json") -> str:
        """
        导出任务数据
        
        Args:
            format: 导出格式 (json, csv)
            
        Returns:
            导出文件的相对路径
        """
        tasks = self.get_tasks()
        stats = self.get_statistics()
        
        if format == "json":
            export_data = {
                "exported_at": datetime.now().isoformat(),
                "statistics": stats,
                "tasks": tasks
            }
            content = json.dumps(export_data, ensure_ascii=False, indent=2).encode('utf-8')
            filename = f"tasks_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        elif format == "csv":
            import csv
            from io import StringIO
            
            output = StringIO()
            writer = csv.DictWriter(output, fieldnames=['id', 'title', 'description', 'priority', 'status', 'created_at'])
            writer.writeheader()
            writer.writerows(tasks)
            content = output.getvalue().encode('utf-8')
            filename = f"tasks_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        else:
            raise ValueError(f"不支持的导出格式: {format}")
        
        return self.save_task_attachment("export", filename, content)