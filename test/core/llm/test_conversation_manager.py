"""pytest tests for core.llm.conversation_manager.ConversationManager."""
import pytest
from unittest.mock import MagicMock, patch

from core.llm.conversation_manager import ConversationManager
from core.llm.provider_interface import ChatResponse, UsageInfo
from core.llm.types import Conversation, UsageStats


# ---------------------------------------------------------------------------
# Shared mock LLM that returns predictable ChatResponse objects.
# ---------------------------------------------------------------------------

def _make_mock_llm(content="hello", usage=None, tool_calls=None):
    """Return a mock LLM with chat() and stream_chat() returning ChatResponse."""
    mock = MagicMock()
    usage = usage or UsageInfo(input_tokens=10, output_tokens=20, total_tokens=30)
    mock.chat.return_value = ChatResponse(
        content=content,
        model="test-model",
        usage=usage,
        tool_calls=tool_calls or [],
    )

    def _stream_chat(messages, callback=None, **kwargs):
        if callback:
            for ch in content:
                callback(ch, done=False)
            callback("", done=True)
        return None

    mock.stream_chat.side_effect = _stream_chat
    return mock


# ===========================================================================
# Test: create_conversation
# ===========================================================================

class TestCreateConversation:
    def test_creates_conversation_and_returns_uuid(self, mocker):
        """create_conversation() generates a UUID and stores it in _conversations."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation()

        assert conv_id is not None
        assert len(conv_id) == 36  # UUID format
        assert conv_id in mgr._conversations

    def test_create_conversation_with_system_prompt(self, mocker):
        """create_conversation() with system_prompt sets it on the Conversation."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation(system_prompt="You are a helpful assistant.")

        conv = mgr._conversations[conv_id]
        assert conv.system_prompt == "You are a helpful assistant."


# ===========================================================================
# Test: get_conversation
# ===========================================================================

class TestGetConversation:
    def test_returns_conversation_when_exists(self, mocker):
        """get_conversation() returns the Conversation object."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation()

        conv = mgr.get_conversation(conv_id)
        assert conv is not None
        assert conv.id == conv_id

    def test_returns_none_for_missing_id(self, mocker):
        """get_conversation() returns None for a non-existent ID."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        assert mgr.get_conversation("nonexistent-id") is None


# ===========================================================================
# Test: list_conversations
# ===========================================================================

class TestListConversations:
    def test_returns_list_of_all_conversations(self, mocker):
        """list_conversations() returns a list of all conversations."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        id1 = mgr.create_conversation()
        id2 = mgr.create_conversation()

        convs = mgr.list_conversations()
        assert isinstance(convs, list)
        assert len(convs) == 2
        ids = {c.id for c in convs}
        assert ids == {id1, id2}


# ===========================================================================
# Test: delete_conversation
# ===========================================================================

class TestDeleteConversation:
    def test_removes_conversation_and_returns_true(self, mocker):
        """delete_conversation() removes the conversation and returns True."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation()

        result = mgr.delete_conversation(conv_id)
        assert result is True
        assert conv_id not in mgr._conversations

    def test_returns_false_for_missing_id(self, mocker):
        """delete_conversation() returns False for a non-existent ID."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        result = mgr.delete_conversation("nonexistent-id")
        assert result is False


# ===========================================================================
# Test: send_message
# ===========================================================================

class TestSendMessage:
    def test_raises_value_error_for_missing_conversation(self, mocker):
        """send_message() to a non-existent conversation raises ValueError."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        with pytest.raises(ValueError, match="Conversation not found"):
            mgr.send_message("missing-id", "hello")

    def test_builds_messages_and_calls_llm_chat(self, mocker):
        """send_message() builds the messages list and calls _llm.chat()."""
        mock_llm = _make_mock_llm(content="response text")
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation(system_prompt="system prompt")

        mgr.send_message(conv_id, "user message")

        mock_llm.chat.assert_called_once()
        call_kwargs = mock_llm.chat.call_args.kwargs
        # messages should contain system + user message
        msgs = call_kwargs["messages"]
        assert len(msgs) == 2
        # send_message converts dicts to Message objects before calling LLM
        assert msgs[0].role == "system"
        assert msgs[1].role == "user"
        assert msgs[1].content == "user message"

    def test_adds_response_to_conversation_messages(self, mocker):
        """send_message() appends only the assistant response to conversation.messages."""
        mock_llm = _make_mock_llm(content="assistant response")
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation()

        mgr.send_message(conv_id, "user message")

        conv = mgr._conversations[conv_id]
        # Only assistant response is stored in conversation (user message is sent but not stored)
        assert len(conv.messages) == 1
        assert conv.messages[0]["role"] == "assistant"
        assert conv.messages[0]["content"] == "assistant response"


# ===========================================================================
# Test: stream_send_message
# ===========================================================================

class TestStreamSendMessage:
    def test_raises_value_error_for_missing_conversation(self, mocker):
        """stream_send_message() to non-existent conversation raises ValueError."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        with pytest.raises(ValueError, match="Conversation not found"):
            mgr.stream_send_message("missing-id", "hello")

    def test_calls_llm_stream_chat_with_callback(self, mocker):
        """stream_send_message() calls _llm.stream_chat() with a callback."""
        mock_llm = _make_mock_llm(content="streamed response")
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        conv_id = mgr.create_conversation()

        chunks = []
        mgr.stream_send_message(conv_id, "user message", callback=lambda c: chunks.append(c))

        mock_llm.stream_chat.assert_called_once()
        call_kwargs = mock_llm.stream_chat.call_args.kwargs
        assert call_kwargs["callback"] is not None


# ===========================================================================
# Test: _maybe_truncate_history
# ===========================================================================

class TestMaybeTruncateHistory:
    def test_truncation_triggered_when_exceeds_threshold(self, mocker):
        """When total tokens exceed max_context * 0.8, history is truncated."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        # Use a small max_context so truncation is triggered easily
        mgr = ConversationManager(max_context=100)

        conv_id = mgr.create_conversation(
            system_prompt="system",
        )
        conv = mgr._conversations[conv_id]
        # Add many large messages to exceed threshold
        # With max_context=100, threshold = 80
        # Token estimate: each char is ~0.25 tokens (non-chinese) or 1 (chinese)
        # So 320 chars of non-chinese ~= 80 tokens
        messages = [{"role": "system", "content": "system"}]
        for i in range(20):
            messages.append({"role": "user", "content": "x" * 50})
        messages.append({"role": "user", "content": "hello"})

        mgr._maybe_truncate_history(conv, messages)

        # After truncation: system (1) + 66% of remaining (19 * 0.66 ≈ 12)
        # Should keep system + ~12 non-system messages
        assert len(messages) < 22

    def test_no_truncation_when_below_threshold(self, mocker):
        """When total tokens are below threshold, messages are unchanged."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        # Large enough max_context that threshold won't be reached
        mgr = ConversationManager(max_context=1_000_000)

        conv_id = mgr.create_conversation()
        conv = mgr._conversations[conv_id]

        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "short message"},
        ]

        original_len = len(messages)
        mgr._maybe_truncate_history(conv, messages)

        assert len(messages) == original_len


# ===========================================================================
# Test: _estimate_cost
# ===========================================================================

class TestEstimateCost:
    def test_returns_correct_float(self, mocker):
        """_estimate_cost() returns the correct computed cost."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager(pricing={
            "openai": {
                "chat": {"input_per_1k": 0.5, "output_per_1k": 1.5}
            }
        })

        usage = UsageInfo(input_tokens=1000, output_tokens=500, total_tokens=1500)
        cost = mgr._estimate_cost(usage, "openai", "gpt-4")

        # 1000/1000 * 0.5 + 500/1000 * 1.5 = 0.5 + 0.75 = 1.25
        assert cost == 1.25
        assert isinstance(cost, float)


# ===========================================================================
# Test: _get_or_raise
# ===========================================================================

class TestGetOrRaise:
    def test_raises_value_error_for_missing_conversation(self, mocker):
        """_get_or_raise() raises ValueError for a non-existent conversation."""
        mock_llm = _make_mock_llm()
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        with pytest.raises(ValueError, match="Conversation not found: missing"):
            mgr._get_or_raise("missing")


# ===========================================================================
# Test: get_usage_stats
# ===========================================================================

class TestGetUsageStats:
    def test_aggregates_across_all_conversations(self, mocker):
        """get_usage_stats() with no argument aggregates stats from all conversations."""
        mock_llm = _make_mock_llm(usage=UsageInfo(
            input_tokens=100, output_tokens=200, total_tokens=300
        ))
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        id1 = mgr.create_conversation(provider="provider_a")
        id2 = mgr.create_conversation(provider="provider_b")

        mgr.send_message(id1, "hello")
        mgr.send_message(id2, "hello")

        stats = mgr.get_usage_stats()

        assert stats.total_tokens == 600  # 300 * 2
        assert stats.request_count == 2  # each conv has 1 round-trip = 1 request

    def test_returns_stats_for_specific_conversation(self, mocker):
        """get_usage_stats(conv_id) returns stats for that conversation only."""
        mock_llm = _make_mock_llm(usage=UsageInfo(
            input_tokens=100, output_tokens=200, total_tokens=300
        ))
        mocker.patch("core.llm.conversation_manager.get_llm_provider", return_value=mock_llm)

        mgr = ConversationManager()
        id1 = mgr.create_conversation(provider="provider_a")
        id2 = mgr.create_conversation(provider="provider_b")

        mgr.send_message(id1, "hello")
        mgr.send_message(id2, "hello")

        stats = mgr.get_usage_stats(id1)

        assert stats.total_tokens == 300
        assert stats.request_count == 1
