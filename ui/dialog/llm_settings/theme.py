# ui/dialog/llm_settings/theme.py
"""LLM 设置界面主题模块

以 token 化 ``Theme`` dataclass 集中描述对话框配色；token 值不再硬编码，
而是由 :func:`_theme_from_uikit` 实时取自 InstructionX_UIKit 设计令牌
（``T()``），随全局主题模式（``ui.uikit_theme.current_theme_mode``）生成。
``build_qss(theme)`` 从 token 生成对话框作用域 QSS；
``apply_dialog_theme(dialog)`` 为 LLM 设置对话框完成
palette + stylesheet + 自绘控件换色的一次性应用，并连接 UIKit
``theme_changed`` 信号实现对话框打开期间的实时跟随。

作用域约定：主题只应用于传入的对话框自身（setPalette / setStyleSheet），
**绝不触碰 QApplication 全局 palette / stylesheet**，避免污染主程序主题。
"""

import os
import tempfile
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QDialog, QWidget
from shiboken6 import isValid

from InstructionX_UIKit import T
from InstructionX_UIKit.theme import ThemeManager

from ui.uikit_theme import current_theme_mode


# ---------------------------------------------------------------------------
# 主题 token
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Theme:
    """一套主题 token：背景层级 / 线条 / 前景 / 强调色 / 语义色 / 徽章色

    所有 QSS 与自绘控件（SwitchButton、徽章、品牌图标着色等）只引用
    token；新增主题 = 复制一套 token 改色即可。

    Attributes:
        name: 主题名（"light" / "dark"）
        bg_base: 窗口 / 右侧主区域底
        bg_sidebar: 侧栏底
        bg_card: 抬升面（管理工具条、菜单、对话框抬升元素）
        bg_input: 输入控件底
        bg_hover: 悬停底（rgba 半透明，叠加在不同底色上都自然）
        bg_active: 选中 / 按下底
        bg_disabled: 禁用输入底
        border: 常规 1px 边框
        border_strong: hover 时边框
        hairline: 低对比分隔线（1px 分区线 / 模型行间线）
        fg_primary: 主文字 13px 正文
        fg_secondary: 次级文字 / 图标常态
        fg_muted: 辅助文字 11/12px
        accent / accent_hover / accent_pressed / accent_disabled: 强调色
        accent_fg: accent 实底上的文字色
        success / danger: 语义色
        warning: 警告语义色（如健康检查「跳过」状态）
        danger_soft / danger_soft_pressed: destructive hover 浅底（rgba）
        overlay: 停用遮罩（rgba）
        switch_off: 开关关态轨道色
        scrollbar / scrollbar_hover: 滚动条
        provider_type_colors: 提供商类型徽章色（key 为适配器家族键）
        model_type_colors: 模型类型徽章色（key 为模型主类型）
    """

    name: str
    bg_base: str
    bg_sidebar: str
    bg_card: str
    bg_input: str
    bg_hover: str
    bg_active: str
    bg_disabled: str
    border: str
    border_strong: str
    hairline: str
    fg_primary: str
    fg_secondary: str
    fg_muted: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_disabled: str
    accent_fg: str
    success: str
    danger: str
    warning: str
    danger_soft: str
    danger_soft_pressed: str
    overlay: str
    switch_off: str
    scrollbar: str
    scrollbar_hover: str
    provider_type_colors: dict = field(default_factory=dict)
    model_type_colors: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 品牌/类型徽章配色（语义品牌色，不属主题色板，按模式各存一套）
# ---------------------------------------------------------------------------

_PROVIDER_TYPE_COLORS = {
    "light": {
        "openai": "#4f6fe0",
        "anthropic": "#b06e48",
        "gemini": "#2f8a7e",
        "azure": "#5878c0",
    },
    "dark": {
        "openai": "#8aa1f6",
        "anthropic": "#cf9a78",
        "gemini": "#63b3aa",
        "azure": "#8ba3d9",
    },
}

_MODEL_TYPE_COLORS = {
    "light": {
        "chat": "#4f6fe0",
        "vision": "#2f9062",
        "embedding": "#a87f2c",
        "rerank": "#995cb0",
    },
    "dark": {
        "chat": "#8aa1f6",
        "vision": "#74b595",
        "embedding": "#cfa85f",
        "rerank": "#b98ac2",
    },
}


def _rgba(hex_color: str, alpha: float) -> str:
    """把 #RRGGBB 转为 rgba() 字符串（用于 danger_soft 等半透明派生色）"""
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha})"


def _theme_from_uikit() -> Theme:
    """从 UIKit 设计令牌实时构建对话框主题 token（随当前亮/暗模式）

    全部颜色令牌经 ``T()`` 取当前模式值；品牌/类型徽章色为语义色，
    不属 UIKit 色板，按模式从内置表选取。
    """
    name = current_theme_mode()
    danger = T("color.danger")
    return Theme(
        name=name,
        bg_base=T("color.bg.base"),
        bg_sidebar=T("color.bg.subtle"),
        bg_card=T("color.bg.elevated"),
        bg_input=T("color.bg.elevated"),
        bg_hover=T("color.bg.muted"),
        bg_active=T("color.primary.subtle"),
        bg_disabled=T("color.bg.muted"),
        border=T("color.border"),
        border_strong=T("color.border.strong"),
        hairline=T("color.bg.muted"),
        fg_primary=T("color.text.primary"),
        fg_secondary=T("color.text.secondary"),
        fg_muted=T("color.text.tertiary"),
        accent=T("color.primary"),
        accent_hover=T("color.primary.hover"),
        accent_pressed=T("color.primary.pressed"),
        accent_disabled=T("color.primary.subtle"),
        accent_fg=T("color.on.primary"),
        success=T("color.success"),
        danger=danger,
        warning=T("color.warning"),
        danger_soft=_rgba(danger, 0.12),
        danger_soft_pressed=_rgba(danger, 0.20),
        overlay=T("color.overlay"),
        switch_off=T("color.border.strong"),
        scrollbar=T("color.border"),
        scrollbar_hover=T("color.border.strong"),
        provider_type_colors=dict(_PROVIDER_TYPE_COLORS[name]),
        model_type_colors=dict(_MODEL_TYPE_COLORS[name]),
    )


# 当前主题（自绘控件在 paintEvent / 重绘时读取；apply_dialog_theme 负责切换）
CURRENT_THEME: Theme | None = None


def current_theme() -> Theme:
    """获取当前主题 token（由 apply_dialog_theme 更新，未应用过则实时构建）

    自绘控件应经本访问器读取当前主题，而不是直接 ``from .theme import
    CURRENT_THEME``（模块级 rebinding 会导致导入方持有过期引用）。

    Returns:
        Theme: 当前主题 token
    """
    global CURRENT_THEME
    if CURRENT_THEME is None:
        CURRENT_THEME = _theme_from_uikit()
    return CURRENT_THEME


# ---------------------------------------------------------------------------
# QSS：由 token 生成的 f-string 模板
# ---------------------------------------------------------------------------

def build_qss(t: Theme) -> str:
    """从主题 token 生成对话框作用域 QSS（选择器只命中对话框子树）

    Args:
        t: 主题 token

    Returns:
        str: QSS 文本（设置到对话框上，不影响全局）
    """
    return (
        _anti_interference_qss(t)
        + _base_qss(t) + _input_qss(t) + _push_button_qss(t)
        + _tool_button_qss(t) + _list_scroll_qss(t) + _menu_combo_qss(t)
        + _panel_qss(t) + _progress_bar_qss(t)
    )


def _anti_interference_qss(t: Theme) -> str:
    """抗应用级 QSS 干扰重置（必须置于样式表最前）

    应用主题（UIKit 全局 QSS）中存在两类会穿透到本对话框的规则：
    1. ``QFrame { background-color }``——QLabel/QStackedWidget 均继承 QFrame，
       与应用 QSS 中 ``QLabel { background: transparent }`` 同优先级竞争时
       后者未生效，导致所有标签被画上实底（白块/黑块）；
    2. ``QListView::item`` 系列（选中底色、左侧竖条、padding）——干扰左侧
       Provider 行的自绘 pill 外观，使选中行背景破碎。

    此处统一重置；后续分段的具体规则（QLineEdit、QProgressBar 等继承
    QFrame 的控件）在同优先级下以后置者生效，不受本段影响。
    """
    return f"""
QLabel {{ background: transparent; border: none; }}
QFrame {{ background: transparent; border: none; }}
QStackedWidget {{ background: transparent; }}
QListWidget {{ padding: 0px; }}
QListWidget::item,
QListWidget::item:hover,
QListWidget::item:selected,
QListWidget::item:selected:!active {{
    background: transparent; border: none; padding: 0px; margin: 0px;
}}
"""


def _base_qss(t: Theme) -> str:
    """基础 QSS：对话框底色 / 全局文字 / 提示框 / 面板底色 / 分割条"""
    return f"""
QDialog, QMessageBox {{ background-color: {t.bg_base}; }}
QWidget {{ color: {t.fg_primary}; font-size: 13px; }}

QToolTip {{
    background: {t.bg_card}; color: {t.fg_primary};
    border: 1px solid {t.border}; padding: 4px 8px;
}}

#Sidebar {{ background: {t.bg_sidebar}; border-right: 1px solid {t.border}; }}
#DetailPage, #PlaceholderPage {{ background: {t.bg_base}; }}
#DetailContent {{ background: transparent; }}

QSplitter::handle {{ background: transparent; width: 1px; }}
"""


def _input_qss(t: Theme) -> str:
    """输入控件 QSS：QLineEdit / QAbstractSpinBox 全状态

    Windows 原生风格（windowsvista）下 QSpinBox 忽略 palette 按系统色
    绘制，必须经 QSS 强制接管背景与边框才能随主题换色。
    """
    return f"""
QLineEdit {{
    background: {t.bg_input}; border: 1px solid {t.border};
    border-radius: 6px; padding: 0px 10px; color: {t.fg_primary};
    selection-background-color: {t.accent};
}}
QLineEdit:hover {{ border-color: {t.border_strong}; }}
QLineEdit:focus {{ border-color: {t.accent}; }}
QLineEdit:disabled {{ background: {t.bg_disabled}; color: {t.fg_muted}; }}

QAbstractSpinBox {{
    background: {t.bg_input}; border: 1px solid {t.border};
    border-radius: 6px; padding: 2px 8px; color: {t.fg_primary};
    selection-background-color: {t.accent};
}}
QAbstractSpinBox:hover {{ border-color: {t.border_strong}; }}
QAbstractSpinBox:focus {{ border-color: {t.accent}; }}
QAbstractSpinBox:disabled {{ background: {t.bg_disabled}; color: {t.fg_muted}; }}
"""


def _push_button_qss(t: Theme) -> str:
    """按钮 QSS：QPushButton（常态/accent/danger）/ 添加提供商按钮"""
    return f"""
QPushButton {{
    background: transparent; border: 1px solid {t.border};
    border-radius: 7px; padding: 5px 12px; color: {t.fg_primary};
}}
QPushButton:hover {{ background: {t.bg_hover}; border-color: {t.border_strong}; }}
QPushButton:pressed {{ background: {t.bg_active}; }}
QPushButton:checked {{ background: {t.bg_active}; border-color: {t.border_strong}; }}
QPushButton:disabled {{
    color: {t.fg_muted}; background: transparent; border-color: {t.hairline};
}}
QPushButton[accent="true"] {{
    background: {t.accent}; border-color: {t.accent}; color: {t.accent_fg};
}}
QPushButton[accent="true"]:hover {{
    background: {t.accent_hover}; border-color: {t.accent_hover};
}}
QPushButton[accent="true"]:pressed {{
    background: {t.accent_pressed}; border-color: {t.accent_pressed};
}}
QPushButton[accent="true"]:disabled {{
    background: {t.accent_disabled}; border-color: {t.accent_disabled};
    color: {t.accent_fg};
}}
QPushButton[danger="true"] {{
    color: {t.danger}; border-color: transparent; background: transparent;
}}
QPushButton[danger="true"]:hover {{
    background: {t.danger_soft}; border-color: transparent; color: {t.danger};
}}
QPushButton[danger="true"]:pressed {{ background: {t.danger_soft_pressed}; }}
"""


def _tool_button_qss(t: Theme) -> str:
    """工具按钮 QSS：QToolButton / 模型行删除按钮"""
    return f"""
QToolButton {{
    background: transparent; border: none; border-radius: 6px;
    color: {t.fg_secondary}; padding: 4px;
}}
QToolButton:hover {{ background: {t.bg_hover}; color: {t.fg_primary}; }}
QToolButton:pressed {{ background: {t.bg_active}; }}
QToolButton:checked {{ background: {t.bg_active}; color: {t.accent}; }}
QToolButton:disabled {{ color: {t.fg_muted}; }}

#RowDeleteBtn {{ color: {t.fg_muted}; font-size: 13px; }}
#RowDeleteBtn:hover {{ color: {t.danger}; background: {t.danger_soft}; }}
#RowDeleteBtn:pressed {{ color: {t.danger}; background: {t.danger_soft_pressed}; }}
"""


def _list_scroll_qss(t: Theme) -> str:
    """列表与滚动区 QSS：QListWidget / QScrollArea / QScrollBar"""
    return f"""
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{ border: none; padding: 0px; margin: 0px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px 2px 2px 0px;
}}
QScrollBar::handle:vertical {{
    background: {t.scrollbar}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.scrollbar_hover}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 0px 2px 2px 2px;
}}
QScrollBar::handle:horizontal {{
    background: {t.scrollbar}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t.scrollbar_hover}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
"""


def _menu_combo_qss(t: Theme) -> str:
    """菜单与下拉框 QSS：QMenu / QComboBox / QCheckBox"""
    return f"""
QMenu {{
    background: {t.bg_card}; border: 1px solid {t.border};
    border-radius: 8px; padding: 6px;
}}
QMenu::item {{ padding: 7px 22px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.bg_hover}; }}
QMenu::item[danger="true"] {{ color: {t.danger}; }}
QMenu::separator {{ height: 1px; background: {t.hairline}; margin: 4px 8px; }}

QComboBox {{
    background: {t.bg_input}; border: 1px solid {t.border};
    border-radius: 6px; padding: 5px 10px; min-height: 22px; color: {t.fg_primary};
}}
QComboBox:hover {{ border-color: {t.border_strong}; }}
QComboBox:focus {{ border-color: {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {t.bg_card}; border: 1px solid {t.border};
    selection-background-color: {t.bg_hover}; outline: none; padding: 4px;
}}

QCheckBox {{ spacing: 8px; color: {t.fg_primary}; }}
QCheckBox::indicator {{ width: 16px; height: 16px; }}
QCheckBox:disabled {{ color: {t.fg_muted}; }}
"""


def _panel_qss(t: Theme) -> str:
    """面板定制 QSS：添加按钮 / 列表项 / 模型行 / 分隔线 / 各类命名标签"""
    return f"""
#AddProviderBtn {{
    border: 1px dashed {t.border_strong}; color: {t.fg_secondary};
    background: transparent; border-radius: 7px;
}}
#AddProviderBtn:hover {{
    border-color: {t.fg_muted}; color: {t.fg_primary}; background: {t.bg_hover};
}}
#AddProviderBtn:pressed {{ background: {t.bg_active}; }}

#ProviderItem {{ background: transparent; border-radius: 7px; }}
#ProviderItem[hover="true"] {{ background: {t.bg_hover}; }}
#ProviderItem[selected="true"] {{ background: {t.bg_active}; }}

#ModelRow {{ background: transparent; border-radius: 6px; }}
#ModelRow:hover {{ background: {t.bg_hover}; }}

#Hairline {{ background: {t.hairline}; border: none; }}

#SectionLabel {{ color: {t.fg_muted}; }}
#FieldLabel {{ color: {t.fg_secondary}; font-size: 12px; }}
#FormLabel {{ color: {t.fg_secondary}; font-size: 12px; }}
#GroupCaption {{ color: {t.fg_muted}; font-size: 12px; }}
#CountLabel {{ color: {t.fg_muted}; font-size: 12px; }}
#CheckStatus {{ font-size: 12px; }}
#EmptyHint {{ color: {t.fg_muted}; }}
#PlaceholderText {{ color: {t.fg_muted}; font-size: 15px; }}
#ManageBar {{ background: {t.bg_card}; border-radius: 7px; }}
#OverlayLabel {{ background: {t.overlay}; color: {t.fg_muted}; font-size: 14px; }}
#KeyLinkButton {{ color: {t.accent}; font-size: 12px; }}
#KeyLinkButton:hover {{ color: {t.accent_hover}; }}
"""


def _progress_bar_qss(t: Theme) -> str:
    """进度条 QSS：8px 细条，chunk 走 accent（健康检查对话框使用）"""
    return f"""
QProgressBar {{
    background: {t.bg_input}; border: 1px solid {t.border};
    border-radius: 4px; min-height: 8px; max-height: 8px;
}}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 3px; }}
"""


def _build_palette(t: Theme) -> QPalette:
    """让 Fusion 原生绘制的部件（复选框、滚动区域等）适配当前主题

    Args:
        t: 主题 token

    Returns:
        QPalette: 适配主题的调色板（仅设置到对话框自身）
    """
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t.bg_base))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t.fg_primary))
    pal.setColor(QPalette.ColorRole.Base, QColor(t.bg_input))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t.bg_card))
    pal.setColor(QPalette.ColorRole.Text, QColor(t.fg_primary))
    pal.setColor(QPalette.ColorRole.Button, QColor(t.bg_card))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t.fg_primary))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t.accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t.accent_fg))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t.fg_muted))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.bg_card))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t.fg_primary))
    disabled = QColor(t.fg_muted)
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return pal


def _combo_arrow_qss(t: Theme) -> str:
    """运行时生成下拉箭头小三角（QSS image 需要文件路径，且离屏/部分平台下
    样式默认箭头可能退化，故自行绘制保证一致外观）。按主题色生成。"""
    pm = QPixmap(12, 8)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t.fg_secondary))
    path = QPainterPath()
    path.moveTo(1.0, 1.5)
    path.lineTo(11.0, 1.5)
    path.lineTo(6.0, 7.0)
    path.closeSubpath()
    p.drawPath(path)
    p.end()
    file_path = os.path.join(
        tempfile.gettempdir(), f"instructionx_llm_combo_arrow_{t.name}.png")
    pm.save(file_path)
    # QSS url() 只接受正斜杠路径，Windows 反斜杠会导致整表解析失败
    file_path = file_path.replace(os.sep, "/")
    return (f'QComboBox::down-arrow {{ image: url("{file_path}"); '
            f"width: 12px; height: 8px; }}")


def apply_dialog_theme(dialog: QDialog) -> Theme:
    """按应用当前主题为对话框整套换肤（不污染 QApplication 全局状态）

    流程：由 :func:`_theme_from_uikit` 从 UIKit 令牌实时构建 token ->
    更新模块级 CURRENT_THEME -> 对话框自身 setPalette ->
    对话框自身 setStyleSheet(build_qss + 下拉箭头) -> 鸭子类型遍历
    对话框内全部子控件，调用其 ``apply_theme(theme)`` 完成自绘控件换色 ->
    连接 UIKit ``theme_changed`` 信号，对话框打开期间实时跟随应用主题。

    Args:
        dialog: 目标对话框（主题只作用于它及其子树）

    Returns:
        Theme: 实际应用的主题 token
    """
    global CURRENT_THEME
    theme = _theme_from_uikit()
    CURRENT_THEME = theme
    dialog.setPalette(_build_palette(theme))
    dialog.setStyleSheet(build_qss(theme) + _combo_arrow_qss(theme))
    for widget in [dialog, *dialog.findChildren(QWidget)]:
        handler = getattr(widget, "apply_theme", None)
        if callable(handler):
            handler(theme)
    _follow_app_theme(dialog)
    return theme


def _follow_app_theme(dialog: QDialog) -> None:
    """连接 UIKit theme_changed：应用主题切换时对存活对话框重新换肤"""
    if getattr(dialog, "_uik_theme_following", False):
        return
    dialog._uik_theme_following = True

    def _reapply(*_args) -> None:
        if isValid(dialog):
            apply_dialog_theme(dialog)

    ThemeManager.instance().theme_changed.connect(_reapply)
