"""IXPlugin.json / IXRepo.json 安装元数据多语言字段解析。

``name`` / ``description`` 字段兼容两种形式（i18n-implementation-plan.md §10.4b）：

- 纯字符串（旧形式）：视为"所有语言同一文案"，原样返回；
- 字典形式 ``{"zh": "...", "en": "..."}``：按
  目标语言 → 默认语言 → 字典首个值 的顺序解析。

本模块为纯 Python 实现，不引入 PySide6。
"""

from typing import Dict

from utils.logging_tools import LoggerManager, get_name

from .fallback import resolve_language_code
from .settings_store import DEFAULT_LANGUAGE


def resolve_i18n_field(
    value: object,
    language: str,
    default_language: str = DEFAULT_LANGUAGE,
) -> str:
    """解析可多语言字段为指定语言的文案

    Args:
        value: 字段原始值，允许纯字符串或 ``{语言代码: 文案}`` 字典
        language: 目标语言代码（一般为框架当前语言）
        default_language: 默认语言代码（字典缺目标语言时的首选回退）

    Returns:
        解析后的文案：字符串原样返回；字典按
        目标语言（键集合先做区域子标签解析，如 ``zh-TW`` 命中 ``zh``）
        → 默认语言 → 字典第一个值 解析；字典无任何可用值时返回空字符串
        并记 WARNING 日志；其他类型按 ``str(value)`` 兜底并记 WARNING 日志
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return _resolve_from_dict(value, language, default_language)
    LoggerManager().warning(
        get_name(),
        f"多语言字段类型异常（{type(value).__name__}），按 str() 兜底: {value!r}",
    )
    return str(value)


def _resolve_from_dict(
    value: Dict[object, object],
    language: str,
    default_language: str,
) -> str:
    """从字典形式字段解析文案（目标语言 → 默认语言 → 字典首个值）

    Args:
        value: ``{语言代码: 文案}`` 字典
        language: 目标语言代码
        default_language: 默认语言代码

    Returns:
        命中的文案；空字典返回空字符串并记 WARNING 日志
    """
    logger = LoggerManager()
    resolved = resolve_language_code(language, value.keys())
    if resolved is not None:
        return str(value[resolved])
    resolved_default = resolve_language_code(default_language, value.keys())
    if resolved_default is not None:
        return str(value[resolved_default])
    if value:
        logger.warning(
            get_name(),
            f"多语言字段缺少目标语言({language})与默认语言({default_language})，"
            f"回退字典首个值（可用语言: {list(value.keys())}）",
        )
        return str(next(iter(value.values())))
    logger.warning(get_name(), "多语言字段为空字典，返回空字符串")
    return ""
