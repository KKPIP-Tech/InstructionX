"""LLM 模块 - 异常类定义

该模块定义了 LLM 提供商相关的所有异常类型，继承自 LLMException 基类。
采用层次化设计，不同类型的错误对应不同的异常类，便于错误处理和日志记录。

异常层次:
    LLMException (基类)
    ├── ConfigurationError (配置错误)
    ├── AuthenticationError (认证错误，自带 status_code/provider 属性)
    ├── APIError (API调用错误)
    │   └── RateLimitError (速率限制)
    ├── InvalidRequestError (无效请求)
    ├── ModelNotSupportedError (模型不支持)
    ├── ConnectionError (连接错误)
    ├── TimeoutError (超时错误)
    └── StreamingError (流式输出错误)

使用示例:
    >>> from core.llm.exceptions import LLMException, APIError
    >>> try:
    ...     # LLM API 调用
    ...     pass
    ... except APIError as e:
    ...     print(f"API错误: {e}, 状态码: {e.status_code}")
"""

from typing import Optional


class LLMException(Exception):
    """LLM 基础异常类

    所有 LLM 相关异常的基类，继承自 Python 内置 Exception 类。
    可用于捕获所有 LLM 模块相关的异常。
    """
    pass


class ConfigurationError(LLMException):
    """配置错误异常

    当 LLM 提供商的配置不正确时抛出，例如：
    - 配置文件格式错误
    - 缺少必需的配置项
    - 配置值类型不匹配
    """
    pass


class AuthenticationError(LLMException):
    """认证错误异常

    当 API 密钥无效或已过期时抛出，常见原因：
    - API 密钥为空
    - API 密钥格式错误
    - API 密钥已过期或被撤销

    Attributes:
        message: 错误消息描述
        status_code: HTTP 响应状态码（可选，通常为 401）
        provider: 抛出异常的 LLM 提供商名称（可选）

    Note:
        保持直接继承 LLMException（而非 APIError），以便调用方区分
        认证失败与一般 API 错误；属性签名与 APIError 对齐。
    """

    def __init__(self, message: str, status_code: Optional[int] = None, provider: Optional[str] = None):
        """初始化认证错误异常

        Args:
            message: 错误消息描述
            status_code: HTTP 响应状态码（通常为 401）
            provider: LLM 提供商名称
        """
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class APIError(LLMException):
    """API 调用错误异常

    当 LLM API 返回错误响应时抛出，包含 HTTP 状态码和提供商信息。

    Attributes:
        message: 错误消息描述
        status_code: HTTP 响应状态码（可选）
        provider: 抛出异常的 LLM 提供商名称（可选）
    """

    def __init__(self, message: str, status_code: Optional[int] = None, provider: Optional[str] = None):
        """初始化 API 错误异常

        Args:
            message: 错误消息描述
            status_code: HTTP 响应状态码
            provider: LLM 提供商名称
        """
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


class RateLimitError(APIError):
    """速率限制异常

    当 API 请求频率超过限制时抛出，常见原因：
    - 短时间内请求次数过多
    - 并发请求数超过配额
    - 账户配额耗尽
    """
    pass


class InvalidRequestError(LLMException):
    """无效请求异常

    当请求参数不符合 API 要求时抛出，常见原因：
    - 模型名称不存在
    - 参数值超出有效范围
    - 消息格式不正确
    - 超出最大 token 限制
    """
    pass


class ModelNotSupportedError(LLMException):
    """模型不支持异常

    当请求的模型不被当前提供商支持时抛出。
    """
    pass


class ConnectionError(LLMException):
    """连接错误异常

    当无法连接到 LLM API 服务时抛出。

    Attributes:
        message: 错误消息描述
        provider: 抛出异常的 LLM 提供商名称（可选）
        extra: 额外的错误信息字典（可选）
    """

    def __init__(self, message: str = "", provider: Optional[str] = None, **kwargs):
        """初始化连接错误异常

        Args:
            message: 错误消息描述
            provider: LLM 提供商名称
            **kwargs: 额外的错误信息
        """
        super().__init__(message)
        self.provider = provider
        self.extra = kwargs


class TimeoutError(LLMException):
    """超时异常

    当 API 请求超时时抛出，常见原因：
    - 网络延迟过高
    - 服务端处理时间过长
    - 请求超时配置过短

    Attributes:
        message: 错误消息描述
        provider: 抛出异常的 LLM 提供商名称（可选）
        extra: 额外的错误信息字典（可选）
    """

    def __init__(self, message: str = "", provider: Optional[str] = None, **kwargs):
        """初始化超时异常

        Args:
            message: 错误消息描述
            provider: LLM 提供商名称
            **kwargs: 额外的错误信息
        """
        super().__init__(message)
        self.provider = provider
        self.extra = kwargs


class StreamingError(LLMException):
    """流式输出错误异常

    当流式 API 调用发生错误时抛出，例如：
    - 流式响应解析失败
    - 流式连接中断
    - 回调函数执行异常
    """
    pass