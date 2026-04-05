# src/ui/dialog/llm_settings_dialog.py
"""LLM 设置对话框 - 两栏布局（右侧显示 Provider Logo）."""
from typing import Optional, Dict, List
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QWidget, QInputDialog, QRadioButton,
    QToolButton, QStackedWidget, QSizePolicy, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QEvent, QObject
from PySide6.QtGui import QFont, QResizeEvent, QPixmap, QPainter, QPainterPath

from core.llm.config import LLMConfig, ProviderConfig
from core.llm.providers import get_all_provider_types
from core.llm.provider_interface import ModelInfo
from core.llm import get_llm_provider, get_llm_plugin_service
from ui.dialog.llm_settings_components import (
    CollapsibleGroup, ActionButton, ModelDetailItem, ProviderListItemWidget
)
from utils.style_qss import get_style_qss


class LLMSettingsDialog(QDialog):
    """LLM 设置对话框 - 两栏布局."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 设置")
        self.setObjectName("llmSettingsDialog")
        self.setMinimumSize(900, 600)
        self.resize(1050, 700)

        self._llm_config = LLMConfig()
        self._llm_provider = get_llm_provider()
        self._current_provider_name: Optional[str] = None
        self._provider_items: Dict[str, QListWidgetItem] = {}
        self._fetched_models: Dict[str, List[ModelInfo]] = {}
        self._is_dirty = False
        self._left_panel_width = 250

        # 主题相关
        self._style_qss = get_style_qss()
        self._colors = self._style_qss.colors()

        # Key widget references
        self._api_key_edit: Optional[QLineEdit] = None
        self._api_url_edit: Optional[QLineEdit] = None
        self._enable_toggle: Optional[QCheckBox] = None
        self._chat_model_combo: Optional[QComboBox] = None
        self._emb_model_combo: Optional[QComboBox] = None
        self._preset_view: Optional[QWidget] = None
        self._api_view: Optional[QWidget] = None
        self._preset_radio: Optional[QRadioButton] = None
        self._api_radio: Optional[QRadioButton] = None
        self._save_btn: Optional[QPushButton] = None
        self._fetch_btn: Optional[QPushButton] = None
        self._fetched_list_layout: Optional[QVBoxLayout] = None
        self._fetched_list_scroll: Optional[QScrollArea] = None
        self._model_stack: Optional[QStackedWidget] = None
        self._provider_list_widget: Optional[QListWidget] = None
        self._detail_layout: Optional[QVBoxLayout] = None
        self._header_logo_label: Optional[QLabel] = None

        # 需要动态更新样式的控件列表
        self._dynamic_widgets: List[QWidget] = []

        self._init_ui()
        self._load_data()

    def _get_color(self, name: str, default: str = "#000000") -> str:
        """获取当前主题的颜色."""
        return self._colors.get(name, default)

    def _update_theme_colors(self):
        """更新主题颜色."""
        self._colors = self._style_qss.colors()

    # ------------------------------------------------------------------ #
    # UI Construction                                                       #
    # ------------------------------------------------------------------ #

    def _init_ui(self) -> None:
        """初始化主界面布局."""
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        left = self._create_left_panel()
        right = self._create_right_panel()

        main_layout.addWidget(left)
        main_layout.addWidget(right, 1)

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板：Provider 列表."""
        widget = QWidget()
        widget.setObjectName("leftPanel")
        widget.setFixedWidth(self._left_panel_width)
        
        # 使用动态颜色
        bg_color = self._get_color('window', '#FAFAFA')
        border_color = self._get_color('borderLight', '#E0E0E0')
        item_bg = self._get_color('base', '#FFFFFF')
        item_selected = self._get_color('controlFillSelected', '#E3F2FD')
        item_hover = self._get_color('controlFillHover', '#F5F5F5')
        
        widget.setStyleSheet(f"""
            QWidget#leftPanel {{
                background-color: {bg_color};
                border-right: 1px solid {border_color};
            }}
        """)

        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header = self._create_left_header()
        layout.addWidget(header)

        self._provider_list_widget = QListWidget()
        self._provider_list_widget.setObjectName("providerListWidget")
        self._provider_list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._provider_list_widget.setSpacing(2)
        self._provider_list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self._provider_list_widget.setStyleSheet(f"""
            QListWidget {{
                outline: none;
                border: none;
                background-color: transparent;
            }}
            QListWidget::item {{
                padding: 0px;
                margin: 2px 8px;
                border: none;
                border-radius: 6px;
                min-height: 44px;
                background-color: {item_bg};
            }}
            QListWidget::item:selected {{
                background-color: {item_selected};
            }}
            QListWidget::item:hover {{
                background-color: {item_hover};
            }}
            QListWidget::item:selected:hover {{
                background-color: {self._get_color('accentLight', '#BBDEFB')};
            }}
        """)
        self._provider_list_widget.currentItemChanged.connect(
            self._on_provider_current_changed
        )
        self._provider_list_widget.installEventFilter(self)
        layout.addWidget(self._provider_list_widget, 1)

        # 添加供应商按钮
        add_btn = QPushButton("+ 添加供应商")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(44)
        btn_bg = self._get_color('base', '#FFFFFF')
        btn_border = self._get_color('border', '#CCCCCC')
        btn_color = self._get_color('textSecondary', '#666666')
        btn_hover_bg = self._get_color('controlFillHover', '#F5F5F5')
        btn_hover_color = self._get_color('textPrimary', '#333333')
        
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {btn_bg};
                border: 1px dashed {btn_border};
                border-radius: 6px;
                color: {btn_color};
                font-size: 13px;
            }}
            QPushButton:hover {{
                background-color: {btn_hover_bg};
                border-color: {btn_hover_color};
                color: {btn_hover_color};
            }}
        """)
        add_btn.clicked.connect(self._on_add_provider)
        layout.addWidget(add_btn)

        return widget

    def _create_left_header(self) -> QWidget:
        """创建左侧面板头部."""
        header = QWidget()
        header.setFixedHeight(52)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label = QLabel("模型服务")
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {self._get_color('textPrimary', '#000000')};")
        header_layout.addWidget(title_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {self._get_color('borderLight', '#E0E0E0')};")
        header_layout.addWidget(divider)

        return header

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板：Provider 配置详情."""
        widget = QWidget()
        bg_color = self._get_color('window', '#FFFFFF')
        widget.setStyleSheet(f"background-color: {bg_color};")
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {bg_color};")

        content = QWidget()
        content.setStyleSheet(f"background-color: {bg_color};")
        self._detail_layout = QVBoxLayout(content)
        self._detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._detail_layout.setSpacing(20)
        self._detail_layout.setContentsMargins(24, 24, 24, 24)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        bottom = self._create_bottom_bar()
        layout.addWidget(bottom)

        return widget

    def _create_bottom_bar(self) -> QWidget:
        """创建底部栏：使用统计 + 保存/取消按钮."""
        widget = QWidget()
        widget.setObjectName("bottomBar")
        widget.setFixedHeight(52)
        
        bg_color = self._get_color('window', '#FFFFFF')
        border_color = self._get_color('borderLight', '#E0E0E0')
        text_color = self._get_color('textPrimary', '#000000')
        
        widget.setStyleSheet(f"""
            QWidget#bottomBar {{
                background-color: {bg_color};
                border-top: 1px solid {border_color};
            }}
            QLabel {{
                color: {text_color};
            }}
        """)

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(24, 0, 24, 0)

        usage_text = self._get_usage_text()
        usage_label = QLabel(usage_text)
        layout.addWidget(usage_label)

        layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(30)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        # 保存按钮 - 直接在代码中设置样式表，确保样式生效
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(30)
        save_btn.setEnabled(False)
        save_btn.clicked.connect(self._on_save)
        
        # 获取当前主题颜色
        accent = self._get_color('accent', '#0078D4')
        accent_light = self._get_color('accentLight', '#4CC2FF')
        accent_dark = self._get_color('accentDark', '#005A9E')
        button_bg = self._get_color('button', '#F3F3F3')
        text_disabled = self._get_color('textDisabled', '#6D6D6D')
        border_light = self._get_color('borderLight', '#CCCCCC')
        
        # 设置样式表 - 禁用状态：灰色，启用状态：蓝色
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {button_bg};
                border: 1px solid {border_light};
                border-radius: 3px;
                color: {text_disabled};
                padding: 4px 16px;
                font-weight: 500;
                min-width: 60px;
            }}
            QPushButton:hover {{
                background-color: {button_bg};
                border: 1px solid {border_light};
                color: {text_disabled};
            }}
            QPushButton:pressed {{
                background-color: {button_bg};
                border: 1px solid {border_light};
                color: {text_disabled};
            }}
            QPushButton:enabled {{
                background-color: {accent};
                border: 1px solid {accent};
                color: white;
            }}
            QPushButton:enabled:hover {{
                background-color: {accent_light};
                border: 1px solid {accent_light};
                color: white;
            }}
            QPushButton:enabled:pressed {{
                background-color: {accent_dark};
                border: 1px solid {accent_dark};
                color: white;
            }}
        """)
        self._save_btn = save_btn
        layout.addWidget(save_btn)

        return widget

    def _get_usage_text(self) -> str:
        """获取使用统计文本."""
        try:
            svc = get_llm_plugin_service()
            stats = svc.get_usage_stats()
            total = stats.total_cost
            return f"累计使用：${total:.4f}"
        except Exception:
            return "累计使用：--"

    # ------------------------------------------------------------------ #
    # Event Handling                                                        #
    # ------------------------------------------------------------------ #

    def changeEvent(self, event: QEvent) -> None:
        """处理主题变化事件."""
        if event.type() == QEvent.Type.PaletteChange:
            self._update_theme_colors()
            self._refresh_ui_theme()
        super().changeEvent(event)

    def _refresh_ui_theme(self) -> None:
        """刷新UI主题."""
        # 重新获取颜色
        self._colors = self._style_qss.colors()
        
        # 重新创建面板
        # 注意：由于Qt限制，简单的做法是关闭对话框重新打开
        # 但这里我们尝试更新关键控件的颜色
        
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """事件过滤器：监听 QListWidget 大小变化."""
        if (
            obj is self._provider_list_widget
            and event.type() == QEvent.Type.Resize
        ):
            self._update_provider_list_item_sizes()
        return super().eventFilter(obj, event)

    def _update_provider_list_item_sizes(self) -> None:
        """更新所有 Provider 列表项的尺寸."""
        if not self._provider_list_widget:
            return

        list_width = self._provider_list_widget.viewport().width()
        item_margin = 16

        for i in range(self._provider_list_widget.count()):
            item = self._provider_list_widget.item(i)
            if item:
                new_size = QSize(list_width - item_margin, item.sizeHint().height())
                item.setSizeHint(new_size)

    # ------------------------------------------------------------------ #
    # Logo Helper                                                           #
    # ------------------------------------------------------------------ #

    def _load_circular_pixmap(self, logo_path: str, size: int) -> QPixmap:
        """加载并裁剪为圆形图片 - 保持原始比例居中显示.
        
        Args:
            logo_path: 图片路径
            size: 目标尺寸
            
        Returns:
            QPixmap: 圆形图片
        """
        pixmap = QPixmap(logo_path)
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

    def _get_logo_path(self, provider_type: str) -> Optional[str]:
        """获取 Provider Logo 路径.
        
        Args:
            provider_type: Provider 类型
            
        Returns:
            Optional[str]: Logo 路径
        """
        logo_base = Path(__file__).resolve().parent.parent.parent / "core" / "llm" / "providers"
        logo_path = logo_base / f"{provider_type}.png"
        return str(logo_path) if logo_path.exists() else None

    # ------------------------------------------------------------------ #
    # Data Loading                                                          #
    # ------------------------------------------------------------------ #

    def _load_data(self) -> None:
        """加载 Provider 列表并选中第一个."""
        self._refresh_provider_list()
        for name in self._llm_config.get_all_providers():
            cached = self._llm_config.load_models_cache(name)
            if cached:
                self._fetched_models[name] = [ModelInfo.from_dict(m) for m in cached]
        
        providers = self._llm_config.get_all_providers()
        if providers:
            first_name = next(iter(providers))
            item = self._provider_items.get(first_name)
            if item:
                self._provider_list_widget.setCurrentItem(item)

    def _refresh_provider_list(self) -> None:
        """重建左侧 Provider 列表."""
        if not self._provider_list_widget:
            return

        self._provider_list_widget.clear()
        self._provider_items.clear()

        providers = self._llm_config.get_all_providers()
        for name, config in providers.items():
            item = QListWidgetItem()
            item.setText("")
            item.setData(Qt.ItemDataRole.UserRole, name)
            item.setData(Qt.ItemDataRole.UserRole + 1, config.enabled_chat)
            self._provider_list_widget.addItem(item)
            
            logo_path = self._get_logo_path(config.provider_type)
            widget = ProviderListItemWidget(
                name=config.name or name,
                logo_path=logo_path,
                is_enabled=bool(config.enabled_chat)
            )
            self._provider_list_widget.setItemWidget(item, widget)
            self._provider_items[name] = item

        QTimer.singleShot(0, self._update_provider_list_item_sizes)

    def _refresh_provider_item_widget(self, name: str) -> None:
        """刷新单个 Provider 列表项的控件."""
        item = self._provider_items.get(name)
        if not item or not self._provider_list_widget:
            return
            
        config = self._llm_config.get_provider(name)
        if not config:
            return
            
        logo_path = self._get_logo_path(config.provider_type)
        
        is_enabled = bool(config.enabled_chat)
        # 如果是当前选中的 provider，优先读取 UI 实时状态（配置可能未保存）
        if name == self._current_provider_name and self._enable_toggle is not None:
            is_enabled = self._enable_toggle.isChecked()
        widget = ProviderListItemWidget(
            name=config.name or name,
            logo_path=logo_path,
            is_enabled=is_enabled
        )
        self._provider_list_widget.setItemWidget(item, widget)
        self._update_provider_list_item_sizes()

    # ------------------------------------------------------------------ #
    # Provider Selection                                                   #
    # ------------------------------------------------------------------ #

    def _on_provider_current_changed(
        self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]
    ) -> None:
        """Provider 选中切换事件."""
        if not current:
            return
            
        provider_name = current.data(Qt.ItemDataRole.UserRole)
        if not provider_name:
            return

        if self._is_dirty and self._current_provider_name:
            self._save_current_provider()

        self._current_provider_name = provider_name
        self._show_provider_detail(provider_name)
        self._is_dirty = False
        if self._save_btn:
            self._save_btn.setEnabled(False)

    def _on_provider_clicked(self, provider_name: str) -> None:
        """Provider 点击事件（兼容旧接口）."""
        if provider_name in self._provider_items and self._provider_list_widget:
            self._provider_list_widget.setCurrentItem(self._provider_items[provider_name])

    # ------------------------------------------------------------------ #
    # Provider Detail View                                                 #
    # ------------------------------------------------------------------ #

    def _show_provider_detail(self, provider_name: str) -> None:
        """显示 Provider 配置详情."""
        if not self._detail_layout:
            return

        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        self._build_header_section(config)
        self._add_divider()

        self._build_api_key_section(config)
        self._add_divider()

        self._build_api_url_section(config)
        self._add_divider()

        self._build_validate_section()
        self._add_divider()

        self._build_model_list_section(provider_name, config)
        self._add_divider()

        self._build_model_selection_section(config)

        self._populate_model_combos(provider_name, config)

    def _build_header_section(self, config: ProviderConfig) -> None:
        """构建头部区域：Logo + 名称 + 启用切换.
        
        Args:
            config: Provider 配置
        """
        if not self._detail_layout:
            return

        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Logo - 关键修复：显示 Provider Logo（圆形 64x64）
        self._header_logo_label = QLabel()
        self._header_logo_label.setFixedSize(64, 64)
        self._header_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_path = self._get_logo_path(config.provider_type)
        if logo_path:
            pixmap = self._load_circular_pixmap(logo_path, 64)
            if not pixmap.isNull():
                self._header_logo_label.setPixmap(pixmap)
            else:
                self._set_header_logo_fallback(config.name)
        else:
            self._set_header_logo_fallback(config.name)
        header_layout.addWidget(self._header_logo_label)

        # Name + subtitle
        name_layout = QVBoxLayout()
        name_layout.setSpacing(4)

        text_primary = self._get_color('textPrimary', '#333333')
        text_secondary = self._get_color('textSecondary', '#666666')
        
        name_label = QLabel(config.name or "")
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setStyleSheet(f"color: {text_primary};")
        name_layout.addWidget(name_label)

        type_label = QLabel(config.provider_type)
        type_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        name_layout.addWidget(type_label)

        name_layout.addStretch()
        header_layout.addLayout(name_layout, 1)

        # Enable toggle
        self._enable_toggle = QCheckBox("启用")
        self._enable_toggle.setChecked(config.enabled_chat)
        self._enable_toggle.stateChanged.connect(self._mark_dirty)
        
        checkbox_bg = self._get_color('base', '#FFFFFF')
        checkbox_border = self._get_color('border', '#CCCCCC')
        accent = self._get_color('accent', '#4A90D9')
        
        self._enable_toggle.setStyleSheet(f"""
            QCheckBox {{
                color: {text_primary};
                font-size: 13px;
                font-weight: 500;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid {checkbox_border};
                background-color: {checkbox_bg};
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent};
                border-color: {accent};
            }}
        """)
        header_layout.addWidget(self._enable_toggle)

        self._detail_layout.addWidget(header_widget)

    def _set_header_logo_fallback(self, name: Optional[str]) -> None:
        """设置 header Logo fallback（首字母圆形）.
        
        Args:
            name: Provider 名称
        """
        if not self._header_logo_label:
            return
            
        initial = name[:1].upper() if name else "?"
        accent = self._get_color('accent', '#4A90D9')
        self._header_logo_label.setText(initial)
        self._header_logo_label.setStyleSheet(f"""
            QLabel {{
                background-color: {accent};
                border-radius: 32px;
                color: white;
                font-size: 24px;
                font-weight: bold;
            }}
        """)

    def _build_api_key_section(self, config: ProviderConfig) -> None:
        """构建 API Key 输入区."""
        if not self._detail_layout:
            return

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        text_primary = self._get_color('textPrimary', '#333333')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')
        link_color = self._get_color('link', '#4A90D9')
        hover_bg = self._get_color('controlFillHover', '#F5F5F5')

        label = QLabel("API 密钥")
        label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("请输入 API 密钥")
        self._api_key_edit.setText(config.api_key or "")
        self._api_key_edit.textChanged.connect(self._mark_dirty)
        self._api_key_edit.setStyleSheet(f"""
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
        row.addWidget(self._api_key_edit, 1)

        eye_btn = QToolButton()
        eye_btn.setText("👁")
        eye_btn.setFixedSize(36, 36)
        eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        eye_btn.clicked.connect(self._toggle_api_key_visibility)
        eye_btn.setStyleSheet(f"""
            QToolButton {{
                border: none;
                background-color: transparent;
                font-size: 16px;
            }}
            QToolButton:hover {{
                background-color: {hover_bg};
                border-radius: 6px;
            }}
        """)
        row.addWidget(eye_btn)

        layout.addLayout(row)

        link_label = QLabel("<a href='#'>点击这里获取密钥</a>")
        link_label.setCursor(Qt.CursorShape.PointingHandCursor)
        link_label.setTextFormat(Qt.TextFormat.RichText)
        link_label.setStyleSheet(f"color: {link_color}; font-size: 12px;")
        link_label.linkActivated.connect(lambda: self._open_provider_link(config.provider_type))
        layout.addWidget(link_label)

        self._detail_layout.addWidget(widget)

    def _build_api_url_section(self, config: ProviderConfig) -> None:
        """构建 API URL 输入区."""
        if not self._detail_layout:
            return

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        text_primary = self._get_color('textPrimary', '#333333')
        text_secondary = self._get_color('textSecondary', '#999999')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')

        label = QLabel("API 地址")
        label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        layout.addWidget(label)

        self._api_url_edit = QLineEdit()
        self._api_url_edit.setPlaceholderText("例如：https://api.example.com/v1")
        self._api_url_edit.setText(config.base_url or "")
        self._api_url_edit.textChanged.connect(self._mark_dirty)
        self._api_url_edit.setStyleSheet(f"""
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
        layout.addWidget(self._api_url_edit)

        preview_label = QLabel("请求将发送至此地址")
        preview_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        layout.addWidget(preview_label)

        self._detail_layout.addWidget(widget)

    def _build_validate_section(self) -> None:
        """构建检测供应商有效性按钮区域."""
        if not self._detail_layout:
            return

        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        validate_btn = ActionButton("检测供应商有效性", "✓")
        validate_btn.clicked.connect(self._on_validate_provider)
        layout.addWidget(validate_btn)

        layout.addStretch()
        self._detail_layout.addWidget(widget)

    def _build_model_list_section(
        self, provider_name: str, config: ProviderConfig
    ) -> None:
        """构建模型列表区：预设 / API 切换."""
        if not self._detail_layout:
            return

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        text_primary = self._get_color('textPrimary', '#333333')

        label = QLabel("模型列表")
        label.setFont(QFont("", -1, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {text_primary};")
        layout.addWidget(label)

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(16)

        self._preset_radio = QRadioButton("使用本地预设列表")
        self._api_radio = QRadioButton("从 API 获取")

        radio_layout.addWidget(self._preset_radio)
        radio_layout.addWidget(self._api_radio)
        radio_layout.addStretch()
        layout.addLayout(radio_layout)

        force_preset = provider_name in ("minimax", "glm")
        if force_preset:
            self._preset_radio.setChecked(True)
            self._preset_radio.setEnabled(False)
            self._api_radio.setEnabled(False)
        else:
            presets = self._get_preset_models(provider_name)
            self._preset_radio.toggled.connect(self._on_model_source_changed)
            self._api_radio.toggled.connect(self._on_model_source_changed)
            if presets:
                self._preset_radio.setChecked(True)
            else:
                self._api_radio.setChecked(True)

        self._model_stack = QStackedWidget()
        self._model_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )

        self._preset_view = QWidget()
        preset_layout = QVBoxLayout(self._preset_view)
        preset_layout.setSpacing(4)
        preset_layout.setContentsMargins(0, 0, 0, 0)

        self._populate_preset_view(preset_layout, provider_name)
        self._model_stack.addWidget(self._preset_view)

        self._api_view = QWidget()
        api_layout = QVBoxLayout(self._api_view)
        api_layout.setSpacing(8)
        api_layout.setContentsMargins(0, 0, 0, 0)

        self._populate_api_view(api_layout, provider_name)
        self._model_stack.addWidget(self._api_view)

        if force_preset or (not force_preset and self._preset_radio.isChecked()):
            self._model_stack.setCurrentWidget(self._preset_view)
        else:
            self._model_stack.setCurrentWidget(self._api_view)

        layout.addWidget(self._model_stack)
        self._detail_layout.addWidget(widget)

    def _populate_preset_view(
        self, layout: QVBoxLayout, provider_name: str
    ) -> None:
        """填充预设模型视图."""
        presets = self._get_preset_models(provider_name)
        chat_models = [m for m in presets if m.support_chat]
        emb_models = [m for m in presets if m.support_embedding]
        vision_models = [m for m in presets if m.support_vision]
        other_models = [
            m
            for m in presets
            if not (m.support_chat or m.support_embedding or m.support_vision)
        ]

        categories: List[tuple[str, List[ModelInfo]]] = []
        if chat_models:
            categories.append(("聊天模型 Chat", chat_models))
        if emb_models:
            categories.append(("嵌入模型 Embedding", emb_models))
        if vision_models:
            categories.append(("视觉模型 Vision", vision_models))
        if other_models:
            categories.append(("其他模型", other_models))

        text_secondary = self._get_color('textSecondary', '#666666')
        
        if categories:
            for cat_name, models in categories:
                group = CollapsibleGroup(cat_name, len(models))
                for m in models:
                    model_widget = self._make_preset_model_widget(m)
                    group.add_widget(model_widget)
                layout.addWidget(group)
        else:
            empty_label = QLabel("该供应商暂无预设模型列表，请使用「从 API 获取」")
            empty_label.setStyleSheet(f"color: {text_secondary};")
            layout.addWidget(empty_label)

        layout.addStretch()

    def _populate_api_view(
        self, layout: QVBoxLayout, provider_name: str
    ) -> None:
        """填充 API 模型视图."""
        fetch_row = QHBoxLayout()
        self._fetch_btn = QPushButton("从 API 获取模型列表")
        self._fetch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fetch_btn.clicked.connect(lambda: self._on_fetch_models(provider_name))
        fetch_row.addWidget(self._fetch_btn)
        fetch_row.addStretch()
        layout.addLayout(fetch_row)

        self._fetched_list_scroll = QScrollArea()
        self._fetched_list_scroll.setFixedHeight(300)
        self._fetched_list_scroll.setWidgetResizable(True)
        self._fetched_list_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._fetched_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        
        fetched_container = QWidget()
        self._fetched_list_layout = QVBoxLayout(fetched_container)
        self._fetched_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._fetched_list_layout.setSpacing(2)
        self._fetched_list_layout.setContentsMargins(4, 4, 4, 4)
        self._fetched_list_scroll.setWidget(fetched_container)
        layout.addWidget(self._fetched_list_scroll)

        if provider_name in self._fetched_models:
            self._populate_fetched_list(provider_name)

    def _build_model_selection_section(self, config: ProviderConfig) -> None:
        """构建模型选择区：当前聊天模型 + 当前 Embedding 模型."""
        if not self._detail_layout:
            return

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        text_primary = self._get_color('textPrimary', '#333333')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')

        chat_row = QHBoxLayout()
        chat_label = QLabel("当前聊天模型")
        chat_label.setFixedWidth(120)
        chat_label.setStyleSheet(f"color: {text_primary};")
        self._chat_model_combo = QComboBox()
        self._chat_model_combo.setMinimumWidth(300)
        self._chat_model_combo.currentTextChanged.connect(self._mark_dirty)
        self._chat_model_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QComboBox:focus {{
                border-color: {accent};
            }}
        """)
        chat_row.addWidget(chat_label)
        chat_row.addWidget(self._chat_model_combo, 1)
        layout.addLayout(chat_row)

        emb_row = QHBoxLayout()
        emb_label = QLabel("当前 Embedding 模型")
        emb_label.setFixedWidth(120)
        emb_label.setStyleSheet(f"color: {text_primary};")
        self._emb_model_combo = QComboBox()
        self._emb_model_combo.setMinimumWidth(300)
        self._emb_model_combo.currentTextChanged.connect(self._mark_dirty)
        self._emb_model_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {border_color};
                border-radius: 6px;
                font-size: 13px;
                color: {text_primary};
            }}
            QComboBox:focus {{
                border-color: {accent};
            }}
        """)
        emb_row.addWidget(emb_label)
        emb_row.addWidget(self._emb_model_combo, 1)
        layout.addLayout(emb_row)

        self._detail_layout.addWidget(widget)

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def _add_divider(self) -> None:
        """添加分隔线."""
        if not self._detail_layout:
            return
            
        border_color = self._get_color('borderLight', '#E0E0E0')
        
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setFixedHeight(1)
        div.setStyleSheet(f"background-color: {border_color};")
        self._detail_layout.addWidget(div)

    def _make_preset_model_widget(self, model: ModelInfo) -> QWidget:
        """创建预设模型列表项."""
        item = ModelDetailItem(
            model_id=model.id,
            model_name=model.name or model.id,
            context_length=model.context_length,
            support_chat=model.support_chat,
            support_embedding=model.support_embedding,
            support_vision=model.support_vision,
            support_thinking=getattr(model, "support_thinking", False)
            or "thinking" in model.id.lower(),
            support_tools=model.support_function_calling,
        )
        return item

    def _get_preset_models(self, provider_name: str) -> List[ModelInfo]:
        """获取预设模型列表."""
        models: List[ModelInfo] = []

        if provider_name == "minimax":
            try:
                from core.llm.providers.minimax import MiniMaxProvider

                details = getattr(MiniMaxProvider, "MODEL_DETAILS", {})

                for model_id in getattr(MiniMaxProvider, "CHAT_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=True,
                            support_embedding=False,
                            support_vision=False,
                            support_function_calling=info.get(
                                "support_function_calling", False
                            ),
                            context_length=info.get("context_length", 0),
                        )
                    )

                for model_id in getattr(MiniMaxProvider, "EMBEDDING_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=False,
                            support_embedding=True,
                            support_vision=False,
                            support_function_calling=False,
                            context_length=info.get("context_length", 0),
                        )
                    )
            except Exception:
                pass

        elif provider_name == "glm":
            try:
                from core.llm.providers.glm import GLMProvider

                details = getattr(GLMProvider, "MODEL_DETAILS", {})

                for model_id in getattr(GLMProvider, "CHAT_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=True,
                            support_embedding=False,
                            support_vision=False,
                            support_function_calling=info.get(
                                "support_function_calling", False
                            ),
                            context_length=info.get("context_length", 0),
                        )
                    )

                for model_id in getattr(GLMProvider, "EMBEDDING_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=False,
                            support_embedding=True,
                            support_vision=False,
                            support_function_calling=False,
                            context_length=info.get("context_length", 0),
                        )
                    )

                for model_id in getattr(GLMProvider, "VISION_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=False,
                            support_embedding=False,
                            support_vision=True,
                            support_function_calling=False,
                            context_length=info.get("context_length", 0),
                        )
                    )
            except Exception:
                pass

        return models

    def _populate_model_combos(
        self, provider_name: str, config: ProviderConfig
    ) -> None:
        """填充模型下拉框."""
        if not self._chat_model_combo or not self._emb_model_combo:
            return

        preset_models = self._get_preset_models(provider_name)
        fetched_models = self._fetched_models.get(provider_name, [])

        seen_ids: set[str] = set()
        all_models: List[ModelInfo] = []
        for m in preset_models + fetched_models:
            if m.id not in seen_ids:
                seen_ids.add(m.id)
                all_models.append(m)

        chat_ids = [m.id for m in all_models if m.support_chat]
        emb_ids = [m.id for m in all_models if m.support_embedding]

        self._chat_model_combo.blockSignals(True)
        self._chat_model_combo.clear()
        self._chat_model_combo.addItems(chat_ids)
        if config.chat_model and config.chat_model in chat_ids:
            self._chat_model_combo.setCurrentText(config.chat_model)
        self._chat_model_combo.blockSignals(False)

        self._emb_model_combo.blockSignals(True)
        self._emb_model_combo.clear()
        self._emb_model_combo.addItems(emb_ids)
        if config.embedding_model and config.embedding_model in emb_ids:
            self._emb_model_combo.setCurrentText(config.embedding_model)
        self._emb_model_combo.blockSignals(False)

    def _populate_fetched_list(self, provider_name: str) -> None:
        """填充 API 获取的模型列表."""
        if not self._fetched_list_layout:
            return
            
        models = self._fetched_models.get(provider_name, [])

        while self._fetched_list_layout.count():
            item = self._fetched_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        text_secondary = self._get_color('textSecondary', '#666666')
        
        if not models:
            empty = QLabel("暂无模型，请点击上方按钮获取")
            empty.setStyleSheet(f"color: {text_secondary};")
            self._fetched_list_layout.addWidget(empty)
            return

        for model in models:
            item_widget = self._make_preset_model_widget(model)
            self._fetched_list_layout.addWidget(item_widget)

    def _on_model_source_changed(self, checked: bool) -> None:
        """切换预设/API 视图."""
        if not checked or not self._model_stack:
            return
        if self._preset_radio and self._preset_radio.isChecked() and self._preset_view:
            self._model_stack.setCurrentWidget(self._preset_view)
        elif self._api_view:
            self._model_stack.setCurrentWidget(self._api_view)

    def _on_fetch_models(self, provider_name: str) -> None:
        """触发从 API 获取模型列表."""
        if self._fetch_btn:
            self._fetch_btn.setEnabled(False)
            self._fetch_btn.setText("获取中...")
        QTimer.singleShot(0, lambda: self._do_fetch_models(provider_name))

    def _do_fetch_models(self, provider_name: str) -> None:
        """实际执行从 API 获取模型列表."""
        try:
            models = self._llm_provider.refresh_provider_models(provider_name, force=True)
            self._fetched_models[provider_name] = models
            self._populate_fetched_list(provider_name)
            if self._current_provider_name == provider_name:
                config = self._llm_config.get_provider(provider_name)
                if config:
                    self._populate_model_combos(provider_name, config)
        except Exception as e:
            QMessageBox.warning(
                self, "获取失败", f"无法获取模型列表：{str(e)}"
            )
        finally:
            if self._fetch_btn:
                self._fetch_btn.setEnabled(True)
                self._fetch_btn.setText("从 API 获取模型列表")

    def _on_validate_provider(self) -> None:
        """验证 Provider 配置."""
        if not self._current_provider_name:
            return
        try:
            provider = self._llm_provider.get_provider(self._current_provider_name)
            if provider:
                result = provider.validate_config()
                if result:
                    QMessageBox.information(self, "验证成功", "供应商配置有效。")
                else:
                    QMessageBox.warning(
                        self, "验证失败", "供应商配置无效，请检查 API Key 和 API 地址。"
                    )
            else:
                QMessageBox.warning(self, "验证失败", "Provider 未初始化。")
        except Exception as e:
            QMessageBox.warning(self, "验证失败", f"验证时出错：{str(e)}")

    def _mark_dirty(self) -> None:
        """标记为已修改."""
        self._is_dirty = True
        if self._save_btn:
            self._save_btn.setEnabled(True)
        if self._current_provider_name:
            self._refresh_provider_item_widget(self._current_provider_name)

    def _save_current_provider(self) -> None:
        """保存当前 Provider 配置."""
        if not self._current_provider_name:
            return

        config = self._llm_config.get_provider(self._current_provider_name)
        if not config:
            return

        if self._api_key_edit:
            config.api_key = self._api_key_edit.text()
        if self._api_url_edit:
            config.base_url = self._api_url_edit.text()
        if self._chat_model_combo:
            config.chat_model = self._chat_model_combo.currentText()
        if self._emb_model_combo:
            config.embedding_model = self._emb_model_combo.currentText()
        if self._enable_toggle:
            config.enabled_chat = self._enable_toggle.isChecked()

        self._llm_config.add_provider(self._current_provider_name, config)
        self._refresh_provider_item_widget(self._current_provider_name)

    def _on_save(self) -> None:
        """保存配置."""
        self._save_current_provider()
        try:
            self._llm_config.save_config()
            self._llm_provider.reload_config()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存配置时出错：{str(e)}")
            return
        self._is_dirty = False
        if self._save_btn:
            self._save_btn.setEnabled(False)

    def _on_add_provider(self) -> None:
        """添加新 Provider."""
        available_types = get_all_provider_types()
        if not available_types:
            QMessageBox.warning(self, "无可用供应商", "当前没有可用的供应商类型。")
            return

        provider_type, ok = QInputDialog.getItem(
            self,
            "添加供应商",
            "选择供应商类型:",
            available_types,
            0,
            False,
        )
        if not ok or not provider_type:
            return

        base_name = provider_type.capitalize()
        name = base_name
        counter = 1
        while self._llm_config.get_provider(name):
            name = f"{base_name}_{counter}"
            counter += 1

        new_config = ProviderConfig(
            name=name,
            provider_type=provider_type,
            api_key="",
            base_url="",
            chat_model="",
            embedding_model="",
            enabled_chat=True,
            enabled_embedding=False,
        )
        self._llm_config.add_provider(name, new_config)
        self._refresh_provider_list()
        if name in self._provider_items and self._provider_list_widget:
            self._provider_list_widget.setCurrentItem(self._provider_items[name])

    def _toggle_api_key_visibility(self) -> None:
        """切换 API Key 可见性."""
        if self._api_key_edit:
            if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
                self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _open_provider_link(self, provider_type: str) -> None:
        """打开供应商密钥获取链接."""
        import webbrowser

        links = {
            "openai": "https://platform.openai.com/api-keys",
            "anthropic": "https://console.anthropic.com/settings/keys",
            "minimax": "https://platform.minimaxi.com",
            "glm": "https://open.bigmodel.cn",
            "siliconflow": "https://www.siliconflow.cn",
            "ollama": "https://ollama.com",
        }
        url = links.get(provider_type.lower(), "https://www.google.com")
        webbrowser.open(url)