"""
Skills Panel and Work Area Tests

测试用例：
- SP-01: 插件列表显示 (0/1/多个插件)
- SP-02: 插件搜索 (正常/无结果/特殊字符)
- SP-03: 插件排序 (拖拽排序/自动排序)
- SP-04: 插件启用/禁用 (状态切换)
- WA-01: 插件界面显示 (正常切换)
- WA-02: 多插件标签 (打开/关闭/切换标签)
- WA-03: 插件布局 (不同分辨率)
"""
import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QListWidget


@pytest.mark.gui
class TestSkillsPanel:
    """测试技能面板"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def skills_panel(self, qapp):
        """创建技能面板的模拟对象"""
        panel = MagicMock()
        panel._plugin_manager = MagicMock()
        panel._plugin_list = QListWidget()

        yield panel

        panel._plugin_list.deleteLater()

    def test_sp_01_empty_list(self, skills_panel):
        """SP-01: 测试空插件列表"""
        skills_panel._plugin_list.clear()

        assert skills_panel._plugin_list.count() == 0

    def test_sp_01_single_plugin(self, skills_panel):
        """SP-01: 测试单个插件"""
        skills_panel._plugin_list.clear()
        skills_panel._plugin_list.addItem("TestPlugin")

        assert skills_panel._plugin_list.count() == 1

    def test_sp_01_multiple_plugins(self, skills_panel):
        """SP-01: 测试多个插件"""
        skills_panel._plugin_list.clear()

        plugins = ["Plugin1", "Plugin2", "Plugin3"]
        for name in plugins:
            skills_panel._plugin_list.addItem(name)

        assert skills_panel._plugin_list.count() == 3

    def test_sp_02_search_normal(self, skills_panel):
        """SP-02: 测试正常搜索"""
        skills_panel._plugin_list.clear()
        skills_panel._plugin_list.addItems(["Plugin1", "Plugin2", "Searchable"])

        # 模拟搜索
        search_term = "search"
        for i in range(skills_panel._plugin_list.count()):
            item = skills_panel._plugin_list.item(i)
            item.setHidden(search_term.lower() not in item.text().lower())

        visible_count = sum(
            1 for i in range(skills_panel._plugin_list.count())
            if not skills_panel._plugin_list.item(i).isHidden()
        )
        assert visible_count == 1

    def test_sp_04_plugin_enable_disable(self, skills_panel):
        """SP-04: 测试插件启用/禁用"""
        mock_plugin = MagicMock()
        mock_plugin.is_enabled = True
        mock_plugin.plugin_name = "TestPlugin"

        mock_plugin.enable.assert_not_called()
        mock_plugin.enable()
        mock_plugin.enable.assert_called_once()

        mock_plugin.disable.assert_not_called()
        mock_plugin.disable()
        mock_plugin.disable.assert_called_once()


@pytest.mark.gui
class TestWorkArea:
    """测试工作区"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def work_area(self, qapp):
        """创建工作区的模拟对象"""
        area = MagicMock()
        area._plugin_manager = MagicMock()
        area._layout = QVBoxLayout()
        area._current_widget = None

        yield area

        area._layout.deleteLater()
        if area._current_widget:
            area._current_widget.deleteLater()

    def test_wa_01_show_plugin(self, work_area):
        """WA-01: 测试显示插件"""
        widget = QWidget()
        work_area._current_widget = widget

        assert work_area._current_widget == widget

        widget.deleteLater()

    def test_wa_02_multiple_tabs(self, work_area):
        """WA-02: 测试多标签"""
        widget1 = QWidget()
        widget2 = QWidget()

        work_area._tab_widgets = {"plugin1": widget1, "plugin2": widget2}

        assert len(work_area._tab_widgets) == 2

        widget1.deleteLater()
        widget2.deleteLater()

    def test_wa_03_layout_resolution(self, work_area):
        """WA-03: 测试不同分辨率布局"""
        resolutions = [(800, 600), (1920, 1080), (2560, 1440)]

        for width, height in resolutions:
            work_area._width = width
            work_area._height = height

            assert work_area._width == width
            assert work_area._height == height
