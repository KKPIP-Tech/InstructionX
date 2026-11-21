"""UIKit alpha-v1.0.4 同步副本的框架无网冒烟。"""
import importlib

import ui.uikit_bootstrap  # noqa: F401
import InstructionX_UIKit
from InstructionX_UIKit.components import BudgetSliderGroup
from InstructionX_UIKit.icons import ICONOIR_NAMES, icon_svg
from PySide6.QtCanvasPainter import QCanvasPainterWidget

EXPECTED_VERSION = "alpha-v1.0.4"
REQUIRED_MODULES = (
    "InstructionX_UIKit.charts.canvas_factory",
    "InstructionX_UIKit.charts.canvas_item_viewport",
    "InstructionX_UIKit.charts.rhi_viewport",
    "InstructionX_UIKit.blueprint.canvas_viewport",
    "InstructionX_UIKit.code_editor.completion",
)
REQUIRED_ICONS = ("home", "component", "stats-report", "view-grid", "play", "settings")
EXPECTED_ICONOIR_COUNT = 1671


def check_library() -> None:
    """校验版本、直接 Canvas 模块和图标资产。"""
    assert InstructionX_UIKit.__version__ == EXPECTED_VERSION
    assert BudgetSliderGroup is not None
    assert QCanvasPainterWidget is not None
    assert len(ICONOIR_NAMES) == EXPECTED_ICONOIR_COUNT
    for module_name in REQUIRED_MODULES:
        assert importlib.import_module(module_name) is not None
    for icon_name in REQUIRED_ICONS:
        assert "<svg" in icon_svg(icon_name)


def main() -> int:
    """执行框架库静态检查，失败时由断言输出具体缺失项。"""
    check_library()
    print("UIKit 同步冒烟：PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
