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
