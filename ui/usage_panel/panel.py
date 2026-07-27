"""LLM 用量查询面板（组装与数据编排）

按用量面板 Demo 的 UI 设计组装：顶部标题、KPI 卡片区（含同比）、
用量趋势面板（QtCharts 平滑折线）、使用历史面板（筛选 + 表格 + 分页）。
数据来自 UsageRecordStore 单例，本模块负责查询编排与各子组件的联动。
"""

from datetime import datetime, timedelta
from typing import Callable, Dict, List, Tuple

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from core.llm.types import UsageRecord
from core.llm.usage_record_store import get_usage_record_store
from utils.logging_tools import LoggerManager, get_name
from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.components import Message

from .formatting import fmt_int, fmt_latency, fmt_percent, fmt_tokens
from .history_table import HistoryPanel
from .kpi_card import KpiCard
from .trend_chart import TrendPanel

# 模块级日志器（LoggerManager 为单例）
_logger = LoggerManager()

# ===== 分页与刷新 =====
PAGE_SIZE = 50
INITIAL_REFRESH_DELAY_MS = 100

# ===== KPI 卡片定义：(卡片ID, 标题, get_total_stats 键, 格式化函数) =====
KPI_DEFINITIONS: Tuple[Tuple[str, str, str, Callable[[float], str]], ...] = (
    ("total_requests", "总请求数", "total_requests", fmt_int),
    ("total_input", "输入 Token", "total_input_tokens", fmt_tokens),
    ("total_output", "输出 Token", "total_output_tokens", fmt_tokens),
    ("total_tokens", "总 Token", "total_tokens", fmt_tokens),
    ("cache_hit_rate", "缓存命中率", "cache_hit_rate", fmt_percent),
    ("avg_duration", "平均耗时", "avg_duration_ms", fmt_latency),
)


class UsagePanel(QWidget):
    """LLM 用量查询面板

    由主窗口「AI → 用量查询」以模态对话框承载。
    对外接口与旧版保持一致：``data_refreshed`` 信号与 ``refresh_data()`` 方法。

    Signals:
        data_refreshed: 数据刷新完成后发出
    """

    data_refreshed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = get_usage_record_store()
        self._current_page = 0
        # 当前筛选条件下的总记录数（明细表格为存储层分页，不缓存全量记录）
        self._total_count = 0

        self._init_ui()
        self._connect_signals()
        QTimer.singleShot(INITIAL_REFRESH_DELAY_MS, self.refresh_data)

    # ------------------------------------------------------------------ UI

    def _init_ui(self) -> None:
        # 内容区固定高度，整体放入垂直滚动区：窗口缩小时页面上下滚动，
        # 各区块（KPI / 趋势 / 历史）高度保持不变
        scroll_area = QScrollArea(self)
        scroll_area.setObjectName("usageScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(14, 12, 14, 12)
        content_layout.setSpacing(10)

        content_layout.addLayout(self._build_header())
        content_layout.addLayout(self._build_kpi_row(content))

        self._trend_panel = TrendPanel(content)
        content_layout.addWidget(self._trend_panel)

        self._history_panel = HistoryPanel(content)
        content_layout.addWidget(self._history_panel)
        # 固定高度区块之外的剩余空间沉到底部，避免区块被拉高
        content_layout.addStretch()

        scroll_area.setWidget(content)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(scroll_area)

    @staticmethod
    def _build_header() -> QHBoxLayout:
        """顶部标题行（主标题 + 副标题）"""
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("AI 用量面板")
        title_font = QFont()
        title_font.setPixelSize(T("font.title.lg"))
        title_font.setBold(True)
        title.setFont(title_font)
        subtitle = QLabel("LLM API Usage Overview")
        set_property(subtitle, "role", "secondary")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        return header

    def _build_kpi_row(self, parent: QWidget) -> QHBoxLayout:
        """KPI 卡片行（6 张卡片等宽排列）"""
        row = QHBoxLayout()
        row.setSpacing(12)
        self._kpi_cards: Dict[str, KpiCard] = {}
        for card_id, title, _stats_key, _formatter in KPI_DEFINITIONS:
            card = KpiCard(title, parent)
            self._kpi_cards[card_id] = card
            row.addWidget(card, stretch=1)
        return row

    def _connect_signals(self) -> None:
        self._trend_panel.range_applied.connect(self.refresh_data)
        self._trend_panel.metric_changed.connect(self._on_metric_changed)
        self._history_panel.filters_changed.connect(self.refresh_data)
        self._history_panel.refresh_requested.connect(self.refresh_data)
        self._history_panel.prev_page_requested.connect(self._prev_page)
        self._history_panel.next_page_requested.connect(self._next_page)

    # ------------------------------------------------------------- 数据刷新

    def refresh_data(self) -> None:
        """全量刷新：KPI（含同比）、筛选项、趋势图与明细表格"""
        try:
            self._refresh_kpis()
            all_records = self._query_filtered_records()
            self._total_count = len(all_records)
            self._update_filter_options(all_records)
            self._trend_panel.update_series(all_records)
            self._current_page = 0
            self._update_table()
            self.data_refreshed.emit()
        except Exception as e:
            _logger.error(get_name(), f"刷新用量数据失败: {e}")
            Message.warning(self, f"刷新用量数据失败:\n{str(e)}")

    def _refresh_kpis(self) -> None:
        """刷新 KPI 卡片数值与上一等长周期的同比"""
        start_time, end_time = self._trend_panel.current_range()
        prev_start, prev_end = self._previous_period(start_time, end_time)
        current_stats = self._store.get_total_stats(start_time=start_time, end_time=end_time)
        previous_stats = self._store.get_total_stats(start_time=prev_start, end_time=prev_end)

        for card_id, _title, stats_key, formatter in KPI_DEFINITIONS:
            card = self._kpi_cards[card_id]
            current_value = current_stats.get(stats_key, 0)
            card.set_value(formatter(current_value))
            card.set_delta(current_value, previous_stats.get(stats_key, 0))

    @staticmethod
    def _previous_period(start: datetime, end: datetime) -> Tuple[datetime, datetime]:
        """计算与 [start, end] 等长的前一周期（用于同比）

        Args:
            start: 当前周期起始时间（当天 00:00）
            end: 当前周期结束时间（当天 23:59:59）

        Returns:
            Tuple[datetime, datetime]: 前一周期的 (起始, 结束)
        """
        days = (end.date() - start.date()).days + 1
        prev_end = start - timedelta(microseconds=1)
        prev_start = prev_end - timedelta(days=days) + timedelta(microseconds=1)
        return prev_start, prev_end

    def _query_filtered_records(self) -> List[UsageRecord]:
        """按当前范围与筛选条件查询全量记录（供趋势聚合与总数统计）"""
        start_time, end_time = self._trend_panel.current_range()
        filters = self._history_panel.current_filters()
        return self._store.get_records(
            start_time=start_time,
            end_time=end_time,
            provider=filters["provider"],
            model=filters["model"],
            conversation_id=filters["conversation_id"],
            limit=None,
        )

    def _update_filter_options(self, records: List[UsageRecord]) -> None:
        """根据实际记录动态更新 Provider / Model 下拉选项"""
        self._history_panel.set_provider_options(self._query_providers())
        models = sorted({r.model for r in records if r.model})
        self._history_panel.set_model_options(models)

    def _query_providers(self) -> List[str]:
        """查询当前时间范围内出现过的 Provider 列表

        Returns:
            List[str]: 排序后的 Provider 名称；聚合查询失败时降级为空列表
                （仅显示「全部」），不阻断面板刷新
        """
        try:
            start_time, end_time = self._trend_panel.current_range()
            agg = self._store.aggregate(start_time=start_time, end_time=end_time, group_by="provider")
            return sorted(g["group_key"] for g in agg.get("groups", []) if g.get("group_key"))
        except Exception as e:
            _logger.debug(get_name(), f"查询 Provider 筛选项失败，降级为仅显示「全部」: {e}")
            return []

    # ------------------------------------------------------------- 明细分页

    def _update_table(self) -> None:
        """按当前页从存储层分页查询并交由历史面板渲染（倒序：最新记录在第 1 页）"""
        start_time, end_time = self._trend_panel.current_range()
        filters = self._history_panel.current_filters()
        page_records = self._store.get_records(
            start_time=start_time,
            end_time=end_time,
            provider=filters["provider"],
            model=filters["model"],
            conversation_id=filters["conversation_id"],
            limit=PAGE_SIZE,
            offset=self._current_page * PAGE_SIZE,
            descending=True,
        )
        total_pages = max(1, (self._total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        self._history_panel.update_page(page_records, self._current_page, total_pages, self._total_count)

    def _prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self._update_table()

    def _next_page(self) -> None:
        total_pages = max(1, (self._total_count + PAGE_SIZE - 1) // PAGE_SIZE)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._update_table()

    # ------------------------------------------------------------- 事件

    def _on_metric_changed(self) -> None:
        """趋势指标切换：仅重绘图表，不刷新 KPI 与表格"""
        try:
            self._trend_panel.update_series(self._query_filtered_records())
        except Exception as e:
            _logger.error(get_name(), f"刷新用量趋势图失败: {e}")
            Message.warning(self, f"刷新用量趋势图失败:\n{str(e)}")
