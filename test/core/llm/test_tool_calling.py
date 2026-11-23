"""工具调用类型化测试（core/llm/tool_call_executor.py + types.py）

覆盖：ToolRegistry 双注册路径、ToolChatResult 结构化返回（stream 与否
字段类型固定）、多轮循环至 max_turns 终止、handler 异常、StreamChunk
实填、ToolCall 解析。
"""

from core.llm.config import get_llm_config
from core.llm.plugin_service import LLMPluginService
from core.llm.provider_interface import ChatResponse, ToolCall
from core.llm.tool_call_executor import ToolCallExecutor, ToolRegistry
from core.llm.types import ToolChatResult, ToolDefinition, ToolResult

# 多轮循环测试的最大轮数
TEST_MAX_TURNS = 2


class StubLLM:
    """可控 stub LLM：chat 按预设响应序列出队；stream_chat 回调固定分段
    并把聚合响应放到 last_stream_response（模拟 LLMProvider 契约）"""

    def __init__(self):
        self.chat_responses = []
        self.chat_calls = []
        self.stream_text = ""
        self.stream_parts = []
        self.stream_aggregated = None
        self.last_stream_response = None

    def chat(self, messages, provider=None, model=None,
             temperature=None, tools=None):
        self.chat_calls.append({"messages": list(messages), "tools": tools})
        return self.chat_responses.pop(0)

    def stream_chat(self, messages, callback=None, provider=None,
                    model=None, temperature=None, tools=None):
        self.chat_calls.append({"messages": list(messages), "tools": tools})
        for index, part in enumerate(self.stream_parts):
            callback(part, index == len(self.stream_parts) - 1)
        self.last_stream_response = self.stream_aggregated
        return self.stream_text


def _tool_call(name="calc", arguments=None, call_id="call_1"):
    """构造一个 ToolCall"""
    return ToolCall(id=call_id, name=name, arguments=arguments or {"x": 1})


class TestToolRegistry:
    """工具注册表"""

    def test_register_and_lookup(self):
        """register 原签名：注册后可查定义与 handler"""
        registry = ToolRegistry()
        handler = lambda x: x + 1  # noqa: E731
        registry.register("calc", "计算", {"type": "object"}, handler)
        assert registry.list_tools() == ["calc"]
        assert registry.get_handler("calc") is handler
        tools = registry.get_tools()
        assert tools[0]["function"]["name"] == "calc"

    def test_register_typed_equivalent(self):
        """register_typed(ToolDefinition) 与 register 等效"""
        registry = ToolRegistry()
        handler = lambda q: f"结果:{q}"  # noqa: E731
        registry.register_typed(ToolDefinition(
            name="search", description="搜索",
            parameters={"type": "object"}, handler=handler))
        assert registry.list_tools() == ["search"]
        assert registry.get_handler("search")("a") == "结果:a"

    def test_unregister(self):
        """注销后查询返回 None（边界）"""
        registry = ToolRegistry()
        registry.register("t", "d", {}, lambda: None)
        assert registry.unregister("t") is True
        assert registry.get_handler("t") is None


class TestChatWithoutTools:
    """未注册工具时退化为普通对话"""

    def test_no_tools_degrades(self):
        """无工具注册：直接一轮对话，tool_results 为空"""
        stub = StubLLM()
        stub.chat_responses = [ChatResponse(content="普通回复", model="m")]
        executor = ToolCallExecutor(stub)
        result = executor.chat_with_tools([{"role": "user", "content": "hi"}])
        assert isinstance(result, ToolChatResult)
        assert result.tool_results == []
        assert result.final_text == "普通回复"
        assert result.final_response.content == "普通回复"


class TestToolCallLoop:
    """多轮工具调用循环"""

    def test_single_tool_turn(self):
        """一轮工具调用：handler 执行 + 消息序列 + 最终文本"""
        stub = StubLLM()
        stub.chat_responses = [
            ChatResponse(content="", model="m",
                         tool_calls=[_tool_call()]),
            ChatResponse(content="最终回复", model="m"),
        ]
        executor = ToolCallExecutor(stub)
        executor.tools.register("calc", "计算", {}, lambda x: x * 2)
        result = executor.chat_with_tools([{"role": "user", "content": "算"}])
        assert result.final_text == "最终回复"
        assert result.final_response.content == "最终回复"
        # 工具执行记录
        assert len(result.tool_results) == 1
        record = result.tool_results[0]
        assert isinstance(record, ToolResult)
        assert record.tool_name == "calc"
        assert record.result == 2
        assert record.error is None
        # 消息序列：assistant(tool_calls) + tool 响应 + assistant 最终回复
        roles = [m["role"] for m in result.messages]
        assert roles == ["user", "assistant", "tool", "assistant"]
        assert result.messages[1]["tool_calls"][0]["function"]["name"] == "calc"
        assert result.messages[2]["tool_call_id"] == "call_1"
        assert result.messages[2]["content"] == "2"
        # 第二轮请求携带了工具定义
        assert stub.chat_calls[0]["tools"]

    def test_loop_terminates_at_max_turns(self):
        """模型持续要求调用：循环至 max_turns 终止并追加说明消息"""
        stub = StubLLM()
        stub.chat_responses = [
            ChatResponse(content="", model="m", tool_calls=[_tool_call()])
            for _ in range(TEST_MAX_TURNS)
        ]
        executor = ToolCallExecutor(stub)
        executor.tools.register("calc", "计算", {}, lambda x: x)
        result = executor.chat_with_tools(
            [{"role": "user", "content": "算"}], max_turns=TEST_MAX_TURNS)
        assert len(result.tool_results) == TEST_MAX_TURNS
        assert len(stub.chat_calls) == TEST_MAX_TURNS
        assert "最大工具调用轮数" in result.messages[-1]["content"]

    def test_handler_error_recorded_and_loop_continues(self):
        """handler 抛异常：记录 error 并把错误回传模型，循环继续"""
        stub = StubLLM()
        stub.chat_responses = [
            ChatResponse(content="", model="m", tool_calls=[_tool_call()]),
            ChatResponse(content="恢复", model="m"),
        ]

        def bad_handler(x):
            raise ValueError("工具内部错误")

        executor = ToolCallExecutor(stub)
        executor.tools.register("calc", "计算", {}, bad_handler)
        result = executor.chat_with_tools([{"role": "user", "content": "算"}])
        assert result.tool_results[0].error is not None
        assert "工具内部错误" in result.tool_results[0].error
        assert result.final_text == "恢复"


class TestStreamToolCalling:
    """流式工具调用（ToolChatResult 字段类型固定）"""

    def test_stream_result_shape(self):
        """流式路径：tool_calls 从聚合响应提取，结果结构与非流式一致"""
        stub = StubLLM()
        stub.stream_parts = ["你好", "世界"]
        stub.stream_text = "你好世界"
        stub.stream_aggregated = ChatResponse(
            content="你好世界", model="m", tool_calls=[_tool_call()])
        executor = ToolCallExecutor(stub)
        executor.tools.register("calc", "计算", {}, lambda x: x)
        chunks = []
        # 第二轮（工具结果回传后）为非流式？流式路径每轮都走 stream_chat，
        # 预设第二轮不再返回 tool_calls
        def stream_chat_once(messages, callback=None, **kwargs):
            # 第二轮：无工具调用
            stub.stream_parts = ["完成"]
            stub.stream_text = "完成"
            stub.stream_aggregated = ChatResponse(content="完成", model="m")
            return StubLLM.stream_chat(stub, messages, callback, **kwargs)
        stub.chat_responses = []  # 占位（流式路径不用）
        original_stream = stub.stream_chat
        calls = {"n": 0}

        def stream_switch(messages, callback=None, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                return original_stream(messages, callback, **kwargs)
            return stream_chat_once(messages, callback, **kwargs)
        stub.stream_chat = stream_switch

        result = executor.chat_with_tools(
            [{"role": "user", "content": "hi"}],
            stream=True, stream_callback=lambda c, d: chunks.append((c, d)))
        assert isinstance(result, ToolChatResult)
        assert isinstance(result.messages, list)
        assert isinstance(result.tool_results, list)
        assert len(result.tool_results) == 1
        assert result.final_text == "完成"
        assert result.final_response is stub.stream_aggregated
        assert ("你好", False) in chunks

    def test_service_stream_callback_receives_stream_chunk(
            self, mock_config_factory):
        """chat_with_tools_stream：callback 收到字段实填的 StreamChunk"""
        get_llm_config().add_provider("mock-1", mock_config_factory())
        service = LLMPluginService()
        executor = service.get_tool_executor()
        executor.tools.register("noop", "空操作", {}, lambda: "ok")
        chunks = []
        result = service.chat_with_tools_stream(
            [{"role": "user", "content": "hi"}],
            callback=chunks.append, provider="mock-1")
        assert isinstance(result, ToolChatResult)
        assert result.final_text == "mock 回复"
        assert chunks, "callback 应收到 StreamChunk"
        first = chunks[0]
        assert first.content == "mock "
        assert first.done is False
        # Mock 无 finish_reason 块，底层补发一次空内容的结束块
        assert chunks[-1].done is True
        assert chunks[-1].content == ""


class TestToolCallParsing:
    """ToolCall 解析"""

    def test_from_openai_format(self):
        """标准 OpenAI 格式解析（arguments 为 JSON 字符串）"""
        call = ToolCall.from_dict({
            "id": "call_9", "type": "function",
            "function": {"name": "search", "arguments": '{"q": "x"}'},
        })
        assert call.id == "call_9"
        assert call.name == "search"
        assert call.arguments == {"q": "x"}
        assert call.raw_arguments is None
        # to_dict 回转为 OpenAI 格式
        assert call.to_dict()["function"]["arguments"] == '{"q": "x"}'

    def test_from_flat_format_and_invalid_json(self):
        """扁平格式解析；非法 JSON 回退空参数并保留原文（异常路径）"""
        flat = ToolCall.from_dict({"id": "c1", "name": "f", "arguments": {"a": 1}})
        assert flat.arguments == {"a": 1}
        bad = ToolCall.from_dict({
            "id": "c2", "function": {"name": "g", "arguments": "{不是JSON"}})
        assert bad.arguments == {}
        assert bad.raw_arguments == "{不是JSON"
        # raw_arguments 优先输出原文（便于回传模型重新生成）
        assert bad.to_dict()["function"]["arguments"] == "{不是JSON"
