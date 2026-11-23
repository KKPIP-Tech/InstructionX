"""UIKit alpha-v1.0.4 同步副本守卫测试。

覆盖版本钉扎、顶层导入唯一性、既有组件、直接 Canvas/RHI 模块、
流式与缓存 API，以及框架禁止经 ui.InstructionX_UIKit 子包导入的约束。
"""

import re
import sys
from pathlib import Path

import pytest

EXPECTED_UIKIT_VERSION = "alpha-v1.0.4"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+ui\.InstructionX_UIKit", re.MULTILINE
)
_SCAN_DIRS = ("core", "utils", "workers")
_SCAN_FILES = ("main.py",)
EXPECTED_ICONOIR_COUNT = 1671


def _framework_sources() -> list:
    """收集框架自身 Python 源文件（排除 UIKit 库副本与测试目录）。"""
    sources = [PROJECT_ROOT / name for name in _SCAN_FILES]
    for dir_name in _SCAN_DIRS:
        sources.extend((PROJECT_ROOT / dir_name).rglob("*.py"))
    ui_dir = PROJECT_ROOT / "ui"
    for path in ui_dir.rglob("*.py"):
        if "InstructionX_UIKit" not in path.parts:
            sources.append(path)
    return sources


class TestUIKitVersion:
    """副本版本钉扎。"""

    def test_uikit_version_matches_synced_upstream(self):
        """__version__ 等于当前同步的上游版本号。"""
        import InstructionX_UIKit
        assert InstructionX_UIKit.__version__ == EXPECTED_UIKIT_VERSION


class TestUIKitBootstrap:
    """导入引导契约（ui.uikit_bootstrap）。"""

    def test_bootstrap_enables_top_level_import(self):
        """导入 ui.uikit_bootstrap 后 InstructionX_UIKit 以顶层包可导入。"""
        import ui.uikit_bootstrap  # noqa: F401
        import InstructionX_UIKit
        assert "InstructionX_UIKit" in sys.modules

    def test_bootstrap_appends_ui_dir_to_sys_path(self):
        """项目 ui/ 目录在 sys.path 中（顶层包解析依据）。"""
        import ui.uikit_bootstrap  # noqa: F401
        assert str(ui_dir := (PROJECT_ROOT / "ui")) in sys.path

    def test_top_level_module_is_library_copy(self):
        """顶层包解析到 ui/InstructionX_UIKit 库副本本体。"""
        import InstructionX_UIKit
        module_path = Path(InstructionX_UIKit.__file__).resolve()
        assert module_path.parent.parent.name == "ui"


class TestUIKitNewCapabilities:
    """alpha-v1.0.2 起既有能力的可导入性。"""

    def test_markdown_view_importable(self):
        """MarkdownView Markdown 渲染组件可导入。"""
        from InstructionX_UIKit.components import MarkdownView
        assert MarkdownView is not None

    def test_chat_conversation_importable(self):
        """chat_conversation 流式对话布局工厂可导入。"""
        from InstructionX_UIKit.layouts import create_chat_conversation
        assert callable(create_chat_conversation)

    def test_mermaid_subpackage_importable(self):
        """mermaid 子包可导入。"""
        from InstructionX_UIKit import mermaid
        assert mermaid is not None

    def test_size_mixin_importable(self):
        """SizeMixin 公共 API 可用。"""
        from InstructionX_UIKit.components._mixin import SizeMixin
        assert hasattr(SizeMixin, "set_size")
        assert hasattr(SizeMixin, "size_name")


class TestUIKitNewCapabilitiesV104:
    """alpha-v1.0.4 新增能力的可导入性与公开 API。"""

    def test_code_editor_subpackage_importable(self):
        """code_editor 子包导出主控件。"""
        from InstructionX_UIKit.code_editor import CodeEditor
        assert CodeEditor is not None

    def test_code_editor_lazy_diff_editor_export(self):
        """DiffEditor 为惰性导出，按需导入即可用。"""
        from InstructionX_UIKit.code_editor import DiffEditor
        assert DiffEditor is not None

    def test_charts_viewport_module_importable(self):
        """图表视口工厂可导入，不再暴露旧 GL 判定。"""
        from InstructionX_UIKit.charts import viewport
        assert callable(viewport.create_viewport)
        assert not hasattr(viewport, "gl_available")

    @pytest.mark.parametrize("module_name", [
        "canvas_factory", "canvas_item_viewport", "rhi_viewport",
        "data", "pyramid", "sampling", "stream", "viewport",
    ])
    def test_charts_new_modules_importable(self, module_name):
        """直接 Canvas、RHI、大数据与流式模块均可导入。"""
        import importlib
        module = importlib.import_module(f"InstructionX_UIKit.charts.{module_name}")
        assert module is not None

    def test_chart_widget_stream_and_cache_api(self):
        """ChartWidget 暴露流式入口与缓存失效公开 API。"""
        from InstructionX_UIKit.charts import ChartWidget
        assert callable(getattr(ChartWidget, "set_stream_data", None))
        assert callable(getattr(ChartWidget, "invalidate_all_caches", None))
        assert callable(getattr(ChartWidget, "invalidate_static_layer", None))

    def test_framework_chart_contracts_preserved(self):
        """框架依赖的月标签、字体和内置热力图契约仍然存在。"""
        from InstructionX_UIKit.charts import ChartWidget  # noqa: F401
        from InstructionX_UIKit.charts.axes import _MONTH_LABELS, chart_font
        from InstructionX_UIKit.charts.series_cartesian import HeatmapSeriesRenderer
        assert len(_MONTH_LABELS) == 12
        assert callable(chart_font)
        assert issubclass(HeatmapSeriesRenderer, object)

    def test_direct_canvas_and_new_components_importable(self):
        """直接 Canvas、预算滑块和完整 Iconoir 资产可用。"""
        from PySide6.QtCanvasPainter import QCanvasPainterWidget
        from InstructionX_UIKit.components import BudgetSliderGroup
        from InstructionX_UIKit.icons import ICONOIR_NAMES
        assert QCanvasPainterWidget is not None
        assert BudgetSliderGroup is not None
        assert len(ICONOIR_NAMES) == EXPECTED_ICONOIR_COUNT


class TestNoSubpackageImport:
    """框架代码禁止经 ui.InstructionX_UIKit 子包路径导入。"""

    def test_framework_sources_avoid_subpackage_import(self):
        """全部框架源文件不含 ui.InstructionX_UIKit 导入。"""
        offenders = []
        for path in _framework_sources():
            if not path.is_file():
                continue
            if _FORBIDDEN_IMPORT.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT_ROOT)))
        assert not offenders, (
            f"以下文件经 ui.InstructionX_UIKit 子包路径导入，"
            f"会破坏 ThemeManager 单例唯一性: {offenders}"
        )
