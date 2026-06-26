"""对话管理器模块

管理对话的完整生命周期，自动处理上下文窗口、token 预算、历史截断。
插件开发者无需关心对话状态管理。

Classes:
    ConversationManager: 对话生命周期管理器
"""

import uuid
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable, TYPE_CHECKING

from .types import Conversation, UsageStats, StreamChunk
from .provider_interface import UsageInfo, Message, ChatResponse
from .llm_provider import get_llm_provider
from .usage_record_store import get_usage_record_store
from .types import UsageRecord
import time

logger = logging.getLogger(__name__)


class ConversationManager:
    """对话管理器 — 插件开发者无需关心上下文管理

    管理所有对话的生命周期：
    - 创建 / 获取 / 列出 / 删除对话
    - 发送消息（同步 / 流式）
    - Token 累计与用量记录
    - 用量统计查询
    """

    def __init__(
        self,
        pricing: Optional[Dict[str, Dict]] = None,
        **kwargs,
    ):
        """初始化对话管理器

        Args:
            pricing: 定价表（格式：{provider: {chat: {input_per_1k, output_per_1k}}}，单位：元/百万token）
            **kwargs: 兼容旧参数（如 max_context），已废弃但会被吸收
        """
        self._conversations: Dict[str, Conversation] = {}
        self._llm = get_llm_provider()
        self._pricing = pricing or {}
        self._logger = logger
        self._usage_store = get_usage_record_store()

    # ==================== 对话 CRUD ====================

    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        provider: str = "default",
        model: str = "default",
        metadata: Optional[Dict] = None,
    ) -> str:
        """创建一个新对话

        Args:
            system_prompt: 系统提示词
            provider: Provider 名称
            model: 模型名称
            metadata: 额外元数据

        Returns:
            str: 新对话的唯一 ID
        """
        conv_id = str(uuid.uuid4())
        self._conversations[conv_id] = Conversation(
            id=conv_id,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            metadata=metadata or {},
        )
        self._logger.info(f"Conversation created: {conv_id}")
        return conv_id

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话对象

        Args:
            conversation_id: 对话 ID

        Returns:
            Optional[Conversation]: 对话对象，不存在则返回 None
        """
        return self._conversations.get(conversation_id)

    def list_conversations(self) -> List[Conversation]:
        """列出所有对话

        Returns:
            List[Conversation]: 对话列表
        """
        return list(self._conversations.values())

    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话

        Args:
            conversation_id: 对话 ID

        Returns:
            bool: 是否成功删除
        """
        if conversation_id in self._conversations:
            del self._conversations[conversation_id]
            self._logger.info(f"Conversation deleted: {conversation_id}")
            return True
        return False

    # ==================== 发送消息 ====================

    def send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> tuple[str, Optional[UsageInfo]]:
        """同步发送消息，自动追加到历史

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            tuple[str, Optional[UsageInfo]]: (响应内容, 用量信息)
        """
        conv = self._get_or_raise(conversation_id)

        messages = conv.to_llm_format()
        user_msg: Dict[str, Any] = {"role": "user", "content": content}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)
        conv.add_message("user", content, images=images if images else None)

        msg_objs = [Message(**m) if isinstance(m, dict) else m for m in messages]
        t0 = time.perf_counter()
        response = self._llm.chat(
            messages=msg_objs,
            provider=conv.provider if conv.provider != "default" else None,
            model=conv.model if conv.model != "default" else None,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
        duration_ms = (time.perf_counter() - t0) * 1000

        conv.add_message("assistant", response.content,
                         getattr(response, 'usage', None))
        if response.usage:
            cost = self._estimate_cost(response.usage, conv.provider, conv.model)
            if cost:
                conv.total_cost += cost

        record = self._build_usage_record(
            usage=getattr(response, 'usage', None),
            conversation_id=conversation_id,
            provider=conv.provider,
            model=conv.model,
            is_stream=False,
            duration_ms=duration_ms,
        )
        if record:
            self._usage_store.record(record)

        return response.content, getattr(response, 'usage', None)

    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[[StreamChunk], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> tuple[str, Optional[UsageInfo]]:
        """流式发送消息，逐 chunk 通过 callback 回调

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            callback: 流式回调函数
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            tuple[str, Optional[UsageInfo]]: (完整响应内容, 用量信息)
        """
        conv = self._get_or_raise(conversation_id)

        messages = conv.to_llm_format()
        user_msg: Dict[str, Any] = {"role": "user", "content": content}
        if images:
            user_msg["images"] = images
        messages.append(user_msg)

        full_content = []
        last_usage: Optional[UsageInfo] = None

        def stream_callback(cr: ChatResponse, done: bool):
            nonlocal last_usage
            full_content.append(cr.content)
            if cr.usage:
                last_usage = cr.usage
            sc = StreamChunk(
                content=cr.content,
                done=done,
                full_response="".join(full_content),
            )
            if callback:
                try:
                    callback(sc)
                except Exception as e:
                    self._logger.error(f"Stream callback error: {e}")

        msg_objs = [Message(**m) if isinstance(m, dict) else m for m in messages]

        t0 = time.perf_counter()
        try:
            self._llm.stream_chat(
                messages=msg_objs,
                callback=stream_callback,
                provider=conv.provider if conv.provider != "default" else None,
                model=conv.model if conv.model != "default" else None,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
        except Exception as e:
            sc = StreamChunk(content="", done=True, error=str(e))
            if callback:
                callback(sc)
            raise
        duration_ms = (time.perf_counter() - t0) * 1000

        final_content = "".join(full_content)
        conv.add_message("user", content, images=images if images else None)
        if final_content:
            conv.add_message("assistant", final_content, last_usage)

        record = self._build_usage_record(
            usage=last_usage,
            conversation_id=conversation_id,
            provider=conv.provider,
            model=conv.model,
            is_stream=True,
            duration_ms=duration_ms,
        )
        if record:
            self._usage_store.record(record)

        return final_content, last_usage

    def _estimate_cost(
        self,
        usage: UsageInfo,
        provider: str,
        model: str
    ) -> Optional[float]:
        """估算单次请求费用

        优先查找模型级别定价，再回退到 Provider 级别定价。

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
        input_price = model_pricing.get("input_per_1k", chat_pricing.get("input_per_1k", 0))
        output_price = model_pricing.get("output_per_1k", chat_pricing.get("output_per_1k", 0))
        return (usage.input_tokens or 0) / 1000000 * input_price + \
               (usage.output_tokens or 0) / 1000000 * output_price

    def _build_usage_record(
        self,
        usage,
        conversation_id: str,
        provider: str,
        model: str,
        is_stream: bool,
        duration_ms: float,
    ) -> Optional[UsageRecord]:
        """构建用量记录"""
        if usage is None:
            return None
        import uuid
        cached_tokens = getattr(usage, 'cache_read_tokens', 0) or 0
        return UsageRecord(
            id=uuid.uuid4().hex,
            timestamp=datetime.now(),
            conversation_id=conversation_id,
            provider=provider or "",
            model=model or "",
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            total_tokens=usage.total_tokens or 0,
            cached_tokens=cached_tokens,
            cache_hit=cached_tokens > 0,
            is_stream=is_stream,
            duration_ms=round(duration_ms, 2),
        )

    def _get_or_raise(self, conversation_id: str) -> Conversation:
        """获取对话，不存在则抛出 ValueError

        Args:
            conversation_id: 对话 ID

        Returns:
            Conversation: 对话对象

        Raises:
            ValueError: 对话不存在
        """
        conv = self._conversations.get(conversation_id)
        if not conv:
            raise ValueError(f"Conversation not found: {conversation_id}")
        return conv

    # ==================== 用量统计 ====================

    def get_usage_stats(
        self,
        conversation_id: Optional[str] = None
    ) -> UsageStats:
        """获取用量统计

        Args:
            conversation_id: 对话 ID（可选，为 None 时返回全局统计）

        Returns:
            UsageStats: 用量统计
        """
        stats = UsageStats()
        convs = ([self._conversations[conversation_id]]
                 if conversation_id else self._conversations.values())
        for conv in convs:
            stats.total_tokens += conv.total_tokens
            stats.total_cost += conv.total_cost
            stats.by_provider[conv.provider] = (
                stats.by_provider.get(conv.provider, 0) + conv.total_cost
            )
        stats.request_count = sum(len(c.messages) for c in convs)
        return stats
