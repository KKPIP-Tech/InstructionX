"""UIKit 同步副本守卫测试。

覆盖点（对应 dev 分支「同步 InstructionX_UIKit 上游」提交，当前 alpha-v1.0.3）：

- 副本版本钉扎：``InstructionX_UIKit.__version__`` 为当前同步的上游版本
  （下次同步上游新版本时需同步更新 ``EXPECTED_UIKIT_VERSION``）；
- 导入引导契约：``ui.uikit_bootstrap`` 导入后 ``InstructionX_UIKit`` 以
  顶层包可导入，且项目 ``ui/`` 目录在 ``sys.path`` 中；
- 新增能力可用：MarkdownView 组件、chat_conversation 流式对话布局、
  mermaid 子包、SizeMixin（components/_mixin.py）均可导入；
- alpha-v1.0.3 新增能力可用：code_editor 子包（CodeEditor / DiffEditor）、
  图表 GL/软件双视口与大数据管线模块、流式入口与缓存失效公开 API；
- 单例唯一性防线：框架自身代码（core/、ui/（不含库副本）、utils/、
  workers/、main.py）禁止经 ``ui.InstructionX_UIKit`` 子包路径导入
  （该路径会创建第二份模块副本，破坏 ThemeManager 单例唯一性）。
"""

import re
import sys
from pathlib import Path

import pytest

#: 当前同步的上游 UIKit 版本（每次同步上游新版本时需同步更新本常量）
EXPECTED_UIKIT_VERSION = "alpha-v1.0.3"
#: 项目根目录（本文件位于 test/uikit/ 下）
PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: 禁止在框架代码中出现的子包导入模式（会生成第二份模块副本）
_FORBIDDEN_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+ui\.InstructionX_UIKit", re.MULTILINE
)
#: 参与扫描的框架代码路径（目录取 *.py 递归，文件单独列出）
_SCAN_DIRS = ("core", "utils", "workers")
_SCAN_FILES = ("main.py",)


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
    """alpha-v1.0.2 新增能力的可导入性。"""

    def test_markdown_view_importable(self):
        """MarkdownView Markdown 渲染组件可导入。"""
        from InstructionX_UIKit.components import MarkdownView
        assert MarkdownView is not None

    def test_chat_conversation_importable(self):
        """chat_conversation 流式对话布局工厂可导入。"""
        from InstructionX_UIKit.layouts import create_chat_conversation
        assert callable(create_chat_conversation)

    def test_mermaid_subpackage_importable(self):
        """mermaid 子包（WebEngine 渲染 + 自绘降级 + 交互查看器）可导入。"""
        from InstructionX_UIKit import mermaid
        assert mermaid is not None

    def test_size_mixin_importable(self):
        """SizeMixin（components/_mixin.py，尺寸档公共 API 抽取）可导入。"""
        from InstructionX_UIKit.components._mixin import SizeMixin
        assert hasattr(SizeMixin, "set_size")
        assert hasattr(SizeMixin, "size_name")


class TestUIKitNewCapabilitiesV103:
    """alpha-v1.0.3 新增能力的可导入性与公开 API（本次同步引入）。"""

    def test_code_editor_subpackage_importable(self):
        """code_editor 子包（仿 VS Code 编辑器）可导入且导出主控件。"""
        from InstructionX_UIKit.code_editor import CodeEditor
        assert CodeEditor is not None

    def test_code_editor_lazy_diff_editor_export(self):
        """DiffEditor 为惰性导出（PEP-562），按需导入即可用。"""
        from InstructionX_UIKit.code_editor import DiffEditor
        assert DiffEditor is not None

    def test_charts_viewport_module_importable(self):
        """图表 GL/软件双视口模块可导入，且暴露判定与工厂函数。"""
        from InstructionX_UIKit.charts.viewport import (
            create_viewport, gl_available,
        )
        assert callable(gl_available)
        assert callable(create_viewport)

    @pytest.mark.parametrize("module_name", [
        "data", "gl_series", "pyramid", "sampling", "stream", "viewport",
    ])
    def test_charts_new_modules_importable(self, module_name):
        """图表新增的大数据/流式/视口模块均可导入。"""
        import importlib
        module = importlib.import_module(f"InstructionX_UIKit.charts.{module_name}")
        assert module is not None

    def test_chart_widget_stream_and_cache_api(self):
        """ChartWidget 暴露流式入口与缓存失效公开 API（框架适配所依赖）。"""
        from InstructionX_UIKit.charts import ChartWidget
        assert callable(getattr(ChartWidget, "set_stream_data", None))
        assert callable(getattr(ChartWidget, "invalidate_all_caches", None))
        assert callable(getattr(ChartWidget, "invalidate_static_layer", None))

    def test_framework_chart_contracts_preserved(self):
        """框架依赖的图表契约在 1.0.3 中仍然存在（月标签常量/字体/热力图渲染器）。"""
        from InstructionX_UIKit.charts import ChartWidget  # noqa: F401
        from InstructionX_UIKit.charts.axes import _MONTH_LABELS, chart_font
        from InstructionX_UIKit.charts.series_cartesian import (
            HeatmapSeriesRenderer,
        )
        assert len(_MONTH_LABELS) == 12
        assert callable(chart_font)
        assert issubclass(HeatmapSeriesRenderer, object)


class TestNoSubpackageImport:
    """框架代码禁止经 ui.InstructionX_UIKit 子包路径导入（单例唯一性防线）。"""

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
