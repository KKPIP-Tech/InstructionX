"""LLM 测试目录共享 fixture

- 配置隔离：autouse fixture 将 core.llm.config 的路径常量与
  LLMPluginService 会话持久化路径指向 tmp_path（不读写真实 config/ 与 data/），
  隔离逻辑实现于 llm_v2_helpers.isolated_llm_env（供其它测试目录复用）；
- 单例重置：LLMConfig 单例在隔离环境中重置（LLMProvider / LLMPluginService /
  BackgroundTaskManager / UsageRecordStore 由 test/conftest.py 全局重置）；
- Mock 适配器：mock-adapter 家族键注册可控 MockAdapter（无真实网络，
  实现见 llm_v2_helpers.py）；
- 配置样本工厂：v1 / v2 配置样本生成函数（不含真实密钥）。
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# 本目录加入 sys.path，供测试模块导入 llm_v2_helpers
_LLM_TEST_DIR = Path(__file__).resolve().parent
if str(_LLM_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_LLM_TEST_DIR))

import core.llm.config as _config_mod

from llm_v2_helpers import (
    build_v1_sample,
    build_v2_sample,
    isolated_llm_env,
    make_mock_provider_config,
)


# ==================== 共享 fixture ====================

@pytest.fixture(autouse=True)
def isolated_llm_environment(tmp_path, monkeypatch):
    """隔离 LLM 运行环境（autouse）

    实现见 llm_v2_helpers.isolated_llm_env：路径隔离、LLMConfig 单例重置、
    Mock 适配器注册、用量记录重定向，全程无真实网络访问。
    """
    with isolated_llm_env(tmp_path, monkeypatch) as env:
        yield env


@pytest.fixture
def config_file(isolated_llm_environment) -> Path:
    """隔离后的配置文件路径（llm_providers.json）"""
    return _config_mod.CONFIG_FILE


@pytest.fixture
def write_config(config_file):
    """写入配置文件工具：data -> 落盘 JSON 并返回路径"""
    def _write(data: Dict[str, Any]) -> Path:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return config_file
    return _write


@pytest.fixture
def v1_config_data():
    """v1 配置样本工厂（每次调用返回全新样本）"""
    return build_v1_sample


@pytest.fixture
def v2_config_data():
    """v2 配置样本工厂"""
    return build_v2_sample


@pytest.fixture
def mock_config_factory():
    """Mock 适配器实例配置工厂"""
    return make_mock_provider_config
