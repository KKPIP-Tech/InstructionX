"""Provider 模型刷新、健康结果和可恢复熔断调度。"""

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, Optional

from core.interfaces.health import HealthStatus
from .provider_interface import ModelInfo


@dataclass(frozen=True, slots=True)
class ProviderCheckResult:
    """Provider 连通性详细结果，区分真实成功、空模型和失败。"""

    ok: bool
    model_count: int
    error: Optional[str]
    status: HealthStatus
    models: tuple[ModelInfo, ...] = ()


class ProviderCircuitOpenError(Exception):
    """熔断窗口内拒绝刷新，避免持续打击故障 Provider。"""


class ProviderSupervisor:
    """后台刷新模型并管理失败计数、熔断和半开恢复。"""

    FAILURE_THRESHOLD = 3
    RECOVERY_SECONDS = 30.0
    MAX_WORKERS = 4

    def __init__(self, owner):
        self._owner = owner
        self._executor = ThreadPoolExecutor(
            max_workers=self.MAX_WORKERS, thread_name_prefix="ProviderSupervisor"
        )
        self._lock = threading.RLock()
        self._futures: Dict[str, Future] = {}
        self._failures: Dict[str, int] = {}
        self._open_until: Dict[str, float] = {}

    def refresh_models_async(self, provider_id: str, force: bool = True) -> Future:
        """提交后台刷新并返回 Future；熔断期返回已失败 Future。"""
        with self._lock:
            existing = self._futures.get(provider_id)
            if existing is not None and not existing.done():
                return existing
            if self._is_open(provider_id):
                future = Future()
                future.set_exception(ProviderCircuitOpenError(f"Provider {provider_id} 处于熔断期"))
                return future
            future = self._executor.submit(self._refresh, provider_id, force)
            self._futures[provider_id] = future
            future.add_done_callback(lambda done: self._finish(provider_id, done))
        return future

    def refresh_all_async(self, force: bool = True) -> Dict[str, Future]:
        """并行提交全部 Provider，单实例失败不阻塞其他实例。"""
        return {
            provider_id: self.refresh_models_async(provider_id, force)
            for provider_id in self._owner.get_all_providers()
        }

    def _refresh(self, provider_id: str, force: bool):
        provider = self._owner.get_provider(provider_id)
        if provider is None:
            raise ValueError(f"提供商实例不存在: {provider_id}")
        strict = getattr(provider, "refresh_models_strict", None)
        models = strict(force=force) if callable(strict) else provider.refresh_models(force=force)
        self._owner._models_cache[provider_id] = models
        self._owner._config.save_models_cache(
            provider_id, [model.to_dict() for model in models]
        )
        self._owner._health[provider_id] = (True, None)
        return models

    def _finish(self, provider_id: str, future: Future) -> None:
        error = future.exception()
        with self._lock:
            self._futures.pop(provider_id, None)
            if error is None:
                self._failures.pop(provider_id, None)
                self._open_until.pop(provider_id, None)
            else:
                failures = self._failures.get(provider_id, 0) + 1
                self._failures[provider_id] = failures
                if failures >= self.FAILURE_THRESHOLD:
                    self._open_until[provider_id] = time.monotonic() + self.RECOVERY_SECONDS
                self._owner._health[provider_id] = (False, str(error))

    def _is_open(self, provider_id: str) -> bool:
        deadline = self._open_until.get(provider_id)
        if deadline is None:
            return False
        if time.monotonic() >= deadline:
            self._open_until.pop(provider_id, None)
            self._failures[provider_id] = 0
            return False
        return True

    def close(self) -> None:
        """停止接受新刷新，不等待外部网络请求完成。"""
        self._executor.shutdown(wait=False, cancel_futures=True)
