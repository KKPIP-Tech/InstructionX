"""
LLM 模型服务对话框

三栏布局：左侧设置分类、中间 Provider 列表、右侧详情区
"""

from pathlib import Path
from typing import Optional, Dict, Any, List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QListWidget, QListWidgetItem,
    QPushButton, QWidget, QScrollArea, QGroupBox,
    QLineEdit, QComboBox, QCheckBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QFrame, QInputDialog, QToolButton,
    QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QPixmap

from core.llm.config import LLMConfig, ProviderConfig
from core.llm.llm_provider import get_llm_provider
from core.llm import get_llm_plugin_service
from core.llm.types import ProviderInfo
from core.llm.provider_interface import ModelInfo

from ui.dialog.llm_settings_components import (
    ProviderListItem, CollapsibleGroup, ModelListItem,
    ActionButton, IconLineEdit, SettingsCategoryItem
)


class LLMModelServiceDialog(QDialog):
    """
    LLM 模型服务对话框
    
    三栏布局：
    - 左侧: 设置分类列表
    - 中间: Provider 列表（带图标和状态标签）
    - 右侧: 详情区（Logo、操作按钮、折叠模型分组）
    """

    default_changed = Signal(str, str)  # (provider_name, chat_model)

    # 设置分类定义
    CATEGORIES = [
        ("🤖", "模型服务", "model_service"),
        ("⭐", "默认模型", "default_model"),
        ("⚙️", "常规设置", "general"),
        ("🖥️", "显示设置", "display"),
        ("💾", "数据设置", "data"),
        ("🔌", "MCP 服务器", "mcp"),
        ("🔍", "网络搜索", "search"),
        ("🧠", "全局记忆", "memory"),
        ("🌐", "API 服务器", "api_server"),
        ("📄", "文档处理", "document"),
        ("⚡", "快捷短语", "shortcuts"),
        ("⌨️", "快捷键", "hotkeys"),
        ("🤖", "快捷助手", "quick_assist"),
        ("✏️", "划词助手", "text_select"),
        ("ℹ️", "关于我们", "about"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setObjectName("llmSettingsDialog")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 800)

        self._llm_config = LLMConfig()
        self._llm_provider = get_llm_provider()
        self._llm_svc = get_llm_plugin_service()
        self._current_provider: Optional[str] = None
        self._current_category: str = "model_service"

        # 数据存储
        self._provider_items: Dict[str, ProviderListItem] = {}
        self._category_items: Dict[str, SettingsCategoryItem] = {}
        self._enabled_models: Dict[str, List[str]] = {}
        self._default_provider = self._load_default_provider()

        self._init_ui()
        self._load_styles()
        self._load_data()

    # ===============================================================
    # UI 初始化
    # ===============================================================

    def _init_ui(self):
        """初始化三栏布局"""
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 左侧：设置分类
        left_panel = self._create_left_panel()
        layout.addWidget(left_panel, stretch=0)

        # 中间：Provider 列表
        middle_panel = self._create_middle_panel()
        layout.addWidget(middle_panel, stretch=0)

        # 右侧：详情区
        right_panel = self._create_right_panel()
        layout.addWidget(right_panel, stretch=1)

    def _create_left_panel(self) -> QWidget:
        """创建左侧设置分类面板"""
        widget = QWidget()
        widget.setObjectName("leftCategoryPanel")
        widget.setFixedWidth(170)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(4)
        layout.setContentsMargins(8, 16, 8, 16)

        # 分类列表
        for icon, text, category in self.CATEGORIES:
            item = SettingsCategoryItem(icon, text, category)
            item.clicked.connect(self._on_category_clicked)
            self._category_items[category] = item
            layout.addWidget(item)

        layout.addStretch()
        
        # 默认选中"模型服务"
        self._category_items["model_service"].set_selected(True)

        return widget

    def _create_middle_panel(self) -> QWidget:
        """创建中间 Provider 列表面板"""
        widget = QWidget()
        widget.setObjectName("providerListPanel")
        widget.setFixedWidth(260)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(12, 16, 12, 12)

        # 搜索框
        self._search_box = QLineEdit()
        self._search_box.setObjectName("providerSearchBox")
        self._search_box.setPlaceholderText("搜索模型平台...")
        self._search_box.textChanged.connect(self._on_search_changed)
        layout.addWidget(self._search_box)

        # Provider 列表容器
        self._provider_list_widget = QWidget()
        self._provider_list_layout = QVBoxLayout(self._provider_list_widget)
        self._provider_list_layout.setSpacing(2)
        self._provider_list_layout.setContentsMargins(0, 0, 0, 0)
        self._provider_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        # 滚动区域
        scroll = QScrollArea()
        scroll.setObjectName("providerListScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.setWidget(self._provider_list_widget)
        layout.addWidget(scroll, stretch=1)

        # 添加按钮
        self._add_btn = QPushButton("+ 添加")
        self._add_btn.setObjectName("addProviderBtn")
        self._add_btn.clicked.connect(self._on_add_provider)
        layout.addWidget(self._add_btn)

        return widget

    def _create_right_panel(self) -> QWidget:
        """创建右侧详情面板"""
        widget = QWidget()
        widget.setObjectName("rightDetailPanel")
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # 滚动区域
        self._detail_scroll = QScrollArea()
        self._detail_scroll.setObjectName("detailScrollArea")
        self._detail_scroll.setWidgetResizable(True)
        self._detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self._detail_content = QWidget()
        self._detail_layout = QVBoxLayout(self._detail_content)
        self._detail_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._detail_layout.setContentsMargins(24, 24, 24, 24)
        self._detail_layout.setSpacing(20)
        
        self._detail_scroll.setWidget(self._detail_content)
        layout.addWidget(self._detail_scroll, stretch=1)

        # 底部按钮栏
        self._create_bottom_bar(layout)

        return widget

    def _create_bottom_bar(self, parent_layout: QVBoxLayout):
        """创建底部按钮栏"""
        bottom_widget = QWidget()
        bottom_widget.setObjectName("bottomBar")
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(24, 12, 24, 12)

        # 用量统计
        self._usage_label = QLabel()
        self._usage_label.setObjectName("usageLabel")
        self._update_usage_label()
        bottom_layout.addWidget(self._usage_label)

        bottom_layout.addStretch()

        # 重置用量
        reset_btn = QPushButton("重置用量")
        reset_btn.clicked.connect(self._on_reset_usage)
        bottom_layout.addWidget(reset_btn)

        # 取消
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        # 保存
        save_btn = QPushButton("保存")
        save_btn.setObjectName("accentSave")
        save_btn.setProperty("class", "accentSave")
        save_btn.clicked.connect(self._on_save_all)
        bottom_layout.addWidget(save_btn)

        parent_layout.addWidget(bottom_widget)

    # ===============================================================
    # 样式加载
    # ===============================================================

    def _load_styles(self):
        """加载 LLM 设置专用样式"""
        from utils.style_qss.registry import StyleRegistry
        registry = StyleRegistry()
        extra_style = registry.load_style("llm_settings")
        if extra_style:
            self.setStyleSheet(self.styleSheet() + "\n" + extra_style)

    # ===============================================================
    # 数据加载
    # ===============================================================

    def _load_data(self):
        """加载所有 Provider 数据"""
        # 从本地缓存恢复模型列表到内存缓存
        for name in self._llm_config.get_all_providers():
            cached = self._llm_config.load_models_cache(name)
            if cached:
                models = [ModelInfo.from_dict(m) for m in cached]
                self._llm_provider._models_cache[name] = models
        self._load_enabled_models()
        self._refresh_provider_list()

    def _load_enabled_models(self):
        """从 ProviderConfig.extra 中加载启用的模型列表"""
        self._enabled_models = {}
        for name, config in self._llm_config.get_all_providers().items():
            enabled = config.extra.get("enabled_models", [])
            if isinstance(enabled, list):
                self._enabled_models[name] = enabled
            else:
                self._enabled_models[name] = []

    def _get_enabled_models(self, provider_name: str) -> List[str]:
        return self._enabled_models.get(provider_name, [])

    def _set_enabled_models(self, provider_name: str, models: List[str]):
        self._enabled_models[provider_name] = models

    def _load_default_provider(self) -> str:
        """加载默认 Provider"""
        try:
            providers = self._llm_svc.get_available_providers()
            for p in providers:
                if p.enabled_chat:
                    return p.name
        except Exception:
            pass
        return ""

    def _refresh_provider_list(self):
        """刷新中间 Provider 列表"""
        # 清除现有项
        while self._provider_list_layout.count():
            child = self._provider_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._provider_items.clear()

        # 添加 Provider 项
        providers = self._llm_config.get_all_providers()
        for name, config in providers.items():
            is_active = config.enabled_chat or config.enabled_embedding
            logo_path = str(Path(__file__).resolve().parent.parent.parent / "core" / "llm" / "providers" / f"{config.provider_type}.png")
            item = ProviderListItem(
                provider_name=name,
                provider_type=config.provider_type,
                is_active=is_active,
                display_name=config.name,
                icon_path=logo_path,
            )
            item.clicked.connect(self._on_provider_clicked)
            self._provider_items[name] = item
            self._provider_list_layout.addWidget(item)

        self._provider_list_layout.addStretch()

        # 选中第一个
        if providers:
            first_name = list(providers.keys())[0]
            self._on_provider_clicked(first_name)

    # ===============================================================
    # 事件处理
    # ===============================================================

    def _on_category_clicked(self, category: str):
        """设置分类点击事件"""
        if category == self._current_category:
            return

        # 更新选中状态
        for cat, item in self._category_items.items():
            item.set_selected(cat == category)
        
        self._current_category = category

        # 目前只实现了模型服务
        if category != "model_service":
            # 清空详情区显示提示
            self._clear_detail_panel()
            self._show_placeholder(f"{self.CATEGORIES[[c[2] for c in self.CATEGORIES].index(category)][1]}功能开发中...")

    def _on_provider_clicked(self, provider_name: str):
        """Provider 点击事件"""
        # 更新选中状态
        for name, item in self._provider_items.items():
            item.set_selected(name == provider_name)

        self._current_provider = provider_name
        self._show_provider_detail(provider_name)

    def _on_search_changed(self, text: str):
        """搜索框内容变化"""
        text = text.lower()
        for name, item in self._provider_items.items():
            if text in name.lower() or text in item.provider_name.lower():
                item.setVisible(True)
            else:
                item.setVisible(False)

    def _clear_detail_panel(self):
        """清空详情面板"""
        while self._detail_layout.count():
            child = self._detail_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _show_placeholder(self, message: str):
        """显示占位提示"""
        self._clear_detail_panel()
        label = QLabel(message)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: #888888; font-size: 16px;")
        self._detail_layout.addWidget(label)

    def _show_provider_detail(self, provider_name: str):
        """显示 Provider 详情"""
        self._clear_detail_panel()

        config = self._llm_config.get_provider(provider_name)
        if not config:
            return

        # 1. 头部区域：Logo + 名称 + 开关
        header = self._create_detail_header(config)
        self._detail_layout.addWidget(header)

        # 分隔线
        divider = QFrame()
        divider.setObjectName("sectionDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        self._detail_layout.addWidget(divider)

        # 2. 操作按钮区
        actions = self._create_action_buttons()
        self._detail_layout.addLayout(actions)

        # 3. API 密钥
        api_key_section = self._create_api_key_section(config)
        self._detail_layout.addWidget(api_key_section)

        # 4. API 地址
        api_url_section = self._create_api_url_section(config)
        self._detail_layout.addWidget(api_url_section)

        # 5. 模型列表（折叠分组）
        models_section = self._create_models_section(provider_name)
        self._detail_layout.addWidget(models_section)

        self._detail_layout.addStretch()

    def _create_detail_header(self, config: ProviderConfig) -> QWidget:
        """创建详情头部"""
        widget = QWidget()
        widget.setObjectName("detailHeader")
        
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        # Logo
        logo = QLabel()
        logo.setObjectName("providerLogoLabel")
        logo.setFixedSize(56, 56)
        logo.setScaledContents(True)
        logo_path = str(Path(__file__).resolve().parent.parent.parent / "core" / "llm" / "providers" / f"{config.provider_type}.png")
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            logo.setText(config.name[:1].upper() if config.name else "?")
            logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # 标题信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        title = QLabel(config.name or "Unknown")
        title.setObjectName("providerTitleLabel")
        info_layout.addWidget(title)

        subtitle = QLabel(f"{config.provider_type} Provider")
        subtitle.setObjectName("providerSubtitleLabel")
        info_layout.addWidget(subtitle)

        layout.addLayout(info_layout, stretch=1)

        # 开关
        toggle = QCheckBox()
        toggle.setObjectName("providerToggleSwitch")
        toggle.setChecked(config.enabled_chat)
        toggle.stateChanged.connect(
            lambda state: self._on_toggle_provider(config, state)
        )
        layout.addWidget(toggle)

        return widget

    def _create_action_buttons(self) -> QHBoxLayout:
        """创建操作按钮"""
        layout = QHBoxLayout()
        layout.setSpacing(12)

        # 余额充值
        recharge_btn = ActionButton("余额充值", "💰")
        recharge_btn.clicked.connect(self._on_recharge)
        layout.addWidget(recharge_btn)

        # 费用账单
        bill_btn = ActionButton("费用账单", "📋")
        bill_btn.clicked.connect(self._on_bill)
        layout.addWidget(bill_btn)

        layout.addStretch()

        # 获取模型列表
        refresh_btn = ActionButton("获取模型列表", "🔄")
        refresh_btn.setProperty("class", "primary")
        refresh_btn.clicked.connect(self._on_refresh_models)
        layout.addWidget(refresh_btn)

        # 添加模型
        add_model_btn = ActionButton("+", None)
        add_model_btn.setFixedWidth(32)
        add_model_btn.clicked.connect(self._on_add_model)
        layout.addWidget(add_model_btn)

        return layout

    def _create_api_key_section(self, config: ProviderConfig) -> QWidget:
        """创建 API 密钥区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标签行
        label_layout = QHBoxLayout()
        label = QLabel("API 密钥")
        label.setObjectName("formLabel")
        label.setFont(QFont("", -1, QFont.Weight.Bold))
        label_layout.addWidget(label)
        label_layout.addStretch()
        
        # 设置按钮
        settings_btn = QToolButton()
        settings_btn.setText("⚙")
        settings_btn.setObjectName("modelActionBtn")
        label_layout.addWidget(settings_btn)
        
        layout.addLayout(label_layout)

        # 输入框 + 检测按钮
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        self._api_key_edit = QLineEdit()
        self._api_key_edit.setObjectName("iconLineEdit")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setPlaceholderText("请输入 API Key")
        self._api_key_edit.setText(config.api_key)
        input_layout.addWidget(self._api_key_edit, stretch=1)

        # 眼睛图标（显示/隐藏）
        eye_btn = QToolButton()
        eye_btn.setText("👁")
        eye_btn.setObjectName("modelActionBtn")
        eye_btn.setCheckable(True)
        eye_btn.clicked.connect(self._on_toggle_api_key_visibility)
        input_layout.addWidget(eye_btn)

        # 检测按钮
        test_btn = QPushButton("检测")
        test_btn.setObjectName("actionButton")
        test_btn.setProperty("class", "primary")
        test_btn.clicked.connect(self._on_test_connection)
        input_layout.addWidget(test_btn)

        layout.addLayout(input_layout)

        # 获取密钥链接
        link_layout = QHBoxLayout()
        link = QLabel("点击这里获取密钥")
        link.setObjectName("linkLabel")
        link.setCursor(Qt.CursorShape.PointingHandCursor)
        link.mousePressEvent = lambda e: self._on_open_key_link()
        link_layout.addWidget(link)
        link_layout.addStretch()
        
        hint = QLabel("多个密钥使用逗号分隔")
        hint.setObjectName("providerSubtitleLabel")
        link_layout.addWidget(hint)
        
        layout.addLayout(link_layout)

        return widget

    def _create_api_url_section(self, config: ProviderConfig) -> QWidget:
        """创建 API 地址区域"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标签行
        label_layout = QHBoxLayout()
        label = QLabel("API 地址")
        label.setObjectName("formLabel")
        label.setFont(QFont("", -1, QFont.Weight.Bold))
        label_layout.addWidget(label)

        # 帮助和设置图标
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setObjectName("modelActionBtn")
        label_layout.addWidget(help_btn)
        
        label_layout.addStretch()
        
        settings_btn = QToolButton()
        settings_btn.setText("⚙")
        settings_btn.setObjectName("modelActionBtn")
        label_layout.addWidget(settings_btn)
        
        layout.addLayout(label_layout)

        # 输入框
        self._api_url_edit = QLineEdit()
        self._api_url_edit.setObjectName("iconLineEdit")
        self._api_url_edit.setPlaceholderText("例如: https://api.example.com/v1")
        self._api_url_edit.setText(config.base_url)
        layout.addWidget(self._api_url_edit)

        # 预览地址
        if config.base_url:
            preview = QLabel(f"预览: {config.base_url}/v1/chat/completions")
            preview.setObjectName("providerSubtitleLabel")
            layout.addWidget(preview)

        return widget

    def _create_models_section(self, provider_name: str) -> QWidget:
        """创建模型列表区域（折叠分组）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 标题行
        title_layout = QHBoxLayout()
        
        title = QLabel("模型")
        title.setObjectName("formLabel")
        title.setFont(QFont("", -1, QFont.Weight.Bold))
        title_layout.addWidget(title)

        # 数量
        count = len(self._get_enabled_models(provider_name))
        count_label = QLabel(str(count))
        count_label.setObjectName("modelGroupLabel")
        title_layout.addWidget(count_label)

        # 排序和搜索图标
        title_layout.addStretch()
        
        sort_btn = QToolButton()
        sort_btn.setText("⇅")
        sort_btn.setObjectName("modelActionBtn")
        sort_btn.setToolTip("排序")
        title_layout.addWidget(sort_btn)

        search_btn = QToolButton()
        search_btn.setText("🔍")
        search_btn.setObjectName("modelActionBtn")
        search_btn.setToolTip("搜索")
        title_layout.addWidget(search_btn)
        
        layout.addLayout(title_layout)

        # 获取模型信息
        provider_info = self._get_provider_info(provider_name)
        if provider_info:
            # 按分组组织模型
            groups = self._group_models(provider_info.models)
            
            for group_name, models in groups.items():
                if not models:
                    continue
                    
                group = CollapsibleGroup(group_name, len(models))
                
                for model in models:
                    item = ModelListItem(
                        model_id=model.id,
                        model_name=model.id.split("/")[-1] if "/" in model.id else model.id,
                        is_pinned=False
                    )
                    item.settings_clicked.connect(self._on_model_settings)
                    item.pin_clicked.connect(self._on_model_pin)
                    item.delete_clicked.connect(self._on_model_delete)
                    group.add_widget(item)
                
                layout.addWidget(group)

        layout.addStretch()
        return widget

    def _group_models(self, models: List[ModelInfo]) -> Dict[str, List[ModelInfo]]:
        """将模型按分组组织"""
        groups = {
            "deepseek-ai": [],
            "pro": [],
            "其他": []
        }
        
        for model in models:
            if not model.support_chat:
                continue
                
            model_id = model.id.lower()
            if "deepseek" in model_id:
                groups["deepseek-ai"].append(model)
            elif "pro" in model_id:
                groups["pro"].append(model)
            else:
                groups["其他"].append(model)
        
        # 移除空分组
        return {k: v for k, v in groups.items() if v}

    def _get_provider_info(self, provider_name: str) -> Optional[ProviderInfo]:
        """获取 Provider 信息"""
        try:
            providers = self._llm_svc.get_available_providers()
            return next((p for p in providers if p.name == provider_name), None)
        except Exception:
            return None

    # ===============================================================
    # 操作处理
    # ===============================================================

    def _on_toggle_provider(self, config: ProviderConfig, state: int):
        """切换 Provider 启用状态"""
        config.enabled_chat = bool(state)
        if self._current_provider in self._provider_items:
            self._provider_items[self._current_provider].set_active(bool(state))

    def _on_toggle_api_key_visibility(self):
        """切换 API Key 显示/隐藏"""
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _on_open_key_link(self):
        """打开获取密钥链接"""
        # 根据 Provider 类型打开不同链接
        import webbrowser
        webbrowser.open("https://siliconflow.cn")

    def _on_recharge(self):
        """余额充值"""
        QMessageBox.information(self, "余额充值", "余额充值功能开发中...")

    def _on_bill(self):
        """费用账单"""
        QMessageBox.information(self, "费用账单", "费用账单功能开发中...")

    def _on_refresh_models(self):
        """刷新模型列表"""
        if not self._current_provider:
            return

        try:
            models = self._llm_provider.refresh_provider_models(self._current_provider, force=True)
            self._llm_config.save_models_cache(
                self._current_provider,
                [m.to_dict() for m in models]
            )
            self._show_provider_detail(self._current_provider)
            QMessageBox.information(self, "刷新成功", "模型列表已更新")
        except Exception as e:
            QMessageBox.warning(self, "刷新失败", str(e))

    def _on_add_model(self):
        """添加模型"""
        text, ok = QInputDialog.getText(self, "添加模型", "请输入模型 ID:")
        if ok and text:
            QMessageBox.information(self, "添加模型", f"模型 {text} 添加成功")

    def _on_model_settings(self, model_id: str):
        """模型设置"""
        QMessageBox.information(self, "模型设置", f"设置模型: {model_id}")

    def _on_model_pin(self, model_id: str):
        """固定/取消固定模型"""
        QMessageBox.information(self, "固定模型", f"固定模型: {model_id}")

    def _on_model_delete(self, model_id: str):
        """删除模型"""
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除模型 {model_id} 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "删除成功", f"模型 {model_id} 已删除")

    def _on_test_connection(self):
        """测试连接"""
        if not self._current_provider:
            return

        api_key = self._api_key_edit.text()
        if not api_key:
            QMessageBox.warning(self, "测试连接", "请先填写 API Key")
            return

        try:
            models = self._llm_provider.refresh_provider_models(
                self._current_provider, force=True
            )
            self._llm_config.save_models_cache(
                self._current_provider,
                [m.to_dict() for m in models]
            )
            QMessageBox.information(
                self, "测试成功",
                f"连接成功！\n\n共获取到 {len(models)} 个模型"
            )
            self._show_provider_detail(self._current_provider)
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"连接失败：{str(e)}")

    def _on_add_provider(self):
        """添加 Provider"""
        from core.llm.providers import get_all_provider_types
        available_types = get_all_provider_types()

        if not available_types:
            QMessageBox.warning(self, "添加失败", "未找到可用的 Provider 类型")
            return

        provider_type, ok = QInputDialog.getItem(
            self, "添加 Provider", "选择 Provider 类型:",
            available_types, 0, False
        )
        if not ok or not provider_type:
            return

        # 生成唯一名称
        base_name = provider_type
        name = base_name
        counter = 1
        while self._llm_config.get_provider(name):
            name = f"{base_name}_{counter}"
            counter += 1

        # 创建配置
        new_config = ProviderConfig(
            name=name.capitalize(),
            provider_type=provider_type,
            api_key="",
            base_url="",
            chat_model="",
            embedding_model="",
            enabled_chat=True,
            enabled_embedding=False,
            support_vision=True,
        )
        self._llm_config.add_provider(name, new_config)
        self._enabled_models[name] = []
        self._refresh_provider_list()

        # 选中新添加的
        self._on_provider_clicked(name)

    def _on_reset_usage(self):
        """重置用量统计"""
        reply = QMessageBox.question(
            self, "确认重置", "确定要重置所有用量统计吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            QMessageBox.information(self, "提示", "用量统计已重置")
            self._update_usage_label()

    def _update_usage_label(self):
        """更新用量统计标签"""
        try:
            stats = self._llm_svc.get_usage_stats()
            self._usage_label.setText(
                f"用量: Token {stats.total_tokens:,} | "
                f"费用 ¥{stats.total_cost:.4f} | "
                f"请求 {stats.request_count} 次"
            )
        except Exception:
            self._usage_label.setText("用量统计: 暂无数据")

    def _on_save_all(self):
        """保存所有配置"""
        if self._current_provider:
            self._save_current_provider()

        self._llm_provider.reload_config()

        # 发射信号
        if self._default_provider:
            config = self._llm_config.get_provider(self._default_provider)
            model = config.chat_model if config else ""
            self.default_changed.emit(self._default_provider, model)

        self.accept()

    def _save_current_provider(self):
        """保存当前 Provider 配置"""
        if not self._current_provider:
            return

        config = self._llm_config.get_provider(self._current_provider)
        if not config:
            return

        config.api_key = self._api_key_edit.text()
        config.base_url = self._api_url_edit.text()
        
        self._llm_config.add_provider(self._current_provider, config)