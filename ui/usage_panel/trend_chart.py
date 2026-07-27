"""用量趋势面板（UIKit 原生图表引擎平滑折线图）

移植自用量面板 Demo：时间范围选择（近 7 天 / 近 30 天 / 自定义）、
指标切换（请求数 / 输入 Token / 输出 Token）、平滑折线、悬停提示与区间状态文本。
图表使用 InstructionX_UIKit 原生图表引擎（ChartWidget + set_option），
配色实时取自 UIKit 令牌并随主题切换自动换肤。
"""

from datetime import date, datetime, timedelta
from typing import List, Optional, Tuple

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from core.llm.types import UsageRecord
from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.charts import ChartWidget
from InstructionX_UIKit.components import Button, ComboBox, DatePicker

from .formatting import local_tz, pick_token_scale, to_local_time

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
# 面积填充透明度（面积图叠加在平滑折线下方）
AREA_FILL_OPACITY = 0.18

# ===== 日期显示格式 =====
DATE_DISPLAY_FORMAT = "yyyy-MM-dd"
AXIS_DATE_FORMAT = "%m-%d"

# ===== 图表网格边距 =====
GRID_LEFT = 56
GRID_RIGHT = 24
GRID_TOP = 24
GRID_BOTTOM = 36


class TrendPanel(QFrame):
    """用量趋势面板

    包含范围/指标工具行、UIKit ChartWidget 折线图与区间状态文本。
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

        self._connect_signals()
        self._on_range_changed(DEFAULT_RANGE_INDEX)

    # ------------------------------------------------------------------ UI

    def _build_header(self) -> QHBoxLayout:
        """面板标题行"""
        header = QHBoxLayout()
        title = QLabel("用量趋势")
        font = QFont()
        font.setPixelSize(T("font.title.sm"))
        font.setWeight(QFont.Weight.DemiBold)
        title.setFont(font)
        header.addWidget(title)
        header.addStretch()
        return header

    def _build_toolbar(self) -> QHBoxLayout:
        """范围选择 + 自定义日期 + 指标切换工具行"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._range_combo = ComboBox(items=RANGE_OPTIONS)
        self._range_combo.setAccessibleName("时间范围选择")
        self._range_combo.setCurrentIndex(DEFAULT_RANGE_INDEX)
        toolbar.addWidget(self._range_combo)

        today = date.today()
        self._start_edit = self._make_date_edit(today - timedelta(days=RANGE_DAY_SPANS[1] - 1))
        self._start_edit.setAccessibleName("起始日期")
        self._end_edit = self._make_date_edit(today)
        self._end_edit.setAccessibleName("结束日期")
        to_label = QLabel("至")
        set_property(to_label, "role", "secondary")
        self._apply_btn = Button("应用", variant="default")
        self._apply_btn.setAccessibleName("应用自定义日期范围")

        toolbar.addWidget(self._start_edit)
        toolbar.addWidget(to_label)
        toolbar.addWidget(self._end_edit)
        toolbar.addWidget(self._apply_btn)
        toolbar.addStretch()

        self._metric_combo = ComboBox(items=METRIC_OPTIONS)
        self._metric_combo.setAccessibleName("趋势指标切换")
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
        """将聚合后的序列构建为 ECharts 风格 option 并交给 ChartWidget"""
        max_raw = max((v for _, v in points), default=0)
        is_count_metric = METRIC_FIELDS[metric_idx] is None
        scale, unit = (1.0, "") if is_count_metric else pick_token_scale(max_raw)

        self._chart.set_option({
            "legend": {"show": True, "orient": "horizontal"},
            "tooltip": {"show": True, "trigger": "axis"},
            "grid": {
                "left": GRID_LEFT, "right": GRID_RIGHT,
                "top": GRID_TOP, "bottom": GRID_BOTTOM,
            },
            "xAxis": {
                "type": "category",
                "data": [d.strftime(AXIS_DATE_FORMAT) for d, _ in points],
            },
            "yAxis": {"type": "value"},
            "series": [{
                "type": "line",
                "name": METRIC_OPTIONS[metric_idx] + unit,
                "smooth": True,
                "showSymbol": True,
                "areaStyle": {"opacity": AREA_FILL_OPACITY},
                "data": [v / scale for _, v in points],
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
