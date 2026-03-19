"""
Plugin Interface Tests

测试用例：
- PI-01: 插件名称获取 (正常/空名称/特殊字符)
- PI-02: 插件版本获取 (正常/无版本/格式错误)
- PI-03: Widget 创建 (正常/parent 为 None)
- PI-04: 插件初始化 (正常/初始化失败)
"""
import pytest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QWidget, QApplication
import sys


class TestIPluginInterface:
    """测试 IPlugin 接口实现"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    @pytest.fixture
    def mock_plugin(self):
        """创建模拟的插件对象"""
        from core.plugin.plugin_interface import IPlugin
        from core.plugin.plugin_info_interface import IPluginInfo

        class TestPlugin(IPlugin):
            def __init__(self, name="TestPlugin", version="1.0.0"):
                self._name = name
                self._version = version
                self._enabled = True
                self._init_called = False

            @property
            def plugin_name(self) -> str:
                return self._name

            @property
            def plugin_version(self) -> str:
                return self._version

            @property
            def plugin_info(self) -> IPluginInfo:
                return None

            def _create_widget(self, parent=None):
                widget = QWidget(parent)
                return widget

            def enable(self):
                self._enabled = True

            def disable(self):
                self._enabled = False

            @property
            def is_enabled(self) -> bool:
                return self._enabled

        return TestPlugin

    def test_plugin_name_normal(self, mock_plugin):
        """PI-01: 测试正常插件名称"""
        plugin = mock_plugin(name="MyPlugin")
        assert plugin.plugin_name == "MyPlugin"

    def test_plugin_name_empty(self, mock_plugin):
        """PI-01: 测试空插件名称"""
        plugin = mock_plugin(name="")
        assert plugin.plugin_name == ""

    def test_plugin_name_special_chars(self, mock_plugin):
        """PI-01: 测试特殊字符插件名称"""
        plugin = mock_plugin(name="插件-测试_123")
        assert plugin.plugin_name == "插件-测试_123"

    def test_plugin_version_normal(self, mock_plugin):
        """PI-02: 测试正常插件版本"""
        plugin = mock_plugin(version="1.2.3")
        assert plugin.plugin_version == "1.2.3"

    def test_plugin_version_empty(self, mock_plugin):
        """PI-02: 测试空版本"""
        plugin = mock_plugin(version="")
        assert plugin.plugin_version == ""

    def test_create_widget_normal(self, mock_plugin, qapp):
        """PI-03: 测试正常创建 Widget"""
        plugin = mock_plugin()
        widget = plugin._create_widget()
        assert widget is not None
        assert isinstance(widget, QWidget)
        widget.deleteLater()

    def test_create_widget_no_parent(self, mock_plugin, qapp):
        """PI-03: 测试 parent 为 None 时创建 Widget"""
        plugin = mock_plugin()
        widget = plugin._create_widget(parent=None)
        assert widget is not None
        widget.deleteLater()

    def test_plugin_enable_disable(self, mock_plugin):
        """PI-04: 测试插件启用/禁用"""
        plugin = mock_plugin()
        assert plugin.is_enabled is True

        plugin.disable()
        assert plugin.is_enabled is False

        plugin.enable()
        assert plugin.is_enabled is True


class TestPluginIdentity:
    """测试插件身份管理"""

    def test_generate_uuid(self):
        """测试 UUID 生成"""
        from core.plugin.plugin_identity import PluginIdentity
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            identity = PluginIdentity(plugin_dir)

            uuid1 = identity.load_or_create_id()
            uuid2 = identity.load_or_create_id()

            # UUID 应该一致（从文件加载）
            assert uuid1 == uuid2
            # UUID 格式验证
            assert len(uuid1) == 36  # 标准 UUID 长度

    def test_uuid_format(self):
        """测试 UUID 格式"""
        from core.plugin.plugin_identity import PluginIdentity
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            identity = PluginIdentity(plugin_dir)

            uuid = identity.load_or_create_id()

            # 验证 UUID 格式 (8-4-4-4-12)
            parts = uuid.split("-")
            assert len(parts) == 5
            assert len(parts[0]) == 8
            assert len(parts[1]) == 4
            assert len(parts[2]) == 4
            assert len(parts[3]) == 4
            assert len(parts[4]) == 12


class TestPluginInfoInterface:
    """测试插件信息接口"""

    def test_iplugin_info_is_abstract(self):
        """测试 IPluginInfo 是抽象类"""
        from core.plugin.plugin_info_interface import IPluginInfo
        from abc import ABC

        # IPluginInfo 应该是 ABC
        assert issubclass(IPluginInfo, ABC)

    def test_iplugin_info_properties(self):
        """测试 IPluginInfo 抽象属性"""
        from core.plugin.plugin_info_interface import IPluginInfo
        from core.plugin.plugin_version import PluginVersion
        from core.plugin.plugin_icon import PluginIcon

        # 创建实现类来测试
        class TestPluginInfo(IPluginInfo):
            @property
            def version(self) -> PluginVersion:
                return PluginVersion("release", 1, 0, 0)

            @property
            def developer(self) -> str:
                return "Test Developer"

            @property
            def developer_email(self) -> str:
                return "test@example.com"

            @property
            def developer_website(self) -> str:
                return "https://example.com"

            @property
            def is_free(self) -> bool:
                return True

            @property
            def description(self) -> str:
                return "Test description"

            @property
            def service_api(self) -> dict:
                return {}

            @property
            def skill_icon(self) -> PluginIcon:
                return PluginIcon.default()

            @property
            def skill_description(self) -> str:
                return "Test skill"

        info = TestPluginInfo()

        assert info.developer == "Test Developer"
        assert info.is_free is True
        assert info.skill_description == "Test skill"
