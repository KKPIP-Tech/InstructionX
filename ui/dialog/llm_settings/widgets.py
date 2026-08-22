# ui/dialog/llm_settings/widgets.py
"""LLM 设置界面通用控件模块

提供主题 token 驱动的通用控件与工厂函数：徽章 / 分隔线 / 小标题 /
字段标签 / 眼睛图标、自绘开关 SwitchButton、焦点光环事件过滤器、
Provider 列表项 ProviderItemWidget、模型行 ModelRow 与表单对话框基类
_BaseFormDialog。

所有颜色读取 ``theme.current_theme()`` 的 token，换肤经
``apply_dialog_theme`` 统一驱动（鸭子类型调用各控件的 apply_theme）。
"""

import weakref
from typing import Any, Dict, Optional

from PySide6.QtCore import (
    Property, QEasingCurve, QEvent, QObject, QRectF, QSize, Qt,
    QPropertyAnimation, Signal,
)
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QCheckBox, QComboBox, QDialog, QFrame,
    QGraphicsDropShadowEffect, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.llm.model_schema import (
    CAPABILITY_EMBEDDING, CAPABILITY_RERANK, CAPABILITY_VISION,
)

from . import theme as _theme_module
from .constants import (
    BADGE_HEIGHT, EYE_ICON_SIZE,
    FORM_BUTTON_HEIGHT, FORM_BUTTONS_TOP_GAP, FORM_DIALOG_MARGIN,
    FORM_DIALOG_MIN_WIDTH, FORM_DIALOG_SPACING, FORM_FIELD_GAP,
    FORM_INPUT_HEIGHT, HAIRLINE_HEIGHT, LIST_ITEM_ICON_PX,
    LIST_ITEM_MARGIN_H, LIST_ITEM_NAME_ELIDE_WIDTH, LIST_ITEM_SPACING,
    MODEL_ROW_HEIGHT, MODEL_ROW_MARGIN_LEFT, MODEL_ROW_MARGIN_RIGHT,
    MODEL_ROW_SPACING, MODEL_SWITCH_HEIGHT, MODEL_SWITCH_WIDTH,
    MODEL_TYPE_CHAT, MODEL_TYPE_EMBEDDING, MODEL_TYPE_I18N_KEYS,
    MODEL_TYPE_RERANK, MODEL_TYPE_VISION, ROW_DELETE_BUTTON_SIZE,
    SWITCH_ANIM_DURATION_MS, SWITCH_HEIGHT, SWITCH_WIDTH,
)
from .icons import provider_icon_pixmap
from .theme import Theme

# HiDPI 渲染倍率（2x 保证高分屏清晰）
_HIDPI_DPR = 2.0
# 徽章浅色底透明度（亮/暗主题分别调过对比度）
_BADGE_BG_ALPHA_LIGHT = 30
_BADGE_BG_ALPHA_DARK = 38
# 焦点光环模糊半径与颜色透明度
_FOCUS_HALO_BLUR_RADIUS = 9
_FOCUS_HALO_ALPHA = 80
# 开关绘制：轨道内缩 / 滑块边距 / 禁用态轨道与滑块透明度
_SWITCH_TRACK_INSET = 1
_SWITCH_THUMB_MARGIN = 3.0
_SWITCH_TRACK_DISABLED_ALPHA = 110
_SWITCH_THUMB_DISABLED_ALPHA = 200


# ---------------------------------------------------------------------------
# 眼睛图标（自绘，避免依赖 emoji 字体）
# ---------------------------------------------------------------------------

def make_eye_icon(
    visible: bool, color: Optional[QColor] = None, size: int = EYE_ICON_SIZE,
) -> QIcon:
    """自绘眼睛图标（visible=False 时带斜杠）

    Args:
        visible: 是否可见（False 时绘制斜杠表示隐藏）
        color: 线条颜色，缺省取当前主题 fg_secondary
        size: 图标边长（逻辑像素）

    Returns:
        QIcon: 眼睛图标（HiDPI 2x）
    """
    color = color or QColor(_theme_module.current_theme().fg_secondary)
    dpr = _HIDPI_DPR
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)
    pen = QPen(color)
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QRectF(2.0, size * 0.28, size - 4.0, size * 0.44))   # 眼眶
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(size / 2 - 2.2, size / 2 - 2.2, 4.4, 4.4))    # 瞳孔
    if not visible:
        pen.setWidthF(1.7)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(int(size * 0.18), int(size * 0.84),
                   int(size * 0.84), int(size * 0.18))                  # 斜杠
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


# ---------------------------------------------------------------------------
# 徽章 / 分隔线 / 小标题 / 字段标签
# ---------------------------------------------------------------------------

def _badge_style(color_hex: str) -> str:
    """徽章样式：半透明浅底 + 同色文字，圆角 5px

    Args:
        color_hex: 徽章主色

    Returns:
        str: QLabel QSS
    """
    color = QColor(color_hex)
    bg = QColor(color)
    bg.setAlpha(_BADGE_BG_ALPHA_LIGHT
                if _theme_module.current_theme().name == "light"
                else _BADGE_BG_ALPHA_DARK)
    return (
        f"QLabel {{ color: {color_hex}; "
        f"background: {bg.name(QColor.NameFormat.HexArgb)}; "
        f"border-radius: 5px; padding: 1px 8px; font-size: 11px; }}"
    )


def make_badge(text: str, color_hex: str) -> QLabel:
    """小号类型徽章（浅色半透明底 + 对应色文字）

    Args:
        text: 徽章文本
        color_hex: 徽章主色

    Returns:
        QLabel: 徽章控件
    """
    label = QLabel(text)
    label.setStyleSheet(_badge_style(color_hex))
    label.setFixedHeight(BADGE_HEIGHT)
    return label


def make_hairline() -> QFrame:
    """1px 低对比分隔线（分区 / 模型行间）

    Returns:
        QFrame: 分隔线控件（objectName "Hairline"，颜色走 QSS token）
    """
    line = QFrame()
    line.setObjectName("Hairline")
    line.setFixedHeight(HAIRLINE_HEIGHT)
    return line


def make_section_label(text: str) -> QLabel:
    """区块小标题：12px、半粗、muted、字距略宽

    Args:
        text: 标题文本

    Returns:
        QLabel: 小标题控件（objectName "SectionLabel"）
    """
    label = QLabel(text)
    label.setObjectName("SectionLabel")
    font = label.font()
    font.setPixelSize(12)
    font.setWeight(QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
    label.setFont(font)
    return label


def make_field_label(text: str) -> QLabel:
    """表单字段小标签：12px 次级色

    Args:
        text: 标签文本

    Returns:
        QLabel: 字段标签控件（objectName "FieldLabel"）
    """
    label = QLabel(text)
    label.setObjectName("FieldLabel")
    font = label.font()
    font.setPixelSize(12)
    label.setFont(font)
    return label


def model_type_label(type_key: str) -> str:
    """取模型主类型的展示文案（按当前语言实时取词，不做模块级固化）

    Args:
        type_key: 主类型键（chat / vision / embedding / rerank）

    Returns:
        str: 类型展示文案；未登记的类型键回退原始键名
    """
    i18n_key = MODEL_TYPE_I18N_KEYS.get(type_key)
    if i18n_key is None:
        return type_key
    return tr("dialog_llm_settings", i18n_key)


# ---------------------------------------------------------------------------
# 自绘开关按钮（QAbstractButton + QPainter，带滑块动画，颜色走 token）
# ---------------------------------------------------------------------------

class SwitchButton(QAbstractButton):
    """iOS 风格小开关。checked 变化时滑块位置做 140ms 缓动动画。"""

    def __init__(self, checked: bool = False, parent: Optional[QWidget] = None,
                 size: Optional[QSize] = None):
        """构造开关

        Args:
            checked: 初始选中态
            parent: 父控件
            size: 固定尺寸，缺省为标准开关尺寸
        """
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(size or QSize(SWITCH_WIDTH, SWITCH_HEIGHT))
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(SWITCH_ANIM_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        super().setChecked(checked)
        self.toggled.connect(self._animate)

    # --- Qt property，供动画驱动 ---
    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _animate(self, on: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def set_checked_no_anim(self, on: bool) -> None:
        """同步数据到 UI 时使用：不触发 toggled、不动画

        Args:
            on: 目标选中态
        """
        self._anim.stop()
        self.blockSignals(True)
        self.setChecked(on)
        self.blockSignals(False)
        self._offset = 1.0 if on else 0.0
        self.update()

    def apply_theme(self, _theme: Theme) -> None:
        """主题切换：重新读取 token 绘制

        Args:
            _theme: 新主题 token（绘制时经 current_theme() 读取，仅触发重绘）
        """
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt 命名)
        t = _theme_module.current_theme()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(
            _SWITCH_TRACK_INSET, _SWITCH_TRACK_INSET,
            -_SWITCH_TRACK_INSET, -_SWITCH_TRACK_INSET)
        radius = rect.height() / 2.0
        track = QColor(t.accent if self.isChecked() else t.switch_off)
        if not self.isEnabled():
            track.setAlpha(_SWITCH_TRACK_DISABLED_ALPHA)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(rect, radius, radius)
        margin = _SWITCH_THUMB_MARGIN
        d = rect.height() - 2 * margin
        x = rect.x() + margin + self._offset * (rect.width() - 2 * margin - d)
        thumb = QColor("#ffffff")
        if not self.isEnabled():
            thumb.setAlpha(_SWITCH_THUMB_DISABLED_ALPHA)
        p.setBrush(thumb)
        p.drawEllipse(QRectF(x, rect.y() + margin, d, d))
        p.end()

    def sizeHint(self) -> QSize:
        return self.size()


# ---------------------------------------------------------------------------
# 焦点光环：focus 时给输入控件加一层半透明 accent 外描边
# ---------------------------------------------------------------------------

class _FocusHaloFilter(QObject):
    """对话框作用域焦点光环过滤器

    安装在 QApplication 上，但仅对被观察对话框的子控件（QLineEdit /
    QComboBox）生效：获得焦点时叠加 QGraphicsDropShadowEffect（accent、
    低透明、小模糊半径 ≈ 2px 光环），失去焦点时移除。持有对话框弱引用，
    对话框销毁后不再生效。颜色在 FocusIn 时读取当前主题，始终跟随主题。
    """

    def __init__(self, dialog: QDialog):
        """构造过滤器

        Args:
            dialog: 生效范围对话框（弱引用持有，不延长其生命周期）
        """
        super().__init__()
        self._dialog_ref = weakref.ref(dialog)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        # 先按控件类型与事件类型快速过滤：过滤器挂在 QApplication 上会收到
        # 全部对象（含非 QWidget 的内部 QObject）的全部事件，isAncestorOf
        # 只接受 QWidget，必须在确认类型后再调用
        if not isinstance(obj, (QLineEdit, QComboBox)):
            return False
        if event.type() not in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            return False
        dialog = self._dialog_ref()
        if dialog is None:
            return False
        try:
            if not dialog.isAncestorOf(obj):
                return False
        except RuntimeError:
            # 对话框 C++ 侧已销毁（弱引用包装仍在），不再生效
            return False
        if event.type() == QEvent.Type.FocusIn:
            color = QColor(_theme_module.current_theme().accent)
            color.setAlpha(_FOCUS_HALO_ALPHA)
            effect = QGraphicsDropShadowEffect()
            effect.setBlurRadius(_FOCUS_HALO_BLUR_RADIUS)
            effect.setOffset(0, 0)
            effect.setColor(color)
            obj.setGraphicsEffect(effect)
        else:
            obj.setGraphicsEffect(None)
        return False


def install_focus_halo(dialog: QDialog) -> None:
    """为对话框安装焦点光环（QLineEdit / QComboBox focus 外描边）

    过滤器安装在 QApplication 上但仅对该对话框子树生效；过滤器对象
    由对话框持有，对话框销毁后过滤器随之销毁并自动从 QApplication
    移除（QObject 析构自动摘除事件过滤）。重复调用幂等。

    Args:
        dialog: 目标对话框
    """
    if getattr(dialog, "_llm_focus_halo_filter", None) is not None:
        return
    app = QApplication.instance()
    if app is None:
        return
    halo = _FocusHaloFilter(dialog)
    app.installEventFilter(halo)
    dialog._llm_focus_halo_filter = halo


# ---------------------------------------------------------------------------
# Provider 列表项
# ---------------------------------------------------------------------------

class ProviderItemWidget(QWidget):
    """Provider 列表项：品牌图标(20px) + 名称 + 启用开关，选中为圆角 pill

    图标着色：常态 fg_secondary，hover fg_primary，选中 accent。
    本控件只承载轻量视图参数（不持有配置对象），数据刷新经 refresh()。

    Signals:
        clicked(str): 点击条目（实例 id）
        toggled(str, bool): 开关切换（实例 id, 新状态）
    """

    clicked = Signal(str)
    toggled = Signal(str, bool)

    def __init__(
        self,
        instance_id: str,
        name: str,
        preset_id: Optional[str],
        enabled: bool,
        parent: Optional[QWidget] = None,
    ):
        """构造列表项

        Args:
            instance_id: 实例 id
            name: 实例显示名
            preset_id: 关联预设 id（None 表示自定义实例，走字母方块图标）
            enabled: 启用态（enabled_chat）
            parent: 父控件
        """
        super().__init__(parent)
        self.setObjectName("ProviderItem")
        # 普通 QWidget 子类必须开启此属性，QSS 背景/边框才会绘制
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("selected", False)
        self.setProperty("hover", False)
        self.provider_id = instance_id
        self._name_text = name
        self._preset_id = preset_id
        self._hover = False
        self._init_ui(enabled)
        self.refresh(name, preset_id, enabled)

    def _init_ui(self, enabled: bool) -> None:
        """构建行内布局：图标 + 名称 + 开关

        Args:
            enabled: 开关初始态
        """
        layout = QHBoxLayout(self)
        layout.setContentsMargins(LIST_ITEM_MARGIN_H, 0, LIST_ITEM_MARGIN_H, 0)
        layout.setSpacing(LIST_ITEM_SPACING)
        self._icon = QLabel()
        self._icon.setFixedSize(LIST_ITEM_ICON_PX, LIST_ITEM_ICON_PX)
        layout.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self._name = QLabel()
        self._name.setSizePolicy(QSizePolicy.Policy.Ignored,
                                 QSizePolicy.Policy.Preferred)
        layout.addWidget(self._name, 1)
        self.switch = SwitchButton(enabled)
        self.switch.setToolTip(
            tr("dialog_llm_settings", "widget.provider_switch.tooltip"))
        self.switch.toggled.connect(
            lambda on: self.toggled.emit(self.provider_id, on))
        layout.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------
    def _icon_color(self) -> QColor:
        """按选中/悬停状态推导图标着色"""
        t = _theme_module.current_theme()
        if self.property("selected"):
            return QColor(t.accent)
        if self._hover:
            return QColor(t.fg_primary)
        return QColor(t.fg_secondary)

    def _update_icon(self) -> None:
        self._icon.setPixmap(provider_icon_pixmap(
            self._preset_id, self._name_text, LIST_ITEM_ICON_PX,
            self._icon_color()))

    def refresh(
        self, name: str, preset_id: Optional[str], enabled: bool,
    ) -> None:
        """数据变化后刷新视图（名称/图标/开关）

        Args:
            name: 实例显示名
            preset_id: 关联预设 id
            enabled: 启用态
        """
        self._name_text = name
        self._preset_id = preset_id
        self._update_icon()
        metrics = self._name.fontMetrics()
        self._name.setText(metrics.elidedText(
            name, Qt.TextElideMode.ElideRight, LIST_ITEM_NAME_ELIDE_WIDTH))
        self._name.setToolTip(name)
        self.switch.set_checked_no_anim(enabled)

    def set_selected(self, selected: bool) -> None:
        """更新选中态（pill 背景 + 图标 accent 着色）

        Args:
            selected: 是否选中
        """
        if self.property("selected") == selected:
            return
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_icon()

    def apply_theme(self, _theme: Theme) -> None:
        """主题切换：重渲品牌图标与开关

        Args:
            _theme: 新主题 token
        """
        self._update_icon()
        self.switch.update()

    # ------------------------------------------------------------------
    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True
        self.setProperty("hover", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_icon()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False
        self.setProperty("hover", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self._update_icon()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        # 点击条目（非开关区域）时选中该项
        self.clicked.emit(self.provider_id)
        super().mousePressEvent(event)


# ---------------------------------------------------------------------------
# 模型行
# ---------------------------------------------------------------------------

def _model_primary_type(entry: Dict[str, Any]) -> str:
    """推导模型条目的主类型（用于徽章与分组）

    规则：capabilities 含 embedding → 嵌入；含 rerank → 重排序；
    含 vision → 视觉；否则 → 对话。

    Args:
        entry: 统一 schema 模型条目

    Returns:
        str: 主类型键（chat / vision / embedding / rerank）
    """
    capabilities = entry.get("capabilities") or []
    if CAPABILITY_EMBEDDING in capabilities:
        return MODEL_TYPE_EMBEDDING
    if CAPABILITY_RERANK in capabilities:
        return MODEL_TYPE_RERANK
    if CAPABILITY_VISION in capabilities:
        return MODEL_TYPE_VISION
    return MODEL_TYPE_CHAT


class ModelRow(QWidget):
    """单个模型行：勾选框(管理模式) + ID + 类型徽章 + 开关 + 删除

    行高 44px，行间 1px hairline（由详情面板插入），hover 整行微亮底；
    删除按钮平时 muted、hover 变 danger。模型条目为统一 schema dict。

    Signals:
        sig_delete(object): 请求删除该模型（条目 dict）
        sig_checked(): 管理模式勾选态变化
        sig_toggled(str, bool): 启用开关切换（模型 id, 新状态）
        sig_edit(object): 请求编辑该模型（双击行触发，条目 dict）
    """

    sig_delete = Signal(object)
    sig_checked = Signal()
    sig_toggled = Signal(str, bool)
    sig_edit = Signal(object)

    HEIGHT = MODEL_ROW_HEIGHT

    def __init__(self, entry: Dict[str, Any], parent: Optional[QWidget] = None):
        """构造模型行

        Args:
            entry: 统一 schema 模型条目（开关初始态取 entry["enabled"]，
                缺省 True）
            parent: 父控件
        """
        super().__init__(parent)
        self.setObjectName("ModelRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(self.HEIGHT)
        self.entry = entry
        self._type_key = _model_primary_type(entry)
        self._init_ui()

    def _init_ui(self) -> None:
        """构建行内布局：勾选框 + ID + 类型徽章 + 开关 + 删除按钮"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            MODEL_ROW_MARGIN_LEFT, 0, MODEL_ROW_MARGIN_RIGHT, 0)
        layout.setSpacing(MODEL_ROW_SPACING)
        self.checkbox = QCheckBox()
        self.checkbox.setVisible(False)
        self.checkbox.toggled.connect(
            lambda _checked: self.sig_checked.emit())
        layout.addWidget(self.checkbox)
        id_label = QLabel(str(self.entry.get("id", "")))
        id_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(id_label, 1)
        self._badge_color = self._resolve_badge_color(
            _theme_module.current_theme())
        self._badge = make_badge(
            model_type_label(self._type_key),
            self._badge_color)
        layout.addWidget(self._badge)
        self.switch = SwitchButton(
            bool(self.entry.get("enabled", True)),
            size=QSize(MODEL_SWITCH_WIDTH, MODEL_SWITCH_HEIGHT))
        self.switch.setToolTip(
            tr("dialog_llm_settings", "widget.model_switch.tooltip"))
        self.switch.toggled.connect(self._on_switch_toggled)
        layout.addWidget(self.switch)
        layout.addWidget(self._build_delete_button())

    def _build_delete_button(self) -> QToolButton:
        """构建行尾删除按钮（平时 muted、hover 变 danger，样式走 QSS）"""
        delete_btn = QToolButton()
        delete_btn.setObjectName("RowDeleteBtn")
        delete_btn.setText("✕")
        delete_btn.setFixedSize(ROW_DELETE_BUTTON_SIZE, ROW_DELETE_BUTTON_SIZE)
        delete_btn.setToolTip(
            tr("dialog_llm_settings", "widget.model_row.delete_tooltip"))
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.sig_delete.emit(self.entry))
        return delete_btn

    def _resolve_badge_color(self, t: Theme) -> str:
        """按主类型从主题 token 取徽章色（未登记回退 accent）"""
        return t.model_type_colors.get(self._type_key, t.accent)

    def _on_switch_toggled(self, on: bool) -> None:
        """开关切换：仅外发信号，覆写落盘由详情面板负责"""
        self.sig_toggled.emit(str(self.entry.get("id", "")), on)

    def set_manage_mode(self, on: bool) -> None:
        """切换管理模式（显示/隐藏勾选框；退出时清除勾选）

        Args:
            on: 是否进入管理模式
        """
        self.checkbox.setVisible(on)
        if not on:
            self.checkbox.blockSignals(True)
            self.checkbox.setChecked(False)
            self.checkbox.blockSignals(False)

    def is_checked(self) -> bool:
        """管理模式下是否被勾选"""
        return self.checkbox.isChecked()

    def set_checked(self, on: bool) -> None:
        """设置管理模式勾选态

        Args:
            on: 勾选态
        """
        self.checkbox.setChecked(on)

    def apply_theme(self, theme: Theme) -> None:
        """主题切换：重渲类型徽章与开关

        Args:
            theme: 新主题 token
        """
        self._badge_color = self._resolve_badge_color(theme)
        self._badge.setStyleSheet(_badge_style(self._badge_color))
        self.switch.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        # 双击行 = 请求编辑该模型（编辑对话框由主壳/后续子任务接入）
        self.sig_edit.emit(self.entry)
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# 表单对话框基类
# ---------------------------------------------------------------------------

class _BaseFormDialog(QDialog):
    """带确定/取消按钮的简单表单对话框基类

    子类经 ``_add_field`` 追加「标签 + 输入控件」、``_add_buttons``
    追加按钮行并拿到确定按钮（可做输入校验联动）。
    """

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        """构造表单对话框

        Args:
            title: 窗口标题
            parent: 父控件
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(FORM_DIALOG_MIN_WIDTH)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            FORM_DIALOG_MARGIN, FORM_DIALOG_MARGIN,
            FORM_DIALOG_MARGIN, FORM_DIALOG_MARGIN)
        self._layout.setSpacing(FORM_DIALOG_SPACING)

    def _add_field(self, label: str, widget: QWidget) -> None:
        """追加一个表单字段（标签 + 控件）

        Args:
            label: 字段标签文本
            widget: 输入控件（QLineEdit 统一表单高度）
        """
        text = QLabel(label)
        text.setObjectName("FormLabel")
        self._layout.addWidget(text)
        if isinstance(widget, QLineEdit):
            widget.setFixedHeight(FORM_INPUT_HEIGHT)
        self._layout.addWidget(widget)
        self._layout.addSpacing(FORM_FIELD_GAP)

    def _add_buttons(self, ok_text: str) -> QPushButton:
        """追加按钮行（取消 + 确定），返回确定按钮供校验联动

        Args:
            ok_text: 确定按钮文本

        Returns:
            QPushButton: 确定按钮（accent 样式，默认按钮）
        """
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton(tr("common", "cancel"))
        cancel.setFixedHeight(FORM_BUTTON_HEIGHT)
        cancel.clicked.connect(self.reject)
        self._ok = QPushButton(ok_text)
        self._ok.setFixedHeight(FORM_BUTTON_HEIGHT)
        self._ok.setProperty("accent", True)
        self._ok.setDefault(True)
        self._ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(self._ok)
        self._layout.addSpacing(FORM_BUTTONS_TOP_GAP)
        self._layout.addLayout(row)
        return self._ok
