"""LLM 设置界面测试共享 fixture

- LLM 环境隔离：复用 test/core/llm 的 llm_v2_helpers.isolated_llm_env，
  配置路径指向 tmp_path、注册 Mock 适配器（无真实网络、不读写真实 config/ 与 data/）；
- QSettings 隔离：主壳 LLMSettingsDialog 的 QSettings 重定向到临时 ini
  文件（避免读写真实用户配置/注册表）；
- QMessageBox 拦截：确认/警告弹窗经 monkeypatch 替换为非阻塞实现。
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMessageBox

import ui.dialog.llm_settings.dialog as _dialog_mod

# test/core/llm 目录加入 sys.path，供导入 llm_v2_helpers（Mock 适配器与隔离环境）
_LLM_TEST_DIR = Path(__file__).resolve().parents[2] / "core" / "llm"
if str(_LLM_TEST_DIR) not in sys.path:
    sys.path.insert(0, str(_LLM_TEST_DIR))

from llm_v2_helpers import isolated_llm_env, make_mock_provider_config


@pytest.fixture(autouse=True)
def isolated_llm_environment(tmp_path, monkeypatch):
    """隔离 LLM 运行环境（autouse）

    实现见 llm_v2_helpers.isolated_llm_env：路径隔离、LLMConfig 单例重置、
    Mock 适配器注册、用量记录重定向，全程无真实网络访问。
    """
    with isolated_llm_env(tmp_path, monkeypatch) as env:
        yield env


@pytest.fixture
def mock_config_factory():
    """Mock 适配器实例配置工厂"""
    return make_mock_provider_config


@pytest.fixture(autouse=True)
def isolated_qsettings(tmp_path, monkeypatch):
    """将主壳 QSettings 重定向到临时 ini 文件（autouse）"""
    ini_file = tmp_path / "test_llm_settings.ini"
    monkeypatch.setattr(
        _dialog_mod, "QSettings",
        lambda org, app: QSettings(str(ini_file), QSettings.IniFormat))
    return ini_file


@pytest.fixture
def block_message_boxes(monkeypatch):
    """拦截 QMessageBox 静态弹窗（非阻塞，记录调用）"""
    calls = {"warning": [], "question": [], "information": []}
    monkeypatch.setattr(
        QMessageBox, "warning",
        staticmethod(lambda *args, **kw: calls["warning"].append(args)
                     or QMessageBox.StandardButton.Ok))
    monkeypatch.setattr(
        QMessageBox, "question",
        staticmethod(lambda *args, **kw: calls["question"].append(args)
                     or QMessageBox.StandardButton.Yes))
    monkeypatch.setattr(
        QMessageBox, "information",
        staticmethod(lambda *args, **kw: calls["information"].append(args)
                     or QMessageBox.StandardButton.Ok))
    return calls
