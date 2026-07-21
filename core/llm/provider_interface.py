"""LLM 接口定义模块 - 抽象基类和数据类型

该模块定义了 LLM 提供商的抽象接口 ILLM 以及相关的数据类型。
采用策略模式设计，定义了 LLM 提供商必须实现的接口方法。

数据类型:
    - Message: 聊天消息
    - ToolCall: 类型化的工具调用
    - ChatResponse: 聊天响应
    - EmbeddingResponse: 嵌入响应
    - ModelInfo: 模型信息
    - ModelCheckResult: 单个模型的连通性探测结果

抽象基类:
    - ILLM: LLM 提供商抽象基类，定义同步/异步接口

使用示例:
    >>> from core.llm.provider_interface import Message, ChatResponse, ILLM
    >>> msg = Message(role="user", content="你好")
    >>> print(msg.to_dict())
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, AsyncIterator, Tuple, Union

logger = logging.getLogger(__name__)

# 聊天请求的默认温度参数（各 Provider 签名默认值统一引用此常量）
DEFAULT_TEMPERATURE: float = 0.7


@dataclass
class UsageInfo:
    """Token 用量与费用信息

    表示一次 LLM API 调用的 token 消耗和费用统计。

    Attributes:
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数
        total_tokens: 总 token 数
        input_cost: 输入费用
        output_cost: 输出费用
        total_cost: 总费用
    """
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    input_cost: Optional[float] = None
    output_cost: Optional[float] = None
    total_cost: Optional[float] = None
    cache_read_tokens: Optional[int] = None       # 从缓存读取的 token 数
    cache_creation_tokens: Optional[int] = None   # 写入缓存的 token 数


@dataclass
class ModelCheckResult:
    """单个模型的连通性探测结果

    由 LLMProvider.check_model 返回，描述一次最小化请求探测的结果。

    Attributes:
        ok: 探测是否成功
        latency_ms: 探测耗时（毫秒）；未实际发起请求（skipped）时为 None
        error: 失败原因（成功或未探测时为 None）
        skipped: 是否跳过探测（如提供商实例不存在）
        skip_reason: 跳过原因（skipped 为 True 时填写，中文描述）
    """
    ok: bool
    latency_ms: Optional[float]
    error: Optional[str]
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class ToolCall:
    """类型化的工具调用（与 OpenAI tool_calls 消息格式对齐）

    Attributes:
        id: 调用唯一标识（同一轮并行调用之间必须唯一）
        name: 工具（函数）名称
        arguments: 解析后的调用参数字典
        raw_arguments: arguments 源为字符串且 JSON 解析失败时保留的原始
            字符串（用于把非法参数原文回传给模型，促使其重新生成）；
            正常解析成功时为 None
    """
    id: str = ""
    name: str = ""
    arguments: Dict[str, Any] = field(default_factory=dict)
    raw_arguments: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为 OpenAI tool_calls 格式

        arguments 固定输出为 JSON 字符串；raw_arguments 有值时优先输出
        原始字符串（保留模型下发的原文，便于非法参数场景回传）。

        Returns:
            Dict[str, Any]: {"id", "type": "function",
                "function": {"name", "arguments": <json str>}}
        """
        arguments_str = (self.raw_arguments if self.raw_arguments is not None
                         else json.dumps(self.arguments, ensure_ascii=False))
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.name, "arguments": arguments_str},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolCall":
        """从 OpenAI 风格字典解析为 ToolCall

        兼容两种形态：标准 OpenAI 格式（{"id", "type", "function": {...}}）
        与扁平格式（{"id", "name", "arguments"}）。arguments 为字符串时
        尝试 json.loads，解析失败回退为空 dict 并记 WARNING（原始字符串
        保留在 raw_arguments 中）。

        Args:
            data: OpenAI 风格或扁平风格的 tool_call 字典

        Returns:
            ToolCall: 类型化的工具调用对象
        """
        function = data.get("function")
        if not isinstance(function, dict):
            function = data
        arguments, invalid_raw = cls._parse_arguments(function.get("arguments"))
        return cls(
            id=str(data.get("id") or ""),
            name=str(function.get("name") or ""),
            arguments=arguments,
            raw_arguments=invalid_raw,
        )

    @staticmethod
    def _parse_arguments(raw: Any) -> Tuple[Dict[str, Any], Optional[str]]:
        """解析 arguments 原始值

        Args:
            raw: arguments 原始值（dict / JSON 字符串 / 其他）

        Returns:
            Tuple[Dict[str, Any], Optional[str]]: (解析后的参数字典,
                解析失败时的原始字符串)；解析成功时第二项为 None
        """
        if isinstance(raw, dict):
            return dict(raw), None
        if not isinstance(raw, str) or not raw.strip():
            return {}, None
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("ToolCall arguments JSON 解析失败，回退为空参数: %s", raw)
            return {}, raw
        if isinstance(parsed, dict):
            return parsed, None
        # 合法 JSON 但非对象（如数组）：按空参数处理，与既有执行语义一致
        return {}, None


def _normalize_tool_call(item: Any) -> Any:
    """把 tool_calls 条目标准化为 ToolCall

    带 "index" 键的 dict 视为 OpenAI 流式增量分片（id/name/arguments
    为不完整片段），保持原始 dict 不变，由流式聚合层按 index 合并；
    其余 dict 按完整 tool_call 解析为 ToolCall；非 dict 原样返回。

    Args:
        item: tool_calls 列表中的单个条目

    Returns:
        ToolCall 或原始条目（流式分片 / 无法识别的类型）
    """
    if isinstance(item, ToolCall):
        return item
    if isinstance(item, dict):
        if "index" in item:
            return item
        return ToolCall.from_dict(item)
    return item


class Message:
    """聊天消息类

    表示一次聊天交互中的单条消息，与 OpenAI 消息格式对齐。
    支持视觉（多模态）消息（images）与工具调用消息（tool_calls /
    tool_call_id / name）。

    Attributes:
        role: 消息角色，"user"（用户）/ "assistant"（助手）/
            "system"（系统）/ "tool"（工具响应）
        content: 消息文本内容
        images: 图片 base64 列表（可选），用于视觉模型
        tool_calls: 工具调用列表（可选，assistant 消息携带）
        tool_call_id: 对应的工具调用 id（可选，tool 角色消息携带）
        name: 参与者名称（可选，与 OpenAI 消息格式对齐）
        extra: 额外的消息参数
    """

    def __init__(
        self,
        role: str,
        content: str,
        images: Optional[List[str]] = None,
        tool_calls: Optional[List["ToolCall"]] = None,
        tool_call_id: Optional[str] = None,
        name: Optional[str] = None,
        **kwargs
    ):
        """初始化聊天消息

        Args:
            role: 消息角色
            content: 消息文本内容
            images: 图片 base64 列表（可选）
            tool_calls: 工具调用列表（可选，dict 会自动转换为 ToolCall）
            tool_call_id: 对应的工具调用 id（可选）
            name: 参与者名称（可选）
            **kwargs: 额外的消息参数
        """
        self.role = role
        self.content = content
        self.images = images or []
        self.tool_calls = [_normalize_tool_call(tc) for tc in (tool_calls or [])]
        self.tool_call_id = tool_call_id
        self.name = name
        self.extra = kwargs

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """从字典宽松解析为 Message

        已知扩展键（images/tool_calls/tool_call_id/name）映射为对应字段，
        未知键收入 extra（与构造函数的 **kwargs 行为一致），不会因扩展键
        抛出 TypeError；tool_calls 为 dict 列表时逐项转换为 ToolCall。

        Args:
            data: 消息字典

        Returns:
            Message: 消息对象
        """
        known_keys = {"role", "content", "images", "tool_calls",
                      "tool_call_id", "name"}
        extra = {k: v for k, v in data.items() if k not in known_keys}
        return cls(
            role=data.get("role", ""),
            content=data.get("content", ""),
            images=data.get("images"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
            name=data.get("name"),
            **extra
        )

    def to_dict(self) -> Dict[str, Any]:
        """将消息转换为字典

        转换为符合 LLM API 格式的字典结构：images 保持原样（多模态
        转换在 Provider 层完成），tool_calls 序列化为 OpenAI 格式，
        tool_call_id / name 有值时才输出。

        Returns:
            Dict[str, Any]: 消息字典
        """
        result: Dict[str, Any] = {"role": self.role, "content": self.content}
        if self.images:
            result["images"] = self.images
        if self.tool_calls:
            result["tool_calls"] = [
                tc.to_dict() if isinstance(tc, ToolCall) else tc
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            result["name"] = self.name
        result.update(self.extra)
        return result


class ChatResponse:
    """聊天响应类

    表示 LLM 对聊天请求的响应，包含生成的文本和其他元数据。
    支持思考过程（reasoning_content）和工具调用（tool_calls）。

    Attributes:
        content: 生成的文本内容
        model: 使用的模型名称
        role: 响应角色，默认 "assistant"
        reasoning_content: 思考过程内容（部分模型支持）
        tool_calls: 类型化的工具调用列表（ToolCall）；例外：流式响应块
            携带的 OpenAI 增量分片（带 "index" 键的 dict）保持原始 dict，
            由流式聚合层按 index 合并后再转为 ToolCall
        extra: 额外的响应参数
        usage: Token 用量与费用信息（可选）
    """

    def __init__(
        self,
        content: str,
        model: str,
        role: str = "assistant",
        reasoning_content: str = "",
        tool_calls: Optional[List[ToolCall]] = None,
        usage: Optional[UsageInfo] = None,
        **kwargs
    ):
        """初始化聊天响应

        Args:
            content: 生成的文本内容
            model: 使用的模型名称
            role: 响应角色，默认 "assistant"
            reasoning_content: 思考过程内容
            tool_calls: 工具调用列表（dict 自动转换为 ToolCall；流式增量
                分片保持原始 dict）
            usage: Token 用量与费用信息
            **kwargs: 额外的响应参数
        """
        self.content = content
        self.model = model
        self.role = role
        self.reasoning_content = reasoning_content
        self.tool_calls: List[ToolCall] = [
            _normalize_tool_call(tc) for tc in (tool_calls or [])
        ]
        self.usage = usage
        self.extra = kwargs


class EmbeddingResponse:
    """嵌入响应类

    表示文本嵌入请求的响应，包含向量embedding和模型信息。

    Attributes:
        embedding: 嵌入向量（浮点数列表）
        model: 使用的嵌入模型名称
        extra: 额外的响应参数
    """

    def __init__(
        self,
        embedding: List[float],
        model: str,
        **kwargs
    ):
        """初始化嵌入响应

        Args:
            embedding: 嵌入向量
            model: 嵌入模型名称
            **kwargs: 额外的响应参数
        """
        self.embedding = embedding
        self.model = model
        self.extra = kwargs


class ModelInfo:
    """模型信息类

    描述 LLM 模型的能力和属性，用于模型选择和功能适配。

    Attributes:
        id: 模型唯一标识符
        name: 模型显示名称
        support_chat: 是否支持聊天功能
        support_streaming: 是否支持流式输出
        support_embedding: 是否支持嵌入功能
        support_vision: 是否支持视觉（多模态）
        support_function_calling: 是否支持函数调用
        context_length: 上下文窗口大小（token数）
        extra: 额外的模型参数
        input_price_per_1m: 每百万 token 输入价格（元）
        output_price_per_1m: 每百万 token 输出价格（元）
        provider: 所属提供商名称
    """

    def __init__(
        self,
        id: str,
        name: str,
        support_chat: bool = True,
        support_streaming: bool = True,
        support_embedding: bool = False,
        support_vision: bool = False,
        support_function_calling: bool = False,
        context_length: Optional[int] = None,
        input_price_per_1m: Optional[float] = None,
        output_price_per_1m: Optional[float] = None,
        provider: str = "",
        **kwargs
    ):
        """初始化模型信息

        Args:
            id: 模型唯一标识符
            name: 模型显示名称
            support_chat: 是否支持聊天，默认 True
            support_streaming: 是否支持流式，默认 True
            support_embedding: 是否支持嵌入，默认 False
            support_vision: 是否支持视觉，默认 False
            support_function_calling: 是否支持函数调用，默认 False
            context_length: 上下文窗口大小
            input_price_per_1m: 每百万 token 输入价格（元）
            output_price_per_1m: 每百万 token 输出价格（元）
            provider: 所属提供商名称
            **kwargs: 额外的模型参数
        """
        self.id = id
        self.name = name
        self.support_chat = support_chat
        self.support_streaming = support_streaming
        self.support_embedding = support_embedding
        self.support_vision = support_vision
        self.support_function_calling = support_function_calling
        self.context_length = context_length
        self.input_price_per_1m = input_price_per_1m
        self.output_price_per_1m = output_price_per_1m
        self.provider = provider
        self.extra = kwargs

    def to_dict(self) -> Dict[str, Any]:
        """将模型信息转换为字典

        Returns:
            Dict[str, Any]: 模型信息字典
        """
        result = {
            "id": self.id,
            "name": self.name,
            "support_chat": self.support_chat,
            "support_streaming": self.support_streaming,
            "support_embedding": self.support_embedding,
            "support_vision": self.support_vision,
            "support_function_calling": self.support_function_calling,
            "context_length": self.context_length,
            "input_price_per_1m": self.input_price_per_1m,
            "output_price_per_1m": self.output_price_per_1m,
            "provider": self.provider,
        }
        result.update(self.extra)
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelInfo":
        """从字典创建 ModelInfo

        将字典数据反序列化为 ModelInfo 对象。
        未知字段会被保存到 extra 属性中。

        Args:
            data: 包含模型信息的字典

        Returns:
            ModelInfo: 模型信息对象实例
        """
        # 已知的标准字段（含历史定价键 per_1k：旧缓存文件中该键的值
        # 实际已是 per_1m 语义，读取时原样采用、不做数值换算）
        known_fields = {
            "id", "name", "support_chat", "support_streaming",
            "support_embedding", "support_vision",
            "support_function_calling", "context_length",
            "input_price_per_1m", "output_price_per_1m",
            "input_price_per_1k", "output_price_per_1k", "provider"
        }
        # 将未知字段保存到 extra 中
        extra = {k: v for k, v in data.items() if k not in known_fields}
        # 定价键读取：优先 per_1m 新键；旧缓存的 per_1k 键原样回退（值本为 per_1m 语义）
        input_price = data.get("input_price_per_1m", data.get("input_price_per_1k"))
        output_price = data.get("output_price_per_1m", data.get("output_price_per_1k"))
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            support_chat=data.get("support_chat", True),
            support_streaming=data.get("support_streaming", True),
            support_embedding=data.get("support_embedding", False),
            support_vision=data.get("support_vision", False),
            support_function_calling=data.get("support_function_calling", False),
            context_length=data.get("context_length"),
            input_price_per_1m=input_price,
            output_price_per_1m=output_price,
            provider=data.get("provider", ""),
            **extra
        )


class ILLM(ABC):
    """LLM 提供商抽象基类

    定义 LLM 提供商必须实现的接口方法，包括：
    - 聊天补全（同步/异步）
    - 流式聊天补全（同步/异步）
    - 嵌入生成（同步/异步）
    - 模型列表获取（同步/异步）

    所有方法都有默认实现或抛出 NotImplementedError，
    子类只需实现实际支持的功能。

    Class Attributes:
        provider_type: 提供商类型标识（如 "glm", "minimax"）
        provider_name: 提供商显示名称
        support_chat: 是否支持聊天功能
        support_streaming: 是否支持流式输出
        support_embedding: 是否支持嵌入功能
        support_vision: 是否支持视觉（多模态）
    """

    # Provider 类型标识
    provider_type: str = ""
    provider_name: str = ""

    # 功能支持标志
    support_chat: bool = True
    support_streaming: bool = True
    support_embedding: bool = False
    support_vision: bool = False

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化 LLM 提供商

        Args:
            config: 提供商配置字典，包含 api_key、base_url 等
        """
        self.config = config or {}
        self._session = None
        self._async_session = None

    # ==================== 同步 API ====================

    @abstractmethod
    def chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（同步）

        向 LLM API 发送聊天请求，获取完整的响应文本。

        Args:
            messages: 消息列表，包含历史对话
            model: 模型名称（可选，默认使用配置中的模型）
            temperature: 温度参数，控制随机性，范围 0-2
            max_tokens: 最大生成 token 数（可选）
            **kwargs: 其他参数，如 top_p、stop 等

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            NotImplementedError: 如果提供商不支持聊天功能
        """
        pass

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[ChatResponse], None]] = None,
        **kwargs
    ) -> Union[AsyncIterator[ChatResponse], List[ChatResponse]]:
        """发送流式聊天请求（同步）

        向 LLM API 发送流式聊天请求，通过回调函数逐步获取响应。
        默认实现会抛出 NotImplementedError，子类可选择性实现。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            callback: 流式回调函数，每收到一个响应块调用一次
            **kwargs: 其他参数

        Returns:
            Union[AsyncIterator[ChatResponse], List[ChatResponse]]: 流式响应迭代器或响应列表

        Raises:
            NotImplementedError: 如果提供商不支持流式输出
        """
        raise NotImplementedError("Streaming not supported")

    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求（同步）

        将文本转换为向量嵌入。

        Args:
            texts: 单个文本或文本列表
            model: 嵌入模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表

        Raises:
            NotImplementedError: 如果提供商不支持嵌入功能
        """
        pass

    @abstractmethod
    def get_models(self) -> List[ModelInfo]:
        """获取可用模型列表（同步）

        查询 LLM API 获取当前提供商支持的模型列表。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        pass

    def validate_config(self) -> bool:
        """验证配置是否有效（仅格式校验，不代表连通性）

        检查提供商的必需配置项是否已填写。
        注意：本方法不发起任何网络请求，返回 True 仅表示配置格式完整，
        不代表 API 服务实际可用。

        Returns:
            bool: 配置是否有效（api_key 或 base_url 至少有一个）
        """
        return bool(self.config.get("api_key") or self.config.get("base_url"))

    # ==================== 异步 API ====================

    @abstractmethod
    async def async_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> ChatResponse:
        """发送聊天请求（异步）

        异步版本的聊天接口，适用于需要高并发的场景。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数

        Returns:
            ChatResponse: 聊天响应对象
        """
        pass

    async def async_stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> AsyncIterator[ChatResponse]:
        """发送流式聊天请求（异步）

        异步版本的流式聊天接口。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            **kwargs: 其他参数

        Yields:
            ChatResponse: 聊天响应块
        """
        raise NotImplementedError("Async streaming not supported")

    @abstractmethod
    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求（异步）

        异步版本的嵌入接口。

        Args:
            texts: 单个文本或文本列表
            model: 嵌入模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        pass

    @abstractmethod
    async def async_get_models(self) -> List[ModelInfo]:
        """获取可用模型列表（异步）

        异步版本的模型列表获取接口。

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        pass

    def refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """刷新模型列表（同步）

        从 API 重新获取模型列表，默认实现直接调用 get_models()。
        子类可重写此方法实现缓存逻辑。

        Args:
            force: 是否强制从 API 刷新（忽略缓存）

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return self.get_models()

    async def async_refresh_models(self, force: bool = False) -> List[ModelInfo]:
        """刷新模型列表（异步）

        异步版本的模型列表刷新接口。

        Args:
            force: 是否强制从 API 刷新

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        return await self.async_get_models()

    # ==================== 工具方法 ====================

    def _prepare_messages(
        self,
        messages: List[Union[Message, Dict]]
    ) -> List[Dict[str, Any]]:
        """准备消息格式

        将 Message 对象或字典格式的消息列表转换为统一的字典格式。
        用于确保发送给 API 的消息格式正确。

        Args:
            messages: 原始消息列表

        Returns:
            List[Dict[str, Any]]: 标准化后的消息列表

        Raises:
            ValueError: 如果消息类型不支持
        """
        result = []
        for msg in messages:
            if isinstance(msg, Message):
                result.append(msg.to_dict())
            elif isinstance(msg, dict):
                result.append(msg)
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")
        return result

    def close(self):
        """关闭同步连接

        关闭 HTTP 会话，释放网络资源。
        实现上下文管理器接口，支持 with 语句。
        """
        if self._session:
            self._session.close()
            self._session = None
        if self._async_session:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._async_session.close())
            except RuntimeError:
                # 无运行中的事件循环：新建临时循环完成关闭，避免 session 泄漏
                try:
                    asyncio.run(self._async_session.close())
                except Exception as e:
                    # session 原属事件循环已销毁，无法安全关闭，放弃以避免异常
                    logger.debug("异步 session 关闭失败（原事件循环已销毁，忽略）: %s", e)
            self._async_session = None
            if hasattr(self, "_async_session_loop"):
                self._async_session_loop = None

    async def async_close(self):
        """关闭异步连接

        异步关闭 HTTP 会话。
        """
        if self._async_session:
            await self._async_session.close()
            self._async_session = None

    def __enter__(self):
        """进入上下文管理器

        Returns:
            self: 当前实例
        """
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器

        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常追溯信息
        """
        self.close()
        return False

    async def __aenter__(self):
        """进入异步上下文管理器

        Returns:
            self: 当前实例
        """
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出异步上下文管理器

        Args:
            exc_type: 异常类型
            exc_val: 异常值
            exc_tb: 异常追溯信息
        """
        await self.async_close()
        return False