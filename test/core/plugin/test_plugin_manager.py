"""
PluginManager 单元测试

测试目标：core/plugin/manager.py 中的 PluginManager 类
测试范围：单例模式、插件加载、注册与注销、API 管理、方法调用、函数工具生成、重新加载
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.plugin.manager import PluginManager, PluginAPI
from test.conftest_utils import create_minimal_plugin


# ============================================================================
# Fixture: plugin_dir_from_test
# ============================================================================

@pytest.fixture
def plugin_dir_from_test(tmp_path):
    """
    构造插件测试目录，路径相对于本测试文件。

    返回 test/core/plugin/ 下的临时目录，供测试用例使用。
    与 temp_plugin_dir 不同之处在于：此处使用 __file__ 路径，
    可确保 PluginIdentity 写入的 .plugin_id 文件位于 tmp_path 下。
    """
    return tmp_path / "plugins"


# ============================================================================
# 1. 单例模式测试
# ============================================================================

class TestSingleton:
    """验证 PluginManager 的单例模式"""

    def test_singleton_two_calls_return_same_instance(self):
        """
        两次调用 PluginManager() 应返回同一实例对象。
        """
        mgr1 = PluginManager()
        mgr2 = PluginManager()
        assert mgr1 is mgr2


# ============================================================================
# 2. load_official_plugins() 测试
# ============================================================================

class TestLoadOfficialPlugins:
    """验证官方插件加载逻辑"""

    def test_load_official_plugins_skips_underscore_prefix_dirs(self, mocker, plugin_dir_from_test):
        """
        load_official_plugins() 应跳过以 '_' 开头的目录。
        """
        # 创建正常插件目录和 '_' 前缀目录
        valid_plugin = plugin_dir_from_test / "valid_plugin"
        hidden_plugin = plugin_dir_from_test / "_hidden_plugin"
        plugin_dir_from_test.mkdir(parents=True)

        create_minimal_plugin(valid_plugin, plugin_name="ValidPlugin")

        # '_' 前缀目录不需要完整的 entrance.py，但仍创建它以排除其他失败原因
        hidden_plugin.mkdir()
        (hidden_plugin / "entrance.py").write_text("")
        (hidden_plugin / "__init__.py").write_text("")

        mgr = PluginManager()
        # official_plugin_dir 是实例属性，直接在实例上赋值
        mgr.official_plugin_dir = plugin_dir_from_test
        mgr.load_official_plugins()

        plugin_names = [p.plugin_name for p in mgr._official_plugins]
        assert "ValidPlugin" in plugin_names
        assert "_hidden_plugin" not in plugin_names

    def test_load_plugin_from_directory_no_entrance_returns_none(self, mocker, plugin_dir_from_test):
        """
        _load_plugin_from_directory() 在插件目录缺少 entrance.py 时应返回 None。
        """
        empty_dir = plugin_dir_from_test / "no_entrance"
        empty_dir.mkdir(parents=True)

        mgr = PluginManager()
        result = mgr._load_plugin_from_directory(empty_dir)
        assert result is None

    def test_load_plugin_from_directory_no_iplugin_subclass_returns_none(self, plugin_dir_from_test):
        """
        _load_plugin_from_directory() 在 entrance.py 不包含 IPlugin 子类时返回 None。
        """
        bad_dir = plugin_dir_from_test / "no_iplugin"
        bad_dir.mkdir(parents=True)

        # entrance.py 存在，但不定义任何 IPlugin 子类
        (bad_dir / "entrance.py").write_text("x = 1\n")
        (bad_dir / "__init__.py").write_text("")

        # Directly modify sys.path temporarily (sys.path is a list, not a dict)
        parent = str(bad_dir.parent)
        original_path = sys.path.copy()
        try:
            sys.path.insert(0, parent)
            mgr = PluginManager()
            result = mgr._load_plugin_from_directory(bad_dir)
        finally:
            sys.path[:] = original_path
        assert result is None


# ============================================================================
# 3. register_plugin / unregister_plugin 测试
# ============================================================================

class TestRegisterUnregister:
    """验证插件的手动注册与注销"""

    def test_register_plugin_maintains_all_three_registries(self):
        """
        register_plugin() 应同时将插件添加到注册表、名称映射以及官方/第三方列表。
        """
        mgr = PluginManager()

        # Mock 一个插件实例
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "test-plugin-id-1"
        mock_plugin.plugin_name = "TestPlugin1"

        mgr.register_plugin(mock_plugin, is_official=True)

        assert "test-plugin-id-1" in mgr._plugin_registry
        assert mgr._plugin_registry["test-plugin-id-1"] is mock_plugin
        assert "TestPlugin1" in mgr._plugin_name_to_id
        assert mock_plugin in mgr._official_plugins
        assert mock_plugin not in mgr._thirdparty_plugins

    def test_register_plugin_thirdparty_maintains_registry(self):
        """register_plugin(is_official=False) 应将插件添加到第三方列表"""
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "test-plugin-id-2"
        mock_plugin.plugin_name = "TestPlugin2"

        mgr.register_plugin(mock_plugin, is_official=False)

        assert "test-plugin-id-2" in mgr._plugin_registry
        assert mock_plugin in mgr._thirdparty_plugins
        assert mock_plugin not in mgr._official_plugins

    def test_unregister_plugin_removes_from_all_three_registries(self):
        """
        unregister_plugin() 应从注册表、名称映射以及两个插件列表中完全移除插件。
        """
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "test-plugin-id-3"
        mock_plugin.plugin_name = "TestPlugin3"

        mgr.register_plugin(mock_plugin, is_official=True)
        mgr.unregister_plugin("TestPlugin3")

        assert "test-plugin-id-3" not in mgr._plugin_registry
        assert "TestPlugin3" not in mgr._plugin_name_to_id
        assert mock_plugin not in mgr._official_plugins
        assert mock_plugin not in mgr._thirdparty_plugins

    def test_unregister_plugin_idempotent(self):
        """重复调用 unregister_plugin 不应抛出异常"""
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "test-id-4"
        mock_plugin.plugin_name = "TestPlugin4"

        mgr.register_plugin(mock_plugin, is_official=True)
        mgr.unregister_plugin("TestPlugin4")
        mgr.unregister_plugin("TestPlugin4")  # 不应抛出
        mgr.unregister_plugin("NonExistent")   # 同样不应抛出


# ============================================================================
# 4. 插件查询方法测试
# ============================================================================

class TestPluginQueries:
    """验证 get_plugin_by_name / get_plugin_by_id / get_plugin_id_by_type_id"""

    def test_get_plugin_by_name_returns_plugin(self):
        """已注册的插件可通过名称正确查询"""
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "id-name-test"
        mock_plugin.plugin_name = "NameTestPlugin"

        mgr.register_plugin(mock_plugin, is_official=False)
        result = mgr.get_plugin_by_name("NameTestPlugin")
        assert result is mock_plugin

    def test_get_plugin_by_name_returns_none_for_unknown(self):
        """不存在的插件名称应返回 None"""
        mgr = PluginManager()
        assert mgr.get_plugin_by_name("NonExistentPlugin") is None

    def test_get_plugin_by_id_returns_plugin(self):
        """已注册的插件可通过 ID 正确查询"""
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "id-direct-test"
        mock_plugin.plugin_name = "IdTestPlugin"

        mgr.register_plugin(mock_plugin, is_official=True)
        result = mgr.get_plugin_by_id("id-direct-test")
        assert result is mock_plugin

    def test_get_plugin_by_id_returns_none_for_unknown(self):
        """不存在的插件 ID 应返回 None"""
        mgr = PluginManager()
        assert mgr.get_plugin_by_id("non-existent-id") is None

    def test_get_plugin_id_by_type_id_returns_uuid(self):
        """可通过 plugin_info.plugin_type_id 查询到对应的 plugin_id"""
        mgr = PluginManager()
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "id-type-test"
        mock_plugin.plugin_name = "TypeTestPlugin"
        mock_plugin.plugin_info = MagicMock()
        mock_plugin.plugin_info.plugin_type_id = "my-unique-type"

        mgr.register_plugin(mock_plugin, is_official=False)
        result = mgr.get_plugin_id_by_type_id("my-unique-type")
        assert result == "id-type-test"

    def test_get_plugin_id_by_type_id_returns_none_for_unknown(self):
        """不存在的 plugin_type_id 应返回 None"""
        mgr = PluginManager()
        assert mgr.get_plugin_id_by_type_id("non-existent-type-id") is None


# ============================================================================
# 5. apply_custom_order 测试
# ============================================================================

class TestApplyCustomOrder:
    """验证插件排序逻辑"""

    def test_apply_custom_order_orders_plugins_correctly(self, mocker):
        """
        apply_custom_order() 应按配置文件中的 UUID 顺序排序，
        并将未列入配置的新插件追加到末尾。
        """
        mgr = PluginManager()

        # 注册三个插件
        p1 = MagicMock(plugin_id="uuid-1", plugin_name="P1")
        p2 = MagicMock(plugin_id="uuid-2", plugin_name="P2")
        p3 = MagicMock(plugin_id="uuid-3", plugin_name="P3")

        for p in [p1, p2, p3]:
            mgr.register_plugin(p, is_official=True)

        # Mock 配置：仅指定 uuid-2, uuid-1（p3 追加到末尾）
        mock_config = {
            "official_plugins": ["uuid-2", "uuid-1"],
            "thirdparty_plugins": []
        }
        mocker.patch.object(
            mgr.config_manager, "load_plugin_order", return_value=mock_config
        )

        mgr.apply_custom_order()

        # 顺序应为 uuid-2, uuid-1, uuid-3（p3 为新插件，追加）
        assert mgr._official_plugins[0].plugin_id == "uuid-2"
        assert mgr._official_plugins[1].plugin_id == "uuid-1"
        assert mgr._official_plugins[2].plugin_id == "uuid-3"

    def test_apply_custom_order_with_empty_config_appends_all(self, mocker):
        """配置文件为空时应保留原始顺序（所有插件均视为新增）"""
        mgr = PluginManager()

        p1 = MagicMock(plugin_id="uid-a", plugin_name="A")
        p2 = MagicMock(plugin_id="uid-b", plugin_name="B")
        for p in [p1, p2]:
            mgr.register_plugin(p, is_official=True)

        mocker.patch.object(
            mgr.config_manager, "load_plugin_order",
            return_value={"official_plugins": [], "thirdparty_plugins": []}
        )

        mgr.apply_custom_order()
        assert [p.plugin_id for p in mgr._official_plugins] == ["uid-a", "uid-b"]


# ============================================================================
# 6. save_plugin_order 测试
# ============================================================================

class TestSavePluginOrder:
    """验证插件顺序持久化"""

    def test_save_plugin_order_delegates_to_config_manager(self, mocker):
        """save_plugin_order() 应将调用委托给 config_manager.save_plugin_order()"""
        mgr = PluginManager()
        mock_save = mocker.patch.object(
            mgr.config_manager, "save_plugin_order", return_value=True
        )

        mgr.save_plugin_order(
            official_plugin_ids=["id1", "id2"],
            thirdparty_plugin_ids=["id3"]
        )

        mock_save.assert_called_once_with(["id1", "id2"], ["id3"])


# ============================================================================
# 7. register_plugin_api / unregister_plugin_api / get_plugin_api 测试
# ============================================================================

class TestPluginApiManagement:
    """验证插件 API 的注册、注销和查询"""

    def test_register_plugin_api_raises_valueerror_for_unknown_plugin(self):
        """
        register_plugin_api() 在 plugin_id 未注册时应抛出 ValueError。
        """
        mgr = PluginManager()
        with pytest.raises(ValueError, match="不存在"):
            mgr.register_plugin_api(
                plugin_id="unknown-id",
                service_instance=MagicMock(),
                api_descriptions={}
            )

    def test_register_plugin_api_stores_api_entry(self):
        """register_plugin_api() 成功注册后应能在 _api_registry 中查到"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "api-plugin-id"
        mock_plugin.plugin_name = "ApiPlugin"
        mock_plugin.__class__.__name__ = "ApiPluginClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mock_service = MagicMock()
        mock_service.echo = MagicMock(return_value="hello")
        mgr.register_plugin_api(
            plugin_id="api-plugin-id",
            service_instance=mock_service,
            api_descriptions={"echo": {"description": "test"}}
        )

        api_entry = mgr._api_registry.get("api-plugin-id")
        assert api_entry is not None
        assert api_entry.plugin_id == "api-plugin-id"
        assert "echo" in api_entry.api_methods

    def test_unregister_plugin_api_removes_entry(self):
        """unregister_plugin_api() 应从 _api_registry 中删除对应条目"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "unreg-plugin-id"
        mock_plugin.plugin_name = "UnregPlugin"
        mock_plugin.__class__.__name__ = "UnregClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mgr.register_plugin_api(
            plugin_id="unreg-plugin-id",
            service_instance=MagicMock(),
            api_descriptions={}
        )
        assert "unreg-plugin-id" in mgr._api_registry

        mgr.unregister_plugin_api("unreg-plugin-id")
        assert "unreg-plugin-id" not in mgr._api_registry

    def test_get_plugin_api_returns_dict(self):
        """get_plugin_api() 应返回包含 plugin_id、plugin_name、methods 等字段的字典"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "get-api-id"
        mock_plugin.plugin_name = "GetApiPlugin"
        mock_plugin.__class__.__name__ = "GetApiClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mgr.register_plugin_api(
            plugin_id="get-api-id",
            service_instance=MagicMock(),
            api_descriptions={"echo": {"description": "say hello"}}
        )

        result = mgr.get_plugin_api("get-api-id")
        assert result is not None
        assert result["plugin_id"] == "get-api-id"
        assert result["plugin_name"] == "GetApiPlugin"
        assert "echo" in result["methods"]

    def test_get_plugin_api_returns_none_for_unknown(self):
        """get_plugin_api() 在 plugin_id 不存在时应返回 None"""
        mgr = PluginManager()
        assert mgr.get_plugin_api("non-existent-api-id") is None


# ============================================================================
# 8. call_plugin_method 测试
# ============================================================================

class TestCallPluginMethod:
    """验证跨插件方法调用"""

    def test_call_plugin_method_normal_call_succeeds(self):
        """正常调用应返回方法返回值"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "call-plugin-id"
        mock_plugin.plugin_name = "CallPlugin"
        mock_plugin.__class__.__name__ = "CallClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mock_service = MagicMock()
        mock_service.echo = MagicMock(return_value="response")
        mgr.register_plugin_api(
            plugin_id="call-plugin-id",
            service_instance=mock_service,
            api_descriptions={"echo": {"description": "echo"}}
        )

        result = mgr.call_plugin_method(
            caller_id="caller", plugin_id="call-plugin-id", method_name="echo", text="hello"
        )
        assert result == "response"
        mock_service.echo.assert_called_once_with(text="hello")

    def test_call_plugin_method_raises_valueerror_for_missing_plugin(self):
        """调用未注册的 plugin_id 应抛出 ValueError"""
        mgr = PluginManager()
        with pytest.raises(ValueError, match="未注册"):
            mgr.call_plugin_method(
                caller_id="caller", plugin_id="nonexistent-id", method_name="echo"
            )

    def test_call_plugin_method_raises_valueerror_for_missing_method(self):
        """调用不存在的方法名应抛出 ValueError"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "no-method-id"
        mock_plugin.plugin_name = "NoMethodPlugin"
        mock_plugin.__class__.__name__ = "NoMethodClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mgr.register_plugin_api(
            plugin_id="no-method-id",
            service_instance=MagicMock(),
            api_descriptions={}
        )

        with pytest.raises(ValueError, match="没有方法"):
            mgr.call_plugin_method(
                caller_id="caller", plugin_id="no-method-id", method_name="missing_method"
            )

    def test_call_plugin_method_wraps_handler_exception_in_runtime_error(self):
        """方法内部抛出的异常应被包装为 RuntimeError"""
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "error-plugin-id"
        mock_plugin.plugin_name = "ErrorPlugin"
        mock_plugin.__class__.__name__ = "ErrorClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        def raising_method():
            raise ValueError("original error")

        mock_service = MagicMock()
        mock_service.raising = raising_method
        mgr.register_plugin_api(
            plugin_id="error-plugin-id",
            service_instance=mock_service,
            api_descriptions={"raising": {"description": "raises"}}
        )

        with pytest.raises(RuntimeError, match="original error"):
            mgr.call_plugin_method(
                caller_id="caller", plugin_id="error-plugin-id", method_name="raising"
            )


# ============================================================================
# 9. get_all_function_tools 测试
# ============================================================================

class TestGetAllFunctionTools:
    """验证 MCP 格式函数工具列表生成"""

    def test_get_all_function_tools_produces_mcp_format(self):
        """
        get_all_function_tools() 应返回符合 MCP 规范的列表，
        每个工具包含 type="function"、function.name、function.description、
        function.parameters 等字段。
        """
        mgr = PluginManager()

        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "tools-plugin-id"
        mock_plugin.plugin_name = "ToolsPlugin"
        mock_plugin.__class__.__name__ = "ToolsClass"
        mgr.register_plugin(mock_plugin, is_official=False)

        mock_service = MagicMock()
        mock_service.echo = MagicMock()
        mgr.register_plugin_api(
            plugin_id="tools-plugin-id",
            service_instance=mock_service,
            api_descriptions={
                "echo": {
                    "description": "echo a message",
                    "parameters": {
                        "text": {"type": "str", "description": "message to echo", "required": True}
                    },
                    "returns": {"type": "str"}
                }
            }
        )

        tools = mgr.get_all_function_tools()

        assert len(tools) == 1
        tool = tools[0]
        assert tool["type"] == "function"
        assert "tools-plugin-id.echo" in tool["function"]["name"]
        assert "ToolsPlugin" in tool["function"]["description"]
        assert "echo a message" in tool["function"]["description"]
        assert "text" in tool["function"]["parameters"]["properties"]
        assert "required" in tool["function"]["parameters"]

    def test_get_all_function_tools_empty_when_no_apis(self):
        """没有任何 API 注册时，应返回空列表"""
        mgr = PluginManager()
        assert mgr.get_all_function_tools() == []


# ============================================================================
# 10. reload_plugins 测试
# ============================================================================

class TestReloadPlugins:
    """验证插件重新加载功能"""

    def test_reload_plugins_clears_all_registries_and_rescans(self, mocker, plugin_dir_from_test):
        """
        reload_plugins() 应清空 _official_plugins、_thirdparty_plugins、
        _plugin_registry、_plugin_name_to_id、_api_registry，
        然后重新扫描插件目录。
        """
        # 创建并注册一个插件
        plugin_dir_from_test.mkdir(parents=True, exist_ok=True)
        test_plugin_dir = plugin_dir_from_test / "reload_test_plugin"
        create_minimal_plugin(
            test_plugin_dir,
            plugin_name="ReloadTestPlugin",
            has_service=True,
            service_methods=["echo"],
            has_information=True
        )

        mgr = PluginManager()
        # official_plugin_dir 和 thirdparty_plugin_dir 是实例属性，直接赋值
        mgr.official_plugin_dir = plugin_dir_from_test
        # thirdparty 使用不同目录，避免与 official 混用同一目录导致插件被重复加载
        mgr.thirdparty_plugin_dir = plugin_dir_from_test.parent / "thirdparty_empty"
        mgr.thirdparty_plugin_dir.mkdir(parents=True, exist_ok=True)
        mgr.load_plugins()

        # 验证插件已加载
        assert len(mgr._plugin_registry) > 0

        original_registry_keys = set(mgr._plugin_registry.keys())
        original_name_keys = set(mgr._plugin_name_to_id.keys())

        # reload 前再次注册一个 API（验证 _api_registry 也被清空）
        mock_plugin = MagicMock()
        mock_plugin.plugin_id = "manual-plugin-id"
        mock_plugin.plugin_name = "ManualPlugin"
        mock_plugin.__class__.__name__ = "ManualClass"
        mgr.register_plugin(mock_plugin, is_official=False)
        mgr.register_plugin_api(
            "manual-plugin-id",
            service_instance=MagicMock(),
            api_descriptions={"manual": {"description": "manual"}}
        )

        assert "manual-plugin-id" in mgr._api_registry

        # 执行 reload
        mgr.reload_plugins()

        # 所有注册表应被清空并重新加载
        assert len(mgr._official_plugins) > 0
        assert len(mgr._thirdparty_plugins) == 0  # 临时目录无第三方插件
        assert len(mgr._plugin_registry) > 0
        assert len(mgr._plugin_name_to_id) > 0
        # reload 后只有目录中的插件，手动注册的 API 应消失
        assert "manual-plugin-id" not in mgr._api_registry
