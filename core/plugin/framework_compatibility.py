"""插件描述文件中的 InstructionX 框架兼容性声明评估。"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from core.version import APP_VERSION

from .plugin_version import PluginVersion


COMPATIBILITY_FIELD = "compatible_framework_versions"


class FrameworkCompatibilityStatus(Enum):
    """兼容性声明的四种判定结果。"""

    VERIFIED = "verified"
    MISSING_DECLARATION = "missing_declaration"
    CURRENT_NOT_LISTED = "current_not_listed"
    INVALID_DECLARATION = "invalid_declaration"


@dataclass(frozen=True, slots=True)
class FrameworkCompatibility:
    """保存声明内容及其与当前框架版本的匹配结果。"""

    status: FrameworkCompatibilityStatus
    current_version: str
    declared_versions: Tuple[str, ...] = ()
    invalid_entries: Tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        """只有完整合法的声明精确包含当前版本时才返回 True。"""
        return self.status is FrameworkCompatibilityStatus.VERIFIED


def evaluate_framework_compatibility(
    descriptor: Dict[str, Any],
    current_version: Optional[PluginVersion] = None,
) -> FrameworkCompatibility:
    """评估插件描述中的框架版本声明。

    Args:
        descriptor: 已解析的 IXPlugin.json 对象。
        current_version: 待匹配的框架版本；None 时使用 APP_VERSION。

    Returns:
        包含状态、规范化版本列表及非法条目的不可变结果。
    """
    current = (current_version or APP_VERSION).to_string()
    if COMPATIBILITY_FIELD not in descriptor:
        return _result(FrameworkCompatibilityStatus.MISSING_DECLARATION, current)
    raw_versions = descriptor[COMPATIBILITY_FIELD]
    if not isinstance(raw_versions, list) or not raw_versions:
        return _result(
            FrameworkCompatibilityStatus.INVALID_DECLARATION,
            current,
            invalid_entries=() if isinstance(raw_versions, list) else (str(raw_versions),),
        )
    declared, invalid = _normalize_versions(raw_versions)
    if invalid:
        status = FrameworkCompatibilityStatus.INVALID_DECLARATION
    elif current in declared:
        status = FrameworkCompatibilityStatus.VERIFIED
    else:
        status = FrameworkCompatibilityStatus.CURRENT_NOT_LISTED
    return _result(status, current, declared, invalid)


def _normalize_versions(raw_versions: list) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """规范化合法版本并收集非法项，保持声明顺序且去重。"""
    declared = []
    invalid = []
    for entry in raw_versions:
        if not isinstance(entry, str) or not entry.strip():
            invalid.append(str(entry))
            continue
        try:
            normalized = PluginVersion.from_string(entry.strip()).to_string()
        except ValueError:
            invalid.append(entry)
            continue
        if normalized not in declared:
            declared.append(normalized)
    return tuple(declared), tuple(invalid)


def _result(
    status: FrameworkCompatibilityStatus,
    current_version: str,
    declared_versions: Tuple[str, ...] = (),
    invalid_entries: Tuple[str, ...] = (),
) -> FrameworkCompatibility:
    """以统一字段顺序构造评估结果。"""
    return FrameworkCompatibility(
        status=status,
        current_version=current_version,
        declared_versions=declared_versions,
        invalid_entries=invalid_entries,
    )
