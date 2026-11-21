"""手动检查更新对话框：展示完整 GitHub Release 时间线。"""

from typing import Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from core.framework_update import (
    FrameworkRelease,
    FrameworkUpdateChecker,
    UpdateCheckResult,
)
from core.framework_update.launcher import FrameworkUpdateLauncher, UpdateLaunchError
from core.i18n import tr
from core.interfaces import TaskStatus
from core.task import BackgroundTaskManager
from core.version import get_instructionx_version_string
from InstructionX_UIKit import set_property
from utils.logging_tools import LoggerManager, get_name
from utils.thread_utils import run_in_ui_thread

DIALOG_WIDTH = 860
DIALOG_HEIGHT = 680
CONTENT_MARGIN = 20
CONTENT_SPACING = 12
DETAILS_MAX_HEIGHT = 180
RELEASE_ID_ROLE = int(Qt.ItemDataRole.UserRole)
RELEASE_OBJECT_ROLE = RELEASE_ID_ROLE + 1
RELEASE_TIME_FORMAT = "%Y-%m-%d %H:%M UTC"
UPDATE_TASK_PLUGIN_ID = "__framework_update__"
UPDATE_TASK_NAME = "manual_github_release_check"


class UpdateDialog(QDialog):
    """由用户手动触发检查，并只在确认后启动所选 Release 更新。"""

    update_started = Signal(str)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        checker: Optional[FrameworkUpdateChecker] = None,
        task_manager: Optional[BackgroundTaskManager] = None,
        launcher: Optional[FrameworkUpdateLauncher] = None,
    ) -> None:
        """构建弹窗并启动一次检查；构造本对象即代表用户已点击菜单。"""
        super().__init__(parent)
        self._checker = checker or FrameworkUpdateChecker()
        self._task_manager = task_manager or BackgroundTaskManager()
        self._launcher = launcher or FrameworkUpdateLauncher()
        self._logger = LoggerManager()
        self._task_id: Optional[str] = None
        self._result: Optional[UpdateCheckResult] = None
        self._accept_results = True
        self.setWindowTitle(tr("dialog_update", "title"))
        self.setModal(True)
        self.resize(DIALOG_WIDTH, DIALOG_HEIGHT)
        self._init_ui()
        self._start_check()

    def _init_ui(self) -> None:
        """构建状态区、Release 列表、详情和操作按钮。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN, CONTENT_MARGIN)
        layout.setSpacing(CONTENT_SPACING)
        self.current_label = QLabel(self)
        self.current_label.setText(tr(
            "dialog_update", "current_version",
            version=get_instructionx_version_string()))
        layout.addWidget(self.current_label)
        self.status_label = QLabel(self)
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addLayout(self._create_tool_buttons())
        self.release_list = QListWidget(self)
        self.release_list.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.release_list, 1)
        self.release_details = QPlainTextEdit(self)
        self.release_details.setReadOnly(True)
        self.release_details.setMaximumHeight(DETAILS_MAX_HEIGHT)
        layout.addWidget(self.release_details)
        layout.addLayout(self._create_action_buttons())

    def _create_tool_buttons(self) -> QHBoxLayout:
        """创建重新检查与定位当前版本按钮。"""
        row = QHBoxLayout()
        self.retry_button = QPushButton(tr("dialog_update", "retry"), self)
        self.retry_button.clicked.connect(self._start_check)
        row.addWidget(self.retry_button)
        self.locate_current_button = QPushButton(
            tr("dialog_update", "locate_current"), self)
        self.locate_current_button.setEnabled(False)
        self.locate_current_button.clicked.connect(self._locate_current)
        row.addWidget(self.locate_current_button)
        row.addStretch(1)
        return row

    def _create_action_buttons(self) -> QHBoxLayout:
        """创建 Release 页面、更新和关闭按钮。"""
        row = QHBoxLayout()
        self.view_release_button = QPushButton(
            tr("dialog_update", "view_release"), self)
        self.view_release_button.setEnabled(False)
        self.view_release_button.clicked.connect(self._open_selected_release)
        row.addWidget(self.view_release_button)
        row.addStretch(1)
        self.update_button = QPushButton(
            tr("dialog_update", "update_selected"), self)
        self.update_button.setEnabled(False)
        set_property(self.update_button, "variant", "primary")
        self.update_button.clicked.connect(self._on_update_clicked)
        row.addWidget(self.update_button)
        self.later_button = QPushButton(tr("common", "close"), self)
        self.later_button.clicked.connect(self.reject)
        row.addWidget(self.later_button)
        return row

    def _start_check(self) -> None:
        """通过一次性后台任务检查 Release，不阻塞 UI。"""
        if self._task_id is not None:
            return
        self._accept_results = True
        self.status_label.setText(tr("dialog_update", "checking"))
        self.update_button.setEnabled(False)
        try:
            self._task_id = self._task_manager.register_async_task(
                plugin_id=UPDATE_TASK_PLUGIN_ID,
                name=UPDATE_TASK_NAME,
                func=self._checker.check,
                callback=self._on_task_callback,
            )
        except Exception as exc:
            self._show_error(str(exc))
            return
        if self._task_id is None:
            self._show_error(tr("dialog_update", "task_unavailable"))

    def _on_task_callback(self, task_id, status, result, error) -> None:
        """把工作线程结果封送到 UI 线程。"""
        run_in_ui_thread(self._apply_task_result, task_id, status, result, error)

    def _apply_task_result(self, task_id, status, result, error) -> None:
        """应用当前任务结果；关闭后或旧任务结果直接忽略。"""
        if not self._accept_results or task_id != self._task_id:
            return
        self._task_id = None
        if status is TaskStatus.COMPLETED and isinstance(result, UpdateCheckResult):
            self._show_result(result)
            return
        self._show_error(error or tr("dialog_update", "unknown_error"))

    def _show_result(self, result: UpdateCheckResult) -> None:
        """展示完整 Release 时间线及当前版本位置。"""
        self._result = result
        self._update_current_label(result)
        self._populate_releases(result)
        self._update_latest_status(result)

    def _update_current_label(self, result: UpdateCheckResult) -> None:
        """显示当前版本，并在无匹配 Release 时明确说明。"""
        version = get_instructionx_version_string()
        key = "current_version" if result.current_release_id is not None else "current_missing"
        self.current_label.setText(tr("dialog_update", key, version=version))

    def _update_latest_status(self, result: UpdateCheckResult) -> None:
        """按时间线第一项展示最新 Release 状态。"""
        latest = result.latest_release
        if latest is None:
            self.status_label.setText(tr("dialog_update", "no_releases"))
            return
        if latest.version is None:
            self.status_label.setText(tr("dialog_update", "latest_unparseable"))
            return
        key = "update_available" if result.has_update else "no_newer"
        self.status_label.setText(tr("dialog_update", key, version=latest.name))

    def _populate_releases(self, result: UpdateCheckResult) -> None:
        """按检查器给定的时间顺序填充全部 Release。"""
        self.release_list.clear()
        for index, release in enumerate(result.releases):
            item = self._create_release_item(index, release, result.current_release_id)
            self.release_list.addItem(item)
        self.locate_current_button.setEnabled(result.current_release_id is not None)
        if result.releases:
            self.release_list.setCurrentRow(0)
            return
        self.release_details.clear()
        self.update_button.setEnabled(False)
        self.view_release_button.setEnabled(False)

    def _create_release_item(
        self,
        index: int,
        release: FrameworkRelease,
        current_release_id: Optional[int],
    ) -> QListWidgetItem:
        """创建带最新、当前和 Pre-release 标识的列表项。"""
        badges = []
        if index == 0:
            badges.append(tr("dialog_update", "latest_badge"))
        if release.release_id == current_release_id:
            badges.append(tr("dialog_update", "current_badge"))
        if release.prerelease:
            badges.append(tr("dialog_update", "prerelease_badge"))
        if release.version is None:
            badges.append(tr("dialog_update", "unparseable_badge"))
        timestamp = release.published_at.strftime(RELEASE_TIME_FORMAT)
        item = QListWidgetItem(
            f"{release.name}\n{release.tag_name} · {timestamp} · {' · '.join(badges)}")
        item.setData(RELEASE_ID_ROLE, release.release_id)
        item.setData(RELEASE_OBJECT_ROLE, release)
        if release.release_id == current_release_id:
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        return item

    def _on_selection_changed(self, _current=None, _previous=None) -> None:
        """更新所选 Release 的详情和可用操作。"""
        release = self._selected_release()
        if release is None or self._result is None:
            self.update_button.setEnabled(False)
            self.view_release_button.setEnabled(False)
            return
        notes = release.body or tr("dialog_update", "no_notes")
        self.release_details.setPlainText(notes)
        self.view_release_button.setEnabled(release.html_url.startswith("https://"))
        self.update_button.setEnabled(self._result.can_update(release.release_id))

    def _selected_release(self) -> Optional[FrameworkRelease]:
        """返回当前选中的 Release，未选择时返回 None。"""
        item = self.release_list.currentItem()
        return item.data(RELEASE_OBJECT_ROLE) if item is not None else None

    def _locate_current(self) -> None:
        """滚动并选中当前版本对应的 Release 行。"""
        if self._result is None:
            return
        for row in range(self.release_list.count()):
            item = self.release_list.item(row)
            if item.data(RELEASE_ID_ROLE) == self._result.current_release_id:
                self.release_list.setCurrentItem(item)
                self.release_list.scrollToItem(item)
                return

    def _open_selected_release(self) -> None:
        """在系统浏览器中打开所选 Release 的 HTTPS 页面。"""
        release = self._selected_release()
        if release is None:
            return
        url = QUrl(release.html_url)
        if url.scheme() == "https":
            QDesktopServices.openUrl(url)

    def _on_update_clicked(self) -> None:
        """启动用户确认的更新；成功后才通知主窗口退出。"""
        release = self._selected_release()
        if release is None:
            return
        try:
            self._launcher.launch(release)
        except UpdateLaunchError as exc:
            self._logger.error(get_name(), f"启动框架更新失败: {exc}")
            self.status_label.setText(tr("dialog_update", "launch_failed", error=str(exc)))
            return
        self._accept_results = False
        self.accept()
        self.update_started.emit(release.tag_name)

    def _show_error(self, error: str) -> None:
        """展示检查失败状态并允许重试。"""
        self._logger.error(get_name(), f"检查框架更新失败: {error}")
        self._task_id = None
        self._result = None
        self.release_list.clear()
        self.release_details.clear()
        self.status_label.setText(tr("dialog_update", "check_failed", error=error))
        self.update_button.setEnabled(False)
        self.view_release_button.setEnabled(False)
        self.locate_current_button.setEnabled(False)

    def reject(self) -> None:
        """取消后忽略迟到结果，绝不启动更新。"""
        self._accept_results = False
        self._cancel_pending_task()
        super().reject()

    def _cancel_pending_task(self) -> None:
        """取消尚未完成的任务标记；网络返回由结果守卫忽略。"""
        if self._task_id is None:
            return
        try:
            self._task_manager.cancel_task(self._task_id)
        except Exception as exc:
            self._logger.warning(get_name(), f"取消检查更新任务失败: {exc}")
        self._task_id = None
