"""LLM 层新增数据类型模块

集中管理 LLMPluginService 相关的新增数据类型，与 provider_interface.py 互补。

新增类型:
    - Conversation: 对话数据模型
    - ToolResult: 工具调用结果
    - ToolChatResult: 带工具调用对话的结构化结果
    - ToolDefinition: 类型化的工具定义
    - UsageStats: 用量统计
    - ImageResult: 图像生成结果
    - AudioResult: 语音合成结果
    - ProviderInfo: Provider 信息（面向插件开发者的友好格式）
    - StreamChunk: 流式响应的一个 chunk
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .provider_interface import ChatResponse, ModelInfo, ToolCall, UsageInfo


# 默认实例引用：provider 参数取该值时表示「默认实例」，不指向任何具体实例，
# 由 LLMProvider 按功能维度（chat/embedding）解析为实际实例 id（带粘性缓存）。
# 定义该常量用于消除贯穿各层的 "default" 魔法字符串。
DEFAULT_PROVIDER = "default"

# 默认模型引用：model 参数取该值时表示「使用实例配置中的默认模型」，
# 由 LLMProvider 层解析为实例配置的 chat_model / embedding_model。
DEFAULT_MODEL = "default"


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
class ToolChatResult:
    """带工具调用对话的结构化结果

    替代旧的三元组返回（messages, tool_results, final），字段类型固定，
    不再随 stream 与否变化。

    Attributes:
        messages: 完整对话记录（OpenAI 消息 dict 格式，含 assistant 的
            tool_calls 消息与 tool 角色响应消息），可直接用于后续请求
        tool_results: 本轮循环中全部工具调用的执行结果记录
        final_response: 最终一轮 LLM 响应；流式路径取底层聚合响应
            （last_stream_response），底层未提供时为 None
        final_text: 最终文本内容（流式路径为聚合全文）；无文本时为空串
    """
    messages: List[Dict[str, Any]] = field(default_factory=list)
    tool_results: List[ToolResult] = field(default_factory=list)
    final_response: Optional[ChatResponse] = None
    final_text: str = ""


@dataclass
class ToolDefinition:
    """类型化的工具定义（ToolRegistry.register_typed 的入参）

    Attributes:
        name: 工具名称（唯一）
        description: 工具描述（会发给 LLM）
        parameters: OpenAI 风格的 JSON Schema 参数定义
        handler: 实际执行的函数，签名为 handler(**kwargs) -> Any
    """
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable[..., Any]


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
    """Provider 实例信息（面向插件开发者的友好格式）

    封装一个 Provider 实例的配置状态与运行时健康信息。
    所有字段均有真实数据来源：启用状态/适配器/预设关联/当前模型
    来自 ProviderConfig，base_url 取实例覆写或目录默认，健康状态
    来自 LLMProvider 的健康跟踪，不包含 api_key 等敏感信息。

    Attributes:
        instance_id: 实例唯一标识（配置键名）
        preset_id: 关联的预设目录 ID（完全自定义实例为 None）
        name: 实例显示名
        adapter: 适配器家族键
        base_url: 有效 API 基础地址（实例覆写或目录默认，不含密钥）
        enabled_chat: 是否启用聊天功能（来自真实配置）
        enabled_embedding: 是否启用嵌入功能（来自真实配置）
        is_healthy: 实例是否健康（运行时健康跟踪）
        last_error: 最近一次错误信息（无错误时为 None）
        current_chat_model: 当前聊天模型（实例配置）
        current_embedding_model: 当前嵌入模型（实例配置）
        models: 该实例的可用模型列表
    """
    instance_id: str
    preset_id: Optional[str]
    name: str
    adapter: str
    base_url: str
    enabled_chat: bool
    enabled_embedding: bool
    is_healthy: bool
    last_error: Optional[str]
    current_chat_model: str
    current_embedding_model: str
    models: List[ModelInfo] = field(default_factory=list)


@dataclass
class StreamChunk:
    """流式响应的一个 chunk

    表示流式响应中的单个数据块。

    Attributes:
        content: 本次 chunk 的文本内容
        done: 是否为最后一个 chunk
        full_response: 到目前为止的完整响应
        reasoning_content: 思考过程内容；底层回调契约为 (str, bool) 的
            路径无此数据来源，保持 None
        tool_calls: 类型化的工具调用列表（ToolCall）；仅在底层直接回调
            ChatResponse 块且携带着完整 tool_calls 时填充，否则为空列表
        usage: Token 用量信息；仅在底层末块携带 usage 时填充，否则 None
        error: 错误信息（如果有）
    """
    content: str
    done: bool = False
    full_response: str = ""
    reasoning_content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
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
