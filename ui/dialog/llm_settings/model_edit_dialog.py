# ui/dialog/llm_settings/model_edit_dialog.py
"""模型编辑对话框

编辑单个模型条目（统一模型 schema dict，见 core/llm/model_schema.py）：

- 以 ``model_data=None`` 构造为**新建模式**（模型 ID 可编辑）；
- 传入既有条目为**编辑模式**（模型 ID 只读展示，其余字段回填）；
- 能力标签为徽章风格 checkable QToolButton 开关组，遵循互斥规则
  （选中 embedding/rerank 时禁用其余能力，见 ``get_disabled_capabilities``）；
- ``get_model_data()`` 输出经 ``normalize_model_entry`` 兜底规范化的
  统一 schema 字典（group 留空时经 ``infer_model_group`` 自动推断；
  context_length / 定价为 0 时输出 None 表示未设置）。

条目的落盘（写入实例 ``custom_models``）由调用方（主壳）在对话框被
接受后完成。视觉全部走主题 token，构造时经 ``apply_dialog_theme``
完成换肤并安装焦点光环。
"""

from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QSpinBox, QToolButton, QVBoxLayout, QWidget,
)

from core.llm.model_schema import (
    ALL_CAPABILITIES, CAPABILITY_LABELS, get_disabled_capabilities,
    infer_model_group, normalize_model_entry,
)

from . import theme as _theme_module
from .constants import (
    BADGE_HEIGHT, CONTEXT_LENGTH_MAX, CURRENCY_OPTIONS,
    MODEL_EDIT_DIALOG_WIDTH, PRICE_SPIN_DECIMALS, PRICE_SPIN_MAX,
    TOKENS_PER_K,
)
from .theme import Theme, apply_dialog_theme
from .widgets import (
    SwitchButton, _BaseFormDialog, install_focus_halo, make_field_label,
)

# 能力标签配色透明度：选中浅底（与徽章一致）/ 未选 / 禁用
_TAG_ACTIVE_ALPHA_LIGHT = 30
_TAG_ACTIVE_ALPHA_DARK = 38
_TAG_IDLE_ALPHA = 18
_TAG_DISABLED_ALPHA = 12


def _soft_color(color_hex: str, alpha: int) -> str:
    """取主题色的半透明浅底色（HexArgb）

    Args:
        color_hex: 主色
        alpha: 透明度（0-255）

    Returns:
        str: #AARRGGBB 颜色串
    """
    color = QColor(color_hex)
    color.setAlpha(alpha)
    return color.name(QColor.NameFormat.HexArgb)


def _capability_tag_style(checked: bool, enabled: bool) -> str:
    """能力标签徽章样式：选中=accent 浅底+同色文字，禁用=灰

    Args:
        checked: 是否选中
        enabled: 是否可用

    Returns:
        str: QToolButton QSS
    """
    t = _theme_module.current_theme()
    if not enabled:
        color = t.fg_muted
        background = _soft_color(t.fg_muted, _TAG_DISABLED_ALPHA)
    elif checked:
        color = t.accent
        alpha = (_TAG_ACTIVE_ALPHA_LIGHT if t.name == "light"
                 else _TAG_ACTIVE_ALPHA_DARK)
        background = _soft_color(t.accent, alpha)
    else:
        color = t.fg_secondary
        background = _soft_color(t.fg_secondary, _TAG_IDLE_ALPHA)
    return (
        f"QToolButton {{ color: {color}; background: {background}; "
        f"border: none; border-radius: 5px; padding: 1px 10px; "
        f"font-size: 11px; }}"
    )


class _CapabilityTag(QToolButton):
    """能力标签开关：徽章风格 checkable 按钮（颜色走主题 token）

    选中态为 accent 浅底 + 同色文字；禁用态灰色。互斥禁用由
    ModelEditDialog._apply_capability_exclusion 经 setEnabled 驱动。
    """

    def __init__(
        self, capability: str, checked: bool,
        parent: Optional[QWidget] = None,
    ):
        """构造能力标签

        Args:
            capability: 能力键（ALL_CAPABILITIES 闭集内）
            checked: 初始选中态
            parent: 父控件
        """
        super().__init__(parent)
        self.capability_key = capability
        self.setText(CAPABILITY_LABELS.get(capability, capability))
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(BADGE_HEIGHT)
        self.toggled.connect(self._refresh_style)
        self._refresh_style()

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 (Qt 命名)
        """可用态变化时同步刷新样式（禁用置灰）"""
        super().setEnabled(enabled)
        self._refresh_style()

    def _refresh_style(self, *_args: Any) -> None:
        """按当前选中/可用态重建样式"""
        self.setStyleSheet(
            _capability_tag_style(self.isChecked(), self.isEnabled()))

    def apply_theme(self, _theme: Theme) -> None:
        """主题切换：按新 token 重建样式

        Args:
            _theme: 新主题 token（颜色经 current_theme() 读取，仅触发刷新）
        """
        self._refresh_style()


class ModelEditDialog(_BaseFormDialog):
    """模型条目编辑对话框

    负责单个模型条目的表单展示与校验；条目的落盘（写入实例
    ``custom_models``）由调用方（主壳）在对话框被接受后完成。
    """

    def __init__(
        self,
        model_data: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        """构造对话框

        Args:
            model_data: 既有模型条目（统一 schema）；None 表示新建模式
            parent: 父控件
        """
        self._edit_mode = model_data is not None
        self._model_data = (
            normalize_model_entry(model_data) if model_data else {})
        super().__init__("编辑模型" if self._edit_mode else "添加模型", parent)
        self.setMinimumWidth(MODEL_EDIT_DIALOG_WIDTH)
        # 先换肤（更新 CURRENT_THEME）再构建内容，保证能力标签按当前主题着色
        apply_dialog_theme(self)
        self._capability_tags: List[_CapabilityTag] = []
        self._init_ui()
        install_focus_halo(self)

    # ==================== 界面构建 ====================

    def _init_ui(self) -> None:
        """构建表单：ID/名称/分组 + 能力标签组 + 上下文 + 流式 + 定价 + 按钮"""
        self._id_edit = QLineEdit(self)
        self._id_edit.setText(str(self._model_data.get("id", "")))
        self._id_edit.setPlaceholderText("如 glm-4-flash")
        self._add_field("模型 ID", self._id_edit)
        if self._edit_mode:
            self._id_edit.setReadOnly(True)
            self._id_edit.setToolTip("编辑模式下模型 ID 不可修改")
        self._name_edit = QLineEdit(self)
        self._name_edit.setText(str(self._model_data.get("name", "")))
        self._name_edit.setPlaceholderText("留空则使用模型 ID")
        self._add_field("显示名称", self._name_edit)
        self._group_edit = QLineEdit(self)
        self._group_edit.setText(str(self._model_data.get("group", "")))
        self._group_edit.setPlaceholderText("留空将按模型 ID 自动推断分组")
        self._add_field("分组", self._group_edit)
        self._layout.addLayout(self._build_capability_row())
        self._layout.addLayout(self._build_context_row())
        self._layout.addLayout(self._build_streaming_row())
        self._layout.addLayout(self._build_price_row())
        self._layout.addStretch(1)
        ok = self._add_buttons("确定")
        # 基类默认连接 accept；改为先校验再接受
        ok.clicked.disconnect()
        ok.clicked.connect(self._on_confirm)
        self._apply_capability_exclusion()

    def _build_capability_row(self) -> QVBoxLayout:
        """构建能力标签开关组（互斥规则由 _apply_capability_exclusion 应用）"""
        row = QVBoxLayout()
        row.setSpacing(6)
        row.addWidget(make_field_label("能力标签"))
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(8)
        selected = self._model_data.get("capabilities") or []
        for capability in ALL_CAPABILITIES:
            tag = _CapabilityTag(capability, capability in selected, self)
            tag.toggled.connect(self._apply_capability_exclusion)
            self._capability_tags.append(tag)
            tags_layout.addWidget(tag)
        tags_layout.addStretch(1)
        row.addLayout(tags_layout)
        return row

    def _build_context_row(self) -> QHBoxLayout:
        """构建上下文长度行（0 表示未设置，步进为 1K）"""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(make_field_label("上下文长度"))
        self._context_spin = QSpinBox(self)
        self._context_spin.setRange(0, CONTEXT_LENGTH_MAX)
        self._context_spin.setSingleStep(TOKENS_PER_K)
        self._context_spin.setSpecialValueText("未设置")
        self._context_spin.setSuffix(" tokens")
        self._context_spin.setToolTip("0 表示未设置；步进为 1K（1024）tokens")
        self._context_spin.setValue(self._model_data.get("context_length") or 0)
        row.addWidget(self._context_spin, stretch=1)
        return row

    def _build_streaming_row(self) -> QHBoxLayout:
        """构建「支持流式输出」开关行"""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(make_field_label("支持流式输出"))
        row.addStretch(1)
        streaming = self._model_data.get("support_streaming", True)
        self._streaming_switch = SwitchButton(bool(streaming), self)
        row.addWidget(self._streaming_switch)
        return row

    def _build_price_row(self) -> QVBoxLayout:
        """构建定价行（输入/输出每百万 tokens + 币种，0 表示未设置）"""
        row = QVBoxLayout()
        row.setSpacing(6)
        row.addWidget(make_field_label("定价（每百万 tokens，0 表示未设置）"))
        fields = QHBoxLayout()
        fields.setSpacing(8)
        self._input_price_spin = self._make_price_spin(
            self._model_data.get("input_price_per_1m"))
        self._output_price_spin = self._make_price_spin(
            self._model_data.get("output_price_per_1m"))
        self._currency_combo = QComboBox(self)
        self._currency_combo.addItems(list(CURRENCY_OPTIONS))
        currency = self._model_data.get("currency") or CURRENCY_OPTIONS[0]
        index = self._currency_combo.findText(currency)
        self._currency_combo.setCurrentIndex(max(index, 0))
        fields.addWidget(QLabel("输入", self))
        fields.addWidget(self._input_price_spin, stretch=1)
        fields.addWidget(QLabel("输出", self))
        fields.addWidget(self._output_price_spin, stretch=1)
        fields.addWidget(self._currency_combo)
        row.addLayout(fields)
        return row

    def _make_price_spin(self, value: Optional[float]) -> QDoubleSpinBox:
        """构建单个定价输入框（0 = 未设置）

        Args:
            value: 初始定价（None 按 0 处理）

        Returns:
            QDoubleSpinBox: 定价输入框
        """
        spin = QDoubleSpinBox(self)
        spin.setRange(0.0, PRICE_SPIN_MAX)
        spin.setDecimals(PRICE_SPIN_DECIMALS)
        spin.setSpecialValueText("未设置")
        spin.setValue(float(value) if value else 0.0)
        return spin

    # ==================== 能力互斥 ====================

    def _apply_capability_exclusion(self, *_args: Any) -> None:
        """按互斥规则禁用不可选的能力标签

        已选能力命中互斥组（embedding/rerank）时，其余能力标签禁用；
        已选中的标签始终保持可用（可取消勾选）。
        """
        selected = [t.capability_key for t in self._capability_tags
                    if t.isChecked()]
        disabled = set(get_disabled_capabilities(selected))
        for tag in self._capability_tags:
            tag.setEnabled(tag.capability_key not in disabled)

    # ==================== 确认与数据输出 ====================

    def _on_confirm(self) -> None:
        """确定按钮：校验模型 ID 非空后接受对话框"""
        if not self._id_edit.text().strip():
            QMessageBox.warning(self, "校验失败", "请输入模型 ID。")
            return
        self.accept()

    def get_model_data(self) -> Dict[str, Any]:
        """输出编辑后的模型条目（统一 schema）

        group 留空时经 ``infer_model_group`` 按模型 ID 自动推断；
        context_length 与定价为 0 时输出 None（未设置）；结果经
        ``normalize_model_entry`` 兜底规范化（能力值过滤、缺省键补全）。

        Returns:
            Dict[str, Any]: 统一模型 schema 字典
        """
        model_id = self._id_edit.text().strip()
        group = self._group_edit.text().strip()
        raw = {
            "id": model_id,
            "name": self._name_edit.text().strip() or model_id,
            "group": group or infer_model_group(model_id),
            "capabilities": [t.capability_key for t in self._capability_tags
                             if t.isChecked()],
            "context_length": self._context_spin.value() or None,
            "support_streaming": self._streaming_switch.isChecked(),
            "currency": self._currency_combo.currentText(),
            "input_price_per_1m": self._input_price_spin.value() or None,
            "output_price_per_1m": self._output_price_spin.value() or None,
        }
        return normalize_model_entry(raw)

    # ==================== 主题 ====================

    def apply_theme(self, theme: Theme) -> None:
        """主题切换：刷新能力标签与流式开关的自绘样式

        Args:
            theme: 新主题 token
        """
        for tag in getattr(self, "_capability_tags", []):
            tag.apply_theme(theme)
        streaming = getattr(self, "_streaming_switch", None)
        if streaming is not None:
            streaming.apply_theme(theme)
