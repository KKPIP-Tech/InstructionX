"""回退（Fallback）解析器。

职责：
- 语言代码解析：精确匹配 → 主语言子码回退（``zh-TW`` → ``zh``）；
- 文案查找回退链：当前语言 → 默认语言 → ``ERROR_TEXT``；
- 占位符格式化容错：参数不匹配时返回原始模板，不抛异常。
"""

from typing import Collection, Dict, List, Optional, Tuple

from utils.logging_tools import LoggerManager, get_name

from .catalog import TextCatalog

# 默认语言也缺键时的显式错误文案（需求约定：不静默、直接可见）
ERROR_TEXT = "ERROR_TEXT"

# 区域子标签分隔符（BCP 47 风格，如 zh-CN）
_REGION_SEPARATOR = "-"


def resolve_language_code(requested: str, available: Collection[str]) -> Optional[str]:
    """把请求的语言代码解析为实际可用的语言代码

    解析顺序：精确匹配 → 主语言子码（``zh-TW`` 回退 ``zh``）。

    Args:
        requested: 请求的语言代码（ISO 639-1，可带区域子标签）
        available: 实际存在语言文件的语言代码集合

    Returns:
        可用的语言代码；均不可用时返回 None
    """
    if requested in available:
        return requested
    primary = requested.split(_REGION_SEPARATOR, 1)[0]
    if primary != requested and primary in available:
        return primary
    return None


def lookup_template(
    chain: List[Tuple[str, Optional[TextCatalog]]],
    group: str,
    key: str,
) -> Tuple[Optional[str], Optional[str]]:
    """按优先级链查找文案模板

    Args:
        chain: ``(语言代码, TextCatalog 或 None)`` 的优先级序列，
            靠前者优先；catalog 为 None 的条目（文件缺失）跳过
        group: 分组名
        key: 键名

    Returns:
        ``(模板, 命中语言代码)``；整条链都缺失时返回 ``(None, None)``
    """
    for language, catalog in chain:
        if catalog is None:
            continue
        template = catalog.get(group, key)
        if template is not None:
            return template, language
    return None, None


def format_template(template: str, params: Dict[str, object], context: str) -> str:
    """向文案模板注入命名占位符参数

    Args:
        template: 含 ``{name}`` 占位符的模板
        params: 占位符参数
        context: 日志上下文（一般是 ``group.key``），用于定位问题

    Returns:
        格式化后的文案；参数不匹配时记 ERROR 日志并返回原始模板（不抛异常）
    """
    if not params:
        return template
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError) as e:
        LoggerManager().error(
            get_name(),
            f"文案占位符格式化失败，返回原始模板 [{context}]: {e}")
        return template
