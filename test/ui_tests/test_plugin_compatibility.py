"""插件兼容性摘要与确认组件测试。"""

import importlib
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QDialog

from core.plugin.framework_compatibility import evaluate_framework_compatibility


CURRENT = "alpha.1.1.2"


def _result(versions, invalid_entries=()):
    """使用当前版本构造真实评估结果。"""
    descriptor = {"compatible_framework_versions": versions}
    result = evaluate_framework_compatibility(descriptor)
    if invalid_entries:
        assert result.invalid_entries == invalid_entries
    return result


def _fake_tr(_group, key, **values):
    """提供不依赖用户本机语言设置的固定中文文案。"""
    texts = {
        "summary.current": "当前 InstructionX 框架：{version}",
        "summary.declared": "作者声明已验证：{versions}",
        "summary.no_declared": "作者未声明已验证的框架版本",
        "summary.invalid_entries": "非法声明项：{entries}",
        "status.verified": "当前版本已包含在兼容性验证声明中。",
        "status.missing": "未提供兼容框架版本声明，兼容性未经验证。",
        "status.not_listed": "当前版本未列入声明，兼容性未经验证。",
        "status.invalid": "兼容性声明格式无效，兼容性未经验证。",
        "confirm.title": "插件兼容性未经验证",
        "confirm.risk": "继续安装不能得到兼容保证。仍要安装吗？",
        "confirm.install_anyway": "仍然安装",
        "cancel": "取消",
    }
    return texts.get(key, key).format(**values)


@pytest.fixture
def compatibility_ui(monkeypatch):
    """加载待实现的界面辅助模块并固定文案。"""
    module = importlib.import_module("ui.dialog.plugin_compatibility")
    monkeypatch.setattr(module, "tr", _fake_tr)
    return module


def test_summary_shows_all_author_verified_versions(compatibility_ui):
    """合法声明必须展示完整版本列表和当前框架版本。"""
    result = _result(["alpha.1.1.0", CURRENT])

    text = compatibility_ui.format_compatibility_summary(result)

    assert "alpha.1.1.0" in text and CURRENT in text
    assert "当前版本已包含" in text


def test_summary_marks_current_not_listed_as_unverified(compatibility_ui):
    """当前版本未列入时展示声明列表和未验证状态。"""
    result = _result(["alpha.1.0.0"])

    text = compatibility_ui.format_compatibility_summary(result)

    assert "alpha.1.0.0" in text
    assert "未列入" in text and "未经验证" in text


def test_summary_reports_invalid_entries(compatibility_ui):
    """非法声明应展示具体非法项，且不得显示为已验证。"""
    result = _result([CURRENT, "bad-version"], ("bad-version",))

    text = compatibility_ui.format_compatibility_summary(result)

    assert "bad-version" in text
    assert "格式无效" in text and "当前版本已包含" not in text


def test_verified_items_do_not_open_risk_confirmation(compatibility_ui):
    """全部已验证时无需额外风险确认。"""
    dialog_factory = MagicMock()

    accepted = compatibility_ui.confirm_unverified_compatibility(
        None, [("Demo", _result([CURRENT]))], dialog_factory=dialog_factory)

    assert accepted is True
    dialog_factory.assert_not_called()


def test_unverified_confirmation_allows_cancel_and_force_install(compatibility_ui):
    """未验证提示必须同时提供取消和明确的强制安装入口。"""
    dialog = MagicMock()
    dialog.exec.return_value = QDialog.DialogCode.Rejected
    dialog_factory = MagicMock(return_value=dialog)
    items = [("Legacy", None)]

    cancelled = compatibility_ui.confirm_unverified_compatibility(
        None, items, dialog_factory=dialog_factory)
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    accepted = compatibility_ui.confirm_unverified_compatibility(
        None, items, dialog_factory=dialog_factory)

    assert cancelled is False and accepted is True
    assert dialog_factory.call_args.kwargs["ok_text"] == "仍然安装"
    assert dialog_factory.call_args.kwargs["cancel_text"] == "取消"
    assert "不能得到兼容保证" in dialog.set_text.call_args.args[0]


def test_release_confirmation_keeps_base_text_and_uses_force_button(compatibility_ui):
    """Release 确认页保留升级信息，未验证时使用强制安装按钮。"""
    dialog = MagicMock()
    dialog.exec.return_value = QDialog.DialogCode.Accepted
    dialog_factory = MagicMock(return_value=dialog)

    accepted = compatibility_ui.confirm_installation_with_compatibility(
        None, "确认升级", "Demo: 1.0 -> 2.0", _result(["alpha.1.0.0"]),
        dialog_factory=dialog_factory)

    assert accepted is True
    assert "Demo: 1.0 -> 2.0" in dialog.set_text.call_args.args[0]
    assert "alpha.1.0.0" in dialog.set_text.call_args.args[0]
    assert dialog_factory.call_args.kwargs["ok_text"] == "仍然安装"
