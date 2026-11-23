"""GitHub Key 下拉弹层选项不重叠的真实 Qt 冒烟验证。"""

import sys
from unittest.mock import MagicMock

import ui.uikit_bootstrap  # noqa: F401

from PySide6.QtWidgets import QApplication

from core.github import (
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubKeyView,
    GitHubTokenKind,
)
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog
from ui.uikit_theme import apply_uikit_theme


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


def main() -> int:
    """显示弹层并断言相邻选项矩形不重叠。"""
    app = QApplication(sys.argv)
    apply_uikit_theme(app, "light")
    manager = MagicMock()
    manager.list_keys.return_value = [_key_view()]
    dialog = GitHubPluginInstallDialog(key_manager=manager)
    try:
        dialog.show()
        dialog.key_combo.showPopup()
        app.processEvents()
        view = dialog.key_combo.view()
        model = dialog.key_combo.model()
        first = view.visualRect(model.index(0, 0))
        second = view.visualRect(model.index(1, 0))
        print(f"first={first}; second={second}")
        assert first.height() == second.height(), "选项高度不一致"
        assert second.top() >= first.bottom() + 1, "下拉选项发生重叠"
    finally:
        dialog.key_combo.hidePopup()
        dialog.close()
    print("GitHub Key ComboBox smoke passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
