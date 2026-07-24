"""MiniMax Provider 实现模块

该模块提供 MiniMax 大语言模型的接口实现。
继承自 BaseProvider，聊天、嵌入、流式输出等通用逻辑复用基类模板方法，
本模块仅保留预设模型列表、模型列表解析与 Vision 降级处理。

MiniMax API 文档: https://platform.minimaxi.com/docs/api-reference

支持的模型:
    - CHAT_MODELS: 文本聊天模型（MiniMax-M2.5, MiniMax-M2.1 等）
    - EMBEDDING_MODELS: 向量嵌入模型（embedding-2）

Classes:
    MiniMaxProvider: MiniMax 提供商实现

使用示例:
    >>> from core.llm.providers.minimax import MiniMaxProvider
    >>> config = {"api_key": "xxx", "base_url": "https://api.minimax.chat/v1"}
    >>> provider = MiniMaxProvider(config, provider_name="minimax")
    >>> response = provider.chat([Message("user", "你好")])
"""

import logging
from typing import Dict, Any, Optional, List

from .base import BaseProvider
from ..provider_interface import ModelInfo

logger = logging.getLogger(__name__)


class MiniMaxProvider(BaseProvider):
    """MiniMax LLM Provider

    MiniMax 大语言模型提供商实现，支持文本聊天、嵌入生成等功能。
    由于 MiniMax 官方没有提供模型列表 API，使用预设模型列表。
    聊天/嵌入/流式响应解析直接使用基类的 OpenAI 兼容实现
    （含 tool_calls 解析）。

    Class Attributes:
        provider_type: 提供商类型标识 ("minimax")
        provider_name: 提供商显示名称 ("MiniMax")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (False - 当前不支持图像和音频输入)
        CHAT_MODELS: 文本聊天模型列表
        EMBEDDING_MODELS: 向量嵌入模型列表
        MODEL_DETAILS: 预设模型详细信息

    API 端点:
        - /text/chatcompletion_v2: 聊天完成
        - /embeddings/embedding-async_v2: 嵌入生成

    使用示例:
        >>> from core.llm.providers.minimax import MiniMaxProvider
        >>> from core.llm import Message
        >>> config = {"api_key": "your_api_key", "chat_model": "MiniMax-M2.5"}
        >>> provider = MiniMaxProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "minimax"
    provider_name = "MiniMax"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    # MiniMax 不支持 Vision（官方文档明确说明"当前不支持图像和音频类型的输入"）
    support_vision = False

    # ==================== 预设模型列表 ====================

    # MiniMax 官方没有提供模型列表 API，使用预设列表
    # 参考: https://platform.minimaxi.com/docs/api-reference/api-overview
    CHAT_MODELS = [
        "MiniMax-M2.7",
        "MiniMax-M2.7-highspeed",
        "MiniMax-M2.5",
        "MiniMax-M2.5-highspeed",
        "MiniMax-M2.1",
        "MiniMax-M2.1-highspeed",
        "MiniMax-M2",
    ]

    EMBEDDING_MODELS = [
        "embedding-2",
    ]

    # 预设模型详情（从官方文档获取）
    MODEL_DETAILS = {
        "MiniMax-M2.7": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "MiniMax 旗舰大模型，全面升级推理与多模态能力"
        },
        "MiniMax-M2.7-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.7 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2.5": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "顶尖性能与极致性价比，轻松驾驭复杂任务"
        },
        "MiniMax-M2.5-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.5 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2.1": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "强大多语言编程能力，全面升级编程体验"
        },
        "MiniMax-M2.1-highspeed": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "M2.1 极速版：效果不变，更快，更敏捷"
        },
        "MiniMax-M2": {
            "context_length": 204800,
            "support_function_calling": True,
            "description": "专为高效编码与Agent工作流而生"
        },
        "embedding-2": {
            "context_length": None,
            "support_function_calling": False,
            "description": "Embedding 模型"
        },
    }

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 MiniMax Provider

        Args:
            config: 提供商配置字典
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        # API 端点定义
        self._chat_endpoint = "/text/chatcompletion_v2"
        self._embedding_endpoint = "/embeddings/embedding-async_v2"
        # MiniMax 没有模型列表 API，使用预设列表

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 MiniMax API 返回的模型列表

        从 MiniMax API 响应中提取模型信息，并根据模型类型判断支持的功能。

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []

        for model_data in response.get("data", []):
            model_id = model_data.get("model_id", "")
            model_type = model_data.get("model_type", "")

            # 根据模型类型判断支持的功能
            if model_type in ["chat", "text"]:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=True
                ))
            elif model_type == "embedding":
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False
                ))

        return models

    # ==================== Vision 降级处理 ====================

    def _prepare_vision_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """处理多模态消息（MiniMax 不支持图片输入）

        MiniMax 官方文档明确"当前不支持图像和音频类型的输入"，
        遇到带图片的消息时记录 warning 并忽略图片，仅保留文本内容。

        Args:
            messages: 消息列表

        Returns:
            List[Dict[str, Any]]: 处理后的消息列表
        """
        result = []
        warned = False
        for msg in messages:
            if msg.get("images"):
                if not warned:
                    logger.warning(
                        "[minimax] 当前不支持图像输入，已忽略消息中的 %d 张图片",
                        len(msg["images"]),
                    )
                    warned = True
                msg = {k: v for k, v in msg.items() if k != "images"}
            result.append(msg)
        return result

    # 聊天/嵌入/流式/异步接口均使用基类模板方法默认实现
    # （OpenAI 兼容格式，含 tool_calls 解析）
