"""GitHub Key 下拉弹层布局回归测试。"""

from unittest.mock import MagicMock

import pytest

from core.github import (
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubTokenKind,
)
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog


def _key_view() -> GitHubKeyView:
    """构造一个带账号名的测试 Key。"""
    return GitHubKeyView(
        id="test-key",
        name="Test",
        account_login="Ender-William",
        token_kind=GitHubTokenKind.FINE_GRAINED,
        status=GitHubKeyStatus.VALID,
        expires_at=None,
        expiration_source=GitHubExpirationSource.UNAVAILABLE,
        oauth_scopes=(),
        last_verified_at="",
        last_error_code="",
        last_error_message="",
    )


@pytest.mark.ui
def test_github_key_popup_items_do_not_overlap(qtbot) -> None:
    """弹层中相邻选项必须使用一致高度且矩形不得重叠。"""
    manager = MagicMock()
    manager.list_keys.return_value = [_key_view()]
    dialog = GitHubPluginInstallDialog(key_manager=manager)
    qtbot.addWidget(dialog)
    try:
        dialog.show()
        dialog.key_combo.showPopup()
        qtbot.wait(20)
        view = dialog.key_combo.view()
        model = dialog.key_combo.model()
        first = view.visualRect(model.index(0, 0))
        second = view.visualRect(model.index(1, 0))
        assert first.height() == second.height()
        assert second.top() >= first.bottom() + 1
    finally:
        dialog.key_combo.hidePopup()
