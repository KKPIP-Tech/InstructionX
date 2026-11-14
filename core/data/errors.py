"""数据层共享异常，供兼容门面与独立数据操作模块共同使用。"""


class DataProviderError(Exception):
    """DataProvider 公共数据访问异常。"""
