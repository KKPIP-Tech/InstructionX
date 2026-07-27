# -*- coding: utf-8 -*-
"""应用全局主题入口（基于 InstructionX_UIKit 主题系统）。

本模块取代已删除的 ``utils.style_qss`` / ``utils.themes``：

- :func:`apply_uikit_theme` 是应用唯一的全局主题应用入口，支持
  ``"light" / "dark" / "auto"`` 三模式（auto 读 Windows 注册表解析一次，
  与旧行为一致）；全局 QSS = UIKit ``build_qss`` + 排除区兼容附录。
- :func:`current_theme_mode` 返回当前生效模式（"light" | "dark"）。

兼容附录（:func:`_build_compat_qss`）为三个不做 UI 迁移的区域
（CustomTitleBar / SkillsPanel / WorkArea 占位标签）保留原有选择器结构、
尺寸与字号；颜色一律实时取 UIKit 令牌 ``T()``（全局配色已统一为 UIKit
设计，不保留旧 StyleQSS 色板）。附录选择器（objectName / 类名 / 动态属性）
比 UIKit 的裸类选择器更具体，且拼接在后，同优先级下天然胜出。

注意：UIKit 的 ``ThemeManager.apply()`` 会把不带附录的 QSS 设置到
QApplication，因此本模块在每次主题变更后重新设置一次「build_qss + 附录」
的完整样式表，保证附录始终生效。
"""

import sys

from PySide6.QtWidgets import QApplication

from InstructionX_UIKit import T, build_qss
from InstructionX_UIKit.theme import ThemeManager

# ===================================================================
# 模块级常量
#: 合法主题模式（"auto" 为解析前模式，见 apply_uikit_theme）
THEME_MODES = ("light", "dark")
#: 关闭按钮 hover 的 Windows 原生红（沿用旧标题栏行为，非令牌色）
_CLOSE_HOVER_RED = "#E81123"

#: ThemeManager.apply 是否已完成首次全局应用（模块内跟踪）
_theme_applied = False


# ===================================================================
# 公开接口
def apply_uikit_theme(app: QApplication, theme: str = "auto") -> None:
    """应用 UIKit 全局主题。

    流程：auto 解析 → ``ThemeManager.set_mode``（必要时首次 ``apply``）→
    重新设置「build_qss + 兼容附录」完整样式表。

    Args:
        app: QApplication 实例
        theme: 主题模式，``"light"``、``"dark"`` 或 ``"auto"``
            （auto 读取 Windows 注册表检测一次，解析失败回退 light）

    Raises:
        ValueError: theme 不是合法模式时抛出
    """
    global _theme_applied
    if theme == "auto":
        theme = detect_system_theme()
    if theme not in THEME_MODES:
        raise ValueError(f"未知主题模式: {theme!r}，应为 {THEME_MODES} 之一")

    manager = ThemeManager.instance()
    if not _theme_applied:
        manager.apply(app)
        _theme_applied = True
    if manager.mode != theme:
        manager.set_mode(theme)

    # ThemeManager.apply/set_mode 设置的样式表不含兼容附录，统一在此覆盖
    app.setStyleSheet(build_qss(manager.tokens) + _build_compat_qss())


def current_theme_mode() -> str:
    """返回当前生效的主题模式（"light" | "dark"）。

    供需要按模式选择资源的代码使用（如 llm_settings 对话框主题）。
    """
    return ThemeManager.instance().mode


def detect_system_theme() -> str:
    """检测 Windows 系统主题（读注册表 AppsUseLightTheme）。

    Returns:
        "dark" 或 "light"；非 Windows 或读取失败时回退 "light"
    """
    if sys.platform == "win32":
        try:
            import winreg  # noqa: PLC0415  # 仅 Windows 存在的标准库模块，故延迟导入
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            winreg.CloseKey(key)
            return "dark" if value == 0 else "light"
        except OSError:
            pass
    return "light"


# ===================================================================
# 排除区兼容附录
def _build_compat_qss() -> str:
    """生成排除区（标题栏 / 技能面板 / 工作区占位）兼容 QSS。"""
    return "\n".join((
        _compat_titlebar_qss(),
        _compat_skills_panel_qss(),
        _compat_misc_qss(),
    ))


def _compat_titlebar_qss() -> str:
    """CustomTitleBar 选择器（结构沿用旧 titlebar.qss，颜色取 UIKit 令牌）。"""
    return f"""
/* ==================== 兼容：CustomTitleBar ==================== */
CustomTitleBar {{
    background-color: transparent;
}}
QLabel#titleLogo {{
    background-color: transparent;
    border-radius: 3px;
}}
QLabel#titleText {{
    color: {T("color.text.primary")};
    background: transparent;
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    font-weight: 600;
    padding-right: 10px;
}}
QMenuBar#titleMenuBar {{
    background: transparent;
    color: {T("color.text.primary")};
    border: none;
    padding: 0px;
    font-size: 14px;
}}
QMenuBar#titleMenuBar::item {{
    background: transparent;
    padding: 8px 14px;
    border-radius: 4px;
}}
QMenuBar#titleMenuBar::item:selected {{
    background-color: {T("color.bg.muted")};
}}
QPushButton#btnMinimize,
QPushButton#btnMaximize,
QPushButton#btnClose {{
    background-color: transparent;
    color: {T("color.text.primary")};
    border: none;
    border-radius: 0px;
    font-size: 12px;
    font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
    padding: 0px;
    margin: 0px;
    min-width: 40px; max-width: 40px; width: 40px;
    min-height: 40px; max-height: 40px; height: 40px;
}}
QPushButton#btnMinimize:hover,
QPushButton#btnMaximize:hover {{
    background-color: {T("color.bg.muted")};
}}
QPushButton#btnClose:hover {{
    background-color: {_CLOSE_HOVER_RED};
    color: white;
}}
QWidget#windowControls {{
    background: transparent;
}}
"""


def _compat_skills_panel_qss() -> str:
    """SkillsPanel / SkillButton 选择器（结构沿用旧 custom.qss，颜色取令牌）。"""
    panel_bg = T("color.bg.subtle")
    accent = T("color.primary")
    selected = T("color.primary.subtle")
    active_text = T("color.primary")
    active_gradient = (
        f"qlineargradient(x1:0, y1:0, x2:1, y2:0,"
        f" stop:0 {accent}, stop:0.04 {accent},"
        f" stop:0.04 {selected}, stop:1 {selected})"
    )
    expanded_gradient = (
        f"qlineargradient(x1:1, y1:0, x2:0, y2:0,"
        f" stop:0 {accent}, stop:0.04 {accent},"
        f" stop:0.04 {selected}, stop:1 {selected})"
    )
    return f"""
/* ==================== 兼容：SkillsPanel ==================== */
SkillsPanel {{
    background-color: {panel_bg};
    border-bottom: 1px solid {T("color.border")};
}}
SkillsPanel QWidget#skillsPanelHeader {{
    background-color: {panel_bg};
}}
SkillsPanel QWidget#skillsPillContainer {{
    background-color: {T("color.bg.muted")};
    border-radius: 12px;
}}
SkillsPanel QPushButton#skillsPillButton {{
    background-color: transparent;
    color: {T("color.text.secondary")};
    border: none;
    border-radius: 9px;
    padding: 2px 12px;
    min-height: 18px;
    max-height: 18px;
    font-size: 12px;
    font-weight: 500;
}}
SkillsPanel QPushButton#skillsPillButton:hover {{
    background-color: {T("color.bg.muted")};
}}
SkillsPanel QPushButton#skillsPillButton[active="true"] {{
    background-color: {accent};
    color: {T("color.on.primary")};
}}
SkillsPanel QPushButton#skillsPillButton[active="true"]:hover {{
    background-color: {T("color.primary.hover")};
}}
SkillsPanel QLabel#skillsSeparator {{
    color: {T("color.border")};
    font-size: 12px;
    background: transparent;
}}
SkillsPanel QLabel#skillsCountLabel {{
    color: {T("color.text.secondary")};
    font-size: 11px;
    background: transparent;
}}
SkillsPanel QScrollArea {{
    border: none;
    background: {panel_bg};
}}
SkillsPanel QScrollBar:horizontal {{
    height: 8px;
    background: transparent;
    margin: 0px;
}}
SkillsPanel QScrollBar::handle:horizontal {{
    background: {T("color.border.strong")};
    border-radius: 4px;
    min-width: 30px;
}}
SkillsPanel QScrollBar::handle:horizontal:hover {{
    background: {T("color.text.tertiary")};
}}
SkillsPanel QScrollBar::add-line:horizontal,
SkillsPanel QScrollBar::sub-line:horizontal {{
    width: 0px;
    background: none;
}}
SkillsPanel QScrollBar::add-page:horizontal,
SkillsPanel QScrollBar::sub-page:horizontal {{
    background: none;
}}
SkillsPanel QWidget#skillsContainer {{
    background-color: {panel_bg};
}}

/* ==================== 兼容：SkillButton ==================== */
SkillButton {{
    border: none;
    border-radius: 8px;
    padding: 2px;
    background-color: transparent;
    color: {T("color.text.primary")};
    text-align: top;
    font-size: 10px;
}}
SkillButton:hover {{
    background-color: {T("color.primary.subtle")};
    border: none;
}}
SkillButton:pressed {{
    background-color: {T("color.border")};
    border: none;
}}
SkillButton[active="true"] {{
    background: {active_gradient};
    border: none;
    border-radius: 8px;
    color: {active_text};
    text-align: top;
    font-weight: 500;
    font-size: 10px;
    padding: 2px;
}}
SkillButton[active="true"]:hover {{
    background: {active_gradient};
    border: none;
    padding: 2px;
}}
SkillButton#skillGroupButton[expanded="true"] {{
    background: {expanded_gradient};
    border: none;
    border-radius: 8px;
    color: {active_text};
    text-align: top;
    font-weight: 500;
    font-size: 10px;
    padding: 2px;
}}
SkillButton#skillGroupButton[expanded="true"]:hover {{
    background: {expanded_gradient};
    border: none;
    padding: 2px;
}}
"""


def _compat_misc_qss() -> str:
    """WorkArea 占位标签与主窗口错误标签选择器（沿用旧 label.qss 片段）。"""
    return f"""
/* ==================== 兼容：占位 / 错误标签 ==================== */
QLabel[placeholder="true"] {{
    color: {T("color.text.tertiary")};
    font-size: 12px;
}}
QLabel[error="true"] {{
    color: {T("color.danger")};
}}
"""
