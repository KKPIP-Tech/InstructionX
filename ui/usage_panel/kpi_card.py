"""KPI 统计卡片组件

移植自用量面板 Demo：每张卡片包含小标题、大数值与「较上周期 ±x.x%」同比小字。
同比趋势（up/down/flat）直接以 UIKit 令牌着色（成功绿涨 / 危险红降 / 灰无数据），
卡片外观（底色/边框/圆角）同样取自令牌；对话框为短生命周期，颜色在构建时取一次。
"""

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

from core.i18n import get_language_manager, tr
from InstructionX_UIKit import T, set_property

# ===== 卡片尺寸 =====
CARD_HEIGHT = 92

# ===== 同比趋势取值 =====
TREND_UP = "up"
TREND_DOWN = "down"
TREND_FLAT = "flat"

#: 同比趋势 → UIKit 颜色令牌
_TREND_COLOR_KEYS = {
    TREND_UP: "color.success",
    TREND_DOWN: "color.danger",
    TREND_FLAT: "color.text.secondary",
}

# 同比百分比换算基数
_PERCENT_BASE = 100.0


class KpiCard(QFrame):
    """单张 KPI 统计卡片

    展示一项聚合指标（如总请求数、缓存命中率）的当前值，
    并与上一等长周期对比显示同比涨跌幅（绿色涨 / 红色降 / 灰色无数据）。

    Example:
        >>> card = KpiCard("总请求数")
        >>> card.set_value("12,847")
        >>> card.set_delta(current=12847, previous=11420)
    """

    def __init__(self, title: str, parent=None):
        """初始化卡片

        Args:
            title: 指标标题（如「总请求数」）
            parent: 父控件
        """
        super().__init__(parent)
        # 最近一次的同比数值（语言切换时按原值重算文案）
        self._last_current = 0.0
        self._last_previous = 0.0
        # 固定高度：窗口缩小时由外层滚动区接管，卡片自身不缩水
        self.setFixedHeight(CARD_HEIGHT)
        self.setStyleSheet(
            f"KpiCard {{ background-color: {T('color.bg.elevated')};"
            f" border: 1px solid {T('color.border')};"
            f" border-radius: {T('radius.md')}px; }}"
        )

        self._build_ui(title)
        self._retranslate_ui()
        get_language_manager().language_changed.connect(self._retranslate_ui)

    def _build_ui(self, title: str) -> None:
        """构建卡片内部布局（标题 / 数值 / 同比三行标签）"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        self._title_label = QLabel(title)
        set_property(self._title_label, "role", "secondary")

        self._value_label = QLabel("—")
        self._value_label.setStyleSheet(
            f"font-size: {T('font.display')}px; font-weight: 700;")

        self._delta_label = QLabel()
        self._trend = TREND_FLAT
        self._apply_trend_color(TREND_FLAT)

        # 文本标签水平方向允许压缩（Ignored = 最小宽度为 0），
        # 避免 6 张卡片的文本宽度把整个内容区的最小宽度撑出窗口
        for label in (self._title_label, self._value_label, self._delta_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
        layout.addWidget(self._delta_label)
        layout.addStretch()

    def set_title(self, title: str) -> None:
        """设置指标标题文本（语言切换时由面板重设）

        Args:
            title: 已按当前语言取词的指标标题
        """
        self._title_label.setText(title)

    def set_value(self, text: str) -> None:
        """设置指标数值文本

        Args:
            text: 已格式化好的数值文本（如 "12,847"、"8.42 M"）
        """
        self._value_label.setText(text)

    def set_delta(self, current: float, previous: float) -> None:
        """设置同比文本与趋势颜色

        Args:
            current: 当前周期指标值
            previous: 上一等长周期指标值；<= 0 时视为无数据，显示占位符
        """
        self._last_current = current
        self._last_previous = previous
        if previous <= 0:
            self._apply_delta(tr("usage_panel", "kpi.delta_empty"), TREND_FLAT)
            return
        pct = (current - previous) / previous * _PERCENT_BASE
        trend = TREND_UP if pct >= 0 else TREND_DOWN
        self._apply_delta(tr("usage_panel", "kpi.delta", pct=pct), trend)

    def _retranslate_ui(self) -> None:
        """按当前语言重设文案（同比小字按最近一次的数值重算；标题由面板重设）"""
        self.set_delta(self._last_current, self._last_previous)

    def _apply_delta(self, text: str, trend: str) -> None:
        """更新同比文本与趋势颜色"""
        self._delta_label.setText(text)
        if self._trend != trend:
            self._trend = trend
            self._apply_trend_color(trend)

    def _apply_trend_color(self, trend: str) -> None:
        """按趋势以 UIKit 令牌着色同比小字"""
        color = T(_TREND_COLOR_KEYS.get(trend, "color.text.secondary"))
        self._delta_label.setStyleSheet(
            f"color: {color}; font-size: {T('font.xs')}px;")
