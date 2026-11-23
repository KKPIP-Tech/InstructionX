"""SkillsPanel 宽松/紧凑模式的真实 Qt 冒烟验证。"""

import argparse
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import ui.uikit_bootstrap  # noqa: F401

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from core.plugin.plugin_groups import PluginGroup
from ui.main_window import InstructionXMainWindow
from ui.skills_panel.panel import SkillsPanel
from ui.skills_panel.plugin_group_widget import PluginGroupWidget
from ui.skills_panel.scroll_navigation import SkillsScrollNavigator
from ui.skills_panel.skill_button import SkillButton
from InstructionX_UIKit import T
from ui.uikit_theme import apply_uikit_theme


TEST_ROW_HEIGHT = 24
INVALID_ROW_HEIGHT = 4
RELAXED_BUTTON_SIZE = QSize(78, 64)
COMPACT_BUTTON_WIDTH = 32
SCROLL_VIEW_WIDTH = 240
SCROLL_CONTENT_WIDE = 1200
SCROLL_CONTENT_NARROW = 120
PANEL_TEST_WIDTH = 640
HEADER_VERTICAL_MARGIN = 6
PILL_VERTICAL_MARGIN = 2
RELAXED_PANEL_MIN_HEIGHT = 125
RELAXED_PANEL_MAX_HEIGHT = 135
INTEGRATED_PLUGIN_COUNT = 30


def check_button() -> None:
    """验证按钮紧凑外观、完整名称提示与宽松恢复。"""
    button = SkillButton(QIcon(), "完整插件全称", "插件描述")
    assert hasattr(button, "set_compact"), "SkillButton 缺少 set_compact()"
    button.set_compact(True, TEST_ROW_HEIGHT)
    assert button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert button.width() == COMPACT_BUTTON_WIDTH
    assert button.height() == TEST_ROW_HEIGHT
    assert button.iconSize().height() <= TEST_ROW_HEIGHT
    assert button.toolTip() == "完整插件全称"
    button.set_active(True)
    button.set_compact(False, TEST_ROW_HEIGHT)
    assert button.size() == RELAXED_BUTTON_SIZE
    assert button.toolTip() == "完整插件全称\n插件描述"
    assert button.is_active() is True
    try:
        button.set_compact(True, INVALID_ROW_HEIGHT)
    except ValueError:
        pass
    else:
        raise AssertionError("无效紧凑行高未抛出 ValueError")


def check_group() -> None:
    """验证分组文件夹和组内按钮同步切换外观与行高。"""
    plugin = SimpleNamespace(
        skill_icon=QIcon(),
        plugin_name="组内插件",
        skill_description="组内描述",
    )
    group = PluginGroup.new("测试分组")
    factory = lambda item: SkillButton(
        item.skill_icon, item.plugin_name, item.skill_description
    )
    widget = PluginGroupWidget(group, [plugin], factory)
    assert hasattr(widget, "set_compact"), "PluginGroupWidget 缺少 set_compact()"
    widget.set_compact(True, TEST_ROW_HEIGHT)
    inner_button = widget.expand_area.layout().itemAt(0).widget()
    for button in (widget.folder_btn, inner_button):
        assert button.width() == COMPACT_BUTTON_WIDTH
        assert button.height() == TEST_ROW_HEIGHT
        assert button.is_compact() is True
    widget.set_compact(False, TEST_ROW_HEIGHT)
    assert widget.folder_btn.size() == RELAXED_BUTTON_SIZE
    assert inner_button.size() == RELAXED_BUTTON_SIZE


def _create_navigation_host():
    """创建真实滚动页和导航组件。"""
    host = QWidget()
    layout = QVBoxLayout(host)
    scroll = QScrollArea(host)
    content = QWidget()
    content.setFixedSize(SCROLL_CONTENT_NARROW, TEST_ROW_HEIGHT)
    scroll.setWidget(content)
    navigator = SkillsScrollNavigator(host)
    navigator.set_row_height(TEST_ROW_HEIGHT)
    navigator.watch(scroll)
    navigator.set_current(scroll)
    navigator.set_active(True)
    layout.addWidget(scroll)
    layout.addWidget(navigator)
    host.resize(SCROLL_VIEW_WIDTH, RELAXED_BUTTON_SIZE.height())
    host.show()
    QApplication.processEvents()
    return host, scroll, content, navigator


def check_navigation() -> None:
    """验证溢出导航、UIKit 图标、分页滚动与边界状态。"""
    host, scroll, content, navigator = _create_navigation_host()
    navigator.refresh()
    assert navigator.isHidden(), "无溢出时导航不应显示"
    content.setFixedWidth(SCROLL_CONTENT_WIDE)
    QApplication.processEvents()
    navigator.refresh()
    bar = scroll.horizontalScrollBar()
    assert navigator.isVisible() is True
    assert navigator.left_btn.isEnabled() is False
    assert navigator.right_btn.isEnabled() is True
    assert navigator.left_btn.text() == ""
    assert navigator.right_btn.text() == ""
    assert not navigator.left_btn.icon().isNull()
    assert not navigator.right_btn.icon().isNull()
    previous = bar.value()
    navigator.right_btn.click()
    assert bar.value() == previous + bar.pageStep()
    bar.setValue(bar.maximum())
    assert navigator.right_btn.isEnabled() is False
    assert navigator.left_btn.isEnabled() is True
    navigator.set_current(None)
    assert navigator.isHidden(), "空当前页时导航不应显示"
    host.close()


def check_navigation_lifecycle() -> None:
    """验证视口缩放、主题刷新、行高和异常输入。"""
    host, scroll, content, navigator = _create_navigation_host()
    content.setFixedWidth(SCROLL_CONTENT_WIDE)
    QApplication.processEvents()
    navigator.refresh()
    bar = scroll.horizontalScrollBar()
    previous_maximum = bar.maximum()
    host.resize(SCROLL_VIEW_WIDTH * 2, RELAXED_BUTTON_SIZE.height())
    QApplication.processEvents()
    navigator.refresh()
    assert bar.maximum() < previous_maximum
    assert navigator.isVisible() is True
    assert navigator.left_btn.height() == TEST_ROW_HEIGHT
    assert navigator.right_btn.height() == TEST_ROW_HEIGHT
    icon_key = navigator.left_btn.icon().cacheKey()
    apply_uikit_theme(QApplication.instance(), "dark")
    QApplication.processEvents()
    assert navigator.left_btn.icon().cacheKey() != icon_key
    apply_uikit_theme(QApplication.instance(), "light")
    try:
        navigator.set_row_height(INVALID_ROW_HEIGHT)
    except ValueError:
        pass
    else:
        raise AssertionError("无效导航行高未抛出 ValueError")
    host.close()


def _make_plugin(name: str):
    """创建仅包含技能面板所需数据的插件替身。"""
    return SimpleNamespace(
        plugin_id=f"uuid-{name}",
        plugin_name=name,
        skill_icon=QIcon(),
        skill_description=f"{name}描述",
    )


def _create_loaded_panel():
    """创建包含未分组、分组和第三方插件的真实面板。"""
    official = [_make_plugin(f"官方{index}") for index in range(14)]
    thirdparty = [_make_plugin(f"第三方{index}") for index in range(12)]
    group = PluginGroup.new("测试分组")
    group.plugins = [plugin.plugin_id for plugin in official[2:]]
    manager = MagicMock()
    manager.get_official_plugins.return_value = official
    manager.get_thirdparty_plugins.return_value = thirdparty
    manager.get_sorted_plugins.side_effect = lambda scope: (
        [("plugin", official[0]), ("plugin", official[1]),
         ("group", group, official[2:])]
        if scope == "official" else [("plugin", plugin) for plugin in thirdparty]
    )
    panel = SkillsPanel(None)
    panel.set_plugin_manager(manager)
    panel.load_skills_from_manager()
    panel.resize(PANEL_TEST_WIDTH, RELAXED_PANEL_MAX_HEIGHT)
    panel.show()
    QApplication.processEvents()
    return panel, manager


def _assert_compact_panel(panel, group_widget, active_plugin) -> None:
    """断言紧凑布局、统一行高和状态保持。"""
    row_height = panel._compact_row_height()
    expected_height = (
        row_height + 2 * HEADER_VERTICAL_MARGIN + 2 * PILL_VERTICAL_MARGIN
    )
    assert panel.display_mode == "compact"
    assert panel.property("compact") == "true"
    app_qss = QApplication.instance().styleSheet()
    chrome_start = app_qss.index('SkillsPanel[compact="true"]')
    chrome_end = app_qss.index("SkillsPanel QWidget#skillsPanelHeader", chrome_start)
    compact_chrome = app_qss[chrome_start:chrome_end]
    assert "background: transparent" not in compact_chrome
    assert f"background-color: {T('color.bg.subtle')}" in compact_chrome
    assert 'SkillButton[compact="true"][active="true"]' in app_qss
    assert 'SkillsPanel[compact="true"] QScrollArea' in app_qss
    assert 'SkillsPanel[compact="true"] QStackedWidget' in app_qss
    assert "border: none" in group_widget.expand_area.styleSheet()
    assert panel.count_label.isHidden() is True
    assert panel.height() == expected_height
    assert panel._header_layout.indexOf(panel.stacked_widget) >= 0
    assert panel._active_plugin is active_plugin
    assert group_widget.is_expanded() is True
    for index in range(2):
        button = panel.official_layout.itemAt(index).widget()
        assert button.height() == panel.official_btn.height()
        assert button.height() == panel.thirdparty_btn.height()
    assert group_widget.folder_btn.height() == row_height
    inner_layout = group_widget.expand_area.layout()
    assert inner_layout.itemAt(0).widget().height() == row_height
    assert panel.scroll_navigator.left_btn.height() == row_height
    assert panel.scroll_navigator.right_btn.height() == row_height
    for scroll_area in panel._scroll_areas.values():
        policy = scroll_area.horizontalScrollBarPolicy()
        assert policy == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert scroll_area.frameShape() == QFrame.Shape.NoFrame


def _check_group_overflow(panel, group_widget) -> None:
    """验证分组展开和收起会实时改变溢出导航。"""
    assert panel.scroll_navigator.isVisible() is True
    group_widget.set_expanded(False)
    QApplication.processEvents()
    assert panel.scroll_navigator.isHidden() is True
    group_widget.set_expanded(True)
    QApplication.processEvents()
    assert panel.scroll_navigator.isVisible() is True


def _check_scroll_preservation(panel) -> None:
    """验证两个页面各自的滚动位置在模式往返后保持。"""
    official_bar = panel._scroll_areas[0].horizontalScrollBar()
    thirdparty_bar = panel._scroll_areas[1].horizontalScrollBar()
    official_bar.setValue(min(40, official_bar.maximum()))
    official_value = official_bar.value()
    panel.thirdparty_btn.click()
    thirdparty_bar.setValue(min(60, thirdparty_bar.maximum()))
    thirdparty_value = thirdparty_bar.value()
    panel.official_btn.click()
    assert official_bar.value() == official_value
    panel.set_display_mode("relaxed")
    QApplication.processEvents()
    panel.set_display_mode("compact")
    QApplication.processEvents()
    assert official_bar.value() == official_value
    assert thirdparty_bar.value() == thirdparty_value


def check_panel() -> None:
    """验证面板双模式布局、状态保持和非法模式。"""
    panel, manager = _create_loaded_panel()
    assert hasattr(panel, "set_display_mode"), "SkillsPanel 缺少 set_display_mode()"
    group_widget = panel.official_layout.itemAt(2).widget()
    active_plugin = manager.get_official_plugins.return_value[1]
    panel.official_layout.itemAt(1).widget().click()
    group_widget.set_expanded(True)
    QApplication.processEvents()
    load_call_count = manager.get_sorted_plugins.call_count
    panel.set_display_mode("compact")
    QApplication.processEvents()
    _assert_compact_panel(panel, group_widget, active_plugin)
    assert manager.get_sorted_plugins.call_count == load_call_count
    _check_group_overflow(panel, group_widget)
    _check_scroll_preservation(panel)
    panel.thirdparty_btn.click()
    assert panel.stacked_widget.currentIndex() == 1
    current = panel.scroll_navigator._current_scroll_area
    assert current is panel._scroll_areas[1]
    panel.official_btn.click()
    panel.set_display_mode("relaxed")
    assert panel.property("compact") == "false"
    assert panel.count_label.isHidden() is False
    assert panel.minimumHeight() == RELAXED_PANEL_MIN_HEIGHT
    assert panel.maximumHeight() == RELAXED_PANEL_MAX_HEIGHT
    for scroll_area, shape in panel._scroll_frame_shapes.items():
        assert scroll_area.frameShape() == shape
    assert panel._active_plugin is active_plugin
    assert group_widget.is_expanded() is True
    try:
        panel.set_display_mode("invalid")
    except ValueError:
        pass
    else:
        raise AssertionError("非法面板模式未抛出 ValueError")
    panel.close()


def _create_menu_window():
    """创建使用真实编辑菜单、隔离重型启动依赖的主窗口。"""
    patches = (
        patch.object(InstructionXMainWindow, "_load_saved_theme"),
        patch.object(
            InstructionXMainWindow, "_load_saved_skills_panel_mode", create=True
        ),
        patch.object(InstructionXMainWindow, "_create_main_layout"),
        patch.object(InstructionXMainWindow, "_setup_tray"),
    )
    for patcher in patches:
        patcher.start()
    window = InstructionXMainWindow()
    for patcher in patches:
        patcher.stop()
    window.skills_panel = MagicMock()
    return window


def _check_mode_persistence() -> None:
    """使用内存替身验证保存、重启恢复和异常降级。"""
    storage = {}
    provider = MagicMock()
    provider.get_plugin_data.side_effect = (
        lambda _id, key, _namespace, default: storage.get(key, default)
    )
    provider.set_plugin_data.side_effect = (
        lambda _id, key, value, _namespace, notify: storage.__setitem__(key, value)
    )
    with patch("ui.main_window.DataProvider", return_value=provider):
        owner = SimpleNamespace(_logger=MagicMock(), _skills_panel_mode="compact")
        InstructionXMainWindow._save_skills_panel_mode(owner)
        restored = SimpleNamespace(_logger=MagicMock(), _skills_panel_mode="relaxed")
        InstructionXMainWindow._load_saved_skills_panel_mode(restored)
        assert restored._skills_panel_mode == "compact"
        storage["skills_panel_mode"] = "invalid"
        InstructionXMainWindow._load_saved_skills_panel_mode(restored)
        assert restored._skills_panel_mode == "relaxed"
        provider.set_plugin_data.side_effect = RuntimeError("disk full")
        InstructionXMainWindow._save_skills_panel_mode(owner)
        owner._logger.warning.assert_called_once()


def check_menu() -> None:
    """验证编辑菜单位置、切换动作和模式持久化。"""
    window = _create_menu_window()
    assert hasattr(window, "_action_skills_mode"), "缺少技能区模式菜单动作"
    actions = window._menu_edit.actions()
    action = window._action_skills_mode
    mode_index = actions.index(action)
    assert actions[mode_index - 1] is window._menu_theme_action
    assert actions[mode_index + 1] is window._action_language
    assert action not in window.menuBar().actions()
    with patch.object(window, "_save_skills_panel_mode") as save:
        action.trigger()
        window.skills_panel.set_display_mode.assert_called_once_with("compact")
        save.assert_called_once_with()
        assert window._skills_panel_mode == "compact"
        assert action.isChecked() is True
        action.trigger()
        assert window._skills_panel_mode == "relaxed"
        assert action.isChecked() is False
    window.deleteLater()
    _check_mode_persistence()


def check_panel_metrics() -> None:
    """验证语言和主题刷新后会重新同步所有紧凑行高。"""
    panel, _manager = _create_loaded_panel()
    panel.set_display_mode("compact")
    QApplication.processEvents()
    style_cases = ((22, 26), (26, 30))
    for index, (qss_height, height) in enumerate(style_cases):
        qss = f"min-height: {qss_height}px; max-height: {qss_height}px;"
        panel.official_btn.setStyleSheet(qss)
        panel.thirdparty_btn.setStyleSheet(qss)
        if index == 0:
            panel._retranslate_ui()
        else:
            panel._on_theme_changed("dark")
        QApplication.processEvents()
        first = panel.official_layout.itemAt(0).widget()
        assert first.height() == height
        assert panel.scroll_navigator.left_btn.height() == height
        assert panel.scroll_navigator.right_btn.height() == height
        expected = (
            height + 2 * HEADER_VERTICAL_MARGIN + 2 * PILL_VERTICAL_MARGIN
        )
        assert panel.height() == expected
    panel.close()


class _FakePlugin:
    """提供主窗口集成验证所需的最小插件接口。"""

    def __init__(self, index: int):
        self.plugin_id = f"integrated-{index}"
        self.plugin_name = f"集成验证插件完整名称{index}"
        self.skill_icon = QIcon()
        self.skill_description = "用于验证真实 WorkArea 切换"

    def get_widget(self, parent=None):
        """返回真实插件内容标签，验证 WorkArea 实际接管控件。"""
        return QLabel(self.plugin_name, parent)


def _integrated_services():
    """创建不接触真实数据库和插件目录的集成依赖。"""
    plugins = [_FakePlugin(index) for index in range(INTEGRATED_PLUGIN_COUNT)]
    manager = MagicMock()
    manager.get_official_plugins.return_value = plugins
    manager.get_thirdparty_plugins.return_value = []
    manager.get_sorted_plugins.side_effect = lambda scope: (
        [("plugin", plugin) for plugin in plugins] if scope == "official" else []
    )
    manager.get_plugin_load_failures.return_value = []
    manager.get_service_health_issues.return_value = {}
    storage = {}
    provider = MagicMock()
    provider.get_plugin_data.side_effect = (
        lambda _id, key, _namespace, default: storage.get(key, default)
    )
    provider.set_plugin_data.side_effect = (
        lambda _id, key, value, _namespace, notify: storage.__setitem__(key, value)
    )
    return manager, provider, plugins


def _exercise_integrated_window(window, plugins) -> None:
    """在真实主窗口中验证切换、溢出、插件点击和空间释放。"""
    window.show()
    QApplication.processEvents()
    panel = window.skills_panel
    relaxed_height = panel.height()
    relaxed_work_height = window.work_area.get_widget().height()
    window._action_skills_mode.trigger()
    QApplication.processEvents()
    assert panel.display_mode == "compact"
    assert panel.height() < relaxed_height
    assert window.work_area.get_widget().height() > relaxed_work_height
    assert panel.scroll_navigator.isVisible() is True
    panel.thirdparty_btn.click()
    QApplication.processEvents()
    assert panel.scroll_navigator.isHidden() is True
    panel.official_btn.click()
    QApplication.processEvents()
    assert panel.scroll_navigator.isVisible() is True
    first = panel.official_layout.itemAt(0).widget()
    assert first.height() == panel.official_btn.height()
    assert first.toolTip() == plugins[0].plugin_name
    first.click()
    QApplication.processEvents()
    assert window._active_plugin is plugins[0]
    labels = window.work_area.get_widget().findChildren(QLabel)
    assert any(label.text() == plugins[0].plugin_name for label in labels)
    bar = panel._scroll_areas[0].horizontalScrollBar()
    previous = bar.value()
    panel.scroll_navigator.right_btn.click()
    assert bar.value() > previous


def check_integrated_window() -> None:
    """验证真实主窗口链路和重建后的模式恢复。"""
    manager, provider, plugins = _integrated_services()
    with (
        patch("ui.main_window.DataProvider", return_value=provider),
        patch("ui.main_window.PluginManager", return_value=manager),
        patch("ui.main_window.TrayIconManager"),
    ):
        window = InstructionXMainWindow()
        _exercise_integrated_window(window, plugins)
        window.hide()
        window.deleteLater()
        QApplication.processEvents()
        restored = InstructionXMainWindow()
        restored.show()
        QApplication.processEvents()
        assert restored.skills_panel.display_mode == "compact"
        assert restored._action_skills_mode.isChecked() is True
        restored.hide()
        restored.deleteLater()
        QApplication.processEvents()


CASES = {
    "button": check_button,
    "group": check_group,
    "navigation": check_navigation,
    "navigation_lifecycle": check_navigation_lifecycle,
    "panel": check_panel,
    "panel_metrics": check_panel_metrics,
    "menu": check_menu,
    "integrated": check_integrated_window,
}


def main() -> int:
    """运行指定或全部冒烟场景，失败时输出具体断言。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=tuple(CASES), default=None)
    args = parser.parse_args()
    app = QApplication.instance() or QApplication(sys.argv)
    apply_uikit_theme(app)
    selected = CASES if args.case is None else {args.case: CASES[args.case]}
    try:
        for name, check in selected.items():
            check()
            print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {args.case}: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
