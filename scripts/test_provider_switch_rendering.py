#!/usr/bin/env python3
r"""测试 Provider 切换时的样式渲染一致性与自动保存语义（新架构适配版）.

新架构适配说明：新版 ``ui.dialog.llm_settings`` 设置对话框为「自动保存」
语义，切换 Provider 无脏检查弹窗，编辑即时落盘。与旧架构的结构差异：
- 详情面板启用开关为头部 ``_master_switch``（SwitchButton），实例名
  称为 ``_name_label``（重命名经「更多」菜单弹窗）；
- 模型列表为 ``_model_section._rows``（ModelRow 列表，行间 hairline，
  不再有 ModelGroupWidget 分组容器）；
- 模型行编辑为双击触发，行内仅有启用开关与删除按钮。

本脚本验证：
1. 初始渲染时样式正确；
2. 编辑（切换总开关）后切换 Provider，配置已落盘（写回
   config/llm_providers.json）且详情面板正确加载新实例；
3. 切换回来后渲染保持一致，并将总开关恢复原值。

用法:
    .venv\Scripts\python.exe scripts\test_provider_switch_rendering.py
"""
import json
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
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QToolButton

# ===================================================================
# 项目模块
import ui.uikit_bootstrap  # noqa: F401  # 必须为首个项目 import：扩展 sys.path 使 InstructionX_UIKit 可导入
from core.llm.config import get_llm_config
from ui.dialog.llm_settings import LLMSettingsDialog
from ui.uikit_theme import apply_uikit_theme

CONFIG_PATH = Path("config/llm_providers.json")


def test_widget_rendering(widget, name: str) -> dict:
    """测试单个 Widget 的渲染属性."""
    return {
        'name': name,
        'styled_background': widget.testAttribute(
            Qt.WidgetAttribute.WA_StyledBackground),
        'auto_fill_background': widget.autoFillBackground(),
        'has_stylesheet': bool(widget.styleSheet()),
        'visible': widget.isVisible(),
    }


def check_model_rows_rendering(detail_panel, tag: str) -> None:
    """检查详情面板模型行前两条的渲染属性并打印."""
    rows = detail_panel._model_section._rows
    print(f"{tag}模型行数量: {len(rows)}")
    for i, row in enumerate(rows[:2]):
        result = test_widget_rendering(row, f"Row_{i}_{tag}")
        print(f"  行 {i}: styled_bg={result['styled_background']}, "
              f"auto_fill={result['auto_fill_background']}, "
              f"has_style={result['has_stylesheet']}")


def read_saved_enabled(instance_id: str):
    """从落盘的配置文件读取指定实例的 enabled_chat（不存在返回 None）."""
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    entry = data.get("providers", {}).get(instance_id)
    return entry.get("enabled_chat") if entry else None


def check_first_row_controls(detail_panel) -> None:
    """检查第一个模型行的开关与删除按钮（无模型行时明确提示）."""
    rows = detail_panel._model_section._rows
    if not rows:
        print("模型列表为空，跳过模型行控件检查")
        return
    first_row = rows[0]
    delete_buttons = first_row.findChildren(QToolButton)
    print(f"启用开关存在: {first_row.switch is not None}")
    print(f"启用开关大小: {first_row.switch.size().width()}x"
          f"{first_row.switch.size().height()}")
    print(f"删除按钮数量: {len(delete_buttons)}")
    if delete_buttons:
        btn = delete_buttons[0]
        print(f"删除按钮大小: {btn.size().width()}x{btn.size().height()}")


def verify_edit_persisted(instance_id: str, expected: bool) -> None:
    """断言启用开关编辑结果已落盘为期望值."""
    saved_enabled = read_saved_enabled(instance_id)
    print(f"落盘值: enabled_chat={saved_enabled}（期望 {expected}）")
    assert saved_enabled == expected, \
        f"编辑未落盘: enabled_chat={saved_enabled} != {expected}"


def main():
    app = QApplication([])

    # 设置主题
    apply_uikit_theme(app, "light")

    # 创建对话框
    dialog = LLMSettingsDialog()
    dialog.resize(1200, 800)
    dialog.show()

    # 等待渲染
    time.sleep(0.5)
    app.processEvents()

    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    list_panel = dialog._list_panel
    detail_panel = dialog._detail_panel

    print("=" * 60)
    print("测试 1: 初始渲染状态")
    print("=" * 60)

    initial_provider = list_panel.current_provider_id()
    print(f"当前实例: {initial_provider}")
    assert initial_provider, "未选中任何 Provider 实例"
    check_model_rows_rendering(detail_panel, "initial")

    initial_shot = out_dir / "test_initial_render.png"
    dialog.grab().save(str(initial_shot))
    print(f"初始截图: {initial_shot}")

    providers = get_llm_config().get_all_providers()
    provider_names = list(providers.keys())
    if len(provider_names) <= 1:
        print("\n仅有一个 Provider 实例，跳过切换测试")
        return 0

    print("\n" + "=" * 60)
    print("测试 2: 自动保存（编辑落盘）+ 切换后详情加载")
    print("=" * 60)

    # 在当前实例上做一次编辑：翻转总开关（自动保存语义下即时落盘）
    # 注：SwitchButton.set_checked_no_anim() 不发射 toggled（避免加载回填
    # 时误落盘），此处直接发射 toggled 模拟用户点击
    initial_enabled = providers[initial_provider].enabled_chat
    detail_panel._master_switch.toggled.emit(not initial_enabled)
    app.processEvents()
    print(f"切换前编辑: enabled_chat {initial_enabled} -> {not initial_enabled}")
    verify_edit_persisted(initial_provider, not initial_enabled)

    # 切换到另一个实例
    next_provider = next(
        (name for name in provider_names if name != initial_provider),
        provider_names[0],
    )
    print(f"切换到实例: {next_provider}")
    list_panel._select(next_provider)
    time.sleep(0.5)
    app.processEvents()

    # 验证详情面板正确加载新实例（无脏检查弹窗，直接切换）
    assert detail_panel._instance_id == next_provider, \
        f"详情面板未加载新实例: {detail_panel._instance_id}"
    expected_name = get_llm_config().get_provider(next_provider).name
    assert detail_panel._name_label.text() == expected_name, \
        f"详情名称不正确: {detail_panel._name_label.text()} != {expected_name}"
    print(f"详情已加载: {detail_panel._name_label.text()}")

    # 切换后此前的编辑仍保持落盘
    assert read_saved_enabled(initial_provider) == (not initial_enabled), \
        "切换后编辑结果未保持落盘"
    print("切换后编辑结果保持落盘 ✅")

    check_model_rows_rendering(detail_panel, "switched")
    switched_shot = out_dir / "test_switched_render.png"
    dialog.grab().save(str(switched_shot))
    print(f"切换后截图: {switched_shot}")

    print("\n" + "=" * 60)
    print("测试 3: 切回初始实例并恢复原值")
    print("=" * 60)

    list_panel._select(initial_provider)
    time.sleep(0.5)
    app.processEvents()
    assert detail_panel._instance_id == initial_provider, \
        f"切回后详情面板实例不正确: {detail_panel._instance_id}"

    back_shot = out_dir / "test_switched_back_render.png"
    dialog.grab().save(str(back_shot))
    print(f"切回截图: {back_shot}")

    # 恢复总开关原值并验证落盘，避免污染用户配置
    detail_panel._master_switch.toggled.emit(initial_enabled)
    app.processEvents()
    verify_edit_persisted(initial_provider, initial_enabled)
    print(f"总开关已恢复: enabled_chat={initial_enabled} ✅")

    print("\n" + "=" * 60)
    print("测试 4: 模型行控件检查")
    print("=" * 60)
    check_first_row_controls(detail_panel)

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
