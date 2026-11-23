"""适配器注册表测试（core/llm/providers/__init__.py）

覆盖：adapter 键查类、未注册异常路径、旧名薄别名等价、
同 adapter 多实例共存。
"""

import pytest

from core.llm.llm_provider import LLMProvider
from core.llm.providers import (
    PROVIDER_REGISTRY,
    BaseProvider,
    GLMProvider,
    get_adapter_class,
    get_all_adapters,
    get_all_provider_types,
    get_provider_class,
    register_adapter,
    register_provider,
)

# 内置适配器家族键全集
BUILTIN_ADAPTERS = {
    "minimax", "siliconflow", "glm", "ollama", "openai", "openai-compatible",
}


class TestAdapterRegistry:
    """适配器家族注册表"""

    def test_builtin_adapters_registered(self):
        """内置 6 个适配器家族键全部注册，且映射到 BaseProvider 子类"""
        assert BUILTIN_ADAPTERS <= set(get_all_adapters())
        for key in BUILTIN_ADAPTERS:
            cls = get_adapter_class(key)
            assert cls is not None
            assert issubclass(cls, BaseProvider)

    def test_unknown_adapter_returns_none(self):
        """查询未注册的 adapter 键返回 None（异常路径不抛异常）"""
        assert get_adapter_class("no-such-adapter") is None

    def test_register_adapter_roundtrip(self):
        """register_adapter 注册新键可查，返回原类（可作装饰器）"""
        key = "temp-test-adapter"
        try:
            result = register_adapter(key, GLMProvider)
            assert result is GLMProvider
            assert get_adapter_class(key) is GLMProvider
            assert key in get_all_adapters()
        finally:
            PROVIDER_REGISTRY.pop(key, None)

    def test_legacy_aliases_equivalent(self):
        """旧名薄别名与新函数语义一致（适配器家族）"""
        assert get_provider_class("glm") is get_adapter_class("glm")
        assert get_all_provider_types() == get_all_adapters()
        # register_provider 按类的 provider_type 类属性注册（重注册内置类幂等）
        assert register_provider(GLMProvider) is GLMProvider
        assert PROVIDER_REGISTRY["glm"] is GLMProvider


class TestMultiInstanceSameAdapter:
    """同一 adapter 多实例共存"""

    def test_two_instances_share_adapter(self, mock_config_factory):
        """两个实例共用 mock-adapter，运行时各自独立创建"""
        llm = LLMProvider()
        llm.add_provider("inst-1", mock_config_factory(name="实例一"))
        llm.add_provider("inst-2", mock_config_factory(name="实例二"))
        providers = llm.get_all_providers()
        assert set(providers) == {"inst-1", "inst-2"}
        assert providers["inst-1"] is not providers["inst-2"]

    def test_unknown_adapter_instance_skipped(self, mock_config_factory):
        """未知 adapter 的实例被跳过且不崩溃，不影响其余实例"""
        llm = LLMProvider()
        bad = mock_config_factory(name="坏实例")
        bad.adapter = "no-such-adapter"
        llm.add_provider("bad-1", bad)
        llm.add_provider("good-1", mock_config_factory(name="好实例"))
        providers = llm.get_all_providers()
        assert "bad-1" not in providers
        assert "good-1" in providers
