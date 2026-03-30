"""Data 模块 - 插件式桌面应用程序的数据层

该模块提供数据持久化、缓存和访问接口，主要包括：
- DataProvider: 核心数据提供者，负责插件数据的存储和管理

模块依赖:
    - utils.logging_tools: 日志管理工具

使用示例:
    >>> from core.data import DataProvider
    >>> provider = DataProvider()
    >>> provider.register_plugin("plugin-001", "VideoEditor")
"""

from .data_provider import DataProvider, DataNamespace, DataProviderError


__all__ = [
    "DataProvider",
    "DataNamespace",
    "DataProviderError",
]

