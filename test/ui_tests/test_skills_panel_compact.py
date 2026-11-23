"""SkillsPanel 紧凑模式的 Qt 生命周期回归测试。"""

import pytest
from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QScrollArea

from ui.skills_panel.scroll_navigation import SkillsScrollNavigator


@pytest.mark.ui
def test_delayed_refresh_after_scroll_area_deleted_is_noop(qtbot) -> None:
    """ScrollArea 销毁后，延迟刷新和滚动不得访问失效 C++ 对象。"""
    navigator = SkillsScrollNavigator()
    qtbot.addWidget(navigator)
    scroll_area = QScrollArea()
    navigator.watch(scroll_area)
    navigator.set_current(scroll_area)
    navigator.set_active(True)
    navigator.eventFilter(
        scroll_area.viewport(),
        QEvent(QEvent.Type.Resize),
    )

    scroll_area.deleteLater()
    qtbot.wait(20)
    navigator.refresh()
    navigator._scroll_page(1)

    assert navigator.isHidden() is True
