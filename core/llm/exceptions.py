"""
LLM Provider 相关异常定义
"""


class LLMException(Exception):
    """LLM 基础异常类"""
    pass


class ConfigurationError(LLMException):
    """配置错误异常"""
    pass


class AuthenticationError(LLMException):
    """认证错误异常"""
    pass


class APIError(LLMException):
    """API 调用错误异常"""

    def __init__(self, message: str, status_code: int = None, provider: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class RateLimitError(APIError):
    """速率限制异常"""
    pass


class InvalidRequestError(LLMException):
    """无效请求异常"""
    pass


class ModelNotSupportedError(LLMException):
    """模型不支持异常"""
    pass


class ConnectionError(LLMException):
    """连接错误异常"""

    def __init__(self, message: str = "", provider: str = None, **kwargs):
        super().__init__(message)
        self.provider = provider
        self.extra = kwargs


class TimeoutError(LLMException):
    """超时异常"""

    def __init__(self, message: str = "", provider: str = None, **kwargs):
        super().__init__(message)
        self.provider = provider
        self.extra = kwargs


class StreamingError(LLMException):
    """流式输出错误异常"""
    pass
