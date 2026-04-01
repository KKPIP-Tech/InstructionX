# src/ui/dialog/llm_settings_components.py
"""LLM 设置中心自定义组件 - 支持深色模式."""

from typing import Optional, Callable, List
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QToolButton, QMenu, QLineEdit,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPainterPath, QBrush, QPen

from utils.style_qss import get_style_qss


def get_current_colors() -> dict:
    """获取当前主题颜色."""
    return get_style_qss().colors()


class ProviderListItemWidget(QWidget):
    """Provider 列表项自定义控件 - 圆形 Logo + 动态背景."""

    def __init__(self, name: str, logo_path: Optional[str], is_enabled: bool, parent=None):
        super().__init__(parent)
        self._name = name
        self._logo_path = logo_path
        self._is_enabled = is_enabled

        self.setFixedHeight(44)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        
        # 获取当前主题颜色
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
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        accent = colors.get('accent', '#4A90D9')

        # 左侧 Logo - 圆形
        self._logo = QLabel()
        self._logo.setFixedSize(32, 32)
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 圆形样式
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

        # 中间名称 - 透明背景
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

        # 右侧启用状态
        self._status_label = QLabel("已启用" if self._is_enabled else "未启用")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setFixedHeight(20)
        
        # 使用更明显的颜色
        if self._is_enabled:
            status_color = "#16A34A"  # 绿色
            status_bg = "#DCFCE7" if get_style_qss().theme() == 'light' else "#166534"
        else:
            status_color = "#9CA3AF"  # 灰色
            status_bg = "#F3F4F6" if get_style_qss().theme() == 'light' else "#4B5563"
            
        self._status_label.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                background-color: {status_bg};
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 500;
            }}
        """)
        layout.addWidget(self._status_label, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _load_circular_pixmap(self, path: str, size: int) -> QPixmap:
        """加载并裁剪为圆形图片 - 保持原始比例居中显示.
        
        Args:
            path: 图片路径
            size: 目标尺寸
            
        Returns:
            QPixmap: 圆形图片
        """
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return QPixmap()
        
        # 关键修复：使用 KeepAspectRatio 保持原始比例
        scaled = pixmap.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        
        # 创建圆形蒙版
        circular_pixmap = QPixmap(size, size)
        circular_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(circular_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # 计算居中位置
        x = (size - scaled.width()) // 2
        y = (size - scaled.height()) // 2
        
        # 绘制圆形裁剪路径
        clip_path = QPainterPath()
        clip_path.addEllipse(0, 0, size, size)
        painter.setClipPath(clip_path)
        
        # 绘制居中的图片
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

    def set_enabled(self, enabled: bool):
        """更新启用状态."""
        self._is_enabled = enabled
        self._status_label.setText("已启用" if enabled else "未启用")
        
        if enabled:
            status_color = "#16A34A"
            status_bg = "#DCFCE7" if get_style_qss().theme() == 'light' else "#166534"
        else:
            status_color = "#9CA3AF"
            status_bg = "#F3F4F6" if get_style_qss().theme() == 'light' else "#4B5563"
            
        self._status_label.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                background-color: {status_bg};
                border-radius: 10px;
                padding: 2px 10px;
                font-size: 10px;
                font-weight: 500;
            }}
        """)


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
        header_layout.setContentsMargins(12, 10, 12, 10)
        
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
        self.header.setChecked(self.is_expanded)
        self.content_widget.setVisible(self.is_expanded)
        self.arrow_label.setText("▼" if self.is_expanded else "▶")
        self.toggled.emit(self.is_expanded)
    
    def add_widget(self, widget: QWidget):
        """添加内容控件."""
        self.content_layout.addWidget(widget)
    
    def set_expanded(self, expanded: bool):
        self.is_expanded = expanded
        self.header.setChecked(expanded)
        self.content_widget.setVisible(expanded)
        self.arrow_label.setText("▼" if expanded else "▶")


class ModelListItem(QWidget):
    """模型列表项 - 带操作按钮."""
    
    settings_clicked = Signal(str)
    pin_clicked = Signal(str)
    delete_clicked = Signal(str)
    
    def __init__(self, model_id: str, model_name: str, 
                 icon_path: Optional[str] = None, is_pinned: bool = False,
                 parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.model_name = model_name
        self.is_pinned = is_pinned
        
        self.setObjectName("modelListItem")
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._init_ui(icon_path)
    
    def _init_ui(self, icon_path: Optional[str]):
        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        hover_bg = colors.get('controlFillHover', '#F5F5F5')
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        if icon_path:
            pixmap = QPixmap(icon_path)
            if not pixmap.isNull():
                # 保持比例缩放
                scaled = pixmap.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.icon_label.setPixmap(scaled)
            else:
                self._set_icon_fallback()
        else:
            self._set_icon_fallback()
        layout.addWidget(self.icon_label)
        
        text_primary = colors.get('textPrimary', '#333333')
        self.name_label = QLabel(self.model_name)
        self.name_label.setObjectName("modelNameLabel")
        self.name_label.setStyleSheet(f"color: {text_primary};")
        layout.addWidget(self.name_label, stretch=1)
        
        self.pin_btn = QToolButton()
        self.pin_btn.setObjectName("modelActionBtn")
        self.pin_btn.setFixedSize(24, 24)
        self.pin_btn.setText("📌" if self.is_pinned else "📍")
        self.pin_btn.setToolTip("固定" if not self.is_pinned else "取消固定")
        self.pin_btn.clicked.connect(lambda: self.pin_clicked.emit(self.model_id))
        layout.addWidget(self.pin_btn)
        
        self.settings_btn = QToolButton()
        self.settings_btn.setObjectName("modelActionBtn")
        self.settings_btn.setFixedSize(24, 24)
        self.settings_btn.setText("⚙")
        self.settings_btn.setToolTip("设置")
        self.settings_btn.clicked.connect(lambda: self.settings_clicked.emit(self.model_id))
        layout.addWidget(self.settings_btn)
        
        self.delete_btn = QToolButton()
        self.delete_btn.setObjectName("modelActionBtn")
        self.delete_btn.setFixedSize(24, 24)
        self.delete_btn.setText("×")
        self.delete_btn.setToolTip("删除")
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.model_id))
        layout.addWidget(self.delete_btn)
        
        # 保存颜色供事件方法使用
        self._bg_color = bg_color
        self._hover_bg = hover_bg
    
    def _set_icon_fallback(self):
        """设置默认图标."""
        colors = get_current_colors()
        accent = colors.get('accent', '#4A90D9')
        
        self.icon_label.setStyleSheet(f"""
            QLabel {{
                background-color: {accent};
                border-radius: 10px;
                color: white;
                font-size: 10px;
            }}
        """)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setText(self.model_name[:1].upper())
    
    def set_pinned(self, pinned: bool):
        self.is_pinned = pinned
        self.pin_btn.setText("📌" if pinned else "📍")
        self.pin_btn.setToolTip("取消固定" if pinned else "固定")
    
    def enterEvent(self, event):
        self.setStyleSheet(f"""
            QWidget#modelListItem {{
                background-color: {self._hover_bg};
                border-radius: 6px;
            }}
        """)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.setStyleSheet(f"""
            QWidget#modelListItem {{
                background-color: {self._bg_color};
                border-radius: 6px;
            }}
        """)
        super().leaveEvent(event)


class ActionButton(QPushButton):
    """操作按钮."""
    
    def __init__(self, text: str, icon: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("actionButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(36)
        
        colors = get_current_colors()
        accent = colors.get('accent', '#4A90D9')
        accent_dark = colors.get('accentDark', '#3A7BC8')
        
        self.setStyleSheet(f"""
            QPushButton#actionButton {{
                background-color: {accent};
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 13px;
                font-weight: 500;
                padding: 0 16px;
            }}
            QPushButton#actionButton:hover {{
                background-color: {accent_dark};
            }}
            QPushButton#actionButton:pressed {{
                background-color: {colors.get('accentDark', '#2E6BB5')};
            }}
        """)
        
        if icon:
            self.setText(f"{icon} {text}")
        else:
            self.setText(text)


class IconLineEdit(QWidget):
    """带图标的输入框."""
    
    def __init__(self, placeholder: str = "", icon: Optional[str] = None, 
                 is_password: bool = False, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        border_color = colors.get('borderLight', '#E0E0E0')
        accent = colors.get('accent', '#4A90D9')
        
        self.line_edit = QLineEdit()
        self.line_edit.setObjectName("iconLineEdit")
        self.line_edit.setPlaceholderText(placeholder)
        if is_password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.line_edit.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QLineEdit:focus {{
                border-color: {accent};
            }}
        """)
        layout.addWidget(self.line_edit)
        
        if icon:
            self.icon_btn = QToolButton()
            self.icon_btn.setObjectName("lineEditIconBtn")
            self.icon_btn.setFixedSize(28, 28)
            self.icon_btn.setText(icon)
            self.icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(self.icon_btn)
    
    def text(self) -> str:
        return self.line_edit.text()
    
    def setText(self, text: str):
        self.line_edit.setText(text)
    
    def setEchoMode(self, mode):
        self.line_edit.setEchoMode(mode)


class SettingsCategoryItem(QWidget):
    """左侧设置分类项."""

    clicked = Signal(str)

    def __init__(self, icon: str, text: str, category: str, parent=None):
        super().__init__(parent)
        self.category = category
        self.is_selected = False

        self.setObjectName("settingsCategoryItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(40)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        
        self.icon_label = QLabel(icon)
        self.icon_label.setObjectName("categoryIcon")
        self.icon_label.setFixedWidth(20)
        self.icon_label.setStyleSheet(f"color: {text_primary};")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("categoryText")
        self.text_label.setStyleSheet(f"color: {text_primary};")
        layout.addWidget(self.text_label, stretch=1)

        self.set_selected(False)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.setProperty("selected", "true" if self.is_selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.category)
        super().mousePressEvent(event)


class ModelDetailItem(QWidget):
    """模型详情列表项 - 显示模型完整信息."""
    
    clicked = Signal(str)
    
    def __init__(self, model_id: str, model_name: str, 
                 context_length: Optional[int] = None,
                 support_chat: bool = False,
                 support_embedding: bool = False,
                 support_vision: bool = False,
                 support_thinking: bool = False,
                 support_tools: bool = False,
                 parent=None):
        super().__init__(parent)
        self.model_id = model_id
        self.model_name = model_name
        self.context_length = context_length
        
        self.setObjectName("modelDetailItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(56)
        
        colors = get_current_colors()
        bg_color = colors.get('base', '#FFFFFF')
        border_color = colors.get('borderLight', '#E0E0E0')
        hover_bg = colors.get('controlFillHover', '#F5F5F5')
        hover_border = colors.get('border', '#CCCCCC')
        
        self.setStyleSheet(f"""
            QWidget#modelDetailItem {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 6px;
            }}
            QWidget#modelDetailItem:hover {{
                background-color: {hover_bg};
                border-color: {hover_border};
            }}
        """)
        
        self._init_ui(
            support_chat=support_chat,
            support_embedding=support_embedding,
            support_vision=support_vision,
            support_thinking=support_thinking,
            support_tools=support_tools
        )
    
    def _init_ui(self, support_chat: bool, support_embedding: bool,
                 support_vision: bool, support_thinking: bool, support_tools: bool):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(12)
        
        colors = get_current_colors()
        text_primary = colors.get('textPrimary', '#333333')
        text_secondary = colors.get('textSecondary', '#666666')
        accent = colors.get('accent', '#4A90D9')
        
        # 左侧：图标 - 圆形
        icon_label = QLabel()
        icon_label.setFixedSize(36, 36)
        icon_label.setObjectName("modelIcon")
        icon_text = self.model_name[:1].upper() if self.model_name else "?"
        icon_label.setText(icon_text)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"""
            QLabel#modelIcon {{
                background-color: {accent};
                border-radius: 18px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        main_layout.addWidget(icon_label)
        
        # 中间：名称和上下文长度
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        name_label = QLabel(self.model_name or self.model_id)
        name_label.setObjectName("modelName")
        name_label.setStyleSheet(f"color: {text_primary}; font-size: 14px; font-weight: 500;")
        info_layout.addWidget(name_label)
        
        if self.context_length:
            ctx_text = self._format_context_length(self.context_length)
            ctx_label = QLabel(f"上下文：{ctx_text}")
            ctx_label.setObjectName("modelContext")
            ctx_label.setStyleSheet(f"color: {text_secondary}; font-size: 11px;")
            info_layout.addWidget(ctx_label)
        
        info_layout.addStretch()
        main_layout.addLayout(info_layout, 1)
        
        # 右侧：标签组
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(4)
        
        if support_chat:
            chat_tag = self._create_tag("Chat", "category")
            tags_layout.addWidget(chat_tag)
        
        if support_embedding:
            emb_tag = self._create_tag("Embedding", "category")
            tags_layout.addWidget(emb_tag)
        
        if support_vision:
            vision_tag = self._create_tag("Vision", "vision")
            tags_layout.addWidget(vision_tag)
        
        if support_thinking:
            thinking_tag = self._create_tag("Thinking", "thinking")
            tags_layout.addWidget(thinking_tag)
        
        if support_tools:
            tools_tag = self._create_tag("Tools", "tools")
            tags_layout.addWidget(tools_tag)
        
        tags_layout.addStretch()
        main_layout.addLayout(tags_layout)
    
    def _create_tag(self, text: str, tag_type: str) -> QLabel:
        """创建标签."""
        tag = QLabel(text)
        tag.setObjectName("modelTag")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        colors = get_current_colors()
        
        # 根据主题调整标签颜色
        if get_style_qss().theme() == 'dark':
            tag_colors = {
                "category": ("#90CAF9", "#1565C0"),
                "vision": ("#CE93D8", "#7B1FA2"),
                "thinking": ("#FFCC80", "#F57C00"),
                "tools": ("#80CBC4", "#00796B"),
            }
        else:
            tag_colors = {
                "category": ("#2196F3", "#E3F2FD"),
                "vision": ("#9C27B0", "#F3E5F5"),
                "thinking": ("#FF9800", "#FFF3E0"),
                "tools": ("#009688", "#E0F2F1"),
            }
        
        text_color, bg_color = tag_colors.get(tag_type, ("#666666", "#F5F5F5"))
        
        tag.setStyleSheet(f"""
            QLabel#modelTag {{
                color: {text_color};
                background-color: {bg_color};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: 600;
            }}
        """)
        return tag
    
    def _format_context_length(self, length: int) -> str:
        """格式化上下文长度显示."""
        if length < 1000:
            return f"{length}"
        elif length < 1000000:
            return f"{length // 1000}K"
        else:
            return f"{length / 1000000:.1f}M"
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model_id)
        super().mousePressEvent(event)