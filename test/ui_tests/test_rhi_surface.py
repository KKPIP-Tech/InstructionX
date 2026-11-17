"""RHI Surface 匹配与旧 GL 清理测试。"""
from pathlib import Path

from PySide6.QtGui import QSurface
from PySide6.QtQuick import QSGRendererInterface

from ui.rhi_surface import prepare_rhi_surface


def test_software_platform_is_noop(mocker):
    """offscreen 不创建原生句柄。"""
    app = mocker.MagicMock()
    app.platformName.return_value = "offscreen"
    mocker.patch("ui.rhi_surface.QGuiApplication.instance", return_value=app)
    window = mocker.MagicMock()
    prepare_rhi_surface(window)
    window.winId.assert_not_called()


def test_cocoa_surface_is_not_forced(mocker):
    """macOS Cocoa 顶层交给 Qt 自管理，避免离屏 RHI 帧崩溃。"""
    app = mocker.MagicMock()
    app.platformName.return_value = "cocoa"
    mocker.patch("ui.rhi_surface.QGuiApplication.instance", return_value=app)
    window = mocker.MagicMock()
    prepare_rhi_surface(window)
    window.winId.assert_not_called()
    window.windowHandle.assert_not_called()


def test_d3d11_surface_is_selected_before_show(mocker):
    """Qt 自动选择 D3D11 时顶层 Surface 同步为 Direct3DSurface。"""
    app = mocker.MagicMock()
    app.platformName.return_value = "windows"
    mocker.patch("ui.rhi_surface.QGuiApplication.instance", return_value=app)
    mocker.patch(
        "ui.rhi_surface.QQuickWindow.graphicsApi",
        return_value=QSGRendererInterface.GraphicsApi.Direct3D11,
    )
    window = mocker.MagicMock()
    handle = window.windowHandle.return_value
    handle.surfaceType.return_value = QSurface.OpenGLSurface
    prepare_rhi_surface(window)
    window.winId.assert_called_once_with()
    handle.setSurfaceType.assert_called_once_with(QSurface.Direct3DSurface)


def test_framework_has_no_legacy_gl_entrypoints():
    """框架入口不再强制 OpenGL 或引用已删除的 gl_available。"""
    main_source = Path("main.py").read_text(encoding="utf-8")
    window_source = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "setGraphicsApi" not in main_source
    assert "gl_available" not in window_source
    assert "_prewarm_blueprint_viewport" not in window_source
