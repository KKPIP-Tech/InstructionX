"""LLM 插件服务层 — 第三方插件开发者主入口

这是插件开发者使用 LLM 能力的唯一入口（ILLMService 的唯一实现），整合了：
- 对话管理（历史、费用、上下文自动截断、会话持久化）
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
    result = executor.chat_with_tools(
        messages, max_turns=5
    )  # 返回 ToolChatResult（messages/tool_results/final_response/final_text）
"""

import copy
import logging
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from core.interfaces.i_llm_service import ILLMService

from .catalog import get_provider_preset
from .config import ProviderConfig, get_llm_config
from .conversation_manager import ConversationManager
from .exceptions import ConfigurationError
from .llm_provider import get_llm_provider
from .pricing import DEFAULT_PRICING
from .provider_interface import (
    ChatResponse, EmbeddingResponse, Message, ModelInfo,
)
from .tool_call_executor import (
    ToolCallExecutor, ToolRegistry, DEFAULT_MAX_TOOL_TURNS,
)
from .types import (
    DEFAULT_MODEL, DEFAULT_PROVIDER,
    AudioResult, Conversation, ImageResult, ProviderInfo,
    StreamChunk, ToolChatResult, UsageStats,
)

logger = logging.getLogger(__name__)

# 会话持久化默认路径：项目根目录/data/conversations.json
_DEFAULT_CONVERSATION_STORAGE = (
    Path(__file__).resolve().parent.parent.parent / "data" / "conversations.json"
)


class LLMPluginService(ILLMService):
    """插件开发者使用 LLM 的主接口（ILLMService 实现）

    双重身份：
    ① 对话管理器（ConversationManager）
    ② 底层 LLM 的代理（仅暴露契约能力，不泄漏适配器实例与原始配置）

    定价表随配置变更实时刷新：构造时订阅 LLMConfig 变更事件，
    实例增删 / custom_models 定价修改后自动重建注入 ConversationManager。

    单例访问方式：通过模块级工厂函数 get_llm_plugin_service() 获取
    全局唯一实例（模块级 _instance + 双重检查锁实现），请避免直接
    实例化本类。
    """

    def __init__(
        self,
        max_context: Optional[int] = None,
        pricing: Optional[Dict[str, Dict]] = None,
    ):
        """初始化插件服务

        Args:
            max_context: 最大上下文 token 数
            pricing: 定价表（覆盖默认定价 DEFAULT_PRICING）
        """
        self._llm = get_llm_provider()
        self._config = get_llm_config()
        # 基础定价表引用（每次重建时深拷贝，绝不污染全局 DEFAULT_PRICING）
        self._base_pricing = pricing if pricing is not None else DEFAULT_PRICING
        self._conversation_mgr = ConversationManager(
            max_context_tokens=max_context,
            pricing=self._build_effective_pricing(),
            storage_path=_DEFAULT_CONVERSATION_STORAGE,
        )
        self._tool_executor = ToolCallExecutor(self)
        self._shared_tool_registry = ToolRegistry()
        self._logger = logger
        # 订阅配置变更：实例增删 / 定价修改后重建定价表（消除构造期快照陈旧）
        self._config.subscribe(self._on_config_changed)

    # ==================== 定价表构建与配置变更联动 ====================

    def _build_effective_pricing(self) -> Dict[str, Dict]:
        """构建生效定价表

        以基础定价表的深拷贝为底，将各实例 custom_models 中的模型级
        定价注入对应实例的 models 定价表。

        Returns:
            Dict[str, Dict]: 生效定价表（深拷贝，不污染全局 DEFAULT_PRICING）
        """
        effective = copy.deepcopy(self._base_pricing)
        for name, cfg in self._config.get_all_providers().items():
            custom_models = cfg.extra.get("custom_models", [])
            if not custom_models:
                continue
            models_pricing = effective.setdefault(name, {}).setdefault("models", {})
            for entry in custom_models:
                if isinstance(entry, dict):
                    self._inject_model_pricing(models_pricing, entry)
        return effective

    @staticmethod
    def _inject_model_pricing(models_pricing: Dict[str, Dict], entry: Dict) -> None:
        """把单条 custom_models 条目的定价注入 models 定价表

        仅读取统一 schema 的 per_1m 定价键（单位 元/百万 tokens）；
        加载路径已经 normalize_model_entry 完成历史 per_1k 键迁移，
        无需 per_1k 回退。两个定价键均缺失时跳过该条目。

        Args:
            models_pricing: 目标 models 定价表（原地修改）
            entry: 规范化后的 custom_models 条目
        """
        model_id = entry.get("id")
        input_price = entry.get("input_price_per_1m")
        output_price = entry.get("output_price_per_1m")
        if not model_id or (input_price is None and output_price is None):
            return
        models_pricing[model_id] = {
            "input": input_price or 0,
            "output": output_price or 0,
        }

    def _on_config_changed(self, event: str, provider_name: Optional[str]) -> None:
        """LLMConfig 变更回调：重建定价表并热注入 ConversationManager

        Args:
            event: 变更事件名（EVENT_PROVIDERS_CHANGED）
            provider_name: 变更涉及的实例 id（批量变更时为 None）
        """
        self._conversation_mgr.update_pricing(self._build_effective_pricing())
        self._logger.debug(
            "LLM 配置变更（实例: %s），插件服务定价表已刷新", provider_name
        )

    # ==================== 对话管理 ====================

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
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """同步发送消息，自动追加到对话历史

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表
            temperature: 温度参数
            max_tokens: 最大 token 数
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            str: LLM 响应内容
        """
        content_text, _ = self._conversation_mgr.send_message(
            conversation_id=conversation_id,
            content=content,
            images=images,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            provider=provider,
        )
        return content_text

    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[[StreamChunk], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> str:
        """流式发送消息

        Args:
            conversation_id: 对话 ID
            content: 消息内容
            images: 图片 base64 列表
            callback: 流式回调，每收到一个 chunk 调用一次
            temperature: 温度参数
            max_tokens: 最大 token 数
            model: 临时覆盖本次调用的模型（不修改会话绑定）
            provider: 临时覆盖本次调用的实例 id（不修改会话绑定）

        Returns:
            str: 完整的 LLM 响应内容
        """
        content_text, _ = self._conversation_mgr.stream_send_message(
            conversation_id=conversation_id,
            content=content,
            images=images,
            callback=callback,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            provider=provider,
        )
        return content_text

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
        messages: List[Union[Message, Dict]],
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> ChatResponse:
        """直接发起 chat（无对话状态管理）

        Args:
            messages: 消息列表（Message 对象或字典）
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称，DEFAULT_MODEL 表示使用实例配置中的模型
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            ChatResponse: LLM 响应对象
        """
        msg_objs = [Message.from_dict(m) if isinstance(m, dict) else m for m in messages]
        # DEFAULT_PROVIDER 原样透传，由 LLMProvider 层解析；None 可选参数不下传
        call_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if tools is not None:
            call_kwargs["tools"] = tools
        return self._llm.chat(
            messages=msg_objs,
            provider=provider,
            model=model,
            **call_kwargs,
        )

    def stream_chat(
        self,
        messages: List[Union[Message, Dict]],
        callback: Callable[[str, bool], None],
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """流式 chat（无对话状态管理）

        Args:
            messages: 消息列表（Message 对象或字典）
            callback: 回调函数 (chunk: str, done: bool)
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称，DEFAULT_MODEL 表示使用实例配置中的模型
            temperature: 温度参数
            max_tokens: 最大 token 数
            tools: 工具定义列表

        Returns:
            str: 拼接后的完整响应文本
        """
        msg_objs = [Message.from_dict(m) if isinstance(m, dict) else m for m in messages]
        # DEFAULT_PROVIDER 原样透传，由 LLMProvider 层解析；None 可选参数不下传
        call_kwargs: Dict[str, Any] = {}
        if temperature is not None:
            call_kwargs["temperature"] = temperature
        if max_tokens is not None:
            call_kwargs["max_tokens"] = max_tokens
        if tools is not None:
            call_kwargs["tools"] = tools
        return self._llm.stream_chat(
            messages=msg_objs,
            callback=callback,
            provider=provider,
            model=model,
            **call_kwargs,
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
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
        max_turns: int = DEFAULT_MAX_TOOL_TURNS,
        temperature: Optional[float] = None,
    ) -> ToolChatResult:
        """带有工具调用的对话

        Args:
            messages: 消息列表
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称，DEFAULT_MODEL 表示使用实例配置中的模型
            max_turns: 最多工具调用轮数
            temperature: 温度参数

        Returns:
            ToolChatResult: 结构化结果（完整消息记录 / 工具结果 /
                最终响应 / 最终文本）
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
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
        max_turns: int = DEFAULT_MAX_TOOL_TURNS,
        temperature: Optional[float] = None,
    ) -> ToolChatResult:
        """流式版本的 chat_with_tools

        Returns:
            ToolChatResult: 结构化结果，final_text 为流式聚合全文
        """
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
        texts: Union[str, List[str]],
        provider: str = DEFAULT_PROVIDER,
        model: str = DEFAULT_MODEL,
    ) -> List[EmbeddingResponse]:
        """文本向量化

        Args:
            texts: 单个文本或文本列表
            provider: 实例 id，DEFAULT_PROVIDER 表示默认嵌入实例
            model: 模型名称，DEFAULT_MODEL 表示使用实例配置中的嵌入模型

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        # DEFAULT_PROVIDER 原样透传，由 LLMProvider 层解析
        return self._llm.embed(
            texts=texts,
            provider=provider,
            model=model,
        )

    # ==================== 多模态 ====================

    def generate_image(
        self,
        prompt: str,
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        size: str = "1024x1024",
        quality: str = "standard",
    ) -> ImageResult:
        """图像生成

        Args:
            prompt: 图像描述
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称
            size: 图像尺寸
            quality: 图像质量

        Returns:
            ImageResult: 生成的图像结果

        Raises:
            ConfigurationError: 实例不存在时抛出
            NotImplementedError: 实例不支持图像生成时抛出（错误信息
                会列出当前支持图像生成的实例）
        """
        resolved = self.resolve_provider_id(provider)
        p = self._llm.get_provider(resolved)
        if p is None:
            raise ConfigurationError(f"Provider not found: {resolved}")
        if not hasattr(p, 'generate_image'):
            supported = [n for n, inst in self._llm.get_all_providers().items()
                         if hasattr(inst, 'generate_image')]
            hint = (f"，当前支持图像生成的实例: {', '.join(supported)}"
                    if supported else "（当前没有任何实例支持图像生成）")
            raise NotImplementedError(
                f"实例 '{resolved}' 不支持图像生成{hint}"
            )
        result = p.generate_image(prompt=prompt, model=model,
                                   size=size, quality=quality)
        # 契约：provider 返回 types.ImageResult；兼容返回 dict 的旧实现
        if isinstance(result, ImageResult):
            if not result.provider:
                result.provider = resolved
            if not result.model:
                result.model = model or ""
            return result
        return ImageResult(
            url=result.get("url"),
            base64=result.get("b64_json"),
            revised_prompt=result.get("revised_prompt"),
            model=model or "",
            provider=resolved,
        )

    def text_to_speech(
        self,
        text: str,
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        voice: Optional[str] = None,
    ) -> AudioResult:
        """语音合成

        Args:
            text: 要合成的文本
            provider: 实例 id，DEFAULT_PROVIDER 表示默认实例
            model: 模型名称
            voice: 声音名称

        Returns:
            AudioResult: 语音合成结果

        Raises:
            ConfigurationError: 实例不存在时抛出
            NotImplementedError: 实例不支持语音合成时抛出（错误信息
                会列出当前支持 TTS 的实例）
        """
        resolved = self.resolve_provider_id(provider)
        p = self._llm.get_provider(resolved)
        if p is None:
            raise ConfigurationError(f"Provider not found: {resolved}")
        if not hasattr(p, 'text_to_speech'):
            supported = [n for n, inst in self._llm.get_all_providers().items()
                         if hasattr(inst, 'text_to_speech')]
            hint = (f"，当前支持语音合成的实例: {', '.join(supported)}"
                    if supported else "（当前没有任何实例支持语音合成）")
            raise NotImplementedError(
                f"实例 '{resolved}' 不支持语音合成{hint}"
            )
        result = p.text_to_speech(text=text, model=model, voice=voice)
        # 契约：provider 返回 types.AudioResult；兼容返回 dict 的旧实现
        if isinstance(result, AudioResult):
            if not result.provider:
                result.provider = resolved
            if not result.model:
                result.model = model or ""
            return result
        return AudioResult(
            audio_data=result.get("audio"),
            url=result.get("url"),
            duration_seconds=result.get("duration"),
            model=model or "",
            provider=resolved,
        )

    # ==================== 实例与模型查询 ====================

    def list_providers(self) -> List[ProviderInfo]:
        """列出所有 Provider 实例信息

        数据来源全部为真实配置与运行时状态：启用状态 / 适配器 / 预设
        关联 / 当前模型来自 ProviderConfig，base_url 取实例覆写或目录
        默认，健康状态来自 LLMProvider 的健康跟踪。

        Returns:
            List[ProviderInfo]: 实例信息列表（按配置的排序权重排序）
        """
        configs = self._config.get_all_providers()
        # 全量健康字典（LLMProvider.get_provider_health(None) 契约）
        health_map = self._llm.get_provider_health()
        ordered = sorted(configs.items(), key=lambda item: item[1].order)
        return [
            self._build_provider_info(instance_id, cfg, health_map)
            for instance_id, cfg in ordered
        ]

    def _build_provider_info(
        self,
        instance_id: str,
        cfg: ProviderConfig,
        health_map: Dict[str, Tuple[bool, Optional[str]]],
    ) -> ProviderInfo:
        """由真实配置与健康数据组装单个实例的 ProviderInfo

        Args:
            instance_id: 实例 id（配置键名）
            cfg: 该实例的 ProviderConfig
            health_map: 全量健康字典 {实例 id: (是否健康, 最近错误)}

        Returns:
            ProviderInfo: 实例信息（不含 api_key 等敏感字段）
        """
        base_url = cfg.base_url
        if not base_url and cfg.preset_id:
            preset = get_provider_preset(cfg.preset_id)
            base_url = preset.default_base_url if preset else ""
        # 适配器创建失败等原因不在健康字典中的实例按默认健康处理
        is_healthy, last_error = health_map.get(instance_id, (True, None))
        return ProviderInfo(
            instance_id=instance_id,
            preset_id=cfg.preset_id,
            name=cfg.name,
            adapter=cfg.adapter,
            base_url=base_url,
            enabled_chat=cfg.enabled_chat,
            enabled_embedding=cfg.enabled_embedding,
            is_healthy=is_healthy,
            last_error=last_error,
            current_chat_model=cfg.chat_model,
            current_embedding_model=cfg.embedding_model,
            models=self._llm.get_cached_models(instance_id),
        )

    def get_models(self, provider: str = DEFAULT_PROVIDER) -> List[ModelInfo]:
        """获取单个实例的模型列表

        Args:
            provider: 实例 id，DEFAULT_PROVIDER 解析为默认实例后取其模型列表

        Returns:
            List[ModelInfo]: 该实例的模型列表
        """
        resolved = self.resolve_provider_id(provider)
        return self._llm.get_cached_models(resolved)

    def resolve_provider_id(self, provider: str) -> str:
        """解析实例引用为实际实例 id

        Args:
            provider: 实例 id 或 DEFAULT_PROVIDER（默认实例引用）

        Returns:
            str: 实际实例 id（非默认引用时原样返回）

        Raises:
            ConfigurationError: DEFAULT_PROVIDER 且无可用实例时抛出
        """
        return self._llm.resolve_provider_name(provider, feature="chat")

    def get_default_provider_id(self, feature: str = "chat") -> Optional[str]:
        """获取默认实例解析结果（透传 LLMProvider，不抛异常）

        Args:
            feature: 功能类型，"chat" 或 "embedding"

        Returns:
            Optional[str]: 默认实例 id；无可用实例时为 None
        """
        return self._llm.get_default_provider_id(feature)

    # ==================== 统计与校验 ====================

    @property
    def last_stream_response(self) -> Optional[ChatResponse]:
        """最近一次流式请求的聚合响应（供工具调用执行器提取 tool_calls）

        Returns:
            Optional[ChatResponse]: 底层 LLMProvider 的聚合响应
        """
        return self._llm.last_stream_response

    def get_usage_stats(self, conversation_id: Optional[str] = None) -> Optional[UsageStats]:
        """获取用量统计

        Args:
            conversation_id: 对话 ID（可选，为 None 时返回全局统计）

        Returns:
            Optional[UsageStats]: 用量统计；指定的对话不存在时返回 None
        """
        return self._conversation_mgr.get_usage_stats(conversation_id)

    def validate_provider(self, provider: str) -> Tuple[bool, str]:
        """验证指定实例的配置是否有效

        Args:
            provider: 实例 id

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
