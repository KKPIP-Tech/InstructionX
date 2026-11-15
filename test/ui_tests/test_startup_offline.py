"""真实 Qt 离线启动、交互响应与对话框生命周期验收。"""

import time

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication

from core.llm.provider_supervisor import ProviderSupervisor
from ui.dialog.about_dialog import AboutDialog
from ui.main_window import InstructionXMainWindow

STARTUP_INCREASE_LIMIT = 1.10
LOCAL_OPERATION_P95_LIMIT_MS = 100.0
DIALOG_CYCLES = 50
MEASUREMENT_CYCLES = 7


def _patch_offline_refresh(mocker, offline: bool):
    """让所有 Provider 刷新成功或确定性离线，不访问外部网络。"""
    if offline:
        def fail_refresh(self, provider_id, force):
            raise ConnectionError("全部 Provider 离线")
        mocker.patch.object(ProviderSupervisor, "_refresh", fail_refresh)
        return
    mocker.patch.object(ProviderSupervisor, "_refresh", lambda self, provider_id, force: [])


def _create_window(mocker, qtbot, offline: bool, patch_refresh: bool = True):
    """创建并显示真实主窗口，Provider 仅替换网络结果。"""
    if patch_refresh:
        _patch_offline_refresh(mocker, offline)
    manager = mocker.MagicMock()
    manager.get_plugin_load_failures.return_value = []
    manager.get_all_plugins.return_value = []
    manager.get_service_health_issues.return_value = {}
    mocker.patch("ui.main_window.PluginManager", return_value=manager)
    data_provider = mocker.MagicMock()
    data_provider.get_plugin_data.return_value = "light"
    mocker.patch("ui.main_window.DataProvider", return_value=data_provider)
    mocker.patch("ui.main_window.TrayIconManager")
    window = InstructionXMainWindow()
    qtbot.addWidget(window)
    window.show()
    QApplication.processEvents()
    assert window.isVisible()
    assert window.isEnabled()
    return window


def _measure_startup(mocker, qtbot, offline: bool) -> float:
    _patch_offline_refresh(mocker, offline)
    started = time.perf_counter()
    window = _create_window(mocker, qtbot, offline, patch_refresh=False)
    elapsed = time.perf_counter() - started
    window.deleteLater()
    QApplication.processEvents()
    return elapsed


def test_all_providers_offline_startup_is_interactive_and_within_110_percent(mocker, qtbot):
    """全部 Provider 离线时启动可交互，且相对在线冷启动增幅不超过 10%。"""
    _create_window(mocker, qtbot, offline=False).deleteLater()
    QApplication.processEvents()
    samples = {False: [], True: []}
    for index in range(MEASUREMENT_CYCLES):
        # 交换每组的先后次序，避免把 Qt 窗口创建/销毁的顺序效应误判为离线开销。
        modes = (False, True) if index % 2 == 0 else (True, False)
        for offline in modes:
            samples[offline].append(_measure_startup(mocker, qtbot, offline))
    online = sorted(samples[False])
    offline = sorted(samples[True])
    baseline = online[len(online) // 2]
    offline_median = offline[len(offline) // 2]
    assert offline_median <= baseline * STARTUP_INCREASE_LIMIT, (
        f"在线启动样本={online}，离线启动样本={offline}"
    )


def test_local_event_processing_p95_within_100ms(mocker, qtbot):
    """真实窗口本地事件处理 p95 不超过 100ms。"""
    _create_window(mocker, qtbot, offline=True)
    samples = []
    for _ in range(20):
        started = time.perf_counter()
        QApplication.processEvents()
        samples.append((time.perf_counter() - started) * 1000)
    samples.sort()
    rank = max(1, int(len(samples) * 0.95 + 0.999999))
    assert samples[rank - 1] <= LOCAL_OPERATION_P95_LIMIT_MS


def test_repeated_about_dialog_open_close_releases_resources(qtbot):
    """反复 50 次显示关闭关于对话框，不遗留可见对话框或顶层部件。"""
    baseline_widgets = len(QApplication.topLevelWidgets())
    for _ in range(DIALOG_CYCLES):
        dialog = AboutDialog()
        dialog.show()
        QApplication.processEvents()
        assert dialog.isVisible()
        dialog.close()
        dialog.deleteLater()
        QApplication.sendPostedEvents(dialog, QEvent.Type.DeferredDelete)
        QApplication.processEvents()
    assert not any(widget.isVisible() for widget in QApplication.topLevelWidgets() if isinstance(widget, AboutDialog))
    QApplication.sendPostedEvents()
    assert len(QApplication.topLevelWidgets()) <= baseline_widgets
