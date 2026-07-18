# ui/dialog/llm_settings_components.py
"""LLM 设置中心自定义组件 - 支持深色模式."""

from typing import Optional, Callable, List, Dict, Any
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QToolButton, QMenu, QLineEdit,
    QGraphicsDropShadowEffect, QCheckBox, QDialog, QDialogButtonBox,
    QComboBox, QDoubleSpinBox, QScrollArea, QTextEdit, QGroupBox
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QPropertyAnimation, QEasingCurve, QRect
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPainterPath, QBrush, QPen

from utils.style_qss import get_style_qss


def get_current_colors() -> dict:
    """获取当前主题颜色."""
    return get_style_qss().colors()


# Provider 启用状态标签配色（区分明/暗主题背景）
STATUS_ENABLED_COLOR = "#16A34A"        # 启用：绿色文字
STATUS_ENABLED_BG_LIGHT = "#DCFCE7"    # 启用：浅色主题背景
STATUS_ENABLED_BG_DARK = "#166534"     # 启用：深色主题背景
STATUS_DISABLED_COLOR = "#9CA3AF"      # 未启用：灰色文字
STATUS_DISABLED_BG_LIGHT = "#F3F4F6"   # 未启用：浅色主题背景
STATUS_DISABLED_BG_DARK = "#4B5563"    # 未启用：深色主题背景

# 连接状态点配色
STATUS_CONNECTED = "#16A34A"      # 已连接：绿色
STATUS_FAILED = "#DC2626"         # 连接失败：红色
STATUS_UNKNOWN = "#9CA3AF"        # 未检测：灰色

# 模型能力标签配色
CAPABILITY_COLORS = {
    'vision': ('#EC4899', '#FCE7F3'),      # 视觉：粉色
    'web': ('#8B5CF6', '#EDE9FE'),          # 联网：紫色
    'reasoning': ('#F59E0B', '#FEF3C7'),    # 推理：橙色
    'tools': ('#8B5CF6', '#EDE9FE'),        # 工具：紫色
    'rerank': ('#6B7280', '#F3F4F6'),       # 重排：灰色
    'embedding': ('#10B981', '#D1FAE5'),    # 嵌入：绿色
    'chat': ('#3B82F6', '#DBEAFE'),         # 聊天：蓝色
    'thinking': ('#F59E0B', '#FEF3C7'),     # 思考：橙色
}


class OnOffSwitch(QWidget):
    """ON/OFF 切换开关 - 圆角矩形带文字标签."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(36, 18)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(36, 18)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = get_current_colors()
        bg_color = QColor(colors.get('controlFillHover', '#E0E0E0'))

        # 绘制背景轨道
        rect = QRect(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, self.height() / 2, self.height() / 2)

        if self._checked:
            painter.fillPath(path, QColor("#22C55E"))  # 绿色 ON
        else:
            painter.fillPath(path, QColor("#9CA3AF"))  # 灰色 OFF

        # 绘制滑块（圆形）
        knob_size = self.height() - 2
        knob_y = 1
        if self._checked:
            knob_x = self.width() - knob_size - 1
        else:
            knob_x = 1

        knob_rect = QRect(knob_x, knob_y, knob_size, knob_size)
        painter.setBrush(Qt.GlobalColor.white)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob_rect)

        # 绘制 ON/OFF 文字（在滑块另一侧）
        painter.setPen(Qt.GlobalColor.white)
        font = painter.font()
        font.setPointSize(7)
        font.setBold(True)
        painter.setFont(font)

        text = "ON" if self._checked else "OFF"
        if self._checked:
            # ON 文字在左侧
            text_rect = QRect(4, 0, self.width() - knob_size - 8, self.height())
        else:
            # OFF 文字在右侧
            text_rect = QRect(knob_size + 4, 0, self.width() - knob_size - 8, self.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.update()


class CircularToggleSwitch(QWidget):
    """圆形切换开关 - 仅滑块，无文字（用于右侧面板头部）."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(44, 24)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 绘制背景轨道
        rect = QRect(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, self.height() / 2, self.height() / 2)

        if self._checked:
            painter.fillPath(path, QColor("#22C55E"))  # 绿色 ON
        else:
            painter.fillPath(path, QColor("#D1D5DB"))  # 灰色 OFF

        # 绘制滑块（圆形，带边框）
        knob_size = self.height() - 4
        knob_y = 2
        if self._checked:
            knob_x = self.width() - knob_size - 2
        else:
            knob_x = 2

        knob_rect = QRect(knob_x, knob_y, knob_size, knob_size)
        painter.setBrush(Qt.GlobalColor.white)
        painter.setPen(QPen(QColor("#E5E7EB"), 1))
        painter.drawEllipse(knob_rect)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.update()


class SearchBox(QWidget):
    """搜索框组件."""

    textChanged = Signal(str)

    def __init__(self, placeholder: str = "搜索...", parent=None):
        super().__init__(parent)
        self._init_ui(placeholder)

    def _init_ui(self, placeholder: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        border_color = colors.get('border', '#CCCCCC')
        text_color = colors.get('textSecondary', '#999999')
        focus_color = colors.get('accent', '#4A90D9')

        self._edit = QLineEdit()
        self._edit.setPlaceholderText(placeholder)
        self._edit.setClearButtonEnabled(True)
        self._edit.textChanged.connect(self.textChanged.emit)
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {colors.get('textPrimary', '#333333')};
                background-color: {bg_color};
            }}
            QLineEdit:focus {{
                border-color: {focus_color};
            }}
        """)
        layout.addWidget(self._edit)

    def text(self) -> str:
        return self._edit.text()


class CapabilityTag(QLabel):
    """能力标签."""

    def __init__(self, capability: str, parent=None):
        super().__init__(capability, parent)
        fg, bg = CAPABILITY_COLORS.get(capability.lower(), ('#6B7280', '#F3F4F6'))
        self.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 500;
            }}
        """)


class ProviderListItemWidget(QWidget):
    """Provider 列表项自定义控件 - 圆形 Logo + ON/OFF 开关 + 状态指示."""

    toggled = Signal(bool)

    def __init__(self, name: str, logo_path: Optional[str], is_enabled: bool,
                 health_status: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._name = name
        self._logo_path = logo_path
        self._is_enabled = is_enabled
        self._health_status = health_status

        self.setFixedHeight(48)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        hover_color = colors.get('controlFillHover', '#F5F5F5')

        self.setStyleSheet(f"""
            QWidget#ProviderListItemWidget {{
                background-color: {bg_color};
                border-radius: 8px;
            }}
            QWidget#ProviderListItemWidget:hover {{
                background-color: {hover_color};
            }}
        """)
        self.setObjectName("ProviderListItemWidget")
        self._init_ui()

    def _init_ui(self):
        # 立即应用样式，避免延迟渲染
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')

        # 左侧 Logo - 圆形
        self._logo = QLabel()
        self._logo.setFixedSize(36, 36)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setStyleSheet("""
            QLabel {
                border-radius: 18px;
            }
        """)

        if self._logo_path and Path(self._logo_path).exists():
            pixmap = self._load_circular_pixmap(self._logo_path, 36)
            if not pixmap.isNull():
                self._logo.setPixmap(pixmap)
            else:
                self._set_logo_fallback()
        else:
            self._set_logo_fallback()
        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 中间名称
        self._name_label = QLabel(self._name)
        self._name_label.setStyleSheet(f"""
            QLabel {{
                color: {text_primary};
                font-size: 13px;
                font-weight: 500;
                background-color: transparent;
            }}
        """)
        layout.addWidget(self._name_label, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 右侧 ON/OFF 开关
        self._toggle = OnOffSwitch(self._is_enabled)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _load_circular_pixmap(self, path: str, size: int) -> QPixmap:
        """加载并裁剪为圆形图片."""
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return QPixmap()

        scaled = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )

        circular_pixmap = QPixmap(size, size)
        circular_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(circular_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2

        clip_path = QPainterPath()
        clip_path.addEllipse(0, 0, size, size)
        painter.setClipPath(clip_path)

        painter.drawPixmap(x, y, scaled.width(), scaled.height(), scaled)
        painter.end()

        return circular_pixmap

    def _set_logo_fallback(self):
        """无 Logo 时显示首字母 - 圆形."""
        colors = get_current_colors()
        accent = colors.get('accent', '#4A90D9')

        self._logo.setText(self._name[:1].upper() if self._name else "?")
        self._logo.setStyleSheet(f"""
            QLabel {{
                background-color: {accent};
                border-radius: 18px;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }}
        """)

    def _on_toggled(self, checked: bool):
        """开关切换事件."""
        self._is_enabled = checked
        self.toggled.emit(checked)

    def set_enabled(self, enabled: bool):
        """更新启用状态."""
        self._is_enabled = enabled
        self._toggle.setChecked(enabled)

    def set_health_status(self, status: Optional[str]):
        """更新连接状态."""
        self._health_status = status


class ModelGroupWidget(QWidget):
    """模型分组容器 - 显示模型系列分组（像素级匹配参考设计）."""

    editModelClicked = Signal(dict)  # 编辑模型信号
    deleteModelClicked = Signal(dict)  # 删除模型信号

    def __init__(self, group_name: str, models: List[Dict[str, Any]], parent=None):
        super().__init__(parent)
        self._group_name = group_name
        self._models = models
        self._expanded = True
        # 立即应用样式，避免延迟渲染问题
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._init_ui()

    def _init_ui(self):
        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#999999')
        border_color = colors.get('borderLight', '#E0E0E0')
        bg_color = colors.get('base', '#FFFFFF')

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)

        # 分组标题栏
        header = QWidget()
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header.setAutoFillBackground(True)
        header.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }}
        """)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        # 下拉箭头（带圆形背景）
        self._arrow = QLabel("▼")
        self._arrow.setFixedSize(20, 20)
        self._arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._arrow.setStyleSheet(f"""
            QLabel {{
                background-color: {border_color};
                border-radius: 10px;
                color: {text_secondary};
                font-size: 10px;
            }}
        """)
        header_layout.addWidget(self._arrow)

        # 分组标题
        title = QLabel(self._group_name)
        title.setStyleSheet(f"""
            color: {text_primary};
            font-size: 13px;
            font-weight: 600;
        """)
        header_layout.addWidget(title, stretch=1)

        # 模型数量
        count_label = QLabel(str(len(self._models)))
        count_label.setStyleSheet(f"""
            color: {text_secondary};
            font-size: 11px;
        """)
        header_layout.addWidget(count_label)

        header.mousePressEvent = self._toggle_expand
        header.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(header)

        # 模型列表内容区
        self._content = QWidget()
        self._content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content.setAutoFillBackground(True)
        self._content.setStyleSheet(f"""
            QWidget {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-top: none;
                border-bottom-left-radius: 6px;
                border-bottom-right-radius: 6px;
            }}
        """)
        content_layout = QVBoxLayout(self._content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        for i, model in enumerate(self._models):
            item = ModelItemWidget(model, self._group_name)
            # 连接信号
            item.editClicked.connect(self.editModelClicked.emit)
            item.deleteClicked.connect(self.deleteModelClicked.emit)
            content_layout.addWidget(item)
            
            # 添加分隔线（除了最后一项）
            if i < len(self._models) - 1:
                divider = QFrame()
                divider.setFrameShape(QFrame.Shape.HLine)
                divider.setFixedHeight(1)
                divider.setStyleSheet(f"background-color: {border_color};")
                content_layout.addWidget(divider)

        layout.addWidget(self._content)

    def _toggle_expand(self, event):
        self._expanded = not self._expanded
        self._arrow.setText("▼" if self._expanded else "▶")
        self._content.setVisible(self._expanded)


class ModelItemWidget(QWidget):
    """模型列表项 - 显示单个模型及其能力标签（像素级匹配参考设计）."""

    editClicked = Signal(dict)  # 编辑按钮点击信号，携带模型数据
    deleteClicked = Signal(dict)  # 删除按钮点击信号，携带模型数据

    def __init__(self, model: Dict[str, Any], group_name: str, parent=None):
        super().__init__(parent)
        self._model = model
        self._group_name = group_name
        self._init_ui()

    def _init_ui(self):
        # 立即应用样式，避免延迟渲染
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#999999')
        border_color = colors.get('borderLight', '#E0E0E0')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(12)

        # 模型图标（蓝色圆形 M）- 使用 Frame 确保渲染
        icon_frame = QFrame()
        icon_frame.setFixedSize(36, 36)
        icon_frame.setStyleSheet("""
            QFrame {
                background-color: #3B82F6;
                border-radius: 18px;
            }
        """)
        icon_layout = QVBoxLayout(icon_frame)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_label = QLabel("M")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("""
            QLabel {
                background-color: transparent;
                color: white;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        icon_layout.addWidget(icon_label)
        layout.addWidget(icon_frame)

        # 模型信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(self._model.get('name', self._model.get('id', '')))
        name_label.setStyleSheet(f"""
            color: {text_primary};
            font-size: 13px;
            font-weight: 500;
        """)
        info_layout.addWidget(name_label)

        if self._model.get('context_length'):
            ctx = self._model['context_length']
            ctx_label = QLabel(f"上下文：{ctx // 1024}K")
            ctx_label.setStyleSheet(f"""
                color: {text_secondary};
                font-size: 11px;
            """)
            info_layout.addWidget(ctx_label)

        layout.addLayout(info_layout, 1)

        # 右侧区域：能力标签 + 操作按钮
        right_layout = QHBoxLayout()
        right_layout.setSpacing(6)

        # 能力标签（紫色 tools 标签）
        capabilities = self._model.get('capabilities', [])
        for cap in capabilities[:2]:  # 最多显示2个
            tag = QLabel(cap)
            tag.setStyleSheet("""
                QLabel {
                    background-color: #EDE9FE;
                    color: #8B5CF6;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                    font-weight: 500;
                }
            """)
            right_layout.addWidget(tag)

        # 设置按钮（齿轮图标）- 使用工具提示确保显示完整
        self._edit_btn = QPushButton()
        self._edit_btn.setFixedSize(32, 32)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setText("⚙")
        self._edit_btn.setToolTip("编辑模型")
        self._edit_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                font-size: 16px;
                color: {text_secondary};
                padding: 4px;
            }}
            QPushButton:hover {{
                background-color: {colors.get('controlFillHover', '#F5F5F5')};
                border-radius: 4px;
            }}
        """)
        self._edit_btn.clicked.connect(lambda: self.editClicked.emit(self._model))
        right_layout.addWidget(self._edit_btn)

        # 删除按钮（减号图标）
        self._delete_btn = QPushButton()
        self._delete_btn.setFixedSize(28, 28)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setText("−")
        self._delete_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                font-size: 18px;
                font-weight: bold;
                color: {text_secondary};
            }}
            QPushButton:hover {{
                background-color: #FEE2E2;
                border-radius: 4px;
                color: #DC2626;
            }}
        """)
        self._delete_btn.clicked.connect(lambda: self.deleteClicked.emit(self._model))
        right_layout.addWidget(self._delete_btn)

        layout.addLayout(right_layout)


class ModelEditDialog(QDialog):
    """模型编辑对话框 - 编辑模型详细配置（像素级匹配参考设计）."""

    def __init__(self, model_data: Optional[Dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self._model_data = model_data or {}
        self._capabilities = {
            'vision': False,
            'web': False,
            'reasoning': False,
            'tools': False,
            'rerank': False,
            'embedding': False,
        }
        # 立即应用样式，避免延迟渲染
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("编辑模型")
        self.setModal(True)
        self.setFixedWidth(520)
        self.setMinimumHeight(600)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#999999')
        border_color = colors.get('borderLight', '#E0E0E0')
        bg_color = colors.get('base', '#FFFFFF')
        required_color = '#DC2626'

        # 主容器（带边框）
        main_container = QWidget()
        main_container.setObjectName("modelEditContainer")
        main_container.setStyleSheet(f"""
            QWidget#modelEditContainer {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)

        main_layout = QVBoxLayout(main_container)
        main_layout.setSpacing(16)
        main_layout.setContentsMargins(24, 20, 24, 24)

        # 标题行
        title_layout = QHBoxLayout()
        title_label = QLabel("编辑模型")
        title_label.setStyleSheet(f"""
            color: {text_primary};
            font-size: 16px;
            font-weight: 600;
        """)
        title_layout.addWidget(title_label)
        title_layout.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                font-size: 18px;
                color: {text_secondary};
            }}
            QPushButton:hover {{
                background-color: {colors.get('controlFillHover', '#F5F5F5')};
                border-radius: 4px;
            }}
        """)
        close_btn.clicked.connect(self.reject)
        title_layout.addWidget(close_btn)
        main_layout.addLayout(title_layout)

        # 模型 ID（必填）
        id_layout = QVBoxLayout()
        id_layout.setSpacing(6)
        id_label_layout = QHBoxLayout()
        id_label_layout.setSpacing(4)
        id_required = QLabel("*")
        id_required.setStyleSheet(f"color: {required_color};")
        id_label_layout.addWidget(id_required)
        id_label = QLabel("模型 ID")
        id_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        id_label_layout.addWidget(id_label)
        id_help = QLabel("?")
        id_help.setFixedSize(16, 16)
        id_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        id_help.setStyleSheet(f"""
            background-color: {border_color};
            border-radius: 8px;
            color: {text_secondary};
            font-size: 10px;
        """)
        id_label_layout.addWidget(id_help)
        id_label_layout.addStretch()
        id_layout.addLayout(id_label_layout)

        id_input_layout = QHBoxLayout()
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("Pro/moonshotai/Kimi-K2.5")
        self._id_edit.setText(self._model_data.get('id', ''))
        self._id_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QLineEdit:focus {{
                border-color: #16A34A;
            }}
        """)
        id_input_layout.addWidget(self._id_edit)

        copy_btn = QPushButton()
        copy_btn.setFixedSize(36, 36)
        copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        copy_btn.setText("📋")
        copy_btn.setToolTip("复制")
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                border: none;
                background-color: transparent;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {colors.get('controlFillHover', '#F5F5F5')};
                border-radius: 4px;
            }}
        """)
        id_input_layout.addWidget(copy_btn)
        id_layout.addLayout(id_input_layout)
        main_layout.addLayout(id_layout)

        # 模型名称
        name_layout = QVBoxLayout()
        name_layout.setSpacing(6)
        name_label_layout = QHBoxLayout()
        name_label_layout.setSpacing(4)
        name_label = QLabel("模型名称")
        name_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        name_label_layout.addWidget(name_label)
        name_help = QLabel("?")
        name_help.setFixedSize(16, 16)
        name_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_help.setStyleSheet(f"""
            background-color: {border_color};
            border-radius: 8px;
            color: {text_secondary};
            font-size: 10px;
        """)
        name_label_layout.addWidget(name_help)
        name_label_layout.addStretch()
        name_layout.addLayout(name_label_layout)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Pro/moonshotai/Kimi-K2.5")
        self._name_edit.setText(self._model_data.get('name', ''))
        self._name_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QLineEdit:focus {{
                border-color: #16A34A;
            }}
        """)
        name_layout.addWidget(self._name_edit)
        main_layout.addLayout(name_layout)

        # 分组名称
        group_layout = QVBoxLayout()
        group_layout.setSpacing(6)
        group_label_layout = QHBoxLayout()
        group_label_layout.setSpacing(4)
        group_label = QLabel("分组名称")
        group_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        group_label_layout.addWidget(group_label)
        group_help = QLabel("?")
        group_help.setFixedSize(16, 16)
        group_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group_help.setStyleSheet(f"""
            background-color: {border_color};
            border-radius: 8px;
            color: {text_secondary};
            font-size: 10px;
        """)
        group_label_layout.addWidget(group_help)
        group_label_layout.addStretch()
        group_layout.addLayout(group_label_layout)

        self._group_edit = QLineEdit()
        self._group_edit.setPlaceholderText("pro")
        self._group_edit.setText(self._model_data.get('group', ''))
        self._group_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 10px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QLineEdit:focus {{
                border-color: #16A34A;
            }}
        """)
        group_layout.addWidget(self._group_edit)
        main_layout.addLayout(group_layout)

        # 更多设置 + 保存按钮行
        action_layout = QHBoxLayout()
        self._more_btn = QPushButton("更多设置 ▲")
        self._more_btn.setCheckable(True)
        self._more_btn.setChecked(False)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors.get('controlFillHover', '#F5F5F5')};
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: {text_secondary};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {colors.get('controlFillPressed', '#E8E8E8')};
            }}
        """)
        self._more_btn.clicked.connect(self._toggle_more_settings)
        action_layout.addWidget(self._more_btn)
        action_layout.addStretch()

        save_btn = QPushButton("保存")
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #16A34A;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: #15803D;
            }}
        """)
        save_btn.clicked.connect(self.accept)
        action_layout.addWidget(save_btn)
        main_layout.addLayout(action_layout)

        # 更多设置区域
        self._more_widget = QWidget()
        self._more_widget.setVisible(False)
        more_layout = QVBoxLayout(self._more_widget)
        more_layout.setContentsMargins(0, 0, 0, 0)
        more_layout.setSpacing(20)

        # 模型类型
        type_layout = QVBoxLayout()
        type_layout.setSpacing(10)
        type_label_layout = QHBoxLayout()
        type_label_layout.setSpacing(4)
        type_label = QLabel("模型类型")
        type_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        type_label_layout.addWidget(type_label)
        type_warning = QLabel("⚠")
        type_warning.setStyleSheet("color: #F59E0B;")
        type_label_layout.addWidget(type_warning)
        type_label_layout.addStretch()
        type_layout.addLayout(type_label_layout)

        # 能力标签
        self._capability_checkboxes = {}
        capabilities_layout = QHBoxLayout()
        capabilities_layout.setSpacing(10)

        capability_tags = [
            ('vision', '视觉', '#EC4899', '#FCE7F3'),
            ('web', '联网', '#8B5CF6', '#EDE9FE'),
            ('reasoning', '推理', '#F59E0B', '#FEF3C7'),
            ('tools', '工具', '#8B5CF6', '#EDE9FE'),
            ('rerank', '重排', '#6B7280', '#F3F4F6'),
            ('embedding', '嵌入', '#10B981', '#D1FAE5'),
        ]

        for cap_key, cap_name, fg_color, bg_color in capability_tags:
            cb = QCheckBox(cap_name)
            cb.setChecked(self._capabilities.get(cap_key, False))
            cb.stateChanged.connect(
                lambda state, key=cap_key: self._on_capability_changed(key, state)
            )
            self._capability_checkboxes[cap_key] = cb
            # 样式化为标签
            cb.setStyleSheet(f"""
                QCheckBox {{
                    spacing: 6px;
                    color: {fg_color};
                    background-color: {bg_color};
                    border: none;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 12px;
                    font-weight: 500;
                }}
                QCheckBox::indicator {{
                    width: 0px;
                    height: 0px;
                }}
                QCheckBox:checked {{
                    background-color: {fg_color};
                    color: white;
                }}
            """)
            capabilities_layout.addWidget(cb)

        capabilities_layout.addStretch()
        type_layout.addLayout(capabilities_layout)
        more_layout.addLayout(type_layout)

        # 支持增量文本输出
        streaming_layout = QHBoxLayout()
        streaming_layout.setSpacing(4)
        streaming_label = QLabel("支持增量文本输出")
        streaming_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        streaming_layout.addWidget(streaming_label)
        streaming_help = QLabel("?")
        streaming_help.setFixedSize(16, 16)
        streaming_help.setAlignment(Qt.AlignmentFlag.AlignCenter)
        streaming_help.setStyleSheet(f"""
            background-color: {border_color};
            border-radius: 8px;
            color: {text_secondary};
            font-size: 10px;
        """)
        streaming_layout.addWidget(streaming_help)
        streaming_layout.addStretch()

        self._streaming_check = QCheckBox()
        self._streaming_check.setChecked(
            self._model_data.get('support_streaming', True)
        )
        # 样式化为开关
        self._streaming_check.setStyleSheet(f"""
            QCheckBox {{
                spacing: 0px;
            }}
            QCheckBox::indicator {{
                width: 40px;
                height: 22px;
                border-radius: 11px;
                background-color: {border_color};
            }}
            QCheckBox::indicator:checked {{
                background-color: #16A34A;
            }}
        """)
        streaming_layout.addWidget(self._streaming_check)
        more_layout.addLayout(streaming_layout)

        # 币种
        currency_layout = QHBoxLayout()
        currency_label = QLabel("币种")
        currency_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        currency_layout.addWidget(currency_label)
        currency_layout.addStretch()
        self._currency_combo = QComboBox()
        self._currency_combo.addItems(["$", "¥", "€"])
        self._currency_combo.setFixedWidth(80)
        self._currency_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
        """)
        currency_layout.addWidget(self._currency_combo)
        more_layout.addLayout(currency_layout)

        # 输入价格
        input_price_layout = QVBoxLayout()
        input_price_layout.setSpacing(6)
        input_price_label = QLabel("输入价格")
        input_price_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        input_price_layout.addWidget(input_price_label)

        input_price_row = QHBoxLayout()
        self._input_price_spin = QDoubleSpinBox()
        self._input_price_spin.setRange(0, 999999)
        self._input_price_spin.setValue(
            self._model_data.get('input_price_per_1m', 0.0)
        )
        self._input_price_spin.setDecimals(2)
        self._input_price_spin.setFixedWidth(120)
        self._input_price_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
        """)
        input_price_row.addWidget(self._input_price_spin)
        input_price_unit = QLabel("$ / 百万 Token")
        input_price_unit.setStyleSheet(f"color: {text_secondary};")
        input_price_row.addWidget(input_price_unit)
        input_price_row.addStretch()
        input_price_layout.addLayout(input_price_row)
        more_layout.addLayout(input_price_layout)

        # 输出价格
        output_price_layout = QVBoxLayout()
        output_price_layout.setSpacing(6)
        output_price_label = QLabel("输出价格")
        output_price_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        output_price_layout.addWidget(output_price_label)

        output_price_row = QHBoxLayout()
        self._output_price_spin = QDoubleSpinBox()
        self._output_price_spin.setRange(0, 999999)
        self._output_price_spin.setValue(
            self._model_data.get('output_price_per_1m', 0.0)
        )
        self._output_price_spin.setDecimals(2)
        self._output_price_spin.setFixedWidth(120)
        self._output_price_spin.setStyleSheet(f"""
            QDoubleSpinBox {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
        """)
        output_price_row.addWidget(self._output_price_spin)
        output_price_unit = QLabel("$ / 百万 Token")
        output_price_unit.setStyleSheet(f"color: {text_secondary};")
        output_price_row.addWidget(output_price_unit)
        output_price_row.addStretch()
        output_price_layout.addLayout(output_price_row)
        more_layout.addLayout(output_price_layout)

        main_layout.addWidget(self._more_widget)

        # 设置对话框布局
        dialog_layout = QVBoxLayout(self)
        dialog_layout.setContentsMargins(0, 0, 0, 0)
        dialog_layout.addWidget(main_container)

    def _toggle_more_settings(self):
        """切换更多设置区域的显示."""
        self._more_widget.setVisible(self._more_btn.isChecked())

    def _on_capability_changed(self, key: str, state: int):
        """能力标签状态变化."""
        self._capabilities[key] = (state == Qt.CheckState.Checked.value)

    def get_model_data(self) -> Dict[str, Any]:
        """获取编辑后的模型数据."""
        capabilities = [
            cap for cap, enabled in self._capabilities.items() if enabled
        ]
        return {
            'id': self._id_edit.text(),
            'name': self._name_edit.text(),
            'group': self._group_edit.text(),
            'capabilities': capabilities,
            'support_streaming': self._streaming_check.isChecked(),
            'input_price_per_1m': self._input_price_spin.value(),
            'output_price_per_1m': self._output_price_spin.value(),
        }


class ActionButton(QPushButton):
    """带图标的操作按钮."""

    def __init__(self, text: str, icon_text: str = "", parent=None):
        super().__init__(parent)
        self._icon_text = icon_text
        self.setText(f"{icon_text} {text}" if icon_text else text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_style()

    def _apply_style(self):
        colors = get_current_colors()
        accent = colors.get('accent', '#4A90D9')
        accent_light = colors.get('accentLight', '#4CC2FF')
        accent_dark = colors.get('accentDark', '#005A9E')

        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {accent_light};
            }}
            QPushButton:pressed {{
                background-color: {accent_dark};
            }}
            QPushButton:disabled {{
                background-color: #CCCCCC;
                color: #999999;
            }}
        """)


class ConfigCard(QWidget):
    """配置卡片容器 - 带标题的圆角卡片."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._init_ui(title)

    def _init_ui(self, title: str):
        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        border_color = colors.get('borderLight', '#E0E0E0')
        text_primary = colors.get('textPrimary', '#333333')

        self.setStyleSheet(f"""
            QWidget#ConfigCard {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 8px;
            }}
        """)
        self.setObjectName("ConfigCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 标题
        title_label = QLabel(title)
        title_label.setStyleSheet(f"""
            color: {text_primary};
            font-size: 13px;
            font-weight: 600;
        """)
        layout.addWidget(title_label)

        self._content_layout = QVBoxLayout()
        self._content_layout.setSpacing(10)
        layout.addLayout(self._content_layout)

    def add_widget(self, widget: QWidget):
        """添加控件到卡片内容区."""
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        """添加布局到卡片内容区."""
        self._content_layout.addLayout(layout)


# 保留向后兼容的 CollapsibleGroup
class CollapsibleGroup(QWidget):
    """可折叠分组组件（向后兼容）."""

    toggled = Signal(bool)

    def __init__(self, title: str, count: int = 0, parent=None):
        super().__init__(parent)
        self.title = title
        self.count = count
        self.is_expanded = True

        self.setStyleSheet("background-color: transparent;")
        self._init_ui()

    def _init_ui(self):
        colors = get_current_colors()
        header_bg = colors.get('controlFillHover', '#F8F9FA')
        header_hover = colors.get('controlFillPressed', '#F0F0F0')
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#666666')

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.header = QPushButton()
        self.header.setObjectName("collapsibleHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(f"""
            QPushButton#collapsibleHeader {{
                background-color: {header_bg};
                border: none;
                border-radius: 6px;
                text-align: left;
            }}
            QPushButton#collapsibleHeader:hover {{
                background-color: {header_hover};
            }}
        """)

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 8, 12, 8)

        self.arrow_label = QLabel("▼")
        self.arrow_label.setObjectName("collapsibleArrow")
        self.arrow_label.setFixedWidth(16)
        self.arrow_label.setStyleSheet(f"color: {text_secondary};")
        header_layout.addWidget(self.arrow_label)

        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("collapsibleTitle")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet(f"color: {text_primary};")
        header_layout.addWidget(self.title_label, stretch=1)

        if self.count > 0:
            count_bg = colors.get('borderLight', '#E0E0E0')
            self.count_label = QLabel(str(self.count))
            self.count_label.setObjectName("collapsibleCount")
            self.count_label.setFixedSize(24, 18)
            self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.count_label.setStyleSheet(f"""
                QLabel {{
                    background-color: {count_bg};
                    color: {text_secondary};
                    border-radius: 9px;
                    font-size: 10px;
                }}
            """)
            header_layout.addWidget(self.count_label)

        header_layout.addSpacing(4)

        self.header.clicked.connect(self._on_header_clicked)
        self.main_layout.addWidget(self.header)

        self.content_widget = QWidget()
        self.content_widget.setObjectName("collapsibleContent")
        self.content_widget.setStyleSheet("background-color: transparent;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(8, 8, 0, 8)
        self.content_layout.setSpacing(4)
        self.main_layout.addWidget(self.content_widget)

    def _on_header_clicked(self):
        self.is_expanded = not self.is_expanded
        self.arrow_label.setText("▼" if self.is_expanded else "▶")
        self.content_widget.setVisible(self.is_expanded)
        self.toggled.emit(self.is_expanded)

    def add_widget(self, widget: QWidget):
        self.content_layout.addWidget(widget)


# 保留向后兼容的 ModelDetailItem
class ModelDetailItem(QWidget):
    """模型详情项（向后兼容）."""

    def __init__(self, model_id: str, model_name: str, context_length: int = 0,
                 support_chat: bool = False, support_embedding: bool = False,
                 support_vision: bool = False, support_thinking: bool = False,
                 support_tools: bool = False, parent=None):
        super().__init__(parent)
        self._init_ui(model_id, model_name, context_length,
                      support_chat, support_embedding, support_vision,
                      support_thinking, support_tools)

    def _init_ui(self, model_id, model_name, context_length,
                 support_chat, support_embedding, support_vision,
                 support_thinking, support_tools):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(12)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#999999')

        # 模型信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        name_label = QLabel(model_name)
        name_label.setStyleSheet(f"""
            color: {text_primary};
            font-size: 12px;
            font-weight: 500;
        """)
        info_layout.addWidget(name_label)

        if context_length and context_length > 0:
            ctx_label = QLabel(f"上下文：{context_length // 1024}K")
            ctx_label.setStyleSheet(f"""
                color: {text_secondary};
                font-size: 10px;
            """)
            info_layout.addWidget(ctx_label)

        layout.addLayout(info_layout, 1)

        # 能力标签
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)

        if support_chat:
            tags_layout.addWidget(CapabilityTag('chat'))
        if support_tools:
            tags_layout.addWidget(CapabilityTag('tools'))
        if support_vision:
            tags_layout.addWidget(CapabilityTag('vision'))
        if support_embedding:
            tags_layout.addWidget(CapabilityTag('embedding'))
        if support_thinking:
            tags_layout.addWidget(CapabilityTag('thinking'))

        layout.addLayout(tags_layout)


# 保留向后兼容的 ToggleSwitch
class ToggleSwitch(QWidget):
    """现代切换开关组件（向后兼容）."""

    toggled = Signal(bool)

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setFixedSize(40, 22)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(40, 22)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._checked = not self._checked
            self.toggled.emit(self._checked)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        colors = get_current_colors()
        accent = QColor(colors.get('accent', '#4A90D9'))
        border_color = QColor(colors.get('border', '#CCCCCC'))
        bg_color = QColor(colors.get('controlFillHover', '#E0E0E0'))

        # 绘制背景轨道
        rect = QRect(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, self.height() / 2, self.height() / 2)

        if self._checked:
            painter.fillPath(path, accent)
        else:
            painter.fillPath(path, bg_color)

        # 绘制滑块
        knob_size = self.height() - 4
        knob_y = 2
        if self._checked:
            knob_x = self.width() - knob_size - 2
        else:
            knob_x = 2

        knob_rect = QRect(knob_x, knob_y, knob_size, knob_size)
        painter.setBrush(Qt.GlobalColor.white)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(knob_rect)

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self.update()
