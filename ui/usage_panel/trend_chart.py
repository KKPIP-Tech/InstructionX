"""用量趋势面板（QtCharts 平滑折线图）

移植自用量面板 Demo：时间范围选择（近 7 天 / 近 30 天 / 自定义）、
指标切换（请求数 / 输入 Token / 输出 Token）、QSplineSeries 平滑折线、
悬停提示与区间状态文本。图表配色取自 StyleQSS 当前主题色板，随全局主题自动适配。
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QSplineSeries, QValueAxis
from PySide6.QtCore import QDate, QDateTime, QTime, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel, QPushButton, QToolTip, QVBoxLayout,
)

from core.llm.types import UsageRecord
from InstructionX_UIKit import T

from .formatting import fmt_int, fmt_tokens, local_tz, pick_token_scale, to_local_time

# ===== 时间范围选项 =====
RANGE_OPTIONS = ("近 7 天", "近 30 天", "自定义")
RANGE_DAY_SPANS = (7, 30)  # 与 RANGE_OPTIONS 前两项一一对应
DEFAULT_RANGE_INDEX = 1  # 默认「近 30 天」
CUSTOM_RANGE_INDEX = 2

# ===== 趋势指标选项 =====
METRIC_OPTIONS = ("请求数", "输入 Token", "输出 Token")
# 与 METRIC_OPTIONS 一一对应；None 表示按请求条数计数，否则为 UsageRecord 字段名
METRIC_FIELDS: Tuple[Optional[str], ...] = (None, "input_tokens", "output_tokens")

# ===== 图表显示常量 =====
# 面板固定高度：窗口缩小时由外层滚动区接管，面板自身不缩水
TREND_PANEL_HEIGHT = 320
CHART_MIN_HEIGHT = 200
MAX_X_TICKS = 10
Y_TICK_COUNT = 4
Y_HEADROOM_RATIO = 1.15
Y_EMPTY_TOP = 1.0
Y_INTEGER_THRESHOLD = 10
SERIES_LINE_WIDTH = 2
# 折线数据点固定在当天正午，避免时区偏移导致点落在日期边界上
POINT_HOUR = 12

# ===== 日期显示格式 =====
DATE_DISPLAY_FORMAT = "yyyy-MM-dd"
AXIS_DATE_FORMAT = "MM-dd"


class TrendPanel(QFrame):
    """用量趋势面板

    包含范围/指标工具行、QtCharts 折线图与区间状态文本。
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
        self.setFixedHeight(TREND_PANEL_HEIGHT)
        # 折线点横坐标(ms) → (日期, 原始值)，供悬停提示反查
        self._point_meta: Dict[int, Tuple[date, int]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_chart_view(), stretch=1)

        self._status_label = QLabel()
        self._status_label.setObjectName("usageStatusText")
        layout.addWidget(self._status_label)

        self._connect_signals()
        self._on_range_changed(DEFAULT_RANGE_INDEX)

    # ------------------------------------------------------------------ UI

    def _build_header(self) -> QHBoxLayout:
        """面板标题行"""
        header = QHBoxLayout()
        title = QLabel("用量趋势")
        title.setObjectName("usagePanelTitle")
        header.addWidget(title)
        header.addStretch()
        return header

    def _build_toolbar(self) -> QHBoxLayout:
        """范围选择 + 自定义日期 + 指标切换工具行"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._range_combo = QComboBox()
        self._range_combo.setObjectName("usageFilterCombo")
        self._range_combo.setAccessibleName("时间范围选择")
        self._range_combo.addItems(RANGE_OPTIONS)
        self._range_combo.setCurrentIndex(DEFAULT_RANGE_INDEX)
        toolbar.addWidget(self._range_combo)

        today = date.today()
        self._start_edit = self._make_date_edit(today - timedelta(days=RANGE_DAY_SPANS[1] - 1))
        self._start_edit.setAccessibleName("起始日期")
        self._end_edit = self._make_date_edit(today)
        self._end_edit.setAccessibleName("结束日期")
        to_label = QLabel("至")
        to_label.setObjectName("usageStatusText")
        self._apply_btn = QPushButton("应用")
        self._apply_btn.setAccessibleName("应用自定义日期范围")

        toolbar.addWidget(self._start_edit)
        toolbar.addWidget(to_label)
        toolbar.addWidget(self._end_edit)
        toolbar.addWidget(self._apply_btn)
        toolbar.addStretch()

        self._metric_combo = QComboBox()
        self._metric_combo.setObjectName("usageFilterCombo")
        self._metric_combo.setAccessibleName("趋势指标切换")
        self._metric_combo.addItems(METRIC_OPTIONS)
        toolbar.addWidget(self._metric_combo)
        return toolbar

    def _make_date_edit(self, d: date) -> QDateEdit:
        """创建统一格式的日期选择框"""
        edit = QDateEdit(QDate(d.year, d.month, d.day))
        edit.setObjectName("usageDateEdit")
        edit.setDisplayFormat(DATE_DISPLAY_FORMAT)
        edit.setCalendarPopup(True)
        return edit

    def _build_chart_view(self) -> QChartView:
        """创建 QChartView + 平滑折线系列与坐标轴"""
        self._chart = QChart()
        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._chart.setBackgroundRoundness(0)
        self._chart.layout().setContentsMargins(0, 0, 0, 0)

        self._series = QSplineSeries()
        self._series.setPointsVisible(True)
        self._chart.addSeries(self._series)

        self._axis_x = QDateTimeAxis()
        self._axis_x.setFormat(AXIS_DATE_FORMAT)
        self._axis_y = QValueAxis()
        self._axis_y.setLabelFormat("%.0f")
        self._chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)
        self._series.attachAxis(self._axis_x)
        self._series.attachAxis(self._axis_y)

        chart_view = QChartView(self._chart)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_view.setMinimumHeight(CHART_MIN_HEIGHT)
        return chart_view

    def _connect_signals(self) -> None:
        self._range_combo.currentIndexChanged.connect(self._on_range_changed)
        self._apply_btn.clicked.connect(self._on_apply_clicked)
        self._metric_combo.currentIndexChanged.connect(self._on_metric_changed)
        self._series.hovered.connect(self._on_series_hovered)

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
        """按当前范围与指标重绘折线图并更新状态文本

        Args:
            records: 当前筛选条件下的全部用量记录（面板内部按天聚合）
        """
        start_dt, end_dt = self.current_range()
        metric_idx = self._metric_combo.currentIndex()
        points = self._daily_series(records, start_dt.date(), end_dt.date(), METRIC_FIELDS[metric_idx])
        self._render_series(points, metric_idx)
        days = (end_dt.date() - start_dt.date()).days + 1
        self._status_label.setText(
            f"{start_dt.date().isoformat()} ~ {end_dt.date().isoformat()} · 共 {days} 天"
        )

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
        """将聚合后的序列写入图表并调整坐标轴"""
        max_raw = max((v for _, v in points), default=0)
        is_count_metric = METRIC_FIELDS[metric_idx] is None
        scale, unit = (1.0, "") if is_count_metric else pick_token_scale(max_raw)

        self._series.clear()
        self._point_meta.clear()
        for d, v in points:
            msec = int(QDateTime(QDate(d.year, d.month, d.day), QTime(POINT_HOUR, 0)).toMSecsSinceEpoch())
            self._series.append(msec, v / scale)
            self._point_meta[msec] = (d, v)
        self._series.setName(METRIC_OPTIONS[metric_idx] + unit)

        self._update_axes(points, max_raw, scale)
        self._apply_chart_theme()

    def _update_axes(self, points: List[Tuple[date, int]], max_raw: int, scale: float) -> None:
        """根据序列范围调整 X/Y 轴刻度"""
        if points:
            first_d, last_d = points[0][0], points[-1][0]
            self._axis_x.setRange(
                QDateTime(QDate(first_d.year, first_d.month, first_d.day), QTime(0, 0)),
                QDateTime(QDate(last_d.year, last_d.month, last_d.day), QTime(23, 59, 59)),
            )
            self._axis_x.setTickCount(min(len(points), MAX_X_TICKS) if len(points) > 1 else 2)

        top = max_raw / scale if max_raw > 0 else Y_EMPTY_TOP
        self._axis_y.setRange(0, top * Y_HEADROOM_RATIO)
        self._axis_y.applyNiceNumbers()
        self._axis_y.setTickCount(Y_TICK_COUNT)
        self._axis_y.setLabelFormat("%.0f" if top >= Y_INTEGER_THRESHOLD else "%.1f")

    def _apply_chart_theme(self) -> None:
        """图表配色跟随 UIKit 当前主题（背景、坐标轴、网格线、折线颜色）"""
        card = QColor(T("color.bg.elevated"))
        subtext = QColor(T("color.text.secondary"))
        self._chart.setBackgroundBrush(card)
        self._chart.setPlotAreaBackgroundBrush(card)
        self._chart.setPlotAreaBackgroundVisible(True)
        self._chart.legend().setLabelColor(subtext)
        for axis in (self._axis_x, self._axis_y):
            axis.setLabelsColor(subtext)
            axis.setGridLineColor(QColor(T("color.border")))
            axis.setLinePenColor(QColor(T("color.border.strong")))
        self._series.setColor(QColor(T("color.primary")))
        pen = self._series.pen()
        pen.setWidth(SERIES_LINE_WIDTH)
        self._series.setPen(pen)

    # ------------------------------------------------------------- 事件

    def _on_range_changed(self, index: int) -> None:
        """范围选项变更：自定义仅解锁控件，其余立即生效"""
        is_custom = index == CUSTOM_RANGE_INDEX
        for widget in (self._start_edit, self._end_edit, self._apply_btn):
            widget.setEnabled(is_custom)
        if not is_custom:
            self.range_applied.emit()

    def _on_apply_clicked(self) -> None:
        """应用自定义范围：起始晚于结束时自动交换，保证区间合法"""
        start_d = self._start_edit.date().toPython()
        end_d = self._end_edit.date().toPython()
        if start_d > end_d:
            self._start_edit.blockSignals(True)
            self._end_edit.blockSignals(True)
            self._start_edit.setDate(QDate(end_d.year, end_d.month, end_d.day))
            self._end_edit.setDate(QDate(start_d.year, start_d.month, start_d.day))
            self._start_edit.blockSignals(False)
            self._end_edit.blockSignals(False)
        self.range_applied.emit()

    def _on_metric_changed(self, _index: int) -> None:
        self.metric_changed.emit()

    def _on_series_hovered(self, point, state: bool) -> None:
        """折线点悬停：显示该日期的原始值提示"""
        if not state:
            return
        meta = self._point_meta.get(int(point.x()))
        if not meta:
            return
        d, raw_value = meta
        metric_idx = self._metric_combo.currentIndex()
        is_count_metric = METRIC_FIELDS[metric_idx] is None
        value = fmt_int(raw_value) if is_count_metric else fmt_tokens(raw_value)
        QToolTip.showText(
            QCursor.pos(),
            f"{d.isoformat()}  {METRIC_OPTIONS[metric_idx]}：{value}",
            self,
        )
