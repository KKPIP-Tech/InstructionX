# ui/dialog/llm_settings/provider_detail_panel.py
"""右栏 Provider 详情面板

视觉：头部（品牌图标 + 名称 + 类型徽章 + 总开关 + 更多菜单）+
平面分区（API 配置 / 模型 / 默认模型，1px hairline + 12px 小标题），
总开关关闭时主体覆盖停用遮罩。

数据：全部编辑采用**自动保存语义**（编辑完成即经 ``get_llm_config()``
落盘，无「保存」按钮；删除类操作保留中文确认弹窗）。模型列表为
``merge_model_entries``（目录预设 + 缓存拉取 + 用户覆写）三路合并结果；
模型开关写 ``enabled`` 覆写、非自定义模型删除写 ``hidden`` 覆写
（均落进 custom_models）。

模型分区的视图与交互已拆分到 ``model_section.ModelSection``，本面板持有
其实例并负责数据装配与落盘；「↻ 刷新」经 FetchModelsWorker 从 API
获取最新模型列表后重渲染。模型的「＋ 添加」与「编辑」（双击模型行）
仅转发 ``sig_add_model_requested`` / ``sig_edit_model_requested`` 信号，
由主壳接模型编辑对话框。
"""

from typing import Any, Callable, Dict, List, Optional, Set

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu,
    QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from core.llm.catalog import PRESET_MODELS, ProviderPreset, get_provider_preset
from core.llm.config import ProviderConfig, get_llm_config
from core.llm.llm_provider import get_llm_provider
from core.llm.model_schema import (
    CAPABILITY_EMBEDDING, CAPABILITY_RERANK, merge_model_entries,
)
from utils.logging_tools import LoggerManager, get_name

from . import theme as _theme_module
from .constants import (
    CHECK_BUTTON_HEIGHT, CHECK_BUTTON_WIDTH, CHECK_STATUS_TOP_GAP,
    CONTENT_MARGIN_BOTTOM, CONTENT_MARGIN_H, CONTENT_MARGIN_TOP,
    CUSTOM_PROVIDER_TYPE_LABEL, DEFAULT_MODEL_LABEL_WIDTH,
    DEFAULT_MODEL_ROW_GAP, EYE_BUTTON_SIZE, FIELD_BLOCK_GAP, FIELD_GAP,
    HEADER_ICON_PX, HEADER_MARGIN_BOTTOM, HEADER_MARGIN_H,
    HEADER_MARGIN_RIGHT, HEADER_MARGIN_TOP, HEADER_NAME_FONT_PX,
    HEADER_SPACING, INPUT_HEIGHT, MORE_BUTTON_SIZE, RESET_BUTTON_HEIGHT,
    RESET_BUTTON_WIDTH, SECTION_CONTENT_GAP, SECTION_GAP,
    WORKER_STOP_WAIT_MS,
)
from .health_check_dialog import HealthCheckDialog
from .icons import provider_icon_pixmap
from .model_section import ModelSection
from .sync_models_dialog import SyncModelsDialog
from .theme import Theme
from .feedback import confirm as _confirm_dialog
from .feedback import info as _info_toast
from .feedback import notice as _notice_dialog
from .widgets import (
    SwitchButton, _badge_style, make_badge, make_eye_icon, make_field_label,
    make_hairline, make_section_label,
)
from .workers import ConnectionCheckWorker, FetchModelsWorker

_logger = LoggerManager()

# 连接检测状态种类：成功 / 失败 / 进行中（muted）
_STATUS_OK = "ok"
_STATUS_ERR = "err"
_STATUS_MUTED = "muted"

# 默认模型下拉「未设置」项的用户数据
_NO_MODEL_DATA = ""

# 模型 id 过滤类型：默认模型下拉的对话 / 嵌入两类
_MODEL_KIND_CHAT = "chat"
_MODEL_KIND_EMBEDDING = "embedding"


class ProviderDetailPanel(QWidget):
    """Provider 详情面板（右栏）

    Signals:
        sig_config_changed(): 实例配置发生变更（已落盘），供主壳协调刷新
        sig_provider_deleted(): 当前实例已删除
        sig_add_model_requested(): 点击「＋ 添加」请求新增模型（扩展点）
        sig_edit_model_requested(object): 双击模型行请求编辑该模型条目
            （统一 schema dict，扩展点）
    """

    sig_config_changed = Signal()
    sig_provider_deleted = Signal()
    sig_add_model_requested = Signal()
    sig_edit_model_requested = Signal(object)

    def __init__(self, parent: Optional[QWidget] = None):
        """构造面板（构建 UI，初始为空态容错）

        Args:
            parent: 父控件
        """
        super().__init__(parent)
        self.setObjectName("DetailPage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._instance_id: Optional[str] = None
        self._preset: Optional[ProviderPreset] = None
        self._check_worker: Optional[ConnectionCheckWorker] = None
        self._fetch_worker: Optional[FetchModelsWorker] = None
        self._entries: List[Dict[str, Any]] = []
        self._status_kind: Optional[str] = None
        self._init_ui()

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建头部 + 主体（滚动分区）+ 停用遮罩"""
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())
        root.addWidget(make_hairline())
        root.addWidget(self._build_body(), 1)
        self._overlay = QLabel("该提供商已停用\n开启右上角开关后进行配置", self)
        self._overlay.setObjectName("OverlayLabel")
        self._overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay.hide()

    def _build_header(self) -> QWidget:
        """构建头部：图标 + 名称 + 类型徽章 + 总开关 + 更多菜单"""
        header_widget = QWidget(self)
        header = QHBoxLayout(header_widget)
        header.setContentsMargins(
            HEADER_MARGIN_H, HEADER_MARGIN_TOP,
            HEADER_MARGIN_RIGHT, HEADER_MARGIN_BOTTOM)
        header.setSpacing(HEADER_SPACING)
        self._icon_label = QLabel(header_widget)
        self._icon_label.setFixedSize(HEADER_ICON_PX, HEADER_ICON_PX)
        header.addWidget(self._icon_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self._name_label = QLabel(header_widget)
        name_font = self._name_label.font()
        name_font.setPixelSize(HEADER_NAME_FONT_PX)
        name_font.setWeight(QFont.Weight.DemiBold)
        self._name_label.setFont(name_font)
        header.addWidget(self._name_label)
        self._type_badge = make_badge("", _theme_module.current_theme().accent)
        header.addWidget(self._type_badge)
        header.addStretch(1)
        self._master_switch = SwitchButton()
        self._master_switch.setToolTip("启用 / 停用该提供商")
        self._master_switch.toggled.connect(self._on_master_toggled)
        header.addWidget(self._master_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self._build_more_button())
        return header_widget

    def _build_more_button(self) -> QToolButton:
        """构建「更多」菜单按钮（重命名 / 删除提供商）"""
        more_btn = QToolButton(self)
        more_btn.setText("⋮")
        more_btn.setFixedSize(MORE_BUTTON_SIZE, MORE_BUTTON_SIZE)
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(more_btn)
        menu.addAction("重命名", self._on_rename)
        delete_action = menu.addAction("删除提供商", self._on_delete_provider)
        delete_action.setProperty("danger", True)
        # 手动弹出菜单：避免 InstantPopup 模式下样式绘制的小箭头
        more_btn.clicked.connect(
            lambda: menu.exec(more_btn.mapToGlobal(more_btn.rect().bottomLeft())))
        return more_btn

    def _build_body(self) -> QWidget:
        """构建主体：滚动区包裹的平面分区内容"""
        self._body = QWidget(self)
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self._body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        # QScrollArea.setWidget 会把内容部件置为 autoFillBackground，且其
        # 调色板可能未继承对话框主题（落成默认浅色）；以 objectName 在 QSS
        # 中强制透明背景（QSS 优先于调色板填充），透出 #DetailPage 底色
        content.setObjectName("DetailContent")
        self._content_layout = QVBoxLayout(content)
        self._content_layout.setContentsMargins(
            CONTENT_MARGIN_H, CONTENT_MARGIN_TOP,
            CONTENT_MARGIN_H, CONTENT_MARGIN_BOTTOM)
        self._content_layout.setSpacing(0)
        self._build_api_section(self._content_layout)
        self._content_layout.addSpacing(SECTION_GAP)
        self._content_layout.addWidget(make_hairline())
        self._content_layout.addSpacing(SECTION_GAP)
        self._build_models_section(self._content_layout)
        self._content_layout.addSpacing(SECTION_GAP)
        self._content_layout.addWidget(make_hairline())
        self._content_layout.addSpacing(SECTION_GAP)
        self._build_default_model_section(self._content_layout)
        self._content_layout.addStretch(1)
        scroll.setWidget(content)
        body_layout.addWidget(scroll)
        return self._body

    # ------------------------------------------------------------------
    # API 配置区
    # ------------------------------------------------------------------

    def _build_api_section(self, parent_layout: QVBoxLayout) -> None:
        """构建 API 配置区：密钥（眼睛/检测/状态）+ 地址（重置）"""
        parent_layout.addWidget(make_section_label("API 配置"))
        parent_layout.addSpacing(SECTION_CONTENT_GAP)
        key_label_row = QHBoxLayout()
        key_label_row.addWidget(make_field_label("API 密钥"))
        key_label_row.addStretch(1)
        self._key_link_btn = QToolButton(self)
        self._key_link_btn.setObjectName("KeyLinkButton")
        self._key_link_btn.setText("获取密钥")
        self._key_link_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._key_link_btn.clicked.connect(self._on_open_key_url)
        key_label_row.addWidget(self._key_link_btn)
        parent_layout.addLayout(key_label_row)
        parent_layout.addSpacing(FIELD_GAP)
        parent_layout.addLayout(self._build_key_row())
        parent_layout.addSpacing(CHECK_STATUS_TOP_GAP)
        self._check_status = QLabel("")
        self._check_status.setObjectName("CheckStatus")
        parent_layout.addWidget(self._check_status)
        parent_layout.addSpacing(FIELD_BLOCK_GAP)
        parent_layout.addWidget(make_field_label("API 地址"))
        parent_layout.addSpacing(FIELD_GAP)
        parent_layout.addLayout(self._build_host_row())

    def _build_key_row(self) -> QHBoxLayout:
        """构建密钥行：密文输入 + 眼睛 + 「检测」按钮"""
        key_row = QHBoxLayout()
        key_row.setSpacing(FIELD_GAP)
        self._key_edit = QLineEdit(self)
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setClearButtonEnabled(True)
        self._key_edit.setFixedHeight(INPUT_HEIGHT)
        self._key_edit.textChanged.connect(self._on_key_changed)
        self._key_edit.editingFinished.connect(self._on_key_edited)
        key_row.addWidget(self._key_edit, 1)
        self._eye_btn = QToolButton(self)
        self._eye_btn.setCheckable(True)
        self._eye_btn.setFixedSize(EYE_BUTTON_SIZE, EYE_BUTTON_SIZE)
        self._eye_btn.setIcon(make_eye_icon(False))
        self._eye_btn.setToolTip("显示 / 隐藏密钥")
        self._eye_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._eye_btn.toggled.connect(self._on_eye_toggled)
        key_row.addWidget(self._eye_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        self._check_btn = QPushButton("检测", self)
        self._check_btn.setProperty("accent", True)
        self._check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._check_btn.setFixedSize(CHECK_BUTTON_WIDTH, CHECK_BUTTON_HEIGHT)
        self._check_btn.clicked.connect(self._on_check_key)
        key_row.addWidget(self._check_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return key_row

    def _build_host_row(self) -> QHBoxLayout:
        """构建地址行：输入框 + 「重置」按钮（清空 base_url 用目录默认）"""
        host_row = QHBoxLayout()
        host_row.setSpacing(FIELD_GAP)
        self._host_edit = QLineEdit(self)
        self._host_edit.setFixedHeight(INPUT_HEIGHT)
        self._host_edit.editingFinished.connect(self._on_host_edited)
        host_row.addWidget(self._host_edit, 1)
        self._reset_btn = QPushButton("重置", self)
        self._reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reset_btn.setFixedSize(RESET_BUTTON_WIDTH, RESET_BUTTON_HEIGHT)
        self._reset_btn.setToolTip("恢复默认 API 地址")
        self._reset_btn.clicked.connect(self._on_host_reset)
        host_row.addWidget(self._reset_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        return host_row

    # ------------------------------------------------------------------
    # 模型区（视图委托 ModelSection）
    # ------------------------------------------------------------------

    def _build_models_section(self, parent_layout: QVBoxLayout) -> None:
        """构建模型区：ModelSection 实例并接线"""
        self._model_section = ModelSection(self)
        section = self._model_section
        section.sig_add_requested.connect(self.sig_add_model_requested)
        section.sig_edit_requested.connect(self.sig_edit_model_requested)
        section.sig_refresh_requested.connect(self._on_refresh_models)
        section.sig_model_toggled.connect(self._on_model_toggled)
        section.sig_delete_confirmed.connect(self._on_models_delete_confirmed)
        section.sig_health_check_requested.connect(self._on_health_check)
        section.sig_sync_requested.connect(self._on_sync_models)
        parent_layout.addWidget(section)

    # ------------------------------------------------------------------
    # 默认模型区
    # ------------------------------------------------------------------

    def _build_default_model_section(self, parent_layout: QVBoxLayout) -> None:
        """构建默认模型区：对话/Embedding 模型下拉 + 启用 Embedding 开关"""
        parent_layout.addWidget(make_section_label("默认模型"))
        parent_layout.addSpacing(SECTION_CONTENT_GAP)
        self._chat_combo = self._make_model_combo(self._on_chat_model_chosen)
        parent_layout.addLayout(
            self._make_combo_row("对话模型", self._chat_combo))
        parent_layout.addSpacing(DEFAULT_MODEL_ROW_GAP)
        self._embedding_combo = self._make_model_combo(
            self._on_embedding_model_chosen)
        parent_layout.addLayout(
            self._make_combo_row("Embedding 模型", self._embedding_combo))
        parent_layout.addSpacing(DEFAULT_MODEL_ROW_GAP)
        embedding_row = QHBoxLayout()
        embedding_row.addWidget(make_field_label("启用 Embedding"))
        embedding_row.addStretch(1)
        self._embedding_switch = SwitchButton()
        self._embedding_switch.setToolTip("启用 / 停用该提供商的嵌入功能")
        self._embedding_switch.toggled.connect(self._on_embedding_toggled)
        embedding_row.addWidget(self._embedding_switch)
        parent_layout.addLayout(embedding_row)

    def _make_model_combo(self, handler: Callable[[int], None]) -> QComboBox:
        """构建默认模型下拉框（activated 仅由用户操作触发）

        Args:
            handler: 用户选择后的处理槽（携带选项索引）

        Returns:
            QComboBox: 下拉框控件
        """
        combo = QComboBox(self)
        combo.activated.connect(handler)
        return combo

    def _make_combo_row(self, label_text: str, combo: QComboBox) -> QHBoxLayout:
        """构建「标签 + 下拉框」行"""
        row = QHBoxLayout()
        row.setSpacing(FIELD_GAP)
        label = make_field_label(label_text)
        label.setFixedWidth(DEFAULT_MODEL_LABEL_WIDTH)
        row.addWidget(label)
        row.addWidget(combo, 1)
        return row

    # ==================== 实例加载 ====================

    def load_instance(self, instance_id: Optional[str]) -> None:
        """加载指定实例到面板（None 或不存在时清空为空态容错）

        切换实例前会安全终止进行中的后台 Worker。

        Args:
            instance_id: 实例 id；None 表示空态
        """
        self.shutdown_workers()
        self._instance_id = instance_id
        cfg = get_llm_config().get_provider(instance_id) if instance_id else None
        self._preset = (
            get_provider_preset(cfg.preset_id)
            if cfg is not None and cfg.preset_id else None)
        self._populate_header(cfg)
        self._populate_api(cfg)
        self._model_section.reset_manage_mode()
        self._model_section.set_refresh_status("")
        self.rebuild_models()

    def _populate_header(self, cfg: Optional[ProviderConfig]) -> None:
        """按实例配置填充头部（图标/名称/徽章/总开关/遮罩）"""
        self._update_header_icon(cfg)
        self._rebuild_type_badge(cfg)
        self._name_label.setText(cfg.name if cfg else "")
        enabled = bool(cfg and cfg.enabled_chat)
        self._master_switch.setEnabled(cfg is not None)
        self._master_switch.set_checked_no_anim(enabled)
        self._apply_enabled_state(cfg is not None and enabled)

    def _update_header_icon(self, cfg: Optional[ProviderConfig]) -> None:
        """重渲头部品牌图标（fg_primary 着色，空态清空）"""
        if cfg is None:
            self._icon_label.setPixmap(provider_icon_pixmap(
                None, "", HEADER_ICON_PX,
                QColor(_theme_module.current_theme().fg_primary)))
            return
        self._icon_label.setPixmap(provider_icon_pixmap(
            cfg.preset_id, cfg.name, HEADER_ICON_PX,
            QColor(_theme_module.current_theme().fg_primary)))

    def _rebuild_type_badge(self, cfg: Optional[ProviderConfig]) -> None:
        """重渲类型徽章（预设显示名或「自定义」，色按 adapter 回退 accent）"""
        t = _theme_module.current_theme()
        if cfg is None:
            self._type_badge.setVisible(False)
            return
        self._type_badge.setVisible(True)
        text = self._preset.display_name if self._preset else CUSTOM_PROVIDER_TYPE_LABEL
        color = t.provider_type_colors.get(cfg.adapter, t.accent)
        self._type_badge.setText(text)
        self._type_badge.setStyleSheet(_badge_style(color))

    def _populate_api(self, cfg: Optional[ProviderConfig]) -> None:
        """按实例配置填充 API 配置区（密钥/地址/链接/状态）"""
        auth_optional = bool(self._preset and self._preset.auth_optional)
        self._key_edit.blockSignals(True)
        self._key_edit.setText(cfg.api_key if cfg else "")
        self._key_edit.blockSignals(False)
        self._key_edit.setPlaceholderText(
            "sk-...（可选）" if auth_optional else "sk-...")
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._eye_btn.blockSignals(True)
        self._eye_btn.setChecked(False)
        self._eye_btn.blockSignals(False)
        self._eye_btn.setIcon(make_eye_icon(False))
        key_url = self._preset.api_key_url if self._preset else ""
        self._key_link_btn.setVisible(bool(key_url))
        default_url = self._preset.default_base_url if self._preset else ""
        self._host_edit.blockSignals(True)
        self._host_edit.setText(cfg.base_url if cfg else "")
        self._host_edit.blockSignals(False)
        self._host_edit.setPlaceholderText(default_url or "https://...")
        self._reset_btn.setVisible(bool(default_url))
        self._reset_check_ui()

    def _apply_enabled_state(self, enabled: bool) -> None:
        """按总开关状态切换主体可用性与停用遮罩

        Args:
            enabled: 是否启用
        """
        self._body.setEnabled(enabled)
        self._overlay.setVisible(not enabled)
        if not enabled:
            self._overlay.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._overlay.setGeometry(self._body.geometry())

    # ==================== 配置落盘 ====================

    def _persist(self, apply: Callable[[ProviderConfig], None]) -> bool:
        """对当前实例应用修改并落盘

        Args:
            apply: 修改函数，接收 ProviderConfig 并就地修改

        Returns:
            bool: 是否落盘成功（无当前实例或实例已删除时失败）
        """
        if not self._instance_id:
            return False
        config = get_llm_config()
        cfg = config.get_provider(self._instance_id)
        if cfg is None:
            return False
        apply(cfg)
        config.add_provider(self._instance_id, cfg)
        return True

    def _persist_and_notify(self, apply: Callable[[ProviderConfig], None]) -> None:
        """落盘并外发 sig_config_changed（供主壳协调刷新）"""
        if self._persist(apply):
            self.sig_config_changed.emit()

    # ==================== 头部交互 ====================

    def _on_master_toggled(self, on: bool) -> None:
        """总开关：写 enabled_chat 落盘并切换遮罩"""
        self._persist_and_notify(lambda cfg: setattr(cfg, "enabled_chat", on))
        self._apply_enabled_state(on)

    def _on_rename(self) -> None:
        """更多菜单-重命名：中文输入弹窗，非空且变化时落盘"""
        cfg = self._current_config()
        if cfg is None:
            return
        name, ok = QInputDialog.getText(
            self, "重命名提供商", "名称：", QLineEdit.EchoMode.Normal, cfg.name)
        name = name.strip()
        if not ok or not name or name == cfg.name:
            return
        self._persist_and_notify(lambda c: setattr(c, "name", name))
        self._name_label.setText(name)

    def _on_delete_provider(self) -> None:
        """更多菜单-删除提供商：中文确认后删除配置"""
        cfg = self._current_config()
        if cfg is None or not self._instance_id:
            return
        if not _confirm_dialog(
                self, "删除提供商",
                f"确定删除「{cfg.name}」及其全部模型配置吗？"):
            return
        self.shutdown_workers()
        # remove_provider 会同步触发配置变更通知，列表重载后可能立即
        # load_instance 其他实例；须先摘下当前实例 id，避免覆盖新加载的实例
        deleted_id = self._instance_id
        self._instance_id = None
        get_llm_config().remove_provider(deleted_id)
        self.sig_provider_deleted.emit()

    def _current_config(self) -> Optional[ProviderConfig]:
        """获取当前实例配置（无实例或已删除返回 None）"""
        if not self._instance_id:
            return None
        return get_llm_config().get_provider(self._instance_id)

    # ==================== API 配置区交互 ====================

    def _on_key_changed(self, _text: str) -> None:
        """密钥输入变化：重置检测状态（落盘在 editingFinished 进行）"""
        self._reset_check_ui()

    def _on_key_edited(self) -> None:
        """密钥编辑完成：落盘 api_key"""
        text = self._key_edit.text()
        self._persist(lambda cfg: setattr(cfg, "api_key", text))

    def _on_eye_toggled(self, visible: bool) -> None:
        """眼睛按钮：切换密钥明文/密文显示"""
        self._key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible
            else QLineEdit.EchoMode.Password)
        self._eye_btn.setIcon(make_eye_icon(visible))

    def _on_open_key_url(self) -> None:
        """「获取密钥」链接：打开预设的密钥获取页"""
        if self._preset and self._preset.api_key_url:
            QDesktopServices.openUrl(QUrl(self._preset.api_key_url))

    def _on_host_edited(self) -> None:
        """地址编辑完成：落盘 base_url（去首尾空白）"""
        text = self._host_edit.text().strip()
        self._persist(lambda cfg: setattr(cfg, "base_url", text))

    def _on_host_reset(self) -> None:
        """「重置」：清空 base_url 落盘（运行时回退目录默认），输入框显示默认地址"""
        default_url = self._preset.default_base_url if self._preset else ""
        self._host_edit.setText(default_url)
        self._persist(lambda cfg: setattr(cfg, "base_url", ""))

    # ------------------------------------------------------------------
    # 连接检测
    # ------------------------------------------------------------------

    def _reset_check_ui(self) -> None:
        """重置检测按钮与状态文案"""
        self._check_btn.setEnabled(True)
        self._check_btn.setText("检测")
        self._status_kind = None
        self._check_status.setText("")

    def _apply_status_color(self, kind: str) -> None:
        """按状态种类给状态文案着色"""
        t = _theme_module.current_theme()
        color = {_STATUS_OK: t.success, _STATUS_ERR: t.danger,
                 _STATUS_MUTED: t.fg_muted}[kind]
        self._check_status.setStyleSheet(f"color: {color};")

    def _set_check_status(self, text: str, kind: str) -> None:
        """更新状态文案与种类

        Args:
            text: 状态文本
            kind: 状态种类（ok / err / muted）
        """
        self._status_kind = kind
        self._apply_status_color(kind)
        self._check_status.setText(text)

    def _on_check_key(self) -> None:
        """「检测」：先落盘当前输入，再启动连接检测 Worker"""
        if not self._instance_id:
            return
        key = self._key_edit.text()
        host = self._host_edit.text().strip()

        def apply(cfg: ProviderConfig) -> None:
            cfg.api_key = key
            cfg.base_url = host

        if not self._persist(apply):
            return
        self._check_btn.setEnabled(False)
        self._check_btn.setText("检测中…")
        self._set_check_status("正在检测连接…", _STATUS_MUTED)
        worker = ConnectionCheckWorker(self._instance_id, parent=self)
        worker.checked.connect(self._on_check_finished)
        self._check_worker = worker
        worker.start()

    def _on_check_finished(
        self, instance_id: str, ok: bool, error: Optional[str], count: int,
    ) -> None:
        """检测完成：更新状态；成功且当前停用时自动开启总开关

        Args:
            instance_id: 实例 id（与当前实例不符时忽略迟到信号）
            ok: 是否成功
            error: 错误信息（成功为 None）
            count: 可用模型数
        """
        if instance_id != self._instance_id:
            return
        self._check_worker = None
        self._check_btn.setEnabled(True)
        self._check_btn.setText("检测")
        if not ok:
            self._set_check_status(f"✗ 连接失败：{error or '未知错误'}", _STATUS_ERR)
            return
        self._set_check_status(f"✓ 连接正常 · {count} 个模型", _STATUS_OK)
        cfg = self._current_config()
        if cfg is not None and not cfg.enabled_chat:
            self._persist_and_notify(
                lambda c: setattr(c, "enabled_chat", True))
            self._master_switch.set_checked_no_anim(True)
            self._apply_enabled_state(True)

    # ------------------------------------------------------------------
    # 「↻ 刷新」获取模型列表
    # ------------------------------------------------------------------

    def _on_refresh_models(self) -> None:
        """「↻ 刷新」：启动 FetchModelsWorker 从 API 获取最新模型列表"""
        if not self._instance_id or self._fetch_worker is not None:
            return
        self._model_section.set_refresh_busy(True)
        self._model_section.set_refresh_status("正在获取模型列表…")
        worker = FetchModelsWorker(self._instance_id, parent=self)
        worker.succeeded.connect(self._on_fetch_succeeded)
        worker.failed.connect(self._on_fetch_failed)
        self._fetch_worker = worker
        worker.start()

    def _on_fetch_succeeded(self, instance_id: str, models: list) -> None:
        """获取成功：状态文案提示数量并重渲染模型区

        Args:
            instance_id: 实例 id（与当前实例不符时忽略迟到信号）
            models: ModelInfo 列表
        """
        if instance_id != self._instance_id:
            return
        self._fetch_worker = None
        self._model_section.set_refresh_busy(False)
        self._model_section.set_refresh_status(f"✓ 已更新 · {len(models)} 个模型")
        self.rebuild_models()

    def _on_fetch_failed(self, instance_id: str, error: str) -> None:
        """获取失败：恢复按钮并弹出中文错误

        Args:
            instance_id: 实例 id（与当前实例不符时忽略迟到信号）
            error: 错误信息
        """
        if instance_id != self._instance_id:
            return
        self._fetch_worker = None
        self._model_section.set_refresh_busy(False)
        self._model_section.set_refresh_status("")
        _logger.warning(
            get_name(), f"获取模型列表失败: {instance_id} ({error})")
        _notice_dialog(
            self, "获取模型列表失败",
            f"无法从 API 获取最新模型列表：\n{error or '未知错误'}")

    # ------------------------------------------------------------------
    # 「⚡ 检查」/ 「⇅ 同步」对话框
    # ------------------------------------------------------------------

    def _on_health_check(self) -> None:
        """「⚡ 检查」：以当前合并列表打开模型健康检查对话框"""
        if not self._instance_id:
            return
        if not self._entries:
            _info_toast(self, "暂无可检查的模型，请先添加模型或刷新模型列表。")
            return
        cfg = self._current_config()
        name = cfg.name if cfg else self._instance_id
        dialog = HealthCheckDialog(
            self._instance_id, name, self._entries, parent=self)
        dialog.exec()

    def _on_sync_models(self) -> None:
        """「⇅ 同步」：打开模型同步对话框；发生落盘变更时重载当前实例"""
        if not self._instance_id:
            return
        dialog = SyncModelsDialog(
            self._instance_id, self._entries, parent=self)
        dialog.exec()
        if dialog.changed:
            self.load_instance(self._instance_id)

    def shutdown_workers(self) -> None:
        """安全终止进行中的后台 Worker（面板卸载 / 切换实例时调用，幂等）"""
        for attr in ("_check_worker", "_fetch_worker"):
            worker = getattr(self, attr)
            setattr(self, attr, None)
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(WORKER_STOP_WAIT_MS)
        self._model_section.set_refresh_busy(False)

    # ==================== 模型区（数据装配与覆写落盘） ====================

    def rebuild_models(self) -> None:
        """按三路合并结果重建模型分组列表，并同步默认模型下拉选项"""
        self._entries = self._merged_entries()
        self._model_section.rebuild(self._entries)
        self._refresh_default_model_combos()

    def _merged_entries(self) -> List[Dict[str, Any]]:
        """三路合并模型条目并过滤 hidden 覆写（空态返回空列表）"""
        cfg = self._current_config()
        if cfg is None:
            return []
        preset_models = PRESET_MODELS.get(cfg.preset_id or "", [])
        fetched = self._fetched_entries()
        custom = cfg.extra.get("custom_models", [])
        merged = merge_model_entries(preset_models, fetched, custom)
        return [entry for entry in merged if not entry.get("hidden")]

    def _fetched_entries(self) -> List[Dict[str, Any]]:
        """读取缓存模型并转为统一 schema dict（读取失败降级为空列表）"""
        if not self._instance_id:
            return []
        try:
            models = get_llm_provider().get_cached_models(self._instance_id)
        except Exception as e:
            _logger.warning(
                get_name(), f"读取模型缓存失败: {self._instance_id} ({e})")
            return []
        return [model.to_dict() for model in models]

    # ------------------------------------------------------------------
    # 模型覆写落盘
    # ------------------------------------------------------------------

    def _base_model_ids(self) -> Set[str]:
        """目录预设 + 缓存拉取的模型 id 集合（用于区分自定义新增条目）"""
        cfg = self._current_config()
        ids: Set[str] = set()
        if cfg is not None:
            ids.update(e.get("id") for e in PRESET_MODELS.get(cfg.preset_id or "", []))
        if self._instance_id:
            try:
                models = get_llm_provider().get_cached_models(self._instance_id)
                ids.update(m.id for m in models)
            except Exception as e:
                _logger.warning(
                    get_name(), f"读取模型缓存失败: {self._instance_id} ({e})")
        ids.discard(None)
        return ids

    @staticmethod
    def _apply_model_enabled(
        cfg: ProviderConfig, model_id: str, enabled: bool,
    ) -> None:
        """写模型 enabled 覆写：更新 custom_models 同 id 条目，不存在则创建"""
        customs = cfg.extra.setdefault("custom_models", [])
        for entry in customs:
            if isinstance(entry, dict) and entry.get("id") == model_id:
                entry["enabled"] = enabled
                return
        customs.append({"id": model_id, "enabled": enabled})

    def _apply_model_removal(self, cfg: ProviderConfig, model_id: str) -> None:
        """写模型删除语义：自定义条目移除；预设/拉取条目写 hidden 覆写

        判定基准：模型 id 命中目录预设或缓存拉取集合即为非自定义
        （此时 custom_models 中同 id 条目属覆写而非用户新增，删除应
        转为 hidden 覆写，避免移除覆写后条目重新出现）。
        """
        customs = cfg.extra.setdefault("custom_models", [])
        if model_id in self._base_model_ids():
            for entry in customs:
                if isinstance(entry, dict) and entry.get("id") == model_id:
                    entry["hidden"] = True
                    return
            customs.append({"id": model_id, "hidden": True})
            return
        cfg.extra["custom_models"] = [
            entry for entry in customs
            if not (isinstance(entry, dict) and entry.get("id") == model_id)
        ]

    def _on_model_toggled(self, model_id: str, on: bool) -> None:
        """模型行开关：写 enabled 覆写落盘并刷新默认模型下拉（选项随启用态变化）"""
        if not self._persist(
                lambda cfg: self._apply_model_enabled(cfg, model_id, on)):
            return
        # 同步内存中的合并条目，避免重建行列表（保持管理工具条勾选态）
        for entry in self._entries:
            if entry.get("id") == model_id:
                entry["enabled"] = on
        self._refresh_default_model_combos()

    def _on_models_delete_confirmed(self, model_ids: List[str]) -> None:
        """删除确认完成：按语义批量落盘并重建列表

        Args:
            model_ids: 待删除的模型 id 列表（单条或管理模式的批量）
        """
        if not model_ids:
            return

        def apply(cfg: ProviderConfig) -> None:
            for model_id in model_ids:
                self._apply_model_removal(cfg, model_id)

        self._persist_and_notify(apply)
        self.rebuild_models()

    # ==================== 默认模型区 ====================

    def _default_model_options(self, kind: str) -> List[str]:
        """计算默认模型下拉选项（未 hidden 且未禁用的模型 id）

        Args:
            kind: "chat"（排除 embedding/rerank 能力模型）或
                "embedding"（仅 embedding 能力模型）

        Returns:
            List[str]: 模型 id 选项列表
        """
        options: List[str] = []
        for entry in self._entries:
            if not entry.get("enabled", True):
                continue
            capabilities = entry.get("capabilities") or []
            if kind == _MODEL_KIND_CHAT and (
                    CAPABILITY_EMBEDDING in capabilities
                    or CAPABILITY_RERANK in capabilities):
                continue
            if kind == _MODEL_KIND_EMBEDDING and (
                    CAPABILITY_EMBEDDING not in capabilities):
                continue
            model_id = str(entry.get("id", ""))
            if model_id:
                options.append(model_id)
        return options

    def _refresh_default_model_combos(self) -> None:
        """按当前模型集重建两个下拉选项并回显已保存的默认模型"""
        cfg = self._current_config()
        self._fill_combo(
            self._chat_combo, self._default_model_options(_MODEL_KIND_CHAT),
            cfg.chat_model if cfg else "")
        self._fill_combo(
            self._embedding_combo,
            self._default_model_options(_MODEL_KIND_EMBEDDING),
            cfg.embedding_model if cfg else "")
        self._embedding_switch.set_checked_no_anim(
            bool(cfg and cfg.enabled_embedding))

    def _fill_combo(
        self, combo: QComboBox, options: List[str], current: str,
    ) -> None:
        """填充下拉选项（首项「未设置」；已保存值不在选项中时补入以免误清空）

        Args:
            combo: 目标下拉框
            options: 模型 id 选项
            current: 当前已保存的默认模型 id（空串表示未设置）
        """
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("（未设置）", _NO_MODEL_DATA)
        items = list(options)
        if current and current not in items:
            items.append(current)
        for model_id in items:
            combo.addItem(model_id, model_id)
        index = combo.findData(current) if current else 0
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _on_chat_model_chosen(self, index: int) -> None:
        """对话模型下拉选择：落盘 chat_model"""
        model_id = self._chat_combo.itemData(index) or ""
        self._persist(lambda cfg: setattr(cfg, "chat_model", model_id))

    def _on_embedding_model_chosen(self, index: int) -> None:
        """Embedding 模型下拉选择：落盘 embedding_model"""
        model_id = self._embedding_combo.itemData(index) or ""
        self._persist(lambda cfg: setattr(cfg, "embedding_model", model_id))

    def _on_embedding_toggled(self, on: bool) -> None:
        """启用 Embedding 开关：落盘 enabled_embedding"""
        self._persist(lambda cfg: setattr(cfg, "enabled_embedding", on))

    # ==================== 主题 ====================

    def apply_theme(self, theme: Theme) -> None:
        """主题切换：重渲头部图标 / 徽章 / 眼睛图标 / 状态色 / 模型区

        Args:
            theme: 新主题 token
        """
        cfg = self._current_config()
        self._update_header_icon(cfg)
        self._rebuild_type_badge(cfg)
        self._eye_btn.setIcon(make_eye_icon(self._eye_btn.isChecked()))
        if self._status_kind is not None:
            self._apply_status_color(self._status_kind)
        self._master_switch.update()
        self._embedding_switch.update()
        self._model_section.apply_theme(theme)
