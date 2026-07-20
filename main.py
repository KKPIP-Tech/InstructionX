import sys
import traceback
from pathlib import Path

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import (
    QApplication, QMessageBox, QStyleFactory
)
from PySide6.QtGui import (
    QPalette, QColor, QIcon
)
from PySide6.QtCore import Qt

# ===================================================================
# ui
from ui.main_window import InstructionXMainWindow

# ===================================================================
# 自定义工具
from utils.themes import set_style_qss_theme

from utils.logging_tools import LoggerManager, get_name

# ===================================================================
# 后台任务
from core.task import BackgroundTaskManager

# ===================================================================
# LLM 用量记录（退出时冲刷待写数据）
from core.llm.usage_record_store import get_usage_record_store


def main():
    # 创建应用实例
    application = QApplication(sys.argv)
    
    # 设置应用名称
    application.setApplicationName("InstructionX - CE")
    application.setOrganizationName("LumenThread")
    
    # 设置 StyleQSS 主题（自动检测系统主题）
    set_style_qss_theme(application)

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
    
    # 运行应用
    result = application.exec()

    application.closeAllWindows()

    # 关闭后台任务管理器
    if BackgroundTaskManager._instance is not None:
        BackgroundTaskManager._instance.shutdown()

    # 冲刷 LLM 用量记录防抖窗口内的待写数据，避免退出时丢失
    try:
        get_usage_record_store().flush()
    except Exception as flush_err:
        logger.warning(get_name(), f'LLM 用量记录冲刷失败: {flush_err}')

    sys.exit(result)

if __name__ == "__main__":
    main()
    