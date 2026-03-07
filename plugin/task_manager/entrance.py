"""
任务管理器插件 - 官方插件示例
提供任务管理、状态跟踪和数据持久化功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, 
    QListWidget, QInputDialog, QMessageBox, 
    QGroupBox, QComboBox, QHBoxLayout
)
from PySide6.QtCore import Qt
from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider, DataProviderError
from .service import TaskService


class TaskManagerPlugin(IPlugin):
    """任务管理器插件"""
    
    @property
    def plugin_name(self) -> str:
        return "任务\n管理器"
    
    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 使用单例的 DataProvider
        dp = DataProvider()
        
        # 确保 plugin_id 存在
        if not self.plugin_id:
            self._plugin_id = "task-manager-default"
        
        # 获取实际的 plugin_id（此时保证不为 None）
        actual_plugin_id = self.plugin_id
        if actual_plugin_id is None:
            # 理论上不应该到这里，但作为最后的保障
            actual_plugin_id = "task-manager-default"
            self._plugin_id = actual_plugin_id
        
        # 尝试注册插件（如果不存在）
        try:
            dp.register_plugin(actual_plugin_id, "TaskManager")
            dp.set_active_instance(actual_plugin_id)
        except DataProviderError:
            # 插件已存在，忽略
            pass
        
        # 创建服务实例
        service = TaskService(actual_plugin_id)
        
        # 如果外部传入了 data_provider，也尝试使用它注册（保持向后兼容）
        if data_provider:
            try:
                data_provider.register_plugin(actual_plugin_id, "TaskManager")
                data_provider.set_active_instance(actual_plugin_id)
            except DataProviderError:
                pass
        
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # 标题
        title = QLabel("任务管理器")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)
        
        # 添加任务区域
        add_group = QGroupBox("添加新任务")
        add_layout = QVBoxLayout()
        
        # 标题输入提示
        self.title_input = QListWidget()
        self.title_input.addItem("双击此处添加新任务...")
        self.title_input.itemDoubleClicked.connect(self._add_task_dialog)
        add_layout.addWidget(self.title_input)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        add_btn = QPushButton("添加任务")
        add_btn.clicked.connect(lambda: self._add_task_dialog())
        button_layout.addWidget(add_btn)
        
        priority_combo = QComboBox()
        priority_combo.addItems(["low", "normal", "high"])
        button_layout.addWidget(QLabel("优先级:"))
        button_layout.addWidget(priority_combo)
        self.priority_combo = priority_combo
        
        add_layout.addLayout(button_layout)
        add_group.setLayout(add_layout)
        layout.addWidget(add_group)
        
        # 任务列表
        list_group = QGroupBox("任务列表")
        list_layout = QVBoxLayout()
        
        self.task_list = QListWidget()
        self.task_list.itemDoubleClicked.connect(self._toggle_task_status)
        list_layout.addWidget(self.task_list)
        
        # 筛选按钮
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))
        
        filter_combo = QComboBox()
        filter_combo.addItems(["全部", "pending", "in_progress", "completed", "cancelled"])
        filter_combo.currentTextChanged.connect(lambda: self._filter_tasks(filter_combo.currentText()))
        filter_layout.addWidget(filter_combo)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(lambda: self._refresh_tasks(service))
        filter_layout.addWidget(refresh_btn)
        
        list_layout.addLayout(filter_layout)
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # 操作按钮
        action_layout = QHBoxLayout()
        
        complete_btn = QPushButton("标记完成")
        complete_btn.clicked.connect(lambda: self._complete_task(service))
        action_layout.addWidget(complete_btn)
        
        delete_btn = QPushButton("删除任务")
        delete_btn.clicked.connect(lambda: self._delete_task(service))
        action_layout.addWidget(delete_btn)
        
        export_btn = QPushButton("导出任务")
        export_btn.clicked.connect(lambda: self._export_tasks(service))
        action_layout.addWidget(export_btn)
        
        layout.addLayout(action_layout)
        
        # 统计信息
        stats_group = QGroupBox("统计信息")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("加载中...")
        stats_layout.addWidget(self.stats_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # 刷新数据
        self._refresh_tasks(service)
        self._update_stats(service)
        
        layout.addStretch()
        return widget
    
    def _add_task_dialog(self):
        """添加任务对话框"""
        if not self.plugin_id:
            return
        title, ok = QInputDialog.getText(None, "添加任务", "请输入任务标题:")
        if ok and title:
            service = TaskService(self.plugin_id)
            priority = self.priority_combo.currentText()
            task = service.add_task(title, priority=priority)
            QMessageBox.information(None, "成功", f"任务已添加！\nID: {task['id']}")
            self._refresh_tasks(service)
            self._update_stats(service)
    
    def _toggle_task_status(self):
        """切换任务状态"""
        if not self.plugin_id:
            return
        current_item = self.task_list.currentItem()
        if current_item:
            task_id = current_item.data(Qt.ItemDataRole.UserRole)
            service = TaskService(self.plugin_id)
            
            # 获取当前任务状态
            tasks = service.get_tasks()
            current_task = None
            for task in tasks:
                if task["id"] == task_id:
                    current_task = task
                    break
            
            if current_task:
                status = current_task["status"]
                new_status = "completed" if status != "completed" else "pending"
                if service.update_task_status(task_id, new_status):
                    self._refresh_tasks(service)
                    self._update_stats(service)
    
    def _complete_task(self, service):
        """标记任务完成"""
        current_item = self.task_list.currentItem()
        if current_item:
            task_id = current_item.data(Qt.ItemDataRole.UserRole)
            if service.update_task_status(task_id, "completed"):
                self._refresh_tasks(service)
                self._update_stats(service)
            else:
                QMessageBox.warning(None, "警告", "无法更新任务状态")
        else:
            QMessageBox.warning(None, "警告", "请先选择一个任务")
    
    def _delete_task(self, service):
        """删除任务"""
        current_item = self.task_list.currentItem()
        if current_item:
            task_id = current_item.data(Qt.ItemDataRole.UserRole)
            reply = QMessageBox.question(
                None, "确认删除", "确定要删除这个任务吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                if service.delete_task(task_id):
                    self._refresh_tasks(service)
                    self._update_stats(service)
                else:
                    QMessageBox.warning(None, "警告", "删除失败")
        else:
            QMessageBox.warning(None, "警告", "请先选择一个任务")
    
    def _export_tasks(self, service):
        """导出任务"""
        try:
            path = service.export_tasks("json")
            QMessageBox.information(
                None, "导出成功", 
                f"任务已导出到:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(None, "导出失败", f"导出失败: {str(e)}")
    
    def _filter_tasks(self, status_filter):
        """筛选任务"""
        if not self.plugin_id:
            return
        service = TaskService(self.plugin_id)
        if status_filter == "全部":
            tasks = service.get_tasks()
        else:
            tasks = service.get_tasks(status_filter)
        
        self.task_list.clear()
        for task in tasks:
            item_text = f"[{task['priority']}] {task['title']} ({task['status']})"
            item = self.task_list.addItem(item_text)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, task["id"])
    
    def _refresh_tasks(self, service=None):
        """刷新任务列表"""
        # 如果没有传入 service，则重新创建
        if service is None:
            if not self.plugin_id:
                return
            service = TaskService(self.plugin_id)
        
        tasks = service.get_tasks()
        self.task_list.clear()
        
        for task in tasks:
            item_text = f"[{task['priority']}] {task['title']} ({task['status']})"
            item = self.task_list.addItem(item_text)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, task["id"])
    
    def _update_stats(self, service=None):
        """更新统计信息"""
        # 如果没有传入 service，则重新创建
        if service is None:
            if not self.plugin_id:
                return
            service = TaskService(self.plugin_id)
        
        stats = service.get_statistics()
        text = f"总计: {stats['total']} | 待办: {stats['pending']} | 进行中: {stats['in_progress']} | 已完成: {stats['completed']}"
        self.stats_label.setText(text)
