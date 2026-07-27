#!/usr/bin/env python3
r"""截取模型编辑对话框的截图.

新架构适配说明：新版 ``ui.dialog.llm_settings.ModelEditDialog`` 取消了
「更多设置」折叠区，全部字段平铺展示，因此仅截取一张完整表单截图。

用法:
    .venv\Scripts\python.exe scripts\screenshot_model_edit_dialog.py
"""
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication([])

    # 设置主题
    import ui.uikit_bootstrap  # noqa: F401  # 扩展 sys.path 使 InstructionX_UIKit 可导入
    from ui.uikit_theme import apply_uikit_theme
    apply_uikit_theme(app, "light")

    # 创建模型编辑对话框
    from ui.dialog.llm_settings import ModelEditDialog

    model_data = {
        'id': 'Pro/moonshotai/Kimi-K2.5',
        'name': 'Pro/moonshotai/Kimi-K2.5',
        'group': 'pro',
        'input_price_per_1m': 0.0,
        'output_price_per_1m': 0.0,
    }

    dialog = ModelEditDialog(model_data=model_data)
    dialog.show()

    # 等待渲染
    app.processEvents()

    # 截图（新对话框全字段平铺，无折叠/展开两种状态）
    pixmap = dialog.grab()
    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_path = out_dir / "model_edit_dialog.png"
    pixmap.save(str(shot_path))
    print(f"模型编辑对话框: {shot_path}")
    print(f"尺寸: {pixmap.width()}x{pixmap.height()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
