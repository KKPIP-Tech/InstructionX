"""可选进程外插件宿主的生命周期、调用边界与有限重启监督。"""

import atexit
import math
import os
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict, deque
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Deque, Dict, Mapping, Optional

from core.interfaces.health import sanitize_health_message

from .protocol import (
    DEFAULT_MAX_MESSAGE_SIZE,
    ErrorCode,
    ProtocolError,
    RpcError,
    RpcResult,
    encode_message,
    read_message,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
HOST_ENTRY = PROJECT_ROOT / "scripts" / "plugin_host_entry.py"
MAX_STDERR_LINES = 10
MAX_SNAPSHOT_ERROR_LENGTH = 2000
MONITOR_MIN_INTERVAL = 0.02
MONITOR_MAX_INTERVAL = 0.1
ABSOLUTE_MAX_MESSAGE_SIZE = 16 * 1024 * 1024


class HostState(StrEnum):
    """宿主可观测状态机。"""

    STARTING = "STARTING"
    READY = "READY"
    RESTARTING = "RESTARTING"
    CIRCUIT_OPEN = "CIRCUIT_OPEN"
    STOPPING = "STOPPING"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class HostConfig:
    """单插件宿主配置；所有并发、等待与重启资源均有显式上限。"""

    data_dir: Optional[str] = None
    startup_timeout: float = 10.0
    heartbeat_interval: float = 1.0
    heartbeat_timeout: float = 3.0
    max_restarts: int = 2
    restart_backoff: float = 0.1
    max_pending_calls: int = 16
    max_message_size: int = DEFAULT_MAX_MESSAGE_SIZE

    def validate(self) -> None:
        """拒绝会导致无界等待、无界资源或无效心跳的配置。"""
        time_values = (
            self.startup_timeout, self.heartbeat_interval,
            self.heartbeat_timeout, self.restart_backoff,
        )
        if not all(type(value) in (int, float) and math.isfinite(value) for value in time_values):
            raise ValueError("时间配置必须是有限数值")
        if min(self.startup_timeout, self.heartbeat_interval, self.heartbeat_timeout) <= 0:
            raise ValueError("启动与心跳时间必须大于零")
        if self.heartbeat_timeout <= self.heartbeat_interval:
            raise ValueError("心跳超时必须大于心跳间隔")
        if type(self.max_restarts) is not int or self.max_restarts < 0 or self.restart_backoff < 0:
            raise ValueError("重启次数和退避时间不能为负数")
        if type(self.max_pending_calls) is not int or self.max_pending_calls <= 0:
            raise ValueError("在途调用上限必须是正整数")
        if type(self.max_message_size) is not int or not 0 < self.max_message_size <= ABSOLUTE_MAX_MESSAGE_SIZE:
            raise ValueError("消息大小上限超出允许范围")


@dataclass(frozen=True, slots=True)
class PluginHandle:
    """当前子进程身份；重启后由 ``PluginHost.handle`` 获取新句柄。"""

    plugin_path: Path
    plugin_id: str
    pid: int
    started_at: float


@dataclass(frozen=True, slots=True)
class HostSnapshot:
    """某一时刻的宿主健康、心跳、熔断和在途调用快照。"""

    state: HostState
    pid: Optional[int]
    restart_count: int
    pending_calls: int
    last_heartbeat: float
    last_error: str


@dataclass(frozen=True, slots=True)
class StopReport:
    """停止结果；强杀和清理失败均明确标记。"""

    success: bool
    forced: bool
    exit_code: Optional[int]
    error: str = ""


class PluginHostError(RuntimeError):
    """宿主无法启动或配置不合法。"""


@dataclass(slots=True)
class _PendingCall:
    event: threading.Event
    result: Optional[RpcResult] = None


@dataclass(frozen=True, slots=True)
class _Outbound:
    frame: bytes
    generation: int


class PluginHost:
    """承载一个无 UI Service/API 插件进程，并提供同步有界 RPC。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(1)
        self._outbound: queue.Queue = queue.Queue(maxsize=1)
        self._pending: Dict[str, _PendingCall] = {}
        self._abandoned: OrderedDict[str, None] = OrderedDict()
        self._state = HostState.STOPPED
        self._process: Optional[subprocess.Popen] = None
        self._handle: Optional[PluginHandle] = None
        self._config: Optional[HostConfig] = None
        self._plugin_path: Optional[Path] = None
        self._generation = 0
        self._restart_count = 0
        self._last_heartbeat = 0.0
        self._last_error = ""
        self._stderr_lines: Deque[str] = deque(maxlen=MAX_STDERR_LINES)
        self._reader_failed = False
        self._stopping = False
        self._stop_event = threading.Event()
        self._writer_stop = threading.Event()
        self._monitor: Optional[threading.Thread] = None
        self._writer: Optional[threading.Thread] = None
        self._atexit_registered = False

    def start(
        self, plugin_path: os.PathLike | str, config: HostConfig | Mapping[str, Any]
    ) -> PluginHandle:
        """启动明确指定的插件；启动失败会回收进程并抛出 ``PluginHostError``。"""
        host_config = self._coerce_config(config)
        path = Path(plugin_path).resolve()
        if not path.is_dir():
            raise PluginHostError("插件目录不存在")
        with self._lock:
            if self._process is not None or self._state not in (HostState.STOPPED, HostState.CIRCUIT_OPEN):
                raise PluginHostError("宿主已经启动或正在停止")
            self._initialize(host_config, path)
            try:
                self._launch_locked()
            except OSError as exc:
                self._finish_stop()
                raise PluginHostError(f"无法创建插件进程: {exc}") from exc
        self._monitor = self._daemon("PluginHost-monitor", self._monitor_main)
        self._writer = self._daemon("PluginHost-writer", self._writer_main)
        self._monitor.start()
        self._writer.start()
        atexit.register(self.stop)
        self._atexit_registered = True
        if not self._await_ready(host_config.startup_timeout):
            error = self.snapshot().last_error or "插件宿主启动超时"
            self.stop(host_config.startup_timeout)
            raise PluginHostError(error)
        return self.handle

    def call(self, method: str, args: list | dict, timeout: float) -> RpcResult:
        """调用 Service 方法；等待、在途数量和消息大小均受配置约束。"""
        if timeout <= 0:
            return self._error(ErrorCode.INVALID_PARAMS, "调用超时必须大于零")
        if not isinstance(args, (list, dict)):
            return self._error(ErrorCode.INVALID_PARAMS, "调用参数必须是数组或对象")
        if self._config is None:
            return self._error(ErrorCode.HOST_STOPPED, "插件宿主尚未启动")
        request_id = uuid.uuid4().hex
        message = {"version": 1, "type": "call", "id": request_id, "method": method, "args": args}
        try:
            frame = encode_message(message, max_message_size=self._config.max_message_size)
        except (ProtocolError, AttributeError) as exc:
            return self._error(ErrorCode.INVALID_PARAMS, str(exc), request_id)
        unavailable = self._unavailable_result(request_id)
        if unavailable is not None:
            return unavailable
        if not self._slots.acquire(blocking=False):
            return self._error(ErrorCode.HOST_BUSY, "在途调用已达到上限", request_id)
        pending = _PendingCall(threading.Event())
        with self._lock:
            unavailable = self._unavailable_result(request_id)
            if unavailable is not None:
                self._slots.release()
                return unavailable
            generation = self._generation
            self._pending[request_id] = pending
        try:
            self._outbound.put_nowait(_Outbound(frame, generation))
        except queue.Full:
            self._discard_pending(request_id)
            self._slots.release()
            return self._error(ErrorCode.HOST_BUSY, "宿主写入队列已满", request_id)
        return self._wait_result(request_id, pending, timeout)

    def stop(self, timeout: float = 3.0) -> StopReport:
        """停止并回收子进程；不合作时在截止期后强制终止。"""
        if timeout <= 0:
            return StopReport(False, False, None, "停止超时必须大于零")
        started = time.monotonic()
        with self._lock:
            if self._state == HostState.STOPPED and self._process is None:
                return StopReport(True, False, 0)
            self._stopping = True
            self._state = HostState.STOPPING
            process = self._process
            self._stop_event.set()
        if process is None:
            self._finish_stop()
            return StopReport(True, False, None)
        graceful = self._request_shutdown(process, timeout)
        remaining = max(0.0, timeout - (time.monotonic() - started))
        if graceful:
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                pass
        forced = process.poll() is None
        error = self._terminate_process(process, remaining) if forced else ""
        self._finish_stop()
        self._join_workers()
        success = process.poll() is not None and not error
        return StopReport(success, forced, process.returncode, error)

    @property
    def handle(self) -> PluginHandle:
        """返回当前句柄；未成功启动时抛出明确异常。"""
        with self._lock:
            if self._handle is None:
                raise PluginHostError("插件宿主尚未就绪")
            return self._handle

    def snapshot(self) -> HostSnapshot:
        """返回不暴露插件参数和返回值的健康快照。"""
        with self._lock:
            pid = self._process.pid if self._process is not None else None
            return HostSnapshot(
                self._state, pid, self._restart_count, len(self._pending),
                self._last_heartbeat, self._last_error,
            )

    def _initialize(self, config: HostConfig, path: Path) -> None:
        self._config = config
        self._plugin_path = path
        self._handle = None
        self._slots = threading.BoundedSemaphore(config.max_pending_calls)
        self._outbound = queue.Queue(maxsize=config.max_pending_calls)
        self._pending.clear()
        self._abandoned.clear()
        self._restart_count = 0
        self._last_error = ""
        self._stopping = False
        self._stop_event = threading.Event()
        self._writer_stop = threading.Event()
        self._state = HostState.STARTING

    @staticmethod
    def _coerce_config(config: HostConfig | Mapping[str, Any]) -> HostConfig:
        result = config if isinstance(config, HostConfig) else HostConfig(**config)
        result.validate()
        return result

    def _launch_locked(self) -> None:
        command = self._child_command()
        self._reader_failed = False
        self._stderr_lines.clear()
        self._process = subprocess.Popen(
            command, cwd=PROJECT_ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, bufsize=0,
        )
        self._generation += 1
        self._last_heartbeat = time.monotonic()
        self._daemon("PluginHost-reader", self._reader_main, self._process, self._generation).start()
        self._daemon("PluginHost-stderr", self._stderr_main, self._process).start()

    def _child_command(self) -> list[str]:
        config = self._config
        command = [
            sys.executable, str(HOST_ENTRY), "--plugin-path", str(self._plugin_path),
            "--parent-pid", str(os.getpid()), "--heartbeat-interval", str(config.heartbeat_interval),
            "--max-message-size", str(config.max_message_size),
        ]
        if config.data_dir:
            command.extend(("--data-dir", config.data_dir))
        return command

    def _await_ready(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                if self._state == HostState.READY:
                    return True
                if self._state in (HostState.CIRCUIT_OPEN, HostState.STOPPED):
                    return False
            time.sleep(MONITOR_MIN_INTERVAL)
        return False

    def _wait_result(self, request_id: str, pending: _PendingCall, timeout: float) -> RpcResult:
        completed = pending.event.wait(timeout)
        if completed and pending.result is not None:
            self._slots.release()
            return pending.result
        with self._lock:
            self._pending.pop(request_id, None)
            self._abandoned[request_id] = None
            while len(self._abandoned) > self._config.max_pending_calls:
                self._abandoned.popitem(last=False)
        self._slots.release()
        return self._error(ErrorCode.CALL_TIMEOUT, "插件调用超过截止期", request_id)

    def _unavailable_result(self, request_id: str) -> Optional[RpcResult]:
        with self._lock:
            if self._state == HostState.READY and not self._stopping:
                return None
            if self._state == HostState.CIRCUIT_OPEN:
                code = ErrorCode.CIRCUIT_OPEN
            elif self._stopping or self._state == HostState.STOPPED:
                code = ErrorCode.HOST_STOPPED
            else:
                code = ErrorCode.PLUGIN_UNAVAILABLE
            return self._error(code, f"插件宿主当前不可用: {self._state.value}", request_id)

    def _reader_main(self, process: subprocess.Popen, generation: int) -> None:
        try:
            while True:
                message = read_message(process.stdout, self._config.max_message_size)
                self._handle_message(process, generation, message)
        except (ProtocolError, OSError, ValueError) as exc:
            self._reader_ended(process, generation, str(exc))

    def _handle_message(self, process: subprocess.Popen, generation: int, message: dict) -> None:
        if generation != self._generation:
            return
        message_type = message["type"]
        if message_type == "heartbeat":
            with self._lock:
                self._last_heartbeat = time.monotonic()
            return
        if message_type == "ready":
            self._mark_ready(process, message)
            return
        if message_type == "error" and message["id"] == "startup":
            with self._lock:
                self._reader_failed = True
                self._remember_error(message["message"])
            return
        if message_type == "stopped":
            self._complete_response(message["id"], RpcResult(request_id=message["id"]))
            return
        if message_type == "result":
            self._complete_response(message["id"], RpcResult(message["result"], request_id=message["id"]))
            return
        error = RpcError(message["code"], message["message"])
        self._complete_response(message["id"], RpcResult(error=error, request_id=message["id"]))

    def _mark_ready(self, process: subprocess.Popen, message: dict) -> None:
        with self._lock:
            if self._stopping:
                return
            self._handle = PluginHandle(
                self._plugin_path, message["plugin_id"], process.pid, time.time()
            )
            self._last_heartbeat = time.monotonic()
            self._state = HostState.READY

    def _complete_response(self, request_id: str, result: RpcResult) -> None:
        with self._lock:
            pending = self._pending.pop(request_id, None)
            if pending is None and request_id in self._abandoned:
                self._abandoned.pop(request_id, None)
                return
            if pending is None:
                raise ProtocolError("响应包含未知请求 ID")
            pending.result = result
            pending.event.set()

    def _reader_ended(self, process: subprocess.Popen, generation: int, error: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._reader_failed = True
            self._remember_error(error)
            if not self._stopping:
                self._fail_pending(ErrorCode.PLUGIN_UNAVAILABLE, "插件连接已中断")

    def _stderr_main(self, process: subprocess.Popen) -> None:
        try:
            for raw_line in iter(process.stderr.readline, b""):
                line = raw_line.decode("utf-8", errors="replace").rstrip()
                with self._lock:
                    self._stderr_lines.append(line[:MAX_SNAPSHOT_ERROR_LENGTH])
        except OSError as exc:
            with self._lock:
                self._stderr_lines.append(f"读取插件错误输出失败: {exc}")

    def _monitor_main(self) -> None:
        interval = min(
            MONITOR_MAX_INTERVAL,
            max(MONITOR_MIN_INTERVAL, self._config.heartbeat_interval / 4),
        )
        while not self._stop_event.wait(interval):
            with self._lock:
                process = self._process
                failed = self._needs_recovery(process)
            if failed:
                self._recover(process)

    def _needs_recovery(self, process: Optional[subprocess.Popen]) -> bool:
        if self._stopping or process is None:
            return False
        if process.poll() is not None or self._reader_failed:
            return True
        timeout = self._config.startup_timeout if self._state == HostState.STARTING else self._config.heartbeat_timeout
        return time.monotonic() - self._last_heartbeat > timeout

    def _recover(self, process: subprocess.Popen) -> None:
        self._terminate_process(process, self._config.restart_backoff)
        with self._lock:
            if self._stopping or process is not self._process:
                return
            self._fail_pending(ErrorCode.PLUGIN_UNAVAILABLE, "插件进程已失效")
            if self._restart_count >= self._config.max_restarts:
                self._state = HostState.CIRCUIT_OPEN
                self._remember_error("插件重启预算耗尽，熔断器已打开")
                return
            self._restart_count += 1
            self._state = HostState.RESTARTING
        if self._stop_event.wait(self._config.restart_backoff):
            return
        with self._lock:
            if self._stopping:
                return
            try:
                self._launch_locked()
            except OSError as exc:
                self._state = HostState.CIRCUIT_OPEN
                self._remember_error(f"重启插件进程失败: {exc}")

    def _request_shutdown(self, process: subprocess.Popen, timeout: float) -> bool:
        request_id = uuid.uuid4().hex
        pending = _PendingCall(threading.Event())
        with self._lock:
            self._pending[request_id] = pending
        message = {"version": 1, "type": "shutdown", "id": request_id}
        try:
            frame = encode_message(message, max_message_size=self._config.max_message_size)
            self._outbound.put_nowait(_Outbound(frame, self._generation))
        except (ProtocolError, queue.Full):
            self._pending.pop(request_id, None)
            return False
        completed = pending.event.wait(timeout)
        self._pending.pop(request_id, None)
        return completed and pending.result is not None and pending.result.success

    def _terminate_process(self, process: subprocess.Popen, timeout: float) -> str:
        if process.poll() is not None:
            return ""
        try:
            process.terminate()
            process.wait(timeout=max(MONITOR_MIN_INTERVAL, timeout))
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=MONITOR_MAX_INTERVAL)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return f"无法回收插件进程: {exc}"
        except OSError as exc:
            return f"无法终止插件进程: {exc}"
        return ""

    def _finish_stop(self) -> None:
        with self._lock:
            self._fail_pending(ErrorCode.HOST_STOPPED, "插件宿主已停止")
            self._close_process_streams()
            self._process = None
            self._state = HostState.STOPPED
        self._writer_stop.set()
        if self._atexit_registered:
            atexit.unregister(self.stop)
            self._atexit_registered = False

    def _close_process_streams(self) -> None:
        if self._process is None:
            return
        for stream in (self._process.stdin, self._process.stdout, self._process.stderr):
            if stream is not None:
                try:
                    stream.close()
                except OSError as exc:
                    self._remember_error(f"关闭插件管道失败: {exc}")

    def _join_workers(self) -> None:
        current = threading.current_thread()
        for worker in (self._writer, self._monitor):
            if worker is not None and worker is not current:
                worker.join(timeout=MONITOR_MAX_INTERVAL)

    def _writer_main(self) -> None:
        while not self._writer_stop.is_set() or not self._outbound.empty():
            try:
                outbound = self._outbound.get(timeout=MONITOR_MAX_INTERVAL)
            except queue.Empty:
                continue
            self._write_outbound(outbound)

    def _write_outbound(self, outbound: _Outbound) -> None:
        with self._lock:
            process = self._process
            current = outbound.generation == self._generation and process is not None
        if not current:
            return
        try:
            with self._write_lock:
                process.stdin.write(outbound.frame)
                process.stdin.flush()
        except (OSError, ValueError) as exc:
            self._reader_ended(process, outbound.generation, f"写入插件失败: {exc}")

    def _fail_pending(self, code: ErrorCode, message: str) -> None:
        for request_id, pending in list(self._pending.items()):
            pending.result = self._error(code, message, request_id)
            pending.event.set()
        self._pending.clear()

    def _discard_pending(self, request_id: str) -> None:
        with self._lock:
            self._pending.pop(request_id, None)

    def _remember_error(self, error: str) -> None:
        details = " | ".join(self._stderr_lines)
        combined = f"{error}; {details}" if details else error
        self._last_error = sanitize_health_message(combined)[:MAX_SNAPSHOT_ERROR_LENGTH]

    @staticmethod
    def _error(code: ErrorCode, message: str, request_id: str = "") -> RpcResult:
        return RpcResult(error=RpcError(code.value, message), request_id=request_id)

    @staticmethod
    def _daemon(name: str, target, *args) -> threading.Thread:
        return threading.Thread(target=target, args=args, name=name, daemon=True)
