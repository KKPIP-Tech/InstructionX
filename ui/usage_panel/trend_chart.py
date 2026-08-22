"""用量趋势面板（UIKit 原生图表引擎日历热力图）

时间范围选择（近半年 / 近一年 / 自定义）、指标切换（请求数 / 输入 Token /
输出 Token）、GitHub 贡献图风格的日历热力图（heatmap + calendar 坐标系）、
悬停提示与区间状态文本。图表使用 InstructionX_UIKit 原生图表引擎
（ChartWidget + set_option），配色实时取自 UIKit 令牌并随主题切换自动换肤。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from PySide6.QtCore import QDate, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.i18n import get_language_manager, tr
from core.llm.types import UsageRecord
from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.charts import (
    ChartWidget, register_component, register_series,
)
from InstructionX_UIKit.charts.axes import _MONTH_LABELS, chart_font
from InstructionX_UIKit.charts.series_cartesian import HeatmapSeriesRenderer
from InstructionX_UIKit.components import Button, ComboBox, DatePicker

from .formatting import local_tz, to_local_time


# ===================================================================
# 图表引擎扩展（经 register_series/register_component 公开扩展点注册，不改库）
class _CalendarHeatmapRenderer(HeatmapSeriesRenderer):
    """日历热力图（悬停 tooltip 显示单元格日期）。

    库内 hit_test 返回 ``series=系列名``，core 的 ``_tooltip_item`` 优先取
    ``hit["series"]`` 作为行名，导致单元格日期（label）被丢弃。此处把
    series 置空，让行名回退为日期；指标名由色点与工具行下拉框表达。
    """

    def hit_test(self, pos):
        """命中单元格时返回 {name: 日期, value: 值}（series 置空）"""
        hit = super().hit_test(pos)
        if hit is not None:
            hit["series"] = ""
        return hit


class _CalendarMonthLabels:
    """跨年月份标签补充组件（option 键 ``monthLabels``）。

    库内 CalendarCoord.paint_axes 的月份标签按 ``date(coord.year, month, 1)``
    构造，只支持单年 range：跨年 range 中相邻年份的月份标签缺失。
    本组件补画「年份 != coord.year」的月份 1 日标签，列位经公开的
    ``cell_rect()`` 计算，样式与内建标签一致。
    """

    option_key = "monthLabels"

    def __init__(self, chart, opt):
        self.chart = chart
        self._marks = []   # [(x, label)]
        self._top = 0.0

    def layout(self, rect: QRectF) -> None:
        """计算需补画的月份标签（仅 coord.year 之外的年份）"""
        self._marks = []
        self._top = rect.top()
        coord = self.chart.coord_for({"coordinateSystem": "calendar"})
        if coord is None or getattr(coord, "kind", "") != "calendar":
            return
        first_monday = coord.start - timedelta(days=coord.start.weekday())
        cursor = date(coord.start.year, coord.start.month, 1)
        last_col = -1
        while cursor <= coord.end:
            if cursor.year != coord.year:
                anchor = max(cursor, coord.start)
                col = (anchor - first_monday).days // 7
                if col != last_col:
                    last_col = col
                    cell = coord.cell_rect(cursor)
                    if not cell.isNull():
                        self._marks.append(
                            (cell.left(), _MONTH_LABELS[cursor.month - 1]))
            cursor = date(cursor.year + (cursor.month == 12),
                          cursor.month % 12 + 1, 1)

    def paint(self, p: QPainter, anim_t: float = 1.0) -> None:
        """按内建标签样式（font.xs + text.tertiary）绘制补充月份标签"""
        if not self._marks:
            return
        p.save()
        p.setPen(QColor(T("color.text.tertiary")))
        font = chart_font(T("font.xs"))
        p.setFont(font)
        for x, label in self._marks:
            p.drawText(QRectF(x, self._top, 40, QFontMetricsF(font).height()),
                       Qt.AlignLeft | Qt.AlignVCenter, label)
        p.restore()


register_series("calendarHeatmap", _CalendarHeatmapRenderer)
register_component("monthLabels", _CalendarMonthLabels)

# ===== 时间范围选项（i18n 键，显示文案在取词时解析） =====
RANGE_OPTION_KEYS = ("range.half_year", "range.year", "range.custom")
RANGE_DAY_SPANS = (182, 365)  # 与 RANGE_OPTION_KEYS 前两项一一对应
DEFAULT_RANGE_INDEX = 1  # 默认「近一年」
CUSTOM_RANGE_INDEX = 2

# ===== 趋势指标选项（i18n 键，显示文案在取词时解析） =====
METRIC_OPTION_KEYS = ("metric.requests", "metric.input_tokens", "metric.output_tokens")
# 与 METRIC_OPTION_KEYS 一一对应；None 表示按请求条数计数，否则为 UsageRecord 字段名
METRIC_FIELDS: Tuple[Optional[str], ...] = (None, "input_tokens", "output_tokens")


def _resolve_texts(keys: Tuple[str, ...]) -> List[str]:
    """按当前语言解析一组 i18n 键的显示文案"""
    return [tr("usage_panel", key) for key in keys]

# ===== 图表显示常量 =====
CHART_MIN_HEIGHT = 60
# 自适应高度的单元格边长上限（短范围时令格不被拉得过大）
MAX_CELL_HEIGHT = 28.0
MIN_CELL_HEIGHT = 3.0
# 月份标签区高度与网格底部余量（与 CalendarCoord.layout 的标签预留一致）
MONTH_LABEL_HEIGHT = 16.0
GRID_BOTTOM_SLACK = 8.0
# 面板自适应高度中的固定部分（边距/间距 + 标题行 + 工具行 + 状态行）
PANEL_FIXED_HEIGHT = 108

# ===== 日期显示格式 =====
DATE_DISPLAY_FORMAT = "yyyy-MM-dd"


class TrendPanel(QFrame):
    """用量趋势面板

    包含范围/指标工具行、UIKit ChartWidget 日历热力图与区间状态文本。
    面板自身不访问数据层，由外部传入筛选后的 UsageRecord 列表进行渲染。

    Signals:
        range_applied: 时间范围发生有效变更（自定义范围需点「应用」）
        metric_changed: 趋势指标切换（仅需重绘图表，不必全量刷新）
    """

    range_applied = Signal()
    metric_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("usageSubPanel")
        self.setStyleSheet(
            f"#usageSubPanel {{ background-color: {T('color.bg.elevated')};"
            f" border: 1px solid {T('color.border')};"
            f" border-radius: {T('radius.md')}px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_chart(), stretch=1)

        self._status_label = QLabel()
        set_property(self._status_label, "role", "secondary")
        layout.addWidget(self._status_label)
        # 最近一次状态文本参数（语言切换时按原值重排文案）
        self._last_status: Optional[Tuple[str, str, int]] = None

        self._connect_signals()
        self._retranslate_ui()
        get_language_manager().language_changed.connect(self._retranslate_ui)
        self._on_range_changed(DEFAULT_RANGE_INDEX)
        self._update_fixed_height()

    # ------------------------------------------------------------------ UI

    def _build_header(self) -> QHBoxLayout:
        """面板标题行（文案由 ``_retranslate_ui`` 统一设置）"""
        header = QHBoxLayout()
        self._title_label = QLabel()
        font = QFont()
        font.setPixelSize(T("font.title.sm"))
        font.setWeight(QFont.Weight.DemiBold)
        self._title_label.setFont(font)
        header.addWidget(self._title_label)
        header.addStretch()
        return header

    def _build_toolbar(self) -> QHBoxLayout:
        """范围选择 + 自定义日期 + 指标切换工具行"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._range_combo = ComboBox(items=_resolve_texts(RANGE_OPTION_KEYS))
        self._range_combo.setCurrentIndex(DEFAULT_RANGE_INDEX)
        toolbar.addWidget(self._range_combo)

        today = date.today()
        self._start_edit = self._make_date_edit(today - timedelta(days=RANGE_DAY_SPANS[1] - 1))
        self._end_edit = self._make_date_edit(today)
        self._to_label = QLabel()
        set_property(self._to_label, "role", "secondary")
        self._apply_btn = Button("", variant="default")

        toolbar.addWidget(self._start_edit)
        toolbar.addWidget(self._to_label)
        toolbar.addWidget(self._end_edit)
        toolbar.addWidget(self._apply_btn)
        toolbar.addStretch()

        self._metric_combo = ComboBox(items=_resolve_texts(METRIC_OPTION_KEYS))
        toolbar.addWidget(self._metric_combo)
        return toolbar

    def _make_date_edit(self, d: date) -> DatePicker:
        """创建统一格式的日期选择框（UIKit DatePicker，自带日历弹层）"""
        edit = DatePicker(QDate(d.year, d.month, d.day))
        edit.setDisplayFormat(DATE_DISPLAY_FORMAT)
        return edit

    def _build_chart(self) -> ChartWidget:
        """创建 UIKit 原生图表控件（set_option 数据驱动）"""
        self._chart = ChartWidget()
        self._chart.setMinimumHeight(CHART_MIN_HEIGHT)
        return self._chart

    def _connect_signals(self) -> None:
        self._range_combo.currentIndexChanged.connect(self._on_range_changed)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)

    def _retranslate_ui(self) -> None:
        """按当前语言重设面板全部用户可见文案（语言切换时自动触发）"""
        self._title_label.setText(tr("usage_panel", "trend.title"))
        self._reset_combo_items(self._range_combo, _resolve_texts(RANGE_OPTION_KEYS))
        self._range_combo.setAccessibleName(tr("usage_panel", "a11y.range_combo"))
        self._start_edit.setAccessibleName(tr("usage_panel", "a11y.start_date"))
        self._end_edit.setAccessibleName(tr("usage_panel", "a11y.end_date"))
        self._to_label.setText(tr("usage_panel", "range.to"))
        self._apply_btn.setText(tr("usage_panel", "range.apply"))
        self._apply_btn.setAccessibleName(tr("usage_panel", "a11y.apply_range"))
        self._reset_combo_items(self._metric_combo, _resolve_texts(METRIC_OPTION_KEYS))
        self._metric_combo.setAccessibleName(tr("usage_panel", "a11y.metric_combo"))
        self._set_status_text()

    @staticmethod
    def _reset_combo_items(combo: ComboBox, items: List[str]) -> None:
        """重建下拉项并保留当前索引（语言切换仅更新文案，选中项不变）"""
        index = combo.currentIndex()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(items)
        combo.setCurrentIndex(index if 0 <= index < len(items) else 0)
        combo.blockSignals(False)

    def _set_status_text(self) -> None:
        """按当前语言重设区间状态文本（未刷新过数据时保持为空）"""
        if self._last_status is None:
            return
        start, end, days = self._last_status
        self._status_label.setText(
            tr("usage_panel", "trend.status", start=start, end=end, days=days))

    # ------------------------------------------------------------- 公共接口

    def current_range(self) -> Tuple[datetime, datetime]:
        """当前选择的统计区间（本地时区 aware，起日 00:00 ~ 止日 23:59:59）

        Returns:
            Tuple[datetime, datetime]: (起始时间, 结束时间)，保证起始不晚于结束
        """
        idx = self._range_combo.currentIndex()
        today = datetime.now().date()
        if idx < len(RANGE_DAY_SPANS):
            start_d = today - timedelta(days=RANGE_DAY_SPANS[idx] - 1)
            end_d = today
        else:
            start_d = self._start_edit.date().toPython()
            end_d = self._end_edit.date().toPython()
            if start_d > end_d:
                start_d, end_d = end_d, start_d
        tz = local_tz()
        return (
            datetime.combine(start_d, datetime.min.time(), tzinfo=tz),
            datetime.combine(end_d, datetime.max.time(), tzinfo=tz),
        )

    def update_series(self, records: List[UsageRecord]) -> None:
        """按当前范围与指标重绘热力图并更新状态文本

        Args:
            records: 当前筛选条件下的全部用量记录（面板内部按天聚合）
        """
        start_dt, end_dt = self.current_range()
        metric_idx = self._metric_combo.currentIndex()
        points = self._daily_series(records, start_dt.date(), end_dt.date(), METRIC_FIELDS[metric_idx])
        self._render_series(points, metric_idx)
        self._update_fixed_height()
        days = (end_dt.date() - start_dt.date()).days + 1
        self._last_status = (start_dt.date().isoformat(), end_dt.date().isoformat(), days)
        self._set_status_text()

    # ------------------------------------------------------------- 自适应高度

    def _update_fixed_height(self) -> None:
        """按当前范围的热力图自然高度调整面板高度

        单元格边长由可用宽度 / 周数决定（上限 MAX_CELL_HEIGHT），面板高度
        = 固定部分 + 月份标签 + 7 行单元格 + 底部余量；窗口变宽时单元格
        随之变大，面板同步增高（resizeEvent 驱动）。
        """
        self.setFixedHeight(int(PANEL_FIXED_HEIGHT + self._grid_height()))

    def _grid_height(self) -> float:
        """当前范围下日历网格的自然高度（月份标签 + 7 行单元格 + 余量）"""
        start_dt, end_dt = self.current_range()
        first = start_dt.date() - timedelta(days=start_dt.date().weekday())
        weeks = max(1, (end_dt.date() - first).days // 7 + 1)
        avail_w = max(20.0, self.width() - 2 * 14)  # 面板左右内边距
        cell = min(avail_w / weeks, MAX_CELL_HEIGHT)
        cell = max(MIN_CELL_HEIGHT, cell)
        return MONTH_LABEL_HEIGHT + 7 * cell + GRID_BOTTOM_SLACK

    def resizeEvent(self, event) -> None:
        """宽度变化时重算自适应高度（高度自身变化不触发，避免递归）"""
        if event.oldSize().width() != event.size().width():
            self._update_fixed_height()
        super().resizeEvent(event)

    # ------------------------------------------------------------- 数据聚合

    @staticmethod
    def _daily_series(
        records: List[UsageRecord], start_d: date, end_d: date, field: Optional[str]
    ) -> List[Tuple[date, int]]:
        """按天聚合趋势序列，覆盖区间内每一天（无记录的天为 0）

        Args:
            records: 用量记录列表
            start_d: 起始日期（包含）
            end_d: 结束日期（包含）
            field: None 表示按请求条数计数，否则累加该 UsageRecord 数值字段

        Returns:
            List[Tuple[date, int]]: [(日期, 聚合值), ...]，按日期升序
        """
        days = (end_d - start_d).days + 1
        buckets = [0] * days
        for record in records:
            # 记录时间戳为 UTC aware，先转本地时间再按天归桶
            idx = (to_local_time(record.timestamp).date() - start_d).days
            if 0 <= idx < days:
                buckets[idx] += 1 if field is None else getattr(record, field)
        return [(start_d + timedelta(days=i), v) for i, v in enumerate(buckets)]

    # ------------------------------------------------------------- 渲染

    def _render_series(self, points: List[Tuple[date, int]], metric_idx: int) -> None:
        """将聚合后的序列构建为日历热力图 option 并交给 ChartWidget

        GitHub 贡献图风格：行=星期、列=周序，单元格颜色深浅映射当日用量
        （色带为 UIKit 令牌 primary.subtle → primary，按数据范围映射）。
        """
        start_d, end_d = points[0][0], points[-1][0]

        self._chart.set_option({
            "legend": {"show": False},
            "tooltip": {"show": True, "trigger": "item"},
            # year 取起始年：内建月份标签可正确覆盖起始年各月；
            # 跨年部分由 monthLabels 组件补画（见模块顶部扩展类）
            "calendar": {
                "year": start_d.year,
                "range": [start_d.isoformat(), end_d.isoformat()],
                "cellSize": "auto",
            },
            "monthLabels": {},
            "series": [{
                "type": "calendarHeatmap",
                "name": tr("usage_panel", METRIC_OPTION_KEYS[metric_idx]),
                "coordinateSystem": "calendar",
                "data": [[d.isoformat(), v] for d, v in points],
            }],
        })

    # ------------------------------------------------------------- 事件

    def _on_range_changed(self, index: int) -> None:
        """范围选项变更：自定义仅解锁控件，其余立即生效"""
        is_custom = index == CUSTOM_RANGE_INDEX
        for widget in (self._start_edit, self._end_edit, self._apply_btn):
            widget.setEnabled(is_custom)
        if not is_custom:
            self.range_applied.emit()

    def _on_apply_clicked(self) -> None:
        """自定义范围「应用」按钮"""
        self.range_applied.emit()

    def _on_metric_changed(self, _index: int) -> None:
        """指标切换"""
        self.metric_changed.emit()
