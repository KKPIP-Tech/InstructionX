"""LLM 调用链核心修复 — 冒烟验证脚本（不依赖网络，使用 fake provider）

验证项：
a. LLMPluginService.chat 默认参数（provider/model 都 "default"）全链路不再抛 ConfigurationError
b. stream_chat 回调收到 (str, bool) 序列且返回完整文本
c. AuthenticationError("x", status_code=401, provider="y") 正常构造
d. 并行工具调用生成的 messages 序列：一条 assistant（含2个tool_calls）+ 2条 tool
e. 会话持久化：发消息后重新实例化 ConversationManager 能加载

运行：
    .venv\\Scripts\\python.exe scripts\\smoke_llm_core_fixes.py
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

# 项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.provider_interface import ChatResponse, UsageInfo
from core.llm.exceptions import AuthenticationError
import core.llm.llm_provider as lp_module


# ---------------------------------------------------------------------------
# Fake Provider：实现 providers 层契约（chat 返回 ChatResponse，
# stream_chat 返回生成器、yield ChatResponse 增量块、末块带 usage）
# ---------------------------------------------------------------------------

class FakeProvider:
    PROVIDER_TYPE = "fake"
    chat_model = "fake-chat-model"
    embedding_model = "fake-emb-model"
    enabled_chat = True
    enabled_embedding = True
    supports_vision = False
    last_error = None  # 契约：BaseProvider 新增 last_error 属性

    def __init__(self):
        self.chat_calls = []  # 记录调用参数，验证 None 过滤

    def chat(self, messages, model=None, **kwargs):
        # 用 **kwargs 捕获可选参数，验证上层是否透传了 None 值
        self.chat_calls.append({"messages": messages, "model": model, **kwargs})
        return ChatResponse(
            content="fake-reply",
            model="fake-chat-model",
            usage=UsageInfo(input_tokens=5, output_tokens=7, total_tokens=12),
        )

    def stream_chat(self, messages, model=None, callback=None, **kwargs):
        self.chat_calls.append({"messages": messages, "model": model, **kwargs})
        yield ChatResponse(content="Hello", model="fake-chat-model")
        yield ChatResponse(content=" world", model="fake-chat-model")
        # 末块：finish_reason 在 extra 中（契约：provider 层在末块填充 usage）
        yield ChatResponse(
            content="", model="fake-chat-model",
            usage=UsageInfo(input_tokens=3, output_tokens=2, total_tokens=5),
            finish_reason="stop",
        )

    def refresh_models(self, force=False):
        return []

    def get_models(self):
        return []

    def close(self):
        pass


class FakeUsageStore:
    """替代真实 UsageRecordStore，避免冒烟污染 data/llm_usage.json"""

    def __init__(self):
        self.records = []

    def record(self, record):
        self.records.append(record)


def _make_llm_provider(fake: FakeProvider, store: FakeUsageStore):
    """构造一个装配了 fake provider 的 LLMProvider（绕过真实配置/网络）"""
    lp_module.LLMProvider._instance = None
    with patch.object(lp_module.LLMConfig, "__init__", return_value=None), \
         patch.object(lp_module.LLMConfig, "get_all_providers", return_value={}), \
         patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None), \
         patch.object(lp_module, "get_usage_record_store", return_value=store):
        inst = lp_module.LLMProvider()
    inst._providers["fake"] = fake
    inst.get_enabled_providers = lambda feature="chat": {"fake": fake}
    return inst


def _make_plugin_service(llm, conv_mgr):
    """装配 LLMPluginService（绕过单例与真实配置）"""
    from core.llm.plugin_service import LLMPluginService
    from core.llm.tool_call_executor import ToolCallExecutor, ToolRegistry
    import logging

    svc = LLMPluginService.__new__(LLMPluginService)
    svc._llm = llm
    svc._conversation_mgr = conv_mgr
    svc._tool_executor = ToolCallExecutor(svc)
    svc._shared_tool_registry = ToolRegistry()
    svc._logger = logging.getLogger("smoke")
    return svc


def main():
    failures = []

    def check(name, condition, detail=""):
        status = "PASS" if condition else "FAIL"
        print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
        if not condition:
            failures.append(name)

    fake = FakeProvider()
    store = FakeUsageStore()
    llm = _make_llm_provider(fake, store)

    # ------------------------------------------------------------------
    # a. chat 全链路 default 不再抛 ConfigurationError + None 参数过滤
    # ------------------------------------------------------------------
    from core.llm.conversation_manager import ConversationManager

    with tempfile.TemporaryDirectory() as tmpdir:
        storage = Path(tmpdir) / "conversations.json"
        conv_mgr = ConversationManager(pricing={}, storage_path=storage)
        svc = _make_plugin_service(llm, conv_mgr)

        resp = svc.chat([{"role": "user", "content": "hi"}])  # provider/model 全默认
        check("a1. chat 默认参数全链路不抛异常", resp.content == "fake-reply")

        call = fake.chat_calls[-1]
        check("a2. None 可选参数未透传（temperature/max_tokens/tools）",
              "temperature" not in call and "max_tokens" not in call
              and "tools" not in call,
              f"实际调用参数 keys={sorted(call.keys())}")

        check("a3. UsageRecord 记录实际 provider/model（非 default）",
              len(store.records) == 1
              and store.records[0].provider == "fake"
              and store.records[0].model == "fake-chat-model",
              f"records={[(r.provider, r.model) for r in store.records]}")

        # default 粘性：再次 default 调用仍路由到同一 provider
        check("a4. default 粘性缓存生效", llm._default_chat_provider == "fake")

        # --------------------------------------------------------------
        # b. stream_chat 回调 (str, bool) 序列 + 返回完整文本
        # --------------------------------------------------------------
        events = []
        full = svc.stream_chat(
            [{"role": "user", "content": "hi"}],
            callback=lambda text, done: events.append((text, done)),
        )
        check("b1. stream_chat 返回完整文本", full == "Hello world",
              f"full={full!r}")
        check("b2. 回调收到 (str, bool) 序列且末次 done=True",
              all(isinstance(t, str) and isinstance(d, bool) for t, d in events)
              and events[-1] == ("", True)
              and "".join(t for t, _ in events) == "Hello world",
              f"events={events}")
        check("b3. 流式用量记录（末块 usage + is_stream）",
              any(r.is_stream for r in store.records))
        check("b4. last_stream_response 聚合可用",
              llm.last_stream_response is not None
              and llm.last_stream_response.content == "Hello world")

        # ConversationManager 流式路径
        conv_id = svc.create_conversation(system_prompt="sys")
        chunks = []
        text = svc.stream_send_message(conv_id, "你好", callback=chunks.append)
        check("b5. stream_send_message 返回完整文本并写入历史",
              text == "Hello world"
              and len(conv_mgr.get_conversation(conv_id).messages) == 2
              and chunks and chunks[-1].done is True)

        # send_message 路径（"调用成功才入历史" + 双重记录已消除）
        before = len(store.records)
        reply = svc.send_message(conv_id, "再问一句")
        check("b6. send_message 成功入历史且仅 LLMProvider 记录一次用量",
              reply == "fake-reply"
              and len(conv_mgr.get_conversation(conv_id).messages) == 4
              and len(store.records) == before + 1
              and store.records[-1].conversation_id == conv_id)

        # 调用失败不产生孤儿消息
        class BoomProvider(FakeProvider):
            def chat(self, messages, **kw):
                raise RuntimeError("boom")

        llm._providers["fake"] = BoomProvider()
        try:
            svc.send_message(conv_id, "会失败")
        except RuntimeError:
            pass
        check("b7. 调用失败无孤儿消息",
              len(conv_mgr.get_conversation(conv_id).messages) == 4)
        check("b8. 失败已记入健康跟踪",
              llm.get_provider_health("fake")[0] is False
              and "fake" in llm.last_errors)
        llm._providers["fake"] = fake  # 恢复

        # --------------------------------------------------------------
        # e. 会话持久化：重新实例化 ConversationManager 能加载
        # --------------------------------------------------------------
        mgr2 = ConversationManager(pricing={}, storage_path=storage)
        loaded = mgr2.get_conversation(conv_id)
        check("e1. 会话持久化重载",
              loaded is not None and len(loaded.messages) == 4
              and loaded.system_prompt == "sys",
              f"loaded_messages={len(loaded.messages) if loaded else None}")
        mgr2.delete_conversation(conv_id)
        mgr3 = ConversationManager(pricing={}, storage_path=storage)
        check("e2. delete_conversation 同步删除持久化记录",
              mgr3.get_conversation(conv_id) is None)

        # 上下文截断
        from core.llm.conversation_manager import estimate_tokens, estimate_messages_tokens
        check("e3. token 估算器（CJK 1/字，其他 4字符/token）",
              estimate_tokens("你好世界") == 4 and estimate_tokens("abcdefgh") == 2)
        big_conv = mgr3.create_conversation(system_prompt="s")
        mgr3._max_context_tokens = 50
        # 6 条历史（3 轮对话），每条 60 个 CJK 字符 ≈ 64 token，远超阈值
        mgr3._conversations[big_conv].messages = [
            {"role": role, "content": content * 15}
            for role, content in [
                ("user", "历史消息"), ("assistant", "历史回复"),
                ("user", "历史消息"), ("assistant", "历史回复"),
                ("user", "历史消息"), ("assistant", "历史回复"),
            ]
        ]
        svc2 = _make_plugin_service(llm, mgr3)
        svc2.send_message(big_conv, "新消息")
        sent_msgs = fake.chat_calls[-1]["messages"]
        sent_dicts = [m if isinstance(m, dict) else m.to_dict() for m in sent_msgs]
        check("e4. 上下文超限自动截断（丢弃最早历史，保留 system + 最近消息）",
              len(sent_dicts) == 5  # system + 最近 4 条（含新用户消息）
              and sent_dicts[0]["role"] == "system"
              and sent_dicts[-1]["content"] == "新消息"
              and estimate_messages_tokens(sent_dicts)
              < estimate_messages_tokens(
                  [{"role": "system", "content": "s"}]
                  + mgr3.get_conversation(big_conv).messages),
              f"sent={len(sent_dicts)} 条")

    # ------------------------------------------------------------------
    # c. AuthenticationError 带 status_code/provider 正常构造
    # ------------------------------------------------------------------
    exc = AuthenticationError("Invalid API key", status_code=401, provider="glm")
    from core.llm.exceptions import LLMException, APIError
    check("c1. AuthenticationError(status_code, provider) 构造正常",
          exc.status_code == 401 and exc.provider == "glm"
          and exc.args[0] == "Invalid API key"
          and isinstance(exc, LLMException)
          and not isinstance(exc, APIError))

    # ------------------------------------------------------------------
    # d. 并行工具调用消息序列：1 条 assistant（2个tool_calls）+ 2 条 tool
    # ------------------------------------------------------------------
    from core.llm.tool_call_executor import ToolCallExecutor, ToolRegistry

    tool_calls_resp = ChatResponse(
        content="", model="fake",
        tool_calls=[
            {"id": "call_1", "type": "function",
             "function": {"name": "get_weather", "arguments": '{"city": "北京"}'}},
            {"id": "call_2", "type": "function",
             "function": {"name": "get_time", "arguments": '{"tz": "CST"}'}},
        ],
    )
    final_resp = ChatResponse(content="晴，25度，下午3点", model="fake", tool_calls=[])

    class TwoCallLLM:
        def __init__(self):
            self._responses = [tool_calls_resp, final_resp]

        def chat(self, messages, **kwargs):
            return self._responses.pop(0)

    registry = ToolRegistry()
    registry.register("get_weather", "查天气", {}, lambda city: f"{city}晴")
    registry.register("get_time", "查时间", {}, lambda tz: f"{tz} 15:00")
    executor = ToolCallExecutor(TwoCallLLM(), tool_registry=registry)
    msgs, results, final = executor.chat_with_tools(
        [{"role": "user", "content": "北京天气和时间"}])

    seq_ok = (
        len(msgs) == 5
        and msgs[1]["role"] == "assistant"
        and len(msgs[1].get("tool_calls", [])) == 2
        and msgs[1]["content"] == ""  # 空串而非 None（GLM 兼容）
        and msgs[2]["role"] == "tool" and msgs[2]["tool_call_id"] == "call_1"
        and msgs[3]["role"] == "tool" and msgs[3]["tool_call_id"] == "call_2"
        and msgs[4]["role"] == "assistant"
    )
    check("d1. 并行工具调用消息序列合法", seq_ok,
          f"roles={[m['role'] for m in msgs]}")
    check("d2. 工具结果语义不变",
          len(results) == 2 and results[0].result == "北京晴"
          and results[0].error is None
          and "25度" in final.content)

    # register(replace=True) 覆盖重名注册
    registry.register("get_time", "查时间v2", {}, lambda tz: "v2", replace=True)
    check("d3. register(replace=True) 覆盖旧注册",
          registry.get_handler("get_time")(tz="x") == "v2")
    try:
        registry.register("get_time", "x", {}, lambda: None)
        check("d4. register 默认重名仍抛 ValueError", False)
    except ValueError:
        check("d4. register 默认重名仍抛 ValueError", True)

    # 参数 JSON 非法：不静默执行，tool 响应告知模型
    bad_args_resp = ChatResponse(
        content="", model="fake",
        tool_calls=[{"id": "c1", "function": {"name": "get_weather",
                                              "arguments": "not json {"}}],
    )

    class BadArgsLLM:
        def __init__(self):
            self.called = 0

        def chat(self, messages, **kwargs):
            self.called += 1
            return bad_args_resp if self.called == 1 else final_resp

    executor2 = ToolCallExecutor(BadArgsLLM(), tool_registry=registry)
    msgs2, results2, _ = executor2.chat_with_tools([{"role": "user", "content": "x"}])
    check("d5. 非法 arguments JSON：不执行且在 tool 响应中说明",
          results2[0].error is not None
          and "invalid arguments JSON" in msgs2[2]["content"])

    print()
    if failures:
        print(f"冒烟失败 {len(failures)} 项: {failures}")
        sys.exit(1)
    print("全部冒烟项通过 ✔")


if __name__ == "__main__":
    main()
