"""关键插件进程隔离、严格协议与外部 watchdog 验收测试。"""

import json
import os
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
from io import BytesIO
from pathlib import Path

import pytest

from core.process_control import ProcessControl
from core.external_watchdog import (
    HeartbeatFile,
    Watchdog,
    WatchdogAction,
    WatchdogConfig,
    WatchdogStatus,
)
from core.plugin_host.protocol import (
    MESSAGE_HEADER_SIZE,
    PROTOCOL_VERSION,
    ProtocolError,
    decode_message,
    encode_message,
    read_message,
)
from core.plugin_host.proxy import RemotePluginProxy
from core.plugin_host.supervisor import (
    PROJECT_ROOT,
    HostConfig,
    HostState,
    PluginHost,
    PluginHostError,
)


WAIT_TIMEOUT = 8.0
POLL_INTERVAL = 0.05


def _write_test_plugin(plugin_dir: Path) -> None:
    """创建仅存在于临时目录的无 UI Service/API 测试插件。"""
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("", encoding="utf-8")
    (plugin_dir / ".plugin_info.json").write_text(
        json.dumps({"plugin_id": str(uuid.uuid4()), "registered_at": None}),
        encoding="utf-8",
    )
    (plugin_dir / "entrance.py").write_text(
        """from core.interfaces import IPlugin

class HostedPlugin(IPlugin):
    @property
    def plugin_name(self):
        return "HostedPlugin"

    def _create_widget(self, parent=None, data_provider=None):
        raise RuntimeError("进程外宿主禁止创建 UI")
""",
        encoding="utf-8",
    )
    (plugin_dir / "information.py").write_text(
        """from core.interfaces import IPluginInfo
from core.plugin.plugin_version import PluginVersion

class HostedPluginInfo(IPluginInfo):
    version = PluginVersion.from_string("release.1.0.0")
    developer = "Test"
    developer_email = "test@example.invalid"
    developer_website = "https://example.invalid"
    is_free = True
    description = "process isolation fixture"
    skill_icon = None
    skill_description = "fixture"
    plugin_type_id = "hosted-fixture"

    @property
    def service_api(self):
        return {name: {"description": name} for name in (
            "echo", "add", "fail", "spin", "crash", "bad_result", "flood", "bad_protocol"
        )}
""",
        encoding="utf-8",
    )
    (plugin_dir / "service.py").write_text(
        """import json
import os
import struct
import sys
import time

class Service:
    def echo(self, value):
        return {"value": value}

    def add(self, left, right):
        return left + right

    def fail(self):
        raise ValueError("插件预期故障")

    def spin(self):
        while True:
            time.sleep(0.05)

    def crash(self):
        os._exit(23)

    def bad_result(self):
        return object()

    def _flood(self, version):
        for _ in range(1000):
            body = json.dumps({"version": version, "type": "result", "id": "unknown", "result": 0}).encode()
            os.write(1, struct.pack(">I", len(body)) + body)
        return True

    def flood(self):
        return self._flood(1)

    def bad_protocol(self):
        return self._flood(999)
""",
        encoding="utf-8",
    )


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    path = tmp_path / "hosted_plugins" / "fixture_plugin"
    _write_test_plugin(path)
    return path


def _config(tmp_path: Path, **overrides) -> HostConfig:
    values = {
        "data_dir": str(tmp_path / "host-data"),
        "startup_timeout": WAIT_TIMEOUT,
        "heartbeat_interval": 0.1,
        "heartbeat_timeout": 2.0,
        "max_restarts": 1,
        "restart_backoff": 0.01,
        "max_pending_calls": 4,
    }
    values.update(overrides)
    return HostConfig(**values)


def _wait_for(predicate, timeout: float = WAIT_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(POLL_INTERVAL)
    assert predicate(), "等待宿主状态超时"


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def test_protocol_roundtrip_and_rejects_invalid_frames() -> None:
    """协议必须验证版本、长度、消息类型、请求 ID 与错误码。"""
    message = {
        "version": PROTOCOL_VERSION,
        "type": "call",
        "id": "request-1",
        "method": "echo",
        "args": {"value": 1},
    }
    assert decode_message(encode_message(message)[MESSAGE_HEADER_SIZE:]) == message
    assert read_message(BytesIO(encode_message(message))) == message
    invalid_messages = [
        {**message, "version": PROTOCOL_VERSION + 1},
        {**message, "version": True},
        {**message, "type": "unknown"},
        {**message, "type": []},
        {**message, "id": ""},
        {"version": PROTOCOL_VERSION, "type": "error", "id": "x", "code": "NOT_A_CODE", "message": "bad"},
        {"version": PROTOCOL_VERSION, "type": "error", "id": "x", "code": [], "message": "bad"},
    ]
    for invalid in invalid_messages:
        with pytest.raises(ProtocolError):
            decode_message(encode_message(invalid, validate=False))
    with pytest.raises(ProtocolError):
        read_message(BytesIO(struct.pack(">I", 2**31)))
    with pytest.raises(ProtocolError):
        read_message(BytesIO(struct.pack(">I", 10) + b"{}"))


def test_host_calls_proxy_and_plugin_errors(plugin_dir: Path, tmp_path: Path) -> None:
    """正常调用保持参数语义，插件异常不会逃逸为框架进程异常。"""
    host = PluginHost()
    handle = host.start(plugin_dir, _config(tmp_path))
    try:
        assert handle.pid > 0
        assert host.call("add", [2], timeout=2.0).error is not None
        positional = host.call("add", [2, 3], timeout=2.0)
        keyword = host.call("add", {"left": 2, "right": 4}, timeout=2.0)
        assert positional.value == 5 and positional.error is None
        assert keyword.value == 6
        assert RemotePluginProxy(host).echo(" ok ").value == {"value": " ok "}
        assert host.call("missing", [], timeout=1.0).error.code == "METHOD_NOT_FOUND"
        assert host.call("fail", [], timeout=1.0).error.code == "PLUGIN_ERROR"
        assert host.call("bad_result", [], timeout=1.0).error.code == "SERIALIZATION_ERROR"
        snapshot = host.snapshot()
        assert snapshot.state == HostState.READY
        assert snapshot.last_heartbeat > 0
        assert snapshot.restart_count == 0
    finally:
        report = host.stop(3.0)
    assert report.success
    assert not report.forced
    assert not _process_alive(handle.pid)


def test_call_timeout_and_stop_reap_non_cooperative_plugin(plugin_dir: Path, tmp_path: Path) -> None:
    """死循环调用必须有界返回，停止必须强杀不合作的子进程。"""
    host = PluginHost()
    handle = host.start(plugin_dir, _config(tmp_path))
    started = time.monotonic()
    result = host.call("spin", [], timeout=0.15)
    elapsed = time.monotonic() - started
    assert elapsed < 1.5
    assert result.error.code == "CALL_TIMEOUT"
    report = host.stop(0.2)
    assert report.forced
    assert report.success
    assert not _process_alive(handle.pid)


def test_crash_restart_budget_and_circuit_breaker(plugin_dir: Path, tmp_path: Path) -> None:
    """连续崩溃不得无限重启，预算耗尽后必须明确熔断。"""
    host = PluginHost()
    first_handle = host.start(plugin_dir, _config(tmp_path))
    crashed = host.call("crash", [], timeout=2.0)
    assert crashed.error.code == "PLUGIN_UNAVAILABLE"
    _wait_for(
        lambda: host.snapshot().state == HostState.READY
        and host.snapshot().restart_count == 1
    )
    assert host.snapshot().restart_count == 1
    assert host.handle.pid != first_handle.pid
    host.call("crash", [], timeout=2.0)
    _wait_for(lambda: host.snapshot().state == HostState.CIRCUIT_OPEN)
    result = host.call("echo", {"value": 1}, timeout=0.2)
    assert result.error.code == "CIRCUIT_OPEN"
    assert host.snapshot().restart_count == 1
    assert host.stop(1.0).success


@pytest.mark.parametrize("method", ["flood", "bad_protocol"])
def test_message_flood_and_bad_protocol_are_contained(
    method: str, plugin_dir: Path, tmp_path: Path
) -> None:
    """未知响应和错误协议均按故障处理，不能污染其他请求。"""
    host = PluginHost()
    host.start(plugin_dir, _config(tmp_path, max_restarts=0))
    result = host.call(method, [], timeout=2.0)
    assert result.error is not None
    assert result.error.code in {"PLUGIN_UNAVAILABLE", "PROTOCOL_ERROR"}
    _wait_for(lambda: host.snapshot().state == HostState.CIRCUIT_OPEN)
    assert host.stop(1.0).success


def test_concurrent_calls_have_bounded_pending_queue(plugin_dir: Path, tmp_path: Path) -> None:
    """并发提交不得超过声明的在途请求边界，且所有调用均有结果。"""
    host = PluginHost()
    host.start(plugin_dir, _config(tmp_path, max_pending_calls=2))
    results = []
    workers = [threading.Thread(target=lambda: results.append(host.call("echo", {"value": 1}, timeout=2.0))) for _ in range(8)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(3.0)
        assert all(not worker.is_alive() for worker in workers)
        assert len(results) == len(workers)
        assert all(result.error is None or result.error.code == "HOST_BUSY" for result in results)
        assert host.snapshot().pending_calls <= 2
    finally:
        assert host.stop(2.0).success


def test_parent_kill_reaps_child_through_stdin_and_parent_monitor(
    plugin_dir: Path, tmp_path: Path
) -> None:
    """主进程强杀后子进程也必须在限定时间内退出。"""
    driver = tmp_path / "host_driver.py"
    pid_file = tmp_path / "child.pid"
    driver.write_text(
        f"""import json
import sys
import time
from pathlib import Path
sys.path.insert(0, {str(PROJECT_ROOT)!r})
from core.plugin_host.supervisor import HostConfig, PluginHost
host = PluginHost()
handle = host.start(Path({str(plugin_dir)!r}), HostConfig(data_dir={str(tmp_path / 'driver-data')!r}))
Path({str(pid_file)!r}).write_text(str(handle.pid))
time.sleep(60)
""",
        encoding="utf-8",
    )
    parent = subprocess.Popen([sys.executable, str(driver)], cwd=PROJECT_ROOT)
    try:
        _wait_for(pid_file.exists)
        child_pid = int(pid_file.read_text(encoding="utf-8"))
        parent.kill()
        parent.wait(timeout=3.0)
        _wait_for(lambda: not _process_alive(child_pid))
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3.0)


def test_watchdog_requires_fresh_valid_heartbeat(tmp_path: Path) -> None:
    """无动作模式只报告状态，不得终止或启动任何进程。"""
    heartbeat = HeartbeatFile(tmp_path / "heartbeat.json")
    heartbeat.write(os.getpid())
    config = WatchdogConfig(heartbeat.path, os.getpid(), stale_after=5.0)
    healthy = Watchdog(config).check_once()
    assert healthy.status == WatchdogStatus.HEALTHY
    assert healthy.action == WatchdogAction.NONE
    stale_config = WatchdogConfig(heartbeat.path, os.getpid(), stale_after=0.001)
    time.sleep(0.01)
    stale = Watchdog(stale_config).check_once()
    assert stale.status == WatchdogStatus.STALE
    assert _process_alive(os.getpid())
    heartbeat.path.write_text("not-json", encoding="utf-8")
    invalid = Watchdog(config).check_once()
    assert invalid.status == WatchdogStatus.INVALID_HEARTBEAT


def test_watchdog_executes_only_explicit_exit_and_restart(tmp_path: Path) -> None:
    """退出与重启仅作用于配置目标，重启必须具有显式命令。"""
    target = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    created_pids = [target.pid]
    heartbeat = HeartbeatFile(tmp_path / "heartbeat.json")
    heartbeat.write(target.pid)
    try:
        exit_config = WatchdogConfig(
            heartbeat.path, target.pid, stale_after=0.001, action=WatchdogAction.EXIT
        )
        time.sleep(0.01)
        exited = Watchdog(exit_config).check_once()
        assert exited.status == WatchdogStatus.ACTION_COMPLETED
        target.wait(timeout=3.0)
        restarted_target = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        created_pids.append(restarted_target.pid)
        heartbeat.write(restarted_target.pid)
        restart_config = WatchdogConfig(
            heartbeat.path,
            restarted_target.pid,
            stale_after=0.001,
            action=WatchdogAction.RESTART,
            restart_command=(sys.executable, "-c", "import time; time.sleep(60)"),
        )
        time.sleep(0.01)
        restarted = Watchdog(restart_config).check_once()
        assert restarted.status == WatchdogStatus.ACTION_COMPLETED
        assert restarted.new_pid and restarted.new_pid != restarted_target.pid
        created_pids.append(restarted.new_pid)
        restarted_target.wait(timeout=3.0)
    finally:
        for pid in created_pids:
            if ProcessControl.is_alive(pid):
                ProcessControl.terminate(pid, 1.0)


def test_watchdog_rejects_restart_without_command(tmp_path: Path) -> None:
    """未配置重启命令时失败关闭，不得猜测应用入口或设备动作。"""
    with pytest.raises(ValueError):
        WatchdogConfig(
            tmp_path / "heartbeat.json", 1, action=WatchdogAction.RESTART
        ).validate()


def test_unstarted_host_fails_without_creating_resources() -> None:
    """未启动宿主不得隐式创建进程，调用必须立即返回明确状态。"""
    result = PluginHost().call("echo", [], timeout=0.01)
    assert result.error.code == "HOST_STOPPED"


def test_startup_failure_is_explicit_and_reaped(tmp_path: Path) -> None:
    """无有效入口的插件不得留下进程、后台监督器或假就绪句柄。"""
    invalid_plugin = tmp_path / "invalid_plugin"
    invalid_plugin.mkdir()
    host = PluginHost()
    config = _config(tmp_path, max_restarts=0, startup_timeout=1.0)
    with pytest.raises(PluginHostError):
        host.start(invalid_plugin, config)
    assert host.snapshot().state == HostState.STOPPED
    assert host.snapshot().pending_calls == 0


def test_configuration_and_heartbeat_reject_non_finite_or_boolean_values(tmp_path: Path) -> None:
    """布尔值、NaN 和无穷值不得绕过资源边界或心跳身份校验。"""
    invalid_configs = [
        HostConfig(startup_timeout=float("nan")),
        HostConfig(max_restarts=True),
        HostConfig(max_pending_calls=1.5),
        WatchdogConfig(tmp_path / "heartbeat.json", True),
        WatchdogConfig(tmp_path / "heartbeat.json", os.getpid(), stale_after=float("inf")),
    ]
    for config in invalid_configs:
        with pytest.raises(ValueError):
            config.validate()
    heartbeat = HeartbeatFile(tmp_path / "boolean-heartbeat.json")
    heartbeat.path.write_text(
        json.dumps({"version": True, "pid": os.getpid(), "timestamp": time.time()}),
        encoding="utf-8",
    )
    report = Watchdog(WatchdogConfig(heartbeat.path, os.getpid())).check_once()
    assert report.status == WatchdogStatus.INVALID_HEARTBEAT
