#!/usr/bin/env python3
r"""验证编辑模型（能力标签）后，模型列表同步显示修改（新架构适配版）.

新架构适配说明：新版 ``ui.dialog.llm_settings`` 设置对话框中，模型行
（``ModelRow``）不再逐能力显示中文标签，而是按 capabilities 推导主类型
徽章（对话/视觉/嵌入/重排序，见 ``widgets._model_primary_type``）；
编辑确认路径为主壳 ``LLMSettingsDialog._upsert_custom_model()`` 落盘
custom_models 后 ``ProviderDetailPanel.load_instance()`` 重载重渲。
本脚本模拟该编辑确认路径，验证：
1. 编辑结果已写入实例 custom_models（落盘）；
2. 模型列表重载后对应行的条目数据与主类型徽章同步刷新。

用法:
    .venv\Scripts\python.exe scripts\test_model_edit_sync.py
"""
import os
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ===================================================================
# 第三方依赖（需在 sys.path 就绪后导入）
from PySide6.QtWidgets import QApplication

# ===================================================================
# 项目模块
from core.llm.config import get_llm_config
from core.llm.model_schema import CAPABILITY_REASONING, CAPABILITY_VISION
from ui.dialog.llm_settings import LLMSettingsDialog
from ui.dialog.llm_settings.constants import MODEL_TYPE_CHAT, MODEL_TYPE_LABELS
from ui.dialog.llm_settings.widgets import _model_primary_type
from utils.style_qss import set_style_qss_theme


def find_model_row(detail_panel, model_id: str):
    """按模型 id 在模型分区中查找 ModelRow（不存在返回 None）."""
    for row in detail_panel._model_section._rows:
        if row.entry.get("id") == model_id:
            return row
    return None


def pick_new_capabilities(entry: dict) -> list:
    """挑选一组能使主类型徽章发生变化的能力标签.

    原主类型为对话时改为「视觉+推理」（主类型变为视觉）；否则改为
    「推理」（主类型回落为对话），保证徽章文本必然变化便于断言。

    Args:
        entry: 统一 schema 模型条目

    Returns:
        list: 新的 capabilities 列表
    """
    if _model_primary_type(entry) == MODEL_TYPE_CHAT:
        return [CAPABILITY_VISION, CAPABILITY_REASONING]
    return [CAPABILITY_REASONING]


def expected_badge_text(capabilities: list) -> str:
    """按 capabilities 推导期望的主类型徽章文本."""
    return MODEL_TYPE_LABELS[_model_primary_type({"capabilities": capabilities})]


def restore_custom_models(instance_id: str, original_custom: list) -> None:
    """恢复实例原始 custom_models 并重载详情面板，避免污染用户配置."""
    config = get_llm_config()
    cfg = config.get_provider(instance_id)
    cfg.extra["custom_models"] = original_custom
    config.add_provider(instance_id, cfg)


def main():
    app = QApplication([])
    set_style_qss_theme(app, "light")

    dialog = LLMSettingsDialog()
    dialog.resize(1200, 800)
    dialog.show()
    time.sleep(0.5)
    app.processEvents()

    detail = dialog._detail_panel
    instance_id = detail._instance_id
    print(f"当前实例: {instance_id}")
    assert instance_id, "未选中任何 Provider 实例"

    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 备份原始 custom_models，测试结束后原样恢复，避免污染用户配置
    cfg = get_llm_config().get_provider(instance_id)
    original_custom = list(cfg.extra.get("custom_models", []))

    # 编辑前：获取第一个模型行
    row = next(iter(detail._model_section._rows), None)
    if row is None:
        print("当前实例模型列表为空，跳过同步验证")
        return 0
    model = dict(row.entry)
    print(f"编辑前模型: {model['id']}, capabilities={model.get('capabilities')}")
    print(f"编辑前徽章: {row._badge.text()}")
    dialog.grab().save(str(out_dir / "edit_sync_before.png"))

    # 模拟编辑确认：修改能力标签，经主壳落盘入口写 custom_models 并重载
    new_caps = pick_new_capabilities(model)
    model_data = dict(model)
    model_data["capabilities"] = new_caps
    dialog._upsert_custom_model(instance_id, model_data)
    detail.load_instance(instance_id)
    app.processEvents()

    # 编辑后：重新获取同一个模型行
    row_after = find_model_row(detail, model["id"])
    assert row_after is not None, f"编辑后未找到模型 {model['id']}"
    print(f"编辑后模型: {row_after.entry['id']}, "
          f"capabilities={row_after.entry.get('capabilities')}")
    badge_after = row_after._badge.text()
    print(f"编辑后徽章: {badge_after}")
    dialog.grab().save(str(out_dir / "edit_sync_after.png"))

    # 验证 1：界面模型行数据与主类型徽章已同步
    assert row_after.entry.get("capabilities") == new_caps, \
        f"capabilities 未同步: {row_after.entry.get('capabilities')} != {new_caps}"
    assert badge_after == expected_badge_text(new_caps), \
        f"徽章未同步: {badge_after} != {expected_badge_text(new_caps)}"

    # 验证 2：编辑结果已落盘到实例 custom_models
    cfg_after = get_llm_config().get_provider(instance_id)
    saved = [m for m in cfg_after.extra.get("custom_models", [])
             if m.get("id") == model["id"]]
    assert saved and saved[0].get("capabilities") == new_caps, \
        f"custom_models 未落盘: {saved}"

    # 恢复原始 custom_models 并重载
    restore_custom_models(instance_id, original_custom)
    detail.load_instance(instance_id)
    app.processEvents()

    print("\n✅ 测试通过：编辑模型后模型列表已同步显示并即时落盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
