import sys

# ===================================================================
# PySide 相关 
from PySide6.QtWidgets import (
    QApplication, QMessageBox
)

from ui.main_window import InstructionXMainWindow

def main():
    # 创建应用实例
    application = QApplication(sys.argv)
    
    # 设置应用名称
    application.setApplicationName("InstructionX")
    application.setOrganizationName("LumenThread")
    
    # 创建并显示主窗口  # 新增代码
    main_window = InstructionXMainWindow()
    main_window.show()
    
    # 强制立即处理事件，显示启动画面
    application.processEvents()
    
    # 运行应用
    result = application.exec()
    
    application.closeAllWindows()
    
    sys.exit(result)

if __name__ == "__main__":
    main()
    