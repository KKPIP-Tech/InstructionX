"""LLM 插件服务接口

定义插件访问 LLM 能力的唯一抽象契约。
插件通过此接口访问聊天、嵌入、会话管理、工具调用、多模态等能力，
而非直接依赖 LLMProvider / 适配器实例等底层实现。

实现：core.llm.plugin_service.LLMPluginService（显式继承本接口）。

签名默认值说明：接口层在运行时不导入 core.llm（避免循环依赖），
因此 provider/model 维度的默认值以字面量 "default" 标注，语义等同
core.llm.types.DEFAULT_PROVIDER / DEFAULT_MODEL；max_turns 默认值 5
等同 core.llm.tool_call_executor.DEFAULT_MAX_TOOL_TURNS。
"""

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, TYPE_CHECKING

# 复用 core.llm 的数据类型（仅类型检查时导入，避免接口层在运行时牵入 core.llm 重量依赖）
if TYPE_CHECKING:
    from core.llm.provider_interface import (
        ChatResponse, EmbeddingResponse, Message, ModelInfo,
    )
    from core.llm.tool_call_executor import ToolCallExecutor, ToolRegistry
    from core.llm.types import (
        AudioResult, Conversation, ImageResult, ProviderInfo,
        StreamChunk, ToolChatResult, UsageStats,
    )


class ILLMService(ABC):
    """LLM 插件服务抽象接口

    插件访问 LLM 能力的唯一契约。所有 provider 参数语义为**实例 id**，
    取 "default"（DEFAULT_PROVIDER）时由底层按功能维度解析为默认实例；
    model 参数取 "default"（DEFAULT_MODEL）时使用实例配置中的默认模型。
    """

    # ==================== 直接对话（无会话状态） ====================

    @abstractmethod
    def chat(
        self,
        messages: List[Union["Message", Dict]],
        provider: str = "default",
        model: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> "ChatResponse":
        """直接发起聊天请求（无会话状态管理）

        Args:
            messages: 消息列表（Message 对象或字典，字典经 Message.from_dict 宽松解析）
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称，"default" 表示使用实例配置中的模型
            temperature: 温度参数（None 表示不指定）
            max_tokens: 最大生成 token 数（None 表示不指定）
            tools: 工具定义列表（可选）

        Returns:
            ChatResponse: 聊天响应对象

        Raises:
            ConfigurationError: 没有可用的提供商实例时抛出
        """

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Union["Message", Dict]],
        callback: Callable[[str, bool], None],
        provider: str = "default",
        model: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """流式聊天请求（无会话状态管理）

        Args:
            messages: 消息列表（Message 对象或字典）
            callback: 流式回调 (chunk_text: str, done: bool)，每块调用一次
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称，"default" 表示使用实例配置中的模型
            temperature: 温度参数（None 表示不指定）
            max_tokens: 最大生成 token 数（None 表示不指定）
            tools: 工具定义列表（可选）

        Returns:
            str: 拼接后的完整响应文本（注意：返回值是完整文本而非生成器）

        Raises:
            ConfigurationError: 没有可用的提供商实例时抛出
        """

    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        provider: str = "default",
        model: str = "default",
    ) -> List["EmbeddingResponse"]:
        """文本向量化

        Args:
            texts: 单个文本或文本列表
            provider: 实例 id，"default" 表示默认嵌入实例
            model: 模型名称，"default" 表示使用实例配置中的嵌入模型

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表（向量在各项的 embedding 字段）

        Raises:
            ConfigurationError: 没有可用的嵌入提供商实例时抛出
        """

    # ==================== 会话管理 ====================

    @abstractmethod
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
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称，"default" 表示使用实例配置中的模型
            metadata: 额外元数据

        Returns:
            str: 对话 ID
        """

    @abstractmethod
    def send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """同步发送消息，调用成功后自动追加到对话历史

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            temperature: 温度参数（None 表示不指定）
            max_tokens: 最大 token 数（None 表示不指定）
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            str: LLM 响应内容文本（会话对象经 get_conversation() 获取）

        Raises:
            ValueError: 对话不存在时抛出
        """

    @abstractmethod
    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[["StreamChunk"], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """流式发送消息，逐 chunk 通过 callback 回调

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表（可选）
            callback: 流式回调，每收到一个 StreamChunk 调用一次
            temperature: 温度参数（None 表示不指定）
            max_tokens: 最大 token 数（None 表示不指定）
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            str: 完整的 LLM 响应内容文本

        Raises:
            ValueError: 对话不存在时抛出
        """

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Optional["Conversation"]:
        """获取对话对象

        Args:
            conversation_id: 对话 ID

        Returns:
            Optional[Conversation]: 对话对象，不存在时返回 None
        """

    @abstractmethod
    def list_conversations(self) -> List["Conversation"]:
        """列出所有对话

        Returns:
            List[Conversation]: 对话列表
        """

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话（同步从持久化中删除）

        Args:
            conversation_id: 对话 ID

        Returns:
            bool: 是否成功删除
        """

    # ==================== 工具调用 ====================

    @abstractmethod
    def get_tool_executor(self) -> "ToolCallExecutor":
        """获取工具调用执行器

        Returns:
            ToolCallExecutor: 工具调用执行器（多轮工具调用循环）
        """

    @abstractmethod
    def get_shared_tool_registry(self) -> "ToolRegistry":
        """获取共享工具注册表

        Returns:
            ToolRegistry: 共享工具注册表（MCP 工具亦注册于此）
        """

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Dict],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> "ToolChatResult":
        """带有工具调用的对话（自动多轮循环）

        Args:
            messages: 消息列表
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称，"default" 表示使用实例配置中的模型
            max_turns: 最多工具调用轮数
            temperature: 温度参数（None 表示不指定）

        Returns:
            ToolChatResult: 结构化结果（messages / tool_results /
                final_response / final_text），字段类型固定
        """

    @abstractmethod
    def chat_with_tools_stream(
        self,
        messages: List[Dict],
        callback: Callable[["StreamChunk"], None],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> "ToolChatResult":
        """流式版本的 chat_with_tools

        Args:
            messages: 消息列表
            callback: 流式回调（接收 StreamChunk）
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称，"default" 表示使用实例配置中的模型
            max_turns: 最多工具调用轮数
            temperature: 温度参数（None 表示不指定）

        Returns:
            ToolChatResult: 结构化结果，final_text 为流式聚合全文
        """

    # ==================== 多模态 ====================

    @abstractmethod
    def generate_image(
        self,
        prompt: str,
        provider: str = "default",
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> "ImageResult":
        """图像生成

        Args:
            prompt: 图像描述
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称（None 表示使用实例默认）
            size: 图像尺寸
            quality: 图像质量

        Returns:
            ImageResult: 生成的图像结果

        Raises:
            ConfigurationError: 实例不存在时抛出
            NotImplementedError: 实例不支持图像生成时抛出
        """

    @abstractmethod
    def text_to_speech(
        self,
        text: str,
        provider: str = "default",
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> "AudioResult":
        """语音合成

        Args:
            text: 要合成的文本
            provider: 实例 id，"default" 表示默认实例
            model: 模型名称（None 表示使用实例默认）
            voice: 声音名称（None 表示使用实例默认）

        Returns:
            AudioResult: 语音合成结果

        Raises:
            ConfigurationError: 实例不存在时抛出
            NotImplementedError: 实例不支持语音合成时抛出
        """

    # ==================== 实例与模型查询 ====================

    @abstractmethod
    def list_providers(self) -> List["ProviderInfo"]:
        """列出所有 Provider 实例信息

        Returns:
            List[ProviderInfo]: 实例信息列表（按配置的排序权重排序），
                字段均来自真实配置与运行时健康状态，不含 api_key
        """

    @abstractmethod
    def get_models(self, provider: str = "default") -> List["ModelInfo"]:
        """获取单个实例的模型列表

        Args:
            provider: 实例 id，"default" 解析为默认实例后取其模型列表

        Returns:
            List[ModelInfo]: 该实例的模型列表；实例无缓存模型时为空列表

        Raises:
            ConfigurationError: provider 为 "default" 且无可用实例时抛出
        """

    @abstractmethod
    def resolve_provider_id(self, provider: str) -> str:
        """解析实例引用为实际实例 id

        Args:
            provider: 实例 id 或 "default"（默认实例引用）

        Returns:
            str: 实际实例 id（非默认引用时原样返回）

        Raises:
            ConfigurationError: "default" 且无可用实例时抛出
        """

    @abstractmethod
    def get_default_provider_id(self, feature: str = "chat") -> Optional[str]:
        """获取默认实例解析结果（不抛异常）

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            Optional[str]: 默认实例 id；无可用实例时为 None
        """

    # ==================== 统计与校验 ====================

    @abstractmethod
    def get_usage_stats(
        self,
        conversation_id: Optional[str] = None,
    ) -> Optional["UsageStats"]:
        """获取用量统计

        Args:
            conversation_id: 对话 ID（None 时返回全局统计）

        Returns:
            Optional[UsageStats]: 用量统计；指定的对话不存在时返回 None
        """

    @abstractmethod
    def validate_provider(self, provider: str) -> Tuple[bool, str]:
        """验证指定实例的配置是否有效

        Args:
            provider: 实例 id

        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """

    @property
    @abstractmethod
    def last_stream_response(self) -> Optional["ChatResponse"]:
        """最近一次流式请求的聚合响应（供工具调用执行器提取 tool_calls）

        Returns:
            Optional[ChatResponse]: 聚合响应对象，尚无流式请求时为 None
        """
