"""
本地HTTP服务器插件

提供本地HTTP服务器功能，使用长期任务实现。
"""

import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit,
    QLineEdit, QGroupBox, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QThread, QObject

from core.plugin.plugin_interface import IPlugin
from core.task import BackgroundTaskManager
from .service import Service

from utils.logging_tools import LoggerManager, get_name


class RequestHandler(BaseHTTPRequestHandler):
    """HTTP请求处理器"""

    # 类变量，用于存储回调函数
    on_request_callback = None

    def do_GET(self):
        """处理GET请求"""
        if RequestHandler.on_request_callback:
            try:
                RequestHandler.on_request_callback()
            except Exception:
                pass

        # 发送响应
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        response = {
            "status": "ok",
            "message": "Local Server is running",
            "path": self.path
        }
        self.wfile.write(json.dumps(response).encode())

    def do_POST(self):
        """处理POST请求"""
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)

        if RequestHandler.on_request_callback:
            try:
                RequestHandler.on_request_callback()
            except Exception:
                pass

        # 发送响应
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

        response = {
            "status": "ok",
            "message": "POST request received",
            "body": body.decode('utf-8', errors='ignore') if body else None
        }
        self.wfile.write(json.dumps(response).encode())

    def log_message(self, format, *args):
        """抑制HTTP服务器的日志输出"""
        pass


class SignalHolder(QObject):
    """信号持有者，用于跨线程通信"""
    status_changed = Signal(dict)


class LocalServerPlugin(IPlugin):
    """本地HTTP服务器插件"""

    _logger = LoggerManager()

    @property
    def plugin_name(self) -> str:
        return "本地\n服务器"

    def __init__(self):
        super().__init__()
        self._service = None
        self._task_manager = BackgroundTaskManager()
        self._server = None
        self._server_thread = None
        self._stop_event = threading.Event()
        self._port = 8080

        # 信号持有者（用于线程间通信）
        self._signal_holder = SignalHolder()
        self.status_changed = self._signal_holder.status_changed

    def on_plugin_loaded(self):
        """插件加载完成回调"""
        # plugin_id 已设置，可以注册长期任务工厂
        # 延迟注册，确保 plugin_id 可用
        if self.plugin_id:
            self._register_long_running_factory()

    def _register_long_running_factory(self):
        """注册长期任务工厂（用于重启恢复）"""
        self._task_manager.register_long_running_task_factory(
            plugin_id=self.plugin_id,
            func=self._create_server_func(),
            stop_callback=self._create_stop_callback(),
            status_callback=self._create_status_callback(),
            restore_callback=self._on_task_restored
        )

    def _on_task_restored(self, task_id: str, task):
        """任务恢复回调"""
        # 恢复任务时，更新 Service 状态
        self._service._server_task_id = task_id
        self._service._is_running = True
        self._service.save_data("server_task_id", task_id)
        self._service.set_running(True)

        # 如果UI已创建，更新UI状态
        if hasattr(self, 'start_btn'):
            self._restore_ui_state()

    def _create_server_func(self):
        """创建服务器函数"""
        def server_func():
            """HTTP服务器主函数"""
            try:
                self._server = HTTPServer(('127.0.0.1', self._port), RequestHandler)
                RequestHandler.on_request_callback = self._on_request
                self._logger.info(get_name(), f"Server started: http://127.0.0.1:{self._port}")
                self._server.serve_forever()
            except Exception as e:
                self._logger.error(get_name(), f"Server error: {e}")
            finally:
                if self._server:
                    self._server.server_close()
                self._logger.info(get_name(), "Server stopped")
        return server_func

    def _create_stop_callback(self):
        """创建停止回调"""
        def stop_callback():
            """优雅停止服务器"""
            self._logger.info(get_name(), "Stopping server...")
            self._stop_event.set()
            if self._server:
                self._server.shutdown()
        return stop_callback

    def _create_status_callback(self):
        """创建状态回调"""
        def status_callback(task_id: str, status: str):
            """状态更新回调"""
            self._logger.debug(get_name(), f"Server status: {status}")
            # 通知UI更新
            self.status_changed.emit({"status": status})
        return status_callback

    def _on_request(self):
        """处理请求的回调"""
        if self._service:
            self._service.increment_request_count()
            # 通知UI更新
            self.status_changed.emit({"action": "request"})

    def _create_widget(self, parent=None, data_provider=None):
        """创建插件UI"""
        from core.data.data_provider import DataProvider, DataProviderError

        # 使用单例的 DataProvider
        dp = DataProvider()

        # 确保 plugin_id 存在
        if not self.plugin_id:
            self._plugin_id = "local-server-default"

        # 获取实际的 plugin_id
        actual_plugin_id = self.plugin_id
        if actual_plugin_id is None:
            actual_plugin_id = "local-server-default"
            self._plugin_id = actual_plugin_id

        # 创建服务实例
        self._service = Service(actual_plugin_id, dp)

        # 注册插件
        try:
            dp.register_plugin(actual_plugin_id, "LocalServer")
            dp.set_active_instance(actual_plugin_id)
        except DataProviderError:
            # 插件已存在，忽略
            pass

        # 如果外部传入了 data_provider，也尝试使用它注册（保持向后兼容）
        if data_provider:
            try:
                data_provider.register_plugin(actual_plugin_id, "LocalServer")
                data_provider.set_active_instance(actual_plugin_id)
            except DataProviderError:
                pass

        # 创建UI
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        # 服务器控制组
        control_group = QGroupBox("服务器控制")
        control_layout = QVBoxLayout()

        # 端口设置
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("端口:"))
        self.port_input = QSpinBox()
        self.port_input.setRange(1024, 65535)
        self.port_input.setValue(8080)
        self.port_input.setEnabled(False)
        port_layout.addWidget(self.port_input)
        port_layout.addStretch()
        control_layout.addLayout(port_layout)

        # 启动/停止按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("启动服务器")
        self.start_btn.clicked.connect(self._start_server)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("停止服务器")
        self.stop_btn.clicked.connect(self._stop_server)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)
        control_layout.addLayout(btn_layout)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # 状态显示组
        status_group = QGroupBox("服务器状态")
        status_layout = QVBoxLayout()

        self.status_label = QLabel("状态: 未运行")
        self.status_label.setStyleSheet("font-weight: bold; color: gray;")
        status_layout.addWidget(self.status_label)

        self.request_count_label = QLabel("请求数: 0")
        status_layout.addWidget(self.request_count_label)

        self.url_label = QLabel("URL: -")
        status_layout.addWidget(self.url_label)

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # 日志显示
        log_group = QGroupBox("请求日志")
        log_layout = QVBoxLayout()
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(150)
        log_layout.addWidget(self.log_edit)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        # 连接信号
        self.status_changed.connect(self._on_status_changed)

        # 根据恢复的状态更新UI
        self._restore_ui_state()

        return widget

    def _start_server(self):
        """启动服务器"""
        self._port = self.port_input.value()
        self._stop_event.clear()

        # 保存端口
        self._service.save_data("port", self._port)

        # 注册长期任务
        self._service.set_running(True)
        task_id = self._task_manager.register_long_running_task(
            plugin_id=self.plugin_id,
            name="本地HTTP服务器",
            func=self._create_server_func(),
            stop_callback=self._create_stop_callback(),
            status_callback=self._create_status_callback(),
            auto_restart=False
        )

        self._service._server_task_id = task_id
        self._service.save_data("server_task_id", task_id)

        # 更新UI
        self.start_btn.setEnabled(False)
        self.port_input.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText(f"状态: 运行中")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        self.url_label.setText(f"URL: http://127.0.0.1:{self._port}")
        self._log(f"服务器已启动: http://127.0.0.1:{self._port}")

    def _stop_server(self):
        """停止服务器"""
        if self._service._server_task_id:
            self._task_manager.stop_long_running_task(self._service._server_task_id)
            # 清除任务ID
            self._service._server_task_id = None
            self._service.save_data("server_task_id", None)

        self._service.set_running(False)

        # 更新UI
        self.start_btn.setEnabled(True)
        self.port_input.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("状态: 已停止")
        self.status_label.setStyleSheet("font-weight: bold; color: red;")
        self.url_label.setText("URL: -")
        self._log("服务器已停止")

    def _on_status_changed(self, data):
        """状态变化回调"""
        if "action" in data and data["action"] == "request":
            # 更新请求计数
            if self._service:
                count = self._service._request_count
                self.request_count_label.setText(f"请求数: {count}")
                self._log(f"收到请求 (总计: {count})")

    def _restore_ui_state(self):
        """根据恢复的状态更新UI"""
        if not self._service:
            return

        # 获取恢复的状态
        is_running = self._service._is_running
        task_id = self._service._server_task_id
        request_count = self._service._request_count

        if is_running:
            # 更新按钮状态
            self.start_btn.setEnabled(False)
            self.port_input.setEnabled(False)
            self.stop_btn.setEnabled(True)

            # 更新状态显示
            self.status_label.setText("状态: 运行中")
            self.status_label.setStyleSheet("font-weight: bold; color: green;")

            # 获取端口（如果有）
            port = self._service.load_data("port", 8080)
            self.port_input.setValue(port)
            self.url_label.setText(f"URL: http://127.0.0.1:{port}")

            # 更新请求计数
            self.request_count_label.setText(f"请求数: {request_count}")

            self._log(f"服务器已恢复运行 (请求数: {request_count})")

    def _log(self, message: str):
        """添加日志"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_edit.append(f"[{timestamp}] {message}")
