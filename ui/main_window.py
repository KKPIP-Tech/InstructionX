"""
主窗口模块

定义应用程序主窗口类，包含菜单栏、主布局和插件系统集成。
"""

import os
from copy import deepcopy
import time
from typing import Optional, Any, List, Dict
from enum import Enum

import cv2
import numpy as np

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter,
    QHBoxLayout, QVBoxLayout, QLayoutItem,
    QFileDialog, QMessageBox, QDialog, QPushButton, QLabel
)
from PySide6.QtGui import (
    QAction, QIcon, QCursor, QMouseEvent
)
from PySide6.QtCore import (
    Qt, QDateTime, QThread,
    Signal, Slot
)

# ===================================================================
# 自定义工具
from ui.skills_panel.panel import SkillsPanel
from ui.dialog.plugin_order_dialog import PluginOrderDialog
from ui.work_area.work_area import WorkArea
from ui.title_bar import CustomTitleBar
from core.plugin.manager import PluginManager
from utils.style_qss import get_style_qss


class InstructionXMainWindow(QMainWindow):
    """
    应用程序主窗口

    采用单窗口多面板布局：
    - 顶部：菜单栏
    - 左侧：技能面板（插件选择器）
    - 右侧：工作区（显示激活的插件界面）

    负责初始化插件系统、响应技能点击、管理工作区内容。
    """

    def __init__(self):
        """
        初始化主窗口

        设置窗口尺寸，创建菜单栏，初始化插件系统。
        """

        super().__init__()

        # 设置无边框窗口
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # 设置初始窗口大小
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)

        # 获取当前主题
        self._style_qss = get_style_qss()
        self._current_theme = self._style_qss.theme()

        # 创建主容器（用于圆角效果）
        self._container = QWidget()
        self._container.setObjectName("mainContainer")
        self.setCentralWidget(self._container)

        # 主布局
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(8, 0, 8, 8)
        self._container_layout.setSpacing(0)

        # 创建自定义标题栏
        self._title_bar = CustomTitleBar(self)
        self._container_layout.addWidget(self._title_bar)

        # 创建菜单栏并移到标题栏
        self._create_menus()

        # 创建主布局内容
        self._create_main_layout()

        # 应用容器样式
        self._update_container_style()

        # 边缘 resize 相关变量
        self._resize_margin = 8  # 边缘检测区域宽度
        self._resize_dir = None  # 当前 resize 方向
        self._resize_start = None  # resize 起始位置和窗口大小

    # ===============================================================
    # GUI 界面
    def _create_menus(self) -> None:
        """
        创建菜单栏

        包含文件、编辑、用户中心、帮助等菜单项。
        菜单栏将移动到自定义标题栏中。
        """

        # 获取原生菜单栏并移到自定义标题栏
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)
        self._title_bar.set_menu_bar(menu_bar)

        # -------------------------------------------------
        # 文件
        menu_file = menu_bar.addMenu("文件")

        # 加载录制文件动作 - 使用新的安全方法
        menu_file_load_action = QAction("加载录制文件", self)
        menu_file_load_action.setShortcut("Ctrl+Shift+L")
        menu_file.addAction(menu_file_load_action)

        # -------------------------------------------------
        # 编辑
        menu_edit = menu_bar.addMenu("编辑")

        # 插件排序
        menu_edit_plugin_order_action = QAction("插件排序", self)
        menu_edit_plugin_order_action.setShortcut("Ctrl+P")
        menu_edit_plugin_order_action.triggered.connect(self._open_plugin_order_dialog)
        menu_edit.addAction(menu_edit_plugin_order_action)

        # LLM 设置
        menu_edit_llm_settings_action = QAction("LLM 设置", self)
        menu_edit_llm_settings_action.setShortcut("Ctrl+L")
        menu_edit_llm_settings_action.triggered.connect(self._open_llm_settings_dialog)
        menu_edit.addAction(menu_edit_llm_settings_action)

        # -------------------------------------------------
        # 用户中心
        menu_user = menu_bar.addMenu("用户中心")

        # -------------------------------------------------
        # 帮助
        menu_help = menu_bar.addMenu("帮助")

        # 关于软件
        menu_help_about_action = QAction("关于", self)
        menu_help_about_action.triggered.connect(self._open_about_dialog)
        menu_help.addAction(menu_help_about_action)


    def _create_main_layout(self) -> None:
        """
        创建主布局

        初始化插件管理器，加载插件，创建技能面板和工作区。
        """

        # 创建内容布局（用于技能面板和工作区）
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(5)
        self._container_layout.addLayout(content_layout)

        # 初始化插件管理器
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

        # 应用自定义插件顺序
        self.plugin_manager.apply_custom_order()

        # 创建并添加 SkillsPanel（固定高度）
        self.skills_panel = SkillsPanel(self._container)
        self.skills_panel.set_plugin_manager(self.plugin_manager)
        self.skills_panel.load_skills_from_manager()
        self.skills_panel.setMaximumHeight(115)  # 设置最大高度
        self.skills_panel.setMinimumHeight(105)  # 设置最小高度
        content_layout.addWidget(self.skills_panel)

        # 创建工作区（可伸缩）
        self.work_area = WorkArea(self._container)
        content_layout.addWidget(self.work_area.get_widget(), stretch=1)

        # 设置清除高亮的回调
        self.work_area.set_clear_highlight_callback(self.skills_panel.clear_active_state)

        # 连接技能点击信号
        self.skills_panel.skill_clicked.connect(self._on_skill_clicked)

    def _on_skill_clicked(self, plugin):
        """
        处理技能按钮点击事件

        清除工作区并显示被点击插件的用户界面。
        注意：不清除按钮的高亮状态，以指示当前激活的插件。

        Args:
            plugin: 被点击的插件实例
        """
        # 清空工作区（不清除按钮高亮）
        self.work_area.clear_keep_highlight()

        # 获取插件的 widget 并显示在工作区
        plugin_widget = plugin.get_widget(parent=self.work_area.get_widget())
        if plugin_widget:
            self.work_area.add_widget(plugin_widget)
        else:
            # 如果插件 widget 创建失败，显示错误信息
            error_label = QLabel(f"无法加载插件：{plugin.plugin_name}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setProperty("error", "true")
            error_label.style().unpolish(error_label)
            error_label.style().polish(error_label)
            self.work_area.add_widget(error_label)

    def _open_plugin_order_dialog(self):
        """
        打开插件排序对话框

        用户保存排序后，重新加载技能面板以显示新的顺序。
        """
        dialog = PluginOrderDialog(self.plugin_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了保存，重新加载 skills panel
            self.skills_panel.load_skills_from_manager()

    def _open_about_dialog(self):
        """打开关于对话框"""
        from ui.dialog.about_dialog import AboutDialog
        dialog = AboutDialog(self)
        dialog.exec()

    def _open_llm_settings_dialog(self):
        """
        打开 LLM 设置对话框

        用户保存设置后，重新加载 LLM 提供商配置。
        """
        from ui.dialog.llm_settings_dialog import LLMSettingsDialog

        dialog = LLMSettingsDialog(self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了保存，重新加载 LLM Provider
            from core.llm.llm_provider import get_llm_provider
            get_llm_provider().reload_config()

    def _update_container_style(self):
        """更新容器样式（圆角/最大化状态），适配当前主题"""
        colors = self._style_qss.colors()
        window_bg = colors.get('window', '#202020')
        border_color = colors.get('borderLight', '#3C3C3C')

        if self.isMaximized():
            # 最大化时移除圆角
            self._container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {window_bg};
                    border-radius: 0px;
                }}
            """)
        else:
            # 还原时显示圆角
            self._container.setStyleSheet(f"""
                QWidget#mainContainer {{
                    background-color: {window_bg};
                    border-radius: 8px;
                    border: 1px solid {border_color};
                }}
            """)

    def changeEvent(self, event):
        """监听窗口状态变化，更新标题栏按钮"""
        if event.type() == event.Type.WindowStateChange:
            colors = self._style_qss.colors()
            window_bg = colors.get('window', '#202020')

            if self.isMaximized():
                self._title_bar.set_maximized(True)
                self._container.setStyleSheet(f"""
                    QWidget#mainContainer {{
                        background-color: {window_bg};
                        border-radius: 0px;
                    }}
                """)
            else:
                self._title_bar.set_maximized(False)
                border_color = colors.get('borderLight', '#3C3C3C')
                self._container.setStyleSheet(f"""
                    QWidget#mainContainer {{
                        background-color: {window_bg};
                        border-radius: 8px;
                        border: 1px solid {border_color};
                    }}
                """)
        super().changeEvent(event)

    # ===============================================================
    # 边缘 resize 功能
    def _get_resize_direction(self, pos: QMouseEvent) -> Optional[str]:
        """
        检测鼠标位置对应的 resize 方向

        Args:
            pos: 鼠标事件

        Returns:
            resize 方向字符串：'top', 'bottom', 'left', 'right',
            'top-left', 'top-right', 'bottom-left', 'bottom-right' 或 None
        """
        if self.isMaximized():
            return None

        margin = self._resize_margin
        x, y = pos.pos().x(), pos.pos().y()
        width = self.width()
        height = self.height()

        # 检测是否在边缘区域
        on_left = x < margin
        on_right = x > width - margin
        on_top = y < margin
        on_bottom = y > height - margin

        if on_top and on_left:
            return 'top-left'
        elif on_top and on_right:
            return 'top-right'
        elif on_bottom and on_left:
            return 'bottom-left'
        elif on_bottom and on_right:
            return 'bottom-right'
        elif on_top:
            return 'top'
        elif on_bottom:
            return 'bottom'
        elif on_left:
            return 'left'
        elif on_right:
            return 'right'
        return None

    def _get_resize_cursor(self, direction: Optional[str]) -> Qt.CursorShape:
        """根据 resize 方向获取对应的光标样式"""
        cursor_map = {
            'top': Qt.CursorShape.SizeVerCursor,
            'bottom': Qt.CursorShape.SizeVerCursor,
            'left': Qt.CursorShape.SizeHorCursor,
            'right': Qt.CursorShape.SizeHorCursor,
            'top-left': Qt.CursorShape.SizeFDiagCursor,
            'top-right': Qt.CursorShape.SizeBDiagCursor,
            'bottom-left': Qt.CursorShape.SizeBDiagCursor,
            'bottom-right': Qt.CursorShape.SizeFDiagCursor,
        }
        return cursor_map.get(direction, Qt.CursorShape.ArrowCursor)

    def mouseMoveEvent(self, event: QMouseEvent):
        """处理鼠标移动事件 - 边缘检测和 resize"""
        # 如果正在执行 resize 操作
        if self._resize_dir and event.buttons() == Qt.MouseButton.LeftButton:
            self._do_resize(event)
            return

        # 否则检测边缘位置
        direction = self._get_resize_direction(event)
        if direction:
            cursor = self._get_resize_cursor(direction)
            self.setCursor(QCursor(cursor))
            self._resize_dir = direction
        else:
            if self._resize_dir:
                self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
                self._resize_dir = None

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        """处理鼠标按下事件 - 开始 resize"""
        if event.button() == Qt.MouseButton.LeftButton:
            direction = self._get_resize_direction(event)
            if direction and not self.isMaximized():
                self._resize_dir = direction
                self._resize_start = {
                    'pos': event.globalPosition().toPoint(),
                    'geometry': self.geometry()
                }
                return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """处理鼠标释放事件 - 结束 resize"""
        if event.button() == Qt.MouseButton.LeftButton:
            self._resize_dir = None
            self._resize_start = None
            # 恢复默认光标
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

        super().mouseReleaseEvent(event)

    def _do_resize(self, event: QMouseEvent):
        """执行窗口 resize"""
        if not self._resize_start:
            return

        start_pos = self._resize_start['pos']
        start_geo = self._resize_start['geometry']
        current_pos = event.globalPosition().toPoint()

        delta = current_pos - start_pos
        direction = self._resize_dir

        new_x = start_geo.x()
        new_y = start_geo.y()
        new_width = start_geo.width()
        new_height = start_geo.height()

        # 根据方向调整窗口几何
        if 'left' in direction:
            new_x = start_geo.x() + delta.x()
            new_width = start_geo.width() - delta.x()
        if 'right' in direction:
            new_width = start_geo.width() + delta.x()
        if 'top' in direction:
            new_y = start_geo.y() + delta.y()
            new_height = start_geo.height() - delta.y()
        if 'bottom' in direction:
            new_height = start_geo.height() + delta.y()

        # 应用最小尺寸限制
        min_w = self.minimumWidth()
        min_h = self.minimumHeight()
        new_width = max(new_width, min_w)
        new_height = max(new_height, min_h)

        # 调整窗口位置和大小
        self.setGeometry(new_x, new_y, new_width, new_height)
