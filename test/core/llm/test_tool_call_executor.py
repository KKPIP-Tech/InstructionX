"""pytest tests for core.llm.tool_call_executor.ToolRegistry and ToolCallExecutor."""
import pytest
from unittest.mock import MagicMock

from core.llm.tool_call_executor import ToolRegistry, ToolCallExecutor
from core.llm.provider_interface import ChatResponse, Message
from core.llm.types import ToolResult


# ===========================================================================
# Test: ToolRegistry
# ===========================================================================

class TestToolRegistry:
    def test_register_stores_tool(self):
        """register() stores the tool in _tools and _handlers."""
        registry = ToolRegistry()

        def handler(x: int) -> int:
            return x * 2

        registry.register(
            name="double",
            description="Doubles a number",
            parameters={"type": "object", "properties": {"x": {"type": "integer"}}},
            handler=handler,
        )

        tools = registry.get_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "double"
        assert registry.get_handler("double") is handler

    def test_register_raises_on_duplicate_name(self):
        """register() raises ValueError when a tool with the same name already exists."""
        registry = ToolRegistry()

        def handler():
            pass

        registry.register("foo", "desc", {}, handler)

        with pytest.raises(ValueError, match="Tool already registered: foo"):
            registry.register("foo", "another desc", {}, handler)

    def test_unregister_removes_from_both_dicts(self):
        """unregister() removes tool from both _tools and _handlers; returns True."""
        registry = ToolRegistry()

        def handler():
            pass

        registry.register("my_tool", "desc", {}, handler)
        assert registry.get_handler("my_tool") is handler

        result = registry.unregister("my_tool")

        assert result is True
        assert registry.get_handler("my_tool") is None
        assert "my_tool" not in registry.list_tools()

    def test_unregister_returns_false_for_missing_name(self):
        """unregister() returns False when the tool does not exist."""
        registry = ToolRegistry()
        assert registry.unregister("nonexistent") is False

    def test_get_tools_returns_list_of_tool_dicts(self):
        """get_tools() returns a list of tool definition dicts."""
        registry = ToolRegistry()

        def h1(): pass
        def h2(): pass

        registry.register("tool_a", "desc a", {}, h1)
        registry.register("tool_b", "desc b", {}, h2)

        tools = registry.get_tools()
        assert isinstance(tools, list)
        assert len(tools) == 2
        names = {t["function"]["name"] for t in tools}
        assert names == {"tool_a", "tool_b"}

    def test_get_handler_returns_callable_or_none(self):
        """get_handler() returns the registered callable, or None if missing."""
        registry = ToolRegistry()

        def my_handler():
            pass

        registry.register("existing", "desc", {}, my_handler)

        assert registry.get_handler("existing") is my_handler
        assert registry.get_handler("missing") is None

    def test_list_tools_returns_names(self):
        """list_tools() returns a list of tool names."""
        registry = ToolRegistry()

        def h(): pass

        registry.register("alpha", "desc", {}, h)
        registry.register("beta", "desc", {}, h)

        names = registry.list_tools()
        assert set(names) == {"alpha", "beta"}


# ===========================================================================
# Helper: make mock LLM for ToolCallExecutor tests
# ===========================================================================

def _mock_llm(response_content="final answer", tool_calls=None, usage=None):
    """Create a configurable mock LLM service for ToolCallExecutor."""
    mock = MagicMock()
    usage = usage or MagicMock(input_tokens=10, output_tokens=20, total_tokens=30)
    mock.chat.return_value = ChatResponse(
        content=response_content,
        model="test-model",
        usage=usage,
        tool_calls=tool_calls or [],
    )
    mock.stream_chat.side_effect = lambda messages, callback=None, **kw: (
        callback and callback(response_content, done=False) or None,
        callback and callback("", done=True) or None
    )
    return mock


# ===========================================================================
# Test: ToolCallExecutor — no-tools delegation
# ===========================================================================

class TestChatWithToolsNoTools:
    def test_delegates_to_llm_chat_when_no_tools(self):
        """When no tools are registered, chat_with_tools() delegates to _llm.chat()."""
        mock_llm = _mock_llm(response_content="direct response")
        executor = ToolCallExecutor(llm_service=mock_llm)

        messages = [{"role": "user", "content": "hello"}]
        result_msgs, tool_results, final = executor.chat_with_tools(messages)

        mock_llm.chat.assert_called_once()
        call_args = mock_llm.chat.call_args
        # tools is passed as positional arg (index 1 after messages), not kwarg
        assert call_args.kwargs["provider"] == "default"
        assert call_args.kwargs["model"] == "default"

    def test_delegates_to_llm_stream_chat_when_no_tools_and_stream(self):
        """When no tools registered and stream=True, delegates to _llm.stream_chat()."""
        mock_llm = _mock_llm(response_content="streamed response")
        executor = ToolCallExecutor(llm_service=mock_llm)

        chunks = []
        def on_chunk(chunk, done):
            if not done:
                chunks.append(chunk)

        messages = [{"role": "user", "content": "hello"}]
        executor.chat_with_tools(messages, stream=True, stream_callback=on_chunk)

        mock_llm.stream_chat.assert_called_once()


# ===========================================================================
# Test: ToolCallExecutor — single turn with tool call
# ===========================================================================

class TestChatWithToolsSingleTurn:
    def test_one_turn_llm_returns_tool_calls_executor_calls_handler(self):
        """One turn: LLM returns tool_calls -> handler called -> second LLM call -> final."""
        tool_calls_response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {
                    "name": "get_weather",
                    "arguments": '{"city": "Beijing"}'
                }
            }]
        )
        final_response = ChatResponse(
            content="The weather in Beijing is sunny.",
            model="test",
            tool_calls=[]
        )

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [tool_calls_response, final_response]

        def get_weather(city):
            return f"sunny in {city}"

        registry = ToolRegistry()
        registry.register("get_weather", "Get weather", {}, get_weather)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "weather?"}]

        result_msgs, tool_results, final = executor.chat_with_tools(messages)

        # Two LLM calls: first for tool call, second for final response
        assert mock_llm.chat.call_count == 2
        assert len(tool_results) == 1
        assert tool_results[0].tool_name == "get_weather"
        assert tool_results[0].result == "sunny in Beijing"
        # final is a ChatResponse object — access .content directly
        assert "sunny" in final.content

    def test_respects_max_turns_limit(self):
        """When max_turns is reached, the loop exits and returns."""
        # Always return tool calls so the loop never exits naturally
        infinite_response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_x",
                "function": {"name": "dummy", "arguments": "{}"}
            }]
        )
        mock_llm = MagicMock()
        mock_llm.chat.return_value = infinite_response

        registry = ToolRegistry()
        registry.register("dummy", "dummy tool", {}, lambda: "ok")

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "trigger loop"}]

        result_msgs, tool_results, final = executor.chat_with_tools(messages, max_turns=3)

        assert mock_llm.chat.call_count == 3

    def test_handler_raises_tool_result_error_contains_exception(self):
        """When handler raises, ToolResult.error contains the exception message."""
        tool_calls_response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {"name": "bad_tool", "arguments": "{}"}
            }]
        )
        final_response = ChatResponse(content="done", model="test", tool_calls=[])

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [tool_calls_response, final_response]

        def bad_handler():
            raise RuntimeError("something went wrong")

        registry = ToolRegistry()
        registry.register("bad_tool", "bad", {}, bad_handler)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "fail"}]

        _, tool_results, _ = executor.chat_with_tools(messages)

        assert len(tool_results) == 1
        assert "Error executing bad_tool" in str(tool_results[0].result)
        assert "something went wrong" in str(tool_results[0].result)

    def test_handler_not_found_result_starts_with_error(self):
        """When handler not found, ToolResult.result starts with 'Error: tool'."""
        tool_calls_response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {"name": "unknown_tool", "arguments": "{}"}
            }]
        )
        final_response = ChatResponse(content="done", model="test", tool_calls=[])

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [tool_calls_response, final_response]

        registry = ToolRegistry()
        # Register a dummy tool so the registry is non-empty (early-exit is skipped)
        def dummy_handler():
            return "ok"
        registry.register("dummy", "a dummy tool", {}, dummy_handler)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "call unknown"}]

        _, tool_results, _ = executor.chat_with_tools(messages)

        assert len(tool_results) == 1
        assert str(tool_results[0].result).startswith("Error: tool")

    def test_arguments_as_json_string_parsed(self):
        """Arguments as a JSON string are parsed correctly."""
        tool_response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {
                    "name": "multiply",
                    "arguments": '{"a": 3, "b": 7}'
                }
            }]
        )
        final_response = ChatResponse(content="21", model="test", tool_calls=[])
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [tool_response, final_response]

        received_args = {}
        def multiply(**kwargs):
            received_args.update(kwargs)
            return str(kwargs.get("a", 0) * kwargs.get("b", 0))

        registry = ToolRegistry()
        registry.register("multiply", "multiply two numbers", {}, multiply)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "calc"}]

        executor.chat_with_tools(messages)

        assert received_args.get("a") == 3
        assert received_args.get("b") == 7

    def test_arguments_as_invalid_json_falls_back_to_empty_dict(self):
        """Arguments as an invalid JSON string fall back to {}."""
        response = ChatResponse(
            content="",
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {
                    "name": "test_tool",
                    "arguments": "not valid json {"
                }
            }]
        )
        mock_llm = MagicMock()
        mock_llm.chat.return_value = response

        received_args = {}
        def test_tool(**kwargs):
            received_args.update(kwargs)
            return "ok"

        registry = ToolRegistry()
        registry.register("test_tool", "test", {}, test_tool)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "trigger"}]

        executor.chat_with_tools(messages)

        # Should fall back to {} when JSON is invalid
        assert received_args == {}

    def test_empty_tool_calls_exits_loop_immediately(self):
        """tool_calls being empty/None causes the loop to exit and return immediately."""
        response = ChatResponse(content="final answer", model="test", tool_calls=[])
        mock_llm = MagicMock()
        mock_llm.chat.return_value = response

        registry = ToolRegistry()
        registry.register("some_tool", "some tool", {}, lambda: "nope")

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "hello"}]

        _, tool_results, final = executor.chat_with_tools(messages)

        # Should not call the tool at all
        assert tool_results == []
        assert mock_llm.chat.call_count == 1

    def test_stream_accumulates_chunks_via_stream_callback(self):
        """stream=True accumulates response chunks via stream_callback."""
        content_chunks = []

        def stream_callback(chunk, done):
            if not done:
                content_chunks.append(chunk)

        response = ChatResponse(content="hello world", model="test", tool_calls=[])
        mock_llm = MagicMock()
        mock_llm.stream_chat.side_effect = lambda messages, callback=None, **kw: (
            callback and callback("hello ", done=False) or None,
            callback and callback("world", done=False) or None,
            callback and callback("", done=True) or None,
            response
        )

        registry = ToolRegistry()
        registry.register("dummy", "dummy", {}, lambda: "n/a")

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "stream me"}]

        executor.chat_with_tools(messages, stream=True, stream_callback=stream_callback)

        # The executor should have called stream_chat with the callback
        mock_llm.stream_chat.assert_called_once()
        assert mock_llm.stream_chat.call_args.kwargs.get("callback") is not None

    def test_no_content_but_tool_calls_still_processes_tools(self):
        """A response with no content but with tool_calls still processes the tools."""
        response = ChatResponse(
            content="",  # empty content
            model="test",
            tool_calls=[{
                "id": "call_1",
                "function": {"name": "ping", "arguments": "{}"}
            }]
        )
        final_response = ChatResponse(
            content="pong",
            model="test",
            tool_calls=[]
        )

        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [response, final_response]

        def ping():
            return "pong"

        registry = ToolRegistry()
        registry.register("ping", "ping", {}, ping)

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)
        messages = [{"role": "user", "content": "ping?"}]

        _, tool_results, final = executor.chat_with_tools(messages)

        assert len(tool_results) == 1
        assert tool_results[0].tool_name == "ping"


# ===========================================================================
# Test: chat_with_tools_stream (typed callback version)
# ===========================================================================

class TestChatWithToolsStream:
    def test_delegates_to_chat_with_tools_with_stream_true(self):
        """chat_with_tools_stream() calls chat_with_tools() with stream=True."""
        from core.llm.types import StreamChunk

        response = ChatResponse(content="streamed", model="test", tool_calls=[])
        mock_llm = MagicMock()
        mock_llm.stream_chat.side_effect = lambda messages, callback=None, **kw: (
            callback and callback("streamed", done=False) or None,
            callback and callback("", done=True) or None,
            response
        )

        registry = ToolRegistry()
        registry.register("dummy", "dummy", {}, lambda: "n/a")

        executor = ToolCallExecutor(llm_service=mock_llm, tool_registry=registry)

        chunks_received = []
        def callback(chunk: StreamChunk):
            chunks_received.append(chunk)

        messages = [{"role": "user", "content": "stream"}]
        executor.chat_with_tools_stream(messages, callback=callback)

        # stream_chat should have been called (since tools are registered)
        mock_llm.stream_chat.assert_called_once()
