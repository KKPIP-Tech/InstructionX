"""
LLM Chat 服务层 - 处理 LLM 调用逻辑
"""

import base64
from typing import Dict, Any, List, Optional
from pathlib import Path

from core.llm import get_llm_provider
from core.llm.exceptions import (
    LLMException,
    ConfigurationError,
    AuthenticationError,
    APIError,
    RateLimitError,
    TimeoutError,
    ConnectionError,
    InvalidRequestError,
)
from core.llm.provider_interface import Message, ModelInfo
from core.data.data_provider import DataProvider, DataNamespace

from utils.logging_tools import LoggerManager, get_name


class LLMChatService:
    """LLM Chat 服务类"""

    _logger = LoggerManager()

    def __init__(self, plugin_id: str, data_provider: Optional[DataProvider] = None):
        self.plugin_id = plugin_id
        self.data_provider = data_provider or DataProvider()
        self._llm_provider = None

    @property
    def llm_provider(self):
        """获取 LLM Provider 单例"""
        if self._llm_provider is None:
            self._llm_provider = get_llm_provider()
        return self._llm_provider

    def get_providers(self) -> List[str]:
        """获取所有可用的 Provider 列表"""
        try:
            providers = self.llm_provider.get_enabled_providers("chat")
            return list(providers.keys())
        except Exception as e:
            self._logger.error(get_name(), f'获取 Provider 列表失败: {e}')
            return []

    def get_all_providers(self) -> Dict[str, Any]:
        """获取所有 Provider（包括未启用的）"""
        try:
            return self.llm_provider.get_all_providers()
        except Exception as e:
            self._logger.error(get_name(), f'获取所有 Provider 失败: {e}')
            return {}

    def get_models(self, provider: str) -> List[ModelInfo]:
        """获取指定 Provider 的模型列表"""
        try:
            # 优先从缓存获取
            cached_models = self.llm_provider.get_cached_models(provider)
            if cached_models:
                return cached_models

            # 从 Provider 获取
            provider_instance = self.llm_provider.get_provider(provider)
            if provider_instance:
                return provider_instance.get_models()
            return []
        except Exception as e:
            self._logger.error(get_name(), f'获取模型列表失败: {e}')
            return []

    def get_provider_config(self, provider: str) -> Optional[Dict[str, Any]]:
        """获取 Provider 配置"""
        try:
            config = self.llm_provider.config.get_provider(provider)
            if config:
                return config.to_dict()
            return None
        except Exception as e:
            self._logger.error(get_name(), f'获取 Provider 配置失败: {e}')
            return None

    def validate_provider(self, provider: str) -> Dict[str, Any]:
        """
        验证 Provider 配置是否有效

        Returns:
            Dict with 'valid' (bool), 'message' (str), 'supports_vision' (bool)
        """
        self._logger.debug(get_name(), f"Validating provider: {provider}")

        try:
            provider_instance = self.llm_provider.get_provider(provider)
            self._logger.debug(get_name(), f"Provider instance: {provider_instance}")

            if not provider_instance:
                self._logger.debug(get_name(), "Provider instance not found!")
                return {
                    "valid": False,
                    "message": f"Provider '{provider}' 不存在",
                    "supports_vision": False,
                }

            # 检查配置
            self._logger.debug(get_name(), f"API Key: {provider_instance.api_key}")
            self._logger.debug(get_name(), f"Base URL: {provider_instance.base_url}")
            self._logger.debug(get_name(), f"validate_config result: {provider_instance.validate_config()}")

            if not provider_instance.validate_config():
                return {
                    "valid": False,
                    "message": "API Key 或 Base URL 未配置",
                    "supports_vision": False,
                }

            # 检查是否支持 Vision
            models = self.get_models(provider)
            supports_vision = any(
                getattr(m, "support_vision", False) for m in models
            )

            return {
                "valid": True,
                "message": "配置有效",
                "supports_vision": supports_vision,
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"验证失败: {str(e)}",
                "supports_vision": False,
            }

    def send_message(
        self,
        message: str,
        provider: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        发送消息并获取回复

        Args:
            message: 用户消息
            provider: Provider 名称
            model: 模型名称（可选）
            temperature: 温度参数
            max_tokens: 最大 token 数
            images: 图片 base64 列表（用于 Vision）
            history: 对话历史

        Returns:
            Dict with 'success' (bool), 'response' (str), 'error' (str), 'model' (str)
        """
        # ========== DEBUG 信息 ==========
        self._logger.debug(get_name(), f"Provider: {provider}")
        self._logger.debug(get_name(), f"Model: {model}")
        self._logger.debug(get_name(), f"Temperature: {temperature}")
        self._logger.debug(get_name(), f"Max Tokens: {max_tokens}")

        # 输出 Provider 详细信息
        try:
            provider_instance = self.llm_provider.get_provider(provider)
            if provider_instance:
                self._logger.debug(get_name(), f"Provider instance: {type(provider_instance)}")
                self._logger.debug(get_name(), f"API Key: {'已设置' if provider_instance.api_key else '未设置'}")
                self._logger.debug(get_name(), f"Base URL: {provider_instance.base_url}")
                self._logger.debug(get_name(), f"Chat Model: {provider_instance.chat_model}")
            else:
                self._logger.debug(get_name(), "Provider instance not found!")
        except Exception as e:
            self._logger.debug(get_name(), f"Error getting provider: {e}")

        try:
            # 构建消息列表
            messages = []

            # 添加历史记录
            if history:
                for msg in history:
                    messages.append(
                        Message(
                            role=msg.get("role", "user"),
                            content=msg.get("content", ""),
                            images=msg.get("images") or [],
                        )
                    )

            # 添加当前消息
            current_message = Message(
                role="user",
                content=message,
                images=images or [],
            )
            messages.append(current_message)

            # 发送请求
            response = self.llm_provider.chat(
                messages=messages,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return {
                "success": True,
                "response": response.content,
                "model": response.model,
                "reasoning": getattr(response, "reasoning_content", ""),
                "tool_calls": getattr(response, "tool_calls", []),
            }

        except AuthenticationError as e:
            return {
                "success": False,
                "error": f"认证失败: API Key 无效或已过期。请检查 LLM 设置。",
                "error_type": "authentication",
            }
        except RateLimitError as e:
            return {
                "success": False,
                "error": f"请求频率超限: API 调用过于频繁，请稍后重试。",
                "error_type": "rate_limit",
            }
        except TimeoutError as e:
            return {
                "success": False,
                "error": f"请求超时: 服务器响应时间过长，请检查网络或稍后重试。",
                "error_type": "timeout",
            }
        except ConnectionError as e:
            error_msg = f"连接失败: 无法连接到 API 服务器，请检查网络连接。"
            if hasattr(e, 'provider'):
                error_msg += f" (Provider: {e.provider})"
            if str(e):
                error_msg += f" - {str(e)}"
            self._logger.debug(get_name(), f"ConnectionError: {e}, provider: {getattr(e, 'provider', None)}")
            return {
                "success": False,
                "error": error_msg,
                "error_type": "connection",
            }
        except InvalidRequestError as e:
            return {
                "success": False,
                "error": f"无效请求: {str(e)}",
                "error_type": "invalid_request",
            }
        except ConfigurationError as e:
            return {
                "success": False,
                "error": f"配置错误: {str(e)}。请检查 LLM 设置。",
                "error_type": "configuration",
            }
        except APIError as e:
            return {
                "success": False,
                "error": f"API 错误: {str(e)}",
                "error_type": "api",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"未知错误: {str(e)}",
                "error_type": "unknown",
            }

    def stream_send_message(
        self,
        message: str,
        provider: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        images: Optional[List[str]] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ):
        """
        流式发送消息（生成器）

        Yields:
            Dict with 'chunk' (str), 'done' (bool), 'error' (str)
        """
        # ========== DEBUG 信息 ==========
        self._logger.debug(get_name(), f"Provider: {provider}")
        self._logger.debug(get_name(), f"Model: {model}")

        try:
            # 构建消息列表
            messages = []

            # 添加历史记录
            if history:
                for msg in history:
                    messages.append(
                        Message(
                            role=msg.get("role", "user"),
                            content=msg.get("content", ""),
                            images=msg.get("images") or [],
                        )
                    )

            # 添加当前消息
            current_message = Message(
                role="user",
                content=message,
                images=images or [],
            )
            messages.append(current_message)

            # 流式请求
            self._logger.debug(get_name(), "Starting stream request...")
            responses = self.llm_provider.stream_chat(
                messages=messages,
                provider=provider,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            self._logger.debug(get_name(), "Got response iterator, iterating...")
            full_response = ""
            for response in responses:
                content = response.content or ""  # 处理 None 的情况
                full_response += content
                self._logger.debug(get_name(), f"Chunk received: {len(content)} chars")
                yield {
                    "chunk": content,
                    "done": False,
                    "model": response.model,
                }

            yield {
                "chunk": "",
                "done": True,
                "full_response": full_response,
            }

        except AuthenticationError as e:
            yield {
                "chunk": "",
                "done": True,
                "error": f"认证失败: API Key 无效或已过期。",
                "error_type": "authentication",
            }
        except RateLimitError as e:
            yield {
                "chunk": "",
                "done": True,
                "error": f"请求频率超限: API 调用过于频繁。",
                "error_type": "rate_limit",
            }
        except TimeoutError as e:
            yield {
                "chunk": "",
                "done": True,
                "error": f"请求超时: 服务器响应时间过长。",
                "error_type": "timeout",
            }
        except ConnectionError as e:
            self._logger.debug(get_name(), f"ConnectionError: {e}, provider: {getattr(e, 'provider', None)}")

            # 尝试获取更多调试信息
            try:
                provider_instance = self.llm_provider.get_provider(provider)
                if provider_instance:
                    self._logger.debug(get_name(), f"Full URL: {provider_instance.base_url}/chat/completions")
            except Exception as ex:
                self._logger.debug(get_name(), f"Error getting URL: {ex}")

            yield {
                "chunk": "",
                "done": True,
                "error": f"连接失败: 无法连接到 API 服务器。详细信息: {str(e)}",
                "error_type": "connection",
            }
        except Exception as e:
            import traceback
            self._logger.debug(get_name(), f"Exception: {e}")
            self._logger.debug(get_name(), f"Traceback: {traceback.format_exc()}")
            yield {
                "chunk": "",
                "done": True,
                "error": f"错误: {str(e)}",
                "error_type": "unknown",
            }

    def load_image_as_base64(self, image_path: str) -> Optional[str]:
        """
        将图片文件转换为 base64 字符串

        Args:
            image_path: 图片文件路径

        Returns:
            base64 字符串，失败返回 None
        """
        try:
            path = Path(image_path)
            if not path.exists():
                return None

            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except Exception as e:
            self._logger.error(get_name(), f'读取图片失败: {e}')
            return None

    # ========== 数据持久化 ==========

    def save_preference(self, key: str, value: Any):
        """保存偏好设置"""
        self.data_provider.set_plugin_data(
            self.plugin_id,
            key,
            value,
            DataNamespace.PRIVATE,
        )

    def load_preference(self, key: str, default: Any = None) -> Any:
        """加载偏好设置"""
        return self.data_provider.get_plugin_data(
            self.plugin_id,
            key,
            DataNamespace.PRIVATE,
            default,
        )

    def save_chat_history(self, history: List[Dict[str, Any]]):
        """保存对话历史"""
        self.save_preference("chat_history", history)

    def load_chat_history(self) -> List[Dict[str, Any]]:
        """加载对话历史"""
        return self.load_preference("chat_history", [])

    def get_current_llm_preference(self) -> tuple:
        """获取当前全局 LLM 选择（供其他插件使用）

        从 DataProvider 读取系统级 LLM Provider/Model 选择。

        Returns:
            tuple: (provider_name, model_name)
        """
        provider = self.data_provider.get_plugin_data(
            "__app_llm__", "provider", DataNamespace.PRIVATE, ""
        )
        model = self.data_provider.get_plugin_data(
            "__app_llm__", "model", DataNamespace.PRIVATE, ""
        )
        return provider, model
