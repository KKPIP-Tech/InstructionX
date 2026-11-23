"""会话 API 测试（LLMPluginService 会话管理）

覆盖：create/send/stream/get/list/delete 全流程、返回类型一致性、
model/provider 临时覆盖、Message.from_dict 宽松解析、用量统计。
"""

import pytest

from core.llm.config import get_llm_config
from core.llm.llm_provider import get_llm_provider
from core.llm.plugin_service import LLMPluginService
from core.llm.provider_interface import UsageInfo

# 用量断言样本 token 数
SAMPLE_INPUT_TOKENS = 10
SAMPLE_OUTPUT_TOKENS = 5


def _make_service_with_instance(mock_config_factory, **factory_kwargs):
    """构造服务 + 一个 mock 实例，返回 (service, provider 适配器实例)"""
    get_llm_config().add_provider("mock-1", mock_config_factory())
    service = LLMPluginService()
    provider = get_llm_provider().get_provider("mock-1")
    return service, provider


class TestConversationLifecycle:
    """会话全流程"""

    def test_full_lifecycle(self, mock_config_factory):
        """create/send/get/list/delete 全流程正常路径"""
        service, _ = _make_service_with_instance(mock_config_factory)
        conv_id = service.create_conversation(
            system_prompt="你是助手", provider="mock-1")
        assert isinstance(conv_id, str) and conv_id
        reply = service.send_message(conv_id, "你好")
        assert isinstance(reply, str) and reply == "mock 回复"
        conv = service.get_conversation(conv_id)
        assert conv is not None
        # 历史自动追加（user + assistant）
        assert [m["role"] for m in conv.messages] == ["user", "assistant"]
        assert service.list_conversations()[0].id == conv_id
        assert service.delete_conversation(conv_id) is True
        assert service.get_conversation(conv_id) is None

    def test_send_to_missing_conversation_raises(self, mock_config_factory):
        """向不存在的会话发送消息抛 ValueError（异常路径）"""
        service, _ = _make_service_with_instance(mock_config_factory)
        with pytest.raises(ValueError):
            service.send_message("not-exist-conv", "hi")

    def test_temporary_override_keeps_binding(self, mock_config_factory):
        """send_message 的 model/provider 临时覆盖不修改会话绑定"""
        get_llm_config().add_provider("mock-1", mock_config_factory(order=0))
        get_llm_config().add_provider(
            "mock-2", mock_config_factory(name="实例二", order=1))
        service = LLMPluginService()
        conv_id = service.create_conversation(provider="mock-1")
        service.send_message(
            conv_id, "临时换实例", provider="mock-2", model="other-model")
        conv = service.get_conversation(conv_id)
        # 会话绑定不变
        assert conv.provider == "mock-1"
        # 本次调用实际路由到 mock-2 且模型被覆盖
        provider2 = get_llm_provider().get_provider("mock-2")
        assert provider2.chat_calls[-1]["model"] == "other-model"
        assert get_llm_provider().get_provider("mock-1").chat_calls == []

    def test_stream_send_message(self, mock_config_factory):
        """流式发送：callback 逐块回调（StreamChunk 实填）+ 完整文本 + 历史追加"""
        service, _ = _make_service_with_instance(mock_config_factory)
        conv_id = service.create_conversation(provider="mock-1")
        chunks = []
        reply = service.stream_send_message(
            conv_id, "讲个故事", callback=chunks.append)
        assert reply == "mock 回复"
        # StreamChunk 字段实填：content / done / full_response
        assert chunks[0].content == "mock "
        assert chunks[0].done is False
        assert chunks[0].full_response == "mock "
        assert chunks[1].full_response == "mock 回复"
        # Mock 两块 + 无 finish_reason 时的补发结束块
        assert chunks[-1].done is True
        conv = service.get_conversation(conv_id)
        assert conv.messages[-1] == {"role": "assistant", "content": "mock 回复"}


class TestMessageLenientParsing:
    """dict 消息宽松解析"""

    def test_dict_messages_with_extended_keys(self, mock_config_factory):
        """含 images/tool_calls 扩展键的 dict 消息经 chat 不炸"""
        service, _ = _make_service_with_instance(mock_config_factory)
        response = service.chat([
            {"role": "user", "content": "看图", "images": ["aGVsbG8="]},
            {"role": "assistant", "content": "", "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "search", "arguments": "{}"},
            }]},
            {"role": "tool", "tool_call_id": "call_1", "content": "结果"},
            {"role": "user", "content": "继续"},
        ], provider="mock-1")
        assert response.content == "mock 回复"
        # 消息透传到底层（Message 对象经 to_dict 序列化）
        provider = get_llm_provider().get_provider("mock-1")
        sent = provider.chat_calls[-1]["messages"]
        assert sent[0].images == ["aGVsbG8="]
        assert sent[1].tool_calls[0].name == "search"

    def test_unknown_keys_go_extra(self, mock_config_factory):
        """未知键收入 extra，不影响调用（边界）"""
        service, _ = _make_service_with_instance(mock_config_factory)
        response = service.chat(
            [{"role": "user", "content": "hi", "custom_field": 1}],
            provider="mock-1")
        assert response.content == "mock 回复"


class TestUsageStats:
    """用量统计"""

    def test_usage_accumulated(self, mock_config_factory):
        """带 UsageInfo 的响应自动累计 token 与费用统计"""
        service, provider = _make_service_with_instance(mock_config_factory)
        provider.chat_usage = UsageInfo(
            input_tokens=SAMPLE_INPUT_TOKENS,
            output_tokens=SAMPLE_OUTPUT_TOKENS,
            total_tokens=SAMPLE_INPUT_TOKENS + SAMPLE_OUTPUT_TOKENS,
        )
        conv_id = service.create_conversation(provider="mock-1")
        service.send_message(conv_id, "一次请求")
        stats = service.get_usage_stats(conv_id)
        assert stats.total_tokens == SAMPLE_INPUT_TOKENS + SAMPLE_OUTPUT_TOKENS
        assert stats.request_count == 2  # user + assistant 两条消息
        # 全局统计可用；不存在的会话返回 None（边界）
        assert service.get_usage_stats() is not None
        assert service.get_usage_stats("not-exist") is None
