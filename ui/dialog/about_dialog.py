"""
关于对话框
显示软件 Logo、名称、版本号、版权信息
"""
import os

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QFont

from InstructionX_UIKit import T, set_property

from core.version import get_instructionx_version_display


def _get_logo_path():
    """获取 logo 图片路径（ui/logo.png，不存在时返回空字符串）"""
    ui_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(ui_dir, "logo.png")
    return path if os.path.exists(path) else ""


def _token_label(text: str, size_key: str, bold: bool = False) -> QLabel:
    """创建居中标签：字号取 UIKit 字阶令牌，语义色走全局 QSS role 属性"""
    label = QLabel(text)
    font = QFont()
    font.setPixelSize(T(size_key))
    font.setBold(bold)
    label.setFont(font)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if not bold:
        set_property(label, "role", "secondary")
    return label


class AboutDialog(QDialog):
    """关于对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("关于")
        # 使用最小尺寸而非固定尺寸，保证高 DPI/大字体下内容不被裁切
        self.setMinimumSize(400, 350)
        self.resize(400, 350)
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
            set_property(logo_label, "role", "tertiary")

        # 用水平布局让 Logo 居中
        logo_container = QHBoxLayout()
        logo_container.addStretch()
        logo_container.addWidget(logo_label)
        logo_container.addStretch()
        layout.addLayout(logo_container)

        # 软件名称
        layout.addWidget(_token_label("InstructionX - CE", "font.title.lg", bold=True))

        # 版本号
        layout.addWidget(_token_label(get_instructionx_version_display(), "font.sm"))

        # 版权信息
        layout.addWidget(_token_label("© 2025-2026 dakuang 版权所有，保留所有权利。", "font.xs"))

        # 专有软件声明（中文摘要 + 英文法律声明）
        proprietary_label = _token_label(
            "本软件为专有软件，商业使用超过阈值需获得授权。\n"
            "Proprietary software.\n"
            "Commercial use requires authorization if thresholds are exceeded.",
            "font.xs",
        )
        proprietary_label.setWordWrap(True)
        layout.addWidget(proprietary_label)

        layout.addStretch()
