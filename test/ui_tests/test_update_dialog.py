"""手动检查更新对话框的 Release 列表与操作测试。"""

import importlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.framework_update.models import (
    FrameworkRelease,
    UpdateCheckResult,
    parse_release_tag,
)
from core.interfaces import TaskStatus


@pytest.fixture
def dialog_module():
    """加载待实现的检查更新对话框。"""
    return importlib.import_module("ui.dialog.update_dialog")


def _release(release_id: int, tag: str, *, prerelease: bool = True) -> FrameworkRelease:
    """构造列表用 Release。"""
    try:
        version = parse_release_tag(tag)
    except ValueError:
        version = None
    return FrameworkRelease(
        release_id=release_id,
        name=tag if version else "Nightly",
        tag_name=tag,
        version=version,
        prerelease=prerelease,
        published_at=datetime(2026, 5, release_id, tzinfo=timezone.utc),
        body=f"Notes {release_id}",
        html_url=f"https://github.com/KKPIP-Tech/InstructionX/releases/{release_id}",
    )


def _result() -> UpdateCheckResult:
    """构造最新、当前、旧版和非标准 Tag 的完整时间线。"""
    return UpdateCheckResult(
        releases=(
            _release(1, "alpha-v1.2.0"),
            _release(2, "alpha-v1.1.2"),
            _release(3, "alpha-v1.0.0"),
            _release(4, "nightly"),
        ),
        current_release_id=2,
    )


def _dialog(module, qtbot, result=None, launcher=None):
    """创建任务与网络均可控的对话框，并返回依赖替身。"""
    checker = MagicMock()
    checker.check.return_value = result or _result()
    tasks = MagicMock()
    tasks.register_async_task.return_value = "task-1"
    dialog = module.UpdateDialog(
        checker=checker,
        task_manager=tasks,
        launcher=launcher or MagicMock(),
    )
    qtbot.addWidget(dialog)
    return dialog, checker, tasks


def _finish(dialog, result=None):
    """模拟后台任务在 UI 线程交付成功结果。"""
    dialog._apply_task_result(
        "task-1", TaskStatus.COMPLETED, result or _result(), None)


class TestUpdateDialog:
    """验证 Release 时间线、当前定位和显式更新操作。"""

    def test_constructor_starts_one_manual_check(self, dialog_module, qtbot):
        """创建弹窗只注册一次检查任务，尚未返回时不伪造列表。"""
        dialog, checker, tasks = _dialog(dialog_module, qtbot)

        assert tasks.register_async_task.call_count == 1
        assert tasks.register_async_task.call_args.kwargs["func"] == checker.check
        assert dialog.release_list.count() == 0
        assert not dialog.update_button.isEnabled()

    def test_populates_all_releases_and_marks_current(self, dialog_module, qtbot):
        """全部 Release 按结果顺序展示，最新与当前版本均有标识。"""
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot)

        _finish(dialog)

        assert dialog.release_list.count() == 4
        assert "最新发布" in dialog.release_list.item(0).text()
        assert "当前版本" in dialog.release_list.item(1).text()
        assert dialog.release_list.item(1).font().bold()
        assert "无法识别版本号" in dialog.release_list.item(3).text()
        assert dialog.locate_current_button.isEnabled()

    def test_selection_controls_update_availability(self, dialog_module, qtbot):
        """只有可识别且高于当前版本的所选 Release 可更新。"""
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot)
        _finish(dialog)

        dialog.release_list.setCurrentRow(0)
        assert dialog.update_button.isEnabled()
        dialog.release_list.setCurrentRow(1)
        assert not dialog.update_button.isEnabled()
        dialog.release_list.setCurrentRow(2)
        assert not dialog.update_button.isEnabled()
        dialog.release_list.setCurrentRow(3)
        assert not dialog.update_button.isEnabled()

    def test_cancel_never_launches_and_ignores_late_result(self, dialog_module, qtbot):
        """关闭弹窗后不得启动更新，也不得接收迟到的后台结果。"""
        launcher = MagicMock()
        dialog, _checker, tasks = _dialog(dialog_module, qtbot, launcher=launcher)

        dialog.reject()
        _finish(dialog)

        tasks.cancel_task.assert_called_once_with("task-1")
        launcher.launch.assert_not_called()
        assert dialog.release_list.count() == 0

    def test_confirm_launches_selected_release_and_emits(self, dialog_module, qtbot):
        """只有点击更新按钮才启动向导并通知主窗口退出。"""
        launcher = MagicMock()
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot, launcher=launcher)
        _finish(dialog)
        started = MagicMock()
        dialog.update_started.connect(started)
        dialog.release_list.setCurrentRow(0)

        dialog.update_button.click()

        launcher.launch.assert_called_once()
        assert launcher.launch.call_args.args[0].tag_name == "alpha-v1.2.0"
        started.assert_called_once_with("alpha-v1.2.0")

    def test_launch_failure_keeps_dialog_available(self, dialog_module, qtbot):
        """向导启动失败时显示错误，不发退出信号。"""
        from core.framework_update.launcher import UpdateLaunchError

        launcher = MagicMock()
        launcher.launch.side_effect = UpdateLaunchError("无法启动")
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot, launcher=launcher)
        _finish(dialog)
        started = MagicMock()
        dialog.update_started.connect(started)

        dialog.update_button.click()

        assert "无法启动" in dialog.status_label.text()
        started.assert_not_called()
        assert dialog.result() != dialog.DialogCode.Accepted

    def test_missing_current_disables_locate(self, dialog_module, qtbot):
        """当前版本不在 Release 列表中时应说明并禁用定位。"""
        result = UpdateCheckResult(releases=(_release(1, "alpha-v1.2.0"),),
                                   current_release_id=None)
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot, result=result)

        _finish(dialog, result)

        assert not dialog.locate_current_button.isEnabled()
        assert "未出现在" in dialog.current_label.text()

    def test_locate_scrolls_to_current(self, dialog_module, qtbot):
        """定位按钮应选中当前版本所在行。"""
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot)
        _finish(dialog)

        dialog.locate_current_button.click()

        assert dialog.release_list.currentRow() == 1

    def test_open_release_uses_https_url(self, dialog_module, qtbot, mocker):
        """查看 Release 只打开该条目提供的 HTTPS 页面。"""
        dialog, _checker, _tasks = _dialog(dialog_module, qtbot)
        _finish(dialog)
        opener = mocker.patch.object(dialog_module.QDesktopServices, "openUrl")

        dialog.view_release_button.click()

        assert opener.call_args.args[0].scheme() == "https"
