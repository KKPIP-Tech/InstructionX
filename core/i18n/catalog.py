"""文案目录数据模型。

``TextCatalog`` 是单个语言文件的内存表示：一个语言一个 XML 文件，
文件内以 ``<group>`` 划分分组，故目录结构为 ``{group: {key: 模板}}``。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TextCatalog:
    """单语言文案目录（不可变）

    职责：承载一个语言文件解析后的全部文案，提供分组/键级别的查询。
    查找失败（回退）逻辑不在此处，由 fallback.py 负责。

    典型用法::

        catalog = load_catalog(Path("ui/text/zh.xml"))
        template = catalog.get("main_window", "menu.edit")  # "编辑"
    """

    language: str
    groups: Dict[str, Dict[str, str]] = field(default_factory=dict)

    def has(self, group: str, key: str) -> bool:
        """判断指定分组内是否存在指定键

        Args:
            group: 分组名（XML 中 ``<group name="...">``）
            key: 分组内的点分键名

        Returns:
            存在返回 True
        """
        return key in self.groups.get(group, {})

    def get(self, group: str, key: str) -> Optional[str]:
        """取指定分组内指定键的文案模板

        Args:
            group: 分组名
            key: 分组内的点分键名

        Returns:
            文案模板（可能含 ``{name}`` 占位符）；不存在返回 None
        """
        return self.groups.get(group, {}).get(key)

    def group_names(self) -> List[str]:
        """返回全部分组名（按文件中出现的顺序）"""
        return list(self.groups.keys())

    def key_count(self) -> int:
        """返回全部键的总数（供校验脚本统计）"""
        return sum(len(keys) for keys in self.groups.values())
