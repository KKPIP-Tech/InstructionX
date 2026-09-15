# -*- coding: utf-8 -*-
"""技能面板插件名跟随界面语言的回归。

技能面板按钮文案取自 ``plugin.plugin_name``，而按钮文案在创建时固化：插件若提供
本地化名称（经 ``PluginServices.localization`` 取词），语言切换后必须重建按钮才能
跟随。为避免副作用，面板先比对各插件显示名快照——名字没变（固定品牌名插件）
则完全不重建，不重置分组展开状态与焦点；名字变了才重建，并恢复激活插件的高亮。
"""

import pytest
from PySide6.QtWidgets import QTabWidget

from ui.skills_panel.panel import SkillsPanel
from ui.skills_panel.skill_button import SkillButton

#: 分组 id（桩数据）
_GROUP_ID = "group-demo"
#: 桩插件显示名（短名，避免 SkillButton 两行省略影响断言）
_NAME_BEFORE = "旧名"
_NAME_AFTER = "新名"


class _StubPlugin:
    """桩插件：显示名可改（模拟本地化名称随语言变化）。"""

    def __init__(self, name: str) -> None:
        self.plugin_id = "stub-plugin"
        self.skill_icon = None
        self.name = name

    @property
    def plugin_name(self) -> str:
        """插件显示名（测试中直接改 ``name`` 模拟语言切换）。"""
        return self.name

    @property
    def skill_description(self) -> str:
        """插件描述。"""
        return "desc"


class _StubManager:
    """桩插件管理器：单插件（可选单分组）。"""

    def __init__(self, plugins, group=None) -> None:
        self._plugins = list(plugins)
        self._group = group

    def get_sorted_plugins(self, scope):
        """官方页返回分组项或未分组插件列表。"""
        if scope != "official":
            return []
        if self._group is not None:
            return [("group", self._group, list(self._plugins))]
        return [("plugin", plugin) for plugin in self._plugins]

    def get_official_plugins(self):
        """官方插件列表（计数用）。"""
        return list(self._plugins)

    def get_thirdparty_plugins(self):
        """第三方插件列表（计数用）。"""
        return []


class _StubGroup:
    """桩分组数据（``PluginGroup`` 的最小字段集）。"""

    def __init__(self, group_id: str, name: str) -> None:
        self.id = group_id
        self.name = name
        self.icon_key = "folder"
        self.plugins = []


@pytest.fixture
def panel(qtbot):
    """构建技能面板并挂上桩管理器：``(宿主控件, 面板, 插件, 挂载函数)``。

    宿主控件随返回值交给测试持有——面板是它的子控件，宿主被回收会连带销毁整棵
    控件树（``Internal C++ object already deleted``）。
    """
    host = QTabWidget()
    skills = SkillsPanel(host)
    plugin = _StubPlugin(_NAME_BEFORE)

    def _attach(group=None):
        skills.set_plugin_manager(_StubManager([plugin], group))
        skills.load_skills_from_manager()
        return skills

    _attach()
    qtbot.addWidget(host)
    return host, skills, plugin, _attach


def _plugin_buttons(skills: SkillsPanel) -> list:
    """面板内插件按钮（排除分组折叠按钮）。"""
    return [button for button in skills.findChildren(SkillButton)
            if button.objectName() != "skillGroupButton"]


def _live_text(buttons: list) -> list:
    """仍在布局中的插件按钮文案（已 deleteLater 的控件不参与比较）。"""
    return [b.text() for b in buttons if not b.isHidden()]


class TestLocalizedPluginNameFollows:
    """显示名变化的插件：重建按钮并保留状态。"""

    def test_button_rebuilt_with_new_name(self, panel, qtbot):
        """名字变化后按钮文案更新为新的显示名。"""
        _host, skills, plugin, _attach = panel
        assert _plugin_buttons(skills)[0].text() == _NAME_BEFORE

        plugin.name = _NAME_AFTER          # 模拟框架切语言后取词结果变化
        skills.retranslate_ui()
        qtbot.wait(10)

        assert _live_text(_plugin_buttons(skills)) == [_NAME_AFTER]

    def test_active_highlight_restored(self, panel, qtbot):
        """重建后原激活插件仍处于高亮态（且只有一个按钮高亮）。"""
        _host, skills, plugin, _attach = panel
        button = _plugin_buttons(skills)[0]
        skills._on_skill_clicked(button, plugin)

        plugin.name = _NAME_AFTER
        skills.retranslate_ui()
        qtbot.wait(10)

        active = [b for b in _plugin_buttons(skills) if b.is_active()]
        assert len(active) == 1, "重建后激活高亮未恢复"

    def test_group_expansion_preserved(self, panel, qtbot):
        """重建后分组展开状态保留（用户展开的分组不应被折叠）。"""
        _host, skills, plugin, attach = panel
        attach(_StubGroup(_GROUP_ID, "演示分组"))
        skills._group_widgets()[0].set_expanded(True)

        plugin.name = _NAME_AFTER
        skills.retranslate_ui()
        qtbot.wait(10)

        assert skills._group_widgets()[0].is_expanded(), "重建后分组展开状态丢失"


class TestStaticPluginNameUntouched:
    """显示名不变的插件（固定品牌名）：面板完全不重建。"""

    def test_no_rebuild_when_name_unchanged(self, panel, qtbot):
        """名字未变时不得重建按钮（避免重置展开状态与焦点）。"""
        _host, skills, _plugin, _attach = panel
        before = [id(button) for button in _plugin_buttons(skills)]

        skills.retranslate_ui()
        qtbot.wait(10)

        after = [id(button) for button in _plugin_buttons(skills)]
        assert after == before, "显示名未变却重建了面板按钮"

    def test_group_expansion_kept_when_name_unchanged(self, panel, qtbot):
        """名字未变时分组展开状态不受影响。"""
        _host, skills, _plugin, attach = panel
        attach(_StubGroup(_GROUP_ID, "演示分组"))
        skills._group_widgets()[0].set_expanded(True)

        skills.retranslate_ui()
        qtbot.wait(10)

        assert skills._group_widgets()[0].is_expanded()

    def test_no_manager_is_noop(self, qtbot):
        """未挂插件管理器时安全返回（不抛异常）。"""
        host = QTabWidget()
        skills = SkillsPanel(host)
        qtbot.addWidget(host)
        skills.retranslate_ui()          # 不应抛异常
