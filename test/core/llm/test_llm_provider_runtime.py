"""LLMProvider 运行时测试（core/llm/llm_provider.py）

覆盖：adapter 分发、健康查询、配置版本惰性刷新、默认实例解析与
粘性缓存、实例增删同步。
"""

import pytest

from core.llm.config import LLMConfig, get_llm_config
from core.llm.exceptions import ConfigurationError
from core.llm.llm_provider import LLMProvider, get_llm_provider
from core.llm.provider_interface import Message
from core.llm.types import DEFAULT_PROVIDER


class TestEmptyConfig:
    """空配置的优雅处理"""

    def test_empty_config_basics(self):
        """空配置：初始化不崩、无启用实例、默认解析为 None"""
        llm = LLMProvider()
        assert llm.get_enabled_providers() == {}
        assert llm.get_default_provider_id() is None
        assert llm.get_all_providers() == {}

    def test_chat_without_provider_raises(self):
        """空配置 chat 抛出 ConfigurationError（异常路径）"""
        llm = LLMProvider()
        with pytest.raises(ConfigurationError):
            llm.chat([Message(role="user", content="hi")])


class TestAdapterDispatch:
    """按 adapter 分发创建实例"""

    def test_create_provider_by_adapter(self, mock_config_factory):
        """_create_provider 按 adapter 键查注册表创建实例"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        provider = llm.get_provider("mock-1")
        assert provider is not None
        assert provider.provider_type == "mock-adapter"

    def test_get_llm_provider_singleton(self):
        """get_llm_provider() 返回单例"""
        assert get_llm_provider() is LLMProvider()


class TestHealthTracking:
    """健康状态查询（get_provider_health 签名修复回归）"""

    def test_health_full_dict_when_none(self, mock_config_factory):
        """name=None 返回全量健康字典（修复前端零参调用被吞的回归）"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        llm.add_provider("mock-2", mock_config_factory(name="实例二"))
        health = llm.get_provider_health()
        assert isinstance(health, dict)
        assert set(health) == {"mock-1", "mock-2"}
        # 未调用过的实例默认健康
        assert health["mock-1"] == (True, None)

    def test_health_single_and_failure_recorded(self, mock_config_factory):
        """带参返回单个元组；调用失败后记录 (False, 错误)"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        assert llm.get_provider_health("mock-1") == (True, None)
        provider = llm.get_provider("mock-1")
        provider.chat_error = RuntimeError("模拟故障")
        with pytest.raises(RuntimeError):
            llm.chat([Message(role="user", content="hi")], provider="mock-1")
        ok, error = llm.get_provider_health("mock-1")
        assert ok is False
        assert "模拟故障" in error
        # 全量字典同步反映失败
        assert llm.get_provider_health()["mock-1"][0] is False


class TestLazyRefresh:
    """配置版本比对惰性刷新"""

    def test_entry_refreshes_after_config_change(self, mock_config_factory):
        """经 LLMConfig 直接增配后，公开入口自动刷新（无需手动 reload）"""
        llm = LLMProvider()
        assert "mock-1" not in llm.get_all_providers()
        # 绕过 LLMProvider.add_provider，直接改配置（模拟外部编辑落盘）
        get_llm_config().add_provider("mock-1", mock_config_factory())
        # get_cached_models 入口比对 config.version 触发惰性刷新
        llm.get_cached_models("mock-1")
        assert "mock-1" in llm.get_all_providers()

    def test_lazy_refresh_syncs_version(self, mock_config_factory):
        """惰性刷新后版本号同步，不重复全量刷新"""
        llm = LLMProvider()
        config = get_llm_config()
        config.add_provider("mock-1", mock_config_factory())
        llm.get_cached_models("mock-1")
        assert llm._loaded_config_version == config.version


class TestDefaultProviderResolution:
    """默认实例解析与粘性缓存"""

    def test_default_resolution_and_sticky_cache(self, mock_config_factory):
        """DEFAULT_PROVIDER 解析为首个启用实例并粘性记忆"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory(order=1))
        llm.add_provider("mock-2", mock_config_factory(name="实例二", order=0))
        resolved = llm.get_default_provider_id("chat")
        assert resolved in {"mock-1", "mock-2"}
        # 粘性缓存：再次解析结果一致
        assert llm.get_default_provider_id("chat") == resolved
        # DEFAULT_PROVIDER 常量与 "default" 字面量行为一致
        assert llm.resolve_provider_name(DEFAULT_PROVIDER) == resolved
        assert llm.resolve_provider_name("default") == resolved
        # 非默认引用原样返回
        assert llm.resolve_provider_name("mock-1") == "mock-1"

    def test_default_reselected_after_removal(self, mock_config_factory):
        """默认实例被移除后自动重新选择"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory(order=0))
        llm.add_provider("mock-2", mock_config_factory(name="实例二", order=1))
        first = llm.get_default_provider_id("chat")
        llm.remove_provider(first)
        assert llm.get_default_provider_id("chat") is not None
        assert llm.get_default_provider_id("chat") != first


class TestAddRemoveSync:
    """实例增删的运行时同步"""

    def test_add_remove_provider_runtime(self, mock_config_factory):
        """add/remove 后运行时实例表同步增删，健康状态清理"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        assert "mock-1" in llm.get_all_providers()
        assert llm.remove_provider("mock-1") is True
        assert "mock-1" not in llm.get_all_providers()
        assert "mock-1" not in llm.get_provider_health()
        # 配置层同步删除（落盘）
        assert get_llm_config().get_provider("mock-1") is None

    def test_add_then_chat_uses_mock_adapter(self, mock_config_factory):
        """新增实例后 chat 路由到 Mock 适配器（正常路径）"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        response = llm.chat(
            [Message(role="user", content="hi")], provider="mock-1")
        assert response.content == "mock 回复"
        provider = llm.get_provider("mock-1")
        assert len(provider.chat_calls) == 1
