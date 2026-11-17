"""顶层窗口 RHI Surface 匹配，避免可见窗口被后续重型视口重建。"""
from PySide6.QtGui import QGuiApplication, QSurface
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QWidget

_SOFTWARE_PLATFORMS = ("offscreen", "minimal", "minimalegl")
_SURFACE_BY_API = {
    QSGRendererInterface.GraphicsApi.Direct3D11: QSurface.Direct3DSurface,
    QSGRendererInterface.GraphicsApi.Vulkan: QSurface.VulkanSurface,
    QSGRendererInterface.GraphicsApi.Metal: QSurface.MetalSurface,
    QSGRendererInterface.GraphicsApi.OpenGL: QSurface.OpenGLSurface,
}


def prepare_rhi_surface(window: QWidget) -> None:
    """在窗口标志确定后、首次显示前匹配 RHI Surface。

    Args:
        window: 尚未首次显示的顶层窗口；软件平台与未知图形 API 为空操作。
    """
    app = QGuiApplication.instance()
    if app is None or app.platformName() in _SOFTWARE_PLATFORMS:
        return
    surface = _SURFACE_BY_API.get(QQuickWindow.graphicsApi())
    if surface is None:
        return
    window.winId()
    handle = window.windowHandle()
    if handle is not None and handle.surfaceType() != surface:
        handle.setSurfaceType(surface)
