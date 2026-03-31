"""
LLM 设置中心自定义组件
实现 LLM 设置对话框的控件
"""

from typing import Optional, Callable, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QToolButton, QMenu, QLineEdit,
    QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor, QPainter, QPainterPath


class ProviderListItem(QWidget):
    """Provider 列表项 - 带图标和状态标签"""
    
    clicked = Signal(str)  # 发送 provider_name
    
    def __init__(self, provider_name: str, provider_type: str = "",
                 icon_path: Optional[str] = None, is_active: bool = False,
                 display_name: Optional[str] = None,
                 parent=None):
        super().__init__(parent)
        self.provider_name = provider_name  # 内部标识（dict key）
        self.provider_type = provider_type
        self.is_active = is_active
        self.is_selected = False
        self._display_name = display_name  # 用于 UI 显示

        self.setObjectName("providerListItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(44)

        self._init_ui(icon_path)
        self._update_style()
    
    def _init_ui(self, icon_path: Optional[str]):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(10)
        
        # 图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(24, 24)
        if icon_path:
            self.icon_label.setPixmap(QPixmap(icon_path).scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            # 默认图标 - 使用首字母
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: {accent};
                    border-radius: 4px;
                    color: white;
                    font-weight: bold;
                    font-size: 12px;
                }
            """)
            self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.icon_label.setText((self._display_name or self.provider_name)[:1].upper())
        layout.addWidget(self.icon_label)

        # 名称
        self.name_label = QLabel(self._display_name or self.provider_name)
        self.name_label.setObjectName("providerNameLabel")
        font = QFont()
        font.setPointSize(10)
        self.name_label.setFont(font)
        layout.addWidget(self.name_label, stretch=1)
        
        # 状态标签 (ON/OFF)
        self.status_label = QLabel("ON" if self.is_active else "OFF")
        self.status_label.setObjectName("providerStatusLabel")
        self.status_label.setFixedSize(36, 20)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_status_style()
        layout.addWidget(self.status_label)
        
        layout.addSpacing(4)
    
    def _update_status_style(self):
        """更新状态标签样式"""
        if self.is_active:
            self.status_label.setStyleSheet("""
                QLabel#providerStatusLabel {
                    background-color: rgba(0, 200, 83, 0.15);
                    color: #00C853;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px 6px;
                }
            """)
        else:
            self.status_label.setStyleSheet("""
                QLabel#providerStatusLabel {
                    background-color: rgba(158, 158, 158, 0.15);
                    color: #9E9E9E;
                    border-radius: 10px;
                    font-size: 10px;
                    font-weight: bold;
                    padding: 2px 6px;
                }
            """)
    
    def _update_style(self):
        """更新选中/悬停样式"""
        if self.is_selected:
            self.setStyleSheet("""
                QWidget#providerListItem {
                    background-color: {controlFillSelected};
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget#providerListItem {
                    background-color: transparent;
                    border-radius: 8px;
                }
                QWidget#providerListItem:hover {
                    background-color: {controlFillHover};
                }
            """)
    
    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_style()
    
    def set_active(self, active: bool):
        self.is_active = active
        self.status_label.setText("ON" if active else "OFF")
        self._update_status_style()
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.provider_name)
        super().mousePressEvent(event)


class CollapsibleGroup(QWidget):
    """可折叠分组组件"""
    
    toggled = Signal(bool)  # 展开/收起状态
    
    def __init__(self, title: str, count: int = 0, parent=None):
        super().__init__(parent)
        self.title = title
        self.count = count
        self.is_expanded = True
        
        self._init_ui()
    
    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 头部按钮
        self.header = QPushButton()
        self.header.setObjectName("collapsibleHeader")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(12, 10, 12, 10)
        
        # 展开/收起图标
        self.arrow_label = QLabel("▼")
        self.arrow_label.setObjectName("collapsibleArrow")
        self.arrow_label.setFixedWidth(16)
        header_layout.addWidget(self.arrow_label)
        
        # 标题
        self.title_label = QLabel(self.title)
        self.title_label.setObjectName("collapsibleTitle")
        font = QFont()
        font.setPointSize(10)
        font.setBold(True)
        self.title_label.setFont(font)
        header_layout.addWidget(self.title_label, stretch=1)
        
        # 数量标签
        if self.count > 0:
            self.count_label = QLabel(str(self.count))
            self.count_label.setObjectName("collapsibleCount")
            self.count_label.setFixedSize(24, 18)
            self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            header_layout.addWidget(self.count_label)
        
        header_layout.addSpacing(4)
        
        self.header.clicked.connect(self._on_header_clicked)
        self.main_layout.addWidget(self.header)
        
        # 内容区域
        self.content_widget = QWidget()
        self.content_widget.setObjectName("collapsibleContent")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 8, 0, 8)
        self.content_layout.setSpacing(4)
        self.main_layout.addWidget(self.content_widget)
    
    def _on_header_clicked(self):
        self.is_expanded = not self.is_expanded
        self.header.setChecked(self.is_expanded)
        self.content_widget.setVisible(self.is_expanded)
        self.arrow_label.setText("▼" if self.is_expanded else "▶")
        self.toggled.emit(self.is_expanded)
    
    def add_widget(self, widget: QWidget):
        """添加内容控件"""
        self.content_layout.addWidget(widget)
    
    def set_expanded(self, expanded: bool):
        self.is_expanded = expanded
        self.header.setChecked(expanded)
        self.content_widget.setVisible(expanded)
        self.arrow_label.setText("▼" if expanded else "▶")


class ModelListItem(QWidget):
    """模型列表项 - 带操作按钮"""
    
    settings_clicked = Signal(str)  # model_id
    pin_clicked = Signal(str)  # model_id
    delete_clicked = Signal(str)  # model_id
    
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
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        
        # 模型图标
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(20, 20)
        if icon_path:
            self.icon_label.setPixmap(QPixmap(icon_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            # 默认图标
            self.icon_label.setStyleSheet("""
                QLabel {
                    background-color: {accent};
                    border-radius: 4px;
                    color: white;
                    font-size: 10px;
                }
            """)
            self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.icon_label.setText(self.model_name[:1].upper())
        layout.addWidget(self.icon_label)
        
        # 模型名称
        self.name_label = QLabel(self.model_name)
        self.name_label.setObjectName("modelNameLabel")
        layout.addWidget(self.name_label, stretch=1)
        
        # 操作按钮
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
    
    def set_pinned(self, pinned: bool):
        self.is_pinned = pinned
        self.pin_btn.setText("📌" if pinned else "📍")
        self.pin_btn.setToolTip("取消固定" if pinned else "固定")
    
    def enterEvent(self, event):
        self.setStyleSheet("""
            QWidget#modelListItem {
                background-color: {controlFillHover};
                border-radius: 6px;
            }
        """)
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.setStyleSheet("""
            QWidget#modelListItem {
                background-color: transparent;
                border-radius: 6px;
            }
        """)
        super().leaveEvent(event)


class ActionButton(QPushButton):
    """操作按钮 - 用于余额充值、费用账单等"""
    
    def __init__(self, text: str, icon: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("actionButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(32)
        
        if icon:
            self.setText(f"{icon} {text}")
        else:
            self.setText(text)


class IconLineEdit(QWidget):
    """带图标的输入框"""
    
    def __init__(self, placeholder: str = "", icon: Optional[str] = None, 
                 is_password: bool = False, parent=None):
        super().__init__(parent)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.line_edit = QLineEdit()
        self.line_edit.setObjectName("iconLineEdit")
        self.line_edit.setPlaceholderText(placeholder)
        if is_password:
            self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
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
    """左侧设置分类项"""
    
    clicked = Signal(str)  # category_name
    
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
        
        # 图标
        self.icon_label = QLabel(icon)
        self.icon_label.setObjectName("categoryIcon")
        self.icon_label.setFixedWidth(20)
        layout.addWidget(self.icon_label)
        
        # 文本
        self.text_label = QLabel(text)
        self.text_label.setObjectName("categoryText")
        layout.addWidget(self.text_label, stretch=1)
        
        self._update_style()
    
    def set_selected(self, selected: bool):
        self.is_selected = selected
        self._update_style()
    
    def _update_style(self):
        if self.is_selected:
            self.setStyleSheet("""
                QWidget#settingsCategoryItem {
                    background-color: {controlFillSelected};
                    border-radius: 8px;
                }
                QLabel#categoryIcon, QLabel#categoryText {
                    color: {accent};
                }
            """)
        else:
            self.setStyleSheet("""
                QWidget#settingsCategoryItem {
                    background-color: transparent;
                    border-radius: 8px;
                }
                QWidget#settingsCategoryItem:hover {
                    background-color: {controlFillHover};
                }
                QLabel#categoryIcon, QLabel#categoryText {
                    color: {textPrimary};
                }
            """)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.category)
        super().mousePressEvent(event)


class ModelDetailItem(QWidget):
    """模型详情列表项 - 显示模型完整信息
    
    显示内容：
    - 模型图标/首字母
    - 模型名称
    - 上下文长度
    - 模型类别标签 [Chat] [Embedding]
    - 能力标签 [Vision] [Thinking] [Tools]
    """
    
    clicked = Signal(str)  # model_id
    
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
        
        self._init_ui(
            support_chat=support_chat,
            support_embedding=support_embedding,
            support_vision=support_vision,
            support_thinking=support_thinking,
            support_tools=support_tools
        )
        self._update_style()
    
    def _init_ui(self, support_chat: bool, support_embedding: bool,
                 support_vision: bool, support_thinking: bool, support_tools: bool):
        from utils.style_qss import get_style_qss
        qss = get_style_qss().get_color_dict()
        
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 8, 12, 8)
        main_layout.setSpacing(12)
        
        # 左侧：图标
        icon_label = QLabel()
        icon_label.setFixedSize(36, 36)
        icon_label.setObjectName("modelIcon")
        # 使用首字母作为图标
        icon_text = self.model_name[:1].upper() if self.model_name else "?"
        icon_label.setText(icon_text)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet(f"""
            QLabel#modelIcon {{
                background-color: {qss['accent']};
                border-radius: 8px;
                color: white;
                font-size: 14px;
                font-weight: bold;
            }}
        """)
        main_layout.addWidget(icon_label)
        
        # 中间：名称和上下文长度
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        # 模型名称
        name_label = QLabel(self.model_name or self.model_id)
        name_label.setObjectName("modelName")
        name_label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 14px; font-weight: 500;")
        info_layout.addWidget(name_label)
        
        # 上下文长度
        if self.context_length:
            ctx_text = self._format_context_length(self.context_length)
            ctx_label = QLabel(f"上下文: {ctx_text}")
            ctx_label.setObjectName("modelContext")
            ctx_label.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 11px;")
            info_layout.addWidget(ctx_label)
        
        info_layout.addStretch()
        main_layout.addLayout(info_layout, 1)
        
        # 右侧：标签组
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(4)
        
        # 模型类别标签
        if support_chat:
            chat_tag = self._create_tag("Chat", "category", qss)
            tags_layout.addWidget(chat_tag)
        
        if support_embedding:
            emb_tag = self._create_tag("Embedding", "category", qss)
            tags_layout.addWidget(emb_tag)
        
        # 能力标签
        if support_vision:
            vision_tag = self._create_tag("Vision", "vision", qss)
            tags_layout.addWidget(vision_tag)
        
        if support_thinking:
            thinking_tag = self._create_tag("Thinking", "thinking", qss)
            tags_layout.addWidget(thinking_tag)
        
        if support_tools:
            tools_tag = self._create_tag("Tools", "tools", qss)
            tags_layout.addWidget(tools_tag)
        
        tags_layout.addStretch()
        main_layout.addLayout(tags_layout)
    
    def _create_tag(self, text: str, tag_type: str, qss: dict) -> QLabel:
        """创建标签"""
        tag = QLabel(text)
        tag.setObjectName("modelTag")
        tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 根据标签类型设置颜色
        colors = {
            "category": ("#2196F3", "#E3F2FD"),  # 蓝色 - Chat/Embedding
            "vision": ("#9C27B0", "#F3E5F5"),    # 紫色 - Vision
            "thinking": ("#FF9800", "#FFF3E0"),  # 橙色 - Thinking
            "tools": ("#009688", "#E0F2F1"),     # 青色 - Tools
        }
        
        text_color, bg_color = colors.get(tag_type, (qss['textSecondary'], qss['controlFill']))
        
        tag.setStyleSheet(f"""
            QLabel#modelTag {{
                color: {text_color};
                background-color: {bg_color};
                border-radius: 4px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }}
        """)
        return tag
    
    def _format_context_length(self, length: int) -> str:
        """格式化上下文长度显示"""
        if length < 1000:
            return f"{length}"
        elif length < 1000000:
            return f"{length // 1000}K"
        else:
            return f"{length / 1000000:.1f}M"
    
    def _update_style(self):
        """更新悬停样式"""
        pass  # 样式通过 QSS 控制
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.model_id)
        super().mousePressEvent(event)
