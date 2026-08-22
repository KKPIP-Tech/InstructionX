"""core.i18n — 多国语言（i18n）子系统。

一个语言一个 XML 文件（``text/<语言代码>.xml``），文件内以 ``<group>``
划分分组；取词走「当前语言 → 默认语言 → ERROR_TEXT」回退链。

纯数据模块（catalog/loader/fallback/settings_store/plugin_registry）直接导出；
LanguageManager 依赖 PySide6，按 PEP-562 惰性导出，
避免 ``import core.i18n`` 时拉起 Qt。
"""

from .catalog import TextCatalog
from .fallback import ERROR_TEXT, format_template, lookup_template, resolve_language_code
from .loader import CatalogCache, load_catalog
from .plugin_registry import PluginTextRegistry
from .settings_store import DEFAULT_LANGUAGE, I18nSettingsStore

__all__ = [
    "TextCatalog",
    "ERROR_TEXT",
    "format_template",
    "lookup_template",
    "resolve_language_code",
    "CatalogCache",
    "load_catalog",
    "PluginTextRegistry",
    "DEFAULT_LANGUAGE",
    "I18nSettingsStore",
    "LanguageManager",
    "get_language_manager",
    "tr",
]

_LAZY_EXPORTS = {"LanguageManager", "get_language_manager", "tr"}


def __getattr__(name: str):
    """PEP-562 惰性导出：LanguageManager 相关符号按需引入 PySide6"""
    if name in _LAZY_EXPORTS:
        from . import language_manager

        return getattr(language_manager, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
