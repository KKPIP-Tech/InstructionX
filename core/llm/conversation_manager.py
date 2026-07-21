"""对话管理器模块

管理对话的完整生命周期。
插件开发者无需关心对话状态管理。

特性：
- 上下文窗口自动截断（基于 token 估算，保留 system prompt 与最近消息）
- 消息"调用成功才入历史"（LLM 调用失败不产生孤儿消息）
- 会话持久化（传入 storage_path 时启用，原子写 + 锁，变更即全量写）
- 线程安全（内部字典与持久化均加锁）

Classes:
    ConversationManager: 对话生命周期管理器

Functions:
    estimate_tokens: 文本 token 数估算器（可独立测试）
    estimate_messages_tokens: 消息列表 token 数估算
"""

import json
import os
import threading
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable, Union

from .types import (
    DEFAULT_MODEL, DEFAULT_PROVIDER,
    Conversation, StreamChunk, UsageStats,
)
from .provider_interface import UsageInfo, Message
from .llm_provider import get_llm_provider

logger = logging.getLogger(__name__)

# 上下文截断时始终保留的最近消息条数
_KEEP_RECENT_MESSAGES = 4

# 默认最大上下文 token 数
DEFAULT_MAX_CONTEXT_TOKENS = 120000


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数

    估算规则：中文/日文/韩文（CJK）字符按 ~1 token/字，
    其他字符按 ~4 字符/token。

    Args:
        text: 待估算文本

    Returns:
        int: 估算的 token 数
    """
    if not text:
        return 0
    cjk_count = 0
    for ch in text:
        # CJK 统一表意文字、扩展A、日文平/片假名、韩文音节
        if ('\u4e00' <= ch <= '\u9fff'
                or '\u3400' <= ch <= '\u4dbf'
                or '\u3040' <= ch <= '\u30ff'
                or '\uac00' <= ch <= '\ud7a3'):
            cjk_count += 1
    other_count = len(text) - cjk_count
    return cjk_count + (other_count + 3) // 4


def estimate_messages_tokens(messages: List[Dict]) -> int:
    """估算消息列表的总 token 数（含每条消息的结构开销）

    Args:
        messages: 消息字典列表

    Returns:
        int: 估算的总 token 数
    """
    total = 0
    for m in messages:
        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        total += 4  # 每条消息的 role/结构开销
    return total


class ConversationManager:
    """对话管理器 — 插件开发者无需关心上下文管理

    管理所有对话的生命周期：
    - 创建 / 获取 / 列出 / 删除对话
    - 发送消息（同步 / 流式），上下文超限时自动截断
    - Token 累计与费用估算
    - 用量统计查询
    - 会话持久化（可选，传入 storage_path 启用）

    消息历史语义：LLM 调用成功才把用户消息与助手回复写入历史，
    调用失败时历史保持不变（无孤儿消息）。
    """

    def __init__(
        self,
        pricing: Optional[Dict[str, Dict]] = None,
        max_context_tokens: Optional[int] = DEFAULT_MAX_CONTEXT_TOKENS,
        storage_path: Optional[Union[str, Path]] = None,
        **kwargs,
    ):
        """初始化对话管理器

        Args:
            pricing: 定价表。新契约单位：元/百万 tokens（per_1m），结构
                {provider: {"models": {model: {"input": x, "output": y}},
                            "chat": {"input": x, "output": y}}}
                兼容旧格式（元/千 tokens，键 input_per_1k/output_per_1k）
            max_context_tokens: 最大上下文 token 估算阈值，默认 120000；
                发送前超出阈值时从最早的用户/助手消息开始丢弃
                （system prompt 与最近几条消息保留）
            storage_path: 会话持久化文件路径（如 data/conversations.json）；
                为 None 时不持久化（纯内存模式）
            **kwargs: 兼容旧参数（如 max_context），已废弃但会被吸收
        """
        self._conversations: Dict[str, Conversation] = {}
        self._lock = threading.RLock()
        self._llm = get_llm_provider()
        self._pricing = pricing or {}
        self._logger = logger
        self._max_context_tokens = (
            max_context_tokens if max_context_tokens is not None
            else DEFAULT_MAX_CONTEXT_TOKENS
        )
        self._storage_path = Path(storage_path) if storage_path else None
        if self._storage_path:
            self._load_conversations()

    # ==================== 对话 CRUD ====================

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
        metadata: Optional[Dict] = None,
    ) -> str:
        """创建一个新对话

        Args:
            system_prompt: 系统提示词
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称，DEFAULT_MODEL 表示使用实例配置中的模型
            metadata: 额外元数据

        Returns:
            str: 新对话的唯一 ID
        """
        conv_id = str(uuid.uuid4())
        with self._lock:
            self._conversations[conv_id] = Conversation(
                id=conv_id,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                system_prompt=system_prompt,
                provider=provider,
                model=model,
                metadata=metadata or {},
            )
        self._save_conversations()
        self._logger.info(f"Conversation created: {conv_id}")
        return conv_id

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话对象

        Args:
            conversation_id: 对话 ID

        Returns:
            Optional[Conversation]: 对话对象，不存在则返回 None
        """
        with self._lock:
            return self._conversations.get(conversation_id)

    def list_conversations(self) -> List[Conversation]:
        """列出所有对话

        Returns:
            List[Conversation]: 对话列表
        """
        with self._lock:
            return list(self._conversations.values())

    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话（同步从持久化文件中删除）

        Args:
            conversation_id: 对话 ID

        Returns:
            bool: 是否成功删除
        """
        with self._lock:
            if conversation_id not in self._conversations:
                return False
            del self._conversations[conversation_id]
        self._save_conversations()
        self._logger.info(f"Conversation deleted: {conversation_id}")
        return True

    # ==================== 发送消息 ====================

    def send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> tuple[str, Optional[UsageInfo]]:
        """同步发送消息，调用成功后自动追加到历史

        上下文超出 max_context_tokens 时自动从最早的用户/助手消息开始截断
        （system prompt 与最近消息保留）。LLM 调用失败时历史保持不变。

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            temperature: 温度参数（可选，None 表示不指定）
            max_tokens: 最大 token 数（可选，None 表示不指定）
            tools: 工具定义列表（可选）
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            tuple[str, Optional[UsageInfo]]: (响应内容, 用量信息)
        """
        conv = self._get_or_raise(conversation_id)
        call_provider, call_model = self._resolve_call_target(conv, provider, model)

        # 基于历史构建请求消息（此时不写入历史，调用成功才入历史）
        messages = conv.to_llm_format()
        user_msg: Dict[str, Any] = {"role": "user", "content": content}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)
        messages = self._truncate_messages(messages)

        msg_objs = [Message.from_dict(m) if isinstance(m, dict) else m for m in messages]
        # None 表示"不指定"，不传给底层（避免写入 payload 变成 null）
        call_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if tools is not None:
            call_kwargs["tools"] = tools

        # DEFAULT_PROVIDER 原样透传，由 LLMProvider 层解析；用量记录也在该层完成
        response = self._llm.chat(
            messages=msg_objs,
            provider=call_provider,
            model=call_model,
            conversation_id=conversation_id,
            **call_kwargs,
        )

        # 调用成功才写入历史（避免孤儿消息）
        usage = getattr(response, 'usage', None)
        conv.add_message("user", content, images=images if images else None)
        conv.add_message("assistant", response.content, usage)
        if usage:
            cost = self._estimate_cost(usage, call_provider, call_model)
            if cost:
                conv.total_cost += cost
        self._save_conversations()

        return response.content, usage

    @staticmethod
    def _resolve_call_target(
        conv: Conversation,
        provider: Optional[str],
        model: Optional[str],
    ) -> tuple[str, str]:
        """解析本次调用的实例与模型（临时覆盖优先，不修改会话绑定）

        Args:
            conv: 会话对象（绑定的 provider/model 作为缺省值）
            provider: 临时覆盖的实例 id，None 表示使用会话绑定
            model: 临时覆盖的模型，None 表示使用会话绑定

        Returns:
            tuple[str, str]: (实际实例引用, 实际模型引用)
        """
        call_provider = provider if provider is not None else (conv.provider or DEFAULT_PROVIDER)
        call_model = model if model is not None else (conv.model or DEFAULT_MODEL)
        return call_provider, call_model

    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[[StreamChunk], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> tuple[str, Optional[UsageInfo]]:
        """流式发送消息，逐 chunk 通过 callback 回调

        与 send_message 语义一致：LLM 调用成功才把消息写入历史。
        底层流式回调契约 (chunk_text: str, done: bool) 在此适配为
        对外的 StreamChunk 回调。

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            callback: 流式回调函数（接收 StreamChunk）
            temperature: 温度参数（可选，None 表示不指定）
            max_tokens: 最大 token 数（可选，None 表示不指定）
            tools: 工具定义列表（可选）
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            tuple[str, Optional[UsageInfo]]: (完整响应内容, 用量信息)
        """
        conv = self._get_or_raise(conversation_id)
        call_provider, call_model = self._resolve_call_target(conv, provider, model)

        messages = conv.to_llm_format()
        user_msg: Dict[str, Any] = {"role": "user", "content": content}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)
        messages = self._truncate_messages(messages)

        full_content: List[str] = []
        last_usage: Optional[UsageInfo] = None
        last_reasoning: Optional[str] = None
        last_tool_calls: List[Any] = []

        def stream_callback(chunk: Any, done: bool):
            """适配底层 (str, bool) 回调契约为对外 StreamChunk 回调

            防御性兼容底层误传 ChatResponse 的情况（提取其 content/usage/
            reasoning_content/tool_calls）。
            """
            nonlocal last_usage, last_reasoning, last_tool_calls
            if isinstance(chunk, str):
                text = chunk
            else:
                text = getattr(chunk, "content", "") or ""
                if not isinstance(text, str):
                    text = str(text)
                chunk_usage = getattr(chunk, "usage", None)
                if isinstance(chunk_usage, UsageInfo):
                    last_usage = chunk_usage
                chunk_reasoning = getattr(chunk, "reasoning_content", None)
                if isinstance(chunk_reasoning, str) and chunk_reasoning:
                    last_reasoning = chunk_reasoning
                chunk_tool_calls = getattr(chunk, "tool_calls", None)
                if chunk_tool_calls:
                    last_tool_calls = list(chunk_tool_calls)
            full_content.append(text)
            sc = StreamChunk(
                content=text,
                done=done,
                full_response="".join(full_content),
                reasoning_content=last_reasoning,
                tool_calls=last_tool_calls,
                usage=last_usage,
            )
            if callback:
                try:
                    callback(sc)
                except Exception as e:
                    self._logger.error(f"Stream callback error: {e}")

        msg_objs = [Message.from_dict(m) if isinstance(m, dict) else m for m in messages]
        call_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if tools is not None:
            call_kwargs["tools"] = tools

        try:
            result = self._llm.stream_chat(
                messages=msg_objs,
                callback=stream_callback,
                provider=call_provider,
                model=call_model,
                conversation_id=conversation_id,
                **call_kwargs,
            )
        except Exception as e:
            sc = StreamChunk(content="", done=True, error=str(e))
            if callback:
                try:
                    callback(sc)
                except Exception as cb_err:
                    # 错误通知回调本身失败不应掩盖原始异常，记录后继续抛出
                    self._logger.error(f"Stream error callback failed: {cb_err}")
            raise

        # 修复后的 LLMProvider.stream_chat 返回完整文本；
        # 防御底层未返回文本时回退到回调拼接结果
        final_content = result if isinstance(result, str) else "".join(full_content)

        # 调用成功才写入历史（与 send_message 语义一致）
        conv.add_message("user", content, images=images if images else None)
        if final_content:
            conv.add_message("assistant", final_content, last_usage)
        if last_usage:
            cost = self._estimate_cost(last_usage, call_provider, call_model)
            if cost:
                conv.total_cost += cost
        self._save_conversations()

        return final_content, last_usage

    # ==================== 定价表 ====================

    def update_pricing(self, pricing: Dict[str, Dict]) -> None:
        """热更新定价表

        配置变更时由上层（LLMPluginService 的订阅回调）注入重建后的
        定价表，后续费用估算立即使用新表，无需重建对话管理器。

        Args:
            pricing: 新定价表（结构与构造入参一致）
        """
        self._pricing = pricing

    # ==================== 内部方法 ====================

    def _truncate_messages(self, messages: List[Dict]) -> List[Dict]:
        """按 max_context_tokens 截断消息列表

        保留全部 system 消息与最近 _KEEP_RECENT_MESSAGES 条消息，
        从最早的用户/助手消息开始丢弃，直到估算总 token 低于阈值。

        Args:
            messages: 完整消息列表

        Returns:
            List[Dict]: 截断后的消息列表
        """
        if not self._max_context_tokens:
            return messages
        if estimate_messages_tokens(messages) <= self._max_context_tokens:
            return messages

        system_msgs = [m for m in messages
                       if isinstance(m, dict) and m.get("role") == "system"]
        convo_msgs = [m for m in messages
                      if not (isinstance(m, dict) and m.get("role") == "system")]

        dropped = 0
        while len(convo_msgs) > _KEEP_RECENT_MESSAGES:
            if estimate_messages_tokens(system_msgs + convo_msgs) <= self._max_context_tokens:
                break
            convo_msgs.pop(0)
            dropped += 1

        if dropped:
            self._logger.info(
                f"Context truncated: dropped {dropped} oldest messages "
                f"(max_context_tokens={self._max_context_tokens})"
            )
        if estimate_messages_tokens(system_msgs + convo_msgs) > self._max_context_tokens:
            self._logger.warning(
                "Context still exceeds max_context_tokens after truncation "
                "(system prompt 或最近消息过长)"
            )
        return system_msgs + convo_msgs

    def _estimate_cost(
        self,
        usage: UsageInfo,
        provider: str,
        model: str
    ) -> Optional[float]:
        """估算单次请求费用（元）

        优先查找模型级别定价，再回退到 Provider 级别定价。
        新契约：键 "input"/"output"，单位 元/百万 tokens（per_1m），
        费用 = tokens / 1_000_000 × 单价；
        兼容旧格式：键 "input_per_1k"/"output_per_1k"，单位 元/千 tokens。

        Args:
            usage: 用量信息
            provider: Provider 名称
            model: 模型名称

        Returns:
            Optional[float]: 估算费用（元）
        """
        if not usage or usage.total_tokens is None:
            return None
        provider_pricing = self._pricing.get(provider, {})
        # 优先查找模型级别定价
        model_pricing = provider_pricing.get("models", {}).get(model, {})
        chat_pricing = provider_pricing.get("chat", {})
        input_tokens = usage.input_tokens or 0
        output_tokens = usage.output_tokens or 0
        # 新契约：per_1m（元/百万 tokens）
        if any(k in model_pricing or k in chat_pricing for k in ("input", "output")):
            input_price = model_pricing.get("input", chat_pricing.get("input", 0))
            output_price = model_pricing.get("output", chat_pricing.get("output", 0))
            return (input_tokens / 1_000_000 * input_price
                    + output_tokens / 1_000_000 * output_price)
        # 旧格式回退：per_1k（元/千 tokens）
        input_price = model_pricing.get("input_per_1k", chat_pricing.get("input_per_1k", 0))
        output_price = model_pricing.get("output_per_1k", chat_pricing.get("output_per_1k", 0))
        return (input_tokens / 1000 * input_price
                + output_tokens / 1000 * output_price)

    def _get_or_raise(self, conversation_id: str) -> Conversation:
        """获取对话，不存在则抛出 ValueError

        Args:
            conversation_id: 对话 ID

        Returns:
            Conversation: 对话对象

        Raises:
            ValueError: 对话不存在
        """
        with self._lock:
            conv = self._conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation not found: {conversation_id}")
        return conv

    # ==================== 会话持久化 ====================

    def _load_conversations(self) -> None:
        """从持久化文件加载会话（初始化时自动调用）

        文件不存在或损坏时按空会话处理，不抛出异常。
        """
        if not self._storage_path or not self._storage_path.exists():
            return
        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self._logger.warning(f"会话持久化文件读取失败，按空会话处理: {e}")
            return
        loaded = 0
        with self._lock:
            for d in data.get("conversations", []):
                try:
                    conv = Conversation.from_dict(d)
                    self._conversations[conv.id] = conv
                    loaded += 1
                except Exception as e:
                    self._logger.warning(f"跳过损坏的会话记录: {e}")
        if loaded:
            self._logger.info(
                f"Loaded {loaded} conversations from {self._storage_path}")

    def _save_conversations(self) -> None:
        """把全部会话原子写入持久化文件（临时文件 + os.replace）

        每次对话变更后全量写（会话数量少，简单可靠）。
        未配置 storage_path 时为空操作。
        """
        if not self._storage_path:
            return
        with self._lock:
            data = {
                "version": 1,
                "conversations": [c.to_dict() for c in self._conversations.values()],
            }
            try:
                self._storage_path.parent.mkdir(parents=True, exist_ok=True)
                temp_file = self._storage_path.with_suffix(".json.tmp")
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(temp_file, self._storage_path)
            except IOError as e:
                self._logger.error(f"会话持久化写入失败: {e}")

    # ==================== 用量统计 ====================

    def get_usage_stats(
        self,
        conversation_id: Optional[str] = None
    ) -> Optional[UsageStats]:
        """获取用量统计

        Args:
            conversation_id: 对话 ID（可选，为 None 时返回全局统计）

        Returns:
            Optional[UsageStats]: 用量统计；指定了不存在的 conversation_id
                时返回 None。request_count 语义为消息条数。
        """
        stats = UsageStats()
        with self._lock:
            if conversation_id:
                conv = self._conversations.get(conversation_id)
                if conv is None:
                    return None
                convs = [conv]
            else:
                convs = list(self._conversations.values())
            for conv in convs:
                stats.total_tokens += conv.total_tokens
                stats.total_cost += conv.total_cost
                stats.by_provider[conv.provider] = (
                    stats.by_provider.get(conv.provider, 0) + conv.total_cost
                )
            stats.request_count = sum(len(c.messages) for c in convs)
        return stats
