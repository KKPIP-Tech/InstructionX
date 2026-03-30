"""
后台任务演示器插件

用于演示 BackgroundTask 模块的所有功能：
1. 同步任务注册与执行
2. 异步任务注册与执行
3. 任务回调机制
4. 按插件 UUID 检索任务
5. 定时任务注册与管理
6. 任务状态查询
"""

import time
import threading
from datetime import datetime
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QComboBox, QSpinBox, QListWidget,
    QListWidgetItem, QLineEdit, QMessageBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QObject, Slot

from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider
from core.task import BackgroundTaskManager, TaskStatus


# Qt 信号桥接器 - 用于在主线程中安全更新 UI
class SignalBridge(QObject):
    """Qt 信号桥接器，用于线程安全的 UI 更新"""
    task_completed = Signal(str, str, str, str)  # task_id, status, result, error
    task_updated = Signal()  # 任务列表更新信号


# 全局日志缓冲区 - 用于定时任务回调（不依赖 UI）
_log_buffer = []


def _buffer_log(message: str):
    """缓冲区日志（供定时任务使用）"""
    _log_buffer.append(message)


class BackgroundTaskDemoPlugin(IPlugin):
    """后台任务演示器插件"""

    def __init__(self):
        super().__init__()
        self._data_provider = DataProvider()
        self._task_manager = BackgroundTaskManager()
        self._signal_bridge = SignalBridge()
        self._log_widget = None  # UI 日志组件引用

        # 注册到 DataProvider
        try:
            self._data_provider.register_plugin("background_task_demo", "official")
        except Exception:
            pass  # 插件已存在

        # 连接信号
        self._signal_bridge.task_completed.connect(self._on_task_completed)
        self._signal_bridge.task_updated.connect(self._refresh_task_list)

    def on_plugin_loaded(self) -> None:
        """
        插件加载完成回调

        在插件被加载且 plugin_id 已设置后调用。
        用于注册定时任务工厂，使定时任务可以在不打开插件的情况下执行。
        """
        if self.plugin_id:
            self._register_factory(self.plugin_id)

    def _register_factory(self, plugin_id: Optional[str]):
        """注册定时任务工厂"""
        # 定义不依赖 UI 的任务函数
        def task_func(name: str, seconds: int):
            _buffer_log(f"任务 '{name}' 开始执行，耗时 {seconds} 秒...")
            time.sleep(seconds)
            result = f"任务 '{name}' 完成！执行时间: {seconds}秒"
            _buffer_log(f"任务 '{name}' 执行完成")
            return result

        # 回调函数会在 UI 可用时被调用
        def task_callback(task_id: str, status: TaskStatus, result: str, error: Optional[str]):
            # 尝试通过信号更新 UI
            try:
                self._signal_bridge.task_completed.emit(
                    task_id,
                    status.value,
                    str(result) if result else "",
                    error if error else ""
                )
            except Exception:
                pass  # UI 不可用时忽略

        # 使用实际的 plugin_id 注册工厂
        if plugin_id:
            self._task_manager.register_scheduled_task_factory(
                plugin_id,
                task_func,
                task_callback
            )

    @property
    def plugin_name(self) -> str:
        return "后台任务演示"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        widget = QWidget(parent)
        main_layout = QVBoxLayout(widget)

        # 标题
        title = QLabel("BackgroundTask 模块演示")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title)

        # 显示插件 UUID
        self.plugin_id_label = QLabel(f"插件 UUID: {self.plugin_id or '加载中...'}")
        main_layout.addWidget(self.plugin_id_label)

        # ========== 任务创建区域 ==========
        create_group = QGroupBox("创建任务")
        create_layout = QVBoxLayout()

        # 任务类型选择
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("任务类型:"))
        self.task_type_combo = QComboBox()
        self.task_type_combo.addItems(["同步任务 (sync)", "异步任务 (async)", "定时任务 (scheduled)"])
        type_layout.addWidget(self.task_type_combo)
        create_layout.addLayout(type_layout)

        # 任务名称
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("任务名称:"))
        self.task_name_input = QLineEdit()
        self.task_name_input.setPlaceholderText("输入任务名称")
        self.task_name_input.setText("测试任务")
        name_layout.addWidget(self.task_name_input)
        create_layout.addLayout(name_layout)

        # 任务时长（模拟耗时任务）
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("执行时长(秒):"))
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 30)
        self.duration_spin.setValue(2)
        duration_layout.addWidget(self.duration_spin)
        create_layout.addLayout(duration_layout)

        # 定时任务间隔（仅定时任务使用）
        interval_layout = QHBoxLayout()
        interval_layout.addWidget(QLabel("间隔(秒):"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 3600)
        self.interval_spin.setValue(10)
        self.interval_spin.setEnabled(False)
        interval_layout.addWidget(self.interval_spin)

        # 启用定时任务复选框
        self.enable_scheduled_check = QCheckBox("启用")
        self.enable_scheduled_check.setChecked(True)
        interval_layout.addWidget(self.enable_scheduled_check)
        interval_layout.addStretch()
        create_layout.addLayout(interval_layout)

        # 任务类型切换时更新 UI
        self.task_type_combo.currentIndexChanged.connect(self._on_task_type_changed)

        # 创建任务按钮
        btn_layout = QHBoxLayout()
        self.create_btn = QPushButton("创建任务")
        self.create_btn.clicked.connect(self._create_task)
        btn_layout.addWidget(self.create_btn)

        self.cancel_btn = QPushButton("取消选中任务")
        self.cancel_btn.clicked.connect(self._cancel_task)
        btn_layout.addWidget(self.cancel_btn)

        create_layout.addLayout(btn_layout)
        create_group.setLayout(create_layout)
        main_layout.addWidget(create_group)

        # ========== 任务列表区域 ==========
        list_group = QGroupBox("任务列表")
        list_layout = QVBoxLayout()

        self.task_list = QListWidget()
        list_layout.addWidget(self.task_list)

        # 筛选和刷新
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("筛选:"))

        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["全部", "pending", "running", "completed", "failed", "cancelled"])
        self.filter_combo.currentTextChanged.connect(self._refresh_task_list)
        filter_layout.addWidget(self.filter_combo)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_task_list)
        filter_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("清理已完成")
        clear_btn.clicked.connect(self._clear_completed)
        filter_layout.addWidget(clear_btn)

        list_layout.addLayout(filter_layout)
        list_group.setLayout(list_layout)
        main_layout.addWidget(list_group)

        # ========== 日志区域 ==========
        log_group = QGroupBox("执行日志")
        log_layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        log_layout.addWidget(self.log_text)

        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)

        # 保存日志组件引用
        self._log_widget = self.log_text

        # 初始化插件 UUID
        if self.plugin_id:
            self.plugin_id_label.setText(f"插件 UUID: {self.plugin_id}")
            # 注册工厂（使用正确的 plugin_id）
            self._register_factory(self.plugin_id)
            # 恢复定时任务
            restored = self._task_manager.restore_scheduled_tasks(self.plugin_id)
            if restored > 0:
                self._log(f"[恢复] 已恢复 {restored} 个定时任务")

        # 输出缓冲区中的日志
        self._flush_log_buffer()

        # 初始刷新
        self._refresh_task_list()

        main_layout.addStretch()
        widget.setLayout(main_layout)
        return widget

    def _flush_log_buffer(self):
        """输出缓冲区中的日志"""
        global _log_buffer
        for msg in _log_buffer:
            self._log(msg)
        _log_buffer.clear()

    def _on_task_type_changed(self, index: int):
        """任务类型切换处理"""
        self.interval_spin.setEnabled(index == 2)

    def _create_task(self):
        """创建任务"""
        if not self.plugin_id:
            QMessageBox.warning(None, "警告", "插件未初始化")
            return

        task_type = self.task_type_combo.currentIndex()
        task_name = self.task_name_input.text().strip() or f"任务_{datetime.now().strftime('%H:%M:%S')}"
        duration = self.duration_spin.value()

        # 定义任务函数
        def task_func(name: str, seconds: int):
            self._log(f"任务 '{name}' 开始执行，耗时 {seconds} 秒...")
            time.sleep(seconds)
            result = f"任务 '{name}' 完成！执行时间: {seconds}秒"
            self._log(f"任务 '{name}' 执行完成")
            return result

        # 定义回调函数
        def task_callback(task_id: str, status: TaskStatus, result: str, error: Optional[str]):
            self._signal_bridge.task_completed.emit(
                task_id,
                status.value,
                str(result) if result else "",
                error if error else ""
            )

        try:
            if task_type == 0:  # 同步任务
                self._log(f"[同步] 创建任务: {task_name}")
                task_id = self._task_manager.register_sync_task(
                    plugin_id=self.plugin_id,
                    name=task_name,
                    func=task_func,
                    callback=task_callback,
                    args=(task_name, duration)
                )
                self._log(f"[同步] 任务已创建，ID: {task_id}")

            elif task_type == 1:  # 异步任务
                self._log(f"[异步] 创建任务: {task_name}")
                task_id = self._task_manager.register_async_task(
                    plugin_id=self.plugin_id,
                    name=task_name,
                    func=task_func,
                    callback=task_callback,
                    args=(task_name, duration)
                )
                self._log(f"[异步] 任务已创建，ID: {task_id}")

            elif task_type == 2:  # 定时任务
                interval = self.interval_spin.value()
                enabled = self.enable_scheduled_check.isChecked()
                self._log(f"[定时] 创建任务: {task_name}, 间隔: {interval}秒")

                task_id = self._task_manager.register_scheduled_task(
                    plugin_id=self.plugin_id,
                    name=task_name,
                    func=task_func,
                    interval=interval,
                    callback=task_callback,
                    args=(f"{task_name}_定时", 1)
                )

                if not enabled:
                    self._task_manager.disable_scheduled_task(task_id)
                    self._log(f"[定时] 任务已创建但已禁用，ID: {task_id}")
                else:
                    self._log(f"[定时] 任务已创建，ID: {task_id}")

            self._refresh_task_list()

        except Exception as e:
            QMessageBox.critical(None, "错误", f"创建任务失败: {str(e)}")
            self._log(f"[错误] 创建任务失败: {str(e)}")

    def _cancel_task(self):
        """取消选中的任务"""
        current_item = self.task_list.currentItem()
        if not current_item:
            QMessageBox.warning(None, "警告", "请先选择一个任务")
            return

        task_id = current_item.data(Qt.ItemDataRole.UserRole)
        if self._task_manager.cancel_task(task_id):
            self._log(f"[取消] 任务 {task_id} 已取消")
            self._refresh_task_list()
        else:
            QMessageBox.warning(None, "警告", "无法取消该任务（可能已完成）")

    def _clear_completed(self):
        """清理已完成的任务"""
        count = self._task_manager.clear_completed_tasks(self.plugin_id)
        self._log(f"[清理] 已清理 {count} 个已完成任务")
        self._refresh_task_list()

    def _refresh_task_list(self):
        """刷新任务列表"""
        if not self.plugin_id:
            return

        all_tasks = self._task_manager.get_tasks_by_plugin(self.plugin_id)
        scheduled_tasks = self._task_manager.get_scheduled_tasks(self.plugin_id)

        filter_status = self.filter_combo.currentText()

        self.task_list.clear()

        for task in all_tasks:
            if filter_status != "全部" and task.status.value != filter_status:
                continue

            status_icon = self._get_status_icon(task.status)
            item_text = f"{status_icon} {task.name} [{task.status.value}]"

            if task.result:
                result_str = str(task.result)
                if len(result_str) > 30:
                    result_str = result_str[:30] + "..."
                item_text += f" - {result_str}"

            if task.error:
                item_text += f" [错误: {task.error}]"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, task.task_id)
            self.task_list.addItem(item)

        for task in scheduled_tasks:
            status_str = "运行中" if task.enabled else "已禁用"
            next_run_str = task.next_run.strftime("%H:%M:%S") if task.next_run else "N/A"
            item_text = f"[定时] {task.name} [每{task.interval}秒] [{status_str}] 下次: {next_run_str}"

            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, f"scheduled_{task.task_id}")
            self.task_list.addItem(item)

    def _get_status_icon(self, status: TaskStatus) -> str:
        """获取状态图标"""
        icons = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫"
        }
        return icons.get(status, "❓")

    @Slot(str, str, str, str)
    def _on_task_completed(self, task_id: str, status: str, result: str, error: str):
        """任务完成回调（主线程）"""
        if error:
            self._log(f"[回调] 任务 {task_id} 失败: {error}")
        else:
            self._log(f"[回调] 任务 {task_id} 完成，结果: {result}")
        # 仅在 UI 已创建时刷新列表
        if hasattr(self, "task_list") and self.task_list is not None:
            self._refresh_task_list()

    def _log(self, message: str):
        """添加日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        # 检查 UI 是否已创建
        if hasattr(self, "log_text") and self.log_text is not None:
            self.log_text.append(f"[{timestamp}] {message}")
            self.log_text.verticalScrollBar().setValue(
                self.log_text.verticalScrollBar().maximum()
            )
        else:
            # UI 未创建时写入缓冲区
            _buffer_log(f"[{timestamp}] {message}")
