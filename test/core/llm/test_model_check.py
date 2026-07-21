"""check_provider / check_model 连通性探测测试（core/llm/llm_provider.py）

覆盖：chat / embed 两种探测路径、成功 / 异常 / 跳过三路径、
超时临时覆盖与恢复、模型缓存写入。
"""

from core.llm.llm_provider import (
    MODEL_CHECK_DEFAULT_TIMEOUT,
    LLMProvider,
)
from core.llm.provider_interface import ModelCheckResult

from llm_v2_helpers import (
    MOCK_CHAT_MODEL_ID, MOCK_EMBEDDING_MODEL_ID, MOCK_INITIAL_TIMEOUT,
)

# 探测参数契约（与 llm_provider 模块常量一致）
PROBE_TEXT = "hi"
PROBE_MAX_TOKENS = 1
PROBE_TEMPERATURE = 0.0


def _ready_llm(mock_config_factory):
    """构造含一个 mock 实例的 LLMProvider 并完成模型缓存刷新"""
    llm = LLMProvider()
    llm.add_provider("mock-1", mock_config_factory())
    ok, error, count = llm.check_provider("mock-1")
    assert ok and count == 2
    return llm


class TestCheckModel:
    """单模型连通性探测"""

    def test_chat_probe_success(self, mock_config_factory):
        """聊天模型走 chat 最小请求探测：成功 + 延迟非负 + 探测参数契约"""
        llm = _ready_llm(mock_config_factory)
        result = llm.check_model("mock-1", MOCK_CHAT_MODEL_ID)
        assert isinstance(result, ModelCheckResult)
        assert result.ok is True
        assert result.error is None
        assert result.latency_ms is not None and result.latency_ms >= 0
        provider = llm.get_provider("mock-1")
        probe_call = provider.chat_calls[-1]
        assert probe_call["max_tokens"] == PROBE_MAX_TOKENS
        assert probe_call["temperature"] == PROBE_TEMPERATURE
        assert probe_call["messages"][0].content == PROBE_TEXT

    def test_embedding_model_uses_embed_probe(self, mock_config_factory):
        """声明嵌入能力的模型走 embed 探测（不走 chat）"""
        llm = _ready_llm(mock_config_factory)
        provider = llm.get_provider("mock-1")
        chat_calls_before = len(provider.chat_calls)
        result = llm.check_model("mock-1", MOCK_EMBEDDING_MODEL_ID)
        assert result.ok is True
        assert len(provider.chat_calls) == chat_calls_before
        assert provider.embed_calls[-1]["texts"] == [PROBE_TEXT]
        assert provider.embed_calls[-1]["model"] == MOCK_EMBEDDING_MODEL_ID

    def test_probe_failure_records_error(self, mock_config_factory):
        """探测抛异常：ok=False + error 非空 + 延迟非负（异常路径）"""
        llm = _ready_llm(mock_config_factory)
        provider = llm.get_provider("mock-1")
        provider.chat_error = RuntimeError("连接拒绝")
        result = llm.check_model("mock-1", MOCK_CHAT_MODEL_ID)
        assert result.ok is False
        assert "连接拒绝" in result.error
        assert result.latency_ms is not None and result.latency_ms >= 0

    def test_missing_instance_skipped(self, mock_config_factory):
        """实例不存在：skipped=True + 中文原因 + 无延迟（边界路径）"""
        llm = LLMProvider()
        result = llm.check_model("not-exist", "any-model")
        assert result.ok is False
        assert result.skipped is True
        assert result.latency_ms is None
        assert "not-exist" in result.skip_reason

    def test_timeout_override_and_restore(self, mock_config_factory):
        """timeout 经临时覆盖生效，探测结束后恢复原值"""
        llm = _ready_llm(mock_config_factory)
        provider = llm.get_provider("mock-1")
        assert provider.timeout == MOCK_INITIAL_TIMEOUT
        result = llm.check_model(
            "mock-1", MOCK_CHAT_MODEL_ID, timeout=MODEL_CHECK_DEFAULT_TIMEOUT)
        assert result.ok is True
        # 调用瞬间观测到的是覆盖值，结束后恢复原值
        assert provider.chat_calls[-1]["seen_timeout"] == (
            MODEL_CHECK_DEFAULT_TIMEOUT)
        assert provider.timeout == MOCK_INITIAL_TIMEOUT


class TestCheckProvider:
    """实例级连通性检查"""

    def test_success_returns_model_count_and_caches(
            self, mock_config_factory):
        """成功：返回模型数、更新模型缓存、记录健康"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        ok, error, count = llm.check_provider("mock-1")
        assert (ok, error, count) == (True, None, 2)
        cached = llm.get_cached_models("mock-1")
        assert {m.id for m in cached} == {
            MOCK_CHAT_MODEL_ID, MOCK_EMBEDDING_MODEL_ID}
        assert llm.get_provider_health("mock-1") == (True, None)

    def test_refresh_failure_returns_error(self, mock_config_factory):
        """拉取失败：返回错误信息并记录不健康（异常路径）"""
        llm = LLMProvider()
        llm.add_provider("mock-1", mock_config_factory())
        provider = llm.get_provider("mock-1")
        provider.refresh_error = ConnectionError("网络不可达")
        ok, error, count = llm.check_provider("mock-1")
        assert ok is False
        assert "网络不可达" in error
        assert count == 0
        assert llm.get_provider_health("mock-1")[0] is False

    def test_missing_instance(self):
        """实例不存在：返回 (False, 中文错误, 0)，不抛异常（边界路径）"""
        llm = LLMProvider()
        ok, error, count = llm.check_provider("not-exist")
        assert ok is False
        assert count == 0
        assert "not-exist" in error
