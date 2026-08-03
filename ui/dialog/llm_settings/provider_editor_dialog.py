# ui/dialog/llm_settings/provider_editor_dialog.py
"""Provider 实例添加/编辑对话框

提供两种工作模式：

- ``MODE_CREATE``：两页流程——「选择类型」页（预设列表 + 末尾
  「自定义 OpenAI 兼容服务」项）→「填写信息」页（名称 / Base URL /
  API Key，按预设预填）；
- ``MODE_EDIT``：编辑既有实例的名称 / Base URL / API Key（不更换预设，
  API Key 留空表示不修改）。

本对话框只做交互编排与表单校验提示；实例 id 生成规则收敛在模块级
``generate_instance_id()``，配置读写一律经 ``get_llm_config()``。
确认成功后配置即时落盘，以 ``created_instance_id`` 属性暴露实例 id。

视觉全部走主题 token（QDialog / QLineEdit / QPushButton 由主题 QSS
覆盖，表单标签用 make_field_label），构造时经 ``apply_dialog_theme``
完成换肤并安装焦点光环。
"""

import uuid
from typing import Dict, Optional, Set, Tuple
from urllib.parse import urlparse

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from core.llm.catalog import (
    CUSTOM_ADAPTER, PROVIDER_PRESETS, ProviderPreset, get_provider_preset,
)
from core.llm.config import ProviderConfig, get_llm_config

from . import theme as _theme_module
from .constants import (
    CUSTOM_INSTANCE_ID_PREFIX, EDITOR_DIALOG_CREATE_HEIGHT,
    EDITOR_DIALOG_WIDTH, FORM_BUTTON_HEIGHT, FORM_DIALOG_SPACING,
    FORM_FIELD_GAP, FORM_INPUT_HEIGHT, INSTANCE_ID_SUFFIX_LENGTH,
    PRESET_ICON_SIZE, PRESET_ITEM_HEIGHT,
)
from .icons import provider_icon_pixmap
from .theme import apply_dialog_theme
from .feedback import warn as _warn_toast
from .widgets import _BaseFormDialog, install_focus_halo, make_field_label

# 对话框工作模式
MODE_CREATE = "create"  # 添加入口：先选类型，再填信息
MODE_EDIT = "edit"      # 编辑既有实例

# 预设类型列表项的 preset_id 数据角色（None 表示「自定义 OpenAI 兼容服务」项）
_ROLE_PRESET_ID = Qt.ItemDataRole.UserRole

# 自定义类型项的展示文案
_CUSTOM_CHOICE_TITLE = "自定义 OpenAI 兼容服务"
_CUSTOM_CHOICE_SUBTITLE = "接入任意 OpenAI 兼容协议的模型服务"

# 自定义实例的默认名称
_CUSTOM_DEFAULT_NAME = "自定义服务"


def generate_instance_id(
    preset_id: Optional[str],
    existing_ids: Set[str],
) -> str:
    """生成不冲突的实例 id

    规则：预设实例在该预设尚无实例时直接使用 ``preset_id``
    （保证旧配置向后兼容）；否则生成
    ``f"{preset_id 或 custom}-{uuid4().hex[:8]}"`` 短码 id，冲突时重试。

    Args:
        preset_id: 关联预设 id（自定义实例为 None）
        existing_ids: 已存在的实例 id 集合

    Returns:
        str: 唯一的实例 id
    """
    if preset_id and preset_id not in existing_ids:
        return preset_id
    prefix = preset_id or CUSTOM_INSTANCE_ID_PREFIX
    while True:
        candidate = f"{prefix}-{uuid.uuid4().hex[:INSTANCE_ID_SUFFIX_LENGTH]}"
        if candidate not in existing_ids:
            return candidate


def _next_order(providers: Dict[str, ProviderConfig]) -> int:
    """计算新实例的排序权重（现有最大 order + 1，空列表为 0）

    Args:
        providers: 现有实例 id → 配置映射

    Returns:
        int: 新实例应使用的 order 值
    """
    if not providers:
        return 0
    return max(cfg.order for cfg in providers.values()) + 1


def _base_url_subtitle(url: str) -> str:
    """从 Base URL 提取简介副标题（优先域名）

    Args:
        url: 预设默认 Base URL

    Returns:
        str: 域名；无法解析时回退原始串，空串回退「自定义接入」
    """
    if not url:
        return "自定义接入"
    host = urlparse(url).netloc
    return host or url


class ProviderEditorDialog(_BaseFormDialog):
    """Provider 实例添加/编辑对话框

    ``MODE_CREATE`` 下内含两页（选择类型 / 填写信息）的 QStackedWidget；
    ``MODE_EDIT`` 直接展示「填写信息」页。确认成功后配置即时落盘，
    ``created_instance_id`` 记录实例 id。

    Attributes:
        created_instance_id: 确认成功后新建/编辑的实例 id（未确认为 None）
    """

    def __init__(
        self,
        mode: str = MODE_CREATE,
        instance_id: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        """构造对话框

        Args:
            mode: 工作模式（MODE_CREATE / MODE_EDIT）
            instance_id: MODE_EDIT 模式下被编辑的实例 id
            parent: 父控件
        """
        title = "编辑提供商" if mode == MODE_EDIT else "添加提供商"
        super().__init__(title, parent)
        self._mode = mode
        self._instance_id = instance_id
        self._preset: Optional[ProviderPreset] = None
        self._custom = False
        self.created_instance_id: Optional[str] = None
        self.setMinimumWidth(EDITOR_DIALOG_WIDTH)
        if mode == MODE_CREATE:
            # 两页流程默认高度：完整展示全部类型项，避免列表滚动截断
            self.resize(EDITOR_DIALOG_WIDTH, EDITOR_DIALOG_CREATE_HEIGHT)
        # 先换肤（更新 CURRENT_THEME）再构建内容，保证类型页品牌图标
        # 与表单控件按当前主题着色
        apply_dialog_theme(self)
        self._init_ui()
        install_focus_halo(self)

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建整体布局：按模式决定是否包含「选择类型」页"""
        self._form_page = self._build_form_page()
        if self._mode == MODE_EDIT:
            self._layout.addWidget(self._form_page)
            self._prefill_edit_form()
            return
        self._stack = QStackedWidget(self)
        self._type_page = self._build_type_page()
        self._stack.addWidget(self._type_page)
        self._stack.addWidget(self._form_page)
        self._layout.addWidget(self._stack)

    # ------------------------------------------------------------------
    # 「选择类型」页
    # ------------------------------------------------------------------

    def _build_type_page(self) -> QWidget:
        """构建「选择类型」页：预设列表 + 末尾自定义选项 + 取消按钮"""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(FORM_FIELD_GAP)
        layout.addWidget(make_field_label("选择模型服务类型"))
        self._type_list = QListWidget(page)
        self._type_list.setIconSize(QSize(PRESET_ICON_SIZE, PRESET_ICON_SIZE))
        color = QColor(_theme_module.current_theme().fg_secondary)
        for preset in PROVIDER_PRESETS.values():
            self._type_list.addItem(self._make_type_item(
                preset.preset_id, preset.display_name,
                _base_url_subtitle(preset.default_base_url), color))
        self._type_list.addItem(self._make_type_item(
            None, _CUSTOM_CHOICE_TITLE, _CUSTOM_CHOICE_SUBTITLE, color))
        self._type_list.itemClicked.connect(self._on_type_chosen)
        layout.addWidget(self._type_list, 1)
        cancel_row = QHBoxLayout()
        cancel_row.addStretch(1)
        cancel_btn = QPushButton("取消", page)
        cancel_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)
        return page

    def _make_type_item(
        self, preset_id: Optional[str], title: str, subtitle: str,
        color: QColor,
    ) -> QListWidgetItem:
        """构建单个类型列表项（品牌图标 + 名称 + 副标题）

        Args:
            preset_id: 预设 id（None 表示自定义项，走字母方块图标）
            title: 主标题（预设显示名）
            subtitle: 副标题（默认地址域名）
            color: 图标着色

        Returns:
            QListWidgetItem: 列表项（preset_id 存入 UserRole）
        """
        item = QListWidgetItem(f"{title}\n{subtitle}")
        item.setData(_ROLE_PRESET_ID, preset_id)
        item.setIcon(QIcon(provider_icon_pixmap(
            preset_id, title, PRESET_ICON_SIZE, color)))
        item.setSizeHint(QSize(-1, PRESET_ITEM_HEIGHT))
        return item

    def _on_type_chosen(self, item: QListWidgetItem) -> None:
        """「选择类型」页点选：记录类型并进入「填写信息」页"""
        preset_id = item.data(_ROLE_PRESET_ID)
        self._custom = preset_id is None
        self._preset = None if self._custom else get_provider_preset(preset_id)
        self._apply_form_prefill()
        self._stack.setCurrentWidget(self._form_page)

    # ------------------------------------------------------------------
    # 「填写信息」页
    # ------------------------------------------------------------------

    def _build_form_page(self) -> QWidget:
        """构建「填写信息」页：名称 / Base URL / API Key + 按钮栏"""
        page = QWidget(self)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(FORM_DIALOG_SPACING)
        self._form_hint = make_field_label("")
        layout.addWidget(self._form_hint)
        self.name_edit = self._build_form_field(layout, "名称", "")
        self.base_url_edit = self._build_form_field(
            layout, "Base URL", "https://...")
        self._key_label, self.api_key_edit = self._build_key_field(layout)
        layout.addStretch(1)
        layout.addLayout(self._build_form_buttons())
        return page

    def _build_form_field(
        self, layout: QVBoxLayout, label_text: str, placeholder: str,
    ) -> QLineEdit:
        """向表单页追加「标签 + 单行输入框」字段

        Args:
            layout: 表单页布局
            label_text: 字段标签文案
            placeholder: 占位提示

        Returns:
            QLineEdit: 输入框控件
        """
        layout.addWidget(make_field_label(label_text))
        edit = QLineEdit(self)
        edit.setFixedHeight(FORM_INPUT_HEIGHT)
        edit.setPlaceholderText(placeholder)
        layout.addWidget(edit)
        layout.addSpacing(FORM_FIELD_GAP)
        return edit

    def _build_key_field(
        self, layout: QVBoxLayout,
    ) -> Tuple[QLabel, QLineEdit]:
        """构建 API Key 字段（密文输入；返回标签供按预设标注「可选」）

        Args:
            layout: 表单页布局

        Returns:
            Tuple[QLabel, QLineEdit]: 标签与输入框控件
        """
        label = make_field_label("API Key")
        layout.addWidget(label)
        edit = QLineEdit(self)
        edit.setFixedHeight(FORM_INPUT_HEIGHT)
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setPlaceholderText("sk-...")
        layout.addWidget(edit)
        layout.addSpacing(FORM_FIELD_GAP)
        return label, edit

    def _build_form_buttons(self) -> QHBoxLayout:
        """构建底部按钮栏（[返回] + 取消 + 确定；返回仅 MODE_CREATE）"""
        row = QHBoxLayout()
        if self._mode == MODE_CREATE:
            back_btn = QPushButton("返回", self)
            back_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
            back_btn.clicked.connect(
                lambda: self._stack.setCurrentWidget(self._type_page))
            row.addWidget(back_btn)
        row.addStretch(1)
        cancel_btn = QPushButton("取消", self)
        cancel_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        cancel_btn.clicked.connect(self.reject)
        ok_btn = QPushButton("确定", self)
        ok_btn.setFixedHeight(FORM_BUTTON_HEIGHT)
        ok_btn.setProperty("accent", True)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_confirm)
        row.addWidget(cancel_btn)
        row.addWidget(ok_btn)
        return row

    # ==================== 预填 ====================

    def _apply_form_prefill(self) -> None:
        """按所选类型预填表单（名称 / Base URL / API Key 标签）"""
        auth_optional = bool(self._preset and self._preset.auth_optional)
        self._key_label.setText("API Key（可选）" if auth_optional else "API Key")
        if self._preset is not None:
            self._form_hint.setText(f"创建 {self._preset.display_name} 实例")
            self.name_edit.setText(self._preset.display_name)
            self.base_url_edit.setText(self._preset.default_base_url)
            return
        self._form_hint.setText(f"创建{_CUSTOM_CHOICE_TITLE}实例")
        self.name_edit.setText(_CUSTOM_DEFAULT_NAME)
        self.base_url_edit.setText("")

    def _prefill_edit_form(self) -> None:
        """edit 模式：从既有配置回填表单（API Key 不回显，留空不修改）"""
        cfg = get_llm_config().get_provider(self._instance_id or "")
        if cfg is None:
            self._form_hint.setText("实例不存在")
            return
        self._preset = (
            get_provider_preset(cfg.preset_id) if cfg.preset_id else None)
        auth_optional = bool(self._preset and self._preset.auth_optional)
        self._key_label.setText("API Key（可选）" if auth_optional else "API Key")
        self._form_hint.setText(f"编辑实例（适配器：{cfg.adapter}）")
        self.name_edit.setText(cfg.name)
        self.base_url_edit.setText(cfg.base_url)
        self.api_key_edit.setPlaceholderText("留空则不修改")

    # ==================== 确认与落盘 ====================

    def _on_confirm(self) -> None:
        """确定按钮：校验表单并按模式落盘"""
        name = self.name_edit.text().strip()
        base_url = self.base_url_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        if not name:
            self._warn("校验失败", "请输入实例名称。")
            return
        if self._mode == MODE_CREATE and self._custom and not base_url:
            self._warn("校验失败", "自定义 OpenAI 兼容服务必须填写 Base URL。")
            return
        if self._mode == MODE_EDIT:
            if not self._save_edit(name, base_url, api_key):
                return
        else:
            self._save_create(name, base_url, api_key)
        self.accept()

    def _save_create(self, name: str, base_url: str, api_key: str) -> None:
        """创建新实例并落盘，记录 created_instance_id"""
        config = get_llm_config()
        providers = config.get_all_providers()
        preset = None if self._custom else self._preset
        instance_id = generate_instance_id(
            preset.preset_id if preset else None, set(providers.keys()))
        cfg = ProviderConfig(
            name=name,
            preset_id=preset.preset_id if preset else None,
            adapter=preset.adapter if preset else CUSTOM_ADAPTER,
            base_url=base_url,
            api_key=api_key,
            order=_next_order(providers),
        )
        config.add_provider(instance_id, cfg)
        self.created_instance_id = instance_id

    def _save_edit(self, name: str, base_url: str, api_key: str) -> bool:
        """更新既有实例的名称 / Base URL / API Key（Key 留空不修改）

        Returns:
            bool: 是否保存成功（实例不存在时失败并提示）
        """
        config = get_llm_config()
        cfg = config.get_provider(self._instance_id or "")
        if cfg is None:
            self._warn("保存失败", "要编辑的实例不存在，可能已被删除。")
            return False
        cfg.name = name
        cfg.base_url = base_url
        if api_key:
            cfg.api_key = api_key
        config.add_provider(self._instance_id, cfg)
        self.created_instance_id = self._instance_id
        return True

    def _warn(self, title: str, message: str) -> None:
        """弹出中文警告轻提示（UIKit Message，标题并入文案）"""
        _warn_toast(self, f"{title}：{message}")
