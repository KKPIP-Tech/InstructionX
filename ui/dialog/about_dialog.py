"""
关于对话框
显示软件 Logo、名称、版本号、版权信息
"""
import os

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont

from core.version import get_instructionx_version_display


def _get_logo_path():
    """获取 logo 图片路径"""
    # 先检查 ui 目录
    ui_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(ui_dir, "logo.png")
    if os.path.exists(path):
        return path
    # 备用：检查当前目录
    path = os.path.join(os.path.dirname(__file__), "..", "logo.png")
    if os.path.exists(path):
        return os.path.abspath(path)
    return ""


class AboutDialog(QDialog):
    """关于对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        self.setFixedSize(400, 350)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
        )

        self._init_ui()

    def _init_ui(self):
        """初始化界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(30, 40, 30, 40)

        # Logo
        logo_label = QLabel()
        logo_label.setFixedSize(128, 128)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setScaledContents(False)
        logo_path = _get_logo_path()
        pixmap = QPixmap(logo_path) if logo_path else QPixmap()

        if not pixmap.isNull():
            scaled = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_label.setPixmap(scaled)
        else:
            logo_label.setText("Logo")
            logo_label.setStyleSheet("QLabel { color: #666666; }")

        # 用水平布局让 Logo 居中
        logo_container = QHBoxLayout()
        logo_container.addStretch()
        logo_container.addWidget(logo_label)
        logo_container.addStretch()
        layout.addLayout(logo_container)

        # 软件名称
        name_label = QLabel("InstructionX - CE")
        name_font = QFont()
        name_font.setPointSize(16)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        # 版本号
        version_label = QLabel(get_instructionx_version_display())
        version_font = QFont()
        version_font.setPointSize(9)
        version_label.setFont(version_font)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setProperty("muted", "true")
        version_label.style().unpolish(version_label)
        version_label.style().polish(version_label)
        layout.addWidget(version_label)

        # 版权信息
        copyright_label = QLabel("© 2025-2026 dakuang. 保留所有权利。")
        copyright_font = QFont()
        copyright_font.setPointSize(8)
        copyright_label.setFont(copyright_font)
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copyright_label.setProperty("muted", "true")
        copyright_label.style().unpolish(copyright_label)
        copyright_label.style().polish(copyright_label)
        layout.addWidget(copyright_label)

        # 专有软件声明
        proprietary_label = QLabel("Proprietary software.\nCommercial use requires authorization if thresholds are exceeded.")
        proprietary_font = QFont()
        proprietary_font.setPointSize(7)
        proprietary_label.setFont(proprietary_font)
        proprietary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        proprietary_label.setProperty("muted", "true")
        proprietary_label.style().unpolish(proprietary_label)
        proprietary_label.style().polish(proprietary_label)
        proprietary_label.setWordWrap(True)
        layout.addWidget(proprietary_label)

        layout.addStretch()