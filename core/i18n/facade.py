"""插件多语言取词门面。

``PluginI18nFacade`` 绑定插件 UUID 与 LanguageManager，为插件提供
免感知 plugin_id 的取词入口。框架在加载插件时创建实例，
经 ``PluginServices.localization`` 注入给插件。
"""

from typing import List, Optional

from core.interfaces.i_localization import ILocalizationFacade

from .language_manager import LanguageManager, get_language_manager


class PluginI18nFacade(ILocalizationFacade):
    """绑定单个插件的多语言取词门面

    全部取词能力委托 LanguageManager 的插件方法，
    本类只负责绑定 plugin_id，让插件侧调用无需携带 UUID。

    典型用法（插件代码内）::

        class MyPlugin(IPlugin):
            def __init__(self, services: PluginServices | None = None):
                super().__init__()
                self._i18n = services.localization if services else None

            def on_plugin_loaded(self):
                title = self._i18n.tr("main", "title")

    Args:
        plugin_id: 插件 UUID
        language_manager: 语言管理器实例；None 时使用全局单例
            ``get_language_manager()``（测试可注入独立实例）
    """

    def __init__(
        self,
        plugin_id: str,
        language_manager: Optional[LanguageManager] = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._language_manager = (
            language_manager if language_manager is not None else get_language_manager()
        )

    def tr(self, group: str, key: str, /, **params: object) -> str:
        """按分组与键名取插件文案（委托 LanguageManager.plugin_tr）

        Args:
            group: 分组名（语言文件内 ``<group name="...">``）
            key: 分组内的点分键名
            params: 命名占位符参数（对应模板中的 ``{name}``）

        Returns:
            最终文案；插件无语言包时优雅降级返回键名本身
        """
        return self._language_manager.plugin_tr(self._plugin_id, group, key, **params)

    def current_language(self) -> str:
        """本插件当前的有效语言代码（委托 effective_plugin_language）"""
        return self._language_manager.effective_plugin_language(self._plugin_id)

    def available_languages(self) -> List[str]:
        """本插件提供的语言代码列表（委托 plugin_available_languages）"""
        return self._language_manager.plugin_available_languages(self._plugin_id)

    def has_catalog(self) -> bool:
        """本插件是否提供了语言包（委托 plugin_has_catalog）"""
        return self._language_manager.plugin_has_catalog(self._plugin_id)
