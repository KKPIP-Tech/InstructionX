"""日志、指标与健康快照共用的递归敏感信息清理。"""

import re
import threading
from typing import Any, Dict, Iterable

REDACTED = "[已脱敏]"
MAX_TEXT_LENGTH = 4096
_MAX_RECURSION_DEPTH = 8
_DEFAULT_SENSITIVE_FIELDS = frozenset({
    "authorization", "api_key", "apikey", "token", "access_token", "refresh_token",
    "password", "secret", "client_secret", "patient", "patient_id", "patient_name",
    "medical_record", "medical_record_number", "id_card", "pii", "phi", "sensitive",
})
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_CUSTOM_FIELDS: set[str] = set()
_CUSTOM_LOCK = threading.Lock()
_FIELD_PATTERN_CACHE = None
_FIELD_PATTERN_DIRTY = True


def _normalize_field(name: object) -> str:
    return str(name).strip().strip("\"'").lower().replace("-", "_").replace(" ", "_")


def register_sensitive_fields(*names: str) -> None:
    """注册插件自定义敏感字段标记，后续日志与快照均按名称脱敏。"""
    global _FIELD_PATTERN_DIRTY
    normalized = {_normalize_field(name) for name in names if _normalize_field(name)}
    with _CUSTOM_LOCK:
        new_fields = normalized - _CUSTOM_FIELDS
        if new_fields:
            _CUSTOM_FIELDS.update(new_fields)
            _FIELD_PATTERN_DIRTY = True


def is_sensitive_field(name: object) -> bool:
    """判断字段是否属于内置或插件注册的敏感标记。"""
    normalized = _normalize_field(name)
    with _CUSTOM_LOCK:
        custom = normalized in _CUSTOM_FIELDS
    return normalized in _DEFAULT_SENSITIVE_FIELDS or custom


def _field_pattern() -> re.Pattern:
    global _FIELD_PATTERN_CACHE, _FIELD_PATTERN_DIRTY
    with _CUSTOM_LOCK:
        if not _FIELD_PATTERN_DIRTY and _FIELD_PATTERN_CACHE is not None:
            return _FIELD_PATTERN_CACHE
        names = _DEFAULT_SENSITIVE_FIELDS | _CUSTOM_FIELDS
        alternatives = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
        _FIELD_PATTERN_CACHE = re.compile(
            rf"(?i)(?P<prefix>[\"']?(?:{alternatives})[\"']?\s*[:=]\s*)"
            rf"(?P<quote>[\"']?)(?P<value>(?:bearer\s+)?[^\s,;&\"']+)(?P=quote)"
        )
        _FIELD_PATTERN_DIRTY = False
        return _FIELD_PATTERN_CACHE


def sanitize_text(value: object) -> str:
    """清理文本中的 Bearer 和敏感键值，并限制单条诊断文本长度。"""
    text = str(value or "")
    text = _field_pattern().sub(
        lambda match: f"{match.group('prefix')}{match.group('quote')}{REDACTED}{match.group('quote')}",
        text,
    )
    text = _BEARER_PATTERN.sub(f"Bearer {REDACTED}", text)
    return text[:MAX_TEXT_LENGTH]


def sanitize_value(value: Any, depth: int = 0) -> Any:
    """递归清理字典键、序列与文本，未知对象仅保留脱敏字符串。"""
    if depth >= _MAX_RECURSION_DEPTH:
        return "[超出嵌套上限]"
    if isinstance(value, dict):
        return _sanitize_dict(value, depth)
    if isinstance(value, list):
        return [sanitize_value(item, depth + 1) for item in value]
    if isinstance(value, tuple):
        return tuple(sanitize_value(item, depth + 1) for item in value)
    if isinstance(value, (str, bytes, BaseException)):
        return sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return sanitize_text(value)


def _sanitize_dict(value: Dict[Any, Any], depth: int) -> Dict[Any, Any]:
    result = {}
    for key, item in value.items():
        safe_key = sanitize_text(key)
        result[safe_key] = REDACTED if is_sensitive_field(key) else sanitize_value(item, depth + 1)
    return result
