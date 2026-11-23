"""GitHub Key 基础测试夹具。"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.github import (
    GitHubApiClient,
    GitHubKeyManager,
    GitHubKeyStore,
    InMemorySecretVault,
)


@pytest.fixture
def key_store(tmp_path: Path, mock_logger) -> GitHubKeyStore:
    """创建使用内存凭据后端的临时 KeyStore。"""
    return GitHubKeyStore(
        tmp_path / "config",
        InMemorySecretVault(),
        logger=mock_logger,
    )


@pytest.fixture(autouse=True)
def reset_github_key_manager():
    """隔离 GitHubKeyManager 单例。"""
    GitHubKeyManager._instance = None
    yield
    GitHubKeyManager._instance = None


@pytest.fixture
def fake_response():
    """构造可配置的 requests Response 替身。"""

    def factory(
        status_code: int = 200,
        payload=None,
        headers=None,
    ) -> MagicMock:
        response = MagicMock()
        response.status_code = status_code
        response.payload = payload
        response.headers = headers or {}
        response.json.return_value = payload
        return response

    return factory


@pytest.fixture
def api_client():
    """创建使用可控 Session 的 API 客户端。"""
    session = MagicMock()
    return GitHubApiClient(
        session=session,
        api_base_url="https://api.github.test",
    ), session


@pytest.fixture
def key_manager(tmp_path, mock_logger):
    """创建注入假 API 的 Key 管理器。"""
    store = GitHubKeyStore(
        tmp_path / "config",
        InMemorySecretVault(),
        logger=mock_logger,
    )
    api = MagicMock()
    manager = GitHubKeyManager(
        store=store,
        api_client=api,
        environment_reader=lambda _name: "",
        logger=mock_logger,
    )
    return manager, store, api
