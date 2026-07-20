"""KPI 统计卡片组件

移植自用量面板 Demo：每张卡片包含小标题、大数值与「较上周期 ±x.x%」同比小字。
同比趋势通过 Qt 动态属性 trend（up/down/flat）驱动 QSS 变色，
样式定义见 utils/style_qss/styles/usage_panel.qss。
"""

from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout

# ===== 卡片尺寸 =====
CARD_HEIGHT = 92

# ===== 同比趋势取值（与 usage_panel.qss 中 #kpiDelta[trend="..."] 选择器对应）=====
TREND_UP = "up"
TREND_DOWN = "down"
TREND_FLAT = "flat"

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
        self.setObjectName("kpiCard")
        # 固定高度：窗口缩小时由外层滚动区接管，卡片自身不缩水
        self.setFixedHeight(CARD_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("kpiTitle")

        self._value_label = QLabel("—")
        self._value_label.setObjectName("kpiValue")

        self._delta_label = QLabel("较上周期 —")
        self._delta_label.setObjectName("kpiDelta")
        self._delta_label.setProperty("trend", TREND_FLAT)

        # 文本标签水平方向允许压缩（Ignored = 最小宽度为 0），
        # 避免 6 张卡片的文本宽度把整个内容区的最小宽度撑出窗口
        for label in (title_label, self._value_label, self._delta_label):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

        layout.addWidget(title_label)
        layout.addWidget(self._value_label)
        layout.addWidget(self._delta_label)
        layout.addStretch()

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
        if previous <= 0:
            self._apply_delta("较上周期 —", TREND_FLAT)
            return
        pct = (current - previous) / previous * _PERCENT_BASE
        trend = TREND_UP if pct >= 0 else TREND_DOWN
        self._apply_delta(f"较上周期 {pct:+.1f}%", trend)

    def _apply_delta(self, text: str, trend: str) -> None:
        """更新同比文本并按需刷新 trend 属性触发 QSS 重绘"""
        self._delta_label.setText(text)
        if self._delta_label.property("trend") == trend:
            return
        self._delta_label.setProperty("trend", trend)
        # 动态属性变化后需 unpolish/polish 才会重新匹配 QSS 选择器
        self._delta_label.style().unpolish(self._delta_label)
        self._delta_label.style().polish(self._delta_label)
