"""主窗口原生边框适配，避免 Windows 分层窗口与直接 RHI 的输入冲突。"""
import ctypes
from ctypes import wintypes
import logging
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_WINDOWS_11_BUILD = 22000
_FRAME_MARGIN_PX = 1
_SUCCESS = 0
_logger = logging.getLogger(__name__)


class _Margins(ctypes.Structure):
    """DwmExtendFrameIntoClientArea 使用的四边像素宽度。"""

    _fields_ = [
        ("left", ctypes.c_int), ("right", ctypes.c_int),
        ("top", ctypes.c_int), ("bottom", ctypes.c_int),
    ]


def _dwm_library():
    """声明本模块使用的两个 DWM 接口及参数类型。"""
    library = ctypes.WinDLL("dwmapi", use_last_error=True)
    library.DwmSetWindowAttribute.argtypes = [
        wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
    ]
    library.DwmSetWindowAttribute.restype = ctypes.c_long
    library.DwmExtendFrameIntoClientArea.argtypes = [
        wintypes.HWND, ctypes.POINTER(_Margins),
    ]
    library.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
    return library


def _check_dwm_result(operation: str, status: int) -> None:
    """DWM 装饰失败仅记录并保留可用窗口，不阻断业务界面。"""
    if status != _SUCCESS:
        _logger.warning("%s失败，HRESULT=0x%08X", operation, status & 0xFFFFFFFF)


def _apply_dwm_frame(hwnd: int) -> None:
    """为无边框窗口启用系统阴影，并在 Windows 11 请求圆角。"""
    library = _dwm_library()
    margins = _Margins(*([_FRAME_MARGIN_PX] * 4))
    _check_dwm_result(
        "启用主窗口系统阴影",
        library.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins)),
    )
    if sys.getwindowsversion().build < _WINDOWS_11_BUILD:
        return
    preference = wintypes.DWORD(_DWMWCP_ROUND)
    _check_dwm_result(
        "启用主窗口系统圆角",
        library.DwmSetWindowAttribute(
            hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(preference), ctypes.sizeof(preference),
        ),
    )


def prepare_native_window_frame(window: QWidget) -> None:
    """按平台准备主窗口宿主；Windows 使用非分层窗口和 DWM 装饰。

    Windows 的逐像素分层窗口会把新增透明区域的鼠标事件交给后台窗口；
    直接 Canvas/RHI 参与组合后，该分层区域可能停留在初始尺寸。这里在创建
    原生句柄前关闭顶层透明属性，其他平台不改变既有透明窗口路径。

    Args:
        window: 已设置无边框标志、尚未首次显示的顶层窗口。
    """
    app = QGuiApplication.instance()
    if app is None or app.platformName() != "windows":
        return
    window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
    _apply_dwm_frame(int(window.winId()))
