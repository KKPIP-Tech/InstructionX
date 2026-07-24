"""Ollama Provider 实现模块

该模块提供 Ollama 本地大语言模型部署的接口实现。
继承自 BaseProvider，聊天/流式接口复用基类模板方法，
本模块保留 Ollama 特有的请求格式、响应解析与逐条嵌入实现。

Ollama 是一款可以在本地运行大语言模型的工具，支持多种开源模型。
该 Provider 连接到本地运行的 Ollama 服务（默认 http://localhost:11434）。

Ollama 官方文档: https://github.com/ollama/ollama

支持的模型类型:
    - 聊天模型：支持 llama、qwen、mistral 等多种开源模型
    - 嵌入模型：支持 nomic-embed-text 等
    - 视觉模型：支持 llava 等视觉模型

Classes:
    OllamaProvider: Ollama 本地模型提供商实现

使用示例:
    >>> from core.llm.providers.ollama import OllamaProvider
    >>> config = {"base_url": "http://localhost:11434", "chat_model": "llama3.1"}
    >>> provider = OllamaProvider(config, provider_name="ollama")
    >>> response = provider.chat([Message("user", "你好")])
"""

import json
from typing import Dict, Any, Optional, List, Union

from .base import BaseProvider
from ..provider_interface import (
    ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo,
    DEFAULT_TEMPERATURE,
)


class OllamaProvider(BaseProvider):
    """Ollama LLM Provider (本地部署)

    Ollama 本地大语言模型提供商实现，连接到本地运行的 Ollama 服务。
    支持从本地 API 获取模型列表，无需 API Key。
    聊天/流式聊天/异步聊天使用基类模板方法（配合本类的
    _prepare_chat_payload 与 _parse_chat_response 钩子）。

    Class Attributes:
        provider_type: 提供商类型标识 ("ollama")
        provider_name: 提供商显示名称 ("Ollama")
        support_chat: 是否支持聊天功能 (True)
        support_streaming: 是否支持流式输出 (True)
        support_embedding: 是否支持嵌入功能 (True)
        support_vision: 是否支持视觉功能 (True - 取决于具体模型)

    API 端点:
        - /api/chat: 聊天完成
        - /api/generate: 文本生成
        - /api/embeddings: 嵌入生成
        - /api/tags: 模型列表

    使用示例:
        >>> from core.llm.providers.ollama import OllamaProvider
        >>> from core.llm import Message
        >>> # 无需 API Key，只需指定 base_url
        >>> config = {"base_url": "http://localhost:11434", "chat_model": "llama3.1"}
        >>> provider = OllamaProvider(config)
        >>> response = provider.chat([Message("user", "你好")])
        >>> print(response.content)
    """

    # ==================== 类属性定义 ====================

    # 提供商标识
    provider_type = "ollama"
    provider_name = "Ollama"

    # 功能支持标志
    support_chat = True
    support_streaming = True
    support_embedding = True
    support_vision = True

    # ==================== 初始化 ====================

    def __init__(self, config: Optional[Dict[str, Any]] = None, provider_name: str = ""):
        """初始化 Ollama Provider

        Args:
            config: 提供商配置字典
            provider_name: 提供商名称（用于缓存标识）
        """
        super().__init__(config, provider_name)
        # API 端点定义
        self._chat_endpoint = "/api/chat"
        self._generate_endpoint = "/api/generate"
        self._embedding_endpoint = "/api/embeddings"
        self._models_endpoint = "/api/tags"
        # Ollama 默认端口
        if not self.base_url:
            self.base_url = "http://localhost:11434"

    # ==================== 模型列表解析 ====================

    def _parse_models_response(self, response: Dict[str, Any]) -> List[ModelInfo]:
        """解析 Ollama API 返回的模型列表

        从 Ollama 本地 API 响应中提取模型信息，并判断是否为视觉模型。

        API 端点: GET /api/tags

        响应格式:
            {
                "models": [
                    {
                        "name": "llama3.1",
                        "model": "llama3.1:latest",
                        "size": 3826793472,
                        "digest": "...",
                        "details": {
                            "parent_model": "",
                            "format": "gguf",
                            "family": "llama",
                            "families": ["llama"],
                            "parameter_size": "7B",
                            "quantization_level": "Q4_0"
                        }
                    }
                ]
            }

        Args:
            response: API 响应字典

        Returns:
            List[ModelInfo]: 模型信息列表
        """
        models = []

        for model_data in response.get("models", []):
            model_id = model_data.get("name", "")

            if not model_id:
                continue

            # 判断是否为 Vision 模型
            # Ollama vision 模型通常名称包含 "vision" 或 "llava"
            is_vision = "vision" in model_id.lower() or "llava" in model_id.lower()

            models.append(ModelInfo(
                id=model_id,
                name=model_id,
                support_chat=True,
                support_streaming=True,
                support_embedding=True,
                support_vision=is_vision,
                extra=model_data
            ))

        return models

    # ==================== 请求载荷准备 ====================

    def _prepare_chat_payload(
        self,
        messages: List[Union[Dict, Any]],
        model: Optional[str] = None,
        temperature: float = DEFAULT_TEMPERATURE,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """准备聊天请求载荷

        准备发送给 Ollama API 的请求参数。
        需要将消息格式转换为 Ollama 特有的格式。
        图片使用 Ollama 原生 images 字段（base64 字符串列表）。

        Args:
            messages: 消息列表
            model: 模型名称
            temperature: 温度参数
            max_tokens: 最大 token 数
            stream: 是否流式输出
            **kwargs: 其他参数

        Returns:
            Dict[str, Any]: 请求载荷字典
        """
        prepared_messages = self._prepare_messages(messages)

        # 转换消息格式为 Ollama 格式（保留原生 images 字段）
        ollama_messages = []
        for msg in prepared_messages:
            ollama_msg = {
                "role": msg["role"],
                "content": msg["content"]
            }
            # 处理多模态图片（Ollama 原生格式）
            if "images" in msg and msg["images"]:
                ollama_msg["images"] = msg["images"]
            ollama_messages.append(ollama_msg)

        payload: Dict[str, Any] = {
            "model": model or self.chat_model,
            "messages": ollama_messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            }
        }

        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        payload.update(kwargs)
        # 剔除 None 值，避免污染 API 请求
        return {k: v for k, v in payload.items() if v is not None}

    # ==================== 响应解析 ====================

    @staticmethod
    def _parse_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """解析 Ollama 响应中的 tool_calls 并转换为统一契约格式

        Ollama /api/chat 的 tool_calls 位于 message.tool_calls，
        其 function.arguments 已是 dict，需要序列化为 JSON 字符串；
        id 缺失时按 call_{name}_{i} 规则生成。

        Args:
            message: 响应中的 message 字典

        Returns:
            List[Dict]: OpenAI 风格 tool_calls 列表
                [{"id": str, "type": "function",
                  "function": {"name": str, "arguments": str(JSON)}}]
        """
        tool_calls = []
        for i, tc in enumerate(message.get("tool_calls") or []):
            function = tc.get("function") or {}
            name = function.get("name", "")
            arguments = function.get("arguments", "")
            # Ollama 返回的 arguments 通常是 dict，统一为 JSON 字符串
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False)
            tool_calls.append({
                "id": tc.get("id") or f"call_{name}_{i}",
                "type": "function",
                "function": {"name": name, "arguments": arguments},
            })
        return tool_calls

    def _parse_usage(self, response: Dict[str, Any]) -> Optional[UsageInfo]:
        """从 Ollama 响应中提取 usage 信息

        Ollama 使用 prompt_eval_count / eval_count 字段统计 token 用量
        （非流式响应与流式末尾块均在顶层返回）。

        Args:
            response: API 响应字典

        Returns:
            Optional[UsageInfo]: 用量信息，如果 API 未返回则返回 None
        """
        if "prompt_eval_count" in response or "eval_count" in response:
            input_tokens = response.get("prompt_eval_count")
            output_tokens = response.get("eval_count")
            total_tokens = None
            if input_tokens is not None or output_tokens is not None:
                total_tokens = (input_tokens or 0) + (output_tokens or 0)
            return UsageInfo(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
            )
        return super()._parse_usage(response)

    def _parse_chat_response(self, response: Dict[str, Any]) -> ChatResponse:
        """解析聊天响应

        从 Ollama API 响应中提取聊天内容、思考过程（如果有）与 tool_calls。

        Args:
            response: API 响应字典

        Returns:
            ChatResponse: 聊天响应对象
        """
        message = response.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=response.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("thinking", ""),
            tool_calls=self._parse_tool_calls(message),
            usage=self._parse_usage(response),
            extra=response
        )

    def _parse_stream_response(self, data: Dict) -> ChatResponse:
        """解析流式响应

        从流式数据块中提取聊天内容、思考过程与 tool_calls。
        末尾块（done=true）中的 token 统计会映射进 usage。

        Args:
            data: 流式数据块

        Returns:
            ChatResponse: 聊天响应对象
        """
        message = data.get("message", {})

        return ChatResponse(
            content=message.get("content", ""),
            model=data.get("model", ""),
            role=message.get("role", "assistant"),
            reasoning_content=message.get("thinking", ""),
            tool_calls=self._parse_tool_calls(message),
            usage=self._parse_usage(data),
            extra=data
        )

    # 聊天/流式聊天/异步聊天/异步流式均使用基类模板方法默认实现
    # （端点与解析钩子已由本类提供）

    # ==================== 嵌入 API ====================

    def embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """发送嵌入请求（同步）

        将文本转换为向量嵌入。
        注意：Ollama 的嵌入 API 不支持批量处理，需要逐个请求。

        Args:
            texts: 单个文本或文本列表
            model: 嵌入模型名称（可选，默认使用配置中的模型）
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        if isinstance(texts, str):
            texts = [texts]

        model_name = model or self.embedding_model

        embeddings = []
        for text in texts:
            payload = {
                "model": model_name,
                "prompt": text,
            }
            payload.update(kwargs)
            # 剔除 None 值，避免污染 API 请求
            payload = {k: v for k, v in payload.items() if v is not None}

            response = self._make_request("POST", self._embedding_endpoint, data=payload)

            embeddings.append(EmbeddingResponse(
                embedding=response.get("embedding", []),
                model=model_name,
                extra=response
            ))

        return embeddings

    async def async_embed(
        self,
        texts: Union[str, List[str]],
        model: Optional[str] = None,
        **kwargs
    ) -> List[EmbeddingResponse]:
        """异步发送嵌入请求

        注意：Ollama 的嵌入 API 不支持批量处理，需要逐个请求。

        Args:
            texts: 文本或文本列表
            model: 嵌入模型名称
            **kwargs: 其他参数

        Returns:
            List[EmbeddingResponse]: 嵌入响应列表
        """
        if isinstance(texts, str):
            texts = [texts]

        model_name = model or self.embedding_model

        embeddings = []
        for text in texts:
            payload = {
                "model": model_name,
                "prompt": text,
            }
            payload.update(kwargs)
            # 剔除 None 值，避免污染 API 请求
            payload = {k: v for k, v in payload.items() if v is not None}

            response = await self._make_async_request("POST", self._embedding_endpoint, data=payload)

            embeddings.append(EmbeddingResponse(
                embedding=response.get("embedding", []),
                model=model_name,
                extra=response
            ))

        return embeddings

    def validate_config(self) -> bool:
        """验证配置是否有效（仅格式校验，不代表连通性）

        Ollama 不需要 API Key，只需确保 base_url 已设置。
        注意：本方法不发起任何网络请求，返回 True 仅表示配置格式完整，
        不代表本地 Ollama 服务实际可用。

        Returns:
            bool: 配置是否有效（base_url 是否设置）
        """
        # Ollama 不需要 API Key，只需要确保 base_url 可用
        return bool(self.base_url)
