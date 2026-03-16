import sys

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QStyleFactory
)
from PySide6.QtGui import (
    QPalette, QColor
)
from PySide6.QtCore import Qt

# ===================================================================
# ui
from ui.main_window import InstructionXMainWindow

# ===================================================================
# 自定义工具
from utils import set_light_theme
from utils.logging_tools import LoggerManager, get_name

# ===================================================================
# 后台任务
from core.task import BackgroundTaskManager


def main():
    # 创建应用实例
    application = QApplication(sys.argv)
    
    # 设置应用名称
    application.setApplicationName("InstructionX - CE")
    application.setOrganizationName("LumenThread")
    
    # 设置浅色主题
    set_light_theme(application)

    # 初始化日志管理器
    logger = LoggerManager()
    logger.info(get_name(), '程序启动')

    # 创建并显示主窗口
    main_window = InstructionXMainWindow()
    main_window.show()
    
    # 强制立即处理事件，显示启动画面
    application.processEvents()
    
    # 运行应用
    result = application.exec()

    application.closeAllWindows()

    # 关闭后台任务管理器
    if BackgroundTaskManager._instance is not None:
        BackgroundTaskManager._instance.shutdown()

    sys.exit(result)

if __name__ == "__main__":
    main()
    