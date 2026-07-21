"""回归测试：模型服务窗口模型开关交互的三个关联缺陷修复

覆盖缺陷（dev 分支 fc07fdd 修复）：
1. 停用模型后窗口跳回第一个供应商（ProviderListPanel.reload 重建时
   被 _apply_filter 的自动重选覆盖选中）；
2. 回到该供应商后模型列表只剩操作过的模型（LLMProvider.reload_config
   清空内存模型缓存且未从磁盘回填）；
3. 关闭再打开后操作报 RuntimeError: Internal C++ object already deleted
   （LLMConfig 单例持有已销毁面板的订阅回调）。
"""
import gc
import json
import logging

import pytest

from core.llm.config import LLMConfig, get_llm_config
from core.llm.llm_provider import LLMProvider
from core.llm.providers.base import BaseProvider

from ui.dialog.llm_settings import LLMSettingsDialog

# 测试用实例与缓存模型（API 拉取型供应商场景）
INSTANCE_ID = "siliconflow"
CACHED_MODEL_IDS = [
    "Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3",
    "BAAI/bge-m3", "BAAI/bge-reranker-v2-m3", "Qwen/Qwen2-VL-72B",
]


def _write_models_cache(monkeypatch) -> None:
    """向隔离配置目录写入 SiliconFlow 实例与磁盘模型缓存"""
    from core.llm import config as config_mod

    providers = {
        "version": 2,
        "providers": {
            "minimax": {
                "preset_id": "minimax", "name": "MiniMax",
                "adapter": "minimax", "api_key": "", "base_url": "",
                "enabled_chat": True, "enabled_embedding": False,
                "chat_model": "", "embedding_model": "",
                "order": 0, "custom_models": [],
            },
            INSTANCE_ID: {
                "preset_id": "siliconflow", "name": "SiliconFlow",
                "adapter": "siliconflow", "api_key": "", "base_url": "",
                "enabled_chat": True, "enabled_embedding": False,
                "chat_model": "", "embedding_model": "",
                "order": 1, "custom_models": [],
            },
        },
    }
    config_mod.CONFIG_FILE.write_text(
        json.dumps(providers, ensure_ascii=False), encoding="utf-8")
    models = [
        {"id": mid, "name": mid, "support_chat": True,
         "support_streaming": True, "support_embedding": False,
         "support_vision": False, "support_function_calling": False,
         "context_length": None,
         "input_price_per_1m": None, "output_price_per_1m": None,
         "provider": INSTANCE_ID}
        for mid in CACHED_MODEL_IDS
    ]
    config_mod.MODELS_CACHE_FILE.write_text(
        json.dumps({INSTANCE_ID: models}, ensure_ascii=False), encoding="utf-8")
    # 隔离配置已写入磁盘，重置单例迫使下次构造重新加载
    LLMConfig._instance = None
    LLMProvider._instance = None


@pytest.fixture()
def seeded_env(qapp, isolated_llm_environment, monkeypatch):
    """播种 SiliconFlow 实例 + 磁盘模型缓存，并禁止真实联网刷新"""
    _write_models_cache(monkeypatch)
    monkeypatch.setattr(
        BaseProvider, "refresh_models",
        lambda self, force=False: (_ for _ in ()).throw(
            RuntimeError("测试环境禁止联网")))
    return True


def _open_dialog(qtbot, qapp):
    """构造并展示设置对话框，选中 SiliconFlow 实例"""
    dialog = LLMSettingsDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    qapp.processEvents()
    dialog._list_panel._select(INSTANCE_ID)
    qapp.processEvents()
    return dialog


class TestModelToggleRegression:
    """模型开关交互回归测试"""

    def test_toggle_model_keeps_selection_and_models(
            self, qtbot, qapp, seeded_env):
        """停用模型后：选中不跳回首个供应商，模型列表不丢失"""
        dialog = _open_dialog(qtbot, qapp)
        detail = dialog._detail_panel
        rows_before = list(detail._model_section._rows)
        assert len(rows_before) == len(CACHED_MODEL_IDS)

        rows_before[0].switch.setChecked(False)
        qapp.processEvents()

        assert dialog._list_panel.current_provider_id() == INSTANCE_ID
        assert len(detail._model_section._rows) == len(CACHED_MODEL_IDS)

    def test_toggle_model_writes_enabled_override(
            self, qtbot, qapp, seeded_env):
        """停用模型写入 enabled=False 的 custom_models 覆写"""
        from core.llm import config as config_mod

        dialog = _open_dialog(qtbot, qapp)
        rows = dialog._detail_panel._model_section._rows
        rows[0].switch.setChecked(False)
        qapp.processEvents()

        data = json.loads(config_mod.CONFIG_FILE.read_text(encoding="utf-8"))
        custom = data["providers"][INSTANCE_ID]["custom_models"]
        assert any(
            e.get("id") == CACHED_MODEL_IDS[0] and e.get("enabled") is False
            for e in custom)

    def test_reopen_dialog_has_no_dangling_subscription(
            self, qtbot, qapp, seeded_env, caplog):
        """关闭再打开后重复操作：无悬挂回调、无 RuntimeError 日志"""
        dialog1 = _open_dialog(qtbot, qapp)
        dialog1.reject()
        dialog1.deleteLater()
        qapp.processEvents()
        del dialog1
        gc.collect()
        qapp.processEvents()
        assert len(get_llm_config()._subscribers) == 0

        dialog2 = _open_dialog(qtbot, qapp)
        rows2 = dialog2._detail_panel._model_section._rows
        assert len(rows2) == len(CACHED_MODEL_IDS)

        with caplog.at_level(logging.ERROR):
            rows2[1].switch.setChecked(False)
            qapp.processEvents()
        runtime_errors = [
            r for r in caplog.records
            if r.levelno >= logging.ERROR and "already deleted" in r.getMessage()]
        assert not runtime_errors
        assert dialog2._list_panel.current_provider_id() == INSTANCE_ID
        assert len(get_llm_config()._subscribers) == 1

        dialog2.reject()
        dialog2.deleteLater()
        qapp.processEvents()

    def test_reload_config_restores_models_from_disk(
            self, qtbot, qapp, seeded_env):
        """reload_config 清空内存模型缓存后从磁盘缓存回填（不联网）"""
        provider = LLMProvider()
        provider._models_cache.clear()
        provider.reload_config()
        assert len(provider.get_cached_models(INSTANCE_ID)) == len(
            CACHED_MODEL_IDS)
