"""进程终止竞态的受控测试，不接触真实外部进程。"""

import os

import pytest

from core.process_control import ProcessControl, WINDOWS_STILL_ACTIVE


@pytest.mark.skipif(os.name != "nt", reason="Windows 进程句柄语义专项")
def test_terminate_accepts_target_that_exits_during_race(mocker) -> None:
    """TerminateProcess 返回失败时，目标已退出则按清理成功处理。"""
    exit_codes = [WINDOWS_STILL_ACTIVE, 0]
    kernel = mocker.MagicMock()
    kernel.OpenProcess.return_value = 123

    def get_exit_code(_handle, reference):
        reference._obj.value = exit_codes.pop(0)
        return 1

    kernel.GetExitCodeProcess.side_effect = get_exit_code
    kernel.TerminateProcess.return_value = 0
    mocker.patch("core.process_control.ctypes.WinDLL", return_value=kernel)
    mocker.patch("core.process_control.ctypes.get_last_error", return_value=5)
    ProcessControl.terminate(1234, 1.0)
