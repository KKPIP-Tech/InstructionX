"""系统托盘管理器门面

TrayIconManager 封装托盘图标、右键菜单与恢复/退出信号，
平台差异全部委托给 TrayBackend，本类不出现任何 sys.platform 判断。

托盘菜单四项（决策见 close-to-tray-report.md §7）：
    - 显示主窗口
    - 正在运行的插件（子菜单，aboutToShow 时动态重建，点击切换插件）
    - 后台正在运行的任务（子菜单，aboutToShow 时动态重建，只读展示）
    - 退出

两个运行状态子菜单的数据来源由主窗口经 set_status_providers 注入，
门面不直接依赖 PluginManager / BackgroundTaskManager，保持可测试性。
"""

from typing import Callable, List, Optional, Tuple

# ===================================================================
# PySide 相关
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

# ===================================================================
# 本地
from core.i18n import get_language_manager, tr
from ui.tray import backends as _tray_backends  # noqa: F401  # 触发后端注册
from ui.tray.backend import TrayBackend, create_tray_backend
from utils.logging_tools import LoggerManager, get_name

# 菜单与通知文案均经 i18n 子系统取词（分组 tray），在使用处调用 tr()，
# 不做模块级固化，保证语言切换后可刷新

# 插件子菜单数据条目类型：(插件实例, 是否当前激活)
PluginStatusEntry = Tuple[object, bool]
# 任务子菜单数据条目类型：(任务名, 所属插件名)
TaskStatusEntry = Tuple[str, str]


class TrayIconManager(QObject):
    """系统托盘管理器门面：托盘图标、右键菜单与恢复/退出信号的封装。

    Signals:
        show_main_window_requested: 请求显示主窗口（菜单项或图标激活）
        quit_requested: 请求真正退出程序（托盘菜单「退出」）
        plugin_activate_requested(object): 请求恢复主窗口并切换到指定插件
    """

    show_main_window_requested = Signal()
    quit_requested = Signal()
    plugin_activate_requested = Signal(object)

    def __init__(
        self,
        icon: QIcon,
        backend: Optional[TrayBackend] = None,
        parent: Optional[QObject] = None,
    ):
        """初始化托盘管理器。

        Args:
            icon: 托盘图标（通常为应用 logo）
            backend: 平台后端，可注入便于测试；缺省时按当前平台经工厂创建
            parent: Qt 父对象
        """
        super().__init__(parent)
        self._logger = LoggerManager()
        self._backend = backend if backend is not None else create_tray_backend()
        self._plugins_provider: Optional[Callable[[], List[PluginStatusEntry]]] = None
        self._tasks_provider: Optional[Callable[[], List[TaskStatusEntry]]] = None

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(tr("tray", "tooltip"))
        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._connect_activation()
        # 托盘为长生命周期组件，语言切换后需显式重译菜单与提示文案
        get_language_manager().language_changed.connect(self._retranslate_ui)

    # ===============================================================
    # 对外 API
    def show(self) -> None:
        """显示托盘图标。"""
        self._tray.show()

    def hide(self) -> None:
        """移除托盘图标（退出时调用，避免通知区域残留幽灵图标）。"""
        self._tray.hide()

    def is_tray_available(self) -> bool:
        """检测当前桌面环境的托盘可用性（委托后端）。

        Returns:
            托盘可用返回 True；主窗口据此决定「最小化到托盘」是否降级
        """
        return self._backend.is_tray_available()

    def show_minimize_hint(self) -> None:
        """最小化到托盘的通知提示（每次都弹，发送失败仅记日志）。"""
        sent = self._backend.send_notification(
            self._tray,
            tr("tray", "notify.minimize_title"),
            tr("tray", "notify.minimize_message"),
        )
        if not sent:
            self._logger.info(
                get_name(),
                f"托盘通知未发送（{self._backend.capabilities.message_note or '渠道不可用'}），"
                "不影响托盘驻留功能",
            )

    def set_status_providers(
        self,
        plugins_provider: Callable[[], List[PluginStatusEntry]],
        tasks_provider: Callable[[], List[TaskStatusEntry]],
    ) -> None:
        """注入两个运行状态子菜单的数据来源回调（由主窗口提供）。

        Args:
            plugins_provider: 返回 [(插件实例, 是否当前激活), ...] 的回调
            tasks_provider: 返回 [(任务名, 所属插件名), ...] 的回调
        """
        self._plugins_provider = plugins_provider
        self._tasks_provider = tasks_provider

    # ===============================================================
    # 菜单构建
    def _build_menu(self) -> None:
        """构建托盘右键菜单（四项；两个子菜单在 aboutToShow 时动态重建）。"""
        self._show_action = self._menu.addAction(tr("tray", "menu.show_main_window"))
        self._show_action.triggered.connect(self.show_main_window_requested.emit)

        self._plugins_menu = self._menu.addMenu(tr("tray", "menu.running_plugins"))
        self._plugins_menu.aboutToShow.connect(self._rebuild_plugins_menu)

        self._tasks_menu = self._menu.addMenu(tr("tray", "menu.running_tasks"))
        self._tasks_menu.aboutToShow.connect(self._rebuild_tasks_menu)

        self._quit_action = self._menu.addAction(tr("tray", "menu.quit"))
        self._quit_action.triggered.connect(self.quit_requested.emit)

    def _retranslate_ui(self, _language: str) -> None:
        """语言切换后重译菜单固定项与托盘提示。

        两个状态子菜单的条目在 aboutToShow 动态重建时取词，无需在此刷新。
        """
        self._tray.setToolTip(tr("tray", "tooltip"))
        self._show_action.setText(tr("tray", "menu.show_main_window"))
        self._plugins_menu.setTitle(tr("tray", "menu.running_plugins"))
        self._tasks_menu.setTitle(tr("tray", "menu.running_tasks"))
        self._quit_action.setText(tr("tray", "menu.quit"))

    def _rebuild_plugins_menu(self) -> None:
        """动态重建「正在运行的插件」子菜单（点击项发射切换信号）。"""
        self._plugins_menu.clear()
        entries = self._query_safely(self._plugins_provider)
        if not entries:
            self._add_disabled_item(self._plugins_menu, tr("tray", "menu.no_plugins"))
            return
        for plugin, is_active in entries:
            action = self._plugins_menu.addAction(plugin.plugin_name)
            action.setCheckable(True)
            action.setChecked(is_active)
            action.triggered.connect(
                lambda _checked=False, p=plugin: self.plugin_activate_requested.emit(p)
            )

    def _rebuild_tasks_menu(self) -> None:
        """动态重建「后台正在运行的任务」子菜单（只读展示，不绑定动作）。"""
        self._tasks_menu.clear()
        entries = self._query_safely(self._tasks_provider)
        if not entries:
            self._add_disabled_item(self._tasks_menu, tr("tray", "menu.no_tasks"))
            return
        for task_name, plugin_name in entries:
            self._tasks_menu.addAction(
                tr("tray", "menu.task_entry", task_name=task_name, plugin_name=plugin_name)
            )

    def _query_safely(self, provider: Optional[Callable[[], list]]) -> list:
        """调用数据回调并兜底异常：失败记 WARNING、按空列表处理，
        不允许子菜单构建失败导致整个托盘菜单无法弹出。

        Args:
            provider: 子菜单数据回调，未注入时为 None

        Returns:
            回调返回的数据条目列表，异常或未注入时为空列表
        """
        if provider is None:
            return []
        try:
            return provider()
        except Exception as e:
            self._logger.warning(get_name(), f"托盘状态子菜单数据查询失败: {e}")
            return []

    def _add_disabled_item(self, menu: QMenu, text: str) -> None:
        """向菜单添加置灰的占位项（无数据时提示用）。"""
        action = menu.addAction(text)
        action.setEnabled(False)

    # ===============================================================
    # 图标激活
    def _connect_activation(self) -> None:
        """按后端能力接线 activated 信号：空元组（macOS/generic）则不接。"""
        self._activation_reasons = self._backend.activation_reasons()
        if not self._activation_reasons:
            return
        self._tray.activated.connect(self._on_tray_activated)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """托盘图标激活回调：命中后端声明的激活原因才请求恢复主窗口。"""
        if reason in self._activation_reasons:
            self.show_main_window_requested.emit()
