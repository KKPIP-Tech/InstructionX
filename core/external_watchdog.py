"""独立外部 watchdog：校验应用心跳并执行用户明确配置的恢复动作。"""

import json
import math
import os
import subprocess
import time
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Optional, Sequence, Tuple

from core.process_control import ProcessControl


HEARTBEAT_VERSION = 1
MAX_HEARTBEAT_BYTES = 4096
MAX_CLOCK_SKEW = 5.0


class WatchdogAction(StrEnum):
    """watchdog 允许执行的全部动作，不包含设备控制。"""

    NONE = "none"
    EXIT = "exit"
    RESTART = "restart"


class WatchdogStatus(StrEnum):
    """单次检查结果。"""

    HEALTHY = "HEALTHY"
    STALE = "STALE"
    PROCESS_EXITED = "PROCESS_EXITED"
    INVALID_HEARTBEAT = "INVALID_HEARTBEAT"
    ACTION_COMPLETED = "ACTION_COMPLETED"
    ACTION_FAILED = "ACTION_FAILED"


@dataclass(frozen=True, slots=True)
class WatchdogConfig:
    """监测目标与恢复动作；重启命令不得由 watchdog 自行猜测。"""

    heartbeat_path: Path
    target_pid: int
    stale_after: float = 10.0
    action: WatchdogAction = WatchdogAction.NONE
    restart_command: Optional[Tuple[str, ...]] = None
    termination_timeout: float = 3.0

    def validate(self) -> None:
        """验证目标、时间和动作配置，非法配置失败关闭。"""
        numeric_values = (self.stale_after, self.termination_timeout)
        if type(self.target_pid) is not int or self.target_pid <= 0:
            raise ValueError("目标 PID 必须是正整数")
        if not all(type(value) in (int, float) and math.isfinite(value) and value > 0 for value in numeric_values):
            raise ValueError("watchdog 超时必须是有限正数")
        if not isinstance(self.action, WatchdogAction):
            raise ValueError("watchdog 动作不受支持")
        if self.action == WatchdogAction.RESTART and not self.restart_command:
            raise ValueError("重启动作必须显式提供 restart_command")
        if self.restart_command and not all(self.restart_command):
            raise ValueError("重启命令不能包含空参数")


@dataclass(frozen=True, slots=True)
class WatchdogReport:
    """单次监测与动作结果；新 PID 只在实际重启后出现。"""

    status: WatchdogStatus
    action: WatchdogAction
    target_pid: int
    new_pid: Optional[int]
    message: str
    checked_at: float


class HeartbeatError(ValueError):
    """心跳文件损坏、版本不符或目标身份不一致。"""


class HeartbeatFile:
    """应用侧原子心跳写入与 watchdog 侧严格读取。"""

    def __init__(self, path: os.PathLike | str) -> None:
        self.path = Path(path)

    def write(self, pid: int) -> None:
        """写入当前进程心跳；调用方负责按声明周期执行。"""
        if type(pid) is not int or pid <= 0:
            raise ValueError("心跳 PID 必须是正整数")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = {"version": HEARTBEAT_VERSION, "pid": pid, "timestamp": time.time()}
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.path)

    def read(self, expected_pid: int) -> float:
        """读取并校验心跳，返回单调比较所需的 Unix 时间戳。"""
        try:
            raw = self.path.read_bytes()
            if len(raw) > MAX_HEARTBEAT_BYTES:
                raise HeartbeatError("心跳文件超过大小上限")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HeartbeatError(f"无法读取有效心跳: {exc}") from exc
        if not isinstance(payload, dict) or set(payload) != {"version", "pid", "timestamp"}:
            raise HeartbeatError("心跳字段不完整")
        if type(payload["version"]) is not int or payload["version"] != HEARTBEAT_VERSION:
            raise HeartbeatError("心跳版本不匹配")
        if type(payload["pid"]) is not int or payload["pid"] != expected_pid:
            raise HeartbeatError("心跳进程身份不匹配")
        timestamp = payload["timestamp"]
        if type(timestamp) not in (int, float) or not math.isfinite(timestamp) or timestamp <= 0:
            raise HeartbeatError("心跳时间戳类型无效")
        if timestamp > time.time() + MAX_CLOCK_SKEW:
            raise HeartbeatError("心跳时间戳超出允许的时钟偏差")
        return float(timestamp)


class Watchdog:
    """无全局状态的单次检查器，适合由独立脚本周期调用。"""

    def __init__(self, config: WatchdogConfig) -> None:
        config.validate()
        self._config = config

    def check_once(self) -> WatchdogReport:
        """检查一次心跳，仅在状态可信且动作明确时执行退出或重启。"""
        checked_at = time.time()
        try:
            timestamp = HeartbeatFile(self._config.heartbeat_path).read(self._config.target_pid)
        except HeartbeatError as exc:
            return self._report(WatchdogStatus.INVALID_HEARTBEAT, str(exc), checked_at)
        alive = self._process_alive(self._config.target_pid)
        if alive and checked_at - timestamp <= self._config.stale_after:
            return self._report(WatchdogStatus.HEALTHY, "目标心跳有效", checked_at)
        status = WatchdogStatus.STALE if alive else WatchdogStatus.PROCESS_EXITED
        if self._config.action == WatchdogAction.NONE:
            return self._report(status, "目标未按声明更新心跳", checked_at)
        return self._execute_action(alive, checked_at)

    def _execute_action(self, alive: bool, checked_at: float) -> WatchdogReport:
        try:
            if alive:
                self._terminate_target()
            new_pid = self._start_replacement() if self._config.action == WatchdogAction.RESTART else None
        except (OSError, TimeoutError, subprocess.TimeoutExpired) as exc:
            return self._report(WatchdogStatus.ACTION_FAILED, f"恢复动作失败: {exc}", checked_at)
        message = "已启动配置的新进程" if new_pid else "目标已退出"
        return self._report(WatchdogStatus.ACTION_COMPLETED, message, checked_at, new_pid)

    def _terminate_target(self) -> None:
        ProcessControl.terminate(self._config.target_pid, self._config.termination_timeout)

    def _start_replacement(self) -> int:
        command: Sequence[str] = self._config.restart_command or ()
        creation_flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True, creationflags=creation_flags,
        )
        return process.pid

    def _report(
        self, status: WatchdogStatus, message: str, checked_at: float,
        new_pid: Optional[int] = None,
    ) -> WatchdogReport:
        return WatchdogReport(
            status, self._config.action, self._config.target_pid,
            new_pid, message, checked_at,
        )

    @staticmethod
    def _process_alive(pid: int) -> bool:
        return ProcessControl.is_alive(pid)
