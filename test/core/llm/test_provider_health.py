"""Provider 真实健康、后台刷新和熔断恢复测试。"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from core.interfaces.health import HealthStatus
from core.llm.llm_provider import LLMProvider
from core.llm.provider_interface import ChatResponse, ModelInfo
from core.llm.provider_supervisor import ProviderSupervisor


class ControlledProvider:
    """可控 Provider，真实执行严格刷新、聊天和流式路径。"""

    def __init__(self):
        self.models = [ModelInfo(id="m1", name="m1")]
        self.refresh_error = None
        self.refresh_calls = 0
        self.timeout = 60
        self.chat_calls = []
        self.chat_model = "m1"

    def refresh_models(self, force=False):
        self.refresh_calls += 1
        if self.refresh_error:
            raise self.refresh_error
        return list(self.models)

    def refresh_models_strict(self, force=False):
        return self.refresh_models(force)

    def chat(self, messages, model=None, **kwargs):
        self.chat_calls.append(kwargs)
        return ChatResponse(content="ok", model=model or "m1")

    def close(self):
        return None


def make_manager(provider):
    """以隔离配置构造 LLMProvider 和 supervisor，不访问真实配置。"""
    manager = object.__new__(LLMProvider)
    manager._providers = {"p": provider}
    manager._models_cache = {}
    manager._config = MagicMock()
    manager._config.version = 0
    manager._health = {}
    manager._logger = MagicMock()
    manager._loaded_config_version = 0
    manager._stream_local = threading.local()
    manager._supervisor = ProviderSupervisor(manager)
    return manager


def test_failed_refresh_is_not_healthy_empty_success():
    """严格刷新失败必须返回不健康，不能伪装为空模型成功。"""
    provider = ControlledProvider()
    provider.refresh_error = ConnectionError("网络不可达")
    manager = make_manager(provider)
    ok, error, count = manager.check_provider("p")
    assert not ok
    assert count == 0
    assert "网络不可达" in error
    assert manager.get_provider_health("p")[0] is False


def test_startup_returns_before_slow_refresh_finishes():
    """启动只读缓存，慢远程刷新在后台完成，不阻塞调用方。"""
    provider = ControlledProvider()
    manager = make_manager(provider)
    original_refresh = provider.refresh_models
    provider.refresh_models = lambda force=False: (time.sleep(0.5) or original_refresh(force))
    started = time.monotonic()
    manager._fetch_all_models()
    assert time.monotonic() - started < 0.2
    deadline = time.monotonic() + 2
    while provider.refresh_calls < 1:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert provider.refresh_calls >= 1


def test_circuit_opens_and_recovers_after_timeout():
    """连续失败触发熔断，恢复窗口后允许半开成功并重置健康。"""
    provider = ControlledProvider()
    provider.refresh_error = ConnectionError("持续失败")
    manager = make_manager(provider)
    manager._supervisor.RECOVERY_SECONDS = 0.02
    for _ in range(3):
        assert not manager.check_provider_detailed("p").ok
    circuit_result = manager.check_provider_detailed("p")
    assert not circuit_result.ok
    assert "熔断" in circuit_result.error
    provider.refresh_error = None
    time.sleep(0.03)
    result = manager.check_provider_detailed("p")
    assert result.ok
    assert result.status is HealthStatus.HEALTHY
    assert manager.get_provider_health("p") == (True, None)
