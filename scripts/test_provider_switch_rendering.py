#!/usr/bin/env python3
r"""测试 Provider 切换时的样式渲染一致性.

该脚本验证：
1. 初始渲染时样式正确
2. 切换 Provider 后样式保持一致
3. 边框、图标等元素正确渲染

用法:
    .venv\Scripts\python.exe scripts\test_provider_switch_rendering.py
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


def test_widget_rendering(widget, name: str) -> dict:
    """测试单个 Widget 的渲染属性."""
    result = {
        'name': name,
        'styled_background': widget.testAttribute(Qt.WidgetAttribute.WA_StyledBackground),
        'auto_fill_background': widget.autoFillBackground(),
        'has_stylesheet': bool(widget.styleSheet()),
        'visible': widget.isVisible(),
    }
    return result


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication([])

    # 设置主题
    from utils.style_qss import set_style_qss_theme
    set_style_qss_theme(app, "light")

    # 创建对话框
    from ui.dialog.llm_settings_dialog import LLMSettingsDialog
    dialog = LLMSettingsDialog()
    dialog.resize(1200, 800)
    dialog.show()

    # 等待渲染
    time.sleep(0.5)
    app.processEvents()

    print("=" * 60)
    print("测试 1: 初始渲染状态")
    print("=" * 60)

    # 测试初始 Provider 的模型分组
    initial_provider = dialog._current_provider_name
    print(f"当前 Provider: {initial_provider}")

    if dialog._model_groups_layout:
        count = dialog._model_groups_layout.count()
        print(f"模型分组数量: {count}")

        for i in range(min(count, 2)):
            item = dialog._model_groups_layout.itemAt(i)
            if item and item.widget():
                group = item.widget()
                result = test_widget_rendering(group, f"Group_{i}")
                print(f"  分组 {i}: styled_bg={result['styled_background']}, "
                      f"auto_fill={result['auto_fill_background']}, "
                      f"has_style={result['has_stylesheet']}")

    # 截图初始状态
    from pathlib import Path
    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    pixmap = dialog.grab()
    initial_shot = out_dir / "test_initial_render.png"
    pixmap.save(str(initial_shot))
    print(f"初始截图: {initial_shot}")

    print("\n" + "=" * 60)
    print("测试 2: 切换 Provider 后的渲染状态")
    print("=" * 60)

    # 切换到另一个 Provider
    providers = dialog._llm_config.get_all_providers()
    provider_names = list(providers.keys())
    if len(provider_names) > 1:
        # 选择一个与当前不同的 Provider（修复原先可能重选同一 Provider 的问题）
        next_provider = next(
            (name for name in provider_names if name != initial_provider),
            provider_names[0],
        )
        print(f"切换到 Provider: {next_provider}")

        # 模拟切换
        item = dialog._provider_items.get(next_provider)
        if item:
            dialog._provider_list_widget.setCurrentItem(item)
            time.sleep(0.5)
            app.processEvents()

            # 检查新的模型分组
            if dialog._model_groups_layout:
                count = dialog._model_groups_layout.count()
                print(f"切换后模型分组数量: {count}")

                for i in range(min(count, 2)):
                    item = dialog._model_groups_layout.itemAt(i)
                    if item and item.widget():
                        group = item.widget()
                        result = test_widget_rendering(group, f"Group_{i}_after")
                        print(f"  分组 {i}: styled_bg={result['styled_background']}, "
                              f"auto_fill={result['auto_fill_background']}, "
                              f"has_style={result['has_stylesheet']}")

            # 截图切换后状态
            pixmap = dialog.grab()
            switched_shot = out_dir / "test_switched_render.png"
            pixmap.save(str(switched_shot))
            print(f"切换后截图: {switched_shot}")

            # 切换回初始 Provider，验证渲染保持一致
            back_item = dialog._provider_items.get(initial_provider)
            if back_item:
                dialog._provider_list_widget.setCurrentItem(back_item)
                time.sleep(0.5)
                app.processEvents()
                pixmap = dialog.grab()
                back_shot = out_dir / "test_switched_back_render.png"
                pixmap.save(str(back_shot))
                print(f"切回截图: {back_shot}")

    print("\n" + "=" * 60)
    print("测试 3: 模型项按钮功能")
    print("=" * 60)

    # 测试模型项的按钮
    if dialog._model_groups_layout and dialog._model_groups_layout.count() > 0:
        group_item = dialog._model_groups_layout.itemAt(0)
        if group_item and group_item.widget():
            group = group_item.widget()
            if hasattr(group, '_content') and group._content:
                content_layout = group._content.layout()
                if content_layout and content_layout.count() > 0:
                    model_item = content_layout.itemAt(0)
                    if model_item and model_item.widget():
                        widget = model_item.widget()
                        if hasattr(widget, '_edit_btn') and hasattr(widget, '_delete_btn'):
                            edit_btn = widget._edit_btn
                            delete_btn = widget._delete_btn
                            print(f"编辑按钮存在: {edit_btn is not None}")
                            print(f"删除按钮存在: {delete_btn is not None}")
                            print(f"编辑按钮大小: {edit_btn.size().width()}x{edit_btn.size().height()}")
                            print(f"删除按钮大小: {delete_btn.size().width()}x{delete_btn.size().height()}")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    from PySide6.QtCore import Qt
    sys.exit(main())
