import sys
import traceback
from pathlib import Path

# 必须为第一行业务 import：扩展 sys.path 使 InstructionX_UIKit 以顶层包可导入
import ui.uikit_bootstrap  # noqa: F401

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface

# ===================================================================
# ui
from ui.main_window import InstructionXMainWindow
from ui.uikit_theme import apply_uikit_theme

from utils.gc_main_thread import MainThreadGcGuard
from utils.logging_tools import LoggerManager, get_name
from utils.macos_dock_icon import set_macos_dock_icon

# ===================================================================
# 应用生命周期（统一关闭外部服务、插件、任务和存储）
from core.application_lifecycle import ApplicationLifecycle, LifecycleServices

# ===================================================================
# i18n（界面语言）
from core.i18n import get_language_manager


def main():
    # 图形 API 统一（必须在 QApplication 创建之前设置）：
    # 主窗口预热的蓝图 GL 视口（QOpenGLWidget）会把顶层窗口合成锁定为 OpenGL，
    # 而 UIKit Mermaid 交互查看器基于 QWebEngineView（Qt Quick RHI，Windows 默认 D3D11）；
    # 同一顶层窗口混用两种图形 API 会刷 "QQuickWidget: Failed to get a QRhi" 且窗口闪烁，
    # 因此统一顶层窗口图形 API 为 OpenGL（与上游 UIKit demo 入口一致）。
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)

    # 创建应用实例
    application = QApplication(sys.argv)

    # 托盘模式前置条件：关闭「最后一个窗口关闭即退出」的隐式链路，
    # 退出时机完全由代码显式控制（主窗口 closeEvent / 托盘菜单「退出」）
    application.setQuitOnLastWindowClosed(False)
    
    # 设置应用名称
    application.setApplicationName("InstructionX - CE")
    application.setOrganizationName("KKPIP-Tech")
    
    # 设置 UIKit 全局主题（auto：自动检测系统主题）
    apply_uikit_theme(application)

    # 提前初始化语言管理器：加载当前语言配置与语言文件缓存，
    # 确保主窗口构造期间全部 tr() 取词就绪（与主题初始化平级）
    get_language_manager()

    # 初始化日志管理器
    logger = LoggerManager()
    logger.info(get_name(), '程序启动')

    # 未捕获异常兜底：先写入日志再走默认行为（pythonw 下槽函数异常不再静默）
    def _excepthook(exc_type, exc_value, exc_tb):
        try:
            stack = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
            logger.critical(get_name(), f'未捕获异常:\n{stack}')
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    # 创建并显示主窗口
    main_window = InstructionXMainWindow()
    # 图标路径基于 main.py 所在目录推导，避免相对 CWD 失效
    main_window.setWindowIcon(QIcon(str(Path(__file__).resolve().parent / "ui" / "logo.ico")))
    main_window.show()
    
    # 强制立即处理事件，显示启动画面
    application.processEvents()

    # macOS：设置 Dock 栏应用图标（直接 python 运行时进程属 Python.app，
    # Dock 默认显示 Python 图标；其他平台为空操作）
    set_macos_dock_icon(Path(__file__).resolve().parent / "ui" / "logo.png")

    # 主线程GC守卫：把循环 GC 收敛到 GUI 线程，避免后台线程回收 Qt/PySide
    # 对象导致原生崩溃（2026-11-04 paint 0xC0000005 现场：崩溃线程在后台
    # Garbage-collecting，详见 docs/utils/gc-main-thread.md）。只接管循环垃圾，
    # 引用计数回收不受影响；若长测仍闪退需按该文档采集原生 dump 再定位。
    gc_guard = MainThreadGcGuard(application)
    gc_guard.install()

    # 运行应用
    result = application.exec()
    gc_guard.shutdown()

    # 先停止外部服务和任务并冲刷存储，最后释放 UI，统一记录关闭结果
    services = LifecycleServices(close_ui=application.closeAllWindows)
    shutdown_report = ApplicationLifecycle(services).shutdown()
    if not shutdown_report.success:
        logger.warning(get_name(), f'应用关闭未全部完成: {shutdown_report}')

    sys.exit(result)

if __name__ == "__main__":
    main()
    