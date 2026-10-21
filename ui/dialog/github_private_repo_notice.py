"""GitHub 私有仓库显式提示组件。"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from InstructionX_UIKit import T
from InstructionX_UIKit.theme import ThemeManager
from core.i18n import tr

_TR_GROUP = "github_private_repo"


class PrivateRepositoryNotice(QFrame):
    """展示私有仓库、访问 Key 和更新绑定风险。"""

    def __init__(self, parent=None):
        """初始化提示组件。"""
        super().__init__(parent)
        self.setObjectName("githubPrivateRepoNotice")
        self._title = QLabel()
        self._title.setWordWrap(True)
        self._detail = QLabel()
        self._detail.setWordWrap(True)
        self._detail.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self._fit_pending = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._detail)
        title_font = self._title.font()
        title_font.setBold(True)
        self._title.setFont(title_font)
        self._apply_style()
        ThemeManager.instance().theme_changed.connect(self._apply_style)
        self.hide()

    def set_repository(
        self,
        repository_url: str,
        key_name: str,
        account_login: str,
    ) -> None:
        """更新私有仓库提示内容。

        Args:
            repository_url: 仓库 URL。
            key_name: 访问 Key 名称。
            account_login: Key 对应 GitHub 账号。
        """
        self._title.setText(tr(_TR_GROUP, "title"))
        identity = account_login or tr(_TR_GROUP, "unknown_account")
        self._detail.setText(tr(
            _TR_GROUP,
            "detail",
            url=repository_url,
            key_name=key_name,
            account=identity,
        ))
        self.updateGeometry()
        self.show()
        self._schedule_fit()

    def clear(self) -> None:
        """清空并隐藏提示。"""
        self._title.clear()
        self._detail.clear()
        self.setMinimumHeight(0)
        self.hide()

    def resizeEvent(self, event) -> None:
        """宽度变化后重新计算换行文本所需高度。"""
        super().resizeEvent(event)
        if self.isVisible():
            self._schedule_fit()

    def _schedule_fit(self) -> None:
        """合并同一轮布局中的高度重算请求。"""
        if self._fit_pending:
            return
        self._fit_pending = True
        QTimer.singleShot(0, self._fit_content_height)

    def _fit_content_height(self) -> None:
        """按当前宽度设置完整内容高度，避免底部文案被截断。"""
        self._fit_pending = False
        layout = self.layout()
        if layout is None:
            return
        layout.activate()
        required = layout.totalHeightForWidth(max(1, self.width()))
        if required > 0 and required != self.minimumHeight():
            self.setMinimumHeight(required)
            self.updateGeometry()

    def _apply_style(self) -> None:
        """应用 UIKit 令牌样式。"""
        self.setStyleSheet(
            f"#githubPrivateRepoNotice {{"
            f" background: {T('color.warning.subtle')};"
            f" border: 1px solid {T('color.warning')};"
            f" border-radius: {T('radius.md')}px;"
            f" }}"
            f" QLabel {{ color: {T('color.text.primary')}; }}"
        )
