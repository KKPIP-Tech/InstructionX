"""核心服务健康状态、错误分类与敏感信息清理契约。"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class HealthStatus(str, Enum):
    """核心服务健康等级，严重程度按定义顺序递增。"""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class HealthErrorCode(str, Enum):
    """框架统一错误类别，供日志、界面和插件降级逻辑使用。"""

    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    NETWORK = "network"
    PERMISSION = "permission"
    PERSISTENCE = "persistence"
    PLUGIN_CODE = "plugin_code"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class HealthSnapshot:
    """某一服务在某一时刻的健康状态快照。"""

    status: HealthStatus
    error_code: Optional[HealthErrorCode]
    message: str
    timestamp: datetime
    correlation_id: str


_SECRET_PATTERN = re.compile(
    r"(?i)\b(authorization|api[_-]?key|token|password|secret)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
_REDACTED = "[已脱敏]"
_MAX_HEALTH_MESSAGE_LENGTH = 300


def sanitize_health_message(message: object) -> str:
    """清理健康消息中的常见凭据并限制长度，避免日志和界面泄密。"""
    text = str(message or "")
    text = _SECRET_PATTERN.sub(lambda match: f"{match.group(1)}={_REDACTED}", text)
    return _BEARER_PATTERN.sub(f"Bearer {_REDACTED}", text)[:_MAX_HEALTH_MESSAGE_LENGTH]


def classify_exception(error: BaseException) -> HealthErrorCode:
    """按异常类型给出默认错误分类，调用方可传入更准确的领域分类。"""
    if isinstance(error, PermissionError):
        return HealthErrorCode.PERMISSION
    if isinstance(error, ConnectionError):
        return HealthErrorCode.NETWORK
    if isinstance(error, sqlite3.Error):
        return HealthErrorCode.PERSISTENCE
    if isinstance(error, OSError):
        return HealthErrorCode.RESOURCE
    if isinstance(error, ImportError):
        return HealthErrorCode.PLUGIN_CODE
    if isinstance(error, ValueError):
        return HealthErrorCode.CONFIGURATION
    return HealthErrorCode.INTERNAL
