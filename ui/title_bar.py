"""
自定义标题栏模块

提供自定义标题栏，包含 Logo、标题、菜单栏和窗口控制按钮。
"""

import os
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QMenuBar, QApplication, QMenu
)
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QMouseEvent, QPainter, QColor, QPen, QAction, QCursor

from core.i18n import tr, get_language_manager
from InstructionX_UIKit import T


class IconButton(QPushButton):
    """自定义图标按钮，使用 QPainter 绘制图标"""

    def __init__(self, icon_type, parent=None):
        super().__init__(parent)
        self._icon_type = icon_type  # 'minimize', 'maximize', 'restore', 'close'
        self._hover = False
        self.setFlat(True)
        self.setText("")

    def set_icon_type(self, icon_type: str):
        self._icon_type = icon_type
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        w, h = rect.width(), rect.height()
        cx, cy = w / 2, h / 2

        # 直接从 UIKit 主题令牌获取当前主题的前景色，确保与 QSS 完全一致
        text_color = QColor(T("color.text.primary"))

        if self._icon_type == 'close':
            if self._hover:
                painter.fillRect(rect, QColor("#E81123"))
            # 关闭按钮 hover 时强制白色，否则使用主题色
            icon_color = QColor("#FFFFFF") if self._hover else text_color
        else:
            if self._hover:
                # hover 背景：根据文字亮度选择对比色背景
                is_light_text = text_color.lightness() > 128
                hover_bg = QColor(255, 255, 255, 40) if is_light_text else QColor(0, 0, 0, 40)
                painter.fillRect(rect, hover_bg)
            icon_color = text_color

        pen = QPen(icon_color)
        # DPI 自适应线宽：100% 用 1.0px，150% 用 1.5px，200% 用 2.0px
        pen.setWidthF(max(1.0, 1.0 * self.devicePixelRatioF()))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self._icon_type == 'minimize':
            painter.drawLine(int(cx - 6), int(cy), int(cx + 6), int(cy))
        elif self._icon_type == 'maximize':
            painter.drawRect(int(cx - 5), int(cy - 5), 10, 10)
        elif self._icon_type == 'restore':
            painter.drawRect(int(cx - 3), int(cy - 5), 8, 8)
            painter.drawRect(int(cx - 5), int(cy - 3), 8, 8)
        elif self._icon_type == 'close':
            painter.drawLine(int(cx - 5), int(cy - 5), int(cx + 5), int(cy + 5))
            painter.drawLine(int(cx + 5), int(cy - 5), int(cx - 5), int(cy + 5))

        painter.end()


class CustomTitleBar(QWidget):
    """
    自定义标题栏

    包含：Logo、软件名称、菜单栏、窗口控制按钮（最小化/最大化/关闭）
    支持拖拽移动、双击最大化功能
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._parent_window = parent
        self._drag_pos = None
        self._is_maximized = False
        self._pre_max_geometry = None  # 记录最大化前的窗口几何信息
        self._menu_bar_inserted = False
        self._move_mode = False  # 右键菜单“移动”模式标志
        self._move_offset = None  # 移动模式下鼠标与窗口左上角的偏移

        self.setFixedHeight(40)
        self.setMouseTracking(True)
        self._setup_ui()

        # 首次填充文案，并跟随语言切换重设（Qt 对象销毁时自动断开连接）
        self._retranslate_ui()
        get_language_manager().language_changed.connect(self._retranslate_ui)

    def _retranslate_ui(self) -> None:
        """集中重设标题栏用户可见文案（窗口控制按钮 tooltip 与无障碍名称）"""
        self._btn_min.setToolTip(tr("title_bar", "tooltip.minimize"))
        self._btn_min.setAccessibleName(tr("title_bar", "accessibility.minimize"))
        self._btn_max.setToolTip(tr("title_bar", "tooltip.maximize_restore"))
        self._btn_max.setAccessibleName(tr("title_bar", "accessibility.maximize"))
        self._btn_close.setToolTip(tr("common", "close"))
        self._btn_close.setAccessibleName(tr("title_bar", "accessibility.close"))

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
        self._btn_min = IconButton('minimize', self)
        self._btn_min.setFixedSize(w, h)
        self._btn_min.setObjectName("btnMinimize")
        self._btn_min.clicked.connect(self._parent_window.showMinimized)
        controls_layout.addWidget(self._btn_min)

        # 最大化/还原按钮
        self._btn_max = IconButton('maximize', self)
        self._btn_max.setFixedSize(w, h)
        self._btn_max.setObjectName("btnMaximize")
        self._btn_max.clicked.connect(self._toggle_maximize)
        controls_layout.addWidget(self._btn_max)

        # 关闭按钮
        self._btn_close = IconButton('close', self)
        self._btn_close.setFixedSize(w, h)
        self._btn_close.setObjectName("btnClose")
        self._btn_close.clicked.connect(self._parent_window.close)
        controls_layout.addWidget(self._btn_close)

        layout.addWidget(controls, alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def _is_window_maximized_or_fullscreen(self):
        """检查窗口是否处于最大化或全屏状态"""
        return self._parent_window.isMaximized() or self._parent_window.isFullScreen()

    def _toggle_maximize(self):
        """切换最大化/还原/全屏"""
        if self._is_window_maximized_or_fullscreen():
            # 最大化与全屏统一通过 showNormal 还原
            self._parent_window.showNormal()
            self._btn_max.set_icon_type("maximize")
            self._is_maximized = False
        else:
            self._pre_max_geometry = self._parent_window.geometry()
            self._parent_window.showMaximized()
            self._btn_max.set_icon_type("restore")
            self._is_maximized = True

    def set_menu_bar(self, menu_bar: QMenuBar):
        """设置外部传入的菜单栏（幂等调用安全）"""
        if self._menu_bar_inserted:
            return
        
        self._menu_bar_inserted = True
        
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
        self._btn_max.set_icon_type("restore" if maximized else "maximize")
        if maximized and not self._pre_max_geometry:
            self._pre_max_geometry = self._parent_window.geometry()

    def _restore_from_maximized(self, global_pos: QPoint):
        """从最大化/全屏状态恢复，并保持鼠标相对位置"""
        if not self._is_window_maximized_or_fullscreen():
            return
        
        geo = self._parent_window.geometry()
        # 防止窗口宽度为 0 时除零
        ratio = (global_pos.x() - geo.x()) / geo.width() if geo.width() > 0 else 0.5
        
        self._parent_window.showNormal()
        self._btn_max.set_icon_type("maximize")
        self._is_maximized = False
        
        new_geo = self._parent_window.geometry()
        new_x = global_pos.x() - int(new_geo.width() * ratio)
        new_y = global_pos.y() - 20
        self._parent_window.move(new_x, new_y)

    # ========== 鼠标事件处理（窗口拖拽） ==========
    def mousePressEvent(self, event: QMouseEvent):
        # 移动模式下，鼠标按下即结束移动模式
        if self._move_mode:
            self._move_mode = False
            self._move_offset = None
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # 移动模式：无需按住鼠标，窗口跟随光标移动
        if self._move_mode and self._move_offset is not None:
            self._parent_window.move(QCursor.pos() - self._move_offset)
            super().mouseMoveEvent(event)
            return

        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            delta = QPoint(event.globalPosition().toPoint() - self._drag_pos)

            # 拖动时从最大化/全屏恢复
            if self._is_window_maximized_or_fullscreen():
                self._restore_from_maximized(event.globalPosition().toPoint())
                self._drag_pos = event.globalPosition().toPoint()
                super().mouseMoveEvent(event)
                return

            self._parent_window.move(
                self._parent_window.x() + delta.x(),
                self._parent_window.y() + delta.y()
            )
            self._drag_pos = event.globalPosition().toPoint()
            super().mouseMoveEvent(event)
            return

        # 不在拖拽时，让事件传播给父窗口，以便父窗口处理边缘 resize cursor
        event.ignore()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None
        # 传播事件给父窗口，确保父窗口能正确结束 edge-resize 并重置光标
        event.ignore()
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """双击标题栏切换最大化"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximize()
        super().mouseDoubleClickEvent(event)

    # ========== 右键系统菜单 ==========
    def contextMenuEvent(self, event):
        """右键标题栏显示系统菜单"""
        menu = QMenu(self)
        
        is_max = self._parent_window.isMaximized()
        
        restore_action = QAction(tr("title_bar", "context_menu.restore"), self)
        restore_action.setEnabled(is_max)
        restore_action.triggered.connect(self._parent_window.showNormal)
        menu.addAction(restore_action)

        move_action = QAction(tr("title_bar", "context_menu.move"), self)
        move_action.setEnabled(not is_max)
        # 移动功能：进入拖动模式，随后移动鼠标即可移动窗口，单击结束
        move_action.triggered.connect(self._start_system_move)
        menu.addAction(move_action)
        # 注：原“大小(S)”菜单项从未实现（窗口边缘拖拽已提供 resize 能力），已移除
        menu.addSeparator()

        minimize_action = QAction(tr("title_bar", "context_menu.minimize"), self)
        minimize_action.triggered.connect(self._parent_window.showMinimized)
        menu.addAction(minimize_action)

        maximize_action = QAction(tr("title_bar", "context_menu.maximize"), self)
        maximize_action.setEnabled(not is_max)
        maximize_action.triggered.connect(self._parent_window.showMaximized)
        menu.addAction(maximize_action)
        menu.addSeparator()

        close_action = QAction(tr("title_bar", "context_menu.close"), self)
        close_action.triggered.connect(self._parent_window.close)
        menu.addAction(close_action)
        
        menu.exec(event.globalPos())
    
    def _start_system_move(self):
        """进入移动模式：移动鼠标即拖动窗口，下次鼠标按下结束"""
        self._move_mode = True
        self._move_offset = QCursor.pos() - self._parent_window.frameGeometry().topLeft()

