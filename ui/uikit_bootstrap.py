# -*- coding: utf-8 -*-
"""UIKit 导入引导：让 ``ui/InstructionX_UIKit`` 以顶层包身份可导入。

背景：InstructionX_UIKit 库内约 20 个模块使用
``from InstructionX_UIKit.xxx import ...`` 绝对导入（库独立维护，不改库文件）。
若仅作为 ``ui.InstructionX_UIKit`` 子包导入，这些绝对导入会 ImportError。

本模块在被导入时（模块级副作用）把项目根的 ``ui/`` 目录追加到 ``sys.path``
（用 append 而非 insert(0)，避免 ``ui/`` 下其他子包遮蔽同名第三方包），
此后 ``import InstructionX_UIKit`` 与库内绝对导入解析到同一模块对象，
保证 ThemeManager 等单例全局唯一。

用法：``main.py`` 的第一行业务 import 必须是 ``import ui.uikit_bootstrap``
（早于任何 ``InstructionX_UIKit`` / ``ui.uikit_theme`` 导入）。
"""

import sys
from pathlib import Path

_UI_DIR = Path(__file__).resolve().parent
if str(_UI_DIR) not in sys.path:
    sys.path.append(str(_UI_DIR))
