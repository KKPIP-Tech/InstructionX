# ui/dialog/llm_settings_components.py
"""LLM 设置中心自定义组件 - 支持深色模式."""

from typing import Optional, Callable, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QToolButton, QMenu, QLineEdit,
    QGraphicsDropShadowEffect, QCheckBox
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


class ToggleSwitch(QWidget):
    """现代切换开关组件 - 圆角矩形滑块."""

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


class ProviderListItemWidget(QWidget):
    """Provider 列表项自定义控件 - 圆形 Logo + 切换开关 + 状态指示点."""

    toggled = Signal(bool)

    def __init__(self, name: str, logo_path: Optional[str], is_enabled: bool,
                 health_status: Optional[str] = None, parent=None):
        super().__init__(parent)
        self._name = name
        self._logo_path = logo_path
        self._is_enabled = is_enabled
        self._health_status = health_status  # "connected" / "failed" / None

        self.setFixedHeight(44)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        hover_color = colors.get('controlFillHover', '#F5F5F5')

        self.setStyleSheet(f"""
            QWidget#ProviderListItemWidget {{
                background-color: {bg_color};
                border-radius: 6px;
            }}
            QWidget#ProviderListItemWidget:hover {{
                background-color: {hover_color};
            }}
        """)
        self.setObjectName("ProviderListItemWidget")
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')

        # 左侧 Logo - 圆形
        self._logo = QLabel()
        self._logo.setFixedSize(32, 32)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setStyleSheet("""
            QLabel {
                border-radius: 16px;
            }
        """)

        if self._logo_path and Path(self._logo_path).exists():
            pixmap = self._load_circular_pixmap(self._logo_path, 32)
            if not pixmap.isNull():
                self._logo.setPixmap(pixmap)
            else:
                self._set_logo_fallback()
        else:
            self._set_logo_fallback()
        layout.addWidget(self._logo, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 中间区域：名称 + 状态指示点
        name_layout = QVBoxLayout()
        name_layout.setSpacing(2)
        name_layout.setContentsMargins(0, 0, 0, 0)

        self._name_label = QLabel(self._name)
        self._name_label.setStyleSheet(f"""
            QLabel {{
                color: {text_primary};
                font-size: 13px;
                font-weight: 500;
                background-color: transparent;
            }}
        """)
        name_layout.addWidget(self._name_label)

        # 状态指示点 + 文本
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        status_row.setContentsMargins(0, 0, 0, 0)

        # 状态点
        self._status_dot = QLabel()
        self._status_dot.setFixedSize(6, 6)
        self._update_status_dot()
        status_row.addWidget(self._status_dot)

        # 状态文本
        self._status_text = QLabel()
        self._status_text.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {colors.get('textSecondary', '#999999')};
            }}
        """)
        self._update_status_text()
        status_row.addWidget(self._status_text)
        status_row.addStretch()

        name_layout.addLayout(status_row)
        
        # 使用容器包装 name_layout 以支持对齐
        name_container = QWidget()
        name_container_layout = QVBoxLayout(name_container)
        name_container_layout.setContentsMargins(0, 0, 0, 0)
        name_container_layout.addLayout(name_layout)
        name_container_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(name_container, stretch=1, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 右侧切换开关
        self._toggle = ToggleSwitch(self._is_enabled)
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _update_status_dot(self):
        """更新状态指示点样式."""
        if self._health_status == "connected":
            color = STATUS_CONNECTED
        elif self._health_status == "failed":
            color = STATUS_FAILED
        else:
            color = STATUS_UNKNOWN

        self._status_dot.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)

    def _update_status_text(self):
        """更新状态文本."""
        if self._health_status == "connected":
            self._status_text.setText("已连接")
        elif self._health_status == "failed":
            self._status_text.setText("连接失败")
        else:
            self._status_text.setText("未检测")

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
                border-radius: 16px;
                color: white;
                font-size: 14px;
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
        self._update_status_dot()
        self._update_status_text()


class CollapsibleGroup(QWidget):
    """可折叠分组组件."""

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


class ModelDetailItem(QWidget):
    """模型详情项 - 显示模型名称、上下文和能力标签."""

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

        tag_colors = {
            'chat': ('#3B82F6', '#DBEAFE'),
            'tools': ('#8B5CF6', '#EDE9FE'),
            'vision': ('#EC4899', '#FCE7F3'),
            'embedding': ('#10B981', '#D1FAE5'),
            'thinking': ('#F59E0B', '#FEF3C7'),
        }

        if support_chat:
            tag = self._make_tag("Chat", *tag_colors['chat'])
            tags_layout.addWidget(tag)
        if support_tools:
            tag = self._make_tag("Tools", *tag_colors['tools'])
            tags_layout.addWidget(tag)
        if support_vision:
            tag = self._make_tag("Vision", *tag_colors['vision'])
            tags_layout.addWidget(tag)
        if support_embedding:
            tag = self._make_tag("Embedding", *tag_colors['embedding'])
            tags_layout.addWidget(tag)
        if support_thinking:
            tag = self._make_tag("Thinking", *tag_colors['thinking'])
            tags_layout.addWidget(tag)

        layout.addLayout(tags_layout)

    def _make_tag(self, text: str, fg: str, bg: str) -> QLabel:
        """创建能力标签."""
        tag = QLabel(text)
        tag.setStyleSheet(f"""
            QLabel {{
                color: {fg};
                background-color: {bg};
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
            }}
        """)
        return tag


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
