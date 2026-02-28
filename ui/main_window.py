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
from core.plugin.manager import PluginManager


class InstructionXMainWindow(QMainWindow):
    
    def __init__(self):
        
        super().__init__()
        
        # 设置初始窗口大小
        self.setMinimumSize(800, 600)
        self.resize(1024, 768)
        
        self._create_menus()
        self._create_main_layout()
        
    # ===============================================================
    # GUI 界面
    def _create_menus(self) -> None:
        
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
        self.work_area = QWidget()
        self.work_layout = QVBoxLayout(self.work_area)
        self.work_layout.setContentsMargins(0, 0, 0, 0)
        
        # 初始显示的占位标签
        self.work_placeholder = QLabel("点击上方技能按钮，在此处显示插件功能")
        self.work_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.work_placeholder.setStyleSheet("""
            QLabel {
                color: #999999;
                font-size: 14px;
            }
        """)
        self.work_layout.addWidget(self.work_placeholder)
        
        main_layout.addWidget(self.work_area, stretch=1)  # 工作区可伸缩
        
        # 连接技能点击信号
        self.skills_panel.skill_clicked.connect(self._on_skill_clicked)
    
    def _on_skill_clicked(self, plugin):
        """
        处理技能按钮点击事件
        在工作区显示插件的 widget
        """
        # 清空工作区
        self._clear_work_area()
        
        # 获取插件的 widget 并显示在工作区
        plugin_widget = plugin.get_widget(parent=self.work_area)
        if plugin_widget:
            self.work_layout.addWidget(plugin_widget)
        else:
            # 如果插件 widget 创建失败，显示错误信息
            error_label = QLabel(f"无法加载插件：{plugin.plugin_name}")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            error_label.setStyleSheet("color: red;")
            self.work_layout.addWidget(error_label)
    
    def _clear_work_area(self):
        """清空工作区"""
        while self.work_layout.count():
            item: Optional[QLayoutItem] = self.work_layout.takeAt(0)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            # 清理 item 对象
            if item:
                del item
        
        # 清空工作区时，取消所有插件按钮的高亮状态
        self.skills_panel.clear_active_state()
