from PySide6.QtWidgets import QApplication, QStyleFactory

from PySide6.QtGui import QPalette, QColor

def set_light_theme(app: QApplication) -> None:
    """
    设置浅色主题
    """
    # 设置为 Fusion 样式，这是一种跨平台的自定义样式
    app.setStyle(QStyleFactory.create("Fusion"))
    
    # 创建浅色调色板
    palette = QPalette()
    
    # 设置窗口背景色为白色
    palette.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
    
    # 设置窗口文本颜色为深灰色
    palette.setColor(QPalette.ColorRole.WindowText, QColor(0, 0, 0))
    
    # 设置基础背景色为浅灰白色
    palette.setColor(QPalette.ColorRole.Base, QColor(245, 245, 245))
    
    # 设置基础文本颜色为深灰色
    palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    
    # 设置按钮背景色为浅灰色
    palette.setColor(QPalette.ColorRole.Button, QColor(240, 240, 240))
    
    # 设置按钮文本颜色为深灰色
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(0, 0, 0))
    
    # 设置高亮背景色（选中项）为浅蓝色
    palette.setColor(QPalette.ColorRole.Highlight, QColor(76, 163, 255))
    
    # 设置高亮文本颜色（选中项文本）为白色
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    
    # 应用调色板
    app.setPalette(palette)