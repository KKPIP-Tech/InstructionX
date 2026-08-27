# -*- coding: utf-8 -*-
"""macOS Dock 栏应用图标设置。

直接以 ``python main.py`` 运行时进程属于 Python.app，Dock 栏默认显示
Python 自身图标；``setWindowIcon`` 在 macOS 上不影响 Dock。本模块经
AppKit（pyobjc，macOS 条件依赖）在运行时替换为本应用 Logo。

非 macOS 平台为空操作；加载/设置失败仅记录 WARNING 日志，不影响启动。
"""

import sys
from pathlib import Path

from utils.logging_tools import LoggerManager, get_name

# 平台条件导入：pyobjc 仅 macOS 安装（pyproject 中按 sys_platform 限定），
# Windows/Linux 不会执行本分支，不影响跨平台运行
if sys.platform == "darwin":
    import AppKit


def set_macos_dock_icon(icon_path: Path) -> None:
    """设置 macOS Dock 栏应用图标（其他平台空操作）。

    Args:
        icon_path: 方形图标 PNG 文件路径（建议 256×256 及以上）
    """
    if sys.platform != "darwin":
        return
    try:
        image = AppKit.NSImage.alloc().initWithContentsOfFile_(str(icon_path))
        if image is None:
            LoggerManager().warning(
                get_name(), f"Dock 图标加载失败（文件不可读或格式不支持）: {icon_path}"
            )
            return
        AppKit.NSApplication.sharedApplication().setApplicationIconImage_(image)
        LoggerManager().info(get_name(), f"macOS Dock 图标已设置: {icon_path}")
    except Exception as e:
        LoggerManager().warning(get_name(), f"设置 macOS Dock 图标失败: {e}")
