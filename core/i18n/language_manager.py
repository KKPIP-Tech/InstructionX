"""语言管理器。

框架多语言子系统的对外门面（单例，QObject）：
- 框架文案取词 ``tr(group, key, **params)``，缺失自动回退默认语言，
  默认语言也缺失时返回 ``ERROR_TEXT``；
- 当前语言/默认语言状态管理与 ``language_changed`` 变更通知（实时切换）；
- 插件语言包注册、每插件语言覆盖与有效语言解析。

单例访问：``get_language_manager()``；模块级便捷函数 ``tr()``。
"""

import threading
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QObject, Signal

from utils.logging_tools import LoggerManager, get_name

from .catalog import TextCatalog
from .fallback import (
    ERROR_TEXT,
    format_template,
    lookup_template,
    resolve_language_code,
)
from .loader import CatalogCache
from .plugin_registry import PluginTextRegistry
from .settings_store import (
    DEFAULT_LANGUAGE,
    I18nSettingsStore,
    _KEY_CURRENT_LANGUAGE,
    _KEY_DEFAULT_LANGUAGE,
)

# 项目根目录（core/i18n/language_manager.py → core/i18n → core → 根目录）
_PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]

# 框架语言文件目录（ui/text/<语言代码>.xml）
_FRAMEWORK_TEXT_DIR: Path = _PROJECT_ROOT / "ui" / "text"


class LanguageManager(QObject):
    """语言管理器单例

    职责：框架/插件文案的统一取词入口、当前语言状态管理、语言变更通知。
    仿 FontManager/ThemeManager 模式；配置读写委托 I18nSettingsStore，
    插件语言包登记委托 PluginTextRegistry。

    典型用法（框架 UI 代码）::

        from core.i18n import tr
        menu.addAction(tr("main_window", "menu.edit.plugin_management"))

    Signals:
        language_changed(str): 框架当前语言变化（参数为新语言代码）
        plugin_language_changed(str, str): 某插件有效语言变化（插件 UUID, 新语言）
    """

    language_changed = Signal(str)
    plugin_language_changed = Signal(str, str)

    _instance: Optional["LanguageManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args, **kwargs) -> "LanguageManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        text_dir: Optional[Path] = None,
        settings_store: Optional[I18nSettingsStore] = None,
    ) -> None:
        """初始化语言管理器（单例，重复构造无副作用）

        Args:
            text_dir: 框架语言文件目录，默认 ``ui/text/``（测试可注入临时目录）
            settings_store: 配置存储，默认使用 ``config/`` 目录（测试可注入）
        """
        if getattr(self, "_initialized", False):
            return
        super().__init__()
        self._initialized = True
        self._logger = LoggerManager()
        self._catalogs = CatalogCache(text_dir or _FRAMEWORK_TEXT_DIR)
        self._store = settings_store or I18nSettingsStore()
        settings = self._store.load_framework_settings()
        self._default_language = settings[_KEY_DEFAULT_LANGUAGE]
        self._current_language = settings[_KEY_CURRENT_LANGUAGE]
        self._registry = PluginTextRegistry()
        self._overrides: Optional[Dict[str, str]] = None
        # 日志去重集合：缺失的语言文件 / 缺失的键只各警告一次
        self._warned_missing_files: Set[str] = set()
        self._warned_missing_keys: Set[Tuple[str, str, str]] = set()

    # ==================== 框架文案取词 ====================

    def tr(self, group: str, key: str, /, **params: object) -> str:
        """框架文案取词：按当前语言查找，缺失自动回退默认语言

        Args:
            group: 分组名（语言文件内 ``<group name="...">``）
            key: 分组内的点分键名
            params: 命名占位符参数（对应模板中的 ``{name}``）

        Returns:
            最终文案；默认语言也缺失时返回 ``ERROR_TEXT`` 并记 ERROR 日志
        """
        chain = self._framework_chain()
        template, hit_language = lookup_template(chain, group, key)
        if template is None:
            self._logger.error(
                get_name(),
                f"默认语言 '{self._default_language}' 缺失文案 [{group}.{key}]，"
                f"界面将显示 {ERROR_TEXT}")
            return ERROR_TEXT
        self._log_fallback_once(chain, hit_language, group, key)
        return format_template(template, params, f"{group}.{key}")

    def _framework_chain(self) -> List[Tuple[str, Optional[TextCatalog]]]:
        """构造框架取词回退链：当前语言 → 默认语言（去重）"""
        available = self._catalogs.available_languages()
        codes: List[str] = []
        for raw in (self._current_language, self._default_language):
            resolved = resolve_language_code(raw, available)
            if resolved and resolved not in codes:
                codes.append(resolved)
        return [(code, self._get_framework_catalog(code)) for code in codes]

    def _get_framework_catalog(self, language: str) -> Optional[TextCatalog]:
        """取框架语言目录；文件缺失/损坏记 WARNING（每语言一次）"""
        catalog = self._catalogs.get(language)
        if catalog is None and language not in self._warned_missing_files:
            self._warned_missing_files.add(language)
            self._logger.warning(
                get_name(), f"语言文件缺失或损坏，回退默认语言: {language}.xml")
        return catalog

    def _log_fallback_once(
        self,
        chain: List[Tuple[str, Optional[TextCatalog]]],
        hit_language: Optional[str],
        group: str,
        key: str,
    ) -> None:
        """键级回退记 WARNING（每 语言+键 一次，避免刷屏）"""
        if not chain or hit_language == chain[0][0]:
            return
        marker = (chain[0][0], group, key)
        if marker in self._warned_missing_keys:
            return
        self._warned_missing_keys.add(marker)
        self._logger.warning(
            get_name(),
            f"语言 '{chain[0][0]}' 缺失文案 [{group}.{key}]，已回退 '{hit_language}'")

    # ==================== 语言状态 ====================

    def current_language(self) -> str:
        """当前生效的语言代码（用户选择，未经区域子标签解析）"""
        return self._current_language

    def default_language(self) -> str:
        """开发者设定的默认语言（回退终点，用户不可修改）"""
        return self._default_language

    def available_languages(self) -> List[str]:
        """框架可用的语言代码列表（扫描 ui/text/*.xml 文件名）"""
        return self._catalogs.available_languages()

    def language_display_name(self, code: str) -> str:
        """取语言的用户可读显示名（语言选择对话框等场景使用）

        显示名取自该语言文件 ``common`` 分组的 ``language.self_name`` 键
        （各语言的自称，如 zh 的「简体中文」）。

        Args:
            code: 语言代码

        Returns:
            语言显示名；语言文件缺失/损坏（负缓存）或键缺失时
            返回语言代码本身作为兜底
        """
        catalog = self._catalogs.get(code)
        if catalog is None:
            return code
        return catalog.get("common", "language.self_name") or code

    def set_language(self, code: str) -> bool:
        """切换框架当前语言（实时生效）

        Args:
            code: 目标语言代码（需存在对应语言文件，支持区域子标签回退）

        Returns:
            切换成功返回 True；语言不可用返回 False（记 WARNING）
        """
        if resolve_language_code(code, self.available_languages()) is None:
            self._logger.warning(
                get_name(), f"切换到不可用语言 '{code}' 被拒绝（无语言文件）")
            return False
        if code == self._current_language:
            return True
        self._current_language = code
        self._store.save_framework_settings(self._default_language, code)
        self._logger.info(get_name(), f"界面语言已切换: {code}")
        self.language_changed.emit(code)
        return True

    # ==================== 插件语言包 ====================

    def register_plugin_texts(
        self,
        plugin_id: str,
        plugin_dir: Path,
        declared_default: Optional[str] = None,
    ) -> bool:
        """扫描并注册插件语言包（由 PluginManager 在加载插件时调用）

        Args:
            plugin_id: 插件 UUID
            plugin_dir: 插件根目录
            declared_default: 插件声明的默认语言（IPluginInfo.default_language）

        Returns:
            插件提供了 text/ 目录返回 True
        """
        return self._registry.register(plugin_id, plugin_dir, declared_default)

    def unregister_plugin_texts(self, plugin_id: str) -> None:
        """注销插件语言包（由 PluginManager 在热卸载时调用）

        Args:
            plugin_id: 插件 UUID
        """
        self._registry.unregister(plugin_id)

    def plugin_available_languages(self, plugin_id: str) -> List[str]:
        """插件提供的语言代码列表；未提供语言包返回空表"""
        return self._registry.languages_of(plugin_id)

    def effective_plugin_language(self, plugin_id: str) -> str:
        """解析插件有效语言：用户覆盖 → 框架当前语言 → 插件默认语言

        Args:
            plugin_id: 插件 UUID

        Returns:
            有效语言代码；插件无语言包时返回框架当前语言（概念性跟随）
        """
        languages = self._registry.languages_of(plugin_id)
        if not languages:
            return self._current_language
        override = self._load_overrides().get(plugin_id)
        resolved = self._resolve_in_order(
            [override, self._current_language,
             self._registry.declared_default_of(plugin_id) or self._default_language],
            languages)
        if resolved:
            return resolved
        # 保底：声明的语言均无文件时，用插件实际提供的首个语言
        return sorted(languages)[0]

    def set_plugin_language(self, plugin_id: str, code: Optional[str]) -> bool:
        """设置/清除某插件的语言覆盖

        Args:
            plugin_id: 插件 UUID
            code: 语言代码；None 表示清除覆盖（恢复跟随框架）

        Returns:
            设置成功返回 True；插件不提供该语言返回 False（记 WARNING）
        """
        if code is not None and resolve_language_code(
                code, self._registry.languages_of(plugin_id)) is None:
            self._logger.warning(
                get_name(), f"插件 {plugin_id} 不提供语言 '{code}'，覆盖设置被拒绝")
            return False
        self._load_overrides()
        if code is None:
            self._overrides.pop(plugin_id, None)
        else:
            self._overrides[plugin_id] = code
        self._store.set_plugin_override(plugin_id, code)
        effective = self.effective_plugin_language(plugin_id)
        self._logger.info(
            get_name(), f"插件 {plugin_id} 语言覆盖已更新: {code or '跟随框架'}，生效 {effective}")
        self.plugin_language_changed.emit(plugin_id, effective)
        return True

    def plugin_tr(self, plugin_id: str, group: str, key: str, /, **params: object) -> str:
        """插件文案取词（供 PluginI18nFacade 调用）

        回退链：插件有效语言 → 插件默认语言 → ``ERROR_TEXT``。
        插件无语言包时优雅降级：返回 key 并记 DEBUG 日志。

        Args:
            plugin_id: 插件 UUID
            group: 分组名
            key: 键名
            params: 命名占位符参数

        Returns:
            最终文案
        """
        if not self._registry.has_catalog(plugin_id):
            self._logger.debug(
                get_name(), f"插件 {plugin_id} 无语言包，直接返回键名 [{group}.{key}]")
            return key
        chain = self._plugin_chain(plugin_id)
        template, _ = lookup_template(chain, group, key)
        if template is None:
            self._logger.error(
                get_name(),
                f"插件 {plugin_id} 默认语言缺失文案 [{group}.{key}]，界面将显示 {ERROR_TEXT}")
            return ERROR_TEXT
        return format_template(template, params, f"{plugin_id}:{group}.{key}")

    def _plugin_chain(self, plugin_id: str) -> List[Tuple[str, Optional[TextCatalog]]]:
        """构造插件取词回退链：有效语言 → 插件默认语言（去重）"""
        languages = self._registry.languages_of(plugin_id)
        declared = self._registry.declared_default_of(plugin_id) or self._default_language
        codes: List[str] = []
        for raw in (self.effective_plugin_language(plugin_id), declared):
            resolved = resolve_language_code(raw, languages)
            if resolved and resolved not in codes:
                codes.append(resolved)
        return [(code, self._registry.catalog_of(plugin_id, code)) for code in codes]

    def _load_overrides(self) -> Dict[str, str]:
        """惰性加载插件语言覆盖表（内存缓存）"""
        if self._overrides is None:
            self._overrides = self._store.load_plugin_overrides()
        return self._overrides

    @staticmethod
    def _resolve_in_order(
        candidates: List[Optional[str]],
        languages: List[str],
    ) -> Optional[str]:
        """按候选顺序返回首个可解析为可用语言的代码（支持区域子标签回退）"""
        for raw in candidates:
            if not raw:
                continue
            resolved = resolve_language_code(raw, languages)
            if resolved:
                return resolved
        return None


def get_language_manager() -> LanguageManager:
    """获取 LanguageManager 单例"""
    return LanguageManager()


def tr(group: str, key: str, /, **params: object) -> str:
    """框架文案取词便捷函数，等价于 ``get_language_manager().tr(...)``"""
    return get_language_manager().tr(group, key, **params)
