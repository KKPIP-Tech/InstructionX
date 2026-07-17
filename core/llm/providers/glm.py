"""GLM (智谱AI) Provider 实现模块

该模块提供智谱 GLM 大语言模型的接口实现。
继承自 BaseProvider，聊天、嵌入、流式输出等通用逻辑复用基类模板方法，
本模块仅保留预设模型列表、模型列表解析与图像生成实现。

智谱AI API 文档: https://open.bigmodel.cn/dev/api

支持的模型类型:
    - CHAT_MODELS: 文本聊天模型（如 glm-5, glm-4.7, glm-4-flash 等）
    - EMBEDDING_MODELS: 向量嵌入模型（embedding-3, embedding-2）
    - VISION_MODELS: 视觉理解模型（glm-4.6v, glm-4v-flash 等）
    - IMAGE_MODELS: 图像生成模型（glm-image, cogview-4 等）
    - VIDEO_MODELS: 视频生成模型（cogvideox-3, vidu-2 等）
    - AUDIO_MODELS: 音视频模型（glm-tts, glm-asr-2512 等）
    - OTHER_MODELS: 其他模型（codegeex-4, rerank 等）

Classes:
    GLMProvider: 智谱 GLM 提供商实现

使用示例:
    >>> from core.llm.providers.glm import GLMProvider
    >>> config = {"api_key": "xxx", "base_url": "https://open.bigmodel.cn/api/paas/v4"}
    >>> provider = GLMProvider(config, provider_name="glm")
    >>> response = provider.chat([Message("user", "你好")])
"""

from typing import Dict, Any, Optional, List

from .base import BaseProvider
from ..provider_interface import ModelInfo
from ..exceptions import ConfigurationError
from ..types import ImageResult


class GLMProvider(BaseProvider):
    """GLM (智谱AI) LLM Provider

    智谱 AI 大语言模型提供商实现，支持文本聊天、视觉理解、嵌入生成等功能。
    继承自 BaseProvider，使用预设模型列表无需调用 API 获取模型列表。
    聊天/嵌入/流式响应解析直接使用基类的 OpenAI 兼容实现
    （含 tool_calls 解析与 Vision 消息转换）。

    Class Attributes:
        provider_type: 提供商类型标识 ("glm")
        provider_name: 提供商显示名称 ("GLM")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (True)
        CHAT_MODELS: 文本聊天模型列表
        EMBEDDING_MODELS: 向量嵌入模型列表
        VISION_MODELS: 视觉理解模型列表
        IMAGE_MODELS: 图像生成模型列表
        VIDEO_MODELS: 视频生成模型列表
        AUDIO_MODELS: 音视频模型列表
        OTHER_MODELS: 其他模型列表
        MODEL_DETAILS: 预设模型详细信息

    API 端点:
        - /chat/completions: 聊天完成
        - /embeddings: 嵌入生成
        - /models: 模型列表
        - /images/generations: 图像生成

    使用示例:
        >>> from core.llm.providers.glm import GLMProvider
        >>> from core.llm import Message
        >>> config = {"api_key": "your_api_key", "chat_model": "glm-4-flash"}
        >>> provider = GLMProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "glm"
    provider_name = "GLM"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    # 图像生成默认模型（与 IMAGE_MODELS 对齐，可被配置 image_model 覆盖）
    DEFAULT_IMAGE_MODEL = "cogview-3-flash"

    # ==================== 预设模型列表 ====================

    # GLM 模型列表（官方文档：https://docs.bigmodel.cn/cn/guide/start/model-overview）
    # 文本模型
    CHAT_MODELS = [
        # 旗舰模型
        "glm-5",
        "glm-5-turbo",
        # 高智能模型
        "glm-4.7",
        "glm-4.7-flashx",
        # 超强性能
        "glm-4.6",
        # 高性价比
        "glm-4.5-air",
        "glm-4.5-airx",
        # 超长输入
        "glm-4-long",
        # 高速低价
        "glm-4-flashx-250414",
        # 免费模型
        "glm-4.7-flash",
        "glm-4.5-flash",
        "glm-4-flash-250414",
    ]

    # 向量模型 (Embedding)
    EMBEDDING_MODELS = [
        "embedding-3",
        "embedding-2",
    ]

    # 视觉理解模型 (Vision)
    VISION_MODELS = [
        "glm-4.6v",
        "glm-4.1v-thinking-flashx",
        "glm-4.6v-flash",
        "glm-4.1v-thinking-flash",
        "glm-4v-flash",
    ]

    # 图像生成模型（generate_image 的默认模型从此列表选取）
    IMAGE_MODELS = [
        "glm-image",
        "cogview-4",
        "cogview-3-flash",
    ]

    # 视频生成模型
    VIDEO_MODELS = [
        "cogvideox-3",
        "vidu-q1",
        "vidu-2",
        "cogvideox-flash",
    ]

    # 音视频模型（语音合成/识别，暂无对应接口实现，仅作能力展示）
    AUDIO_MODELS = [
        "glm-tts",
        "glm-tts-clone",
        "glm-asr-2512",
        "glm-realtime",
        "glm-4-voice",
    ]

    # 其他模型
    OTHER_MODELS = [
        "charglm-4",
        "emohaa",
        "codegeex-4",
        "rerank",
    ]

    # ==================== 预设模型详情 ====================

    # 预设模型详情字典，包含上下文长度、输出限制、功能支持等信息
    MODEL_DETAILS = {
        # 文本模型
        "glm-5": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "最新旗舰基座模型 - 编程能力对齐Claude Opus 4.5"
        },
        "glm-5-turbo": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "旗舰增强基座 - 复杂长任务执行连续性好"
        },
        "glm-4.7": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "高智能模型 - 通用对话、推理与智能体能力全面升级"
        },
        "glm-4.7-flashx": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "轻量高速 - 适用于中文写作、翻译、长文本等通用场景"
        },
        "glm-4.6": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "超强性能 - 高级编码能力、强大推理以及工具调用能力"
        },
        "glm-4.5-air": {
            "context_length": 128000,
            "max_output": 96000,
            "support_function_calling": True,
            "description": "高性价比 - 在推理、编码和智能体任务上表现强劲"
        },
        "glm-4.5-airx": {
            "context_length": 128000,
            "max_output": 96000,
            "support_function_calling": True,
            "description": "高性价比-极速版 - 推理速度快，适用于时效性要求强的场景"
        },
        "glm-4-long": {
            "context_length": 1000000,
            "max_output": 4000,
            "support_function_calling": True,
            "description": "超长输入 - 支持高达1M上下文长度"
        },
        "glm-4-flashx-250414": {
            "context_length": 128000,
            "max_output": 16000,
            "support_function_calling": True,
            "description": "高速低价 - Flash增强版本，超快推理速度"
        },
        "glm-4.7-flash": {
            "context_length": 200000,
            "max_output": 128000,
            "support_function_calling": True,
            "description": "免费模型 - 最新基座模型的普惠版本"
        },
        "glm-4.5-flash": {
            "context_length": 128000,
            "max_output": 96000,
            "support_function_calling": True,
            "description": "免费模型（即将下线）- 支持深度思考模式"
        },
        "glm-4-flash-250414": {
            "context_length": 128000,
            "max_output": 16000,
            "support_function_calling": True,
            "description": "免费模型 - 超长上下文处理能力"
        },
        # 向量模型
        "embedding-3": {
            "context_length": 8000,
            "support_function_calling": False,
            "description": "向量模型 V3"
        },
        "embedding-2": {
            "context_length": 8000,
            "support_function_calling": False,
            "description": "向量模型 V2"
        },
        # 视觉模型
        "glm-4.6v": {
            "context_length": 128000,
            "max_output": 32000,
            "support_function_calling": True,
            "description": "旗舰视觉推理模型 - 视觉推理模型SOTA"
        },
        "glm-4.1v-thinking-flashx": {
            "context_length": 64000,
            "max_output": 16000,
            "support_function_calling": True,
            "description": "轻量视觉推理 - 复杂场景理解、多步骤分析"
        },
        "glm-4.6v-flash": {
            "context_length": 128000,
            "max_output": 32000,
            "support_function_calling": True,
            "description": "免费模型 - 视觉推理能力，支持工具调用"
        },
        "glm-4.1v-thinking-flash": {
            "context_length": 64000,
            "max_output": 16000,
            "support_function_calling": True,
            "description": "免费模型 - 视觉推理能力"
        },
        "glm-4v-flash": {
            "context_length": 16000,
            "max_output": 1000,
            "support_function_calling": False,
            "description": "免费模型 - 图像理解、多语言支持"
        },
        # 图像生成模型
        "glm-image": {
            "context_length": None,
            "support_function_calling": False,
            "description": "旗舰图像生成模型 - 文字渲染开源SOTA"
        },
        "cogview-4": {
            "context_length": None,
            "support_function_calling": False,
            "description": "图像生成模型 - 高质量图像生成、风格多样化"
        },
        "cogview-3-flash": {
            "context_length": None,
            "support_function_calling": False,
            "description": "免费模型 - 创意丰富多样、推理速度快"
        },
        # 视频生成模型
        "cogvideox-3": {
            "context_length": None,
            "support_function_calling": False,
            "description": "高智能旗舰视频生成模型"
        },
        "vidu-q1": {
            "context_length": None,
            "support_function_calling": False,
            "description": "质量较优 - 影视级画质清晰度"
        },
        "vidu-2": {
            "context_length": None,
            "support_function_calling": False,
            "description": "高速低价 - 速度优、性价比优"
        },
        "cogvideox-flash": {
            "context_length": None,
            "support_function_calling": False,
            "description": "免费模型 - 沉浸式AI音效、4K高清"
        },
        # 音视频模型
        "glm-tts": {
            "context_length": None,
            "support_function_calling": False,
            "description": "语音合成模型 - 超拟人语音合成"
        },
        "glm-tts-clone": {
            "context_length": None,
            "support_function_calling": False,
            "description": "音色克隆模型 - 3秒音频即可生成音色"
        },
        "glm-asr-2512": {
            "context_length": None,
            "support_function_calling": False,
            "description": "语音识别 - 字符错误率极低"
        },
        "glm-realtime": {
            "context_length": 120000,
            "support_function_calling": False,
            "description": "实时音视频 - 实时视频通话功能"
        },
        "glm-4-voice": {
            "context_length": None,
            "support_function_calling": False,
            "description": "语音模型 - 实时语音对话"
        },
        # 其他模型
        "charglm-4": {
            "context_length": 8000,
            "max_output": 4000,
            "support_function_calling": False,
            "description": "拟人模型 - 情感陪伴和虚拟角色"
        },
        "emohaa": {
            "context_length": 8000,
            "max_output": 4000,
            "support_function_calling": False,
            "description": "心理模型 - 专业咨询能力"
        },
        "codegeex-4": {
            "context_length": 128000,
            "max_output": 32000,
            "support_function_calling": False,
            "description": "代码模型 - 代码自动补全"
        },
        "rerank": {
            "context_length": 4000,
            "support_function_calling": False,
            "description": "重排序模型 - 对召回结果进行重排序"
        },
    }

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 GLM Provider

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

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 GLM API 返回的模型列表

        从智谱 API 响应中提取模型信息，并根据模型 ID 判断模型类型。

        API 响应格式:
            {
                "request_id": "...",
                "data": [
                    {
                        "id": "glm-4",
                        "object": "model",
                        "created": 1699254000,
                        "owned_by": "zhipuai"
                    }
                ]
            }

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

            # 根据模型 ID 判断类型
            is_embedding = "embedding" in model_id.lower()
            is_vision = "4v" in model_id.lower() or "cogview" in model_id.lower()

            if is_embedding:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=False,
                    support_streaming=False,
                    support_embedding=True,
                    support_vision=False,
                    extra=model_data
                ))
            else:
                models.append(ModelInfo(
                    id=model_id,
                    name=model_id,
                    support_chat=True,
                    support_streaming=True,
                    support_embedding=False,
                    support_vision=is_vision,
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
            model: 图像生成模型（默认取配置 image_model 或 cogview-3-flash，
                可选值见 IMAGE_MODELS）
            size: 图像尺寸（如 "1024x1024"）
            **kwargs: 其他 API 参数（如 quality、user_id）

        Returns:
            ImageResult: 图像生成结果（url 或 base64 至少其一有值）

        Raises:
            ConfigurationError: 未配置图像生成模型时抛出
        """
        model = model or self.config.get("image_model") or self.DEFAULT_IMAGE_MODEL
        if not model:
            raise ConfigurationError(
                "未配置图像生成模型，请在提供商配置中设置 image_model "
                f"（可选值: {', '.join(self.IMAGE_MODELS)}）或调用时传入 model 参数"
            )

        payload: Dict[str, Any] = {"model": model, "prompt": prompt}
        if size:
            payload["size"] = size
        payload.update(kwargs)
        # 剔除 None 值，避免污染 API 请求
        payload = {k: v for k, v in payload.items() if v is not None}

        response = self._make_request("POST", self._image_endpoint, data=payload)

        data = response.get("data") or []
        item = data[0] if data else {}
        return ImageResult(
            url=item.get("url"),
            base64=item.get("b64_json"),
            revised_prompt=item.get("revised_prompt"),
            model=model,
            provider=self.provider_type,
        )
