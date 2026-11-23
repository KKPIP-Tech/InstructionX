"""模型顺序刷新与故障隔离性能契约。"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.llm.llm_provider import LLMProvider
from core.llm.provider_interface import ModelInfo
from core.llm.provider_supervisor import ProviderSupervisor
from core.observability import register_sensitive_fields, sanitize_text


class _RefreshProvider:
    """可控刷新延迟与失败的 Provider 替身。"""

    def __init__(self, model_id: str, delay: float, error: Exception = None):
        self.model_id = model_id
        self.delay = delay
        self.error = error

    def refresh_models(self, force: bool):
        time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return [ModelInfo(id=self.model_id, name=self.model_id)]


def _llm_with_providers(providers):
    """构造仅含刷新依赖的 LLMProvider，避免读取真实配置或网络。"""
    llm = object.__new__(LLMProvider)
    llm._providers = providers
    llm._models_cache = {}
    llm._health = {}
    llm._logger = MagicMock()
    llm._config = SimpleNamespace(version=0, save_models_cache=MagicMock())
    llm._loaded_config_version = 0
    llm._supervisor = ProviderSupervisor(llm)
    return llm


def test_refresh_all_models_runs_sequentially_without_overlapping_refreshes():
    """按注册顺序逐个刷新，任意时刻最多一个 Provider 在执行。"""
    providers = {
        "fast": _RefreshProvider("fast-model", 0.08),
        "slow": _RefreshProvider("slow-model", 0.08),
    }
    active = [0, 0]
    lock = threading.Lock()

    def track(provider):
        original = provider.refresh_models

        def tracked(force):
            with lock:
                active[0] += 1
                active[1] = max(active)
            try:
                return original(force)
            finally:
                with lock:
                    active[0] -= 1

        provider.refresh_models = tracked

    for provider in providers.values():
        track(provider)
    llm = _llm_with_providers(providers)
    started = time.perf_counter()
    try:
        models = llm.refresh_all_models(timeout=0.01)
        elapsed = time.perf_counter() - started
        assert elapsed >= 0.15, (elapsed, active, models, llm._health, type(llm._supervisor._executor))
        assert active[1] == 1
        assert models["fast"][0].id == "fast-model"
        assert models["slow"][0].id == "slow-model"
    finally:
        llm._supervisor.close()


def test_refresh_all_models_single_failure_does_not_block_success():
    """一个 Provider 刷新失败不得阻止其他 Provider 更新缓存。"""
    providers = {
        "failed": _RefreshProvider("failed-model", 0.01, ConnectionError("离线")),
        "healthy": _RefreshProvider("healthy-model", 0.02),
    }
    llm = _llm_with_providers(providers)
    try:
        models = llm.refresh_all_models(timeout=0.10)
        assert models["healthy"][0].id == "healthy-model"
        assert llm._health["healthy"][0] is True
        assert llm._health["failed"][0] is False
    finally:
        llm._supervisor.close()



def test_sensitive_pattern_cache_invalidates_for_new_fields():
    """正则缓存建立后，新注册字段仍必须立即脱敏。"""
    sanitize_text("initial=1")
    register_sensitive_fields("performance_private_field")
    sanitized = sanitize_text("performance_private_field=secret-value")
    assert "secret-value" not in sanitized
    assert "performance_private_field" in sanitized
