"""数据层测试共享隔离，避免真实日志处理器影响临时目录。"""

import pytest


@pytest.fixture(autouse=True)
def isolate_sqlite_logger(mocker):
    """将 SQLite 后端日志替换为测试替身，防止 MagicMock 类继承冲突。"""
    return mocker.patch(
        "core.data.sqlite_backend.LoggerManager",
        return_value=mocker.MagicMock(),
    )
