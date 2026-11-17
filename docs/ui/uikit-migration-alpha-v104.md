# UIKit alpha-v1.0.4 迁移与适配说明

## 1. 基线与范围

本次同步的上游为 `KKPIP-Tech/InstructionX_UIKit` 的 `main@e6e169a71ea8f89fa40f0a0340e02b4fc84ef756`，包版本 `alpha-v1.0.4`。框架只替换 `ui/InstructionX_UIKit/` 并修改框架自身的调用、依赖、脚本、测试和文档；`plugin/` 与 `custom_plugin/` 下的全部内容保持只读，未增加旧 UIKit 兼容 shim。

主要新能力与变化：

- 59 个组件，新增 `BudgetSliderGroup` / `BudgetSpec`；设计令牌、组件密度与全局 QSS 整体更新。
- 完整 Iconoir v7.12.1：1,383 个 Regular + 288 个 Solid，共 1,671 个 SVG；`get_icon` / `get_pixmap` / `icon_svg` / `search_icons` 只接受 Iconoir 原名。
- Chart 与 Blueprint 真实窗口默认 `QCanvasPainterWidget + QRhi`，Qt 自动选择 Direct3D 11 / Metal / Vulkan / OpenGL；显式 `rhi` 使用 `QQuickView + Scene Graph` 完整快照，`raster` 仅作软件参考。
- 旧 `QOpenGLWidget`、`gl_available()`、`gl_series.py`、VBO/GLSL、`UIKIT_CHART_GL`、`UIKIT_BLUEPRINT_GL` 和 GL 预热均已删除。
- 图表采样、流式原子提交、坐标映射和实时 Tooltip 修复：Tooltip 从原始数据取值，空 category 的实时流按隐式下标反查。
- 代码编辑器语言感知补全、Diff 对齐与选区/小地图修复；Markdown 流式局部更新和 Mermaid 实时 SVG 防重影修复。

## 2. 框架实际适配

### 2.1 启动与主窗口

- `main.py` 不再调用 `QQuickWindow.setGraphicsApi()` 强制 OpenGL。
- 新增 `ui/rhi_surface.py` 的 `prepare_rhi_surface(window)`：主窗口在窗口标志确定后、首次 `show()` 前匹配顶层 Surface，避免 Canvas/RHI 子控件触发可见窗口重建。
- 删除 `_prewarm_blueprint_viewport()` 及全部旧 GL 导入；预渲染九宫格窗口阴影保留。
- `scripts/smoke_uikit_canvas.py` 使用 Win32 客户区原生抓图。`QWidget.grab()` 不能覆盖原生 QQuickView 子窗口，不能作为 RHI 整窗验收依据；最终帧在 resize 预览和入场动画结束后捕获。

### 2.2 用量趋势图

`ui/usage_panel/trend_chart.py` 不再注册自定义 `calendarHeatmap`，改用内置 `heatmap`，以满足 Canvas 的精确类型检查。核心在全量构建时会把空系列名补成 `series0`，因此框架在每次 `set_option()` 后同步执行：

```python
renderer = self._chart.series_renderers[HEATMAP_SERIES_INDEX]
renderer.name = ""
renderer.opt["name"] = ""
```

这样命中结果的 `series` 为空，核心 Tooltip 回退到单元格日期；`set_stream_data()` 不重建渲染器，无需重复处理。全量/增量分流和 `invalidate_all_caches()` 保持不变。

### 2.3 依赖与许可

- `PySide6>=6.11.1`、`matplotlib>=3.11.1`，已同步 `pyproject.toml`、`requirements.txt` 与 `uv.lock`。
- Qt Canvas Painter 按上游选择 **GPL-3.0-only**，全文在 `licenses/QtCanvasPainter-GPL-3.0.txt`，不得误写为 LGPL。
- Iconoir 为 MIT；完整声明见 `licenses/InstructionX_UIKit-THIRD-PARTY.md` 与 `licenses/manifest.json`。

## 3. 后续插件迁移要求

本次没有修改任何插件。既有插件若引用旧 UIKit，应由各自后续任务处理：

1. 删除 `gl_available()`、GL 预热、`QOpenGLWidget` 与 `UIKIT_*_GL`，不再强制 OpenGL。
2. 图标改为 Iconoir 原名，经 `icon_names()` / `search_icons()` 查询，不依赖旧手绘名称。
3. 图表与蓝图优先使用内置系列和组件；自定义系列需检查 Canvas 的精确类型限制，分别验证 Canvas 与 RHI，不得静默接受回退。
4. 使用 `UIKIT_CHART_BACKEND` / `UIKIT_BLUEPRINT_BACKEND` 的 `canvas` / `rhi` / `raster` 选择后端，软件或离屏结果不得冒充真实性能。
5. 按新视觉基线复查亮暗主题、组件密度和布局，并更新插件实际验证过的框架版本声明。

本地 UI Demo 仍引用旧 `gl_available`，其加载失败属于已明确接受的本次范围外现象，未通过修改插件或上游库掩盖。

## 4. 严苛验收结果

| 验收项 | 标准 | 结果 |
|---|---|---|
| 同步一致性 | 固定上游 `.py` / `.qml` 内容与框架副本一致 | 通过 |
| 框架完整 pytest | `test` 分支全部测试通过 | **1351 passed，0 failed** |
| 定向适配测试 | RHI、同步、趋势与旧 GL 测试更新 | 51 passed |
| 静态契约与 i18n | 公开签名、语言完整性、框架更新与插件管理冒烟 | 通过；插件管理 74 项通过 |
| 上游独立测试 | 固定上游包源码对应的 95 个脚本全部退出 0 | **95/95 通过**，含 160 个页面状态 RGBA 零差异 |
| 默认真实后端 | Chart、Blueprint、TrendPanel 全部 `canvas-widget` | 通过 |
| 显式回退 | Chart、Blueprint、TrendPanel 全部 `rhi` | 通过 |
| 软件参考 | 三者全部 `_RasterViewport`，最终帧无黑带/空白 | 通过 |
| 趋势 Tooltip | 内置热力图命中后显示日期，不显示 `series0` | 通过 |
| 主程序端到端 | 真实 `main.py` 启动并执行统一关闭 | 通过 |
| 插件只读 | 两个插件目录哈希与迁移前一致 | `plugin/` 132 文件、`custom_plugin/` 1 文件，未变 |

截图与机器可读结果位于 `temp/uikit-{core,all}-{canvas,rhi,raster}.png` 及同名 `.json`。测试过程中修正的是抓图方式与测试夹具，未修改上游库来规避断言。

## 5. 性能证据与未通过项

同一物理 3840×2160 场景、每后端 10 秒短测用于发现回退与异常退化，不能替代正式验收：

- 直接 Canvas 约 43.52 FPS、P95 约 38ms，明显快于 RHI 快照；
- RHI 快照约 0.92–1.63 FPS，并有大量 UI 长任务；
- Canvas 仍未达到平均 FPS≥60、P95≤16.67ms 的正式门槛。

上游自己的 alpha-v1.0.4 验收记录同样未通过正式 4K 门禁，其短测约 53.69 FPS、P95 约 30.67ms，正式 5×60 秒和 PresentMon 未闭环。不同机器和窗口环境的数据不能直接用于证明迁移性能退化，但也不得宣称“上游或本框架已经稳定 4K 60 FPS”。

本次完成的是**最新默认直接 Canvas 路径的完整迁移与功能适配**，不是正式 4K 性能验收通过。

## 6. 提交边界

- `dev`：UIKit/依赖、RHI 初始化、趋势图、框架文档分别提交，不含测试代码。
- `test`：`test/ui_tests/` 与 `test/uikit/` 的适配测试单独提交。
- `plugin/`、`custom_plugin/`：零修改。
- `core/version.py`：未修改。
