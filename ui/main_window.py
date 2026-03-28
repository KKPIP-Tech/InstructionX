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
    QFileDialog, QMessageBox, QDialog, QPushButton, QLabel, QFrame
)
from PySide6.QtGui import (
    QAction, QIcon
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
from core.plugin.manager import PluginManager


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

        # 设置初始窗口大小
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)

        self._create_menus()
        self._create_main_layout()

    # ===============================================================
    # GUI 界面
    def _create_menus(self) -> None:
        """
        创建菜单栏

        包含文件、编辑、用户中心、帮助等菜单项。
        """

        # -------------------------------------------------
        # 文件
        menu_file = self.menuBar().addMenu("文件")

        # 加载录制文件动作 - 使用新的安全方法
        menu_file_load_action = QAction("加载录制文件", self)
        menu_file_load_action.setShortcut("Ctrl+Shift+L")
        menu_file.addAction(menu_file_load_action)

        # -------------------------------------------------
        # 编辑
        menu_edit = self.menuBar().addMenu("编辑")

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
        menu_user = self.menuBar().addMenu("用户中心")

        # -------------------------------------------------
        # 帮助
        menu_help = self.menuBar().addMenu("帮助")

        # 关于软件
        menu_help_about_action = QAction("关于", self)
        # menu_help_about_action.setShortcut()
        menu_help.addAction(menu_help_about_action)


    def _create_main_layout(self) -> None:
        """
        创建主布局

        初始化插件管理器，加载插件，创建技能面板和工作区。
        """

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 使用垂直布局：工具栏在上，工作区在下
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 初始化插件管理器
        self.plugin_manager = PluginManager()
        self.plugin_manager.load_plugins()

        # 应用自定义插件顺序
        self.plugin_manager.apply_custom_order()

        # 创建并添加 SkillsPanel（固定高度）
        self.skills_panel = SkillsPanel(central_widget)
        self.skills_panel.set_plugin_manager(self.plugin_manager)
        self.skills_panel.load_skills_from_manager()
        self.skills_panel.setMaximumHeight(150)  # 设置最大高度
        self.skills_panel.setMinimumHeight(120)  # 设置最小高度
        main_layout.addWidget(self.skills_panel)

        # 添加分割线
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        separator.setStyleSheet("""
            QFrame {
                background-color: #CCCCCC;
                max-height: 2px;
                min-height: 2px;
            }
        """)
        main_layout.addWidget(separator)

        # 创建工作区（可伸缩）
        self.work_area = WorkArea(central_widget)
        main_layout.addWidget(self.work_area.get_widget(), stretch=1)

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
            error_label.setStyleSheet("color: red;")
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
