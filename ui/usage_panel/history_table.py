"""使用历史面板（筛选 + 明细表格 + 分页）

展示用量记录明细：Provider / Model / 对话 ID 筛选、10 列只读表格、
上一页 / 下一页分页控件。面板自身不访问数据层，
筛选条件通过 ``current_filters`` 暴露，数据由外部传入 ``update_page`` 渲染。
"""

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel,
    QTableWidgetItem, QVBoxLayout,
)

from core.i18n import get_language_manager, tr
from core.llm.types import UsageRecord
from InstructionX_UIKit import T, set_property
from InstructionX_UIKit.components import Button, ComboBox, LineEdit, Table

from .formatting import fmt_latency, to_local_time


def _all_option_text() -> str:
    """「全部」筛选项文案（运行时取词，随语言切换更新）"""
    return tr("usage_panel", "filter.all")


# ===== 表格结构 =====
# 表头 i18n 键（usage_panel 分组），显示文案在 _retranslate_ui 中统一取词
TABLE_HEADER_KEYS = (
    "table.header.time", "table.header.provider", "table.header.model",
    "table.header.input", "table.header.output", "table.header.total_tokens",
    "table.header.cache_hit", "table.header.cached_tokens",
    "table.header.duration", "table.header.stream",
)
COLUMN_WIDTHS = (140, 80, 120, 70, 70, 80, 70, 80, 80, 50)
# 右对齐的数值列索引
NUMERIC_COLUMNS = (3, 4, 5, 7, 8)
# 「缓存命中」列索引（命中时绿色高亮）
CACHE_HIT_COLUMN = 6
ROW_HEIGHT = 27
# 自适应高度的安全余量（px）：补偿表体边框 / 表头实测偏差，保证整页完整显示
FIT_HEIGHT_SLACK = 4
TIME_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"

# ===== 控件尺寸 =====
CONV_INPUT_MAX_WIDTH = 200
FILTER_COMBO_MIN_WIDTH = 100
FILTER_COMBO_MAX_WIDTH = 160
PAGE_BTN_MIN_WIDTH = 72
PAGE_LABEL_MIN_WIDTH = 180


def _panel_title(text: str) -> QLabel:
    """子面板标题标签（font.title.sm + semibold）"""
    label = QLabel(text)
    font = QFont()
    font.setPixelSize(T("font.title.sm"))
    font.setWeight(QFont.Weight.DemiBold)
    label.setFont(font)
    return label


def _sub_panel_qss() -> str:
    """子面板容器（卡片底 + 边框 + 圆角）的实例 QSS，颜色取 UIKit 令牌"""
    return (
        f"#usageSubPanel {{ background-color: {T('color.bg.elevated')};"
        f" border: 1px solid {T('color.border')};"
        f" border-radius: {T('radius.md')}px; }}"
    )


class HistoryPanel(QFrame):
    """使用历史面板

    包含筛选工具行（Provider / Model / 对话 ID / 刷新按钮）、
    明细表格与分页控件。筛选与翻页动作以信号形式通知外部，
    由外部完成数据查询后回调 ``update_page`` 渲染。

    Signals:
        filters_changed: Provider / Model 筛选变更
        refresh_requested: 用户点击「刷新」按钮
        prev_page_requested: 用户点击「上一页」
        next_page_requested: 用户点击「下一页」
    """

    filters_changed = Signal()
    refresh_requested = Signal()
    prev_page_requested = Signal()
    next_page_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("usageSubPanel")
        self.setStyleSheet(_sub_panel_qss())

        # 当前下拉选项（语言切换时按原选项重建，仅更新「全部」文案）
        self._provider_options: List[str] = []
        self._model_options: List[str] = []
        # 最近一次分页状态（语言切换时按原值重排分页文案）
        self._last_page: Optional[Tuple[int, int, int]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 8)
        layout.setSpacing(6)

        layout.addLayout(self._build_header())
        layout.addLayout(self._build_toolbar())
        layout.addWidget(self._build_table(), stretch=1)
        layout.addLayout(self._build_pagination())

        self._connect_signals()
        self._retranslate_ui()
        get_language_manager().language_changed.connect(self._retranslate_ui)
        # 初始按 0 行计算高度，首次数据刷新后随当前页行数自动调整
        self._fit_height_to_rows(0)

    # ------------------------------------------------------------------ UI

    def _build_header(self) -> QHBoxLayout:
        """面板标题行（文案由 ``_retranslate_ui`` 统一设置）"""
        header = QHBoxLayout()
        self._title_label = _panel_title("")
        header.addWidget(self._title_label)
        header.addStretch()
        return header

    def _build_toolbar(self) -> QHBoxLayout:
        """筛选工具行：Provider / Model / 对话 ID / 刷新按钮"""
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        self._provider_combo = self._make_filter_combo()
        self._model_combo = self._make_filter_combo()
        self._provider_label = self._make_filter_label("")
        self._model_label = self._make_filter_label("")

        self._conv_label = self._make_filter_label("")
        self._conv_id_input = LineEdit()
        self._conv_id_input.setMaximumWidth(CONV_INPUT_MAX_WIDTH)

        self._refresh_btn = Button("", variant="primary")
        self._refresh_btn.setMinimumWidth(PAGE_BTN_MIN_WIDTH)

        toolbar.addWidget(self._provider_label)
        toolbar.addWidget(self._provider_combo)
        toolbar.addWidget(self._model_label)
        toolbar.addWidget(self._model_combo)
        toolbar.addWidget(self._conv_label)
        toolbar.addWidget(self._conv_id_input)
        toolbar.addStretch()
        toolbar.addWidget(self._refresh_btn)
        return toolbar

    @staticmethod
    def _make_filter_label(text: str) -> QLabel:
        label = QLabel(text)
        set_property(label, "role", "secondary")
        return label

    @staticmethod
    def _make_filter_combo() -> ComboBox:
        combo = ComboBox()
        combo.setMinimumWidth(FILTER_COMBO_MIN_WIDTH)
        combo.setMaximumWidth(FILTER_COMBO_MAX_WIDTH)
        return combo

    def _build_table(self) -> Table:
        """创建 10 列只读明细表格（UIKit Table：斑马纹/整行选择/禁编辑）"""
        self._table = Table(0, len(TABLE_HEADER_KEYS), sortable=False)
        # UIKit Table 默认行高 32，此处沿用面板的紧凑行高
        self._table.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        for col, width in enumerate(COLUMN_WIDTHS):
            self._table.setColumnWidth(col, width)
        return self._table

    def _build_pagination(self) -> QHBoxLayout:
        """分页控件行：上一页 / 页码信息 / 下一页"""
        pagination = QHBoxLayout()
        pagination.setContentsMargins(0, 4, 0, 0)

        self._prev_btn = Button("", variant="default")
        self._prev_btn.setMinimumWidth(PAGE_BTN_MIN_WIDTH)
        self._prev_btn.setEnabled(False)

        self._page_label = QLabel()
        set_property(self._page_label, "role", "secondary")
        self._page_label.setMinimumWidth(PAGE_LABEL_MIN_WIDTH)
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._next_btn = Button("", variant="default")
        self._next_btn.setMinimumWidth(PAGE_BTN_MIN_WIDTH)
        self._next_btn.setEnabled(False)

        pagination.addStretch()
        pagination.addWidget(self._prev_btn)
        pagination.addSpacing(16)
        pagination.addWidget(self._page_label)
        pagination.addSpacing(16)
        pagination.addWidget(self._next_btn)
        pagination.addStretch()
        return pagination

    def _retranslate_ui(self) -> None:
        """按当前语言重设面板全部用户可见文案（语言切换时自动触发）"""
        self._title_label.setText(tr("usage_panel", "table.title"))
        self._provider_label.setText(tr("usage_panel", "filter.provider"))
        self._model_label.setText(tr("usage_panel", "filter.model"))
        self._conv_label.setText(tr("usage_panel", "filter.conversation_id"))
        self._conv_id_input.setPlaceholderText(
            tr("usage_panel", "filter.conversation_id_placeholder"))
        self._refresh_btn.setText(tr("common", "refresh"))
        self._prev_btn.setText(tr("usage_panel", "page.prev"))
        self._next_btn.setText(tr("usage_panel", "page.next"))
        self._retranslate_accessible_names()
        self._table.setHorizontalHeaderLabels(
            [tr("usage_panel", key) for key in TABLE_HEADER_KEYS])
        self._reset_combo_options(self._provider_combo, self._provider_options)
        self._reset_combo_options(self._model_combo, self._model_options)
        self._update_page_label()

    def _retranslate_accessible_names(self) -> None:
        """按当前语言重设各控件的无障碍名称"""
        self._provider_combo.setAccessibleName(tr("usage_panel", "a11y.provider_filter"))
        self._model_combo.setAccessibleName(tr("usage_panel", "a11y.model_filter"))
        self._conv_id_input.setAccessibleName(tr("usage_panel", "a11y.conversation_id_input"))
        self._refresh_btn.setAccessibleName(tr("usage_panel", "a11y.refresh"))
        self._table.setAccessibleName(tr("usage_panel", "a11y.table"))
        self._prev_btn.setAccessibleName(tr("usage_panel", "page.prev"))
        self._next_btn.setAccessibleName(tr("usage_panel", "page.next"))

    def _update_page_label(self) -> None:
        """按当前语言重设分页信息（未刷新过数据时显示初始占位文案）"""
        if self._last_page is None:
            self._page_label.setText(tr("usage_panel", "page.initial"))
            return
        current_page, total_pages, total_count = self._last_page
        self._page_label.setText(tr(
            "usage_panel", "page.info",
            current=current_page + 1, total=total_pages, count=total_count))

    def _connect_signals(self) -> None:
        self._provider_combo.currentTextChanged.connect(self._on_filter_changed)
        self._model_combo.currentTextChanged.connect(self._on_filter_changed)
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._prev_btn.clicked.connect(self.prev_page_requested.emit)
        self._next_btn.clicked.connect(self.next_page_requested.emit)

    def _on_filter_changed(self) -> None:
        self.filters_changed.emit()

    # ------------------------------------------------------------- 公共接口

    def current_filters(self) -> Dict[str, Optional[str]]:
        """当前筛选条件（「全部」/空串归一化为 None）

        Returns:
            Dict[str, Optional[str]]: provider / model / conversation_id 三个键
        """
        provider = self._provider_combo.currentText()
        model = self._model_combo.currentText()
        conversation_id = self._conv_id_input.text().strip()
        return {
            "provider": provider if provider != _all_option_text() else None,
            "model": model if model != _all_option_text() else None,
            "conversation_id": conversation_id if conversation_id else None,
        }

    def set_provider_options(self, providers: List[str]) -> None:
        """更新 Provider 下拉选项，尽量保留当前选中项

        Args:
            providers: 实际记录中出现过的 Provider 名称列表（无需包含「全部」）
        """
        self._provider_options = providers
        self._reset_combo_options(self._provider_combo, providers)

    def set_model_options(self, models: List[str]) -> None:
        """更新 Model 下拉选项，尽量保留当前选中项

        Args:
            models: 当前筛选条件下出现过的 Model 名称列表（无需包含「全部」）
        """
        self._model_options = models
        self._reset_combo_options(self._model_combo, models)

    @staticmethod
    def _reset_combo_options(combo: ComboBox, options: List[str]) -> None:
        """重建下拉选项并保留选中项；阻断信号避免触发级联刷新"""
        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(_all_option_text())
        combo.addItems(options)
        if current in [_all_option_text(), *options]:
            combo.setCurrentText(current)
        combo.blockSignals(False)

    def update_page(
        self, records: List[UsageRecord], current_page: int, total_pages: int, total_count: int
    ) -> None:
        """渲染当前页记录并更新分页控件状态

        Args:
            records: 当前页的用量记录（由外部按页查询）
            current_page: 当前页码（从 0 开始）
            total_pages: 总页数（至少为 1）
            total_count: 当前筛选条件下的总记录数
        """
        self._table.setRowCount(len(records))
        for row, record in enumerate(records):
            self._fill_row(row, record)

        self._last_page = (current_page, total_pages, total_count)
        self._update_page_label()
        self._prev_btn.setEnabled(current_page > 0)
        self._next_btn.setEnabled(current_page < total_pages - 1)
        # 面板高度随当前页行数自适应，保证整页记录完整显示
        self._fit_height_to_rows(len(records))

    def _fit_height_to_rows(self, row_count: int) -> None:
        """按当前页行数调整面板固定高度（表头 + 工具行 + 分页行 + 行数 × 行高）

        Args:
            row_count: 当前页显示的记录行数
        """
        layout = self.layout()
        margins = layout.contentsMargins()
        # 表格所需高度：横表头 + 全部行 + 表体边框 + 安全余量
        height = (
            self._table.horizontalHeader().height()
            + row_count * ROW_HEIGHT
            + self._table.frameWidth() * 2
            + FIT_HEIGHT_SLACK
        )
        # 累加表头行 / 工具行 / 分页行等表格之外的子布局高度
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() is self._table or item.layout() is None:
                continue
            height += item.layout().sizeHint().height()
        # 布局间距（子项数量 - 1 个间隔）与面板上下边距
        height += layout.spacing() * (layout.count() - 1)
        height += margins.top() + margins.bottom()
        self.setFixedHeight(height)

    # ------------------------------------------------------------- 表格渲染

    def _fill_row(self, row: int, record: UsageRecord) -> None:
        """填充一行记录（时间转本地时区显示，缓存命中绿色高亮）"""
        cells = (
            to_local_time(record.timestamp).strftime(TIME_DISPLAY_FORMAT),
            record.provider,
            record.model,
            f"{record.input_tokens:,}",
            f"{record.output_tokens:,}",
            f"{record.total_tokens:,}",
            tr("common", "yes") if record.cache_hit else tr("common", "no"),
            f"{record.cached_tokens:,}",
            fmt_latency(record.duration_ms),
            tr("common", "yes") if record.is_stream else tr("common", "no"),
        )
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            if col in NUMERIC_COLUMNS:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if record.cache_hit and col == CACHE_HIT_COLUMN:
                item.setForeground(QColor(T("color.success")))
            self._table.setItem(row, col, item)
