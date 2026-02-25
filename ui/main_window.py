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
    QHBoxLayout, QVBoxLayout,
    QFileDialog, QMessageBox
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


class InstructionXMainWindow(QMainWindow):
    
    def __init__(self):
        
        super().__init__()
        
        self._create_menus()
        self._create_main_layout()
        
    # ===============================================================
    # GUI 界面
    def _create_menus(self) -> None:
        
        # -------------------------------------------------
        # 文件
        menu_file = self.menuBar().addMenu("文件(&F)")
        
        # 加载录制文件动作 - 使用新的安全方法
        menu_file_load_action = QAction("加载录制文件", self)
        menu_file_load_action.setShortcut("Ctrl+Shift+L")
        menu_file.addAction(menu_file_load_action)
        
        # -------------------------------------------------
        # 传感器
        menu_sensor = self.menuBar().addMenu("传感器(&S)")
        
        menu_sensor_calibrate_color = QAction("色彩校准", self)
        menu_sensor_calibrate_color.setShortcut("Ctrl+Shift+C")
        menu_sensor.addAction(menu_sensor_calibrate_color)
        
        menu_sensor_find_mark_point = QAction("标定点校准", self)
        menu_sensor.addAction(menu_sensor_find_mark_point)
        
    
    def _create_main_layout(self) -> None:
        
        pass