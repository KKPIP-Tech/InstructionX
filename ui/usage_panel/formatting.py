"""用量面板数值与时间格式化工具

提供 KPI 卡片 / 趋势图 / 明细表格共用的格式化函数与时区转换工具。
数值缩写与坐标轴缩放逻辑移植自用量面板 Demo（temp/ai_usage_panel_demo），
时区转换逻辑保留自旧版用量面板。
"""

from datetime import datetime, tzinfo
from typing import Tuple

# ===== 数值缩写阈值 =====
THOUSAND = 1_000
MILLION = 1_000_000

# ===== 单位换算 =====
MS_PER_SECOND = 1000.0
PERCENT_BASE = 100.0


def fmt_int(n: float) -> str:
    """千分位整数字符串，如 12,847

    Args:
        n: 待格式化的数值

    Returns:
        str: 带千分位分隔符的整数文本
    """
    return f"{int(round(n)):,}"


def fmt_tokens(n: float) -> str:
    """Token 数量带单位缩写，如 8.42 M / 845.2 K

    Args:
        n: Token 数量

    Returns:
        str: 缩写后的文本（不足 1K 时返回整数原文）
    """
    if n >= MILLION:
        return f"{n / MILLION:.2f} M"
    if n >= THOUSAND:
        return f"{n / THOUSAND:.1f} K"
    return str(int(round(n)))


def fmt_latency(ms: float) -> str:
    """耗时格式化，如 1.42 s / 850 ms

    Args:
        ms: 毫秒耗时

    Returns:
        str: 大于等于 1 秒时以秒显示（两位小数），否则以毫秒显示
    """
    if ms >= MS_PER_SECOND:
        return f"{ms / MS_PER_SECOND:.2f} s"
    return f"{ms:.0f} ms"


def fmt_percent(rate: float) -> str:
    """比率（0~1）格式化为百分比文本，如 68.3%

    Args:
        rate: 0~1 之间的小数比率

    Returns:
        str: 一位小数的百分比文本
    """
    return f"{rate * PERCENT_BASE:.1f}%"


def pick_token_scale(max_value: float) -> Tuple[float, str]:
    """为图表 Y 轴挑选缩放倍率与单位后缀

    Args:
        max_value: 序列中的最大值

    Returns:
        Tuple[float, str]: (缩放倍率, 单位后缀)，如 (1000000.0, "（百万）")
    """
    if max_value >= MILLION:
        return float(MILLION), "（百万）"
    if max_value >= THOUSAND:
        return float(THOUSAND), "（千）"
    return 1.0, ""


def local_tz() -> tzinfo:
    """获取本地时区（aware），用于与 UTC aware 的记录时间戳比较

    Returns:
        tzinfo: 当前系统本地时区
    """
    return datetime.now().astimezone().tzinfo


def to_local_time(ts: datetime) -> datetime:
    """将记录时间戳转换为本地时间显示

    Args:
        ts: 记录时间戳（aware 时转换为本地时间，naive 原样返回）

    Returns:
        datetime: 本地时间
    """
    if ts.tzinfo is not None:
        return ts.astimezone()
    return ts
