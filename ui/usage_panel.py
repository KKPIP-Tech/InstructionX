"""LLM 用量查询面板

提供 Token 用量统计、趋势图表和明细查询功能的 UI 面板。
包含：统计卡片、趋势图、筛选栏、明细表格。
"""

import os
from datetime import datetime, timedelta
from typing import List, Any, Optional, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView,
    QFrame, QDateEdit, QLineEdit, QGroupBox,
    QAbstractItemView, QMessageBox,
)
from PySide6.QtCore import Qt, QDate, Signal, QTimer, QThread, QObject
from PySide6.QtGui import QColor, QFont, QFontDatabase

from core.llm.usage_record_store import get_usage_record_store
from core.llm.types import UsageRecord
from utils.font_map import FontMap, FontFamily, FontVariant

# Matplotlib 导入和配置
try:
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import matplotlib.pyplot as plt
    import matplotlib
    MATPLOTLIB_AVAILABLE = True
    
    # 配置 Matplotlib 中文字 体
    def setup_chinese_font():
        """设置 Matplotlib 中文字体"""
        # 尝试使用系统自带的中文字体
        chinese_fonts = [
            'Microsoft YaHei',  # Windows 微软雅黑
            'SimHei',           # Windows 黑体
            'WenQuanYi Micro Hei',  # Linux
            'PingFang SC',      # macOS
            'Heiti TC',         # macOS
            'Arial Unicode MS', # 备用
        ]
        
        font_found = False
        for font in chinese_fonts:
            try:
                # 测试字体是否可用
                from matplotlib import font_manager
                if any(f.name == font for f in font_manager.fontManager.ttflist):
                    plt.rcParams['font.sans-serif'] = [font] + plt.rcParams['font.sans-serif']
                    plt.rcParams['axes.unicode_minus'] = False  # 解决负号显示问题
                    font_found = True
                    break
            except:
                continue
        
        if not font_found:
            # 如果找不到中文字体，使用默认字体并设置 fallback
            plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
            plt.rcParams['axes.unicode_minus'] = False
    
    setup_chinese_font()
    
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ===================================================================
# 模块级工具函数
# ===================================================================

# ZenDots 字体只需注册一次（模块级缓存字体族名）
_zendots_font_family: Optional[str] = None


def _ensure_zendots_font() -> Optional[str]:
    """注册 ZenDots 字体并返回字体族名（仅首次调用真正执行注册）"""
    global _zendots_font_family
    if _zendots_font_family is not None:
        return _zendots_font_family

    font_path = FontMap.get_path(FontFamily.ZEN_DOTS, FontVariant.REGULAR)
    if font_path and os.path.exists(font_path):
        font_id = QFontDatabase.addApplicationFont(font_path)
        if font_id != -1:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _zendots_font_family = families[0]
    return _zendots_font_family


def _local_tz():
    """获取本地时区（aware），用于与 UTC aware 的记录时间戳比较"""
    return datetime.now().astimezone().tzinfo


def _to_local_time(ts: datetime) -> datetime:
    """将记录时间戳转换为本地时间显示（aware 时转换，naive 原样返回）"""
    if ts.tzinfo is not None:
        return ts.astimezone()
    return ts


class ChartWorker(QObject):
    """图表生成工作线程"""
    
    chart_ready = Signal(object)  # 发送图表数据
    error_occurred = Signal(str)
    
    def __init__(self):
        super().__init__()
        self._records: List[UsageRecord] = []
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
        self._is_dark = False
        
    def set_data(self, records: List[UsageRecord], start_time: datetime, end_time: datetime, is_dark: bool):
        """设置图表数据"""
        self._records = records
        self._start_time = start_time
        self._end_time = end_time
        self._is_dark = is_dark
        
    def generate_chart(self) -> Optional[Dict]:
        """生成图表数据（在后台线程中执行）"""
        if not MATPLOTLIB_AVAILABLE or not self._records:
            return None
            
        try:
            # 按日期聚合数据
            from collections import defaultdict
            daily = defaultdict(lambda: {"input": 0, "output": 0})
            for r in self._records:
                # 记录时间戳为 UTC aware，聚合前转换为本地时间
                day = _to_local_time(r.timestamp).strftime("%m-%d")
                daily[day]["input"] += r.input_tokens
                daily[day]["output"] += r.output_tokens
                
            if not daily:
                return None
                
            # 排序并限制显示最近 10 天
            days = sorted(daily.keys())
            if len(days) > 10:
                days = days[-10:]
                
            input_vals = [daily[d]["input"] for d in days]
            output_vals = [daily[d]["output"] for d in days]
            
            return {
                "days": days,
                "input_vals": input_vals,
                "output_vals": output_vals,
                "is_dark": self._is_dark
            }
        except Exception as e:
            self.error_occurred.emit(str(e))
            return None
            
    def run(self):
        """运行工作线程"""
        result = self.generate_chart()
        if result:
            self.chart_ready.emit(result)


class StatsCard(QFrame):
    """现代化统计卡片组件"""

    # 预定义的配色方案 (主题色, 强调色)
    COLOR_SCHEMES = {
        "blue": ("#3B82F6", "#60A5FA"),      # 蓝色系 - 总请求数
        "cyan": ("#06B6D4", "#22D3EE"),      # 青色系 - 输入 Token
        "purple": ("#8B5CF6", "#A78BFA"),    # 紫色系 - 输出 Token
        "orange": ("#F59E0B", "#FBBF24"),    # 橙色系 - 总 Token
        "green": ("#10B981", "#34D399"),     # 绿色系 - 缓存命中率
        "red": ("#EF4444", "#F87171"),       # 红色系 - 平均耗时
    }

    def __init__(self, title: str, value: str = "0", color_scheme: str = "blue", parent=None):
        super().__init__(parent)
        self._color_scheme = color_scheme
        self._title = title
        self._value = value
        
        # 设置卡片样式 - 自适应宽度
        self.setObjectName("statsCard")
        self.setMinimumWidth(120)
        self.setMinimumHeight(90)
        
        # 启用鼠标追踪以实现悬停效果
        self.setMouseTracking(True)
        
        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        """设置 UI 布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)
        
        # 标题标签
        self._title_label = QLabel(self._title)
        self._title_label.setObjectName("statsCardTitle")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        
        # 数值标签 - 使用 ZenDots 字体
        self._value_label = QLabel(self._value)
        self._value_label.setObjectName("statsCardValue")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._apply_zendots_font()
        
        layout.addWidget(self._title_label)
        layout.addWidget(self._value_label)
        layout.addStretch()
    
    def _apply_zendots_font(self):
        """应用 ZenDots 字体到数值标签（字体注册为模块级一次性操作）"""
        family = _ensure_zendots_font()
        if family:
            font = QFont(family, 20)
            font.setWeight(QFont.Weight.Normal)
            self._value_label.setFont(font)

    def _apply_style(self):
        """应用动态样式"""
        primary, accent = self.COLOR_SCHEMES.get(self._color_scheme, self.COLOR_SCHEMES["blue"])
        
        # 根据父窗口判断当前主题
        is_dark = self._is_dark_theme()
        
        if is_dark:
            bg_color = "#1E1E1E"
            text_color = "#FFFFFF"
            title_color = "#9CA3AF"
            shadow = "0 2px 8px rgba(0, 0, 0, 0.4)"
        else:
            bg_color = "#FFFFFF"
            text_color = "#1F2937"
            title_color = "#6B7280"
            shadow = "0 2px 8px rgba(0, 0, 0, 0.1)"
        
        # 确保 ZenDots 字体已注册（模块级一次性，重复调用直接命中缓存）
        _ensure_zendots_font()

        self.setStyleSheet(f"""
            #statsCard {{
                background-color: {bg_color};
                border-radius: 12px;
                border-left: 4px solid {primary};
                {f"box-shadow: {shadow};" if is_dark else ""}
            }}
            #statsCard:hover {{
                border-left: 4px solid {accent};
            }}
            #statsCardTitle {{
                color: {title_color};
                font-size: 12px;
                font-weight: 500;
            }}
            #statsCardValue {{
                color: {text_color};
                font-size: 20px;
                font-family: "Zen Dots";
            }}
        """)

    def _is_dark_theme(self) -> bool:
        """检测当前是否为暗色主题"""
        # 通过窗口背景色判断
        window_color = self.palette().window().color()
        return window_color.lightness() < 128

    def set_value(self, value: str):
        """设置数值"""
        self._value = value
        self._value_label.setText(value)

    def enterEvent(self, event):
        """鼠标进入事件"""
        super().enterEvent(event)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        super().leaveEvent(event)
        self.setCursor(Qt.CursorShape.ArrowCursor)


class UsageChartWidget(QWidget):
    """用量趋势图表组件（使用 Matplotlib，异步渲染）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._figure: Optional[Any] = None
        self._canvas: Optional[Any] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[ChartWorker] = None
        self._setup_ui()
        self._is_dark = False

    def _setup_ui(self):
        """设置 UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        if MATPLOTLIB_AVAILABLE:
            # 创建 Matplotlib 图形（DPI 随屏幕缩放，避免高分屏模糊）
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
            self._figure = Figure(figsize=(8, 3), dpi=100 * self.devicePixelRatioF())
            self._figure.set_facecolor('none')
            self._canvas = FigureCanvas(self._figure)
            self._canvas.setStyleSheet("background: transparent;")
            layout.addWidget(self._canvas)
        else:
            # 回退到文本显示
            self._fallback_label = QLabel("图表需要 matplotlib 库")
            self._fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(self._fallback_label)

    def update_chart(self, records: List[UsageRecord], start_time: datetime, end_time: datetime):
        """异步更新图表数据"""
        if not MATPLOTLIB_AVAILABLE:
            return
            
        if not records:
            self._clear_chart()
            return
        
        # 检测主题
        self._is_dark = self._is_dark_theme()
        
        # 停止之前的线程
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        
        # 创建新的工作线程
        self._thread = QThread()
        self._worker = ChartWorker()
        self._worker.moveToThread(self._thread)
        
        # 设置数据
        self._worker.set_data(records, start_time, end_time, self._is_dark)
        
        # 连接信号
        self._worker.chart_ready.connect(self._on_chart_ready)
        self._worker.error_occurred.connect(self._on_chart_error)
        self._thread.started.connect(self._worker.run)
        # 信号驱动清理：线程结束后自动释放 worker 与线程对象，避免泄漏
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

        # 启动线程
        self._thread.start()
    
    def _on_chart_ready(self, data: Dict):
        """图表数据准备就绪（在主线程中渲染）"""
        if not self._figure or not self._canvas:
            return
            
        days = data.get("days", [])
        input_vals = data.get("input_vals", [])
        output_vals = data.get("output_vals", [])
        is_dark = data.get("is_dark", False)
        
        # 保存数据用于悬停提示
        self._chart_data = {
            "days": days,
            "input_vals": input_vals,
            "output_vals": output_vals
        }
        
        # 设置颜色方案
        if is_dark:
            bg_color = '#252526'
            text_color = '#CCCCCC'
            grid_color = '#3C3C3C'
            input_color = '#3B82F6'    # 蓝色
            output_color = '#8B5CF6'   # 紫色
        else:
            bg_color = '#FFFFFF'
            text_color = '#374151'
            grid_color = '#E5E7EB'
            input_color = '#3B82F6'    # 蓝色
            output_color = '#8B5CF6'   # 紫色
        
        # 清除旧图
        self._figure.clear()
        ax = self._figure.add_subplot(111)
        
        # 设置背景色
        ax.set_facecolor(bg_color)
        self._figure.patch.set_facecolor(bg_color)
        
        # 绘制柱状图
        x = range(len(days))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], input_vals, width,
                       label='输入', color=input_color, alpha=0.85,
                       edgecolor='none', linewidth=0)
        bars2 = ax.bar([i + width/2 for i in x], output_vals, width,
                       label='输出', color=output_color, alpha=0.85,
                       edgecolor='none', linewidth=0)
        
        # 设置标签
        ax.set_xlabel('日期', color=text_color, fontsize=10)
        ax.set_ylabel('Token 数', color=text_color, fontsize=10)
        ax.set_title('用量趋势（输入 / 输出）', color=text_color, fontsize=12, fontweight='bold', pad=15)
        
        # 设置刻度
        ax.set_xticks(x)
        ax.set_xticklabels(days, rotation=0, color=text_color, fontsize=9)
        ax.tick_params(axis='y', colors=text_color, labelsize=9)
        
        # 设置网格
        ax.yaxis.grid(True, linestyle='--', alpha=0.3, color=grid_color)
        ax.set_axisbelow(True)
        
        # 移除顶部和右侧边框
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(grid_color)
        ax.spines['bottom'].set_color(grid_color)
        
        # 添加图例
        legend = ax.legend(loc='upper right', frameon=True, fontsize=9)
        legend.get_frame().set_facecolor(bg_color)
        legend.get_frame().set_edgecolor(grid_color)
        for text in legend.get_texts():
            text.set_color(text_color)
        
        # 添加悬停交互
        self._setup_hover_interaction(ax, bars1, bars2, days, input_vals, output_vals, bg_color, text_color)
        
        # 调整布局
        self._figure.tight_layout()
        self._canvas.draw()
        # 线程清理由 finished 信号驱动（deleteLater），此处无需 quit/wait
    
    def _setup_hover_interaction(self, ax, bars1, bars2, days, input_vals, output_vals, bg_color, text_color):
        """设置鼠标悬停交互"""
        if not self._canvas:
            return
            
        # 创建悬停提示框
        self._tooltip = ax.annotate(
            '', xy=(0, 0), xytext=(10, 10),
            textcoords='offset points',
            bbox=dict(boxstyle='round,pad=0.5', fc=bg_color, ec='#666666', alpha=0.95),
            fontsize=9, color=text_color,
            zorder=100
        )
        self._tooltip.set_visible(False)
        
        # 保存条形图引用
        self._bars1 = bars1
        self._bars2 = bars2
        self._ax = ax
        
        # 连接鼠标事件
        self._canvas.mpl_connect('motion_notify_event', self._on_mouse_move)
        self._canvas.mpl_connect('axes_leave_event', self._on_mouse_leave)
    
    def _on_mouse_move(self, event):
        """鼠标移动事件处理"""
        if not self._canvas:
            return
        if not event.inaxes or not hasattr(self, '_bars1') or not hasattr(self, '_chart_data'):
            return
        
        # 检查是否在条形图上
        days = self._chart_data["days"]
        input_vals = self._chart_data["input_vals"]
        output_vals = self._chart_data["output_vals"]
        
        # 检查输入 Token 条形图
        for i, bar in enumerate(self._bars1):
            if bar.contains(event)[0]:
                day = days[i]
                val = input_vals[i]
                self._show_tooltip(event, f'日期: {day}\n输入: {val:,} tokens')
                return
        
        # 检查输出 Token 条形图
        for i, bar in enumerate(self._bars2):
            if bar.contains(event)[0]:
                day = days[i]
                val = output_vals[i]
                self._show_tooltip(event, f'日期: {day}\n输出: {val:,} tokens')
                return
        
        # 隐藏提示框
        self._hide_tooltip()
    
    def _show_tooltip(self, event, text):
        """显示悬停提示框"""
        if not self._canvas:
            return
        if hasattr(self, '_tooltip'):
            self._tooltip.xy = (event.xdata, event.ydata)
            self._tooltip.set_text(text)
            self._tooltip.set_visible(True)
            self._canvas.draw_idle()
    
    def _hide_tooltip(self):
        """隐藏悬停提示框"""
        if not self._canvas:
            return
        if hasattr(self, '_tooltip'):
            self._tooltip.set_visible(False)
            self._canvas.draw_idle()
    
    def _on_mouse_leave(self, event):
        """鼠标离开图表区域"""
        self._hide_tooltip()

    def _on_chart_error(self, error_msg: str):
        """图表生成错误"""
        print(f"Chart error: {error_msg}")

    def _clear_chart(self):
        """清空图表"""
        if MATPLOTLIB_AVAILABLE and self._figure is not None and self._canvas is not None:
            self._figure.clear()
            self._canvas.draw()

    def _is_dark_theme(self) -> bool:
        """检测当前是否为暗色主题"""
        window_color = self.palette().window().color()
        return window_color.lightness() < 128
        
    def cleanup(self):
        """清理资源"""
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()


class UsagePanel(QWidget):
    """LLM 用量查询面板"""

    data_refreshed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._store = get_usage_record_store()
        self._current_page = 0
        self._page_size = 50
        self._current_stats = {}
        # 当前筛选条件下的总记录数（明细表格改为存储层分页，不再缓存全量记录）
        self._total_count = 0

        self._init_ui()
        self._connect_signals()
        QTimer.singleShot(100, self.refresh_data)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        # ═══════════════════════════════════════════════════════════════
        # 统计卡片行
        # ═══════════════════════════════════════════════════════════════
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)
        self._cards = {}
        card_defs = [
            ("total_requests", "总请求数", "blue"),
            ("total_input", "输入 Token", "cyan"),
            ("total_output", "输出 Token", "purple"),
            ("total_tokens", "总 Token", "orange"),
            ("cache_hit_rate", "缓存命中率", "green"),
            ("avg_duration", "平均耗时", "red"),
        ]
        for card_id, title, color in card_defs:
            card = StatsCard(title, "0", color)
            self._cards[card_id] = card
            cards_layout.addWidget(card, 1)  # 设置 stretch factor 为 1，使卡片自适应宽度
        main_layout.addLayout(cards_layout)

        # ═══════════════════════════════════════════════════════════════
        # 趋势图区域
        # ═══════════════════════════════════════════════════════════════
        chart_group = QGroupBox("用量趋势")
        chart_group.setObjectName("chartGroup")
        chart_layout = QVBoxLayout(chart_group)
        chart_layout.setContentsMargins(16, 16, 16, 16)
        chart_layout.setSpacing(12)

        # 时间范围选择器
        range_layout = QHBoxLayout()
        range_layout.setSpacing(8)
        
        range_label = QLabel("时间范围:")
        range_label.setObjectName("filterLabel")
        self._range_combo = QComboBox()
        self._range_combo.setObjectName("filterCombo")
        self._range_combo.setAccessibleName("时间范围选择")
        self._range_combo.addItems(["近 7 天", "近 30 天", "自定义"])
        self._range_combo.setCurrentText("近 7 天")
        
        range_layout.addWidget(range_label)
        range_layout.addWidget(self._range_combo)
        range_layout.addSpacing(16)
        
        # 日期选择
        from_label = QLabel("从:")
        from_label.setObjectName("filterLabel")
        self._date_from = QDateEdit()
        self._date_from.setObjectName("filterDate")
        self._date_from.setAccessibleName("起始日期")
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-7))
        self._date_from.setEnabled(False)
        
        to_label = QLabel("至:")
        to_label.setObjectName("filterLabel")
        self._date_to = QDateEdit()
        self._date_to.setObjectName("filterDate")
        self._date_to.setAccessibleName("结束日期")
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
        self._date_to.setEnabled(False)
        
        range_layout.addWidget(from_label)
        range_layout.addWidget(self._date_from)
        range_layout.addWidget(to_label)
        range_layout.addWidget(self._date_to)
        range_layout.addStretch()
        
        chart_layout.addLayout(range_layout)

        # 图表组件
        self._chart_widget = UsageChartWidget()
        self._chart_widget.setMinimumHeight(200)
        chart_layout.addWidget(self._chart_widget)
        
        main_layout.addWidget(chart_group)

        # ═══════════════════════════════════════════════════════════════
        # 筛选栏
        # ═══════════════════════════════════════════════════════════════
        filter_container = QFrame()
        filter_container.setObjectName("filterContainer")
        filter_layout = QHBoxLayout(filter_container)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(12)

        # Provider 筛选
        provider_label = QLabel("Provider:")
        provider_label.setObjectName("filterLabel")
        self._provider_combo = QComboBox()
        self._provider_combo.setObjectName("filterCombo")
        self._provider_combo.setAccessibleName("Provider 筛选")
        # Provider 选项不再硬编码，由 refresh_data 根据实际用量记录动态生成
        self._provider_combo.addItems(["全部"])

        # Model 筛选
        model_label = QLabel("Model:")
        model_label.setObjectName("filterLabel")
        self._model_combo = QComboBox()
        self._model_combo.setObjectName("filterCombo")
        self._model_combo.setAccessibleName("Model 筛选")
        self._model_combo.addItems(["全部"])

        # 对话ID 筛选
        conv_label = QLabel("对话ID:")
        conv_label.setObjectName("filterLabel")
        self._conv_id_input = QLineEdit()
        self._conv_id_input.setObjectName("filterInput")
        self._conv_id_input.setAccessibleName("对话 ID 筛选输入框")
        self._conv_id_input.setPlaceholderText("输入对话ID筛选...")
        self._conv_id_input.setMaximumWidth(200)

        # 刷新按钮
        self._refresh_btn = QPushButton("刷新")
        self._refresh_btn.setObjectName("refreshBtn")
        self._refresh_btn.setAccessibleName("刷新用量数据")
        self._refresh_btn.setProperty("class", "primary")

        filter_layout.addWidget(provider_label)
        filter_layout.addWidget(self._provider_combo)
        filter_layout.addSpacing(8)
        filter_layout.addWidget(model_label)
        filter_layout.addWidget(self._model_combo)
        filter_layout.addSpacing(8)
        filter_layout.addWidget(conv_label)
        filter_layout.addWidget(self._conv_id_input)
        filter_layout.addStretch()
        filter_layout.addWidget(self._refresh_btn)
        
        main_layout.addWidget(filter_container)

        # ═══════════════════════════════════════════════════════════════
        # 明细表格
        # ═══════════════════════════════════════════════════════════════
        self._table = QTableWidget()
        self._table.setObjectName("usageTable")
        self._table.setAccessibleName("用量明细表格")
        self._table.setColumnCount(10)
        self._table.setHorizontalHeaderLabels([
            "时间", "Provider", "Model", "输入", "输出", "总Token",
            "缓存命中", "缓存Token", "耗时(s)", "流式"
        ])
        
        # 设置列宽策略
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setDefaultSectionSize(100)
        
        # 设置特定列宽度
        self._table.setColumnWidth(0, 140)  # 时间
        self._table.setColumnWidth(1, 80)   # Provider
        self._table.setColumnWidth(2, 120)  # Model
        self._table.setColumnWidth(3, 70)   # 输入
        self._table.setColumnWidth(4, 70)   # 输出
        self._table.setColumnWidth(5, 80)   # 总Token
        self._table.setColumnWidth(6, 70)   # 缓存命中
        self._table.setColumnWidth(7, 80)   # 缓存Token
        self._table.setColumnWidth(8, 80)   # 耗时
        self._table.setColumnWidth(9, 50)   # 流式
        
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        
        # 应用表格样式
        self._apply_table_style()
        
        main_layout.addWidget(self._table)

        # ═══════════════════════════════════════════════════════════════
        # 分页
        # ═══════════════════════════════════════════════════════════════
        page_container = QFrame()
        page_container.setObjectName("pageContainer")
        page_layout = QHBoxLayout(page_container)
        page_layout.setContentsMargins(0, 8, 0, 0)
        
        self._prev_btn = QPushButton("上一页")
        self._prev_btn.setObjectName("pageBtn")
        self._prev_btn.setAccessibleName("上一页")
        self._prev_btn.setEnabled(False)
        
        self._page_label = QLabel("第 1 页")
        self._page_label.setObjectName("pageLabel")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._next_btn = QPushButton("下一页")
        self._next_btn.setObjectName("pageBtn")
        self._next_btn.setAccessibleName("下一页")
        self._next_btn.setEnabled(False)

        page_layout.addStretch()
        page_layout.addWidget(self._prev_btn)
        page_layout.addSpacing(16)
        page_layout.addWidget(self._page_label)
        page_layout.addSpacing(16)
        page_layout.addWidget(self._next_btn)
        page_layout.addStretch()
        
        main_layout.addWidget(page_container)

    def _apply_table_style(self):
        """应用表格样式（使用 StyleQSS 变量）"""
        # 样式通过全局 QSS 管理，这里设置对象名以便 QSS 选择
        pass

    def _connect_signals(self):
        self._refresh_btn.clicked.connect(self.refresh_data)
        self._range_combo.currentTextChanged.connect(self._on_range_changed)
        self._date_from.dateChanged.connect(self.refresh_data)
        self._date_to.dateChanged.connect(self.refresh_data)
        self._provider_combo.currentTextChanged.connect(self._on_filter_changed)
        self._model_combo.currentTextChanged.connect(self._on_filter_changed)
        self._prev_btn.clicked.connect(self._prev_page)
        self._next_btn.clicked.connect(self._next_page)

    def _get_date_range(self) -> tuple:
        # 记录时间戳为 UTC aware，筛选边界需带本地时区才能正确比较
        tz = _local_tz()
        today = datetime.now().date()
        text = self._range_combo.currentText()
        if text == "近 7 天":
            return (
                datetime.combine(today - timedelta(days=7), datetime.min.time(), tzinfo=tz),
                datetime.combine(today, datetime.max.time(), tzinfo=tz),
            )
        elif text == "近 30 天":
            return (
                datetime.combine(today - timedelta(days=30), datetime.min.time(), tzinfo=tz),
                datetime.combine(today, datetime.max.time(), tzinfo=tz),
            )
        else:
            d_from: Any = self._date_from.date().toPython()
            d_to: Any = self._date_to.date().toPython()
            return (
                datetime.combine(d_from, datetime.min.time(), tzinfo=tz),
                datetime.combine(d_to, datetime.max.time(), tzinfo=tz),
            )

    def _get_filters(self) -> dict:
        provider = self._provider_combo.currentText()
        model = self._model_combo.currentText()
        conv_id = self._conv_id_input.text().strip()
        return {
            "provider": provider if provider != "全部" else None,
            "model": model if model != "全部" else None,
            "conversation_id": conv_id if conv_id else None,
        }

    def refresh_data(self):
        try:
            start_time, end_time = self._get_date_range()
            filters = self._get_filters()

            stats = self._store.get_total_stats(start_time=start_time, end_time=end_time)
            self._current_stats = stats

            self._cards["total_requests"].set_value(str(stats.get("total_requests", 0)))
            self._cards["total_input"].set_value(f"{stats.get('total_input_tokens', 0):,}")
            self._cards["total_output"].set_value(f"{stats.get('total_output_tokens', 0):,}")
            self._cards["total_tokens"].set_value(f"{stats.get('total_tokens', 0):,}")
            rate = stats.get("cache_hit_rate", 0.0)
            self._cards["cache_hit_rate"].set_value(f"{rate:.1%}")
            avg_dur = stats.get("avg_duration_ms", 0.0)
            # 转换为秒显示
            avg_dur_sec = avg_dur / 1000.0
            self._cards["avg_duration"].set_value(f"{avg_dur_sec:.2f}s")

            # 说明：UsageRecordStore 暂无 count/distinct API，
            # 图表聚合、Provider/Model 下拉选项与总条数仍需一次全量读取
            # （瞬时使用、不在面板层缓存）；明细表格已改为存储层分页
            # （limit/offset），翻页时只查询当前页。
            all_records = self._store.get_records(
                start_time=start_time,
                end_time=end_time,
                provider=filters["provider"],
                model=filters["model"],
                conversation_id=filters["conversation_id"],
                limit=None,
            )
            self._total_count = len(all_records)

            self._update_provider_options()
            self._update_model_options(all_records)
            self._chart_widget.update_chart(all_records, start_time, end_time)

            self._current_page = 0
            self._update_table()

            self.data_refreshed.emit()

        except Exception as e:
            QMessageBox.warning(self, "刷新失败", f"刷新用量数据失败:\n{str(e)}")

    def _update_provider_options(self):
        """根据实际用量记录动态生成 Provider 筛选选项（不再硬编码）"""
        try:
            start_time, end_time = self._get_date_range()
            agg = self._store.aggregate(
                start_time=start_time, end_time=end_time, group_by="provider"
            )
            providers = sorted(
                g["group_key"] for g in agg.get("groups", []) if g.get("group_key")
            )
        except Exception:
            providers = []

        current = self._provider_combo.currentText()
        self._provider_combo.blockSignals(True)
        self._provider_combo.clear()
        self._provider_combo.addItems(["全部"] + providers)
        if current in ["全部"] + providers:
            self._provider_combo.setCurrentText(current)
        self._provider_combo.blockSignals(False)

    def _update_model_options(self, records: List[UsageRecord]):
        models = sorted(set(r.model for r in records if r.model))
        current = self._model_combo.currentText()
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        self._model_combo.addItems(["全部"] + models)
        if current in models:
            self._model_combo.setCurrentText(current)
        self._model_combo.blockSignals(False)

    def _update_table(self):
        """按当前页从存储层分页查询并填充明细表格"""
        start_time, end_time = self._get_date_range()
        filters = self._get_filters()
        # 存储层分页：只取当前页数据
        page_records = self._store.get_records(
            start_time=start_time,
            end_time=end_time,
            provider=filters["provider"],
            model=filters["model"],
            conversation_id=filters["conversation_id"],
            limit=self._page_size,
            offset=self._current_page * self._page_size,
        )

        self._table.setRowCount(len(page_records))
        for row, record in enumerate(page_records):
            items = [
                # 记录时间戳为 UTC aware，显示时转换为本地时间
                _to_local_time(record.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                record.provider,
                record.model,
                f"{record.input_tokens:,}",
                f"{record.output_tokens:,}",
                f"{record.total_tokens:,}",
                "是" if record.cache_hit else "否",
                f"{record.cached_tokens:,}",
                # 将毫秒转换为秒显示
                f"{record.duration_ms / 1000.0:.2f}",
                "是" if record.is_stream else "否",
            ]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                # 数值列右对齐
                if col in [3, 4, 5, 7, 8]:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                else:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                
                # 缓存命中高亮
                if record.cache_hit and col == 6:
                    item.setForeground(QColor("#10B981"))  # 绿色
                    
                self._table.setItem(row, col, item)

        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        self._page_label.setText(
            f"第 {self._current_page + 1} / {total_pages} 页  (共 {self._total_count} 条)"
        )
        self._prev_btn.setEnabled(self._current_page > 0)
        self._next_btn.setEnabled(self._current_page < total_pages - 1)

    def _prev_page(self):
        if self._current_page > 0:
            self._current_page -= 1
            self._update_table()

    def _next_page(self):
        total_pages = max(1, (self._total_count + self._page_size - 1) // self._page_size)
        if self._current_page < total_pages - 1:
            self._current_page += 1
            self._update_table()

    def _on_range_changed(self, text: str):
        is_custom = text == "自定义"
        self._date_from.setEnabled(is_custom)
        self._date_to.setEnabled(is_custom)
        if not is_custom:
            self.refresh_data()

    def _on_filter_changed(self):
        self.refresh_data()