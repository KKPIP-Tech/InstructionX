"""
DataProvider fixture

提供 DataProvider 实例用于数据层测试。
"""
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def temp_db(tmp_path):
    """
    创建临时数据库用于测试

    返回数据库路径和连接
    """
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))

    yield conn

    conn.close()


@pytest.fixture
def in_memory_db():
    """
    创建内存数据库用于测试

    适合不需要持久化的测试
    """
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def mock_data_provider():
    """
    创建模拟的 DataProvider

    不连接真实数据库，使用内存存储
    """
    with patch("core.data.data_provider.DatabaseManager") as mock_db:
        mock_db_instance = MagicMock()
        mock_db.return_value = mock_db_instance

        from core.data.data_provider import DataProvider, DataNamespace

        # 创建 DataProvider 实例
        provider = DataProvider.__new__(DataProvider)
        provider._cache = {}
        provider._subscribers = {}
        provider._db = mock_db_instance

        yield provider


@pytest.fixture
def data_provider_with_data(mock_data_provider):
    """
    创建带有测试数据的 DataProvider

    返回 provider 和预设的测试数据
    """
    test_data = {
        "test_key": "test_value",
        "nested": {"key1": "value1", "key2": 123},
        "list_data": [1, 2, 3, "test"],
    }

    # 预填充一些数据
    for key, value in test_data.items():
        mock_data_provider._cache[key] = value

    return {
        "provider": mock_data_provider,
        "data": test_data,
    }


@pytest.fixture
def temp_config_dir(tmp_path):
    """
    创建临时配置目录

    用于测试配置读写
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    return config_dir
