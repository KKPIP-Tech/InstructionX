"""工具调用执行器模块

自动处理 LLM → 工具调用 → 结果回传 → 再次 LLM 的完整两轮循环。
插件开发者只需注册工具，调用 chat_with_tools 即可。

Classes:
    ToolRegistry: 工具注册表
    ToolCallExecutor: 工具调用执行器
"""

import logging
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import (
    DEFAULT_PROVIDER, StreamChunk, ToolChatResult, ToolDefinition, ToolResult,
)
from .provider_interface import ChatResponse, Message, ToolCall

logger = logging.getLogger(__name__)

# 工具调用循环的默认最大轮数（防止无限循环）
DEFAULT_MAX_TOOL_TURNS: int = 5


class ToolRegistry:
    """工具注册表 — 管理插件可用的工具

    持有 tools 列表（发给 LLM）和 handlers 映射（实际执行）。
    """

    def __init__(self):
        self._tools: Dict[str, Dict] = {}
        self._handlers: Dict[str, Callable] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict,
        handler: Callable,
        replace: bool = False,
    ) -> None:
        """注册一个工具

        Args:
            name: 工具名称（唯一）
            description: 工具描述（会发给 LLM）
            parameters: OpenAI 风格的 parameters schema
            handler: 实际执行的函数，签名为 handler(**kwargs) -> Any
            replace: 为 True 时覆盖同名旧注册（用于 MCP 重连等重复注册场景）；
                默认 False，重名抛出 ValueError
        """
        if name in self._tools:
            if not replace:
                raise ValueError(f"Tool already registered: {name}")
            logger.info(f"Tool re-registered (replace): {name}")

        self._tools[name] = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            }
        }
        self._handlers[name] = handler
        logger.debug(f"Tool registered: {name}")

    def register_typed(self, definition: ToolDefinition) -> None:
        """以类型化的 ToolDefinition 注册工具（内部转发现有 register）

        Args:
            definition: 工具定义（名称/描述/JSON Schema 参数/处理函数）

        Raises:
            ValueError: 同名工具已注册时抛出（与 register 默认行为一致）
        """
        self.register(
            name=definition.name,
            description=definition.description,
            parameters=definition.parameters,
            handler=definition.handler,
        )

    def unregister(self, name: str) -> bool:
        """注销工具

        Args:
            name: 工具名称

        Returns:
            bool: 是否成功注销
        """
        if name in self._tools:
            del self._tools[name]
            del self._handlers[name]
            logger.debug(f"Tool unregistered: {name}")
            return True
        return False

    def get_tools(self) -> List[Dict]:
        """获取所有工具定义列表

        Returns:
            List[Dict]: 工具定义列表（可传给 LLM）
        """
        return list(self._tools.values())

    def get_handler(self, name: str) -> Optional[Callable]:
        """获取工具处理函数

        Args:
            name: 工具名称

        Returns:
            Optional[Callable]: 处理函数，不存在则返回 None
        """
        return self._handlers.get(name)

    def list_tools(self) -> List[str]:
        """列出所有已注册工具名称

        Returns:
            List[str]: 工具名称列表
        """
        return list(self._tools.keys())


class ToolCallExecutor:
    """
    工具调用执行器 — 自动处理 LLM → 工具调用 → 结果回传 → 再次 LLM 的完整循环。

    插件开发者只需注册工具，调用 chat_with_tools 即可。
    """

    def __init__(
        self,
        llm_service,
        tool_registry: Optional[ToolRegistry] = None,
    ):
        """初始化执行器

        Args:
            llm_service: LLM 服务（通常是 LLMProvider 或 LLMPluginService）
            tool_registry: 工具注册表（可选，默认创建新的）
        """
        self._llm = llm_service
        self._registry = tool_registry or ToolRegistry()

    @property
    def tools(self) -> ToolRegistry:
        """获取工具注册表"""
        return self._registry

    def chat_with_tools(
        self,
        messages: List[Dict],
        provider: str = DEFAULT_PROVIDER,
        model: str = "default",
        max_turns: int = DEFAULT_MAX_TOOL_TURNS,
        temperature: Optional[float] = None,
        stream: bool = False,
        stream_callback: Optional[Callable[[str, bool], None]] = None,
    ) -> ToolChatResult:
        """
        带有工具调用的对话

        Args:
            messages: 消息列表
            provider: Provider 名称（DEFAULT_PROVIDER 表示默认实例）
            model: 模型名称（"default" 表示使用配置中的模型）
            max_turns: 最多工具调用轮数（防止无限循环）
            temperature: 温度参数
            stream: 是否流式
            stream_callback: 流式回调函数

        Returns:
            ToolChatResult: 结构化结果（完整消息记录 / 工具结果 /
                最终响应 / 最终文本）
        """
        if not self._registry.list_tools():
            return self._chat_without_tools(
                messages, provider, model, temperature, stream, stream_callback)

        tools = self._registry.get_tools()
        tool_results: List[ToolResult] = []
        messages = list(messages)
        final_response: Optional[ChatResponse] = None
        final_text = ""

        for turn in range(1, max_turns + 1):
            logger.debug(f"Tool call turn {turn}/{max_turns}")
            response, final_text = self._request_turn(
                messages, tools, provider, model, temperature,
                stream, stream_callback)
            final_response = response
            tool_calls = self._normalize_call_ids(self._extract_tool_calls(response))
            if not tool_calls:
                messages.append({"role": "assistant", "content": final_text or ""})
                return ToolChatResult(
                    messages=messages, tool_results=tool_results,
                    final_response=final_response, final_text=final_text)
            # OpenAI 消息序列契约：一条 assistant 消息携带全部 tool_calls，
            # 随后紧跟全部 tool 响应消息
            messages.append(self._build_tool_call_message(final_text, tool_calls))
            self._execute_tool_calls(tool_calls, tool_results, messages)

        logger.warning(f"Tool call loop exceeded max_turns ({max_turns})")
        # 追加说明消息：避免返回的 messages 以未配对的 tool 消息结尾，
        # 保证可直接用于后续请求
        messages.append({
            "role": "assistant",
            "content": f"已达到最大工具调用轮数（{max_turns}），停止继续调用工具。",
        })
        return ToolChatResult(
            messages=messages, tool_results=tool_results,
            final_response=final_response, final_text=final_text)

    def chat_with_tools_stream(
        self,
        messages: List[Dict],
        callback: Callable[[StreamChunk], None],
        provider: str = DEFAULT_PROVIDER,
        model: str = "default",
        max_turns: int = DEFAULT_MAX_TOOL_TURNS,
        temperature: Optional[float] = None,
    ) -> ToolChatResult:
        """流式版本的 chat_with_tools

        Args:
            messages: 消息列表
            callback: 流式回调（接收 StreamChunk；本路径底层回调契约为
                (str, bool)，故 reasoning_content / usage 无数据来源，
                保持 None，仅 content / done / full_response 实填）
            provider: Provider 名称（DEFAULT_PROVIDER 表示默认实例）
            model: 模型名称（"default" 表示使用配置中的模型）
            max_turns: 最多工具调用轮数
            temperature: 温度参数

        Returns:
            ToolChatResult: 结构化结果，final_text 为流式聚合全文，
                final_response 取底层聚合响应（last_stream_response）
        """
        content_chunks: List[str] = []

        def _sc(chunk: str, done: bool):
            content_chunks.append(chunk)
            callback(StreamChunk(
                content=chunk, done=done,
                full_response="".join(content_chunks)))

        return self.chat_with_tools(
            messages=messages,
            provider=provider,
            model=model,
            max_turns=max_turns,
            temperature=temperature,
            stream=True,
            stream_callback=_sc,
        )

    # ==================== 内部辅助方法 ====================

    def _chat_without_tools(
        self,
        messages: List[Dict],
        provider: str,
        model: str,
        temperature: Optional[float],
        stream: bool,
        stream_callback: Optional[Callable[[str, bool], None]],
    ) -> ToolChatResult:
        """未注册任何工具时退化为普通对话

        Args:
            messages: 消息列表
            provider: Provider 名称
            model: 模型名称
            temperature: 温度参数
            stream: 是否流式
            stream_callback: 流式回调函数

        Returns:
            ToolChatResult: 结构化结果（tool_results 恒为空列表）
        """
        if stream:
            text = self._llm.stream_chat(
                messages, callback=stream_callback,
                provider=provider, model=model, temperature=temperature)
            aggregated = getattr(self._llm, "last_stream_response", None)
            return ToolChatResult(
                messages=list(messages), tool_results=[],
                final_response=aggregated, final_text=text or "")
        response = self._llm.chat(
            messages, provider=provider, model=model, temperature=temperature)
        final_text = (response.content if hasattr(response, "content")
                      else str(response or ""))
        return ToolChatResult(
            messages=list(messages), tool_results=[],
            final_response=response, final_text=final_text)

    def _request_turn(
        self,
        messages: List[Dict],
        tools: List[Dict],
        provider: str,
        model: str,
        temperature: Optional[float],
        stream: bool,
        stream_callback: Optional[Callable[[str, bool], None]],
    ) -> Tuple[Optional[ChatResponse], str]:
        """发起一轮携带工具定义的 LLM 请求

        Returns:
            Tuple[Optional[ChatResponse], str]: (本轮响应对象, 本轮文本)；
                流式路径响应对象取底层聚合响应（last_stream_response），
                底层未提供时为 None
        """
        msg_objs = [Message.from_dict(m) if isinstance(m, dict) else m
                    for m in messages]
        if not stream:
            response = self._llm.chat(
                msg_objs, provider=provider, model=model,
                temperature=temperature, tools=tools)
            text = (response.content if hasattr(response, "content")
                    else str(response or ""))
            return response, text

        content_chunks: List[str] = []

        def _sc(chunk: str, done: bool):
            content_chunks.append(chunk)
            if stream_callback:
                stream_callback(chunk, done)

        # 修复后的 stream_chat 真实发请求并返回完整文本
        result = self._llm.stream_chat(
            msg_objs, callback=_sc, provider=provider, model=model,
            temperature=temperature, tools=tools)
        final_text = (result if isinstance(result, str)
                      else "".join(content_chunks))
        # 流式路径的 tool_calls 从底层聚合响应提取（LLMProvider.stream_chat
        # 聚合后通过 last_stream_response 暴露）；底层未提供时视为无工具调用
        aggregated = getattr(self._llm, "last_stream_response", None)
        return aggregated, final_text

    @staticmethod
    def _extract_tool_calls(response: Optional[ChatResponse]) -> List[ToolCall]:
        """从响应中提取类型化的工具调用列表（防御性兼容裸 dict）

        Args:
            response: 本轮 LLM 响应（可能为 None）

        Returns:
            List[ToolCall]: 工具调用列表，无工具调用时为空列表
        """
        raw_calls = (getattr(response, "tool_calls", None)
                     if response is not None else None)
        if not raw_calls or not isinstance(raw_calls, (list, tuple)):
            return []
        calls: List[ToolCall] = []
        for item in raw_calls:
            if isinstance(item, ToolCall):
                calls.append(item)
            elif isinstance(item, dict):
                calls.append(ToolCall.from_dict(item))
        return calls

    @staticmethod
    def _normalize_call_ids(tool_calls: List[ToolCall]) -> List[ToolCall]:
        """补齐缺失的工具调用 id（同名工具多次调用时 id 也要唯一）

        Args:
            tool_calls: 工具调用列表

        Returns:
            List[ToolCall]: id 齐备的工具调用列表
        """
        normalized: List[ToolCall] = []
        for idx, call in enumerate(tool_calls):
            if call.id:
                normalized.append(call)
                continue
            normalized.append(ToolCall(
                id=f"call_{call.name}_{idx}",
                name=call.name,
                arguments=call.arguments,
                raw_arguments=call.raw_arguments,
            ))
        return normalized

    @staticmethod
    def _build_tool_call_message(
        content: str,
        tool_calls: List[ToolCall],
    ) -> Dict[str, Any]:
        """构造携带 tool_calls 的 assistant 消息（OpenAI 消息序列契约）

        GLM 兼容性：无文本时用空串而非 None。

        Args:
            content: 本轮助手文本（可能为空串）
            tool_calls: 已补齐 id 的工具调用列表

        Returns:
            Dict[str, Any]: OpenAI 格式的 assistant 消息
        """
        return {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [call.to_dict() for call in tool_calls],
        }

    def _execute_tool_calls(
        self,
        tool_calls: List[ToolCall],
        tool_results: List[ToolResult],
        messages: List[Dict],
    ) -> None:
        """逐个执行工具调用，追加 ToolResult 记录与 tool 角色消息

        Args:
            tool_calls: 已补齐 id 的工具调用列表
            tool_results: 工具结果记录列表（就地追加）
            messages: 消息记录列表（就地追加 tool 角色消息）
        """
        for call in tool_calls:
            result, error = self._invoke_tool(call)
            tool_results.append(ToolResult(
                tool_name=call.name,
                arguments=call.arguments,
                result=result,
                error=error,
            ))
            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "content": str(result),
            })

    def _invoke_tool(self, call: ToolCall) -> Tuple[Any, Optional[str]]:
        """执行单个工具调用

        参数 JSON 非法（raw_arguments 有值）时不执行，把原始字符串放入
        tool 响应告知模型重新生成；工具不存在或执行异常以错误文本返回，
        不向上抛异常（保证循环可继续）。

        Args:
            call: 类型化的工具调用

        Returns:
            Tuple[Any, Optional[str]]: (执行结果或错误文本, 错误信息)
        """
        if call.raw_arguments is not None:
            result = (f"Error: invalid arguments JSON for tool "
                      f"'{call.name}': {call.raw_arguments}")
            logger.warning(
                f"Tool '{call.name}' received invalid arguments "
                f"JSON: {call.raw_arguments}")
            return result, result
        handler = self._registry.get_handler(call.name)
        if not handler:
            result = f"Error: tool '{call.name}' not found"
            logger.error(result)
            return result, result
        try:
            return self._call_handler(handler, call.arguments), None
        except Exception as e:
            result = f"Error executing {call.name}: {e}"
            logger.error(result)
            return result, result

    @staticmethod
    def _call_handler(handler: Callable, arguments: Dict[str, Any]) -> Any:
        """调用工具处理函数

        handler 声明 **kwargs 时全量透传参数，否则只传签名中声明的
        参数，避免模型多产出参数导致 TypeError。

        Args:
            handler: 工具处理函数
            arguments: 调用参数字典

        Returns:
            Any: 处理函数的返回值
        """
        sig = inspect.signature(handler)
        has_var_keyword = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in sig.parameters.values()
        )
        if has_var_keyword:
            return handler(**arguments)
        filtered_kwargs = {k: v for k, v in arguments.items()
                           if k in sig.parameters}
        return handler(**filtered_kwargs)
