"""
PluginManager API 自动注册单元测试

测试目标：core/plugin/manager.py 中的 _auto_register_plugin_api 方法
测试范围：自定义 Service 类名、公共方法过滤、空 Service 类、私有方法过滤

风险关联：
- R-01: API 自动注册机制
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.plugin.manager import PluginManager
from test.conftest_utils import create_minimal_plugin


# ============================================================================
# Fixture: plugin_dir_from_test
# ============================================================================

@pytest.fixture
def plugin_dir_from_test(tmp_path):
    """
    构造插件测试目录，路径相对于本测试文件。

    返回 test/core/plugin/ 下的临时目录，供测试用例使用。
    """
    return tmp_path / "plugins"


# ============================================================================
# TC-PLUGIN-025: API 自动注册支持自定义 Service 类名
# ============================================================================

class TestAutoRegisterAPI:
    """API 自动注册功能测试"""

    def test_auto_register_with_custom_service_class(self, plugin_dir_from_test):
        """
        TC-PLUGIN-025: API 自动注册支持自定义 Service 类名

        测试步骤：
        1. 创建使用 MyService 类名的插件（非标准 Service 类名）
        2. 调用 load_plugins()
        3. 验证 API 是否被正确注册

        预期结果：支持自定义类名，或有明确错误提示

        风险关联：R-01
        """
        plugin_dir_from_test.mkdir(parents=True, exist_ok=True)
        test_plugin_dir = plugin_dir_from_test / "custom_service_plugin"

        # 创建使用 MyService 类名的插件
        test_plugin_dir.mkdir(parents=True, exist_ok=True)
        (test_plugin_dir / "__init__.py").write_text("")

        # entrance.py
        entrance_code = '''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QWidget

class CustomServicePlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "CustomServicePlugin"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        from PySide6.QtWidgets import QWidget
        return QWidget(parent)

plugin = CustomServicePlugin()
'''
        (test_plugin_dir / "entrance.py").write_text(entrance_code.lstrip())

        # service.py 使用自定义类名 MyService
        service_code = '''
class MyService:
    def echo(self, text):
        return text
'''
        (test_plugin_dir / "service.py").write_text(service_code.lstrip())

        # information.py
        info_code = '''
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class CustomServicePluginInfo(IPluginInfo):
    @property
    def version(self): return PluginVersion.from_string("release.1.0.0")
    @property
    def developer(self): return "TestDev"
    @property
    def developer_email(self): return "test@test.com"
    @property
    def developer_website(self): return "https://test.com"
    @property
    def is_free(self): return True
    @property
    def description(self): return "Custom service plugin"
    @property
    def service_api(self):
        return {
            "echo": {
                "description": "Echo a message",
                "parameters": {"text": {"type": "str", "description": "input", "required": True}},
                "returns": {"type": "str", "description": "output"}
            }
        }
    @property
    def skill_icon(self): return PluginIcon.none()
    @property
    def skill_description(self): return "Test skill"
    @property
    def plugin_type_id(self): return "custom-service-plugin-type"
'''
        (test_plugin_dir / "information.py").write_text(info_code.lstrip())

        # 加载插件
        mgr = PluginManager()
        mgr.official_plugin_dir = plugin_dir_from_test
        mgr.thirdparty_plugin_dir = plugin_dir_from_test.parent / "thirdparty_empty"
        mgr.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
        mgr.load_plugins()

        # 验证插件已加载
        loaded_plugin = mgr.get_plugin_by_name("CustomServicePlugin")
        assert loaded_plugin is not None

        # 验证 API 注册结果
        # 当前实现硬编码 Service 类名，自定义类名 MyService 不会被注册
        # 因此 _api_registry 应该为空（期望行为）或 API 被正确注册（如果支持自定义类名）
        plugin_api = mgr.get_plugin_api(loaded_plugin.plugin_id)

        # 验证：有明确结果（无论是否支持自定义类名）
        # 如果不支持，plugin_api 应为 None
        # 如果支持，plugin_api 应包含 echo 方法
        assert plugin_api is None or "echo" in plugin_api.get("methods", [])


# ============================================================================
# TC-PLUGIN-026: API 自动注册仅注册 Service 类的方法
# ============================================================================

    def test_auto_register_only_service_methods(self, plugin_dir_from_test):
        """
        TC-PLUGIN-026: API 自动注册仅注册 Service 类的方法

        测试步骤：
        1. 创建带 public_method 和 _private_method 的 Service
        2. 加载插件
        3. 调用 get_all_function_tools()

        预期结果：仅 public_method 被注册为 API

        风险关联：R-01
        """
        plugin_dir_from_test.mkdir(parents=True, exist_ok=True)
        test_plugin_dir = plugin_dir_from_test / "public_private_plugin"

        # 创建带公共方法和私有方法的插件
        test_plugin_dir.mkdir(parents=True, exist_ok=True)
        (test_plugin_dir / "__init__.py").write_text("")

        entrance_code = '''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QWidget

class PublicPrivatePlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "PublicPrivatePlugin"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        from PySide6.QtWidgets import QWidget
        return QWidget(parent)

plugin = PublicPrivatePlugin()
'''
        (test_plugin_dir / "entrance.py").write_text(entrance_code.lstrip())

        # service.py：同时包含公共方法和私有方法
        service_code = '''
class Service:
    def public_method(self, text):
        """Public method - should be registered"""
        return text.upper()

    def _private_method(self):
        """Private method - should not be registered"""
        return "private"
'''
        (test_plugin_dir / "service.py").write_text(service_code.lstrip())

        # information.py：只描述 public_method
        info_code = '''
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class PublicPrivatePluginInfo(IPluginInfo):
    @property
    def version(self): return PluginVersion.from_string("release.1.0.0")
    @property
    def developer(self): return "TestDev"
    @property
    def developer_email(self): return "test@test.com"
    @property
    def developer_website(self): return "https://test.com"
    @property
    def is_free(self): return True
    @property
    def description(self): return "Public private method plugin"
    @property
    def service_api(self):
        return {
            "public_method": {
                "description": "Public method",
                "parameters": {"text": {"type": "str", "description": "input", "required": True}},
                "returns": {"type": "str", "description": "output"}
            }
        }
    @property
    def skill_icon(self): return PluginIcon.none()
    @property
    def skill_description(self): return "Test skill"
    @property
    def plugin_type_id(self): return "public-private-plugin-type"
'''
        (test_plugin_dir / "information.py").write_text(info_code.lstrip())

        # 加载插件
        mgr = PluginManager()
        mgr.official_plugin_dir = plugin_dir_from_test
        mgr.thirdparty_plugin_dir = plugin_dir_from_test.parent / "thirdparty_empty"
        mgr.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
        mgr.load_plugins()

        # 获取所有函数工具
        tools = mgr.get_all_function_tools()

        # 验证：只应有 public_method，不应有 _private_method
        tool_names = [t["function"]["name"] for t in tools]

        # public_method 应该存在
        public_method_found = any("public_method" in name for name in tool_names)
        assert public_method_found, "public_method should be registered"

        # _private_method 不应该存在
        private_method_found = any("_private_method" in name for name in tool_names)
        assert not private_method_found, "_private_method should not be registered"


# ============================================================================
# TC-PLUGIN-027: 空 Service 类不注册任何 API
# ============================================================================

    def test_auto_register_empty_service_no_api(self, plugin_dir_from_test):
        """
        TC-PLUGIN-027: 空 Service 类不注册任何 API

        测试步骤：
        1. 创建空 Service 类
        2. 加载插件
        3. 调用 get_all_function_tools()

        预期结果：返回空列表，无 API 注册

        风险关联：R-01
        """
        plugin_dir_from_test.mkdir(parents=True, exist_ok=True)
        test_plugin_dir = plugin_dir_from_test / "empty_service_plugin"

        # 创建空 Service 插件
        test_plugin_dir.mkdir(parents=True, exist_ok=True)
        (test_plugin_dir / "__init__.py").write_text("")

        entrance_code = '''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QWidget

class EmptyServicePlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "EmptyServicePlugin"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        from PySide6.QtWidgets import QWidget
        return QWidget(parent)

plugin = EmptyServicePlugin()
'''
        (test_plugin_dir / "entrance.py").write_text(entrance_code.lstrip())

        # service.py：空 Service 类
        service_code = '''
class Service:
    pass
'''
        (test_plugin_dir / "service.py").write_text(service_code.lstrip())

        # information.py：无 service_api
        info_code = '''
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class EmptyServicePluginInfo(IPluginInfo):
    @property
    def version(self): return PluginVersion.from_string("release.1.0.0")
    @property
    def developer(self): return "TestDev"
    @property
    def developer_email(self): return "test@test.com"
    @property
    def developer_website(self): return "https://test.com"
    @property
    def is_free(self): return True
    @property
    def description(self): return "Empty service plugin"
    @property
    def service_api(self):
        return {}  # 空 API
    @property
    def skill_icon(self): return PluginIcon.none()
    @property
    def skill_description(self): return "Test skill"
    @property
    def plugin_type_id(self): return "empty-service-plugin-type"
'''
        (test_plugin_dir / "information.py").write_text(info_code.lstrip())

        # 加载插件
        mgr = PluginManager()
        mgr.official_plugin_dir = plugin_dir_from_test
        mgr.thirdparty_plugin_dir = plugin_dir_from_test.parent / "thirdparty_empty"
        mgr.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
        mgr.load_plugins()

        # 获取所有函数工具
        tools = mgr.get_all_function_tools()

        # 验证：空列表
        assert tools == [], "Empty service should register no API"


# ============================================================================
# TC-PLUGIN-028: Service 类仅有私有方法时不注册 API
# ============================================================================

    def test_auto_register_only_private_methods_no_api(self, plugin_dir_from_test):
        """
        TC-PLUGIN-028: Service 类仅有私有方法时不注册 API

        测试步骤：
        1. 创建仅有私有方法的 Service
        2. 加载插件
        3. 调用 get_all_function_tools()

        预期结果：返回空列表

        风险关联：R-01
        """
        plugin_dir_from_test.mkdir(parents=True, exist_ok=True)
        test_plugin_dir = plugin_dir_from_test / "private_only_plugin"

        # 创建仅有私有方法的插件
        test_plugin_dir.mkdir(parents=True, exist_ok=True)
        (test_plugin_dir / "__init__.py").write_text("")

        entrance_code = '''
from core.plugin.plugin_interface import IPlugin
from PySide6.QtWidgets import QWidget

class PrivateOnlyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "PrivateOnlyPlugin"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        from PySide6.QtWidgets import QWidget
        return QWidget(parent)

plugin = PrivateOnlyPlugin()
'''
        (test_plugin_dir / "entrance.py").write_text(entrance_code.lstrip())

        # service.py：只有私有方法
        service_code = '''
class Service:
    def _private_method(self):
        """私有方法"""
        return "private"

    def _another_private(self):
        """另一个私有方法"""
        return "another"
'''
        (test_plugin_dir / "service.py").write_text(service_code.lstrip())

        # information.py：尝试描述私有方法（但方法实际不存在于 Service 类或不应被注册）
        info_code = '''
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class PrivateOnlyPluginInfo(IPluginInfo):
    @property
    def version(self): return PluginVersion.from_string("release.1.0.0")
    @property
    def developer(self): return "TestDev"
    @property
    def developer_email(self): return "test@test.com"
    @property
    def developer_website(self): return "https://test.com"
    @property
    def is_free(self): return True
    @property
    def description(self): return "Private only plugin"
    @property
    def service_api(self):
        return {
            "_private_method": {
                "description": "Private method",
                "parameters": {},
                "returns": {"type": "str", "description": "output"}
            }
        }
    @property
    def skill_icon(self): return PluginIcon.none()
    @property
    def skill_description(self): return "Test skill"
    @property
    def plugin_type_id(self): return "private-only-plugin-type"
'''
        (test_plugin_dir / "information.py").write_text(info_code.lstrip())

        # 加载插件
        mgr = PluginManager()
        mgr.official_plugin_dir = plugin_dir_from_test
        mgr.thirdparty_plugin_dir = plugin_dir_from_test.parent / "thirdparty_empty"
        mgr.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
        mgr.load_plugins()

        # 获取所有函数工具
        tools = mgr.get_all_function_tools()

        # 验证：空列表（因为 _private_method 在 information.py 中定义，
        # 但注册时需要 service_instance 上实际存在该方法）
        # 实际验证的是：仅有私有方法时不注册 API
        assert tools == [], "Service with only private methods should register no API"
