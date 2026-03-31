"""
LLM 设置对话框 - 两栏布局版本
左侧：Provider 列表；右侧：Provider 配置详情
"""

from pathlib import Path
from typing import Optional, Dict, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QWidget, QInputDialog, QRadioButton,
    QToolButton, QStackedWidget, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from core.llm.config import LLMConfig, ProviderConfig
from core.llm.providers import get_all_provider_types
from core.llm.provider_interface import ModelInfo
from core.llm import get_llm_provider, get_llm_plugin_service
from utils.style_qss import get_style_qss
from ui.dialog.llm_settings_components import (
    ProviderListItem, CollapsibleGroup, ActionButton, ModelDetailItem
)


class LLMSettingsDialog(QDialog):
    """LLM 设置对话框 - 两栏布局"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LLM 设置")
        self.setObjectName("llmSettingsDialog")
        self.setMinimumSize(900, 600)
        self.resize(1050, 700)

        self._llm_config = LLMConfig()
        self._llm_provider = get_llm_provider()
        self._current_provider_name: Optional[str] = None
        self._provider_items: Dict[str, ProviderListItem] = {}
        self._fetched_models: Dict[str, List[ModelInfo]] = {}
        self._is_dirty = False

        # Key widget references
        self._api_key_edit: QLineEdit = None
        self._api_url_edit: QLineEdit = None
        self._enable_toggle: QCheckBox = None
        self._chat_model_combo: QComboBox = None
        self._emb_model_combo: QComboBox = None
        self._preset_view: QWidget = None
        self._api_view: QWidget = None
        self._preset_radio: QRadioButton = None
        self._api_radio: QRadioButton = None
        self._save_btn: QPushButton = None
        self._fetch_btn: QPushButton = None
        self._fetched_list_layout: QVBoxLayout = None
        self._fetched_list_scroll: QScrollArea = None
        self._model_stack: QStackedWidget = None

        self._init_ui()
        self._load_styles()
        self._load_data()

    # ------------------------------------------------------------------ #
    # UI Construction                                                       #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)

        left = self._create_left_panel()
        right = self._create_right_panel()

        main_layout.addWidget(left)
        main_layout.addWidget(right, 1)

    def _create_left_panel(self) -> QWidget:
        """左侧面板：Provider 列表"""
        qss = get_style_qss().get_color_dict()
        widget = QWidget()
        widget.setObjectName("leftPanel")
        widget.setFixedWidth(250)
        widget.setStyleSheet(f"""
            QWidget#leftPanel {{
                background-color: {qss['window']};
                border-right: 1px solid {qss['borderLight']};
            }}
        """)

        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QWidget()
        header.setFixedHeight(52)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)

        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label = QLabel("模型服务")
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"color: {qss['textPrimary']};")
        header_layout.addWidget(title_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {qss['borderLight']}; max-height: 1px;")
        header_layout.addWidget(divider)

        layout.addWidget(header)

        # Scroll area for provider list
        scroll = QScrollArea()
        scroll.setObjectName("providerListScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea#providerListScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        container = QWidget()
        self._provider_list_container = container
        self._provider_list_scroll = scroll
        self._provider_list_layout = QVBoxLayout(container)
        self._provider_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._provider_list_layout.setSpacing(2)
        self._provider_list_layout.setContentsMargins(8, 8, 8, 8)

        scroll.setWidget(container)
        layout.addWidget(scroll, 1)

        # Add provider button
        add_btn = QPushButton("+ 添加供应商")
        add_btn.setObjectName("addProviderButton")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_provider)
        add_btn.setStyleSheet(f"""
            QPushButton#addProviderButton {{
                background-color: transparent;
                border: 1px dashed {qss['border']};
                border-radius: 8px;
                color: {qss['accent']};
                font-size: 13px;
                padding: 10px;
                margin: 8px;
            }}
            QPushButton#addProviderButton:hover {{
                background-color: {qss['controlFillHover']};
                border-style: solid;
            }}
        """)
        layout.addWidget(add_btn)

        return widget

    def _create_right_panel(self) -> QWidget:
        """右侧面板：Provider 配置详情"""
        qss = get_style_qss().get_color_dict()

        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for detail content
        scroll = QScrollArea()
        scroll.setObjectName("detailScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea#detailScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """)

        content = QWidget()
        self._detail_layout = QVBoxLayout(content)
        self._detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._detail_layout.setSpacing(20)
        self._detail_layout.setContentsMargins(24, 24, 24, 24)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        # Bottom bar
        bottom = self._create_bottom_bar()
        layout.addWidget(bottom)

        return widget

    def _create_bottom_bar(self) -> QWidget:
        """底部栏：使用统计 + 保存/取消按钮"""
        qss = get_style_qss().get_color_dict()

        widget = QWidget()
        widget.setFixedHeight(52)
        widget.setStyleSheet(f"""
            QWidget {{
                background-color: {qss['window']};
                border-top: 1px solid {qss['borderLight']};
            }}
        """)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(24, 0, 24, 0)

        # Usage stats
        usage_text = "加载中..."
        try:
            svc = get_llm_plugin_service()
            stats = svc.get_usage_stats()
            total = stats.total_cost
            usage_text = f"累计使用: ${total:.4f}"
        except Exception:
            usage_text = "累计使用: --"

        usage_label = QLabel(usage_text)
        usage_label.setObjectName("usageLabel")
        usage_label.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 12px;")
        layout.addWidget(usage_label)

        layout.addStretch()

        # Cancel
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(30)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 6px;
                padding: 0px 16px;
                color: {qss['textPrimary']};
                font-size: 13px;
                min-height: 30px;
            }}
            QPushButton:hover {{
                background-color: {qss['controlFillHover']};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)

        # Save
        save_btn = QPushButton("保存")
        save_btn.setObjectName("accentSave")
        save_btn.setFixedHeight(30)
        save_btn.setEnabled(False)
        save_btn.setStyleSheet(f"""
            QPushButton#accentSave {{
                background-color: {qss['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0px 16px;
                font-size: 13px;
                min-height: 30px;
            }}
            QPushButton#accentSave:hover {{
                background-color: {qss['accentLight']};
            }}
            QPushButton#accentSave:disabled {{
                background-color: {qss['controlFill']};
                color: {qss['textSecondary']};
            }}
        """)
        save_btn.clicked.connect(self._on_save)
        self._save_btn = save_btn
        layout.addWidget(save_btn)

        return widget

    # ------------------------------------------------------------------ #
    # Data Loading                                                          #
    # ------------------------------------------------------------------ #

    def _load_data(self):
        """加载 Provider 列表并选中第一个"""
        self._refresh_provider_list()
        # 从本地缓存恢复已获取的模型列表
        for name in self._llm_config.get_all_providers():
            cached = self._llm_config.load_models_cache(name)
            if cached:
                self._fetched_models[name] = [ModelInfo.from_dict(m) for m in cached]
        providers = self._llm_config.get_all_providers()
        if providers:
            first_name = next(iter(providers))
            self._on_provider_clicked(first_name)

    def _refresh_provider_list(self):
        """重建左侧 Provider 列表"""
        layout = self._provider_list_layout
        # Clear all widgets from layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._provider_items.clear()

        providers = self._llm_config.get_all_providers()
        for name, config in providers.items():
            is_active = config.enabled_chat
            logo_path = str(Path(__file__).resolve().parent.parent.parent / "core" / "llm" / "providers" / f"{config.provider_type}.png")
            item = ProviderListItem(
                provider_name=name,
                provider_type=config.provider_type,
                is_active=is_active,
                display_name=config.name,
                icon_path=logo_path,
            )
            item.setObjectName(f"providerListItem_{name}")
            item.clicked.connect(self._on_provider_clicked)
            layout.addWidget(item)
            self._provider_items[name] = item

        layout.addStretch()

    def _on_provider_clicked(self, provider_name: str):
        """Provider 点击事件"""
        # Save current provider if dirty (在清空详情前保存)
        if self._is_dirty and self._current_provider_name:
            self._save_current_provider()

        # Update selection state
        for name, item in self._provider_items.items():
            item.set_selected(name == provider_name)

        self._current_provider_name = provider_name
        self._show_provider_detail(provider_name)
        self._is_dirty = False
        if self._save_btn:
            self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------ #
    # Provider Detail View                                                 #
    # ------------------------------------------------------------------ #

    def _show_provider_detail(self, provider_name: str):
        """显示 Provider 配置详情"""
        # Clear detail layout
        while self._detail_layout.count():
            item = self._detail_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        qss = get_style_qss().get_color_dict()

        # --- Header ---
        self._build_header_section(config, qss)
        self._add_divider()

        # --- API Key ---
        self._build_api_key_section(config, qss)
        self._add_divider()

        # --- API URL ---
        self._build_api_url_section(config, qss)
        self._add_divider()

        # --- Validate ---
        self._build_validate_section(qss)
        self._add_divider()

        # --- Model List ---
        self._build_model_list_section(provider_name, config, qss)
        self._add_divider()

        # --- Model Selection ---
        self._build_model_selection_section(config, qss)

        # Populate comboboxes
        self._populate_model_combos(provider_name, config)

    def _build_header_section(self, config: ProviderConfig, qss: dict):
        """Header: logo + name + enable toggle"""
        header_widget = QWidget()
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(16)

        # Logo placeholder
        logo_label = QLabel()
        logo_label.setFixedSize(64, 64)
        logo_label.setStyleSheet(f"""
            QLabel {{
                background-color: {qss['accent']};
                border-radius: 12px;
                color: white;
                font-size: 28px;
                font-weight: bold;
            }}
        """)
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_label.setText(config.name[:1].upper() if config.name else "?")
        header_layout.addWidget(logo_label)

        # Name + subtitle
        name_layout = QVBoxLayout()
        name_layout.setSpacing(4)

        name_label = QLabel(config.name or "")
        name_label.setObjectName("providerName")
        name_label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 20px; font-weight: bold;")
        name_layout.addWidget(name_label)

        type_label = QLabel(config.provider_type)
        type_label.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 13px;")
        name_layout.addWidget(type_label)

        name_layout.addStretch()
        header_layout.addLayout(name_layout, 1)

        # Enable toggle
        self._enable_toggle = QCheckBox("启用")
        self._enable_toggle.setChecked(config.enabled_chat)
        self._enable_toggle.setStyleSheet(f"""
            QCheckBox {{
                color: {qss['textPrimary']};
                font-size: 14px;
            }}
        """)
        self._enable_toggle.stateChanged.connect(self._mark_dirty)
        header_layout.addWidget(self._enable_toggle)

        self._detail_layout.addWidget(header_widget)

    def _build_api_key_section(self, config: ProviderConfig, qss: dict):
        """API Key 输入区"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("API 密钥")
        label.setObjectName("formLabelBold")
        label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(label)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("请输入 API 密钥")
        self._api_key_edit.setText(config.api_key or "")
        self._api_key_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {qss['textPrimary']};
                font-size: 13px;
            }}
            QLineEdit:hover {{ border-color: {qss['accent']}; }}
            QLineEdit:focus {{ border-color: {qss['accent']}; background-color: {qss['base']}; }}
        """)
        self._api_key_edit.textChanged.connect(self._mark_dirty)
        row.addWidget(self._api_key_edit, 1)

        # Eye toggle button
        eye_btn = QToolButton()
        eye_btn.setText("👁")
        eye_btn.setFixedSize(36, 36)
        eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        eye_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
            }}
        """)
        eye_btn.clicked.connect(self._toggle_api_key_visibility)
        row.addWidget(eye_btn)

        layout.addLayout(row)

        # Link label
        link_label = QLabel("点击这里获取密钥")
        link_label.setObjectName("linkLabel")
        link_label.setStyleSheet(f"color: {qss['accent']}; font-size: 13px;")
        link_label.setCursor(Qt.CursorShape.PointingHandCursor)
        link_label.mousePressEvent = lambda e: self._open_provider_link(config.provider_type)
        layout.addWidget(link_label)

        self._detail_layout.addWidget(widget)

    def _build_api_url_section(self, config: ProviderConfig, qss: dict):
        """API URL 输入区"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("API 地址")
        label.setObjectName("formLabelBold")
        label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(label)

        self._api_url_edit = QLineEdit()
        self._api_url_edit.setPlaceholderText("例如: https://api.example.com/v1")
        self._api_url_edit.setText(config.base_url or "")
        self._api_url_edit.setStyleSheet(f"""
            QLineEdit {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {qss['textPrimary']};
                font-size: 13px;
            }}
            QLineEdit:hover {{ border-color: {qss['accent']}; }}
            QLineEdit:focus {{ border-color: {qss['accent']}; background-color: {qss['base']}; }}
        """)
        self._api_url_edit.textChanged.connect(self._mark_dirty)
        layout.addWidget(self._api_url_edit)

        preview_label = QLabel("请求将发送至此地址")
        preview_label.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 12px;")
        layout.addWidget(preview_label)

        self._detail_layout.addWidget(widget)

    def _build_validate_section(self, qss: dict):
        """检测供应商有效性按钮"""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        validate_btn = ActionButton("检测供应商有效性", "✓")
        validate_btn.setStyleSheet(f"""
            QPushButton#actionButton {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                color: {qss['textPrimary']};
                font-size: 13px;
                padding: 6px 16px;
                min-height: 30px;
            }}
            QPushButton#actionButton:hover {{
                background-color: {qss['controlFillHover']};
            }}
        """)
        validate_btn.clicked.connect(self._on_validate_provider)
        layout.addWidget(validate_btn)

        layout.addStretch()
        self._detail_layout.addWidget(widget)

    def _build_model_list_section(self, provider_name: str, config: ProviderConfig, qss: dict):
        """模型列表区：预设 / API 切换"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("模型列表")
        label.setObjectName("formLabelBold")
        label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px; font-weight: bold;")
        layout.addWidget(label)

        # Radio buttons for source
        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(16)

        self._preset_radio = QRadioButton("使用本地预设列表")
        self._preset_radio.setObjectName("modelSourceToggle")
        self._preset_radio.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px;")
        self._api_radio = QRadioButton("从 API 获取")
        self._api_radio.setObjectName("modelSourceToggle")
        self._api_radio.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px;")

        radio_layout.addWidget(self._preset_radio)
        radio_layout.addWidget(self._api_radio)
        radio_layout.addStretch()
        layout.addLayout(radio_layout)

        # Force preset for minimax/glm
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

        # Stacked widget: preset view vs API view
        self._model_stack = QStackedWidget()
        self._model_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        # Preset view
        self._preset_view = QWidget()
        preset_layout = QVBoxLayout(self._preset_view)
        preset_layout.setSpacing(4)
        preset_layout.setContentsMargins(0, 0, 0, 0)

        # Build preset groups by category
        presets = self._get_preset_models(provider_name)
        chat_models = [m for m in presets if m.support_chat]
        emb_models = [m for m in presets if m.support_embedding]
        vision_models = [m for m in presets if m.support_vision]
        other_models = [m for m in presets if not (m.support_chat or m.support_embedding or m.support_vision)]

        categories = []
        if chat_models:
            categories.append(("聊天模型 Chat", chat_models))
        if emb_models:
            categories.append(("嵌入模型 Embedding", emb_models))
        if vision_models:
            categories.append(("视觉模型 Vision", vision_models))
        if other_models:
            categories.append(("其他模型", other_models))

        if categories:
            for cat_name, models in categories:
                group = CollapsibleGroup(cat_name, len(models))
                group.setStyleSheet(f"""
                    QPushButton#collapsibleHeader {{
                        background-color: {qss['controlFill']};
                        border: none;
                        border-radius: 8px;
                        color: {qss['textPrimary']};
                        font-size: 12px;
                        font-weight: bold;
                        text-align: left;
                        padding: 8px 12px;
                    }}
                    QPushButton#collapsibleHeader:hover {{
                        background-color: {qss['controlFillHover']};
                    }}
                """)
                for m in models:
                    model_widget = self._make_preset_model_widget(m, qss)
                    group.add_widget(model_widget)
                preset_layout.addWidget(group)
        else:
            empty_label = QLabel("该供应商暂无预设模型列表，请使用「从 API 获取」")
            empty_label.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 13px; padding: 8px;")
            preset_layout.addWidget(empty_label)

        preset_layout.addStretch()
        self._model_stack.addWidget(self._preset_view)

        # API view
        self._api_view = QWidget()
        api_layout = QVBoxLayout(self._api_view)
        api_layout.setSpacing(8)
        api_layout.setContentsMargins(0, 0, 0, 0)

        fetch_row = QHBoxLayout()
        self._fetch_btn = QPushButton("从 API 获取模型列表")
        self._fetch_btn.setObjectName("fetchModelsButton")
        self._fetch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._fetch_btn.setStyleSheet(f"""
            QPushButton#fetchModelsButton {{
                background-color: {qss['accent']};
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 13px;
                padding: 6px 16px;
                min-height: 30px;
            }}
            QPushButton#fetchModelsButton:hover {{
                background-color: {qss['accentLight']};
            }}
            QPushButton#fetchModelsButton:disabled {{
                background-color: {qss['controlFill']};
                color: {qss['textSecondary']};
            }}
        """)
        self._fetch_btn.clicked.connect(lambda: self._on_fetch_models(provider_name))
        fetch_row.addWidget(self._fetch_btn)
        fetch_row.addStretch()
        api_layout.addLayout(fetch_row)

        # Fetched models scroll area
        self._fetched_list_scroll = QScrollArea()
        self._fetched_list_scroll.setFixedHeight(300)
        self._fetched_list_scroll.setWidgetResizable(True)
        self._fetched_list_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._fetched_list_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._fetched_list_scroll.setStyleSheet(f"""
            QScrollArea {{
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                background-color: {qss['controlFill']};
            }}
        """)
        fetched_container = QWidget()
        self._fetched_list_layout = QVBoxLayout(fetched_container)
        self._fetched_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._fetched_list_layout.setSpacing(2)
        self._fetched_list_layout.setContentsMargins(4, 4, 4, 4)
        self._fetched_list_scroll.setWidget(fetched_container)
        api_layout.addWidget(self._fetched_list_scroll)

        # If already fetched, populate
        if provider_name in self._fetched_models:
            self._populate_fetched_list(provider_name)

        self._model_stack.addWidget(self._api_view)

        # Set initial visibility
        if force_preset or (not force_preset and self._preset_radio.isChecked()):
            self._model_stack.setCurrentWidget(self._preset_view)
        else:
            self._model_stack.setCurrentWidget(self._api_view)

        layout.addWidget(self._model_stack)
        self._detail_layout.addWidget(widget)

    def _build_model_selection_section(self, config: ProviderConfig, qss: dict):
        """模型选择区：当前聊天模型 + 当前 Embedding 模型"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # Chat model row
        chat_row = QHBoxLayout()
        chat_label = QLabel("当前聊天模型")
        chat_label.setFixedWidth(120)
        chat_label.setObjectName("formLabelBold")
        chat_label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px; font-weight: bold;")

        self._chat_model_combo = QComboBox()
        self._chat_model_combo.setObjectName("modelSelectCombo")
        self._chat_model_combo.setMinimumWidth(300)
        self._chat_model_combo.setStyleSheet(f"""
            QComboBox#modelSelectCombo {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {qss['textPrimary']};
                font-size: 13px;
                min-height: 20px;
            }}
            QComboBox#modelSelectCombo:hover {{
                border-color: {qss['accent']};
            }}
            QComboBox#modelSelectCombo:focus {{
                border-color: {qss['accent']};
                background-color: {qss['base']};
            }}
        """)
        self._chat_model_combo.currentTextChanged.connect(self._mark_dirty)

        chat_row.addWidget(chat_label)
        chat_row.addWidget(self._chat_model_combo, 1)
        layout.addLayout(chat_row)

        # Embedding model row
        emb_row = QHBoxLayout()
        emb_label = QLabel("当前 Embedding 模型")
        emb_label.setFixedWidth(120)
        emb_label.setObjectName("formLabelBold")
        emb_label.setStyleSheet(f"color: {qss['textPrimary']}; font-size: 13px; font-weight: bold;")

        self._emb_model_combo = QComboBox()
        self._emb_model_combo.setObjectName("modelSelectCombo")
        self._emb_model_combo.setMinimumWidth(300)
        self._emb_model_combo.setStyleSheet(f"""
            QComboBox#modelSelectCombo {{
                background-color: {qss['controlFill']};
                border: 1px solid {qss['borderLight']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {qss['textPrimary']};
                font-size: 13px;
                min-height: 20px;
            }}
            QComboBox#modelSelectCombo:hover {{
                border-color: {qss['accent']};
            }}
            QComboBox#modelSelectCombo:focus {{
                border-color: {qss['accent']};
                background-color: {qss['base']};
            }}
        """)
        self._emb_model_combo.currentTextChanged.connect(self._mark_dirty)

        emb_row.addWidget(emb_label)
        emb_row.addWidget(self._emb_model_combo, 1)
        layout.addLayout(emb_row)

        self._detail_layout.addWidget(widget)

    # ------------------------------------------------------------------ #
    # Helpers                                                               #
    # ------------------------------------------------------------------ #

    def _add_divider(self):
        """添加分隔线"""
        qss = get_style_qss().get_color_dict()
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background-color: {qss['borderLight']}; max-height: 1px; margin: 4px 0;")
        self._detail_layout.addWidget(div)

    def _make_preset_model_widget(self, model: ModelInfo, qss: dict) -> QWidget:
        """创建预设模型列表项 - 使用 ModelDetailItem"""
        # 使用新的 ModelDetailItem 组件显示完整的模型信息
        item = ModelDetailItem(
            model_id=model.id,
            model_name=model.name or model.id,
            context_length=model.context_length,
            support_chat=model.support_chat,
            support_embedding=model.support_embedding,
            support_vision=model.support_vision,
            support_thinking=getattr(model, 'support_thinking', False) or 'thinking' in model.id.lower(),
            support_tools=model.support_function_calling
        )
        return item

    def _get_preset_models(self, provider_name: str) -> List[ModelInfo]:
        """获取预设模型列表"""
        models: List[ModelInfo] = []

        if provider_name == "minimax":
            try:
                from core.llm.providers.minimax import MiniMaxProvider
                details = getattr(MiniMaxProvider, "MODEL_DETAILS", {})

                for model_id in getattr(MiniMaxProvider, "CHAT_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(ModelInfo(
                        id=model_id,
                        name=info.get("name", model_id),
                        support_chat=True,
                        support_embedding=False,
                        support_vision=False,
                        support_function_calling=info.get("support_function_calling", False),
                        context_length=info.get("context_length", 0),
                    ))

                for model_id in getattr(MiniMaxProvider, "EMBEDDING_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(ModelInfo(
                        id=model_id,
                        name=info.get("name", model_id),
                        support_chat=False,
                        support_embedding=True,
                        support_vision=False,
                        support_function_calling=False,
                        context_length=info.get("context_length", 0),
                    ))
            except Exception:
                pass

        elif provider_name == "glm":
            try:
                from core.llm.providers.glm import GLMProvider
                details = getattr(GLMProvider, "MODEL_DETAILS", {})

                for model_id in getattr(GLMProvider, "CHAT_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(ModelInfo(
                        id=model_id,
                        name=info.get("name", model_id),
                        support_chat=True,
                        support_embedding=False,
                        support_vision=False,
                        support_function_calling=info.get("support_function_calling", False),
                        context_length=info.get("context_length", 0),
                    ))

                for model_id in getattr(GLMProvider, "EMBEDDING_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(ModelInfo(
                        id=model_id,
                        name=info.get("name", model_id),
                        support_chat=False,
                        support_embedding=True,
                        support_vision=False,
                        support_function_calling=False,
                        context_length=info.get("context_length", 0),
                    ))

                for model_id in getattr(GLMProvider, "VISION_MODELS", []):
                    info = details.get(model_id, {})
                    models.append(ModelInfo(
                        id=model_id,
                        name=info.get("name", model_id),
                        support_chat=False,
                        support_embedding=False,
                        support_vision=True,
                        support_function_calling=False,
                        context_length=info.get("context_length", 0),
                    ))
            except Exception:
                pass

        # ollama / siliconflow have no preset lists - return empty
        return models

    def _populate_model_combos(self, provider_name: str, config: ProviderConfig):
        """填充模型下拉框"""
        if not self._chat_model_combo or not self._emb_model_combo:
            return

        preset_models = self._get_preset_models(provider_name)
        fetched_models = self._fetched_models.get(provider_name, [])

        # Merge and deduplicate
        seen_ids = set()
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

    def _populate_fetched_list(self, provider_name: str):
        """填充 API 获取的模型列表"""
        models = self._fetched_models.get(provider_name, [])
        qss = get_style_qss().get_color_dict()

        # Clear existing
        while self._fetched_list_layout.count():
            item = self._fetched_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not models:
            empty = QLabel("暂无模型，请点击上方按钮获取")
            empty.setStyleSheet(f"color: {qss['textSecondary']}; font-size: 13px; padding: 8px;")
            self._fetched_list_layout.addWidget(empty)
            return

        for model in models:
            item_widget = self._make_preset_model_widget(model, qss)
            self._fetched_list_layout.addWidget(item_widget)

    def _on_model_source_changed(self, checked: bool):
        """切换预设/API 视图"""
        if not checked:
            return
        if self._preset_radio.isChecked():
            self._model_stack.setCurrentWidget(self._preset_view)
        else:
            self._model_stack.setCurrentWidget(self._api_view)

    def _on_fetch_models(self, provider_name: str):
        """触发从 API 获取模型列表"""
        self._fetch_btn.setEnabled(False)
        self._fetch_btn.setText("获取中...")
        QTimer.singleShot(0, lambda: self._do_fetch_models(provider_name))

    def _do_fetch_models(self, provider_name: str):
        """实际执行从 API 获取模型列表"""
        try:
            models = self._llm_provider.refresh_provider_models(provider_name, force=True)
            self._fetched_models[provider_name] = models
            self._populate_fetched_list(provider_name)
            # Re-populate combos
            if self._current_provider_name == provider_name:
                config = self._llm_config.get_provider(provider_name)
                if config:
                    self._populate_model_combos(provider_name, config)
        except Exception as e:
            QMessageBox.warning(self, "获取失败", f"无法获取模型列表：{str(e)}")
        finally:
            self._fetch_btn.setEnabled(True)
            self._fetch_btn.setText("从 API 获取模型列表")

    def _on_validate_provider(self):
        """验证 Provider 配置"""
        if not self._current_provider_name:
            return
        try:
            provider = self._llm_provider.get_provider(self._current_provider_name)
            if provider:
                result = provider.validate_config()
                if result:
                    QMessageBox.information(self, "验证成功", "供应商配置有效。")
                else:
                    QMessageBox.warning(self, "验证失败", "供应商配置无效，请检查 API Key 和 API 地址。")
            else:
                QMessageBox.warning(self, "验证失败", "Provider 未初始化。")
        except Exception as e:
            QMessageBox.warning(self, "验证失败", f"验证时出错：{str(e)}")

    def _mark_dirty(self):
        """标记为已修改"""
        self._is_dirty = True
        if self._save_btn:
            self._save_btn.setEnabled(True)

    def _save_current_provider(self):
        """保存当前 Provider 配置"""
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

    def _on_save(self):
        """保存并关闭"""
        self._save_current_provider()
        try:
            self._llm_config.save_config()
            self._llm_provider.reload_config()
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存配置时出错：{str(e)}")
            return
        self.accept()

    def _on_add_provider(self):
        """添加新 Provider"""
        available_types = get_all_provider_types()
        if not available_types:
            QMessageBox.warning(self, "无可用供应商", "当前没有可用的供应商类型。")
            return

        provider_type, ok = QInputDialog.getItem(
            self, "添加供应商", "选择供应商类型:", available_types, 0, False
        )
        if not ok or not provider_type:
            return

        # Generate unique name
        base_name = provider_type.capitalize()
        name = base_name
        counter = 1
        while self._llm_config.get_provider(name):
            name = f"{base_name}_{counter}"
            counter += 1

        # Create default config
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
        self._on_provider_clicked(name)

    def _toggle_api_key_visibility(self):
        """切换 API Key 可见性"""
        if self._api_key_edit:
            if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
                self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            else:
                self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _open_provider_link(self, provider_type: str):
        """打开供应商密钥获取链接"""
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

    def _load_styles(self):
        """加载样式表"""
        qss = get_style_qss()
        colors = qss.get_color_dict()

        self.setStyleSheet(f"""
            QDialog#llmSettingsDialog {{
                background-color: {colors['window']};
            }}
            QLabel#providerName {{
                color: {colors['textPrimary']};
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#formLabel {{
                color: {colors['textSecondary']};
                font-size: 13px;
            }}
            QLabel#formLabelBold {{
                color: {colors['textPrimary']};
                font-size: 13px;
                font-weight: bold;
            }}
            QLabel#linkLabel {{
                color: {colors['accent']};
                font-size: 13px;
            }}
            QLabel#linkLabel:hover {{
                text-decoration: underline;
            }}
            QLabel#contextLengthLabel {{
                color: {colors['textSecondary']};
                font-size: 12px;
            }}
            QLabel#usageLabel {{
                color: {colors['textSecondary']};
                font-size: 12px;
            }}
            QComboBox#modelSelectCombo {{
                background-color: {colors['controlFill']};
                border: 1px solid {colors['borderLight']};
                border-radius: 8px;
                padding: 8px 12px;
                color: {colors['textPrimary']};
                font-size: 13px;
                min-height: 20px;
            }}
            QComboBox#modelSelectCombo:hover {{
                border-color: {colors['accent']};
            }}
            QComboBox#modelSelectCombo:focus {{
                border-color: {colors['accent']};
                background-color: {colors['base']};
            }}
            QPushButton#accentSave {{
                background-color: {colors['accent']};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 6px 16px;
                font-size: 13px;
                min-height: 30px;
            }}
            QPushButton#accentSave:hover {{
                background-color: {colors['accentLight']};
            }}
            QPushButton#accentSave:disabled {{
                background-color: {colors['controlFill']};
                color: {colors['textSecondary']};
            }}
            #fetchModelsButton {{
                background-color: {colors['accent']};
                border: none;
                border-radius: 16px;
                color: white;
                font-size: 13px;
                padding: 6px 16px;
                min-height: 30px;
            }}
            #fetchModelsButton:hover {{
                background-color: {colors['accentLight']};
            }}
            #fetchModelsButton:disabled {{
                background-color: {colors['controlFill']};
                color: {colors['textSecondary']};
            }}
            QRadioButton#modelSourceToggle {{
                color: {colors['textPrimary']};
                font-size: 13px;
            }}
            QWidget#modelFetchedItem {{
                background-color: transparent;
                border-radius: 8px;
                margin: 2px 0;
            }}
            #addProviderButton {{
                background-color: transparent;
                border: 1px dashed {colors['border']};
                border-radius: 8px;
                color: {colors['accent']};
                font-size: 13px;
                padding: 10px;
                margin: 8px;
            }}
            #addProviderButton:hover {{
                background-color: {colors['controlFillHover']};
                border-style: solid;
            }}
            QScrollArea#detailScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollArea#providerListScrollArea {{
                border: none;
                background-color: transparent;
            }}
        """ + "\n" + qss.get("llm_settings", ""))
