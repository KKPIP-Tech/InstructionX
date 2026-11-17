# UIKit alpha-v1.0.4 迁移与直接 Canvas 适配 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将上游 `origin/main@e6e169a71ea8f89fa40f0a0340e02b4fc84ef756` 的 UIKit alpha-v1.0.4 完整同步到 InstructionX，并只修改框架，使框架直接使用最新默认 Canvas/RHI 实现。

**Architecture:** UIKit 副本保持与固定上游提交逐字节一致，框架适配放在 `ui/` 的独立模块中，不在库内增加兼容层或私有补丁。主窗口在窗口标志确定后、首次显示前匹配 RHI Surface；趋势图改用内置 `heatmap` 以进入直接 Canvas；`plugin/` 与 `custom_plugin/` 完全只读。

**Tech Stack:** Python 3.14、PySide6 6.11.1、`QCanvasPainterWidget`、QRhi、Qt Widgets、NumPy、pytest（仅 `test` 分支）、独立冒烟脚本（`dev` 分支）。

## Global Constraints

- 上游事实来源固定为 `e6e169a71ea8f89fa40f0a0340e02b4fc84ef756`，不能使用上游工作区中其他分支的未合并代码。
- 真实窗口默认使用 `QCanvasPainterWidget + QRhi`；不得强制 OpenGL，不得恢复 `QOpenGLWidget`、`gl_available()`、`gl_series.py`、`UIKIT_CHART_GL` 或 `UIKIT_BLUEPRINT_GL`。
- `UIKIT_CHART_BACKEND=rhi` / `UIKIT_BLUEPRINT_BACKEND=rhi` 只作为显式回退验证；`raster` 只作为软件参考，不冒充真实性能结果。
- `ui/InstructionX_UIKit/` 必须与固定上游提交一致；框架修复不得写入该目录。
- 最低运行依赖调整为 `PySide6>=6.11.1`、`matplotlib>=3.11.1`；`pyproject.toml` 与 `requirements.txt` 同步修改，随后更新 `uv.lock`。
- 不修改 `core/version.py`，不改变 `IPlugin`、`PluginServices`、DataProvider、LLM、MCP 等框架公共契约。破坏性变更限定在 UIKit 及框架调用方。
- **`plugin/` 与 `custom_plugin/` 下所有内容完全不动**：不修改源码、语言包、配置或插件文档，不新增插件测试，不做兼容 shim。本地示例插件可能因旧 UIKit 调用而失效，该已知边界由后续独立插件任务处理，不阻塞本次框架迁移，也不得为此改动上游库。
- 测试代码只允许进入 `test` 分支；`dev` 只提交框架源码和独立验证脚本。修改既有测试前，需向开发者说明目的并获得认可。
- 每个功能任务先在 `dev` 用失败冒烟验证、实现、复验，再按项目规则请求提交确认；随后同步到 `test` 分支补充/更新 pytest 并运行定向测试。
- 所有 `git commit`、`git merge` 等变更操作执行前均需用户确认；Commit 使用 `<type>(<scope>): <中文描述>`，自定义前缀另行询问。
- 临时归档、截图、性能日志和对比报告只写入 `temp/`；不触碰现有未跟踪的 `.mcp.json`、说明书和 PRD 文件。
- 性能目标是“使用上游当前默认且最新的直接 Canvas 路径”，不是承诺达到 60 FPS。上游真实 4K 门禁尚未通过，迁移报告必须保留这一事实。

## 文件结构

| 文件 | 动作与职责 |
|---|---|
| `ui/InstructionX_UIKit/` | 整体替换为固定上游 alpha-v1.0.4 包，不做本地修改 |
| `ui/rhi_surface.py` | 新增：将顶层 QWidget 的 Surface 匹配到 Qt 自动选择的 RHI API |
| `main.py` | 删除强制 OpenGL 启动逻辑 |
| `ui/main_window.py` | 删除旧 GL 预热，接入 `prepare_rhi_surface()` |
| `ui/usage_panel/trend_chart.py` | 改用内置 `heatmap`，保留日期 Tooltip 与增量渲染 |
| `plugin/`、`custom_plugin/` | **完全只读，不创建、修改或删除任何内容** |
| `scripts/smoke_uikit_sync.py` | 新增：版本、模块和图标资产的框架静态冒烟 |
| `scripts/smoke_uikit_canvas.py` | 新增：真实窗口 Chart / Blueprint / TrendPanel 后端与截图冒烟 |
| `pyproject.toml`、`requirements.txt`、`uv.lock` | 同步上游最低依赖 |
| `licenses/manifest.json` | 补充 Canvas Painter 与 Iconoir 许可信息，更新 PySide6 许可说明 |
| `licenses/InstructionX_UIKit-THIRD-PARTY.md` | 保存固定上游第三方声明 |
| `licenses/QtCanvasPainter-GPL-3.0.txt` | 保存 Qt Canvas Painter 所选 GPLv3 全文 |
| `test/uikit/test_uikit_sync.py`（`test` 分支） | 更新版本与 alpha-v1.0.4 模块契约 |
| `test/ui_tests/test_rhi_surface.py`（`test` 分支） | 新增 RHI Surface 映射及主窗口旧 GL 清理测试 |
| `test/ui_tests/usage_panel/test_trend_chart_render.py`（`test` 分支） | 更新内置 heatmap 断言并覆盖 Tooltip 与渲染器类型 |
| `docs/ui/uikit-migration-alpha-v104.md` | 新增框架迁移记录与第三方插件升级指导，不修改插件本身 |
| `docs/utils/uikit-theme.md`、`docs/ui/main-window.md`、`docs/architecture/overview.md` | 更新实际后端、依赖和初始化流程 |
| `README.md`、`README_EN.md`、`README_FR.md`、`README_RU.md`、`AGENTS.md`、`AGENTS-for-PLUGIN-DEV.md`、`Plugin-Development-Guide.md` | 更新 59 组件、alpha-v1.0.4、Canvas/RHI、依赖与插件迁移指导 |

## 分支与验证工作流

每个 Task 2–3 按以下顺序执行，避免测试代码进入 `dev`：

1. 在 `dev` 新建或运行会失败的冒烟，确认失败原因正是待适配行为。
2. 完成最小实现，运行同一冒烟及相邻既有脚本直至通过。
3. 请求提交确认并提交 `dev`。
4. 请求分支/合并确认，切换 `test` 并合并当前 `dev`。
5. 在 `test` 分支写入本任务列出的 pytest；修改既有测试前单独取得认可。
6. 运行定向测试和规定的全量测试，请求确认后提交测试；切回 `dev` 继续下一任务。

---

### Task 0: 固定基线与上游快照

**Files:**
- Create（临时）: `temp/uikit-alpha-v1.0.4.tar`
- Create（临时）: `temp/uikit-alpha-v1.0.4/InstructionX_UIKit/`

**Interfaces:**
- Consumes: 上游 `origin/main@e6e169a`。
- Produces: 后续唯一用于复制的干净上游目录。

- [ ] **Step 1: 核对两个仓库状态，不清理用户文件**

```bash
git status --short --branch
git -C "C:/Users/fuwa1/Documents/Project/InstructionX_UIKit" status --short --branch
git -C "C:/Users/fuwa1/Documents/Project/InstructionX_UIKit" ls-remote origin refs/heads/main
```

Expected: InstructionX 在 `dev`；远端 `main` 为 `e6e169a71ea8f89fa40f0a0340e02b4fc84ef756`；已有未跟踪文件原样保留。

- [ ] **Step 2: 记录当前测试基线**

```bash
.venv/Scripts/python.exe -m pytest test/ -q --tb=short -p no:cacheprovider
.venv/Scripts/python.exe scripts/validate_plugin_contracts.py --quick --output temp/uikit-migration/baseline-contracts.json
.venv/Scripts/python.exe scripts/check_i18n_completeness.py
```

Expected: 三条命令均退出 0。若已有失败，记录为基线问题，不在本迁移中顺手修复。

- [ ] **Step 3: 从固定提交导出，而非复制上游工作区**

```bash
mkdir -p temp/uikit-alpha-v1.0.4
git -C "C:/Users/fuwa1/Documents/Project/InstructionX_UIKit" archive --format=tar --output="C:/Users/fuwa1/Documents/Project/InstructionX/temp/uikit-alpha-v1.0.4.tar" e6e169a71ea8f89fa40f0a0340e02b4fc84ef756 InstructionX_UIKit THIRD-PARTY.md
tar -xf temp/uikit-alpha-v1.0.4.tar -C temp/uikit-alpha-v1.0.4
```

Expected: `temp/uikit-alpha-v1.0.4/InstructionX_UIKit/__init__.py` 与 `temp/uikit-alpha-v1.0.4/THIRD-PARTY.md` 存在。

- [ ] **Step 4: 验证当前环境具备直接 Canvas 前置能力**

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -B -c "import PySide6; from PySide6.QtCanvasPainter import QCanvasPainterWidget; print(PySide6.__version__, QCanvasPainterWidget.__name__)"
```

Expected: 输出 `6.11.1 QCanvasPainterWidget`。若导入失败，停止迁移并先修复 PySide6 环境，不回退到旧 GL。

---

### Task 1: 同步 UIKit、依赖与第三方许可

**Files:**
- Replace: `ui/InstructionX_UIKit/`
- Create: `scripts/smoke_uikit_sync.py`
- Modify: `pyproject.toml:12-25`
- Modify: `requirements.txt:4-13`
- Modify: `uv.lock`
- Modify: `licenses/manifest.json`
- Create: `licenses/InstructionX_UIKit-THIRD-PARTY.md`
- Create: `licenses/QtCanvasPainter-GPL-3.0.txt`
- Test（仅 `test` 分支）: `test/uikit/test_uikit_sync.py`

**Interfaces:**
- Consumes: Task 0 的固定上游目录。
- Produces: `InstructionX_UIKit.__version__ == "alpha-v1.0.4"`、可导入的 `PySide6.QtCanvasPainter.QCanvasPainterWidget`、完整第三方声明。

- [ ] **Step 1: 先创建同步守卫并确认旧版本失败**

创建 `scripts/smoke_uikit_sync.py`：

```python
"""UIKit alpha-v1.0.4 同步副本的框架无网冒烟。"""
import importlib

import ui.uikit_bootstrap  # noqa: F401

EXPECTED_VERSION = "alpha-v1.0.4"
REQUIRED_MODULES = (
    "InstructionX_UIKit.charts.canvas_factory",
    "InstructionX_UIKit.charts.canvas_item_viewport",
    "InstructionX_UIKit.charts.rhi_viewport",
    "InstructionX_UIKit.blueprint.canvas_viewport",
    "InstructionX_UIKit.code_editor.completion",
)
REQUIRED_ICONS = ("home", "component", "stats-report", "view-grid", "play", "settings")


def check_library() -> None:
    """校验版本、直接 Canvas 模块和图标资产。"""
    import InstructionX_UIKit
    from InstructionX_UIKit.components import BudgetSliderGroup
    from InstructionX_UIKit.icons import ICONOIR_NAMES, icon_svg
    from PySide6.QtCanvasPainter import QCanvasPainterWidget

    assert InstructionX_UIKit.__version__ == EXPECTED_VERSION
    assert BudgetSliderGroup is not None
    assert QCanvasPainterWidget is not None
    assert len(ICONOIR_NAMES) == 1671
    for module_name in REQUIRED_MODULES:
        assert importlib.import_module(module_name) is not None
    for icon_name in REQUIRED_ICONS:
        assert "<svg" in icon_svg(icon_name)


def main() -> int:
    """执行框架库静态检查。"""
    check_library()
    print("UIKit 同步冒烟：PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `.venv/Scripts/python.exe scripts/smoke_uikit_sync.py`
Expected: FAIL，版本仍为 `alpha-v1.0.3`。

- [ ] **Step 2: 完整替换同步副本**

```bash
.venv/Scripts/python.exe - <<'PY'
from pathlib import Path
import shutil
source = Path("temp/uikit-alpha-v1.0.4/InstructionX_UIKit")
target = Path("ui/InstructionX_UIKit")
assert source.is_dir()
shutil.rmtree(target)
shutil.copytree(source, target)
PY
```

Expected: 目标包存在且没有旧 `charts/gl_series.py`、旧 `__pycache__` 或框架私有补丁。

- [ ] **Step 3: 更新依赖并重新锁定**

将 `pyproject.toml` 与 `requirements.txt` 中两行同步改为：

```toml
"PySide6>=6.11.1",
"matplotlib>=3.11.1",
```

`requirements.txt` 使用无引号形式：

```text
PySide6>=6.11.1
matplotlib>=3.11.1
```

Run:

```bash
uv lock
uv pip install -r requirements.txt
.venv/Scripts/python.exe scripts/smoke_uikit_sync.py
```

Expected: 锁定 PySide6 6.11.1 或兼容的更高版本；冒烟输出 `UIKit 同步冒烟：PASS`。

- [ ] **Step 4: 同步第三方许可**

将 `temp/uikit-alpha-v1.0.4/THIRD-PARTY.md` 复制为 `licenses/InstructionX_UIKit-THIRD-PARTY.md`。在 `licenses/manifest.json`：

- 将 PySide6 的 `version` 改为 `>=6.11.1`，`license_type` 改为 `LGPL-3.0 / GPL-3.0 / 商业许可（按 Qt 模块）`。
- 新增 `Qt Canvas Painter`：`version=6.11.1`、`license_type=GPL-3.0-only`、`license_file=licenses/QtCanvasPainter-GPL-3.0.txt`、来源 `https://doc.qt.io/qt-6/qtcanvaspainter-module.html`。
- 新增 `Iconoir`：`version=v7.12.1`、`license_type=MIT`、`license_file=licenses/InstructionX_UIKit-THIRD-PARTY.md`、来源 `https://github.com/iconoir-icons/iconoir`。
- 使用 GNU 官方 `https://www.gnu.org/licenses/gpl-3.0.txt` 保存 GPL 全文，不将 Canvas Painter 误写为 LGPL。

Run: `.venv/Scripts/python.exe -c "import json; json.load(open('licenses/manifest.json', encoding='utf-8')); print('manifest PASS')"`
Expected: 输出 `manifest PASS`。

- [ ] **Step 5: 在 test 分支更新既有同步守卫**

先说明：旧测试仍断言 alpha-v1.0.3、`gl_available` 和 `gl_series`，必须与删除的旧 API 同步。取得认可后：

- `EXPECTED_UIKIT_VERSION` 改为 `alpha-v1.0.4`。
- `test_charts_viewport_module_importable` 只导入并断言 `create_viewport`，不再导入 `gl_available`。
- 图表模块参数改为 `canvas_factory`、`canvas_item_viewport`、`rhi_viewport`、`data`、`pyramid`、`sampling`、`stream`、`viewport`。
- 新增以下完整测试：

```python
def test_direct_canvas_and_new_components_importable():
    """alpha-v1.0.4 直接 Canvas、预算滑块和 Iconoir 资产可用。"""
    from PySide6.QtCanvasPainter import QCanvasPainterWidget
    from InstructionX_UIKit.components import BudgetSliderGroup
    from InstructionX_UIKit.icons import ICONOIR_NAMES
    assert QCanvasPainterWidget is not None
    assert BudgetSliderGroup is not None
    assert len(ICONOIR_NAMES) == 1671
```

Run: `.venv/Scripts/python.exe -m pytest test/uikit/test_uikit_sync.py -q --tb=short -p no:cacheprovider`
Expected: PASS，且没有引用 `gl_available` / `gl_series` 的失败。

- [ ] **Step 6: 请求确认并分别提交源码与测试**

```bash
git add ui/InstructionX_UIKit scripts/smoke_uikit_sync.py pyproject.toml requirements.txt uv.lock licenses
# 经确认后在 dev 提交：feat(ui): 同步 UIKit alpha-v1.0.4 与运行依赖
# 经确认后在 test 提交：test(ui): 更新 UIKit alpha-v1.0.4 同步契约
```

---

### Task 2: 主窗口与启动入口适配 RHI Surface

**Files:**
- Create: `ui/rhi_surface.py`
- Modify: `main.py:10-14,33-40`
- Modify: `ui/main_window.py:61-65,191-245,249-254,537-558`
- Create: `scripts/smoke_uikit_canvas.py`
- Test（仅 `test` 分支）: `test/ui_tests/test_rhi_surface.py`

**Interfaces:**
- Consumes: `QQuickWindow.graphicsApi()` 的平台自动选择结果。
- Produces: `prepare_rhi_surface(window: QWidget) -> None`；`active_backend() == "canvas-widget"` 的 Chart 与 Blueprint 真实视口。

- [ ] **Step 1: 编写 RHI Surface 模块**

```python
"""顶层窗口 RHI Surface 匹配，避免可见窗口被后续重型视口重建。"""
from PySide6.QtGui import QGuiApplication, QSurface
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtWidgets import QWidget

_SOFTWARE_PLATFORMS = ("offscreen", "minimal", "minimalegl")
_SURFACE_BY_API = {
    QSGRendererInterface.GraphicsApi.Direct3D11: QSurface.Direct3DSurface,
    QSGRendererInterface.GraphicsApi.Vulkan: QSurface.VulkanSurface,
    QSGRendererInterface.GraphicsApi.Metal: QSurface.MetalSurface,
    QSGRendererInterface.GraphicsApi.OpenGL: QSurface.OpenGLSurface,
}


def prepare_rhi_surface(window: QWidget) -> None:
    """在窗口标志确定后、show 前匹配 Surface；软件平台为空操作。

    Args:
        window: 尚未首次显示的顶层窗口。
    """
    app = QGuiApplication.instance()
    if app is None or app.platformName() in _SOFTWARE_PLATFORMS:
        return
    surface = _SURFACE_BY_API.get(QQuickWindow.graphicsApi())
    if surface is None:
        return
    window.winId()
    handle = window.windowHandle()
    if handle is not None and handle.surfaceType() != surface:
        handle.setSurfaceType(surface)
```

- [ ] **Step 2: 创建真实后端冒烟，核心场景先验证 Chart 与 Blueprint**

`scripts/smoke_uikit_canvas.py` 使用 `--scope core|all` 与 `--backend canvas|rhi|raster`。核心结构如下（完整实现应保持这些公开检查，不添加跳过后端断言）：

```python
"""真实窗口 UIKit 后端冒烟；不使用 offscreen 结果冒充真实呈现。"""
import argparse
import os
from pathlib import Path

import ui.uikit_bootstrap  # noqa: F401
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from InstructionX_UIKit.blueprint import BlueprintCanvas, BlueprintGraph
from InstructionX_UIKit.charts import ChartWidget
from ui.rhi_surface import prepare_rhi_surface
from ui.usage_panel.trend_chart import TrendPanel


def make_line_chart() -> ChartWidget:
    """构造完成态折线图。"""
    chart = ChartWidget()
    chart.set_option({
        "xAxis": {"type": "category", "data": ["A", "B", "C"]},
        "series": [{"type": "line", "name": "信号", "data": [1, 3, 2]}],
    })
    chart.anim.stop()
    chart.anim.set_progress(1.0)
    return chart


def sync_viewport(owner) -> None:
    """强制同步 Chart 或 Blueprint 的内部视口并处理 Qt 事件。"""
    owner._viewport._sync_now()
    QApplication.processEvents()


def main() -> int:
    """检查真实后端并保存窗口截图到 temp。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("core", "all"), default="core")
    parser.add_argument("--backend", choices=("canvas", "rhi", "raster"), default="canvas")
    args = parser.parse_args()
    os.environ["UIKIT_CHART_BACKEND"] = args.backend
    os.environ["UIKIT_BLUEPRINT_BACKEND"] = args.backend
    app = QApplication([])
    window = QWidget()
    window.setWindowFlag(Qt.FramelessWindowHint, True)
    prepare_rhi_surface(window)
    layout = QVBoxLayout(window)
    chart = make_line_chart()
    blueprint = BlueprintCanvas(BlueprintGraph())
    owners = [chart, blueprint]
    layout.addWidget(chart)
    layout.addWidget(blueprint)
    if args.scope == "all":
        trend = TrendPanel()
        trend.update_series([])
        layout.addWidget(trend)
        owners.append(trend._chart)
    window.resize(1000, 800)
    window.show()
    app.processEvents()
    for owner in owners:
        sync_viewport(owner)
    for owner in owners:
        viewport = owner._viewport
        if args.backend == "raster":
            assert type(viewport).__name__ == "_RasterViewport"
        else:
            expected = "canvas-widget" if args.backend == "canvas" else "rhi"
            assert viewport.active_backend() == expected
    output = Path("temp") / f"uikit-{args.scope}-{args.backend}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    assert window.grab().save(str(output))
    window.close()
    app.processEvents()
    print(f"真实后端冒烟：PASS；截图：{output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Run: `.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope core --backend canvas`
Expected: 修改 `main.py` 前该冒烟本身可评估库后端，但完整应用仍包含旧 GL 导入；不得据此跳过下一步。

- [ ] **Step 3: 删除强制 OpenGL 与旧预热**

`main.py` 删除：

```python
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
```

`ui/main_window.py` 删除 `BlueprintCanvas`、`BlueprintGraph`、`gl_available` 导入，以及 `_prewarm_blueprint_viewport()` 的调用和完整方法。新增：

```python
from ui.rhi_surface import prepare_rhi_surface
```

在 `super().__init__()` 后先完成现有 `setWindowFlags()` 与 `WA_TranslucentBackground` 设置，紧接着调用：

```python
prepare_rhi_surface(self)
```

调用必须位于 `setMinimumSize()`、插件加载和 `show()` 之前，确保后续窗口标志不会再次重建已匹配的句柄。阴影仍保留预渲染九宫格方案，注释改为“硬件加速视口”，不得继续宣称当前使用 `QOpenGLWidget`。

- [ ] **Step 4: 运行核心与显式回退验证**

```bash
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope core --backend canvas
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope core --backend rhi
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope core --backend raster
```

Expected: 三者均 PASS；Canvas 为 `canvas-widget`，RHI 为 `rhi`，Raster 为 `_RasterViewport`；截图非空白、无黑帧和明显错位。

- [ ] **Step 5: 在 test 分支增加 Surface 单测**

```python
"""RHI Surface 匹配与旧 GL 清理测试。"""
from pathlib import Path
from PySide6.QtGui import QSurface
from PySide6.QtQuick import QSGRendererInterface

from ui.rhi_surface import prepare_rhi_surface


def test_software_platform_is_noop(mocker):
    """offscreen 不创建原生句柄。"""
    app = mocker.MagicMock()
    app.platformName.return_value = "offscreen"
    mocker.patch("ui.rhi_surface.QGuiApplication.instance", return_value=app)
    window = mocker.MagicMock()
    prepare_rhi_surface(window)
    window.winId.assert_not_called()


def test_d3d11_surface_is_selected_before_show(mocker):
    """Qt 自动选择 D3D11 时顶层 Surface 同步为 Direct3DSurface。"""
    app = mocker.MagicMock()
    app.platformName.return_value = "windows"
    mocker.patch("ui.rhi_surface.QGuiApplication.instance", return_value=app)
    mocker.patch(
        "ui.rhi_surface.QQuickWindow.graphicsApi",
        return_value=QSGRendererInterface.GraphicsApi.Direct3D11,
    )
    window = mocker.MagicMock()
    handle = window.windowHandle.return_value
    handle.surfaceType.return_value = QSurface.OpenGLSurface
    prepare_rhi_surface(window)
    window.winId.assert_called_once_with()
    handle.setSurfaceType.assert_called_once_with(QSurface.Direct3DSurface)


def test_framework_has_no_legacy_gl_entrypoints():
    """框架入口不再强制 OpenGL 或引用已删除的 gl_available。"""
    main_source = Path("main.py").read_text(encoding="utf-8")
    window_source = Path("ui/main_window.py").read_text(encoding="utf-8")
    assert "setGraphicsApi" not in main_source
    assert "gl_available" not in window_source
    assert "_prewarm_blueprint_viewport" not in window_source
```

Run: `.venv/Scripts/python.exe -m pytest test/ui_tests/test_rhi_surface.py test/ui_tests/test_main_window.py -q --tb=short -p no:cacheprovider`
Expected: PASS。

- [ ] **Step 6: 请求确认并分别提交**

`dev`: `fix(ui): 适配直接 Canvas 的 RHI 窗口初始化`；`test`: `test(ui): 增加 RHI Surface 与旧 GL 清理回归`。

---

### Task 3: 用量趋势图进入直接 Canvas

**Files:**
- Modify: `ui/usage_panel/trend_chart.py:22-48,311-381`
- Test（仅 `test` 分支）: `test/ui_tests/usage_panel/test_trend_chart_render.py`

**Interfaces:**
- Consumes: 内置 `HeatmapSeriesRenderer` 的 `hit_test()` 与核心 `_tooltip_item()` 的 `series or name` 回退。
- Produces: 类型精确为 `HeatmapSeriesRenderer` 的趋势系列、`canvas-widget` 后端、仍显示日期的 Tooltip。

- [ ] **Step 1: 先证明自定义子类不能留在直接 Canvas**

Run: `.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend canvas`
Expected: FAIL；趋势图 `_CalendarHeatmapRenderer` 不满足上游 `type(renderer) is HeatmapSeriesRenderer`，回退为 `rhi`。

- [ ] **Step 2: 删除自定义系列，使用内置 heatmap**

从 `trend_chart.py` 删除：

- `register_series` 与 `HeatmapSeriesRenderer` 导入。
- `_CalendarHeatmapRenderer` 类及 `register_series("calendarHeatmap", _CalendarHeatmapRenderer)`。
- 顶部关于“自定义系列”的过期注释。

`_render_full()` 的系列改为：

```python
"series": [{
    "type": "heatmap",
    "name": "",
    "coordinateSystem": "calendar",
    "data": series_data,
}],
```

保留 `_render_key` 中的 `metric_idx`、全量/增量分流和 `invalidate_all_caches()`。核心在全量构建时会把空系列名补成 `series0`，因此 `set_option()` 后还必须同步执行：

```python
renderer = self._chart.series_renderers[HEATMAP_SERIES_INDEX]
renderer.name = ""
renderer.opt["name"] = ""
```

这样内置命中结果的 `series=""`，核心 Tooltip 按 `hit.get("series") or hit.get("name")` 显示日期，与原自定义子类行为一致；增量入口不重建渲染器，无需重复清除。更新 `_render_series()`、`_push_series_data()`、`_render_full()` 中 alpha-v1.0.3 和“系列名随指标变化”的旧注释为 alpha-v1.0.4 当前语义。

- [ ] **Step 3: 复验直接 Canvas、回退和软件参考**

```bash
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend canvas
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend rhi
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend raster
```

Expected: 全部 PASS；默认趋势图与折线图均为 `canvas-widget`，日期 Tooltip 仍可用，区间切换月份标签正确。

- [ ] **Step 4: 更新既有趋势测试**

先说明：旧测试把 `calendarHeatmap` 和本地化系列名当作实现契约，但本任务为实现直接 Canvas 改用内置系列，断言需要同步。取得认可后：

- `test_cross_year_range_option_payload` 断言 `series["type"] == "heatmap"`、`series["name"] == ""`，其余 range/data 断言不变。
- 保留全量/增量、缓存失效、单日、跨年、无记录和视觉回归测试，不删除既有断言场景。
- 新增：

```python
def test_builtin_heatmap_preserves_date_hit_and_canvas_type(qtbot):
    """内置热力图保留日期命中，且类型满足直接 Canvas 精确检查。"""
    from InstructionX_UIKit.charts.series_cartesian import HeatmapSeriesRenderer
    panel = _make_panel(qtbot)
    points = _points(RANGE_A_START)
    panel._render_series(points, 0)
    panel._chart._layout_all(force=True)
    renderer = panel._chart._series[HEATMAP_SERIES_INDEX]
    assert type(renderer) is HeatmapSeriesRenderer
    cell = renderer._cells[0]
    hit = renderer.hit_test(cell["rect"].center())
    assert hit is not None
    assert hit["series"] == ""
    assert hit["name"] == points[0][0].isoformat()
```

Run: `.venv/Scripts/python.exe -m pytest test/ui_tests/usage_panel/test_trend_chart_render.py -q --tb=short -p no:cacheprovider`
Expected: PASS，视觉测试不是空白截图假通过。

- [ ] **Step 5: 请求确认并分别提交**

`dev`: `fix(ui): 让用量趋势图使用内置热力图直接 Canvas`；`test`: `test(ui): 覆盖趋势图直接 Canvas 与日期命中`。

---

### Task 4: 全量回归、真实性能证据与文档交付

**Files:**
- Create: `docs/ui/uikit-migration-alpha-v104.md`
- Modify: `docs/utils/uikit-theme.md`
- Modify: `docs/ui/main-window.md`
- Modify: `docs/architecture/overview.md`
- Modify: `README.md`、`README_EN.md`、`README_FR.md`、`README_RU.md`、`AGENTS.md`、`AGENTS-for-PLUGIN-DEV.md`、`Plugin-Development-Guide.md`
- Create（临时）: `temp/uikit-migration/` 下截图、JSON 与性能记录

**Interfaces:**
- Consumes: Task 1–3 的全部实现与测试。
- Produces: 可复核的框架迁移验收证据、最新架构文档和面向后续插件任务的升级说明。

- [ ] **Step 1: 运行框架完整自动化回归**

在 `test` 分支、当前合并后的源码上运行：

```bash
.venv/Scripts/python.exe -m pytest test/ -q --tb=short -p no:cacheprovider
.venv/Scripts/python.exe scripts/check_i18n_completeness.py
.venv/Scripts/python.exe scripts/validate_plugin_contracts.py --quick --output temp/uikit-migration/final-contracts.json
.venv/Scripts/python.exe scripts/smoke_framework_update.py
.venv/Scripts/python.exe scripts/smoke_plugin_management.py
```

Expected: 框架测试全部 PASS；不得通过删除旧测试场景获得通过。`plugin/` 下的旧示例插件不参与本次迁移验收，若其旧 UIKit 调用产生错误，记录为明确接受的范围外问题，不得通过修改插件或上游库消除。

- [ ] **Step 2: 运行上游固定源码的功能回归**

确认上游 `test` 工作区的包源码与固定提交一致：

```bash
git -C "C:/Users/fuwa1/Documents/Project/InstructionX_UIKit" diff --quiet e6e169a71ea8f89fa40f0a0340e02b4fc84ef756..test -- InstructionX_UIKit
```

在上游仓库运行其独立脚本全量回归（真实 Qt 字体路径按上游约定设置）：

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QPA_FONTDIR = "C:\Windows\Fonts"
Get-ChildItem tests\test_*.py | ForEach-Object {
    & .venv\Scripts\python.exe $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "FAIL $($_.Name)" }
}
```

Expected: 全部退出 0。该结果证明上游库功能，不替代 InstructionX 真实窗口验证。

- [ ] **Step 3: 验证真实主程序和框架重型界面**

```bash
.venv/Scripts/python.exe scripts/smoke_uikit_sync.py
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend canvas
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend rhi
.venv/Scripts/python.exe scripts/smoke_uikit_canvas.py --scope all --backend raster
.venv/Scripts/python.exe main.py
```

手工验收并记录：

- 主窗口首次显示、框架内 Chart / Blueprint / Mermaid 测试界面没有黑帧、明显闪烁或顶层窗口重建。
- 用量面板默认 Canvas、日期 Tooltip、指标/区间切换和增量刷新正常。
- light/dark/auto 切换、LLM 设置、插件管理、关闭确认和托盘退出正常。
- 框架路径没有 `Failed to get a QRhi`、`gl_available`、未知图标或 Canvas 缺失能力错误；本地示例插件的旧 API 错误只记录为范围外现象，不修改插件。

- [ ] **Step 4: 进行同场景短测，不冒充正式性能验收**

在上游 `test` 工作区用其交互启动器分别运行 Canvas 与 RHI 的相同场景：

```powershell
.\tests\perf\run_interactive.ps1 tests\perf\run_realtime.py 180 migration-canvas -- --backend canvas --seconds 10 --rounds 1 --warmup 2 --only complex --tag migration-canvas
.\tests\perf\run_interactive.ps1 tests\perf\run_realtime.py 180 migration-rhi -- --backend rhi --seconds 10 --rounds 1 --warmup 2 --only complex --tag migration-rhi
```

将两次摘要复制到 `temp/uikit-migration/` 并记录平均 FPS、P95/P99、长任务、实际图形 API、源码 SHA 和窗口物理尺寸。该短测只用于发现异常回退或明显性能退化；不得写成通过正式 4K 门禁，也不得因单次结果擅自改回 RHI。正式 5×60 秒与 PresentMon 仍按上游未闭环状态记录。

- [ ] **Step 5: 更新文档与第三方插件迁移说明**

`docs/ui/uikit-migration-alpha-v104.md` 必须包含：

- 固定上游 SHA、59 组件、1,671 个 Iconoir 图标、直接 Canvas / 显式 RHI / raster 三路径。
- 删除项：`gl_available()`、`gl_series.py`、`QOpenGLWidget`、`UIKIT_CHART_GL`、`UIKIT_BLUEPRINT_GL` 和强制 OpenGL 启动。
- 新环境变量：`UIKIT_CHART_BACKEND`、`UIKIT_BLUEPRINT_BACKEND`，取值为 `canvas` / `rhi` / `raster`。
- 第三方插件需要的动作：删除 GL 探测与预热、图标改为 Iconoir 原名、检查自定义系列的 Canvas 精确类型限制、升级 PySide6 至 6.11.1。
- 本框架趋势图使用内置 `heatmap` 与空系列名保留日期 Tooltip 的示例。
- 许可变化：Qt Canvas Painter 选择 GPLv3；Iconoir MIT 声明位置。
- 验收结果与限制：区分自动化通过、真实窗口通过、短测数据和上游未通过的正式 4K 门禁。

同步更新其他文档中的 `alpha-v1.0.3`、`58 个组件`、`GL/软件双视口`、强制 OpenGL、GL 预热和 `PySide6>=6.10`；版本号 `core/version.py` 不变。根目录三份文档必须分别完成以下更新，不能只添加版本号：

- **`AGENTS.md`**：
  - 项目概述与技术栈改为 59 组件、alpha-v1.0.4、`PySide6>=6.11.1`、`matplotlib>=3.11.1`。
  - `ui/` 目录树增加 `rhi_surface.py`；UIKit 结构改为默认直接 Canvas、显式 RHI 回退和 offscreen/raster 软件参考，补充 Canvas、流式数据、Iconoir 与代码补全新模块。
  - 「核心设计约定」删除蓝图 GL 预热和图表 GL 视口两条，改写为 `prepare_rhi_surface()` 的调用顺序，以及 Chart / Blueprint / TrendPanel 的后端与回退约定。
  - 独立脚本清单加入 `smoke_uikit_sync.py` 与 `smoke_uikit_canvas.py`，文档地图加入 `docs/ui/uikit-migration-alpha-v104.md`。
  - 保留 `IPlugin`、`PluginServices` 等核心接口的向后兼容要求，单独注明“alpha-v1.0.4 是用户批准的 UIKit 破坏性升级例外；旧 UIKit 插件必须按迁移指南适配，不增加兼容 shim”，避免与现有兼容策略混为一谈。
- **`AGENTS-for-PLUGIN-DEV.md`**：
  - 增加“UIKit alpha-v1.0.4 基线与迁移”小节，明确 `PySide6>=6.11.1`、默认 Canvas、禁止旧 GL 探测/预热和强制 OpenGL、图标仅使用 Iconoir 原名、新后端环境变量及自定义系列精确类型限制。
  - 要求涉及图表或蓝图的插件优先使用内置系列/组件；自定义系列必须分别验证 Canvas 与 RHI，不得静默接受性能回退。
  - 「框架文档阅读清单」的 UIKit 主题文档后新增 `docs/ui/uikit-migration-alpha-v104.md`，涉及 UI 的既有插件升级为必读。
  - 保留插件自身 `service_api`、发布订阅 key 和配置语义的兼容要求，明确本次不兼容的是旧 UIKit 调用，不是允许随意破坏插件自己的公开业务接口。
- **`Plugin-Development-Guide.md`**：
  - Part 1 明确当前环境为 Python 3.14.x、PySide6 6.11.1+。
  - Part 4 增加英文 UIKit alpha-v1.0.4 说明与 `docs/ui/uikit-migration-alpha-v104.md` 链接，说明默认直接 Canvas、RHI 回退、Iconoir 原名以及旧 GL API 已删除，引导既有插件先阅读迁移指南。
  - 保持英文文档原有写作风格和入口定位，不复制整份中文规范。

- [ ] **Step 6: 交叉验证并请求最终提交**

```bash
git diff --no-index --ignore-cr-at-eol -- ui/InstructionX_UIKit temp/uikit-alpha-v1.0.4/InstructionX_UIKit
git status --short
```

Expected: 第一条无输出（退出 1 仅表示常规差异；此处必须无差异），第二条只包含本任务文件及用户原有未跟踪文件。确认没有测试输出、归档、截图或 `__pycache__` 被纳入提交。

`dev`: `docs(ui): 更新 UIKit alpha-v1.0.4 迁移与验证说明`。若测试文件在最终回归中仍有修正，`test` 单独提交对应测试，不混入 `dev`。

## 完成判定

只有同时满足以下条件才可宣称迁移完成：

- 内置 UIKit 与固定上游提交无差异，版本为 alpha-v1.0.4。
- 主程序和框架调用点不再引用旧 GL API 或旧图标名。
- 默认真实 Chart、Blueprint、TrendPanel 均为 `canvas-widget`；显式 RHI 和 raster 回退也验证通过。
- 主窗口无强制 OpenGL，RHI Surface 在窗口标志确定后、首次显示前完成匹配。
- 框架自动化、i18n、静态契约与真实框架窗口交互全部通过，测试代码仅在 `test` 分支。
- `plugin/` 与 `custom_plugin/` 下没有任何文件被创建、修改或删除；旧示例插件问题已记录为范围外，不以此阻塞框架验收。
- 依赖与许可文件同步，文档准确描述实际行为及性能限制。
- 根目录 `AGENTS.md`、`AGENTS-for-PLUGIN-DEV.md`、`Plugin-Development-Guide.md` 均已同步最新 UIKit 基线、插件迁移规则和文档链接，不再含旧 GL 或旧版本指导。
- 没有将“使用最新默认 Canvas”误述为“正式 4K 60 FPS 验收通过”。

## Self-Review

- **需求覆盖：** 固定最新上游、完整同步、仅框架适配、插件目录只读、默认 Canvas、依赖许可、测试、根目录三份规范/指南及其他文档分别由 Task 1–4 覆盖。
- **可行性：** 当前环境已确认 PySide6 6.11.1 与 `QCanvasPainterWidget` 可导入；趋势图利用现有内置命中与 Tooltip 回退，无需修改上游库；Surface 调整顺序避免了后续窗口标志造成的句柄重建。
- **无占位：** 所有代码替换点、测试文件、命令、预期结果、提交边界和性能证据口径均已明确。
- **类型一致：** `prepare_rhi_surface(QWidget) -> None`、内置 `HeatmapSeriesRenderer`、`active_backend() == "canvas-widget"` 与上游实现一致。
