#!/usr/bin/env python3
r"""截取 LLM 设置对话框的截图，用于 UI 优化对比。

用法:
    .venv\Scripts\python.exe scripts\screenshot_llm_settings.py [--theme dark|light] [--out <dir>]
"""
import os
import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
os.chdir(project_root)
sys.path.insert(0, str(project_root))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--theme", default="light", choices=["light", "dark"])
    parser.add_argument("--out", default="scripts/screenshots")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 设置环境变量以便 Qt 能正确渲染
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setApplicationName("InstructionX")

    # 设置主题
    import ui.uikit_bootstrap  # noqa: F401  # 扩展 sys.path 使 InstructionX_UIKit 可导入
    from ui.uikit_theme import apply_uikit_theme
    apply_uikit_theme(app, args.theme)

    # 创建对话框
    from ui.dialog.llm_settings import LLMSettingsDialog
    dialog = LLMSettingsDialog()
    dialog.resize(1100, 750)
    dialog.show()

    # 等待渲染
    app.processEvents()

    # 截图
    pixmap = dialog.grab()
    shot_path = out_dir / f"llm_settings_{args.theme}_baseline.png"
    pixmap.save(str(shot_path))
    print(f"截图已保存: {shot_path}")
    print(f"尺寸: {pixmap.width()}x{pixmap.height()}")

    # 不需要 exec，直接截图
    return 0


if __name__ == "__main__":
    sys.exit(main())
