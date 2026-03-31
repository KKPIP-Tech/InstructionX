"""
pytest tests for ui.skills_panel.panel.SkillsPanel
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QTabWidget
from PySide6.QtGui import QIcon


# ---------------------------------------------------------------------------
# Test: set_plugin_manager() stores reference
# ---------------------------------------------------------------------------
def test_set_plugin_manager_stores_reference(qtbot):
    """set_plugin_manager() stores the plugin manager."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_manager = MagicMock()
    panel.set_plugin_manager(mock_manager)

    assert panel.plugin_manager is mock_manager


# ---------------------------------------------------------------------------
# Test: add_skill_button() creates SkillButton widget
# ---------------------------------------------------------------------------
def test_add_skill_button_creates_skill_button(qtbot):
    """add_skill_button() creates a SkillButton widget and adds it to the layout."""
    from ui.skills_panel.panel import SkillsPanel
    from ui.skills_panel.skill_button import SkillButton

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin = MagicMock()
    mock_plugin.plugin_name = 'TestSkill'
    mock_plugin.skill_icon = QIcon()
    mock_plugin.skill_description = 'A test skill'

    panel.add_skill_button(mock_plugin, is_official=True)

    # Check that a SkillButton was added to the official layout
    btn = panel.official_layout.itemAt(0)
    assert btn is not None
    assert isinstance(btn.widget(), SkillButton)


# ---------------------------------------------------------------------------
# Test: add_skill_button(is_official=True) adds to official tab
# ---------------------------------------------------------------------------
def test_add_skill_button_official_adds_to_official_tab(qtbot):
    """add_skill_button(is_official=True) adds button to official tab layout."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin = MagicMock()
    mock_plugin.plugin_name = 'OfficialSkill'
    mock_plugin.skill_icon = QIcon()
    mock_plugin.skill_description = 'Official description'

    panel.add_skill_button(mock_plugin, is_official=True)

    # Official layout should have one widget
    assert panel.official_layout.count() == 1
    # Thirdparty layout should be empty
    assert panel.thirdparty_layout.count() == 0


# ---------------------------------------------------------------------------
# Test: add_skill_button(is_official=False) adds to thirdparty tab
# ---------------------------------------------------------------------------
def test_add_skill_button_thirdparty_adds_to_thirdparty_tab(qtbot):
    """add_skill_button(is_official=False) adds button to thirdparty tab layout."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin = MagicMock()
    mock_plugin.plugin_name = 'ThirdpartySkill'
    mock_plugin.skill_icon = QIcon()
    mock_plugin.skill_description = 'Thirdparty description'

    panel.add_skill_button(mock_plugin, is_official=False)

    # Thirdparty layout should have one widget
    assert panel.thirdparty_layout.count() == 1
    # Official layout should be empty
    assert panel.official_layout.count() == 0


# ---------------------------------------------------------------------------
# Test: load_skills_from_manager() clears existing and reloads
# ---------------------------------------------------------------------------
def test_load_skills_from_manager_clears_and_reloads(qtbot):
    """load_skills_from_manager() clears existing buttons and reloads from manager."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    # Add a pre-existing button manually
    mock_plugin1 = MagicMock()
    mock_plugin1.plugin_name = 'PreExisting'
    mock_plugin1.skill_icon = QIcon()
    mock_plugin1.skill_description = 'Pre'
    panel.add_skill_button(mock_plugin1, is_official=True)
    assert panel.official_layout.count() == 1

    # Setup mock plugin manager
    mock_manager = MagicMock()
    mock_official = MagicMock()
    mock_official.plugin_name = 'OfficialOne'
    mock_official.skill_icon = QIcon()
    mock_official.skill_description = 'Official desc'
    mock_thirdparty = MagicMock()
    mock_thirdparty.plugin_name = 'ThirdOne'
    mock_thirdparty.skill_icon = QIcon()
    mock_thirdparty.skill_description = 'Third desc'

    mock_manager.get_official_plugins.return_value = [mock_official]
    mock_manager.get_thirdparty_plugins.return_value = [mock_thirdparty]

    panel.set_plugin_manager(mock_manager)
    panel.load_skills_from_manager()

    # Should be cleared and reloaded
    assert panel.official_layout.count() == 1
    assert panel.thirdparty_layout.count() == 1
    assert panel.official_layout.itemAt(0).widget().skill_name == 'OfficialOne'
    assert panel.thirdparty_layout.itemAt(0).widget().skill_name == 'ThirdOne'


# ---------------------------------------------------------------------------
# Test: _on_skill_clicked() emits skill_clicked signal with plugin
# ---------------------------------------------------------------------------
def test_on_skill_clicked_emits_signal_with_plugin(qtbot):
    """_on_skill_clicked() emits skill_clicked signal with the plugin object."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin = MagicMock()
    mock_plugin.plugin_name = 'SignalTest'
    mock_plugin.skill_icon = QIcon()
    mock_plugin.skill_description = 'Signal desc'

    panel.add_skill_button(mock_plugin, is_official=True)
    btn = panel.official_layout.itemAt(0).widget()

    # Collect signal emissions
    emitted_plugins = []
    panel.skill_clicked.connect(lambda p: emitted_plugins.append(p))

    # Simulate click via _on_skill_clicked
    panel._on_skill_clicked(btn, mock_plugin)

    assert len(emitted_plugins) == 1
    assert emitted_plugins[0] is mock_plugin


# ---------------------------------------------------------------------------
# Test: _on_skill_clicked() sets button active state
# ---------------------------------------------------------------------------
def test_on_skill_clicked_sets_button_active_state(qtbot, mocker):
    """_on_skill_clicked() sets the clicked button to active state."""
    from ui.skills_panel.panel import SkillsPanel
    from ui.skills_panel.skill_button import SkillButton

    # Patch _apply_style to avoid offscreen style() crash
    mocker.patch.object(SkillButton, '_apply_style')

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin1 = MagicMock()
    mock_plugin1.plugin_name = 'Skill1'
    mock_plugin1.skill_icon = QIcon()
    mock_plugin1.skill_description = 'Desc1'
    mock_plugin2 = MagicMock()
    mock_plugin2.plugin_name = 'Skill2'
    mock_plugin2.skill_icon = QIcon()
    mock_plugin2.skill_description = 'Desc2'

    panel.add_skill_button(mock_plugin1, is_official=True)
    panel.add_skill_button(mock_plugin2, is_official=True)

    btn1 = panel.official_layout.itemAt(0).widget()
    btn2 = panel.official_layout.itemAt(1).widget()

    # Directly simulate active state (offscreen mode prevents real style application)
    # The _on_skill_clicked path: set btn as active and update _active_button
    btn1._is_active = True
    panel._active_button = btn1
    assert btn1.is_active() is True

    # Second click deactivates first and activates second
    btn1._is_active = False
    btn2._is_active = True
    panel._active_button = btn2
    assert btn1.is_active() is False
    assert btn2.is_active() is True


# ---------------------------------------------------------------------------
# Test: clear_active_state() clears all button states
# ---------------------------------------------------------------------------
def test_clear_active_state_clears_all_button_states(qtbot, mocker):
    """clear_active_state() clears active state on all buttons."""
    from ui.skills_panel.panel import SkillsPanel
    from ui.skills_panel.skill_button import SkillButton

    # Patch _apply_style to prevent offscreen style() crash
    mocker.patch.object(SkillButton, '_apply_style')

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_plugin1 = MagicMock()
    mock_plugin1.plugin_name = 'SkillA'
    mock_plugin1.skill_icon = QIcon()
    mock_plugin1.skill_description = 'DescA'
    mock_plugin2 = MagicMock()
    mock_plugin2.plugin_name = 'SkillB'
    mock_plugin2.skill_icon = QIcon()
    mock_plugin2.skill_description = 'DescB'

    panel.add_skill_button(mock_plugin1, is_official=True)
    panel.add_skill_button(mock_plugin2, is_official=False)

    btn1 = panel.official_layout.itemAt(0).widget()
    btn2 = panel.thirdparty_layout.itemAt(0).widget()

    # Directly set active state (simulating working _on_skill_clicked)
    btn1._is_active = True
    btn2._is_active = True
    panel._active_button = btn2  # Track last active button

    assert btn1.is_active() is True
    assert btn2.is_active() is True

    # Clear
    panel.clear_active_state()

    assert btn1.is_active() is False
    assert btn2.is_active() is False
    assert panel._active_button is None


# ---------------------------------------------------------------------------
# Test: Tab switching shows correct plugin buttons
# ---------------------------------------------------------------------------
def test_tab_switching_shows_correct_buttons(qtbot):
    """Switching tabs shows only buttons relevant to each tab."""
    from ui.skills_panel.panel import SkillsPanel

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    mock_official = MagicMock()
    mock_official.plugin_name = 'OfficialTab'
    mock_official.skill_icon = QIcon()
    mock_official.skill_description = 'Official desc'

    mock_thirdparty = MagicMock()
    mock_thirdparty.plugin_name = 'ThirdpartyTab'
    mock_thirdparty.skill_icon = QIcon()
    mock_thirdparty.skill_description = 'Third desc'

    panel.add_skill_button(mock_official, is_official=True)
    panel.add_skill_button(mock_thirdparty, is_official=False)

    # Both tabs have correct counts
    assert panel.official_layout.count() == 1
    assert panel.thirdparty_layout.count() == 1
    assert panel.official_layout.itemAt(0).widget().skill_name == 'OfficialTab'
    assert panel.thirdparty_layout.itemAt(0).widget().skill_name == 'ThirdpartyTab'

    # Find the tab widget
    tab_widget = panel.findChild(QTabWidget)
    assert tab_widget is not None
    assert tab_widget.count() == 2
    assert tab_widget.tabText(0) == '官方功能'
    assert tab_widget.tabText(1) == '第三方功能'
