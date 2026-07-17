"""SiliconFlow Provider 实现模块

该模块提供 SiliconFlow API 的接口实现。
继承自 BaseProvider，聊天、嵌入、流式输出等通用逻辑复用基类模板方法，
本模块仅保留模型能力推断、模型列表解析与图像生成实现。

SiliconFlow API 文档: https://docs.siliconflow.cn/cn/api-reference/models/get-model-list

支持的模型类型:
    - 聊天模型：支持多种开源大模型（如 Qwen、DeepSeek 等）
    - 嵌入模型：支持 bge 系列等
    - 视觉模型：支持 vision、vl、4v 等
    - 重排序模型：支持 rerank

Classes:
    SiliconFlowProvider: SiliconFlow 提供商实现

使用示例:
    >>> from core.llm.providers.siliconflow import SiliconFlowProvider
    >>> config = {"api_key": "xxx", "base_url": "https://api.siliconflow.cn/v1"}
    >>> provider = SiliconFlowProvider(config, provider_name="siliconflow")
    >>> response = provider.chat([Message("user", "你好")])
"""

from typing import Dict, Any, Optional, List

from .base import BaseProvider, _keyword_in_model
from ..provider_interface import ModelInfo
from ..exceptions import ConfigurationError
from ..types import ImageResult


class SiliconFlowProvider(BaseProvider):
    """SiliconFlow LLM Provider

    SiliconFlow 大语言模型提供商实现，通过统一的 API 接口访问多种开源模型。
    支持从 API 动态获取模型列表。
    聊天/嵌入/流式响应解析直接使用基类的 OpenAI 兼容实现
    （含 tool_calls 解析与 Vision 消息转换）。

    Class Attributes:
        provider_type: 提供商类型标识 ("siliconflow")
        provider_name: 提供商显示名称 ("SiliconFlow")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (True)

    API 端点:
        - /chat/completions: 聊天完成
        - /embeddings: 嵌入生成
        - /models: 模型列表
        - /images/generations: 图像生成

    使用示例:
        >>> from core.llm.providers.siliconflow import SiliconFlowProvider
        >>> from core.llm import Message
        >>> config = {"api_key": "your_api_key", "chat_model": "Pro/deepseek-ai/DeepSeek-V3"}
        >>> provider = SiliconFlowProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "siliconflow"
    provider_name = "SiliconFlow"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    # 图像生成默认模型（可被配置 image_model 覆盖）
    DEFAULT_IMAGE_MODEL = "Kwai-Kolors/Kolors"

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 SiliconFlow Provider

        Args:
            config: 提供商配置字典
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        # API 端点定义
        self._chat_endpoint = "/chat/completions"
        self._embedding_endpoint = "/embeddings"
        self._models_endpoint = "/models"
        self._image_endpoint = "/images/generations"

    # ==================== 模型能力推断 ====================

    # 关键词按非字母数字边界匹配，避免 "fc"/"vl" 之类的子串误判
    VISION_KEYWORDS = ["vision", "vl", "4v", "qwen2-vl", "cogview", "llava", "internvl"]
    FC_KEYWORDS = ["function", "fc", "tool", "deepseek"]
    RERANK_KEYWORDS = ["rerank"]

    def _infer_capabilities(self, model_id: str) -> Dict[str, Any]:
        """从模型 ID 推断模型能力

        根据模型 ID 中的关键词判断视觉、函数调用等能力。

        Args:
            model_id: 模型 ID

        Returns:
            Dict[str, Any]: 能力字典
        """
        mid = model_id.lower()
        return {
            "support_vision": any(_keyword_in_model(mid, k) for k in self.VISION_KEYWORDS),
            "support_function_calling": any(_keyword_in_model(mid, k) for k in self.FC_KEYWORDS),
            "context_length": self._estimate_context_length(model_id),
        }

    def _estimate_context_length(self, model_id: str) -> Optional[int]:
        """根据模型名称估算上下文窗口大小

        Args:
            model_id: 模型 ID

        Returns:
            Optional[int]: 估算的上下文长度，不知道则返回 None
        """
        KNOWN_CONTEXTS = {
            "deepseek-v3": 64000,
            "deepseek-chat": 64000,
            "qwen3": 32000,
            "qwen-turbo": 8000,
            "qwen-plus": 32000,
            "qwen2.5-72b": 32000,
            "qwen2.5-32b": 32000,
            "qwen2.5-14b": 32000,
            "qwen2.5-7b": 8000,
            "glm-4": 128000,
            "kimi": 128000,
            "moonshot": 128000,
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "claude-3": 200000,
            "claude-3.5": 200000,
            "yi-light": 16000,
            "yi-spark": 32000,
            "yi-large": 32000,
            "llama-3.1-70b": 128000,
            "llama-3.1-8b": 128000,
            "llama-3-70b": 8000,
            "llama-3-8b": 8000,
        }
        mid = model_id.lower()
        for name, ctx in KNOWN_CONTEXTS.items():
            if name in mid:
                return ctx
        return None

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 SiliconFlow API 返回的模型列表

        从 SiliconFlow API 响应中提取模型信息，并根据模型 ID 判断模型类型和上下文长度。

        模型类型判断规则:
            - 嵌入模型：模型 ID 包含 "embedding" 或 "bge-"
            - 视觉模型：模型 ID 包含 "vision", "vl", "4v", "cogview", "qwen2-vl"
            - 重排序模型：模型 ID 包含 "rerank"

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []

        for model_data in response.get("data", []):
            model_id = model_data.get("id", "")

            if not model_id:
                continue

            # 推断能力
            caps = self._infer_capabilities(model_id)

            # 根据模型 ID 判断类型
            is_embedding = "embedding" in model_id.lower() or "bge-" in model_id.lower()
            is_rerank = any(_keyword_in_model(model_id, x) for x in self.RERANK_KEYWORDS)

            if is_embedding:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False,
                    support_function_calling=False,
                    context_length=caps["context_length"],
                    provider="siliconflow",
                    extra=model_data
                ))
            elif is_rerank:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=False,
                    support_vision=False,
                    support_function_calling=False,
                    context_length=caps["context_length"],
                    provider="siliconflow",
                    extra=model_data
                ))
            else:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=caps["support_vision"],
                    support_function_calling=caps["support_function_calling"],
                    context_length=caps["context_length"],
                    provider="siliconflow",
                    extra=model_data
                ))

        return models

    # 聊天/嵌入/流式/异步接口均使用基类模板方法默认实现
    # （OpenAI 兼容格式，含 tool_calls 解析与 Vision 消息转换）

    # ==================== 多模态：图像生成 ====================

    def generate_image(
        self,
        prompt: str,
        model: Optional[str] = None,
        size: Optional[str] = None,
        **kwargs
    ) -> ImageResult:
        """生成图像（POST /images/generations）

        Args:
            prompt: 图像描述提示词
            model: 图像生成模型（默认取配置 image_model 或 Kwai-Kolors/Kolors）
            size: 图像尺寸（如 "1024x1024"）
            **kwargs: 其他 API 参数（如 batch_size、num_inference_steps）

        Returns:
            ImageResult: 图像生成结果（url 或 base64 至少其一有值）

        Raises:
            ConfigurationError: 未配置图像生成模型时抛出
        """
        model = model or self.config.get("image_model") or self.DEFAULT_IMAGE_MODEL
        if not model:
            raise ConfigurationError(
                "未配置图像生成模型，请在提供商配置中设置 image_model "
                "（如 Kwai-Kolors/Kolors）或调用时传入 model 参数"
            )

        payload: Dict[str, Any] = {"model": model, "prompt": prompt}
        if size:
            payload["image_size"] = size  # SiliconFlow 使用 image_size 字段
        payload.update(kwargs)
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        response = self._make_request("POST", self._image_endpoint, data=payload)

        data = response.get("data") or response.get("images") or []
        item = data[0] if data else {}
        return ImageResult(
            url=item.get("url"),
            base64=item.get("b64_json"),
            revised_prompt=item.get("revised_prompt"),
            model=model,
            provider=self.provider_type,
        )
