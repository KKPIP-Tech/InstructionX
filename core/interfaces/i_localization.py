"""
插件多语言（i18n）取词接口

定义插件访问框架多语言能力的抽象契约。插件经 ``PluginServices.localization``
获得本接口的门面实例（实现：core.i18n.facade.PluginI18nFacade），
按分组/键名取词，无需感知 LanguageManager 与插件语言包注册表等底层实现。
"""

from abc import ABC, abstractmethod
from typing import List


class ILocalizationFacade(ABC):
    """
    插件多语言取词门面抽象接口

    框架在加载插件时为每个插件创建绑定其 UUID 的门面实例，
    经 ``PluginServices.localization`` 注入。取词回退链：
    插件有效语言 → 插件默认语言 → ERROR_TEXT；
    插件未提供语言包（text/ 目录）时优雅降级，直接返回键名。
    """

    @abstractmethod
    def tr(self, group: str, key: str, /, **params: object) -> str:
        """按分组与键名取插件文案

        Args:
            group: 分组名（语言文件内 ``<group name="...">``）
            key: 分组内的点分键名
            params: 命名占位符参数（对应模板中的 ``{name}``）

        Returns:
            最终文案；插件无语言包时返回键名本身
        """
        pass

    @abstractmethod
    def current_language(self) -> str:
        """本插件当前的有效语言代码（用户覆盖 → 框架当前语言 → 插件默认语言）"""
        pass

    @abstractmethod
    def available_languages(self) -> List[str]:
        """本插件提供的语言代码列表；未提供语言包时返回空表"""
        pass

    @abstractmethod
    def has_catalog(self) -> bool:
        """本插件是否提供了语言包（text/ 目录且含至少一个语言文件）"""
        pass
