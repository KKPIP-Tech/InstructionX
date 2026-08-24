"""插件语言包自动注册表。

框架加载插件时自动扫描 ``<插件目录>/text/*.xml`` 完成注册，
插件开发者无需任何登记代码；插件热卸载时注销注册项与缓存。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

from utils.logging_tools import LoggerManager, get_name

from .catalog import TextCatalog
from .loader import CatalogCache

# 插件语言包目录名（位于插件目录下）
TEXT_DIR_NAME = "text"


@dataclass
class PluginTextEntry:
    """单个插件的语言包注册项

    Attributes:
        plugin_id: 插件 UUID
        cache: 该插件 text/ 目录的目录缓存
        languages: 扫描到的可用语言代码集合
        declared_default: 插件声明的默认语言（None = 跟随框架默认语言）
    """

    plugin_id: str
    cache: CatalogCache
    languages: Set[str] = field(default_factory=set)
    declared_default: Optional[str] = None


class PluginTextRegistry:
    """插件语言包注册表

    职责：维护 ``plugin_id -> PluginTextEntry`` 映射，提供按插件的
    语言集合查询与文案目录惰性加载。由 PluginManager 在插件加载/
    卸载时调用 register/unregister，插件自身不感知本表。
    """

    def __init__(self):
        self._logger = LoggerManager()
        self._entries: Dict[str, PluginTextEntry] = {}

    def register(
        self,
        plugin_id: str,
        plugin_dir: Path,
        declared_default: Optional[str] = None,
    ) -> bool:
        """扫描并注册插件语言包

        Args:
            plugin_id: 插件 UUID
            plugin_dir: 插件根目录
            declared_default: 插件声明的默认语言（IPluginInfo.default_language）

        Returns:
            插件提供了 text/ 目录并完成注册返回 True；无 text/ 目录返回 False
        """
        text_dir = plugin_dir / TEXT_DIR_NAME
        if not text_dir.is_dir():
            return False
        cache = CatalogCache(text_dir)
        languages = set(cache.available_languages())
        if not languages:
            self._logger.warning(
                get_name(), f"插件 text/ 目录无语言文件，视为未提供多语言: {plugin_dir}")
        self._entries[plugin_id] = PluginTextEntry(
            plugin_id=plugin_id,
            cache=cache,
            languages=languages,
            declared_default=declared_default,
        )
        self._logger.info(
            get_name(),
            f"插件语言包已注册: {plugin_id}，可用语言 {sorted(languages) or '无'}")
        return True

    def unregister(self, plugin_id: str) -> None:
        """注销插件语言包（热卸载时调用），同时清理其目录缓存

        Args:
            plugin_id: 插件 UUID
        """
        self._entries.pop(plugin_id, None)

    def has_catalog(self, plugin_id: str) -> bool:
        """插件是否提供了语言包（text/ 目录且含至少一个语言文件）"""
        entry = self._entries.get(plugin_id)
        return entry is not None and bool(entry.languages)

    def is_registered(self, plugin_id: str) -> bool:
        """插件是否已注册（无论是否有语言文件）"""
        return plugin_id in self._entries

    def languages_of(self, plugin_id: str) -> List[str]:
        """插件提供的语言代码列表（排序）；未注册返回空表"""
        entry = self._entries.get(plugin_id)
        return sorted(entry.languages) if entry else []

    def declared_default_of(self, plugin_id: str) -> Optional[str]:
        """插件声明的默认语言；未声明/未注册返回 None"""
        entry = self._entries.get(plugin_id)
        return entry.declared_default if entry else None

    def set_declared_default(self, plugin_id: str, language: Optional[str]) -> None:
        """登记插件声明的默认语言；注册表条目不存在时忽略

        Args:
            plugin_id: 插件 UUID
            language: 插件声明的默认语言代码
        """
        entry = self._entries.get(plugin_id)
        if entry is not None:
            entry.declared_default = language

    def catalog_of(self, plugin_id: str, language: str) -> Optional[TextCatalog]:
        """取插件指定语言的文案目录（惰性加载）

        Args:
            plugin_id: 插件 UUID
            language: 语言代码

        Returns:
            TextCatalog；插件未注册或文件缺失/损坏返回 None
        """
        entry = self._entries.get(plugin_id)
        if entry is None:
            return None
        return entry.cache.get(language)
