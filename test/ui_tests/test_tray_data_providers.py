"""主窗口托盘子菜单数据回调与「最小化到托盘」降级路径测试

覆盖（对应 close-to-tray-report.md §6 pytest 计划中的数据回调部分）：
- _collect_running_plugins：返回全部已加载插件、_active_plugin 激活标记
  （含未激活时全 False 的边界）、查询异常返回空列表
- _collect_running_tasks：一次性任务仅保留 RUNNING/PENDING、
  长期任务按 current_status == "running" 合并、管理器未创建返回空列表、
  查询异常返回空列表
- _resolve_plugin_name：UUID → 显示名解析、未知 UUID 回退、空 UUID 占位文案
- _minimize_to_tray：托盘不可用时降级 showMinimized（不 hide、不弹通知）、
  可用时 hide + 托盘 show + 弹最小化提示

主窗口经 mock 构建（SkillsPanel/WorkArea/PluginManager/DataProvider/
TrayIconManager 均替换为 Mock，不加载真实插件、不创建真实托盘图标），
任务对象直接用 dataclass 构造，不起真实线程。
"""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("pytestqt")

from core.interfaces import TaskStatus
from core.task.background_task import (
    BackgroundTaskManager,
    LONG_TASK_STATUS_RESTARTING,
    LONG_TASK_STATUS_RUNNING,
    LONG_TASK_STATUS_STOPPED,
)
from core.task.task_model import BackgroundTask, LongRunningTask
from ui.main_window import UNKNOWN_PLUGIN_NAME

# 测试用数据常量
PLUGIN_NAME_A = "插件甲"
PLUGIN_NAME_B = "插件乙"
PLUGIN_ID_KNOWN = "uuid-known"
PLUGIN_ID_UNKNOWN = "uuid-unknown"
TASK_NAME_RUNNING = "执行中任务"
TASK_NAME_PENDING = "待执行任务"
TASK_NAME_COMPLETED = "已完成任务"
TASK_NAME_FAILED = "已失败任务"
TASK_NAME_CANCELLED = "已取消任务"
LONG_TASK_NAME_RUNNING = "运行中长期任务"
LONG_TASK_NAME_STOPPED = "已停止长期任务"


@pytest.fixture(autouse=True)
def _reset_task_manager_singleton():
    """测试后重置 BackgroundTaskManager 单例（项目既有约定）。"""
    yield
    BackgroundTaskManager._instance = None
    BackgroundTaskManager._initialized = False


def _make_window(mocker, qtbot):
    """构建重依赖全 Mock 的主窗口（不加载真实插件、不创建真实托盘）。

    Returns:
        InstructionXMainWindow 实例（plugin_manager/_tray_manager 均为 MagicMock）
    """
    mocker.patch("ui.main_window.SkillsPanel")
    mocker.patch("ui.main_window.WorkArea")
    mocker.patch("ui.main_window.DataProvider")
    mocker.patch("ui.main_window.PluginManager")
    mocker.patch("ui.main_window.TrayIconManager")

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, "_load_saved_theme"):
        with patch.object(InstructionXMainWindow, "_create_menus"):
            with patch.object(InstructionXMainWindow, "_create_main_layout"):
                window = InstructionXMainWindow()
    qtbot.addWidget(window)
    return window


def _install_task_manager(tasks, long_tasks) -> MagicMock:
    """以 MagicMock 伪装 BackgroundTaskManager 单例，注入给定任务数据。

    Args:
        tasks: get_all_tasks() 返回的一次性任务列表
        long_tasks: get_long_running_tasks() 返回的长期任务列表

    Returns:
        伪装的管理器实例（便于追加断言）
    """
    manager = MagicMock()
    manager.get_all_tasks.return_value = tasks
    manager.get_long_running_tasks.return_value = long_tasks
    BackgroundTaskManager._instance = manager
    return manager


# =====================================================================
# _collect_running_plugins
# =====================================================================
class TestCollectRunningPlugins:
    """_collect_running_plugins：全量返回、激活标记、异常兜底"""

    def test_returns_all_plugins_with_active_marked(self, mocker, qtbot):
        """返回全部已加载插件，仅当前激活插件标记为 True"""
        window = _make_window(mocker, qtbot)
        plugin_a = MagicMock()
        plugin_b = MagicMock()
        plugin_c = MagicMock()
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_all_plugins.return_value = [
            plugin_a, plugin_b, plugin_c,
        ]
        window._active_plugin = plugin_b

        result = window._collect_running_plugins()

        assert result == [(plugin_a, False), (plugin_b, True), (plugin_c, False)]
        # 结果中恰好只有一个激活标记
        assert sum(1 for _, is_active in result if is_active) == 1

    def test_no_active_plugin_marks_all_false(self, mocker, qtbot):
        """未激活任何插件（_active_plugin 为 None）时全部标记为 False（边界）"""
        window = _make_window(mocker, qtbot)
        plugin_a = MagicMock()
        plugin_b = MagicMock()
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_all_plugins.return_value = [plugin_a, plugin_b]
        window._active_plugin = None

        result = window._collect_running_plugins()

        assert result == [(plugin_a, False), (plugin_b, False)]

    def test_no_plugins_loaded_returns_empty(self, mocker, qtbot):
        """无已加载插件时返回空列表（边界）"""
        window = _make_window(mocker, qtbot)
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_all_plugins.return_value = []
        window._active_plugin = None

        assert window._collect_running_plugins() == []

    def test_exception_returns_empty_list(self, mocker, qtbot):
        """查询抛异常时记 WARNING 并返回空列表，不向外抛出（异常路径）"""
        window = _make_window(mocker, qtbot)
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_all_plugins.side_effect = RuntimeError("查询失败")

        assert window._collect_running_plugins() == []


# =====================================================================
# _resolve_plugin_name
# =====================================================================
class TestResolvePluginName:
    """_resolve_plugin_name：UUID → 显示名解析与回退"""

    def test_resolves_known_id_to_display_name(self, mocker, qtbot):
        """已知插件 UUID 解析为插件显示名"""
        window = _make_window(mocker, qtbot)
        plugin = MagicMock()
        plugin.plugin_name = PLUGIN_NAME_A
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_plugin_by_id.return_value = plugin

        assert window._resolve_plugin_name(PLUGIN_ID_KNOWN) == PLUGIN_NAME_A
        window.plugin_manager.get_plugin_by_id.assert_called_once_with(
            PLUGIN_ID_KNOWN
        )

    def test_unknown_id_falls_back_to_id_itself(self, mocker, qtbot):
        """无法解析的 UUID 回退为 UUID 本身"""
        window = _make_window(mocker, qtbot)
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_plugin_by_id.return_value = None

        assert window._resolve_plugin_name(PLUGIN_ID_UNKNOWN) == PLUGIN_ID_UNKNOWN

    def test_empty_id_returns_placeholder(self, mocker, qtbot):
        """空 UUID 返回占位文案「未知插件」（边界）"""
        window = _make_window(mocker, qtbot)
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_plugin_by_id.return_value = None

        assert window._resolve_plugin_name("") == UNKNOWN_PLUGIN_NAME


# =====================================================================
# _collect_running_tasks
# =====================================================================
class TestCollectRunningTasks:
    """_collect_running_tasks：状态过滤、长期任务合并、异常兜底"""

    def _make_window_with_plugin_names(self, mocker, qtbot):
        """构建主窗口，插件名解析固定返回 PLUGIN_NAME_A。"""
        window = _make_window(mocker, qtbot)
        plugin = MagicMock()
        plugin.plugin_name = PLUGIN_NAME_A
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_plugin_by_id.return_value = plugin
        return window

    def test_keeps_only_running_and_pending_tasks(self, mocker, qtbot):
        """一次性任务仅保留 RUNNING/PENDING，其余终态全部过滤"""
        window = self._make_window_with_plugin_names(mocker, qtbot)
        tasks = [
            BackgroundTask(
                name=TASK_NAME_RUNNING, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.RUNNING,
            ),
            BackgroundTask(
                name=TASK_NAME_PENDING, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.PENDING,
            ),
            BackgroundTask(
                name=TASK_NAME_COMPLETED, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.COMPLETED,
            ),
            BackgroundTask(
                name=TASK_NAME_FAILED, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.FAILED,
            ),
            BackgroundTask(
                name=TASK_NAME_CANCELLED, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.CANCELLED,
            ),
        ]
        _install_task_manager(tasks, [])

        result = window._collect_running_tasks()

        assert result == [
            (TASK_NAME_RUNNING, PLUGIN_NAME_A),
            (TASK_NAME_PENDING, PLUGIN_NAME_A),
        ]

    def test_merges_running_long_tasks_after_normal_tasks(self, mocker, qtbot):
        """长期任务按 current_status == "running" 合并，排在一次性任务之后"""
        window = self._make_window_with_plugin_names(mocker, qtbot)
        tasks = [
            BackgroundTask(
                name=TASK_NAME_RUNNING, plugin_id=PLUGIN_ID_KNOWN,
                status=TaskStatus.RUNNING,
            ),
        ]
        long_tasks = [
            LongRunningTask(
                name=LONG_TASK_NAME_RUNNING, plugin_id=PLUGIN_ID_KNOWN,
                current_status=LONG_TASK_STATUS_RUNNING,
            ),
            LongRunningTask(
                name=LONG_TASK_NAME_STOPPED, plugin_id=PLUGIN_ID_KNOWN,
                current_status=LONG_TASK_STATUS_STOPPED,
            ),
            LongRunningTask(
                name="重启中长期任务", plugin_id=PLUGIN_ID_KNOWN,
                current_status=LONG_TASK_STATUS_RESTARTING,
            ),
        ]
        _install_task_manager(tasks, long_tasks)

        result = window._collect_running_tasks()

        assert result == [
            (TASK_NAME_RUNNING, PLUGIN_NAME_A),
            (LONG_TASK_NAME_RUNNING, PLUGIN_NAME_A),
        ]

    def test_unresolvable_plugin_id_falls_back_to_id(self, mocker, qtbot):
        """任务所属插件 UUID 无法解析时，名称回退为 UUID 本身"""
        window = _make_window(mocker, qtbot)
        window.plugin_manager = MagicMock()
        window.plugin_manager.get_plugin_by_id.return_value = None
        tasks = [
            BackgroundTask(
                name=TASK_NAME_RUNNING, plugin_id=PLUGIN_ID_UNKNOWN,
                status=TaskStatus.RUNNING,
            ),
        ]
        _install_task_manager(tasks, [])

        result = window._collect_running_tasks()

        assert result == [(TASK_NAME_RUNNING, PLUGIN_ID_UNKNOWN)]

    def test_no_manager_instance_returns_empty(self, mocker, qtbot):
        """BackgroundTaskManager 尚未创建（_instance 为 None）时返回空列表（边界）"""
        window = _make_window(mocker, qtbot)
        BackgroundTaskManager._instance = None

        assert window._collect_running_tasks() == []

    def test_exception_returns_empty_list(self, mocker, qtbot):
        """查询抛异常时记 WARNING 并返回空列表，不向外抛出（异常路径）"""
        window = _make_window(mocker, qtbot)
        manager = MagicMock()
        manager.get_all_tasks.side_effect = RuntimeError("存储损坏")
        BackgroundTaskManager._instance = manager

        assert window._collect_running_tasks() == []


# =====================================================================
# _minimize_to_tray
# =====================================================================
class TestMinimizeToTray:
    """_minimize_to_tray：托盘可用/不可用两条路径"""

    def test_unavailable_tray_degrades_to_show_minimized(
        self, mocker, qtbot, monkeypatch
    ):
        """托盘不可用时降级 showMinimized：不 hide、不显示托盘、不弹通知"""
        window = _make_window(mocker, qtbot)
        monkeypatch.setattr(
            window._tray_manager, "is_tray_available", lambda: False
        )
        hide_spy = mocker.patch.object(window, "hide")
        minimize_spy = mocker.patch.object(window, "showMinimized")

        window._minimize_to_tray()

        minimize_spy.assert_called_once()
        hide_spy.assert_not_called()
        window._tray_manager.show.assert_not_called()
        window._tray_manager.show_minimize_hint.assert_not_called()

    def test_available_tray_hides_window_and_shows_notification(
        self, mocker, qtbot, monkeypatch
    ):
        """托盘可用时 hide 主窗口 + 托盘 show + 弹最小化提示，不走降级最小化"""
        window = _make_window(mocker, qtbot)
        monkeypatch.setattr(
            window._tray_manager, "is_tray_available", lambda: True
        )
        hide_spy = mocker.patch.object(window, "hide")
        minimize_spy = mocker.patch.object(window, "showMinimized")

        window._minimize_to_tray()

        hide_spy.assert_called_once()
        minimize_spy.assert_not_called()
        window._tray_manager.show.assert_called_once()
        window._tray_manager.show_minimize_hint.assert_called_once()
