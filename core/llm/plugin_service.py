"""LLM 插件服务层 — 第三方插件开发者主入口

这是插件开发者使用 LLM 能力的唯一入口，整合了：
- 对话管理（历史、自动截断、费用）
- 工具调用自动化
- 向量嵌入
- 多模态（图像生成、语音合成）
- 用量统计

使用示例:
    from core.llm import get_llm_plugin_service

    svc = get_llm_plugin_service()

    # 1. 创建对话
    conv_id = svc.create_conversation(
        system_prompt="你是一个代码助手"
    )
    svc.send_message(conv_id, "解释这段代码")

    # 2. 流式对话
    svc.stream_send_message(
        conv_id, "写一个快排",
        callback=lambda c: print(c.content, end="")
    )

    # 3. 直接 chat（无对话状态）
    resp = svc.chat([{"role": "user", "content": "hello"}])

    # 4. 工具调用
    executor = svc.get_tool_executor()
    executor.tools.register("search", "搜索网络", {...}, handler=my_search)
    msgs, results, final = executor.chat_with_tools(
        messages, max_turns=5
    )  # 工具从已注册的注册表中自动获取
"""

import base64
import threading
import logging
import mimetypes
from typing import Any, Callable, Dict, List, Optional, Tuple

from .conversation_manager import ConversationManager
from .tool_call_executor import ToolCallExecutor, ToolRegistry
from .types import (
    Conversation, StreamChunk, ToolResult, UsageStats,
    ImageResult, AudioResult, ProviderInfo
)
from .provider_interface import Message
from .llm_provider import get_llm_provider
from .config import LLMConfig
from .pricing import DEFAULT_PRICING

logger = logging.getLogger(__name__)


class LLMPluginService:
    """
    插件开发者使用 LLM 的主接口

    双重身份：
    ① 对话管理器（ConversationManager）
    ② 底层 LLM 的代理
    """

    _instance: Optional["LLMPluginService"] = None
    _instance_lock = threading.Lock()

    def __init__(
        self,
        max_context: Optional[int] = None,
        pricing: Optional[Dict[str, Dict]] = None,
    ):
        """初始化插件服务

        Args:
            max_context: 最大上下文 token 数
            pricing: 定价表（覆盖默认定价）
        """
        self._llm = get_llm_provider()
        self._config = LLMConfig()
        # 构建定价表，将 custom_models 中的模型级别定价同步注入
        effective_pricing = (pricing or DEFAULT_PRICING).copy()
        for name, cfg in self._config.get_all_providers().items():
            custom_models = cfg.extra.get("custom_models", []) if hasattr(cfg, "extra") else []
            if not custom_models:
                continue
            if name not in effective_pricing:
                effective_pricing[name] = {}
            if "models" not in effective_pricing[name]:
                effective_pricing[name]["models"] = {}
            for m in custom_models:
                model_id = m.get("id")
                if not model_id:
                    continue
                input_price = m.get("input_price_per_1k", 0)
                output_price = m.get("output_price_per_1k", 0)
                if input_price or output_price:
                    effective_pricing[name]["models"][model_id] = {
                        "input_per_1k": input_price,
                        "output_per_1k": output_price,
                    }
        self._conversation_mgr = ConversationManager(
            max_context=max_context,
            pricing=effective_pricing,
        )
        self._tool_executor = ToolCallExecutor(self)
        self._shared_tool_registry = ToolRegistry()
        self._logger = logger

    # ==================== 对话管理 ====================

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
            str: 对话 ID
        """
        return self._conversation_mgr.create_conversation(
            system_prompt=system_prompt,
            provider=provider,
            model=model,
            metadata=metadata,
        )

    def send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """同步发送消息，自动追加到对话历史

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            str: LLM 响应内容
        """
        content, _ = self._conversation_mgr.send_message(
            conversation_id=conversation_id,
            content=content,
            images=images,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content

    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[[StreamChunk], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """流式发送消息

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表
            callback: 流式回调，每收到一个 chunk 调用一次
            temperature: 温度参数
            max_tokens: 最大 token 数

        Returns:
            str: 完整的 LLM 响应内容
        """
        content, _ = self._conversation_mgr.stream_send_message(
            conversation_id=conversation_id,
            content=content,
            images=images,
            callback=callback,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return content

    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """获取对话对象

        Returns:
            Optional[Conversation]: 对话对象
        """
        return self._conversation_mgr.get_conversation(conversation_id)

    def list_conversations(self) -> List[Conversation]:
        """列出所有对话"""
        return self._conversation_mgr.list_conversations()

    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话"""
        return self._conversation_mgr.delete_conversation(conversation_id)

    # ==================== 直接 chat（无对话状态）====================

    def chat(
        self,
        messages: List[Dict],
        provider: str = "default",
        model: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> Any:
        """直接发起 chat（无对话状态管理）

        Args:
            messages: 消息列表
            provider: Provider 名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            ChatResponse: LLM 响应对象
        """
        msg_objs = [Message(**m) if isinstance(m, dict) else m for m in messages]
        return self._llm.chat(
            messages=msg_objs,
            provider=provider if provider != "default" else None,
            model=model if model != "default" else None,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    def stream_chat(
        self,
        messages: List[Dict],
        callback: Callable[[str, bool], None],
        provider: str = "default",
        model: str = "default",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ):
        """流式 chat（无对话状态管理）

        Args:
            messages: 消息列表
            callback: 回调函数 (chunk: str, done: bool)
            provider: Provider 名称
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表
        """
        msg_objs = [Message(**m) if isinstance(m, dict) else m for m in messages]
        self._llm.stream_chat(
            messages=msg_objs,
            callback=callback,
            provider=provider if provider != "default" else None,
            model=model if model != "default" else None,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )

    # ==================== 工具调用 ====================

    def get_tool_executor(self) -> ToolCallExecutor:
        """获取工具调用执行器"""
        return self._tool_executor

    def get_shared_tool_registry(self) -> ToolRegistry:
        """获取共享工具注册表"""
        return self._shared_tool_registry

    def chat_with_tools(
        self,
        messages: List[Dict],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> Tuple[List[Dict], List[ToolResult], Any]:
        """带有工具调用的对话

        Args:
            messages: 消息列表
            provider: Provider 名称
            model: 模型名称
            max_turns: 最多工具调用轮数
            temperature: 温度参数

        Returns:
            Tuple[List[Dict], List[ToolResult], Any]:
                (最终消息列表, 工具结果列表, 最终响应)
        """
        return self._tool_executor.chat_with_tools(
            messages=messages,
            provider=provider,
            model=model,
            max_turns=max_turns,
            temperature=temperature,
        )

    def chat_with_tools_stream(
        self,
        messages: List[Dict],
        callback: Callable[[StreamChunk], None],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> Tuple[List[Dict], List[ToolResult], str]:
        """流式版本的 chat_with_tools"""
        def _sc(chunk: str, done: bool):
            callback(StreamChunk(content=chunk, done=done))
        return self._tool_executor.chat_with_tools(
            messages=messages,
            provider=provider,
            model=model,
            max_turns=max_turns,
            temperature=temperature,
            stream=True,
            stream_callback=_sc,
        )

    # ==================== 向量嵌入 ====================

    def embed(
        self,
        texts: str | List[str],
        provider: str = "default",
        model: str = "default",
    ) -> List[List[float]]:
        """文本向量化

        Args:
            texts: 单个文本或文本列表
            provider: Provider 名称
            model: 模型名称

        Returns:
            List[List[float]]: 嵌入向量列表
        """
        return self._llm.embed(
            texts=texts,
            provider=provider if provider != "default" else None,
            model=model if model != "default" else None,
        )

    # ==================== 多模态 ====================

    def generate_image(
        self,
        prompt: str,
        provider: str = "default",
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> ImageResult:
        """图像生成

        Args:
            prompt: 图像描述
            provider: Provider 名称
            model: 模型名称
            size: 图像尺寸
            quality: 图像质量

        Returns:
            ImageResult: 生成的图像结果
        """
        p = self._llm.get_provider(provider)
        if not hasattr(p, 'generate_image'):
            raise NotImplementedError(
                f"Provider {provider} does not support image generation"
            )
        result = p.generate_image(prompt=prompt, model=model,
                                   size=size, quality=quality)
        return ImageResult(
            url=result.get("url"),
            base64=result.get("b64_json"),
            revised_prompt=result.get("revised_prompt"),
            model=model or "",
            provider=provider,
        )

    def text_to_speech(
        self,
        text: str,
        provider: str = "default",
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> AudioResult:
        """语音合成

        Args:
            text: 要合成的文本
            provider: Provider 名称
            model: 模型名称
            voice: 声音名称

        Returns:
            AudioResult: 语音合成结果
        """
        p = self._llm.get_provider(provider)
        if not hasattr(p, 'text_to_speech'):
            raise NotImplementedError(
                f"Provider {provider} does not support TTS"
            )
        result = p.text_to_speech(text=text, model=model, voice=voice)
        return AudioResult(
            audio_data=result.get("audio"),
            url=result.get("url"),
            duration_seconds=result.get("duration"),
            model=model or "",
            provider=provider,
        )

    # ==================== 辅助方法 ====================

    def load_image_as_base64(self, file_path: str) -> str:
        """加载图片文件为 base64 字符串

        Args:
            file_path: 图片文件路径

        Returns:
            str: base64 编码字符串（不含 data URI 前缀）
        """
        with open(file_path, "rb") as f:
            data = f.read()
        return base64.b64encode(data).decode("utf-8")

    def get_available_providers(self) -> List[ProviderInfo]:
        """获取所有可用的 Provider 信息

        Returns:
            List[ProviderInfo]: Provider 信息列表
        """
        result = []
        for name, p in self._llm.get_all_providers().items():
            models = self._llm.get_cached_models(name)
            result.append(ProviderInfo(
                name=name,
                provider_type=getattr(p, "PROVIDER_TYPE", name),
                enabled_chat=getattr(p, "enabled_chat", True),
                enabled_embedding=getattr(p, "enabled_embedding", True),
                supports_vision=getattr(p, "supports_vision", False),
                supports_function_calling=any(
                    getattr(m, "support_function_calling", False)
                    for m in models
                ),
                current_chat_model=getattr(p, "chat_model", ""),
                current_embedding_model=getattr(p, "embedding_model", ""),
                models=models,
                is_healthy=True,
            ))
        return result

    def get_usage_stats(self, conversation_id: Optional[str] = None) -> UsageStats:
        """获取用量统计

        Args:
            conversation_id: 对话 ID（可选，为 None 时返回全局统计）

        Returns:
            UsageStats: 用量统计
        """
        return self._conversation_mgr.get_usage_stats(conversation_id)

    def validate_provider(self, provider: str) -> Tuple[bool, str]:
        """验证 Provider 配置是否有效

        Args:
            provider: Provider 名称

        Returns:
            Tuple[bool, str]: (是否有效, 错误信息)
        """
        try:
            p = self._llm.get_provider(provider)
            if not p:
                return False, f"Provider '{provider}' not found"
            return p.validate_config(), ""
        except Exception as e:
            return False, str(e)

    def get_raw_provider(self, provider: str = "default"):
        """获取底层 LLM Provider（供高级插件使用）

        Args:
            provider: Provider 名称

        Returns:
            ILLM: 底层 Provider 实例
        """
        return self._llm.get_provider(
            provider if provider != "default" else None
        )


# ==================== 全局单例工厂函数 ====================

_instance: Optional["LLMPluginService"] = None
_instance_lock = threading.Lock()


def get_llm_plugin_service() -> "LLMPluginService":
    """获取 LLMPluginService 全局单例

    Returns:
        LLMPluginService: 插件服务实例
    """
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LLMPluginService()
    return _instance
