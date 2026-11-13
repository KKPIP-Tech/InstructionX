"""插件框架兼容性摘要与安装确认的统一界面辅助。"""

from typing import Callable, Optional, Sequence, Tuple

from PySide6.QtWidgets import QDialog, QWidget

from core.i18n import tr
from core.plugin.framework_compatibility import (
    FrameworkCompatibility,
    FrameworkCompatibilityStatus,
    evaluate_framework_compatibility,
)
from InstructionX_UIKit.components import Dialog


_I18N_GROUP = "dialog_plugin_compatibility"
CompatibilityItem = Tuple[str, Optional[FrameworkCompatibility]]
DialogFactory = Callable[..., Dialog]
_STATUS_KEYS = {
    FrameworkCompatibilityStatus.VERIFIED: "status.verified",
    FrameworkCompatibilityStatus.MISSING_DECLARATION: "status.missing",
    FrameworkCompatibilityStatus.CURRENT_NOT_LISTED: "status.not_listed",
    FrameworkCompatibilityStatus.INVALID_DECLARATION: "status.invalid",
}


def format_compatibility_summary(
    compatibility: Optional[FrameworkCompatibility],
) -> str:
    """格式化当前版本、作者声明列表及匹配状态。

    Args:
        compatibility: 评估结果；None 表示旧调用方未提供字段。

    Returns:
        可直接用于标签或确认对话框的多行文本。
    """
    result = _normalize(compatibility)
    declared = ", ".join(result.declared_versions)
    declared_text = (
        tr(_I18N_GROUP, "summary.declared", versions=declared)
        if declared else tr(_I18N_GROUP, "summary.no_declared")
    )
    lines = [
        tr(_I18N_GROUP, "summary.current", version=result.current_version),
        declared_text,
        tr(_I18N_GROUP, _STATUS_KEYS[result.status]),
    ]
    if result.invalid_entries:
        entries = ", ".join(result.invalid_entries)
        lines.append(tr(_I18N_GROUP, "summary.invalid_entries", entries=entries))
    return "\n".join(lines)


def confirm_unverified_compatibility(
    parent: Optional[QWidget],
    items: Sequence[CompatibilityItem],
    dialog_factory: Optional[DialogFactory] = None,
) -> bool:
    """仅在存在未验证项时请求确认，允许用户取消或强制安装。"""
    unverified = [(name, _normalize(result)) for name, result in items
                  if not _normalize(result).is_verified]
    if not unverified:
        return True
    details = "\n\n".join(
        f"{name}\n{format_compatibility_summary(result)}"
        for name, result in unverified
    )
    text = f"{details}\n\n{tr(_I18N_GROUP, 'confirm.risk')}"
    return _exec_dialog(
        parent, tr(_I18N_GROUP, "confirm.title"), text,
        tr(_I18N_GROUP, "confirm.install_anyway"), dialog_factory,
    )


def confirm_installation_with_compatibility(
    parent: Optional[QWidget],
    title: str,
    text: str,
    compatibility: Optional[FrameworkCompatibility],
    dialog_factory: Optional[DialogFactory] = None,
) -> bool:
    """在既有安装确认中附加兼容摘要，并选择适当的确认按钮。"""
    result = _normalize(compatibility)
    content = f"{text}\n\n{format_compatibility_summary(result)}"
    ok_text = "确定"
    if not result.is_verified:
        content += f"\n\n{tr(_I18N_GROUP, 'confirm.risk')}"
        ok_text = tr(_I18N_GROUP, "confirm.install_anyway")
    return _exec_dialog(parent, title, content, ok_text, dialog_factory)


def _normalize(compatibility: Optional[FrameworkCompatibility]) -> FrameworkCompatibility:
    """把旧调用方缺失的结果转换为缺字段判定。"""
    return compatibility or evaluate_framework_compatibility({})


def _exec_dialog(
    parent: Optional[QWidget],
    title: str,
    text: str,
    ok_text: str,
    dialog_factory: Optional[DialogFactory],
) -> bool:
    """构造并执行实际对话框，接受时返回 True。"""
    factory = dialog_factory or Dialog
    dialog = factory(
        parent,
        title=title,
        ok_text=ok_text,
        cancel_text=tr("common", "cancel"),
    )
    dialog.set_text(text)
    return dialog.exec() == QDialog.DialogCode.Accepted
