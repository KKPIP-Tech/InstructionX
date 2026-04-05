"""工具调用执行器模块

自动处理 LLM → 工具调用 → 结果回传 → 再次 LLM 的完整两轮循环。
插件开发者只需注册工具，调用 chat_with_tools 即可。

Classes:
    ToolRegistry: 工具注册表
    ToolCallExecutor: 工具调用执行器
"""

import json
import logging
import inspect
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import ToolResult, StreamChunk
from .provider_interface import Message

logger = logging.getLogger(__name__)


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
    ) -> None:
        """注册一个工具

        Args:
            name: 工具名称（唯一）
            description: 工具描述（会发给 LLM）
            parameters: OpenAI 风格的 parameters schema
            handler: 实际执行的函数，签名为 handler(**kwargs) -> Any
        """
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")

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
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
        stream: bool = False,
        stream_callback: Optional[Callable[[str, bool], None]] = None,
    ) -> Tuple[List[Dict], List[ToolResult], Any]:
        """
        带有工具调用的对话

        Args:
            messages: 消息列表
            provider: Provider 名称
            model: 模型名称
            max_turns: 最多工具调用轮数（防止无限循环）
            temperature: 温度参数
            stream: 是否流式
            stream_callback: 流式回调函数

        Returns:
            Tuple[List[Dict], List[ToolResult], Any]:
                (最终消息列表, 工具调用结果列表, 最终响应内容)
        """
        if not self._registry.list_tools():
            if stream:
                return messages, [], self._llm.stream_chat(
                    messages, callback=stream_callback,
                    provider=provider, model=model, temperature=temperature
                )
            return messages, [], self._llm.chat(
                messages, provider=provider, model=model, temperature=temperature
            )

        tools = self._registry.get_tools()
        tool_results: List[ToolResult] = []
        turn = 0
        messages = list(messages)

        while turn < max_turns:
            turn += 1
            logger.debug(f"Tool call turn {turn}/{max_turns}")

            if stream:
                content_chunks = []
                def _sc(chunk: str, done: bool):
                    content_chunks.append(chunk)
                    if stream_callback:
                        stream_callback(chunk, done)
                msg_objs = [Message(**m) if isinstance(m, dict) else m
                            for m in messages]
                self._llm.stream_chat(
                    msg_objs, callback=_sc,
                    provider=provider, model=model, temperature=temperature,
                    tools=tools,
                )
                final_content = "".join(content_chunks)
                response = None
            else:
                msg_objs = [Message(**m) if isinstance(m, dict) else m
                            for m in messages]
                response = self._llm.chat(
                    msg_objs,
                    provider=provider, model=model, temperature=temperature,
                    tools=tools,
                )
                final_content = (response.content
                                 if hasattr(response, 'content') else response)

            tool_calls = []
            if response and hasattr(response, 'tool_calls') and response.tool_calls:
                tool_calls = response.tool_calls

            if not tool_calls:
                if response and hasattr(response, 'content'):
                    messages.append({"role": "assistant",
                                     "content": response.content})
                return messages, tool_results, response or final_content

            # 处理工具调用
            for tc in tool_calls:
                tool_name = tc.get("function", {}).get("name", "")
                arguments = tc.get("function", {}).get("arguments", "{}")

                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                handler = self._registry.get_handler(tool_name)
                if not handler:
                    result = f"Error: tool '{tool_name}' not found"
                    logger.error(result)
                else:
                    try:
                        sig = inspect.signature(handler)
                        has_var_keyword = any(
                            p.kind == inspect.Parameter.VAR_KEYWORD
                            for p in sig.parameters.values()
                        )
                        if has_var_keyword:
                            result = handler(**arguments)
                        else:
                            filtered_kwargs = {
                                k: v for k, v in arguments.items()
                                if k in sig.parameters
                            }
                            result = handler(**filtered_kwargs)
                    except Exception as e:
                        result = f"Error executing {tool_name}: {e}"
                        logger.error(result)

                tool_result = ToolResult(
                    tool_name=tool_name,
                    arguments=arguments,
                    result=result,
                    error=str(result) if str(result).startswith("Error") else None,
                )
                tool_results.append(tool_result)

                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": tc.get("id", f"call_{tool_name}"),
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": (arguments if isinstance(arguments, str)
                                         else json.dumps(arguments)),
                        }
                    }]
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", f"call_{tool_name}"),
                    "content": str(result),
                })

        logger.warning(f"Tool call loop exceeded max_turns ({max_turns})")
        return messages, tool_results, final_content

    def chat_with_tools_stream(
        self,
        messages: List[Dict],
        callback: Callable[[StreamChunk], None],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> Tuple[List[Dict], List[ToolResult], str]:
        """流式版本的 chat_with_tools

        Args:
            messages: 消息列表
            callback: 流式回调
            provider: Provider 名称
            model: 模型名称
            max_turns: 最多工具调用轮数
            temperature: 温度参数

        Returns:
            Tuple[List[Dict], List[ToolResult], str]: (消息列表, 工具结果, 最终内容)
        """
        def _sc(chunk: str, done: bool):
            callback(StreamChunk(content=chunk, done=done))
        return self.chat_with_tools(
            messages=messages,
            provider=provider,
            model=model,
            max_turns=max_turns,
            temperature=temperature,
            stream=True,
            stream_callback=_sc,
        )
