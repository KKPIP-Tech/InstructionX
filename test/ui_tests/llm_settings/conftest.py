"""LLM 设置界面测试共享 fixture

- LLM 环境隔离：复用 test/core/llm 的 llm_v2_helpers.isolated_llm_env，
  配置路径指向 tmp_path、注册 Mock 适配器（无真实网络、不读写真实 config/ 与 data/）；
- QSettings 隔离：主壳 LLMSettingsDialog 的 QSettings 重定向到临时 ini
  文件（避免读写真实用户配置/注册表）；
- 反馈层拦截：包内用户反馈已统一走 feedback 模块（UIKit 轻提示/对话框，
  替代旧 QMessageBox），经 monkeypatch 替换为非阻塞实现并记录调用。
"""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QSettings

import ui.dialog.llm_settings.dialog as _dialog_mod
import ui.dialog.llm_settings.model_edit_dialog as _model_edit_mod
import ui.dialog.llm_settings.model_section as _model_section_mod
import ui.dialog.llm_settings.provider_detail_panel as _detail_panel_mod
import ui.dialog.llm_settings.provider_editor_dialog as _provider_editor_mod
import ui.dialog.llm_settings.sync_models_dialog as _sync_models_mod

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
    """拦截 llm_settings 反馈层（UIKit 轻提示/确认对话框），非阻塞并记录调用

    包内用户反馈已统一走 feedback 模块（ui/dialog/llm_settings/feedback.py），
    不再使用 QMessageBox；且各消费模块以别名导入
    （如 from .feedback import warn as _warn_toast），patch 包级
    feedback.warn 无法拦截，故在各消费模块命名空间逐一替换。

    返回的 calls 字典沿用旧键名，保持既有断言语义：
    - "warning"：warn 轻提示（表单校验失败等）；
    - "question"：confirm 确认对话框（自动按「确定」处理，返回 True）；
    - "information"：notice 结果告知对话框与 info/success 轻提示。
    """
    calls = {"warning": [], "question": [], "information": []}

    def _recorder(kind):
        """生成记录调用的替换实现（记录位置参数元组）"""
        return lambda *args, **kw: calls[kind].append(args)

    def _auto_confirm(*args, **kw):
        """confirm 替换实现：记录调用并直接返回「确定」"""
        calls["question"].append(args)
        return True

    # 校验/警告轻提示（warn）
    monkeypatch.setattr(_model_edit_mod, "_warn_toast", _recorder("warning"))
    monkeypatch.setattr(_provider_editor_mod, "_warn_toast",
                        _recorder("warning"))
    # 阻塞式确认对话框（confirm，自动确认）
    monkeypatch.setattr(_model_section_mod, "_confirm_dialog", _auto_confirm)
    monkeypatch.setattr(_detail_panel_mod, "_confirm_dialog", _auto_confirm)
    # 结果告知对话框与信息/成功轻提示（notice / info / success）
    monkeypatch.setattr(_detail_panel_mod, "_notice_dialog",
                        _recorder("information"))
    monkeypatch.setattr(_detail_panel_mod, "_info_toast",
                        _recorder("information"))
    monkeypatch.setattr(_sync_models_mod, "_info_toast",
                        _recorder("information"))
    monkeypatch.setattr(_sync_models_mod, "_success_toast",
                        _recorder("information"))
    return calls
