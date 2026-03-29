"""
自定义标题栏模块

提供自定义标题栏，包含 Logo、标题、菜单栏和窗口控制按钮。
"""

import os
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenuBar, QApplication
from PySide6.QtCore import Qt, QPoint, Signal
from PySide6.QtGui import QMouseEvent, QPixmap


class CustomTitleBar(QWidget):
    """
    自定义标题栏

    包含：Logo、软件名称、菜单栏、窗口控制按钮（最小化/最大化/关闭）
    支持拖拽移动、双击最大化功能
    """

    # 信号：主题变更时通知主窗口更新样式
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self._drag_pos = None
        self._is_maximized = False

        self.setFixedHeight(40)
        self._setup_ui()

    def _setup_ui(self):
        """构建 UI 结构"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 0, 0)
        layout.setSpacing(0)

        # Logo
        self._logo = QLabel()
        self._logo.setObjectName("titleLogo")
        
        # 设置固定大小并加载 Logo 图片
        self._logo.setFixedSize(24, 24)
        logo_path = os.path.join(os.path.dirname(__file__), "logo.png")
        if os.path.exists(logo_path):
            # 使用 border-image 设置图片，确保完整显示且缩放正确
            self._logo.setStyleSheet(f"""
                QLabel#titleLogo {{
                    border-image: url({logo_path.replace("\\", "/")}) 0 0 0 0 stretch stretch;
                    background-color: transparent;
                }}
            """)
        
        self._logo.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 软件名称 - 从 QApplication 获取
        app_name = "InstructionX"
        app = QApplication.instance()
        if app:
            app_name = app.applicationName() or app_name
        
        self._title = QLabel(app_name)
        self._title.setObjectName("titleText")
        self._title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._title.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self._title, alignment=Qt.AlignmentFlag.AlignVCenter)

        layout.addSpacing(20)

        # 菜单栏（占位，实际菜单从外部传入）
        self._menu_bar_placeholder = QWidget()
        self._menu_bar_placeholder.setObjectName("menuBarPlaceholder")
        layout.addWidget(self._menu_bar_placeholder, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 右侧弹性空间
        layout.addStretch()

        # 窗口控制按钮
        self._setup_window_controls(layout)

    def _setup_window_controls(self, layout):
        """创建窗口控制按钮"""
        controls = QWidget()
        controls.setObjectName("windowControls")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(0)

        w = 45
        h = 40
        
        # 最小化按钮
        self._btn_min = QPushButton("—")
        self._btn_min.setFixedSize(w, h)
        self._btn_min.setObjectName("btnMinimize")
        self._btn_min.clicked.connect(self._parent_window.showMinimized)
        controls_layout.addWidget(self._btn_min)

        # 最大化/还原按钮
        self._btn_max = QPushButton("□")
        self._btn_max.setFixedSize(w, h)
        self._btn_max.setObjectName("btnMaximize")
        self._btn_max.clicked.connect(self._toggle_maximize)
        controls_layout.addWidget(self._btn_max)

        # 关闭按钮
        self._btn_close = QPushButton("X")
        self._btn_close.setFixedSize(w, h)
        self._btn_close.setObjectName("btnClose")
        self._btn_close.clicked.connect(self._parent_window.close)
        controls_layout.addWidget(self._btn_close)

        layout.addWidget(controls, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _toggle_maximize(self):
        """切换最大化/还原"""
        if self._is_maximized:
            self._parent_window.showNormal()
            self._btn_max.setText("□")
            self._is_maximized = False
        else:
            self._parent_window.showMaximized()
            self._btn_max.setText("❐")
            self._is_maximized = True

    def set_menu_bar(self, menu_bar: QMenuBar):
        """设置外部传入的菜单栏"""
        # 从布局中移除占位 widget
        layout = self.layout()
        layout.removeWidget(self._menu_bar_placeholder)
        self._menu_bar_placeholder.deleteLater()
        self._menu_bar_placeholder = None

        # 添加外部菜单栏
        menu_bar.setObjectName("titleMenuBar")
        layout.insertWidget(3, menu_bar, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_maximized(self, maximized: bool):
        """设置最大化状态（供外部调用）"""
        self._is_maximized = maximized
        self._btn_max.setText("❐" if maximized else "□")

    # ========== 鼠标事件处理（窗口拖拽） ==========
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            delta = QPoint(event.globalPosition().toPoint() - self._drag_pos)
            self._parent_window.move(
                self._parent_window.x() + delta.x(),
                self._parent_window.y() + delta.y()
            )
            self._drag_pos = event.globalPosition().toPoint()

            # 拖动时从最大化恢复
            if self._is_maximized:
                self._parent_window.showNormal()
                self._btn_max.setText("□")
                self._is_maximized = False

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击标题栏切换最大化"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()