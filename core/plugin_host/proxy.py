"""与插件 Service/API 调用形态对齐的进程外动态代理。"""

from typing import Any

from .protocol import ErrorCode, RpcError, RpcResult
from .supervisor import PluginHost


class RemotePluginProxy:
    """把公开方法访问转换为 ``PluginHost.call``，始终返回结构化结果。

    仅用于无 UI 且参数、返回值均可 JSON 序列化的 Service/API。代理不会伪造
    Qt 控件、对象引用或框架内事件订阅。
    """

    def __init__(self, host: PluginHost, default_timeout: float = 3.0) -> None:
        self._host = host
        if default_timeout <= 0:
            raise ValueError("代理默认超时必须大于零")
        self._default_timeout = default_timeout

    def call(
        self, method: str, args: list | dict, timeout: float | None = None
    ) -> RpcResult:
        """显式调用指定公开方法，可选覆盖本次调用的截止期。"""
        actual_timeout = self._default_timeout if timeout is None else timeout
        return self._host.call(method, args, actual_timeout)

    def __getattr__(self, method: str):
        """生成与 Service 公开方法同名的有界 RPC 可调用对象。"""
        if method.startswith("_"):
            raise AttributeError(method)

        def invoke(*args: Any, **kwargs: Any) -> RpcResult:
            if args and kwargs:
                error = RpcError(ErrorCode.INVALID_PARAMS.value, "位置参数与命名参数不能混用")
                return RpcResult(error=error)
            parameters = kwargs if kwargs else list(args)
            return self.call(method, parameters)

        return invoke
