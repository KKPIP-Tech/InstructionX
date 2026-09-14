"""用量趋势面板渲染通路测试

测试目标: ``ui.usage_panel.trend_chart.TrendPanel`` 与 UIKit 图表引擎的集成
测试范围:

- 渲染分流：首次与结构变化（指标 / 区间）走 ``set_option`` 全量重建，
  结构未变时走 ``set_stream_data`` 增量通路（UIKit alpha-v1.0.3 新增能力）；
- 异常回退：增量写入失败（返回 ``False``）时必须回退全量重建；
- 缓存失效：全量重建必须调用 ``invalidate_all_caches``——alpha-v1.0.3 的静态层
  缓存键不含日历 range，遗漏会令内建月份标签停留在旧区间；
- 视觉回归（``@pytest.mark.ui``）：同尺寸切换区间后月份标签带随区间更新；
- 边界：单日区间、跨年区间、无记录（全零序列）经公开 ``update_series`` 入口。

背景说明见 ``ui/usage_panel/trend_chart.py`` 的 ``_render_full`` docstring。
"""

from datetime import date, timedelta

import pytest
from PySide6.QtCore import QBuffer, QIODevice, Qt

from core.i18n import tr
from ui.usage_panel.trend_chart import (
    HEATMAP_SERIES_INDEX,
    METRIC_OPTION_KEYS,
    TrendPanel,
)

# ===== 测试常量 =====
#: 面板尺寸（固定尺寸是「同尺寸切换区间」这一缓存命中前提）
PANEL_WIDTH = 1100
PANEL_HEIGHT = 400
#: 标签带行数（覆盖月份标签所在区域，留出抗锯齿余量）
LABEL_BAND_ROWS = 22
#: 抓图非空白的颜色数下限（低于该值说明画面未真正渲染，结论不可信）
MIN_DISTINCT_COLORS = 6
#: 两个区间均为 365 天（53 周）→ 图表高度一致，才可能命中静态层缓存
RANGE_A_START = date(2025, 1, 1)
RANGE_B_START = date(2025, 2, 1)
RANGE_DAYS = 365


def _points(start: date, span: int = RANGE_DAYS, modulus: int = 7) -> list:
    """构造每日聚合序列（模运算制造可区分的数值分布）"""
    return [(start + timedelta(days=i), (i * 7 + i // 3) % modulus)
            for i in range(span)]


def _make_panel(qtbot) -> TrendPanel:
    """创建不实际上屏的趋势面板（布局照常生效，便于 grab）"""
    panel = TrendPanel()
    qtbot.addWidget(panel)
    panel.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    panel.resize(PANEL_WIDTH, PANEL_HEIGHT)
    panel.show()
    return panel


def _row_signature(image, y: int) -> bytes:
    """把某一行像素编码为 PNG 字节，作为该行的可比较签名"""
    row = image.copy(0, y, image.width(), 1)
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    row.save(buffer, "PNG")
    return bytes(buffer.data())


def _diff_rows(image_a, image_b, rows: int = LABEL_BAND_ROWS) -> list:
    """返回标签带内像素不一致的行号列表"""
    height = min(rows, image_a.height(), image_b.height())
    return [y for y in range(height)
            if _row_signature(image_a, y) != _row_signature(image_b, y)]


def _distinct_colors(image, step: int = 7) -> int:
    """抽样统计画面颜色数，用于识别「空白抓图」造成的假通过"""
    colors = set()
    for y in range(0, image.height(), step):
        for x in range(0, image.width(), step):
            colors.add(image.pixelColor(x, y).rgba())
    return len(colors)


class TestRenderRouting:
    """渲染分流：全量重建与增量刷新的选择逻辑"""

    def test_first_render_uses_full_option(self, qtbot, mocker):
        """
        测试目的: 首次渲染无结构标识可比，必须走全量 set_option

        前提条件: 新建面板（_render_key 为 None）
        操作步骤: 调用 _render_series
        预期结果: set_option 调用 1 次、set_stream_data 未调用、结构标识已记录
        """
        panel = _make_panel(qtbot)
        spy_option = mocker.spy(panel._chart, "set_option")
        spy_stream = mocker.spy(panel._chart, "set_stream_data")
        points = _points(RANGE_A_START)

        panel._render_series(points, 0)

        assert spy_option.call_count == 1, "首次渲染应走全量 set_option"
        assert spy_stream.call_count == 0, "首次渲染不应走增量通路"
        assert panel._render_key == (0, points[0][0], points[-1][0])

    def test_same_structure_refresh_uses_stream_data(self, qtbot, mocker):
        """
        测试目的: 指标与区间均未变化时走增量通路，不重建 option 与坐标系

        前提条件: 已全量渲染同一区间
        操作步骤: 以同区间同指标、仅数值不同的序列再次渲染
        预期结果: set_stream_data 调用 1 次、option 版本号不变、渲染器数据已更新
        """
        panel = _make_panel(qtbot)
        points = _points(RANGE_A_START)
        panel._render_series(points, 0)
        version_before = panel._chart._opt_version

        spy_option = mocker.spy(panel._chart, "set_option")
        spy_stream = mocker.spy(panel._chart, "set_stream_data")
        refreshed = [(day, (value * 5 + 3) % 11) for day, value in points]
        panel._render_series(refreshed, 0)

        assert spy_stream.call_count == 1, "结构未变应走增量通路"
        assert spy_stream.call_args.kwargs["series"] == HEATMAP_SERIES_INDEX
        assert spy_option.call_count == 0, "增量通路不应触发全量重建"
        assert panel._chart._opt_version == version_before, (
            "增量刷新不应递增 option 版本（不应重建渲染器）"
        )
        renderer_data = panel._chart._series[HEATMAP_SERIES_INDEX].opt["data"]
        assert list(renderer_data[0]) == [refreshed[0][0].isoformat(), refreshed[0][1]]

    def test_metric_change_forces_full_rebuild(self, qtbot, mocker):
        """
        测试目的: 指标切换属结构变化（系列名不同），必须全量重建

        前提条件: 已以指标 0 渲染
        操作步骤: 以指标 1 渲染同区间
        预期结果: set_option 调用 1 次、set_stream_data 未调用、结构标识更新
        """
        panel = _make_panel(qtbot)
        points = _points(RANGE_A_START)
        panel._render_series(points, 0)

        spy_option = mocker.spy(panel._chart, "set_option")
        spy_stream = mocker.spy(panel._chart, "set_stream_data")
        panel._render_series(points, 1)

        assert spy_option.call_count == 1
        assert spy_stream.call_count == 0
        assert panel._render_key[0] == 1

    def test_range_change_forces_full_rebuild(self, qtbot, mocker):
        """
        测试目的: 区间变化属结构变化（日历 range 变），必须全量重建

        前提条件: 已渲染区间 A（365 天）
        操作步骤: 渲染同为 365 天但起点不同的区间 B
        预期结果: 走全量重建（长度相同也不能误判为同结构）
        """
        panel = _make_panel(qtbot)
        panel._render_series(_points(RANGE_A_START), 0)

        spy_option = mocker.spy(panel._chart, "set_option")
        spy_stream = mocker.spy(panel._chart, "set_stream_data")
        panel._render_series(_points(RANGE_B_START), 0)

        assert spy_option.call_count == 1, "区间变化必须全量重建"
        assert spy_stream.call_count == 0
        assert panel._render_key == (0, RANGE_B_START,
                                     RANGE_B_START + timedelta(days=RANGE_DAYS - 1))

    def test_stream_failure_falls_back_to_full_option(self, qtbot, mocker):
        """
        测试目的: 增量写入失败时必须回退全量重建，不能停留在旧数据

        前提条件: 已全量渲染；把 set_stream_data 打桩为返回 False
        操作步骤: 以同结构序列再次渲染
        预期结果: set_option 调用 1 次（回退生效）
        """
        panel = _make_panel(qtbot)
        points = _points(RANGE_A_START)
        panel._render_series(points, 0)

        mocker.patch.object(panel._chart, "set_stream_data", return_value=False)
        spy_option = mocker.spy(panel._chart, "set_option")
        panel._render_series([(day, value + 1) for day, value in points], 0)

        assert spy_option.call_count == 1, "增量失败应回退全量重建"


class TestCacheInvalidation:
    """层级缓存失效：全量重建必须失效静态层，增量刷新则保持命中"""

    def test_full_render_invalidates_cache(self, qtbot, mocker):
        """
        测试目的: 全量重建后调用 invalidate_all_caches

        前提条件: 新建面板
        操作步骤: 首次渲染
        预期结果: invalidate_all_caches 被调用 1 次
        """
        panel = _make_panel(qtbot)
        spy_invalidate = mocker.spy(panel._chart, "invalidate_all_caches")

        panel._render_series(_points(RANGE_A_START), 0)

        assert spy_invalidate.call_count == 1, (
            "1.0.3 静态层缓存键不含日历 range，全量重建后必须失效缓存"
        )

    def test_incremental_render_keeps_static_cache(self, qtbot, mocker):
        """
        测试目的: 增量刷新不失效静态层缓存（区间未变，标签本应保持命中）

        前提条件: 已全量渲染同一区间
        操作步骤: 以同结构序列再次渲染
        预期结果: invalidate_all_caches 未被调用
        """
        panel = _make_panel(qtbot)
        points = _points(RANGE_A_START)
        panel._render_series(points, 0)

        spy_invalidate = mocker.spy(panel._chart, "invalidate_all_caches")
        panel._render_series([(day, value + 2) for day, value in points], 0)

        assert spy_invalidate.call_count == 0

    @pytest.mark.ui
    def test_range_switch_refreshes_month_label_band(self, qtbot):
        """
        测试目的: 视觉回归——同尺寸切换区间后内建月份标签随区间更新

        前提条件: 两个区间天数相同（图表高度一致），构成静态层缓存命中的条件
        操作步骤: 面板 A 依次渲染区间 A、区间 B；面板 B 全新渲染区间 B
        预期结果: A 的标签带在切换后发生变化，且与「全新渲染区间 B」逐行一致
            （未失效缓存时标签带会与区间 A 完全相同，即本用例失败）
        """
        panel = _make_panel(qtbot)
        panel._render_series(_points(RANGE_A_START), 0)
        qtbot.wait(1)
        image_a = panel._chart.grab().toImage()

        panel._render_series(_points(RANGE_B_START), 0)
        qtbot.wait(1)
        image_b = panel._chart.grab().toImage()

        fresh = _make_panel(qtbot)
        fresh._render_series(_points(RANGE_B_START), 0)
        qtbot.wait(1)
        image_fresh_b = fresh._chart.grab().toImage()

        # 先排除「抓图空白」导致的假通过/假失败
        colors = {name: _distinct_colors(image) for name, image in (
            ("A", image_a), ("B", image_b), ("freshB", image_fresh_b))}
        assert min(colors.values()) >= MIN_DISTINCT_COLORS, (
            f"抓图疑似空白，用例结论不可信：{colors}"
        )
        rows_ab = _diff_rows(image_a, image_b)
        assert rows_ab, (
            f"切换区间后月份标签带应随之变化（颜色数={colors}，"
            f"图高={image_a.height()}）"
        )
        assert not _diff_rows(image_b, image_fresh_b), (
            "切换后的标签带与全新渲染不一致：静态层缓存未正确失效"
        )


class TestBoundaries:
    """边界与公开入口"""

    def test_single_day_range_renders(self, qtbot, mocker):
        """
        测试目的: 自定义单日区间不抛异常且正常全量渲染

        前提条件: 序列仅 1 天
        操作步骤: 调用 _render_series
        预期结果: set_option 调用 1 次，日历 range 起止同日
        """
        panel = _make_panel(qtbot)
        spy_option = mocker.spy(panel._chart, "set_option")
        day = date(2025, 6, 15)

        panel._render_series([(day, 3)], 0)

        option = spy_option.call_args.args[0]
        assert option["calendar"]["range"] == [day.isoformat(), day.isoformat()]
        assert panel._render_key == (0, day, day)

    def test_cross_year_range_option_payload(self, qtbot, mocker):
        """
        测试目的: 跨年区间的 option 载荷正确（year 取起始年、range 覆盖两整年）

        前提条件: 区间 2025-02-01 ~ 2026-01-31
        操作步骤: 调用 _render_series
        预期结果: calendar.year 为 2025、range 起止正确、系列数据完整 365 条
        """
        panel = _make_panel(qtbot)
        spy_option = mocker.spy(panel._chart, "set_option")
        points = _points(RANGE_B_START)

        panel._render_series(points, 0)

        option = spy_option.call_args.args[0]
        series = option["series"][HEATMAP_SERIES_INDEX]
        assert option["calendar"]["year"] == RANGE_B_START.year
        assert option["calendar"]["range"] == [
            RANGE_B_START.isoformat(), points[-1][0].isoformat()]
        assert option["calendar"]["cellSize"] == "auto"
        assert series["type"] == "calendarHeatmap"
        assert series["coordinateSystem"] == "calendar"
        assert series["name"] == tr("usage_panel", METRIC_OPTION_KEYS[0])
        assert len(series["data"]) == RANGE_DAYS

    def test_update_series_without_records(self, qtbot, mocker):
        """
        测试目的: 公开入口在无用量记录时仍能出图（全零序列）并更新状态文本

        前提条件: 空记录列表
        操作步骤: 调用 update_series([])
        预期结果: 走全量重建、状态文本参数已记录（区间天数正确）
        """
        panel = _make_panel(qtbot)
        spy_option = mocker.spy(panel._chart, "set_option")

        panel.update_series([])

        assert spy_option.call_count == 1
        assert panel._last_status is not None, "区间状态文本参数应已记录"
        start_iso, end_iso, days = panel._last_status
        assert days >= 1
        assert start_iso <= end_iso
