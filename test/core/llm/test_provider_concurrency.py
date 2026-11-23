"""请求级超时、请求 ID 和流式指标并发测试。"""

import importlib.util
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.llm.llm_provider import LLMProvider
from core.llm.provider_supervisor import ProviderSupervisor


_spec = importlib.util.spec_from_file_location(
    "test_provider_health", Path(__file__).with_name("test_provider_health.py")
)
_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_health)
ControlledProvider = _health.ControlledProvider
make_manager = _health.make_manager


def test_concurrent_probe_timeouts_do_not_mutate_shared_timeout():
    """并发探测使用各自 request_timeout，共享 Provider.timeout 始终不变。"""
    provider = ControlledProvider()
    manager = make_manager(provider)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(manager.check_model, "p", "m1", 0.01),
            executor.submit(manager.check_model, "p", "m1", 0.02),
        ]
        results = [future.result(timeout=5) for future in futures]
    assert all(result.ok for result in results)
    assert provider.timeout == 60
    seen = {call["request_timeout"] for call in provider.chat_calls}
    assert seen == {0.01, 0.02}


def test_chat_assigns_request_id_and_does_not_put_timeout_in_payload():
    """请求携带唯一 request_id 和请求级 timeout，不写入模型业务载荷。"""
    provider = ControlledProvider()
    manager = make_manager(provider)
    manager.chat([{"role": "user", "content": "hi"}], provider="p", request_timeout=0.01)
    manager.chat([{"role": "user", "content": "hi"}], provider="p", request_timeout=0.02)
    first, second = provider.chat_calls
    assert first["request_timeout"] == 0.01
    assert second["request_timeout"] == 0.02
    assert first["request_id"] != second["request_id"]


def test_stream_metrics_capture_first_token_and_interruption():
    """流式路径记录首 token、总耗时和异常中断原因。"""
    provider = ControlledProvider()
    manager = make_manager(provider)

    def failing_stream(messages, **kwargs):
        yield type("Chunk", (), {"content": "首块", "model": "m1", "tool_calls": []})()
        raise ConnectionError("流中断")

    provider.stream_chat = failing_stream
    try:
        manager.stream_chat([{"role": "user", "content": "hi"}], provider="p")
    except ConnectionError as error:
        assert "流中断" in str(error)
    metrics = manager.last_stream_metrics
    assert metrics["first_token_ms"] is not None
    assert metrics["duration_ms"] >= 0
    assert "流中断" in metrics["interruption"]


def test_stream_success_metrics_have_no_interruption():
    """正常流式完成记录首 token 和总耗时，中断原因为空。"""
    provider = ControlledProvider()
    manager = make_manager(provider)

    def successful_stream(messages, **kwargs):
        yield type("Chunk", (), {"content": "完成", "model": "m1", "tool_calls": []})()

    provider.stream_chat = successful_stream
    assert manager.stream_chat([{"role": "user", "content": "hi"}], provider="p") == "完成"
    metrics = manager.last_stream_metrics
    assert metrics["first_token_ms"] is not None
    assert metrics["duration_ms"] >= 0
    assert metrics["interruption"] is None
