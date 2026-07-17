# ui/dialog/llm_settings_dialog.py
"""LLM 设置对话框 - 两栏布局（右侧显示 Provider Logo）."""
import importlib
from typing import Optional, Dict, List, Any
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QComboBox, QCheckBox, QMessageBox,
    QScrollArea, QWidget, QInputDialog, QRadioButton,
    QToolButton, QStackedWidget, QSizePolicy, QListWidget, QListWidgetItem,
    QSpinBox, QDoubleSpinBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QTimer, QSize, QEvent, QObject, QThread
from PySide6.QtGui import QFont, QPixmap, QPainter, QPainterPath

from core.llm.config import LLMConfig, ProviderConfig
from core.llm.providers import get_all_provider_types
from core.llm.provider_interface import ModelInfo
from core.llm import get_llm_provider, get_llm_plugin_service
from ui.dialog.llm_settings_components import (
    CollapsibleGroup, ActionButton, ModelDetailItem, ProviderListItemWidget
)
from utils.style_qss import get_style_qss


class FetchModelsWorker(QThread):
    """后台线程：从 API 获取模型列表（避免主线程同步 HTTP 阻塞界面）."""

    succeeded = Signal(str, list)   # (provider_name, models)
    failed = Signal(str, str)       # (provider_name, 错误信息)

    def __init__(self, llm_provider, provider_name: str, parent=None):
        super().__init__(parent)
        self._llm_provider = llm_provider
        self._provider_name = provider_name

    def run(self) -> None:
        try:
            models = self._llm_provider.refresh_provider_models(
                self._provider_name, force=True
            )
            if models:
                self.succeeded.emit(self._provider_name, models)
            else:
                # 失败原因从 last_errors 获取（真实错误，不再被吞）
                errors = getattr(self._llm_provider, "last_errors", {}) or {}
                message = errors.get(self._provider_name) or "未返回任何模型"
                self.failed.emit(self._provider_name, message)
        except Exception as e:
            self.failed.emit(self._provider_name, str(e))


class ValidateProviderWorker(QThread):
    """后台线程：真实连通性检测（拉取模型列表验证供应商可用性）."""

    succeeded = Signal(str, int)    # (provider_name, 可用模型数量)
    failed = Signal(str, str)       # (provider_name, 错误信息)

    def __init__(self, llm_provider, provider_name: str, parent=None):
        super().__init__(parent)
        self._llm_provider = llm_provider
        self._provider_name = provider_name

    def run(self) -> None:
        try:
            models = self._llm_provider.refresh_provider_models(
                self._provider_name, force=True
            )
            if models:
                self.succeeded.emit(self._provider_name, len(models))
            else:
                errors = getattr(self._llm_provider, "last_errors", {}) or {}
                message = (
                    errors.get(self._provider_name)
                    or "未能获取模型列表，请检查网络与配置"
                )
                self.failed.emit(self._provider_name, message)
        except Exception as e:
            self.failed.emit(self._provider_name, str(e))


# 预设模型表驱动配置：provider -> (模块名, Provider 类名)
_PRESET_PROVIDERS = {
    "minimax": ("core.llm.providers.minimax", "MiniMaxProvider"),
    "glm": ("core.llm.providers.glm", "GLMProvider"),
}

# 预设模型分组：(类属性名, 能力标记, 是否从 MODEL_DETAILS 读取函数调用能力)
_PRESET_MODEL_GROUPS = [
    ("CHAT_MODELS", {"support_chat": True}, True),
    ("EMBEDDING_MODELS", {"support_embedding": True}, False),
    ("VISION_MODELS", {"support_vision": True}, False),
]


class LLMSettingsDialog(QDialog):
    """LLM 设置对话框 - 两栏布局."""

    # 各供应商密钥获取链接（未知供应商不提供 fallback 跳转）
    _PROVIDER_KEY_LINKS = {
        "openai": "https://platform.openai.com/api-keys",
        "anthropic": "https://console.anthropic.com/settings/keys",
        "minimax": "https://platform.minimaxi.com",
        "glm": "https://open.bigmodel.cn",
        "siliconflow": "https://www.siliconflow.cn",
        "ollama": "https://ollama.com",
    }

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

        # 后台 worker 引用（获取模型列表 / 连通性检测）
        self._fetch_worker: Optional[FetchModelsWorker] = None
        self._validate_worker: Optional[ValidateProviderWorker] = None
        self._validate_btn: Optional[QPushButton] = None

        # 主题刷新需要重刷内联样式的结构控件引用
        self._left_panel: Optional[QWidget] = None
        self._left_title_label: Optional[QLabel] = None
        self._left_divider: Optional[QFrame] = None
        self._add_provider_btn: Optional[QPushButton] = None
        self._right_panel: Optional[QWidget] = None
        self._right_scroll: Optional[QScrollArea] = None
        self._right_content: Optional[QWidget] = None
        self._bottom_bar: Optional[QWidget] = None
        self._usage_label: Optional[QLabel] = None
        self._cancel_btn: Optional[QPushButton] = None

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

    # ------------------------------------------------------------------ #
    # 内联样式生成（抽出为方法，供主题切换时重新应用）                          #
    # ------------------------------------------------------------------ #

    def _left_panel_qss(self) -> str:
        """左侧面板样式."""
        bg_color = self._get_color('window', '#FAFAFA')
        border_color = self._get_color('borderLight', '#E0E0E0')
        return f"""
            QWidget#leftPanel {{
                background-color: {bg_color};
                border-right: 1px solid {border_color};
            }}
        """

    def _provider_list_qss(self) -> str:
        """Provider 列表样式."""
        item_bg = self._get_color('base', '#FFFFFF')
        item_selected = self._get_color('controlFillSelected', '#E3F2FD')
        item_hover = self._get_color('controlFillHover', '#F5F5F5')
        return f"""
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
        """

    def _add_provider_btn_qss(self) -> str:
        """添加供应商按钮样式."""
        btn_bg = self._get_color('base', '#FFFFFF')
        btn_border = self._get_color('border', '#CCCCCC')
        btn_color = self._get_color('textSecondary', '#666666')
        btn_hover_bg = self._get_color('controlFillHover', '#F5F5F5')
        btn_hover_color = self._get_color('textPrimary', '#333333')
        return f"""
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
        """

    def _bottom_bar_qss(self) -> str:
        """底部栏样式."""
        bg_color = self._get_color('window', '#FFFFFF')
        border_color = self._get_color('borderLight', '#E0E0E0')
        return f"""
            QWidget#bottomBar {{
                background-color: {bg_color};
                border-top: 1px solid {border_color};
            }}
        """

    def _save_btn_qss(self) -> str:
        """保存按钮样式."""
        accent = self._get_color('accent', '#0078D4')
        accent_light = self._get_color('accentLight', '#4CC2FF')
        accent_dark = self._get_color('accentDark', '#005A9E')
        button_bg = self._get_color('button', '#F3F3F3')
        text_disabled = self._get_color('textDisabled', '#6D6D6D')
        border_light = self._get_color('borderLight', '#CCCCCC')
        return f"""
            QPushButton {{
                background-color: {button_bg};
                border: 1px solid {border_light};
                border-radius: 6px;
                color: {text_disabled};
                padding: 0 20px;
                font-weight: 500;
                min-width: 72px;
            }}
            QPushButton:enabled {{
                background-color: {accent};
                border: 1px solid {accent};
                color: white;
            }}
            QPushButton:enabled:hover {{
                background-color: {accent_light};
                border-color: {accent_light};
            }}
            QPushButton:enabled:pressed {{
                background-color: {accent_dark};
                border-color: {accent_dark};
            }}
        """

    def _create_left_panel(self) -> QWidget:
        """创建左侧面板：Provider 列表."""
        widget = QWidget()
        widget.setObjectName("leftPanel")
        widget.setFixedWidth(self._left_panel_width)
        widget.setStyleSheet(self._left_panel_qss())
        self._left_panel = widget

        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        header = self._create_left_header()
        layout.addWidget(header)

        self._provider_list_widget = QListWidget()
        self._provider_list_widget.setObjectName("providerListWidget")
        self._provider_list_widget.setAccessibleName("供应商列表")
        self._provider_list_widget.setCursor(Qt.CursorShape.PointingHandCursor)
        self._provider_list_widget.setSpacing(2)
        self._provider_list_widget.setFrameShape(QFrame.Shape.NoFrame)
        self._provider_list_widget.setStyleSheet(self._provider_list_qss())
        self._provider_list_widget.currentItemChanged.connect(
            self._on_provider_current_changed
        )
        self._provider_list_widget.installEventFilter(self)
        layout.addWidget(self._provider_list_widget, 1)

        # 添加供应商按钮
        add_btn = QPushButton("+ 添加供应商")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(44)
        add_btn.setStyleSheet(self._add_provider_btn_qss())
        add_btn.clicked.connect(self._on_add_provider)
        self._add_provider_btn = add_btn
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
        self._left_title_label = title_label
        header_layout.addWidget(title_label)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background-color: {self._get_color('borderLight', '#E0E0E0')};")
        self._left_divider = divider
        header_layout.addWidget(divider)

        return header

    def _create_right_panel(self) -> QWidget:
        """创建右侧面板：Provider 配置详情."""
        widget = QWidget()
        bg_color = self._get_color('window', '#FFFFFF')
        widget.setStyleSheet(f"background-color: {bg_color};")
        self._right_panel = widget
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {bg_color};")
        self._right_scroll = scroll

        content = QWidget()
        content.setStyleSheet(f"background-color: {bg_color};")
        self._right_content = content
        self._detail_layout = QVBoxLayout(content)
        self._detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._detail_layout.setSpacing(16)
        self._detail_layout.setContentsMargins(24, 20, 24, 20)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        bottom = self._create_bottom_bar()
        layout.addWidget(bottom)

        return widget

    def _create_bottom_bar(self) -> QWidget:
        """创建底部栏：使用统计 + 保存/取消按钮."""
        widget = QWidget()
        widget.setObjectName("bottomBar")
        widget.setFixedHeight(56)
        widget.setStyleSheet(self._bottom_bar_qss())
        self._bottom_bar = widget

        text_secondary = self._get_color('textSecondary', '#666666')

        layout = QHBoxLayout(widget)
        layout.setContentsMargins(24, 0, 24, 0)

        usage_text = self._get_usage_text()
        usage_label = QLabel(usage_text)
        usage_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        self._usage_label = usage_label
        layout.addWidget(usage_label)

        layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedHeight(36)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        self._cancel_btn = cancel_btn
        layout.addWidget(cancel_btn)

        # 保存按钮
        save_btn = QPushButton("保存")
        save_btn.setFixedHeight(36)
        save_btn.setEnabled(False)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._on_save)
        save_btn.setStyleSheet(self._save_btn_qss())
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
        """刷新 UI 主题：重新应用所有内联样式（主题切换后调用）."""
        # 重新获取颜色
        self._colors = self._style_qss.colors()

        # 重刷结构性面板的内联样式
        bg_color = self._get_color('window', '#FFFFFF')
        if self._left_panel is not None:
            self._left_panel.setStyleSheet(self._left_panel_qss())
        if self._provider_list_widget is not None:
            self._provider_list_widget.setStyleSheet(self._provider_list_qss())
        if self._add_provider_btn is not None:
            self._add_provider_btn.setStyleSheet(self._add_provider_btn_qss())
        if self._left_title_label is not None:
            self._left_title_label.setStyleSheet(
                f"color: {self._get_color('textPrimary', '#000000')};"
            )
        if self._left_divider is not None:
            self._left_divider.setStyleSheet(
                f"background-color: {self._get_color('borderLight', '#E0E0E0')};"
            )
        if self._right_panel is not None:
            self._right_panel.setStyleSheet(f"background-color: {bg_color};")
        if self._right_scroll is not None:
            self._right_scroll.setStyleSheet(f"background-color: {bg_color};")
        if self._right_content is not None:
            self._right_content.setStyleSheet(f"background-color: {bg_color};")
        if self._bottom_bar is not None:
            self._bottom_bar.setStyleSheet(self._bottom_bar_qss())
        if self._usage_label is not None:
            self._usage_label.setStyleSheet(
                f"color: {self._get_color('textSecondary', '#666666')}; font-size: 12px;"
            )
        if self._save_btn is not None:
            self._save_btn.setStyleSheet(self._save_btn_qss())

        # 详情页内联样式随构建生成，重建当前 Provider 详情以应用新颜色；
        # 重建前捕获未保存的表单值，避免用户输入丢失
        if self._current_provider_name:
            was_dirty = self._is_dirty
            form_values = self._capture_form_values()
            self._show_provider_detail(self._current_provider_name)
            self._restore_form_values(form_values)
            self._is_dirty = was_dirty
            if self._save_btn is not None:
                self._save_btn.setEnabled(was_dirty)

    def _capture_form_values(self) -> Dict[str, Any]:
        """捕获当前详情页表单值（用于主题刷新重建后恢复）."""
        return {
            "api_key": self._api_key_edit.text() if self._api_key_edit else "",
            "base_url": self._api_url_edit.text() if self._api_url_edit else "",
            "chat_model": (
                self._chat_model_combo.currentText() if self._chat_model_combo else ""
            ),
            "embedding_model": (
                self._emb_model_combo.currentText() if self._emb_model_combo else ""
            ),
            "enabled_chat": (
                self._enable_toggle.isChecked() if self._enable_toggle else False
            ),
        }

    def _restore_form_values(self, values: Dict[str, Any]) -> None:
        """将捕获的表单值恢复到重建后的详情页控件."""
        if self._api_key_edit:
            self._api_key_edit.setText(values.get("api_key", ""))
        if self._api_url_edit:
            self._api_url_edit.setText(values.get("base_url", ""))
        if self._chat_model_combo:
            chat_model = values.get("chat_model", "")
            if chat_model and self._chat_model_combo.findText(chat_model) >= 0:
                self._chat_model_combo.setCurrentText(chat_model)
        if self._emb_model_combo:
            emb_model = values.get("embedding_model", "")
            if emb_model and self._emb_model_combo.findText(emb_model) >= 0:
                self._emb_model_combo.setCurrentText(emb_model)
        if self._enable_toggle:
            self._enable_toggle.setChecked(values.get("enabled_chat", False))

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
            # 有未保存修改时显式提示，不再静默自动保存
            reply = QMessageBox.question(
                self,
                "未保存的修改",
                f"供应商「{self._current_provider_name}」的配置已修改，是否保存？",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._save_current_provider()
            elif reply == QMessageBox.StandardButton.Cancel:
                # 取消切换：恢复选中之前的 Provider（阻断信号避免递归）
                if self._provider_list_widget:
                    self._provider_list_widget.blockSignals(True)
                    previous_item = self._provider_items.get(
                        self._current_provider_name
                    )
                    if previous_item:
                        self._provider_list_widget.setCurrentItem(previous_item)
                    self._provider_list_widget.blockSignals(False)
                return
            # Discard：放弃修改，继续切换

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

        self._build_api_config_card(config)

        self._build_model_list_card(provider_name, config)

        if config.provider_type == "openai":
            self._build_custom_models_card(provider_name, config)

        self._build_model_selection_card(config)

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

        # Logo - 显示 Provider Logo（圆形 48x48）
        self._header_logo_label = QLabel()
        self._header_logo_label.setFixedSize(48, 48)
        self._header_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        logo_path = self._get_logo_path(config.provider_type)
        if logo_path:
            pixmap = self._load_circular_pixmap(logo_path, 48)
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
        name_font.setPointSize(16)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setStyleSheet(f"color: {text_primary};")
        name_layout.addWidget(name_label)

        type_label = QLabel(config.provider_type)
        type_label.setStyleSheet(f"color: {text_secondary}; font-size: 11px;")
        name_layout.addWidget(type_label)

        name_layout.addStretch()
        header_layout.addLayout(name_layout, 1)

        # Enable toggle
        self._enable_toggle = QCheckBox("启用")
        self._enable_toggle.setAccessibleName("启用供应商")
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
                border-radius: 24px;
                color: white;
                font-size: 18px;
                font-weight: bold;
            }}
        """)

    def _build_api_config_card(self, config: ProviderConfig) -> None:
        """构建 API 配置卡片：合并密钥、地址、检测按钮."""
        if not self._detail_layout:
            return

        from ui.dialog.llm_settings_components import ConfigCard
        card = ConfigCard("API 配置")

        text_primary = self._get_color('textPrimary', '#333333')
        text_secondary = self._get_color('textSecondary', '#999999')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')
        link_color = self._get_color('link', '#4A90D9')
        hover_bg = self._get_color('controlFillHover', '#F5F5F5')

        # API 密钥
        key_label = QLabel("API 密钥")
        key_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        card.add_widget(key_label)

        key_row = QHBoxLayout()
        key_row.setSpacing(8)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setAccessibleName("API 密钥输入框")
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
        key_row.addWidget(self._api_key_edit, 1)

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
        key_row.addWidget(eye_btn)
        card.add_layout(key_row)

        if config.provider_type.lower() in self._PROVIDER_KEY_LINKS:
            link_label = QLabel("<a href='#'>点击这里获取密钥</a>")
            link_label.setCursor(Qt.CursorShape.PointingHandCursor)
            link_label.setTextFormat(Qt.TextFormat.RichText)
            link_label.setStyleSheet(f"color: {link_color}; font-size: 12px;")
            link_label.linkActivated.connect(
                lambda: self._open_provider_link(config.provider_type)
            )
        else:
            # 未知供应商没有可用的密钥链接，禁用该入口（不再 fallback 到无关网站）
            link_label = QLabel("该供应商暂无密钥获取链接")
            link_label.setEnabled(False)
            link_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        card.add_widget(link_label)

        # 细分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {border_color};")
        card.add_widget(sep)

        # API 地址
        url_label = QLabel("API 地址")
        url_label.setStyleSheet(f"color: {text_primary}; font-weight: 500;")
        card.add_widget(url_label)

        self._api_url_edit = QLineEdit()
        self._api_url_edit.setAccessibleName("API 地址输入框")
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
        card.add_widget(self._api_url_edit)

        preview_label = QLabel("请求将发送至此地址")
        preview_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        card.add_widget(preview_label)

        # 检测按钮（真实连通性检测：后台线程拉取模型列表）
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        validate_btn = ActionButton("检测供应商有效性", "✓")
        validate_btn.setAccessibleName("检测供应商有效性")
        validate_btn.clicked.connect(self._on_validate_provider)
        self._validate_btn = validate_btn
        btn_row.addWidget(validate_btn)
        btn_row.addStretch()
        card.add_layout(btn_row)

        self._detail_layout.addWidget(card)

    def _build_model_list_card(
        self, provider_name: str, config: ProviderConfig
    ) -> None:
        """构建模型列表卡片."""
        if not self._detail_layout:
            return

        from ui.dialog.llm_settings_components import ConfigCard
        card = ConfigCard("模型列表")

        text_primary = self._get_color('textPrimary', '#333333')

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(16)

        self._preset_radio = QRadioButton("使用本地预设列表")
        self._api_radio = QRadioButton("从 API 获取")

        radio_layout.addWidget(self._preset_radio)
        radio_layout.addWidget(self._api_radio)
        radio_layout.addStretch()
        card.add_layout(radio_layout)

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

        card.add_widget(self._model_stack)
        self._detail_layout.addWidget(card)

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

    def _build_model_selection_card(self, config: ProviderConfig) -> None:
        """构建默认模型设置卡片."""
        if not self._detail_layout:
            return

        from ui.dialog.llm_settings_components import ConfigCard
        card = ConfigCard("默认模型设置")

        text_primary = self._get_color('textPrimary', '#333333')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')

        chat_row = QHBoxLayout()
        chat_label = QLabel("当前聊天模型")
        chat_label.setFixedWidth(120)
        chat_label.setStyleSheet(f"color: {text_primary};")
        self._chat_model_combo = QComboBox()
        self._chat_model_combo.setAccessibleName("聊天模型选择")
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
        card.add_layout(chat_row)

        emb_row = QHBoxLayout()
        emb_label = QLabel("当前 Embedding 模型")
        emb_label.setFixedWidth(120)
        emb_label.setStyleSheet(f"color: {text_primary};")
        self._emb_model_combo = QComboBox()
        self._emb_model_combo.setAccessibleName("Embedding 模型选择")
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
        card.add_layout(emb_row)

        self._detail_layout.addWidget(card)

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
        """获取预设模型列表（表驱动：_PRESET_PROVIDERS + _PRESET_MODEL_GROUPS）."""
        if provider_name == "openai":
            # openai 走用户自定义模型列表
            try:
                config = self._llm_config.get_provider(provider_name)
                if config:
                    return [
                        ModelInfo.from_dict(m)
                        for m in config.extra.get("custom_models", [])
                    ]
            except Exception:
                pass
            return []

        spec = _PRESET_PROVIDERS.get(provider_name)
        if not spec:
            return []

        models: List[ModelInfo] = []
        try:
            module_name, class_name = spec
            provider_cls = getattr(importlib.import_module(module_name), class_name)
            details = getattr(provider_cls, "MODEL_DETAILS", {})

            for attr, caps, fc_from_info in _PRESET_MODEL_GROUPS:
                for model_id in getattr(provider_cls, attr, []):
                    info = details.get(model_id, {})
                    models.append(
                        ModelInfo(
                            id=model_id,
                            name=info.get("name", model_id),
                            support_chat=caps.get("support_chat", False),
                            support_embedding=caps.get("support_embedding", False),
                            support_vision=caps.get("support_vision", False),
                            support_function_calling=(
                                info.get("support_function_calling", False)
                                if fc_from_info
                                else False
                            ),
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
        """触发从 API 获取模型列表（QThread 后台执行，不阻塞主线程）."""
        if self._fetch_worker is not None and self._fetch_worker.isRunning():
            return  # 已有获取任务进行中

        if self._fetch_btn:
            self._fetch_btn.setEnabled(False)
            self._fetch_btn.setText("获取中...")
        # “获取中...”状态真实可见：列表区域同步显示加载占位
        self._set_fetched_list_message("正在获取模型列表...")

        # worker 不以对话框为 parent，避免对话框关闭时线程仍在运行导致崩溃；
        # 结束后通过 deleteLater 自动释放
        self._fetch_worker = FetchModelsWorker(self._llm_provider, provider_name)
        self._fetch_worker.succeeded.connect(self._on_fetch_models_done)
        self._fetch_worker.failed.connect(self._on_fetch_models_failed)
        self._fetch_worker.finished.connect(self._fetch_worker.deleteLater)
        self._fetch_worker.start()

    def _set_fetched_list_message(self, text: str) -> None:
        """在获取列表区域显示一条提示文本（加载占位/错误占位）."""
        if not self._fetched_list_layout:
            return
        while self._fetched_list_layout.count():
            item = self._fetched_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        label = QLabel(text)
        label.setStyleSheet(
            f"color: {self._get_color('textSecondary', '#666666')};"
        )
        self._fetched_list_layout.addWidget(label)

    def _restore_fetch_btn(self) -> None:
        """恢复获取按钮状态."""
        if self._fetch_btn:
            self._fetch_btn.setEnabled(True)
            self._fetch_btn.setText("从 API 获取模型列表")

    def _on_fetch_models_done(self, provider_name: str, models: list) -> None:
        """模型列表获取完成（主线程槽）."""
        self._fetch_worker = None
        self._fetched_models[provider_name] = models
        self._populate_fetched_list(provider_name)
        if self._current_provider_name == provider_name:
            config = self._llm_config.get_provider(provider_name)
            if config:
                self._populate_model_combos(provider_name, config)
        self._restore_fetch_btn()

    def _on_fetch_models_failed(self, provider_name: str, message: str) -> None:
        """模型列表获取失败（主线程槽）：显示真实错误原因."""
        self._fetch_worker = None
        self._set_fetched_list_message(f"获取失败：{message}")
        QMessageBox.warning(self, "获取失败", f"无法获取模型列表：{message}")
        self._restore_fetch_btn()


    def _on_validate_provider(self) -> None:
        """检测 Provider：先校验配置格式，再后台执行真实连通性检测."""
        if not self._current_provider_name:
            return
        if self._validate_worker is not None and self._validate_worker.isRunning():
            return  # 检测进行中

        try:
            provider = self._llm_provider.get_provider(self._current_provider_name)
            if not provider:
                QMessageBox.warning(self, "检测失败", "Provider 未初始化。")
                return
            if not provider.validate_config():
                QMessageBox.warning(
                    self, "检测失败", "供应商配置不完整，请检查 API Key 和 API 地址。"
                )
                return
        except Exception as e:
            QMessageBox.warning(self, "检测失败", f"检测时出错：{str(e)}")
            return

        # 后台执行真实连通性检测（拉取模型列表），结果通过信号回主线程。
        # worker 不以对话框为 parent，避免对话框关闭时线程仍在运行导致崩溃；
        # 线程启动推迟到事件循环下一拍，确保对话框状态稳定后再执行
        if self._validate_btn:
            self._validate_btn.setEnabled(False)
            self._validate_btn.setText("检测中...")
        self._validate_worker = ValidateProviderWorker(
            self._llm_provider, self._current_provider_name
        )
        self._validate_worker.succeeded.connect(self._on_validate_done)
        self._validate_worker.failed.connect(self._on_validate_failed)
        self._validate_worker.finished.connect(self._validate_worker.deleteLater)
        QTimer.singleShot(0, self._validate_worker.start)

    def _restore_validate_btn(self) -> None:
        """恢复检测按钮状态."""
        if self._validate_btn:
            self._validate_btn.setEnabled(True)
            self._validate_btn.setText("检测供应商有效性")

    def _on_validate_done(self, provider_name: str, model_count: int) -> None:
        """连通性检测成功（主线程槽）."""
        self._validate_worker = None
        self._restore_validate_btn()
        QMessageBox.information(
            self, "检测成功", f"供应商「{provider_name}」连通正常，检测到 {model_count} 个可用模型。"
        )

    def _on_validate_failed(self, provider_name: str, message: str) -> None:
        """连通性检测失败（主线程槽）：显示真实错误原因."""
        self._validate_worker = None
        self._restore_validate_btn()
        QMessageBox.warning(
            self, "检测失败", f"供应商「{provider_name}」连接失败：{message}"
        )


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
        # 保存成功后关闭对话框（保存即完成；“取消”仅用于放弃修改）
        self.accept()

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
        """打开供应商密钥获取链接（未知供应商不跳转，无 fallback）."""
        import webbrowser

        url = self._PROVIDER_KEY_LINKS.get(provider_type.lower())
        if url:
            webbrowser.open(url)

    # ------------------------------------------------------------------ #
    # Custom Models (OpenAI Provider)                                     #
    # ------------------------------------------------------------------ #

    def _build_custom_models_card(self, provider_name: str, config: ProviderConfig) -> None:
        """构建自定义模型管理卡片."""
        if not self._detail_layout:
            return

        from ui.dialog.llm_settings_components import ConfigCard
        card = ConfigCard("自定义模型")

        text_secondary = self._get_color('textSecondary', '#999999')
        border_color = self._get_color('borderLight', '#E0E0E0')
        accent = self._get_color('accent', '#4A90D9')
        hover_bg = self._get_color('controlFillHover', '#F5F5F5')

        # 标题行：说明 + 添加按钮
        header_row = QHBoxLayout()
        header_label = QLabel("管理该供应商的可用模型列表")
        header_label.setStyleSheet(f"color: {text_secondary}; font-size: 12px;")
        header_row.addWidget(header_label)
        header_row.addStretch()

        add_btn = QPushButton("+ 添加模型")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.setFixedHeight(32)
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QPushButton:hover {{
                background-color: {self._get_color('accentLight', '#4CC2FF')};
            }}
        """)
        add_btn.clicked.connect(lambda: self._on_add_custom_model(provider_name))
        header_row.addWidget(add_btn)
        card.add_layout(header_row)

        # 模型列表区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(300)
        scroll.setMaximumHeight(900)

        container = QWidget()
        list_layout = QVBoxLayout(container)
        list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        list_layout.setSpacing(4)
        list_layout.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(container)
        card.add_widget(scroll)

        self._refresh_custom_models_list(provider_name, list_layout)

        self._detail_layout.addWidget(card)

    def _refresh_custom_models_list(self, provider_name: str, layout: QVBoxLayout) -> None:
        """刷新自定义模型列表显示."""
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        custom_models = config.extra.get("custom_models", [])
        text_secondary = self._get_color('textSecondary', '#666666')
        border_color = self._get_color('borderLight', '#E0E0E0')
        hover_bg = self._get_color('controlFillHover', '#F5F5F5')
        accent = self._get_color('accent', '#4A90D9')

        if not custom_models:
            empty_label = QLabel("暂无自定义模型，点击上方按钮添加")
            empty_label.setStyleSheet(f"color: {text_secondary};")
            layout.addWidget(empty_label)
            layout.addStretch()
            return

        for idx, model_data in enumerate(custom_models):
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(12)
            row_widget.setStyleSheet(f"""
                QWidget {{
                    background-color: transparent;
                    border: 1px solid {border_color};
                    border-radius: 6px;
                }}
                QWidget:hover {{
                    background-color: {hover_bg};
                }}
            """)

            # 模型名称/ID
            model_id = model_data.get("id", "")
            model_name = model_data.get("name", model_id)
            name_label = QLabel(f"<b>{model_name}</b> <span style='color:{text_secondary};font-size:11px;'>({model_id})</span>")
            name_label.setTextFormat(Qt.TextFormat.RichText)
            row_layout.addWidget(name_label, 1)

            # 类型标签
            type_tags = []
            if model_data.get("support_chat"):
                type_tags.append("Chat")
            if model_data.get("support_embedding"):
                type_tags.append("Embedding")
            if model_data.get("support_vision"):
                type_tags.append("Vision")
            tag_text = ", ".join(type_tags) if type_tags else "-"
            tag_label = QLabel(tag_text)
            tag_label.setStyleSheet(f"color: {accent}; font-size: 11px;")
            tag_label.setFixedWidth(100)
            row_layout.addWidget(tag_label)

            # 上下文长度
            ctx = model_data.get("context_length")
            ctx_label = QLabel(f"{ctx or '-'}" if ctx else "-")
            ctx_label.setStyleSheet(f"color: {text_secondary}; font-size: 11px;")
            ctx_label.setFixedWidth(60)
            ctx_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            row_layout.addWidget(ctx_label)

            # 编辑按钮
            edit_btn = QPushButton("编辑")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setFixedHeight(24)
            edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {accent};
                    border: none;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    text-decoration: underline;
                }}
            """)
            edit_btn.clicked.connect(lambda checked, i=idx: self._on_edit_custom_model(provider_name, i))
            row_layout.addWidget(edit_btn)

            # 删除按钮
            del_btn = QPushButton("删除")
            del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            del_btn.setFixedHeight(24)
            del_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #E74C3C;
                    border: none;
                    font-size: 12px;
                }
                QPushButton:hover {
                    text-decoration: underline;
                }
            """)
            del_btn.clicked.connect(lambda checked, i=idx: self._on_delete_custom_model(provider_name, i))
            row_layout.addWidget(del_btn)

            layout.addWidget(row_widget)

        layout.addStretch()

    def _on_add_custom_model(self, provider_name: str) -> None:
        """添加自定义模型."""
        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        dialog = ModelEditDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            model_data = dialog.get_model_data()
            if not model_data.get("id"):
                QMessageBox.warning(self, "添加失败", "模型 ID 不能为空")
                return

            custom_models = config.extra.get("custom_models", [])
            # 检查 ID 是否已存在
            if any(m.get("id") == model_data["id"] for m in custom_models):
                QMessageBox.warning(self, "添加失败", f"模型 ID '{model_data['id']}' 已存在")
                return

            custom_models.append(model_data)
            config.extra["custom_models"] = custom_models
            self._mark_dirty()
            # 刷新当前显示的详情页
            self._show_provider_detail(provider_name)

    def _on_edit_custom_model(self, provider_name: str, model_index: int) -> None:
        """编辑自定义模型."""
        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        custom_models = config.extra.get("custom_models", [])
        if model_index < 0 or model_index >= len(custom_models):
            return

        model_data = custom_models[model_index]
        dialog = ModelEditDialog(self, model_data)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_model_data()
            if not new_data.get("id"):
                QMessageBox.warning(self, "编辑失败", "模型 ID 不能为空")
                return

            # 如果 ID 改变了，检查是否冲突
            if new_data["id"] != model_data.get("id"):
                if any(m.get("id") == new_data["id"] for i, m in enumerate(custom_models) if i != model_index):
                    QMessageBox.warning(self, "编辑失败", f"模型 ID '{new_data['id']}' 已存在")
                    return

            custom_models[model_index] = new_data
            config.extra["custom_models"] = custom_models
            self._mark_dirty()
            self._show_provider_detail(provider_name)

    def _on_delete_custom_model(self, provider_name: str, model_index: int) -> None:
        """删除自定义模型."""
        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        custom_models = config.extra.get("custom_models", [])
        if model_index < 0 or model_index >= len(custom_models):
            return

        model_data = custom_models[model_index]
        model_name = model_data.get("name", model_data.get("id", ""))
        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除模型 '{model_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            custom_models.pop(model_index)
            config.extra["custom_models"] = custom_models
            self._mark_dirty()
            self._show_provider_detail(provider_name)


class ModelEditDialog(QDialog):
    """模型编辑对话框 - 用于添加/编辑自定义模型."""

    def __init__(self, parent=None, model_data: Optional[Dict[str, Any]] = None):
        super().__init__(parent)
        self._model_data = model_data or {}
        self.setWindowTitle("编辑模型" if model_data else "添加模型")
        self.setMinimumWidth(420)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化对话框界面."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 模型 ID
        id_label = QLabel("模型 ID *")
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("例如：gpt-4o")
        self._id_edit.setText(self._model_data.get("id", ""))
        layout.addWidget(id_label)
        layout.addWidget(self._id_edit)

        # 显示名称
        name_label = QLabel("显示名称")
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("留空则使用模型 ID")
        self._name_edit.setText(self._model_data.get("name", ""))
        layout.addWidget(name_label)
        layout.addWidget(self._name_edit)

        # 上下文长度
        ctx_label = QLabel("上下文长度")
        self._ctx_spin = QSpinBox()
        self._ctx_spin.setRange(0, 9999999)
        self._ctx_spin.setSingleStep(1000)
        self._ctx_spin.setValue(self._model_data.get("context_length", 128000))
        self._ctx_spin.setSpecialValueText("未设置")
        layout.addWidget(ctx_label)
        layout.addWidget(self._ctx_spin)

        # 类型复选框
        type_label = QLabel("支持能力")
        layout.addWidget(type_label)

        type_grid = QGridLayout()
        type_grid.setSpacing(8)

        self._chat_check = QCheckBox("聊天 Chat")
        self._chat_check.setChecked(self._model_data.get("support_chat", True))
        type_grid.addWidget(self._chat_check, 0, 0)

        self._stream_check = QCheckBox("流式 Streaming")
        self._stream_check.setChecked(self._model_data.get("support_streaming", True))
        type_grid.addWidget(self._stream_check, 0, 1)

        self._embed_check = QCheckBox("嵌入 Embedding")
        self._embed_check.setChecked(self._model_data.get("support_embedding", False))
        type_grid.addWidget(self._embed_check, 1, 0)

        self._vision_check = QCheckBox("视觉 Vision")
        self._vision_check.setChecked(self._model_data.get("support_vision", False))
        type_grid.addWidget(self._vision_check, 1, 1)

        self._fc_check = QCheckBox("函数调用 Function Calling")
        self._fc_check.setChecked(self._model_data.get("support_function_calling", False))
        type_grid.addWidget(self._fc_check, 2, 0, 1, 2)

        layout.addLayout(type_grid)

        # 价格
        price_label = QLabel("定价（元 / 1M tokens）")
        layout.addWidget(price_label)

        price_row = QHBoxLayout()
        price_row.addWidget(QLabel("输入："))
        self._input_price = QDoubleSpinBox()
        self._input_price.setRange(0, 99999)
        self._input_price.setDecimals(6)
        self._input_price.setSingleStep(1.0)
        # 定价单位为元/百万 tokens:优先读 per_1m 新键,兼容 per_1k 旧键(×1000)
        self._input_price.setValue(self._model_data.get(
            "input_price_per_1m", self._model_data.get("input_price_per_1k", 0.0) * 1000))
        price_row.addWidget(self._input_price)
        price_row.addWidget(QLabel("输出："))
        self._output_price = QDoubleSpinBox()
        self._output_price.setRange(0, 99999)
        self._output_price.setDecimals(6)
        self._output_price.setSingleStep(1.0)
        self._output_price.setValue(self._model_data.get(
            "output_price_per_1m", self._model_data.get("output_price_per_1k", 0.0) * 1000))
        price_row.addWidget(self._output_price)
        layout.addLayout(price_row)

        layout.addStretch()

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        btn_row.addWidget(save_btn)

        layout.addLayout(btn_row)

    def get_model_data(self) -> Dict[str, Any]:
        """获取用户填写的模型数据.

        Returns:
            Dict[str, Any]: 模型配置字典
        """
        model_id = self._id_edit.text().strip()
        name = self._name_edit.text().strip()
        return {
            "id": model_id,
            "name": name if name else model_id,
            "context_length": self._ctx_spin.value() if self._ctx_spin.value() > 0 else None,
            "support_chat": self._chat_check.isChecked(),
            "support_streaming": self._stream_check.isChecked(),
            "support_embedding": self._embed_check.isChecked(),
            "support_vision": self._vision_check.isChecked(),
            "support_function_calling": self._fc_check.isChecked(),
            "input_price_per_1m": self._input_price.value(),
            "output_price_per_1m": self._output_price.value(),
        }