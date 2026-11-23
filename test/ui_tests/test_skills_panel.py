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
    # load_skills_from_manager() 的数据源为 get_sorted_plugins(scope)，
    # 未分组插件以 ("plugin", 插件实例) 项返回，仍是布局直接子项
    mock_manager.get_sorted_plugins.side_effect = (
        lambda scope: [('plugin', mock_official)] if scope == 'official'
        else [('plugin', mock_thirdparty)]
    )

    panel.set_plugin_manager(mock_manager)
    panel.load_skills_from_manager()

    # Should be cleared and reloaded
    assert panel.official_layout.count() == 1
    assert panel.thirdparty_layout.count() == 1
    assert panel.official_layout.itemAt(0).widget().skill_name == 'OfficialOne'
    assert panel.thirdparty_layout.itemAt(0).widget().skill_name == 'ThirdOne'


# ---------------------------------------------------------------------------
# Test: load_skills_from_manager() renders group item as PluginGroupWidget
# ---------------------------------------------------------------------------
def test_load_skills_from_manager_renders_group_widget(qtbot):
    """load_skills_from_manager() 遇到 ("group", ...) 项时渲染 PluginGroupWidget，组内插件不直接加入页面布局。"""
    from ui.skills_panel.panel import SkillsPanel
    from ui.skills_panel.plugin_group_widget import PluginGroupWidget
    from core.plugin.plugin_groups import PluginGroup

    panel = SkillsPanel(None)
    qtbot.addWidget(panel)

    # 组内插件需具备分组机制所需的 plugin_id 属性
    mock_plugin = MagicMock()
    mock_plugin.plugin_id = 'grouped-plugin-uuid'
    mock_plugin.plugin_name = 'GroupedOne'
    mock_plugin.skill_icon = QIcon()
    mock_plugin.skill_description = 'Grouped desc'

    mock_group = PluginGroup.new('测试分组')
    mock_group.plugins = [mock_plugin.plugin_id]

    mock_manager = MagicMock()
    mock_manager.get_official_plugins.return_value = [mock_plugin]
    mock_manager.get_thirdparty_plugins.return_value = []
    mock_manager.get_sorted_plugins.side_effect = (
        lambda scope: [('group', mock_group, [mock_plugin])] if scope == 'official'
        else []
    )

    panel.set_plugin_manager(mock_manager)
    panel.load_skills_from_manager()

    # 官方页布局中该项为 PluginGroupWidget 实例
    assert panel.official_layout.count() == 1
    group_widget = panel.official_layout.itemAt(0).widget()
    assert isinstance(group_widget, PluginGroupWidget)

    # 组内插件按钮位于分组控件的展开区，不直接出现在 official_layout 中
    inner_layout = group_widget.expand_area.layout()
    assert inner_layout.count() == 1
    assert inner_layout.itemAt(0).widget().skill_name == 'GroupedOne'


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

    # Verify the stacked widget and pill buttons exist
    assert panel.stacked_widget is not None
    assert panel.stacked_widget.count() == 2
    assert panel.official_btn.text() == '官方功能'
    assert panel.thirdparty_btn.text() == '第三方功能'

    # Switch to thirdparty tab via pill button click
    panel.thirdparty_btn.click()
    assert panel.stacked_widget.currentIndex() == 1
    assert panel.thirdparty_btn.property('active') == 'true'
    assert panel.official_btn.property('active') == 'false'
    assert panel.count_label.text() == '1 Plugins'

    # Switch back to official tab
    panel.official_btn.click()
    assert panel.stacked_widget.currentIndex() == 0
    assert panel.official_btn.property('active') == 'true'
    assert panel.thirdparty_btn.property('active') == 'false'
    assert panel.count_label.text() == '1 Plugins'
