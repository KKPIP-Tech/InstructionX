#!/usr/bin/env python3
r"""截取模型编辑对话框的截图.

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
    from utils.style_qss import set_style_qss_theme
    set_style_qss_theme(app, "light")

    # 创建模型编辑对话框
    from ui.dialog.llm_settings_components import ModelEditDialog

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

    # 截图初始状态（更多设置折叠）
    pixmap = dialog.grab()
    out_dir = Path("scripts/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    shot_path = out_dir / "model_edit_dialog_collapsed.png"
    pixmap.save(str(shot_path))
    print(f"模型编辑对话框（折叠）: {shot_path}")

    # 展开更多设置
    dialog._more_btn.setChecked(True)
    dialog._toggle_more_settings()
    app.processEvents()

    # 截图展开状态
    pixmap = dialog.grab()
    shot_path = out_dir / "model_edit_dialog_expanded.png"
    pixmap.save(str(shot_path))
    print(f"模型编辑对话框（展开）: {shot_path}")
    print(f"尺寸: {pixmap.width()}x{pixmap.height()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
