"""真实窗口 UIKit 后端冒烟；不使用 offscreen 结果冒充真实呈现。"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sys

from PIL import ImageGrab
import ui.uikit_bootstrap  # noqa: F401
from PySide6.QtCore import QDeadlineTimer, Qt
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from InstructionX_UIKit.blueprint import BlueprintCanvas, BlueprintGraph
from InstructionX_UIKit.charts import ChartWidget
from ui.rhi_surface import prepare_rhi_surface
from ui.usage_panel.trend_chart import TrendPanel

MIN_DISTINCT_COLORS = 3
SAMPLE_GRID_SIZE = 32


class _Rect(ctypes.Structure):
    """Win32 客户区矩形。"""

    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


def make_line_chart() -> ChartWidget:
    """构造完成态折线图。"""
    chart = ChartWidget()
    chart.set_option({
        "xAxis": {"type": "category", "data": ["A", "B", "C"]},
        "series": [{"type": "line", "name": "信号", "data": [1, 3, 2]}],
    })
    chart.anim.stop()
    chart.anim.set_progress(1.0)
    return chart


def sync_viewport(owner) -> None:
    """强制同步 Chart 或 Blueprint 的内部视口并处理 Qt 事件。"""
    sync = getattr(owner._viewport, "_sync_now", None)
    if callable(sync):
        sync()
    else:
        layout = getattr(owner, "_layout_all", None)
        if callable(layout):
            layout(force=True)
        owner._viewport.update()
    QApplication.processEvents()


def backend_name(owner) -> str:
    """返回用于验收断言的实际后端名称。"""
    viewport = owner._viewport
    active_backend = getattr(viewport, "active_backend", None)
    return active_backend() if callable(active_backend) else type(viewport).__name__


def distinct_colors(image) -> int:
    """抽样统计非空白截图颜色数，防止空白图假通过。"""
    colors = set()
    x_step = max(1, image.width() // SAMPLE_GRID_SIZE)
    y_step = max(1, image.height() // SAMPLE_GRID_SIZE)
    for x in range(0, image.width(), x_step):
        for y in range(0, image.height(), y_step):
            colors.add(image.pixelColor(x, y).rgba())
    return len(colors)


def grab_native_window(window) -> QImage:
    """抓取 Win32 实际客户区，包含原生 Scene Graph 子窗口。"""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
    user32.GetClientRect.restype = wintypes.BOOL
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    rect = _Rect()
    origin = wintypes.POINT(0, 0)
    hwnd = int(window.winId())
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError(ctypes.get_last_error())
    image = ImageGrab.grab(
        bbox=(origin.x + rect.left, origin.y + rect.top,
              origin.x + rect.right, origin.y + rect.bottom), all_screens=True)
    image = image.convert("RGBA")
    result = QImage(image.tobytes("raw", "RGBA"), image.width, image.height,
                    image.width * 4, QImage.Format_RGBA8888)
    if result.isNull():
        raise AssertionError("原生窗口屏幕抓取为空")
    return result.copy()


def capture_window(window) -> QImage:
    """Windows 使用原生客户区抓图，其他平台使用 Qt 抓图。"""
    return grab_native_window(window) if sys.platform == "win32" else window.grab().toImage()


def build_window(scope: str):
    """创建待测窗口与 Chart / Blueprint / TrendPanel 所有者列表。"""
    window = QWidget()
    window.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    prepare_rhi_surface(window)
    layout = QVBoxLayout(window)
    chart = make_line_chart()
    blueprint = BlueprintCanvas(BlueprintGraph())
    owners = [chart, blueprint]
    layout.addWidget(chart)
    layout.addWidget(blueprint)
    if scope == "all":
        trend = TrendPanel()
        trend.update_series([])
        layout.addWidget(trend)
        owners.append(trend._chart)
    window.resize(1000, 800)
    return window, owners


STABLE_TIMEOUT_MS = 5000


def wait_for_stable_frames(owners) -> None:
    """按条件等待缩放预览与入场动画结束，超时视为渲染异常。"""
    deadline = QDeadlineTimer(STABLE_TIMEOUT_MS)
    while any(
        getattr(owner, "_resize_preview", None) is not None
        and owner._resize_preview.active
        or getattr(owner, "anim", None) is not None and owner.anim.is_running()
        for owner in owners
    ):
        assert not deadline.hasExpired(), "等待最终帧超时"
        QTest.qWait(10)


def validate_trend_tooltip(chart: ChartWidget) -> None:
    """验证内置热力图命中后 Tooltip 显示日期而非空系列名。"""
    chart._layout_all(force=True)
    renderer = chart.series_renderers[0]
    assert renderer._cells, "趋势图没有可命中的日期单元格"
    cell = renderer._cells[0]
    hit = renderer.hit_test(cell["rect"].center())
    assert hit is not None and hit["series"] == "", hit
    chart._tooltip_item(cell["rect"].center())
    assert chart.tooltip.active
    assert chart.tooltip._lines[0][1] == cell["label"], chart.tooltip._lines


def validate_backends(owners, backend: str) -> list[str]:
    """同步全部视口并严格核对实际后端。"""
    for owner in owners:
        sync_viewport(owner)
    wait_for_stable_frames(owners)
    actual = [backend_name(owner) for owner in owners]
    if backend == "raster":
        assert all(name == "_RasterViewport" for name in actual), actual
        return actual
    expected = "canvas-widget" if backend == "canvas" else "rhi"
    assert all(name == expected for name in actual), actual
    return actual


def save_report(window, owners, args, actual: list[str]) -> Path:
    """保存原生截图与机器可读验收报告。"""
    output = Path("temp") / f"uikit-{args.scope}-{args.backend}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    image = capture_window(window)
    colors = distinct_colors(image)
    assert not image.isNull() and colors >= MIN_DISTINCT_COLORS, colors
    assert image.save(str(output))
    for owner in owners:
        assert not owner.grab().toImage().isNull(), backend_name(owner)
    report = {
        "status": "PASS", "scope": args.scope, "requested_backend": args.backend,
        "actual_backends": actual, "graphics_api": str(QQuickWindow.graphicsApi()),
        "distinct_colors": colors, "screenshot": str(output),
        "capture_method": "win32-client" if sys.platform == "win32" else "qt-widget",
    }
    report_path = output.with_suffix(".json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return report_path


def main() -> int:
    """检查真实后端并保存窗口截图和机器可读结果到 temp。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("core", "all"), default="core")
    parser.add_argument("--backend", choices=("canvas", "rhi", "raster"), default="canvas")
    args = parser.parse_args()
    os.environ["UIKIT_CHART_BACKEND"] = args.backend
    os.environ["UIKIT_BLUEPRINT_BACKEND"] = args.backend
    app = QApplication([])
    window, owners = build_window(args.scope)
    window.show()
    window.raise_()
    window.activateWindow()
    app.processEvents()
    try:
        actual = validate_backends(owners, args.backend)
        if args.scope == "all":
            validate_trend_tooltip(owners[-1])
        save_report(window, owners, args, actual)
        return 0
    finally:
        window.close()
        app.processEvents()


if __name__ == "__main__":
    raise SystemExit(main())
