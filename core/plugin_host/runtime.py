"""子进程内复用现有插件加载与服务注册规则的 RPC 运行时。"""

import os
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

from core.application_lifecycle import ApplicationLifecycle
from core.data import DataProvider
from core.interfaces.health import sanitize_health_message
from core.plugin.manager import PluginManager
from core.process_control import ProcessControl
from core.task.task_storage import TaskStorage

from .protocol import (
    ErrorCode,
    ProtocolEOF,
    ProtocolError,
    read_message,
    write_message,
)


HOST_CALLER_ID = "plugin-host"
STARTUP_MESSAGE_ID = "startup"
PROTOCOL_ERROR_MESSAGE_ID = "protocol-error"


class HostedPluginRuntime:
    """加载单个插件并串行执行其公开 Service/API 方法。"""

    def __init__(
        self,
        plugin_path: Path,
        input_stream: BinaryIO,
        output_stream: BinaryIO,
        heartbeat_interval: float,
        max_message_size: int,
        data_dir: Optional[str] = None,
    ) -> None:
        self._plugin_path = plugin_path
        self._input = input_stream
        self._output = output_stream
        self._heartbeat_interval = heartbeat_interval
        self._max_message_size = max_message_size
        self._data_dir = data_dir
        self._manager: Optional[PluginManager] = None
        self._plugin_id = ""
        self._write_lock = threading.Lock()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._heartbeat_sequence = 0

    def start(self) -> None:
        """通过既有插件管理器完成实例化、依赖注入和 API 注册。"""
        self._prepare_data_services()
        self._manager = PluginManager()
        plugin = self._manager._load_plugin_from_directory(self._plugin_path)
        if plugin is None:
            raise RuntimeError(self._load_failure_detail())
        self._plugin_id = plugin.plugin_id
        api = self._manager.get_plugin_api(self._plugin_id)
        if api is None:
            raise RuntimeError("进程外插件必须提供有效的 service_api 与 Service")
        self._send({
            "version": 1, "type": "ready", "id": STARTUP_MESSAGE_ID,
            "plugin_id": self._plugin_id, "methods": api["methods"],
        })
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_main, name="PluginHost-heartbeat", daemon=True
        )
        self._heartbeat_thread.start()

    def serve(self) -> int:
        """读取并处理请求；正常关闭返回 0，协议或插件清理失败返回非零。"""
        try:
            while True:
                message = read_message(self._input, self._max_message_size)
                if message["type"] == "shutdown":
                    return self._shutdown(message["id"])
                if message["type"] == "call":
                    self._dispatch(message)
        except ProtocolEOF:
            return 0
        except (ProtocolError, OSError, ValueError):
            self._send_error(
                PROTOCOL_ERROR_MESSAGE_ID, ErrorCode.PROTOCOL_ERROR, "宿主收到无效协议消息"
            )
            return 2

    def _dispatch(self, message: Dict[str, Any]) -> None:
        request_id = message["id"]
        method = message["method"]
        api = self._manager._api_registry.get(self._plugin_id)
        if api is None or method not in api.api_methods:
            self._send_error(request_id, ErrorCode.METHOD_NOT_FOUND, "插件方法未注册")
            return
        try:
            result = self._invoke(api.api_methods[method], message["args"])
        except Exception as exc:
            self._send_error(request_id, ErrorCode.PLUGIN_ERROR, sanitize_health_message(exc))
            return
        response = {"version": 1, "type": "result", "id": request_id, "result": result}
        try:
            self._send(response)
        except ProtocolError:
            self._send_error(
                request_id, ErrorCode.SERIALIZATION_ERROR, "插件返回值不是受支持的 JSON 数据"
            )

    @staticmethod
    def _invoke(method, args: list | dict) -> Any:
        if isinstance(args, dict):
            return method(**args)
        return method(*args)

    def _shutdown(self, request_id: str) -> int:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=self._heartbeat_interval * 2)
        report = ApplicationLifecycle().shutdown()
        self._send({"version": 1, "type": "stopped", "id": request_id})
        return 0 if report.success else 1

    def _prepare_data_services(self) -> None:
        if self._data_dir:
            DataProvider(data_dir=self._data_dir)
            TaskStorage(data_dir=self._data_dir)

    def _load_failure_detail(self) -> str:
        failures = self._manager.get_plugin_load_failures()
        if not failures:
            return "插件加载失败且未提供诊断"
        return "; ".join(f"{item.reason}: {item.detail}" for item in failures)

    def _heartbeat_main(self) -> None:
        while not self._heartbeat_stop.wait(self._heartbeat_interval):
            self._heartbeat_sequence += 1
            try:
                self._send({
                    "version": 1, "type": "heartbeat",
                    "id": f"heartbeat-{self._heartbeat_sequence}",
                })
            except (OSError, ProtocolError):
                return

    def _send_error(self, request_id: str, code: ErrorCode, message: str) -> None:
        self._send({
            "version": 1, "type": "error", "id": request_id,
            "code": code.value, "message": message,
        })

    def _send(self, message: Dict[str, Any]) -> None:
        with self._write_lock:
            write_message(self._output, message, self._max_message_size)


class ParentProcessMonitor:
    """在主进程异常退出且插件无法读取 stdin 时兜底结束子进程。"""

    def __init__(self, parent_pid: int, interval: float = 0.5) -> None:
        self._parent_pid = parent_pid
        self._interval = interval

    def start(self) -> threading.Thread:
        """启动守护监测线程并返回线程对象。"""
        worker = threading.Thread(target=self._run, name="PluginHost-parent", daemon=True)
        worker.start()
        return worker

    def _run(self) -> None:
        while True:
            time.sleep(self._interval)
            if not self._parent_alive():
                os._exit(0)

    def _parent_alive(self) -> bool:
        return ProcessControl.is_alive(self._parent_pid)
