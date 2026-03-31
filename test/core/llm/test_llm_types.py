"""pytest tests for core/llm/types.py domain types."""

import pytest
from datetime import datetime

from core.llm.types import (
    Conversation,
    ToolResult,
    UsageStats,
    ImageResult,
    AudioResult,
    ProviderInfo,
    StreamChunk,
)
from core.llm.provider_interface import UsageInfo


def make_conv():
    return Conversation(
        id="test-id",
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        updated_at=datetime(2024, 1, 1, 0, 0, 0),
    )


class TestConversationToLlmFormat:
    """Test Conversation.to_llm_format() behavior."""

    def test_without_system_prompt_returns_just_messages(self):
        conv = make_conv()
        conv.add_message("user", "hello")
        conv.add_message("assistant", "hi there")

        result = conv.to_llm_format()
        assert result == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

    def test_with_system_prompt_prepends_system_role_message(self):
        conv = make_conv()
        conv.system_prompt = "You are a helpful assistant."
        conv.add_message("user", "hello")

        result = conv.to_llm_format()
        assert result[0] == {"role": "system", "content": "You are a helpful assistant."}
        assert result[1] == {"role": "user", "content": "hello"}

    def test_with_system_prompt_only_no_messages(self):
        conv = make_conv()
        conv.system_prompt = "System prompt only"

        result = conv.to_llm_format()
        assert result == [{"role": "system", "content": "System prompt only"}]

    def test_empty_conversation_returns_empty_list(self):
        conv = make_conv()
        assert conv.to_llm_format() == []


class TestConversationAddMessage:
    """Test Conversation.add_message() and token/cost accumulation."""

    def test_add_message_with_usage_accumulates(self):
        conv = make_conv()
        conv.add_message("user", "hello", usage=UsageInfo(total_tokens=100, total_cost=0.01))

        assert conv.total_tokens == 100
        assert conv.total_cost == 0.01
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "user"
        assert conv.messages[0]["content"] == "hello"

    def test_add_message_accumulates_multiple(self):
        conv = make_conv()
        conv.add_message("user", "hello", usage=UsageInfo(total_tokens=100, total_cost=0.01))
        conv.add_message("assistant", "hi", usage=UsageInfo(total_tokens=50, total_cost=0.005))

        assert conv.total_tokens == 150
        assert conv.total_cost == 0.015

    def test_add_message_without_usage_does_not_change_stats(self):
        conv = make_conv()
        conv.add_message("user", "hello")

        assert conv.total_tokens == 0
        assert conv.total_cost == 0.0
        assert conv.messages[0]["content"] == "hello"

    def test_add_message_with_extra_fields_via_kwargs(self):
        conv = make_conv()
        conv.add_message("user", "look at this", images=["img1.png"], tags=["urgent"])

        msg = conv.messages[0]
        assert msg["role"] == "user"
        assert msg["content"] == "look at this"
        assert msg["images"] == ["img1.png"]
        assert msg["tags"] == ["urgent"]


class TestToolResult:
    """Test ToolResult fields."""

    def test_required_fields(self):
        result = ToolResult(tool_name="get_weather", arguments={"city": "Beijing"})

        assert result.tool_name == "get_weather"
        assert result.arguments == {"city": "Beijing"}
        assert result.result is None
        assert result.error is None
        assert result.duration_ms is None

    def test_all_fields(self):
        result = ToolResult(
            tool_name="get_weather",
            arguments={"city": "Tokyo"},
            result={"temp": 22},
            error=None,
            duration_ms=150.5,
        )

        assert result.tool_name == "get_weather"
        assert result.arguments == {"city": "Tokyo"}
        assert result.result == {"temp": 22}
        assert result.error is None
        assert result.duration_ms == 150.5

    def test_error_field(self):
        result = ToolResult(
            tool_name="get_weather",
            arguments={},
            error="network timeout",
        )
        assert result.error == "network timeout"


class TestUsageStats:
    """Test UsageStats default values."""

    def test_defaults(self):
        stats = UsageStats()

        assert stats.total_input_tokens == 0
        assert stats.total_output_tokens == 0
        assert stats.total_tokens == 0
        assert stats.total_cost == 0.0
        assert stats.request_count == 0
        assert stats.by_provider == {}

    def test_custom_values(self):
        stats = UsageStats(
            total_input_tokens=1000,
            total_output_tokens=500,
            total_tokens=1500,
            total_cost=0.05,
            request_count=10,
            by_provider={"openai": 0.03, "anthropic": 0.02},
        )

        assert stats.total_input_tokens == 1000
        assert stats.total_output_tokens == 500
        assert stats.total_tokens == 1500
        assert stats.total_cost == 0.05
        assert stats.request_count == 10
        assert stats.by_provider["openai"] == 0.03
        assert stats.by_provider["anthropic"] == 0.02


class TestImageResult:
    """Test ImageResult field initialization and defaults."""

    def test_defaults(self):
        result = ImageResult()

        assert result.url is None
        assert result.base64 is None
        assert result.revised_prompt is None
        assert result.model == ""
        assert result.provider == ""

    def test_with_url_and_model(self):
        result = ImageResult(
            url="https://example.com/image.png",
            model="dall-e-3",
            provider="openai",
            revised_prompt="A beautiful sunset",
        )

        assert result.url == "https://example.com/image.png"
        assert result.model == "dall-e-3"
        assert result.provider == "openai"
        assert result.revised_prompt == "A beautiful sunset"
        assert result.base64 is None

    def test_with_base64(self):
        result = ImageResult(base64="iVBORw0KGgoAAAANSUhEUgAAAAE=", model="sd-xl", provider="local")
        assert result.base64 == "iVBORw0KGgoAAAANSUhEUgAAAAE="
        assert result.url is None


class TestAudioResult:
    """Test AudioResult field initialization and defaults."""

    def test_defaults(self):
        result = AudioResult()

        assert result.audio_data is None
        assert result.url is None
        assert result.duration_seconds is None
        assert result.model == ""
        assert result.provider == ""

    def test_with_url_and_duration(self):
        result = AudioResult(
            url="https://example.com/audio.mp3",
            duration_seconds=12.5,
            model="tts-1",
            provider="openai",
        )

        assert result.url == "https://example.com/audio.mp3"
        assert result.duration_seconds == 12.5
        assert result.model == "tts-1"
        assert result.provider == "openai"
        assert result.audio_data is None


class TestProviderInfo:
    """Test ProviderInfo field initialization."""

    def test_required_fields(self):
        info = ProviderInfo(
            name="openai",
            provider_type="openai",
            enabled_chat=True,
            enabled_embedding=True,
            supports_vision=False,
            supports_function_calling=True,
            current_chat_model="gpt-4",
            current_embedding_model="text-embedding-3-small",
        )

        assert info.name == "openai"
        assert info.provider_type == "openai"
        assert info.enabled_chat is True
        assert info.enabled_embedding is True
        assert info.supports_vision is False
        assert info.supports_function_calling is True
        assert info.current_chat_model == "gpt-4"
        assert info.current_embedding_model == "text-embedding-3-small"

    def test_optional_defaults(self):
        info = ProviderInfo(
            name="custom",
            provider_type="custom",
            enabled_chat=False,
            enabled_embedding=False,
            supports_vision=False,
            supports_function_calling=False,
            current_chat_model="",
            current_embedding_model="",
        )

        assert info.models == []
        assert info.is_healthy is True
        assert info.last_error is None
        assert info.rate_limit_rpm is None

    def test_all_fields(self):
        info = ProviderInfo(
            name="anthropic",
            provider_type="anthropic",
            enabled_chat=True,
            enabled_embedding=False,
            supports_vision=False,
            supports_function_calling=True,
            current_chat_model="claude-3-5-sonnet",
            current_embedding_model="",
            models=["claude-3-5-sonnet", "claude-3-opus"],
            is_healthy=False,
            last_error="connection refused",
            rate_limit_rpm=50,
        )

        assert info.models == ["claude-3-5-sonnet", "claude-3-opus"]
        assert info.is_healthy is False
        assert info.last_error == "connection refused"
        assert info.rate_limit_rpm == 50


class TestStreamChunk:
    """Test StreamChunk field defaults."""

    def test_defaults(self):
        chunk = StreamChunk(content="Hello")

        assert chunk.content == "Hello"
        assert chunk.done is False
        assert chunk.full_response == ""
        assert chunk.reasoning_content is None
        assert chunk.tool_calls == []
        assert chunk.usage is None
        assert chunk.error is None

    def test_all_fields(self):
        usage = UsageInfo(total_tokens=10, total_cost=0.001)
        chunk = StreamChunk(
            content=" world",
            done=True,
            full_response="Hello world",
            reasoning_content="thinking...",
            tool_calls=[{"name": "get_weather", "arguments": {}}],
            usage=usage,
            error=None,
        )

        assert chunk.content == " world"
        assert chunk.done is True
        assert chunk.full_response == "Hello world"
        assert chunk.reasoning_content == "thinking..."
        assert len(chunk.tool_calls) == 1
        assert chunk.tool_calls[0]["name"] == "get_weather"
        assert chunk.usage.total_tokens == 10
        assert chunk.error is None
