"""LLM 层新增数据类型模块

集中管理 LLMPluginService 相关的新增数据类型，与 provider_interface.py 互补。

新增类型:
    - Conversation: 对话数据模型
    - ToolResult: 工具调用结果
    - UsageStats: 用量统计
    - ImageResult: 图像生成结果
    - AudioResult: 语音合成结果
    - ProviderInfo: Provider 信息（面向插件开发者的友好格式）
    - StreamChunk: 流式响应的一个 chunk
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .provider_interface import UsageInfo


@dataclass
class Conversation:
    """对话数据模型

    表示一个完整的对话会话，包含历史消息和统计信息。

    Attributes:
        id: 对话唯一标识符
        created_at: 创建时间
        updated_at: 最后更新时间
        system_prompt: 系统提示词
        messages: 消息历史列表
        total_tokens: 累计 token 数
        total_cost: 累计费用（元）
        provider: 使用的 Provider 名称
        model: 使用的模型名称
        metadata: 额外元数据
    """
    id: str
    created_at: datetime
    updated_at: datetime
    system_prompt: Optional[str] = None
    messages: List[Dict] = field(default_factory=list)
    total_tokens: int = 0
    total_cost: float = 0.0
    provider: str = ""
    model: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_llm_format(self) -> List[Dict]:
        """转换为 LLM 接口所需的 messages 格式

        自动拼接 system_prompt 和消息历史。

        Returns:
            List[Dict]: 符合 LLM API 格式的消息列表
        """
        result = []
        if self.system_prompt:
            result.append({"role": "system", "content": self.system_prompt})
        result.extend(self.messages)
        return result

    def add_message(
        self,
        role: str,
        content: str,
        usage: Optional["UsageInfo"] = None,
        **kwargs
    ):
        """追加消息，自动更新统计

        Args:
            role: 消息角色
            content: 消息内容
            usage: 用量信息（可选）
            **kwargs: 其他字段（如 images、tool_calls 等）
        """
        msg = {"role": role, "content": content}
        msg.update(kwargs)
        self.messages.append(msg)
        self.updated_at = datetime.now()
        if usage:
            if usage.total_tokens:
                self.total_tokens += usage.total_tokens
            if usage.total_cost:
                self.total_cost += usage.total_cost

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 持久化的字典

        Returns:
            Dict[str, Any]: 包含全部会话字段的字典（时间字段为 ISO 格式字符串）
        """
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "system_prompt": self.system_prompt,
            "messages": self.messages,
            "total_tokens": self.total_tokens,
            "total_cost": self.total_cost,
            "provider": self.provider,
            "model": self.model,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Conversation":
        """从字典反序列化为 Conversation 对象

        Args:
            d: to_dict() 产出的字典

        Returns:
            Conversation: 会话对象
        """
        def _parse_dt(value) -> datetime:
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    pass
            return datetime.now()

        return cls(
            id=d.get("id", ""),
            created_at=_parse_dt(d.get("created_at")),
            updated_at=_parse_dt(d.get("updated_at")),
            system_prompt=d.get("system_prompt"),
            messages=list(d.get("messages", [])),
            total_tokens=d.get("total_tokens", 0),
            total_cost=d.get("total_cost", 0.0),
            provider=d.get("provider", ""),
            model=d.get("model", ""),
            metadata=dict(d.get("metadata", {})),
        )


@dataclass
class ToolResult:
    """工具调用结果

    表示一次工具调用的执行结果。

    Attributes:
        tool_name: 工具名称
        arguments: 传入的工具参数
        result: 工具执行结果
        error: 错误信息（如果有）
        duration_ms: 执行耗时（毫秒）
    """
    tool_name: str
    arguments: Dict[str, Any]
    result: Any = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class UsageStats:
    """用量统计

    汇总一个或多个对话的 token 消耗和费用。

    Attributes:
        total_input_tokens: 总输入 token 数
        total_output_tokens: 总输出 token 数
        total_tokens: 总 token 数
        total_cost: 总费用（元）
        request_count: 消息条数
        by_provider: 按 Provider 分组的费用统计
    """
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    request_count: int = 0
    by_provider: Dict[str, float] = field(default_factory=dict)


@dataclass
class ImageResult:
    """图像生成结果

    表示一次图像生成请求的响应。

    Attributes:
        url: 生成的图像 URL（如果有）
        base64: base64 编码的图像数据（如果有）
        revised_prompt: 经过模型修订的提示词
        model: 使用的模型名称
        provider: 使用的 Provider 名称
    """
    url: Optional[str] = None
    base64: Optional[str] = None
    revised_prompt: Optional[str] = None
    model: str = ""
    provider: str = ""


@dataclass
class AudioResult:
    """语音合成结果

    表示一次 TTS 请求的响应。

    Attributes:
        audio_data: 音频数据（字节）
        url: 音频 URL（如果有）
        duration_seconds: 音频时长（秒）
        model: 使用的模型名称
        provider: 使用的 Provider 名称
    """
    audio_data: Optional[bytes] = None
    url: Optional[str] = None
    duration_seconds: Optional[float] = None
    model: str = ""
    provider: str = ""


@dataclass
class ProviderInfo:
    """Provider 信息（面向插件开发者的友好格式）

    封装 Provider 的配置状态和能力信息。

    Attributes:
        name: Provider 名称
        provider_type: Provider 类型
        enabled_chat: 是否启用聊天功能
        enabled_embedding: 是否启用嵌入功能
        supports_vision: 是否支持视觉
        supports_function_calling: 是否支持函数调用
        current_chat_model: 当前聊天模型
        current_embedding_model: 当前嵌入模型
        models: 可用模型列表
        is_healthy: Provider 是否健康
        last_error: 最近一次错误信息
        rate_limit_rpm: 每分钟请求限制
    """
    name: str
    provider_type: str
    enabled_chat: bool
    enabled_embedding: bool
    supports_vision: bool
    supports_function_calling: bool
    current_chat_model: str
    current_embedding_model: str
    models: List[Any] = field(default_factory=list)
    is_healthy: bool = True
    last_error: Optional[str] = None
    rate_limit_rpm: Optional[int] = None


@dataclass
class StreamChunk:
    """流式响应的一个 chunk

    表示流式响应中的单个数据块。

    Attributes:
        content: 本次 chunk 的文本内容
        done: 是否为最后一个 chunk
        full_response: 到目前为止的完整响应
        reasoning_content: 思考过程内容
        tool_calls: 工具调用列表
        usage: Token 用量信息
        error: 错误信息（如果有）
    """
    content: str
    done: bool = False
    full_response: str = ""
    reasoning_content: Optional[str] = None
    tool_calls: List[Dict] = field(default_factory=list)
    usage: Optional[UsageInfo] = None
    error: Optional[str] = None


@dataclass
class UsageRecord:
    """单次 LLM API 请求的用量记录（带时间戳）。

    通过 UsageRecordStore 持久化到 data/llm_usage.json。

    Attributes:
        id: 记录唯一 ID（UUID4 hex 字符串）
        timestamp: 请求的精确 UTC 时间
        conversation_id: 关联的对话 ID，无对话上下文时为 ""
        provider: 提供商名称（如 "minimax"、"glm"）
        model: 本次请求使用的模型 ID
        input_tokens: 输入（提示词）token 数
        output_tokens: 输出（补全）token 数
        total_tokens: 输入与输出 token 数之和
        cached_tokens: 命中提示词缓存的 token 数（无缓存时为 0）
        cache_hit: 是否有至少部分 token 命中缓存
        is_stream: 是否为流式请求
        duration_ms: 请求耗时（毫秒）
    """
    id: str
    timestamp: datetime
    conversation_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_tokens: int
    cache_hit: bool
    is_stream: bool
    duration_ms: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_tokens": self.cached_tokens,
            "cache_hit": self.cache_hit,
            "is_stream": self.is_stream,
            "duration_ms": self.duration_ms,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "UsageRecord":
        ts = d["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        return cls(
            id=d["id"],
            timestamp=ts,
            conversation_id=d.get("conversation_id", ""),
            provider=d["provider"],
            model=d["model"],
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            total_tokens=d.get("total_tokens", 0),
            cached_tokens=d.get("cached_tokens", 0),
            cache_hit=d.get("cache_hit", False),
            is_stream=d.get("is_stream", False),
            duration_ms=d.get("duration_ms", 0.0),
        )
