"""
Logger 接口

定义日志记录的抽象接口，用于依赖注入。
"""

from abc import ABC, abstractmethod


class ILogger(ABC):
    """
    日志记录器接口

    定义日志记录的抽象接口，插件和核心服务通过此接口进行日志记录，
    而非直接依赖 LoggerManager 实现。

    注意：本接口的各方法均不接受 exc_info 等标准 logging 关键字参数；
    需要记录异常堆栈时，请调用方自行用 traceback.format_exc() 格式化
    后并入 message 字符串。
    """

    @abstractmethod
    def info(self, name: str, message: str) -> None:
        """记录信息日志"""
        pass

    @abstractmethod
    def debug(self, name: str, message: str) -> None:
        """记录调试日志"""
        pass

    @abstractmethod
    def warning(self, name: str, message: str) -> None:
        """记录警告日志"""
        pass

    @abstractmethod
    def error(self, name: str, message: str) -> None:
        """记录错误日志"""
        pass

    @abstractmethod
    def critical(self, name: str, message: str) -> None:
        """记录严重错误日志"""
        pass
