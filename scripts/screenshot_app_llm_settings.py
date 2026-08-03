#!/usr/bin/env python3
r"""启动实际应用程序并截取 LLM 设置对话框截图.

用法:
    .venv\Scripts\python.exe scripts\screenshot_app_llm_settings.py [--theme dark|light]
"""
import os
import sys
import argparse
import time
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
    parser.add_argument("--wait", type=int, default=3, help="等待应用启动的秒数")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 设置环境变量
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtCore import Qt, QTimer

    app = QApplication(sys.argv)
    app.setApplicationName("InstructionX")

    # 设置主题
    import ui.uikit_bootstrap  # noqa: F401  # 扩展 sys.path 使 InstructionX_UIKit 可导入
    from ui.uikit_theme import apply_uikit_theme
    apply_uikit_theme(app, args.theme)

    # 创建主窗口
    from ui.main_window import InstructionXMainWindow
    main_window = InstructionXMainWindow()
    main_window.show()

    # 等待主窗口完全显示
    time.sleep(args.wait)
    app.processEvents()

    # 打开 LLM 设置对话框
    print("正在打开 LLM 设置对话框...")
    from ui.dialog.llm_settings import LLMSettingsDialog
    dialog = LLMSettingsDialog(main_window)
    dialog.resize(1200, 800)

    # 使用非模态方式显示，以便截图
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()

    # 等待对话框完全渲染
    time.sleep(1)
    app.processEvents()

    # 截图整个对话框
    pixmap = dialog.grab()
    shot_path = out_dir / f"llm_settings_app_{args.theme}.png"
    pixmap.save(str(shot_path))
    print(f"对话框截图已保存: {shot_path}")
    print(f"尺寸: {pixmap.width()}x{pixmap.height()}")

    # 同时截图主窗口（包含对话框）
    main_pixmap = main_window.grab()
    main_shot_path = out_dir / f"main_window_{args.theme}.png"
    main_pixmap.save(str(main_shot_path))
    print(f"主窗口截图已保存: {main_shot_path}")

    # 不进入事件循环，直接退出
    return 0


if __name__ == "__main__":
    sys.exit(main())
