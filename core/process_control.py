"""跨平台进程存活检查与有界终止，供宿主和 watchdog 复用。"""

import ctypes
import os
import signal
import time
from ctypes import wintypes


WINDOWS_STILL_ACTIVE = 259
WINDOWS_PROCESS_TERMINATE = 0x0001
WINDOWS_SYNCHRONIZE = 0x00100000
WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WINDOWS_WAIT_OBJECT_0 = 0
MILLISECONDS_PER_SECOND = 1000
PROCESS_POLL_INTERVAL = 0.02


class ProcessControl:
    """只执行调用方明确指定 PID 的进程检查与终止。"""

    @staticmethod
    def is_alive(pid: int) -> bool:
        """返回进程是否仍在运行；Windows 使用真实退出码而非信号零探测。"""
        if pid <= 0:
            return False
        if os.name == "nt":
            return ProcessControl._windows_alive(pid)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def terminate(pid: int, timeout: float) -> None:
        """在截止期内终止指定进程，失败时抛出异常而不是报告假成功。"""
        if timeout <= 0:
            raise ValueError("进程终止超时必须大于零")
        if os.name == "nt":
            ProcessControl._windows_terminate(pid, timeout)
            return
        ProcessControl._posix_terminate(pid, timeout)

    @staticmethod
    def _windows_alive(pid: int) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        handle = open_process(WINDOWS_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise OSError(ctypes.get_last_error(), "无法读取进程退出码")
            return exit_code.value == WINDOWS_STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _windows_terminate(pid: int, timeout: float) -> None:
        if not ProcessControl._windows_alive(pid):
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        open_process = kernel32.OpenProcess
        open_process.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        open_process.restype = wintypes.HANDLE
        access = WINDOWS_PROCESS_TERMINATE | WINDOWS_SYNCHRONIZE
        handle = open_process(access, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if not ProcessControl._windows_alive(pid):
                return
            raise OSError(error, "无法打开目标进程")
        try:
            if not kernel32.TerminateProcess(handle, 1):
                raise OSError(ctypes.get_last_error(), "无法终止目标进程")
            wait_ms = int(timeout * MILLISECONDS_PER_SECOND)
            if kernel32.WaitForSingleObject(handle, wait_ms) != WINDOWS_WAIT_OBJECT_0:
                raise TimeoutError("目标进程未在截止期内退出")
        finally:
            kernel32.CloseHandle(handle)

    @staticmethod
    def _posix_terminate(pid: int, timeout: float) -> None:
        if not ProcessControl.is_alive(pid):
            return
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and ProcessControl.is_alive(pid):
            time.sleep(PROCESS_POLL_INTERVAL)
        if ProcessControl.is_alive(pid):
            os.kill(pid, signal.SIGKILL)
        if ProcessControl.is_alive(pid):
            raise TimeoutError("目标进程未在截止期内退出")
