"""
任务报告生成器插件 - 官方插件示例
提供任务统计报告生成和实时监控功能
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QComboBox, QMessageBox,
    QInputDialog, QListWidget, QHBoxLayout
)
from PySide6.QtCore import Qt, QTimer
from core.plugin.plugin_interface import IPlugin
from .service import ReporterService


class TaskReporterPlugin(IPlugin):
    """任务报告生成器插件"""

    @property
    def plugin_name(self) -> str:
        return "任务\n报告"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        # 确保 plugin_id 存在
        plugin_id = self.plugin_id if self.plugin_id else "task-reporter-default"

        # 创建服务实例
        service = ReporterService(plugin_id)

        # 注册插件（如果还没注册）
        if data_provider:
            try:
                data_provider.register_plugin(plugin_id, "TaskReporter")
                data_provider.set_active_instance(plugin_id)
            except:
                pass

        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        # 标题
        title = QLabel("任务报告生成器")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        title.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        layout.addWidget(title)

        # 订阅管理区域
        subscribe_group = QGroupBox("订阅管理")
        subscribe_layout = QVBoxLayout()

        subscribe_layout.addWidget(QLabel("任务管理器插件ID:"))

        id_layout = QHBoxLayout()
        self.manager_id_input = QListWidget()

        # 自动获取活跃的 TaskManager 实例 ID
        active_manager_id = service.get_active_task_manager_id()
        if active_manager_id:
            self.manager_id_input.addItem(active_manager_id)
            self.manager_id_input.addItem("双击修改ID...")
        else:
            self.manager_id_input.addItem("未找到活跃的TaskManager")
            self.manager_id_input.addItem("双击手动输入...")

        self.manager_id_input.itemDoubleClicked.connect(self._edit_manager_id)
        id_layout.addWidget(self.manager_id_input)
        subscribe_layout.addLayout(id_layout)

        button_layout = QHBoxLayout()

        subscribe_btn = QPushButton("订阅")
        subscribe_btn.clicked.connect(lambda: self._subscribe(service))
        button_layout.addWidget(subscribe_btn)

        unsubscribe_btn = QPushButton("取消订阅")
        unsubscribe_btn.clicked.connect(lambda: self._unsubscribe(service))
        button_layout.addWidget(unsubscribe_btn)

        subscribe_layout.addLayout(button_layout)
        subscribe_group.setLayout(subscribe_layout)
        layout.addWidget(subscribe_group)

        # 统计报告区域
        stats_group = QGroupBox("统计报告")
        stats_layout = QVBoxLayout()

        self.stats_display = QTextEdit()
        self.stats_display.setReadOnly(True)
        self.stats_display.setMaximumHeight(150)
        stats_layout.addWidget(self.stats_display)

        refresh_btn = QPushButton("刷新统计")
        refresh_btn.clicked.connect(lambda: self._refresh_stats(service))
        stats_layout.addWidget(refresh_btn)

        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        # 报告生成区域
        report_group = QGroupBox("生成报告")
        report_layout = QVBoxLayout()

        format_layout = QHBoxLayout()
        format_layout.addWidget(QLabel("格式:"))

        format_combo = QComboBox()
        format_combo.addItems(["json", "txt", "html"])
        format_layout.addWidget(format_combo)
        self.format_combo = format_combo

        report_layout.addLayout(format_layout)

        generate_btn = QPushButton("生成报告")
        generate_btn.clicked.connect(lambda: self._generate_report(service))
        report_layout.addWidget(generate_btn)

        report_group.setLayout(report_layout)
        layout.addWidget(report_group)

        # 事件历史区域
        event_group = QGroupBox("事件历史")
        event_layout = QVBoxLayout()

        self.event_list = QListWidget()
        self.event_list.setMaximumHeight(150)
        event_layout.addWidget(self.event_list)

        refresh_events_btn = QPushButton("刷新事件")
        refresh_events_btn.clicked.connect(lambda: self._refresh_events(service))
        event_layout.addWidget(refresh_events_btn)

        clear_events_btn = QPushButton("清除历史")
        clear_events_btn.clicked.connect(lambda: self._clear_events(service))
        event_layout.addWidget(clear_events_btn)

        event_group.setLayout(event_layout)
        layout.addWidget(event_group)

        # 自动刷新
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: self._auto_refresh(service))
        self.timer.start(3000)  # 每3秒自动刷新

        layout.addStretch()
        return widget

    def _edit_manager_id(self):
        """编辑任务管理器ID"""
        current_id = self.manager_id_input.item(0).text()

        # 检查是否为提示性文本
        if current_id in ["未找到活跃的TaskManager", "双击手动输入..."]:
            current_id = ""

        new_id, ok = QInputDialog.getText(
            None, "修改任务管理器ID",
            "请输入任务管理器插件ID:",
            text=current_id
        )

        if ok and new_id:
            self.manager_id_input.clear()
            self.manager_id_input.addItem(new_id)
            self.manager_id_input.addItem("双击修改ID...")

    def _subscribe(self, service):
        """订阅任务管理器"""
        manager_id = self.manager_id_input.item(0).text()

        # 处理提示性文本
        if manager_id in ["未找到活跃的TaskManager", "双击手动输入...", "双击修改ID..."]:
            # 尝试自动获取
            manager_id = None

        plugin_id = self.plugin_id if self.plugin_id else "task-reporter-default"

        if service.subscribe_to_task_manager(manager_id):
            # 更新显示的 ID
            actual_id = service.get_active_task_manager_id() or manager_id
            if actual_id and actual_id != manager_id:
                self.manager_id_input.clear()
                self.manager_id_input.addItem(actual_id)
                self.manager_id_input.addItem("双击修改ID...")

            QMessageBox.information(None, "成功", "订阅成功！")
        else:
            QMessageBox.warning(None, "失败", "订阅失败，请确保 TaskManager 插件已激活")

    def _unsubscribe(self, service):
        """取消订阅"""
        manager_id = self.manager_id_input.item(0).text()

        # 处理提示性文本
        if manager_id in ["未找到活跃的TaskManager", "双击手动输入...", "双击修改ID..."]:
            manager_id = None

        service.unsubscribe_from_task_manager(manager_id)
        QMessageBox.information(None, "成功", "已取消订阅")

    def _refresh_stats(self, service):
        """刷新统计信息"""
        manager_id = self.manager_id_input.item(0).text()

        # 处理提示性文本
        if manager_id in ["未找到活跃的TaskManager", "双击手动输入...", "双击修改ID..."]:
            manager_id = None

        report = service.get_statistics_report(manager_id)

        if "error" in report:
            self.stats_display.setText(f"错误: {report['error']}")
        else:
            text = f"生成时间: {report['generated_at']}\n"

            if "task_manager_id" in report:
                text += f"TaskManager ID: {report['task_manager_id']}\n"

            text += "\n"

            if "statistics" in report:
                stats = report["statistics"]
                text += "统计信息:\n"
                text += f"  总计: {stats.get('total', 0)}\n"
                text += f"  待办: {stats.get('pending', 0)}\n"
                text += f"  进行中: {stats.get('in_progress', 0)}\n"
                text += f"  已完成: {stats.get('completed', 0)}\n"
                text += f"  已取消: {stats.get('cancelled', 0)}\n\n"

            if "metrics" in report:
                metrics = report["metrics"]
                text += "性能指标:\n"
                text += f"  完成率: {metrics.get('completion_rate', 0)}%\n"
                text += f"  待办比例: {metrics.get('pending_ratio', 0)}%\n"
                text += f"  进行中比例: {metrics.get('in_progress_ratio', 0)}%"

            self.stats_display.setText(text)

    def _auto_refresh(self, service):
        """自动刷新"""
        self._refresh_stats(service)
        self._refresh_events(service)

    def _refresh_events(self, service):
        """刷新事件历史"""
        events = service.get_event_history(20)

        self.event_list.clear()
        for event in events:
            event_type = event.get("type", "unknown")
            timestamp = event.get("timestamp", "")
            item_text = f"[{timestamp}] {event_type}"
            self.event_list.addItem(item_text)

    def _clear_events(self, service):
        """清除事件历史"""
        reply = QMessageBox.question(
            None, "确认清除", "确定要清除所有事件历史吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            service.clear_event_log()
            self._refresh_events(service)
            QMessageBox.information(None, "成功", "事件历史已清除")

    def _generate_report(self, service):
        """生成报告"""
        manager_id = self.manager_id_input.item(0).text()

        # 处理提示性文本
        if manager_id in ["未找到活跃的TaskManager", "双击手动输入...", "双击修改ID..."]:
            manager_id = None

        format_type = self.format_combo.currentText()

        try:
            path = service.generate_report(manager_id, format_type)
            QMessageBox.information(
                None, "生成成功",
                f"报告已生成到:\n{path}"
            )
        except Exception as e:
            QMessageBox.critical(None, "生成失败", f"生成失败: {str(e)}")
