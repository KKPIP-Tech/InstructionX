"""
LLM Facade 接口

定义大语言模型统一访问的抽象接口。
插件通过此接口访问 LLM 能力，而非直接依赖 LLMProvider 实现。

此接口已扩展为包含对话管理、工具调用、多模态等完整能力。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union, Callable, Tuple, TYPE_CHECKING

# 复用现有的数据类型（仅类型检查时导入，避免接口层在运行时牵入 core.llm 重量依赖）
if TYPE_CHECKING:
    from core.llm.provider_interface import (
        Message, ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo
    )


# 延迟导出的 LLM 数据类型，保持 `from core.interfaces.i_llm_facade import Message` 可用
_LLM_TYPE_NAMES = {"Message", "ChatResponse", "EmbeddingResponse", "ModelInfo", "UsageInfo"}


def __getattr__(name: str) -> Any:
    if name in _LLM_TYPE_NAMES:
        from core.llm import provider_interface
        return getattr(provider_interface, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


class ILLMFacade(ABC):
    """
    LLM 统一门面接口

    定义大语言模型统一访问的抽象接口。
    插件通过此接口访问聊天、嵌入、模型列表、对话管理、工具调用等 LLM 能力。
    """

    # ==================== 底层 LLM 代理 ====================

    @abstractmethod
    def chat(
        self,
        messages: List[Union["Message", Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> "ChatResponse":
        """发送聊天请求（同步）"""
        pass

    @abstractmethod
    def stream_chat(
        self,
        messages: List[Union["Message", Dict]],
        provider: str = "default",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        callback: Optional[Callable[[str, bool], None]] = None,
        **kwargs
    ):
        """发送流式聊天请求（同步）"""
        pass

    @abstractmethod
    def embed(
        self,
        texts: Union[str, List[str]],
        provider: str = "default",
        model: Optional[str] = None,
        **kwargs
    ) -> List["EmbeddingResponse"]:
        """发送文本嵌入请求（同步）"""
        pass

    @abstractmethod
    def get_models(self, provider: Optional[str] = None) -> Dict[str, List["ModelInfo"]]:
        """获取可用模型列表"""
        pass

    @abstractmethod
    def get_provider(self, name: str) -> Optional[Any]:
        """获取指定名称的提供商实例"""
        pass

    @abstractmethod
    def get_all_providers(self) -> Dict[str, Any]:
        """获取所有已创建的提供商实例"""
        pass

    @abstractmethod
    def get_cached_models(self, provider_name: str) -> List["ModelInfo"]:
        """获取指定提供商的缓存模型列表"""
        pass

    # ==================== 对话管理 ====================

    @abstractmethod
    def create_conversation(
        self,
        system_prompt: Optional[str] = None,
        provider: str = "default",
        model: str = "default",
        metadata: Optional[Dict] = None,
    ) -> str:
        """创建一个新对话，返回对话 ID"""
        pass

    @abstractmethod
    def send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """同步发送消息，自动追加到对话历史"""
        pass

    @abstractmethod
    def stream_send_message(
        self,
        conversation_id: str,
        content: str,
        images: Optional[List[str]] = None,
        callback: Optional[Callable[[Any], None]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """流式发送消息"""
        pass

    @abstractmethod
    def get_conversation(self, conversation_id: str) -> Optional[Any]:
        """获取对话对象"""
        pass

    @abstractmethod
    def list_conversations(self) -> List[Any]:
        """列出所有对话"""
        pass

    @abstractmethod
    def delete_conversation(self, conversation_id: str) -> bool:
        """删除对话"""
        pass

    # ==================== 工具调用 ====================

    @abstractmethod
    def get_tool_executor(self) -> Any:
        """获取工具调用执行器"""
        pass

    @abstractmethod
    def get_shared_tool_registry(self) -> Any:
        """获取共享工具注册表"""
        pass

    @abstractmethod
    def chat_with_tools(
        self,
        messages: List[Dict],
        provider: str = "default",
        model: str = "default",
        max_turns: int = 5,
        temperature: Optional[float] = None,
    ) -> Tuple[List[Dict], List[Any], Any]:
        """带有工具调用的对话"""
        pass

    # ==================== 辅助方法 ====================

    @abstractmethod
    def get_available_providers(self) -> List[Any]:
        """获取所有可用的 Provider 信息"""
        pass

    @abstractmethod
    def get_usage_stats(self, conversation_id: Optional[str] = None) -> Any:
        """获取用量统计"""
        pass

    @abstractmethod
    def validate_provider(self, provider: str) -> Tuple[bool, str]:
        """验证 Provider 配置是否有效"""
        pass

    @abstractmethod
    def load_image_as_base64(self, file_path: str) -> str:
        """加载图片文件为 base64 字符串"""
        pass

    @abstractmethod
    def get_raw_provider(self, provider: str = "default") -> Any:
        """获取底层 LLM Provider（供高级插件使用）"""
        pass
