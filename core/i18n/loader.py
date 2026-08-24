"""语言文件加载器。

负责把 ``text/<语言代码>.xml`` 解析为 :class:`TextCatalog`，并提供
按目录的惰性加载缓存（``CatalogCache``）。

容错原则（与项目既有约定一致）：
- 单个语言文件解析失败不抛出异常，记 ERROR 日志并返回 None，
  该语言整体回退默认语言；
- ``language`` 属性与文件名不一致时记 WARNING，以文件名（路径）为准；
- group 重名 / 键重复时记 WARNING，先出现者生效。
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional

from utils.logging_tools import LoggerManager, get_name

from .catalog import TextCatalog

# ===== XML 结构常量 =====
TEXTS_ROOT_TAG = "texts"
GROUP_TAG = "group"
TEXT_TAG = "text"
LANGUAGE_ATTR = "language"
GROUP_NAME_ATTR = "name"
KEY_ATTR = "key"

# 语言文件扩展名
LANGUAGE_FILE_SUFFIX = ".xml"


def _extract_text(element: ET.Element) -> str:
    """提取 <text> 元素的文案内容

    使用 itertext 兼容 CDATA 与嵌套文本；首尾空白统一剥离，
    避免 XML 排版缩进混入文案（文案内部的换行保留）。
    """
    return "".join(element.itertext()).strip()


def load_catalog(path: Path) -> Optional[TextCatalog]:
    """解析单个语言文件为 TextCatalog

    Args:
        path: 语言文件路径，文件名（不含扩展名）即语言代码

    Returns:
        解析成功返回 TextCatalog；文件缺失或解析失败返回 None（记 ERROR 日志）
    """
    logger = LoggerManager()
    language = path.stem
    if not path.is_file():
        logger.error(get_name(), f"语言文件不存在: {path}")
        return None
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as e:
        logger.error(get_name(), f"语言文件解析失败（该语言整体回退默认语言）: {path}: {e}")
        return None
    if root.tag != TEXTS_ROOT_TAG:
        logger.error(get_name(), f"语言文件根元素应为 <{TEXTS_ROOT_TAG}>: {path}")
        return None
    _check_language_attr(root, language, path)
    return TextCatalog(language=language, groups=_parse_groups(root, path))


def _check_language_attr(root: ET.Element, language: str, path: Path) -> None:
    """校验 language 属性与文件名一致性（不一致时以文件名称为准）"""
    declared = root.get(LANGUAGE_ATTR, "")
    if declared != language:
        LoggerManager().warning(
            get_name(),
            f"语言文件 language 属性与文件名不一致，以文件名 '{language}' 为准: {path}")


def _parse_groups(root: ET.Element, path: Path) -> Dict[str, Dict[str, str]]:
    """解析全部 <group> 分组；group 重名、键重复均记 WARNING 且先出现者生效"""
    logger = LoggerManager()
    groups: Dict[str, Dict[str, str]] = {}
    for group_elem in root.findall(GROUP_TAG):
        group_name = group_elem.get(GROUP_NAME_ATTR, "")
        if not group_name:
            logger.warning(get_name(), f"语言文件存在无名 <group>，已跳过: {path}")
            continue
        if group_name in groups:
            logger.warning(get_name(), f"分组重名 '{group_name}'，先出现者生效: {path}")
            continue
        groups[group_name] = _parse_texts(group_elem, group_name, path)
    return groups


def _parse_texts(group_elem: ET.Element, group_name: str, path: Path) -> Dict[str, str]:
    """解析单个 <group> 内的全部 <text> 条目"""
    logger = LoggerManager()
    texts: Dict[str, str] = {}
    for text_elem in group_elem.findall(TEXT_TAG):
        key = text_elem.get(KEY_ATTR, "")
        if not key:
            logger.warning(get_name(), f"分组 '{group_name}' 存在无 key 的 <text>，已跳过: {path}")
            continue
        if key in texts:
            logger.warning(get_name(), f"分组 '{group_name}' 键重复 '{key}'，先出现者生效: {path}")
            continue
        texts[key] = _extract_text(text_elem)
    return texts


class CatalogCache:
    """某个 text/ 目录的语言文件惰性加载缓存

    职责：扫描目录下的 ``*.xml`` 得出可用语言集合；按需解析并缓存
    TextCatalog（含负缓存——已知缺失/损坏的语言不重复读盘）。
    框架侧与每个插件各持有一个实例。
    """

    def __init__(self, text_dir: Path):
        """初始化缓存

        Args:
            text_dir: 语言文件所在目录（框架为 ui/text/，插件为 <插件>/text/）
        """
        self._text_dir = text_dir
        # 语言代码 -> TextCatalog；值为 None 表示已知缺失/损坏（负缓存）
        self._catalogs: Dict[str, Optional[TextCatalog]] = {}

    @property
    def text_dir(self) -> Path:
        """语言文件目录"""
        return self._text_dir

    def available_languages(self) -> List[str]:
        """扫描目录下全部 *.xml 文件名，返回可用语言代码列表（排序）"""
        if not self._text_dir.is_dir():
            return []
        return sorted(p.stem for p in self._text_dir.glob(f"*{LANGUAGE_FILE_SUFFIX}"))

    def get(self, language: str) -> Optional[TextCatalog]:
        """取指定语言的文案目录（惰性加载 + 缓存）

        Args:
            language: 语言代码（= 文件名，不含扩展名）

        Returns:
            TextCatalog；文件缺失或损坏返回 None
        """
        if language not in self._catalogs:
            self._catalogs[language] = load_catalog(
                self._text_dir / f"{language}{LANGUAGE_FILE_SUFFIX}")
        return self._catalogs[language]

    def invalidate(self, language: Optional[str] = None) -> None:
        """清除缓存

        Args:
            language: 指定语言代码则只清该语言；None 清空全部
        """
        if language is None:
            self._catalogs.clear()
        else:
            self._catalogs.pop(language, None)
