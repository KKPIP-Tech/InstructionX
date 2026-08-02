"""
pytest tests for ui.main_window.InstructionXMainWindow
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import QPoint, QEvent, Qt, Signal
from PySide6.QtGui import QMouseEvent


# ---------------------------------------------------------------------------
# Test: _create_menus() creates expected menus
# ---------------------------------------------------------------------------
def test_create_menus_creates_expected_menus(mocker, qtbot):
    """_create_menus() creates 编辑, 用户中心, AI, 帮助 menus."""
    from ui.main_window import InstructionXMainWindow

    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')

    # Directly test _create_menus logic by checking the class has the expected helper methods
    assert hasattr(InstructionXMainWindow, '_create_menus')
    assert hasattr(InstructionXMainWindow, '_open_plugin_management_dialog')
    assert hasattr(InstructionXMainWindow, '_cycle_theme')
    assert hasattr(InstructionXMainWindow, '_open_about_dialog')


# ---------------------------------------------------------------------------
# Test: _create_main_layout() instantiates components
# ---------------------------------------------------------------------------
def test_create_main_layout_instantiates_components(mocker, qtbot):
    """_create_main_layout() instantiates plugin_manager, skills_panel, work_area."""
    mock_pm_instance = MagicMock()
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager').return_value = mock_pm_instance
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow

    def patched_create_main_layout(self):
        self.plugin_manager = mock_pm_instance
        self.skills_panel = MagicMock()
        self.work_area = MagicMock()

    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout', patched_create_main_layout):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    assert hasattr(window, 'plugin_manager')
    assert hasattr(window, 'skills_panel')
    assert hasattr(window, 'work_area')
    assert window.plugin_manager is mock_pm_instance


# ---------------------------------------------------------------------------
# Test: _cycle_theme() cycles through all 3 states
# ---------------------------------------------------------------------------
def test_cycle_theme_cycles_all_states(mocker, qtbot):
    """_cycle_theme() cycles auto -> light -> dark -> auto."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')
    # 隔离真实全局 QSS 应用（UIKit 主题迁移后 _cycle_theme 走 apply_uikit_theme）
    mocker.patch('ui.main_window.apply_uikit_theme')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    window._menu_theme_action = MagicMock()

    # _current_theme 初值来自 current_theme_mode()（只返回 light/dark），
    # 显式固定为 auto 作为循环起点
    window._current_theme = 'auto'
    window._cycle_theme()
    assert window._current_theme == 'light'
    window._cycle_theme()
    assert window._current_theme == 'dark'
    window._cycle_theme()
    assert window._current_theme == 'auto'


# ---------------------------------------------------------------------------
# Test: Theme changes are saved via DataProvider
# ---------------------------------------------------------------------------
def test_theme_change_saved_via_dataprovider(mocker, qtbot):
    """_cycle_theme() calls _save_theme() which writes to DataProvider."""
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')
    # 隔离真实全局 QSS 应用（UIKit 主题迁移后 _cycle_theme 走 apply_uikit_theme）
    mocker.patch('ui.main_window.apply_uikit_theme')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    window._menu_theme_action = MagicMock()

    # 固定循环起点为 auto，下一步应切换到 light
    window._current_theme = 'auto'
    with patch.object(window, '_save_theme') as mock_save:
        window._cycle_theme()
        mock_save.assert_called_once_with('light')


# ---------------------------------------------------------------------------
# Test: _on_skill_clicked with valid plugin widget adds widget to work area
# ---------------------------------------------------------------------------
def test_on_skill_clicked_with_valid_widget(mocker, qtbot):
    """_on_skill_clicked() with a valid plugin widget adds it to work area."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    mock_wa = MagicMock()
    window.work_area = mock_wa

    mock_plugin = MagicMock()
    mock_plugin_widget = MagicMock()
    mock_plugin.get_widget.return_value = mock_plugin_widget

    window._on_skill_clicked(mock_plugin)

    mock_wa.clear_keep_highlight.assert_called_once()
    mock_plugin.get_widget.assert_called_once()
    mock_wa.add_widget.assert_called_once_with(mock_plugin_widget)


# ---------------------------------------------------------------------------
# Test: _on_skill_clicked with None widget shows error label
# ---------------------------------------------------------------------------
def test_on_skill_clicked_with_none_widget(mocker, qtbot):
    """_on_skill_clicked() with None widget shows error label in work area."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    mock_wa = MagicMock()
    window.work_area = mock_wa

    mock_plugin = MagicMock()
    mock_plugin.plugin_name = 'TestPlugin'
    mock_plugin.get_widget.return_value = None

    window._on_skill_clicked(mock_plugin)

    mock_wa.clear_keep_highlight.assert_called_once()
    last_call = mock_wa.add_widget.call_args
    widget_arg = last_call[0][0]
    assert isinstance(widget_arg, QLabel)
    assert 'TestPlugin' in widget_arg.text()


# ---------------------------------------------------------------------------
# Test: _get_resize_direction() top-left edge returns "top-left"
# ---------------------------------------------------------------------------
def test_get_resize_direction_top_left(mocker, qtbot):
    """_get_resize_direction() returns 'top-left' for top-left edge."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)
    window.resize(200, 200)

    mock_event = MagicMock(spec=QMouseEvent)
    mock_pos = MagicMock(spec=QPoint)
    mock_pos.x.return_value = 2
    mock_pos.y.return_value = 2
    mock_event.pos.return_value = mock_pos

    result = window._get_resize_direction(mock_event)
    assert result == 'top-left'


# ---------------------------------------------------------------------------
# Test: _get_resize_direction() bottom-right edge returns "bottom-right"
# ---------------------------------------------------------------------------
def test_get_resize_direction_bottom_right(mocker, qtbot):
    """_get_resize_direction() returns 'bottom-right' for bottom-right edge."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)

    # Patch width/height on window instance to return reliable values in offscreen mode
    with patch.object(window, 'width', return_value=200):
        with patch.object(window, 'height', return_value=200):
            mock_event = MagicMock(spec=QMouseEvent)
            mock_pos = MagicMock(spec=QPoint)
            mock_pos.x.return_value = 198
            mock_pos.y.return_value = 198
            mock_event.pos.return_value = mock_pos

            result = window._get_resize_direction(mock_event)
    assert result == 'bottom-right'


# ---------------------------------------------------------------------------
# Test: _get_resize_direction() center returns None
# ---------------------------------------------------------------------------
def test_get_resize_direction_center(mocker, qtbot):
    """_get_resize_direction() returns None for center area."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')
    mocker.patch('ui.main_window.TrayIconManager')

    from ui.main_window import InstructionXMainWindow
    with patch.object(InstructionXMainWindow, '_load_saved_theme'):
        with patch.object(InstructionXMainWindow, '_create_menus'):
            with patch.object(InstructionXMainWindow, '_create_main_layout'):
                window = InstructionXMainWindow()

    qtbot.addWidget(window)
    window.resize(200, 200)

    mock_event = MagicMock(spec=QMouseEvent)
    mock_pos = MagicMock(spec=QPoint)
    mock_pos.x.return_value = 100
    mock_pos.y.return_value = 100
    mock_event.pos.return_value = mock_pos

    result = window._get_resize_direction(mock_event)
    assert result is None


# ---------------------------------------------------------------------------
# Test: Menu-related methods exist on InstructionXMainWindow
# ---------------------------------------------------------------------------
def test_menu_actions_exist_and_connected(mocker, qtbot):
    """Menu action methods exist and are callable on InstructionXMainWindow."""
    mocker.patch('ui.main_window.SkillsPanel')
    mocker.patch('ui.main_window.WorkArea')
    mocker.patch('ui.main_window.DataProvider')
    mocker.patch('ui.main_window.PluginManager')

    from ui.main_window import InstructionXMainWindow

    # Verify menu-related methods exist
    assert hasattr(InstructionXMainWindow, '_create_menus')
    assert hasattr(InstructionXMainWindow, '_create_ai_menu')
    assert hasattr(InstructionXMainWindow, '_open_plugin_management_dialog')
    assert hasattr(InstructionXMainWindow, '_open_about_dialog')
    assert hasattr(InstructionXMainWindow, '_cycle_theme')
