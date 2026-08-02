"""托盘后端注册表与 TrayIconManager 门面测试

覆盖（对应 close-to-tray-report.md §4/§6 的托盘设计）：
- 注册表/工厂：create_tray_backend("win32") 命中 WindowsTrayBackend，
  未注册平台键回退 GenericTrayBackend，缺省键取 sys.platform
- 图标激活接线：注入 activation_reasons 返回空元组的假后端时
  tray.activated 信号不接线（receivers == 0，触发不发射恢复信号）；
  非空时接线且仅命中声明原因才发射 show_main_window_requested
- 通知降级：假后端 send_notification 返回 False 时
  show_minimize_hint 不抛异常（降级为仅记日志）
- 状态子菜单：aboutToShow 动态重建——插件子菜单条目与注入回调数据一致、
  激活项勾选、点击发射 plugin_activate_requested；任务子菜单只读；
  空数据/回调异常时显示置灰占位项（MENU_NO_PLUGINS / MENU_NO_TASKS）

TrayIconManager 非单例，构造时注入假后端，不创建真实托盘驻留、
不加载插件系统。
"""

from typing import List, Tuple

import pytest

pytest.importorskip("pytestqt")

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon

from ui.tray.backend import (
    GENERIC_BACKEND_KEY, TRAY_BACKEND_REGISTRY, TrayBackend, TrayCapabilities,
    create_tray_backend,
)
from ui.tray.backends.generic import GenericTrayBackend
from ui.tray.backends.windows import WindowsTrayBackend
from ui.tray.manager import (
    MENU_NO_PLUGINS, MENU_NO_TASKS, MENU_QUIT, MENU_RUNNING_PLUGINS,
    MENU_RUNNING_TASKS, MENU_SHOW_MAIN_WINDOW, TrayIconManager,
)

# QSystemTrayIcon.activated 信号的 Qt 元对象签名（receivers() 查询用）
ACTIVATED_SIGNAL_SIGNATURE = "2activated(QSystemTrayIcon::ActivationReason)"

# 测试用插件名/任务名常量
PLUGIN_NAME_A = "插件甲"
PLUGIN_NAME_B = "插件乙"
TASK_NAME_A = "构建索引"
TASK_NAME_B = "同步数据"


@pytest.fixture(autouse=True)
def _ensure_qapp(qapp):
    """确保 QApplication 存在：创建 QSystemTrayIcon/QMenu 等 GUI 对象的前提。"""
    return qapp


@pytest.fixture(autouse=True)
def _mock_tray_logger(mocker):
    """屏蔽被测模块的日志单例。

    全局 conftest 的 mock_logger 会把 utils.logging_tools.LoggerManager
    替换为 MagicMock，而真实 LoggerManager.__new__ 内部以模块全局名
    引用自身做 super()，一旦被替换且单例尚未创建即抛 TypeError；
    此处直接在被测模块的命名空间内打桩，使被测代码完全不触碰真实单例。
    """
    logger_mock = mocker.MagicMock()
    mocker.patch("ui.tray.manager.LoggerManager", return_value=logger_mock)
    mocker.patch("ui.tray.backend.LoggerManager", return_value=logger_mock)
    return logger_mock


class FakeTrayBackend(TrayBackend):
    """可控假托盘后端：激活原因、通知结果、可用性均可注入。

    Attributes:
        notifications: 已收到的通知请求列表 [(标题, 正文), ...]
    """

    def __init__(
        self,
        reasons: Tuple[QSystemTrayIcon.ActivationReason, ...] = (),
        notification_result: bool = False,
        available: bool = True,
    ):
        self.capabilities = TrayCapabilities(
            supports_icon_activation=bool(reasons),
            supports_message=notification_result,
            message_note="假后端",
        )
        self._reasons = reasons
        self._notification_result = notification_result
        self._available = available
        self.notifications: List[Tuple[str, str]] = []

    def is_tray_available(self) -> bool:
        return self._available

    def activation_reasons(self) -> Tuple[QSystemTrayIcon.ActivationReason, ...]:
        return self._reasons

    def send_notification(self, tray, title, message) -> bool:
        self.notifications.append((title, message))
        return self._notification_result


class _FakePlugin:
    """带 plugin_name 属性的轻量假插件（子菜单条目取该属性渲染）。"""

    def __init__(self, name: str):
        self.plugin_name = name


def _make_manager(
    backend: FakeTrayBackend = None,
    plugins: list = None,
    tasks: list = None,
) -> TrayIconManager:
    """构建注入假后端的 TrayIconManager，并按需注入子菜单数据回调。

    Args:
        backend: 假托盘后端，缺省为全默认 FakeTrayBackend
        plugins: 插件子菜单数据 [(插件, 是否激活), ...]，None 表示不注入回调
        tasks: 任务子菜单数据 [(任务名, 插件名), ...]，None 表示不注入回调

    Returns:
        TrayIconManager 实例（未 show，不产生真实托盘驻留）
    """
    manager = TrayIconManager(QIcon(), backend=backend or FakeTrayBackend())
    if plugins is not None or tasks is not None:
        manager.set_status_providers(
            lambda: list(plugins or []), lambda: list(tasks or [])
        )
    return manager


# =====================================================================
# 托盘后端注册表与工厂
# =====================================================================
class TestTrayBackendRegistry:
    """注册表/工厂：win32 命中 WindowsTrayBackend，未注册平台回退兜底"""

    def test_registry_contains_win32_and_generic(self):
        """注册表含 win32 与通用兜底键，分别指向两个平台后端类"""
        assert TRAY_BACKEND_REGISTRY["win32"] is WindowsTrayBackend
        assert TRAY_BACKEND_REGISTRY[GENERIC_BACKEND_KEY] is GenericTrayBackend

    def test_create_win32_returns_windows_backend(self):
        """create_tray_backend("win32") 返回 WindowsTrayBackend 实例"""
        backend = create_tray_backend("win32")
        assert isinstance(backend, WindowsTrayBackend)
        assert backend.capabilities.supports_icon_activation is True
        assert backend.activation_reasons() == (
            QSystemTrayIcon.ActivationReason.DoubleClick,
        )

    def test_create_unregistered_platform_falls_back_to_generic(self):
        """未注册平台键（darwin/linux）回退 GenericTrayBackend（边界）"""
        for unknown_key in ("darwin", "linux"):
            backend = create_tray_backend(unknown_key)
            assert isinstance(backend, GenericTrayBackend)
            assert backend.activation_reasons() == ()
            assert backend.capabilities.supports_message is False

    def test_create_default_uses_sys_platform(self, monkeypatch):
        """缺省平台键取 sys.platform：未注册平台同样回退兜底"""
        monkeypatch.setattr("ui.tray.backend.sys.platform", "darwin")
        assert isinstance(create_tray_backend(), GenericTrayBackend)


# =====================================================================
# 图标激活接线（注入假后端）
# =====================================================================
class TestActivationWiring:
    """activated 信号接线由后端 activation_reasons 能力位驱动"""

    def test_empty_reasons_activation_not_connected(self):
        """activation_reasons 为空元组：activated 信号无任何接收者"""
        manager = _make_manager(backend=FakeTrayBackend(reasons=()))
        assert manager._tray.receivers(ACTIVATED_SIGNAL_SIGNATURE) == 0

    def test_empty_reasons_activated_emit_does_not_request_show(self):
        """空元组后端：直接发射 tray.activated 也不会请求恢复主窗口"""
        manager = _make_manager(backend=FakeTrayBackend(reasons=()))
        emitted = []
        manager.show_main_window_requested.connect(lambda: emitted.append(1))

        manager._tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)

        assert emitted == []

    def test_non_empty_reasons_connected_and_filters_reason(self):
        """非空元组后端：接线 activated，仅命中声明原因才发射恢复信号"""
        backend = FakeTrayBackend(
            reasons=(QSystemTrayIcon.ActivationReason.DoubleClick,)
        )
        manager = _make_manager(backend=backend)
        assert manager._tray.receivers(ACTIVATED_SIGNAL_SIGNATURE) == 1

        emitted = []
        manager.show_main_window_requested.connect(lambda: emitted.append(1))
        # 单击未在声明原因中：不发射
        manager._tray.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)
        assert emitted == []
        # 双击命中声明原因：发射一次
        manager._tray.activated.emit(QSystemTrayIcon.ActivationReason.DoubleClick)
        assert emitted == [1]


# =====================================================================
# 通知提示降级
# =====================================================================
class TestNotificationFallback:
    """show_minimize_hint 委托后端发送，失败仅记日志不抛异常"""

    def test_send_failure_does_not_raise(self):
        """后端 send_notification 返回 False：不抛异常，且确实委托过后端"""
        backend = FakeTrayBackend(notification_result=False)
        manager = _make_manager(backend=backend)
        manager.show_minimize_hint()  # 不应抛出
        assert len(backend.notifications) == 1

    def test_send_success_also_delegates(self):
        """后端发送成功（返回 True）同样正常返回（正常路径对照）"""
        backend = FakeTrayBackend(notification_result=True)
        manager = _make_manager(backend=backend)
        manager.show_minimize_hint()
        assert len(backend.notifications) == 1


# =====================================================================
# 顶层菜单信号
# =====================================================================
class TestTopLevelMenu:
    """顶层四项菜单结构与「显示主窗口」「退出」信号接线"""

    def test_menu_structure_and_signals(self):
        """菜单四项齐全；点击「显示主窗口」「退出」发射对应信号"""
        manager = _make_manager()
        texts = [a.text() for a in manager._menu.actions()]
        assert texts == [
            MENU_SHOW_MAIN_WINDOW, MENU_RUNNING_PLUGINS,
            MENU_RUNNING_TASKS, MENU_QUIT,
        ]

        shown, quitted = [], []
        manager.show_main_window_requested.connect(lambda: shown.append(1))
        manager.quit_requested.connect(lambda: quitted.append(1))

        manager._menu.actions()[0].trigger()
        manager._menu.actions()[3].trigger()

        assert shown == [1]
        assert quitted == [1]


# =====================================================================
# 插件状态子菜单（aboutToShow 动态重建）
# =====================================================================
class TestPluginsSubmenu:
    """插件子菜单：条目来自注入回调、激活项勾选、点击发射切换信号"""

    def test_about_to_show_rebuilds_entries_matching_provider(self):
        """aboutToShow 后条目文案/勾选态与注入回调数据一致"""
        plugin_a, plugin_b = _FakePlugin(PLUGIN_NAME_A), _FakePlugin(PLUGIN_NAME_B)
        manager = _make_manager(
            plugins=[(plugin_a, True), (plugin_b, False)], tasks=[],
        )

        manager._plugins_menu.aboutToShow.emit()

        actions = manager._plugins_menu.actions()
        assert [a.text() for a in actions] == [PLUGIN_NAME_A, PLUGIN_NAME_B]
        assert all(a.isCheckable() for a in actions)
        assert actions[0].isChecked() is True
        assert actions[1].isChecked() is False

    def test_trigger_item_emits_plugin_activate_requested(self):
        """点击插件条目发射 plugin_activate_requested，负载为该插件实例"""
        plugin_a, plugin_b = _FakePlugin(PLUGIN_NAME_A), _FakePlugin(PLUGIN_NAME_B)
        manager = _make_manager(
            plugins=[(plugin_a, True), (plugin_b, False)], tasks=[],
        )
        manager._plugins_menu.aboutToShow.emit()

        emitted = []
        manager.plugin_activate_requested.connect(emitted.append)
        manager._plugins_menu.actions()[1].trigger()

        assert emitted == [plugin_b]

    def test_empty_data_shows_disabled_placeholder(self):
        """空数据：显示置灰占位项「无已加载插件」，触发不发射任何信号（边界）"""
        manager = _make_manager(plugins=[], tasks=[])

        manager._plugins_menu.aboutToShow.emit()

        actions = manager._plugins_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == MENU_NO_PLUGINS
        assert actions[0].isEnabled() is False

        emitted = []
        manager.plugin_activate_requested.connect(emitted.append)
        actions[0].trigger()
        assert emitted == []

    def test_provider_exception_falls_back_to_placeholder(self):
        """数据回调抛异常：降级为置灰占位项，aboutToShow 不向外抛出（异常路径）"""
        def raising_provider():
            raise RuntimeError("查询失败")

        manager = _make_manager()
        manager.set_status_providers(raising_provider, lambda: [])

        manager._plugins_menu.aboutToShow.emit()  # 不应抛出

        actions = manager._plugins_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == MENU_NO_PLUGINS
        assert actions[0].isEnabled() is False

    def test_repeated_about_to_show_replaces_stale_entries(self):
        """重复 aboutToShow 全量重建：旧条目被清除，不残留过期数据"""
        plugin_a = _FakePlugin(PLUGIN_NAME_A)
        manager = _make_manager(plugins=[(plugin_a, False)], tasks=[])
        manager._plugins_menu.aboutToShow.emit()
        assert len(manager._plugins_menu.actions()) == 1

        # 数据变化后再次弹出：应按新数据重建
        plugin_b = _FakePlugin(PLUGIN_NAME_B)
        manager.set_status_providers(lambda: [(plugin_b, True)], lambda: [])
        manager._plugins_menu.aboutToShow.emit()

        actions = manager._plugins_menu.actions()
        assert [a.text() for a in actions] == [PLUGIN_NAME_B]
        assert actions[0].isChecked() is True


# =====================================================================
# 任务状态子菜单（只读）
# =====================================================================
class TestTasksSubmenu:
    """任务子菜单：只读展示（条目无触发动作），空数据置灰占位"""

    def test_about_to_show_rebuilds_readonly_entries(self):
        """aboutToShow 后条目渲染为「任务名（插件名）」，且未绑定触发动作"""
        manager = _make_manager(
            plugins=[],
            tasks=[(TASK_NAME_A, PLUGIN_NAME_A), (TASK_NAME_B, PLUGIN_NAME_B)],
        )

        manager._tasks_menu.aboutToShow.emit()

        actions = manager._tasks_menu.actions()
        assert [a.text() for a in actions] == [
            f"{TASK_NAME_A}（{PLUGIN_NAME_A}）",
            f"{TASK_NAME_B}（{PLUGIN_NAME_B}）",
        ]
        # 只读展示项：不可勾选、不携带子菜单（触发无任何效果的行为
        # 断言见 test_trigger_readonly_item_emits_nothing）
        for action in actions:
            assert action.isCheckable() is False
            assert action.menu() is None

    def test_trigger_readonly_item_emits_nothing(self):
        """强制触发只读任务条目：不发射任何门面请求信号"""
        manager = _make_manager(tasks=[(TASK_NAME_A, PLUGIN_NAME_A)])
        manager._tasks_menu.aboutToShow.emit()

        fired = []
        manager.show_main_window_requested.connect(lambda: fired.append("show"))
        manager.quit_requested.connect(lambda: fired.append("quit"))
        manager.plugin_activate_requested.connect(lambda p: fired.append("plugin"))

        manager._tasks_menu.actions()[0].trigger()

        assert fired == []

    def test_empty_data_shows_disabled_placeholder(self):
        """空数据：显示置灰占位项「无运行中的任务」（边界）"""
        manager = _make_manager(tasks=[])

        manager._tasks_menu.aboutToShow.emit()

        actions = manager._tasks_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == MENU_NO_TASKS
        assert actions[0].isEnabled() is False

    def test_provider_exception_falls_back_to_placeholder(self):
        """数据回调抛异常：降级为置灰占位项，不向外抛出（异常路径）"""
        def raising_provider():
            raise RuntimeError("存储损坏")

        manager = _make_manager()
        manager.set_status_providers(lambda: [], raising_provider)

        manager._tasks_menu.aboutToShow.emit()  # 不应抛出

        actions = manager._tasks_menu.actions()
        assert len(actions) == 1
        assert actions[0].text() == MENU_NO_TASKS
        assert actions[0].isEnabled() is False
