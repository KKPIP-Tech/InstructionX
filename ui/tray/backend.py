"""系统托盘后端抽象层

定义平台托盘后端的能力位（TrayCapabilities）、抽象基类（TrayBackend），
以及注册表与工厂函数。平台差异全部收敛在 backend 实现中，
TrayIconManager 门面不出现任何 sys.platform 判断。

注册表采用「注册函数」装配（与 core/llm/providers 的 PROVIDER_REGISTRY
同一思路）：backend.py 只持有空注册表与通用键，具体后端在
ui/tray/backends/__init__.py 中导入并登记，避免抽象层反向依赖
实现层造成循环 import。

Classes:
    TrayCapabilities: 平台托盘能力位（frozen dataclass）
    TrayBackend: 平台托盘后端抽象基类

Functions:
    register_tray_backend: 登记平台键 -> 后端类
    create_tray_backend: 按 sys.platform 创建后端，未注册平台回退兜底后端
"""

import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Type

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import QSystemTrayIcon

# ===================================================================
# 自定义工具
from utils.logging_tools import LoggerManager, get_name

# 通用兜底后端在注册表中的键（backends/__init__.py 装配时登记）
GENERIC_BACKEND_KEY = "generic"


@dataclass(frozen=True)
class TrayCapabilities:
    """平台托盘能力位：门面据此决定行为，不做平台判断。

    Attributes:
        supports_icon_activation: 图标点击/双击恢复是否可靠
            （macOS 状态栏项无双击语义，应为 False → 仅菜单恢复）
        supports_message: 是否尝试气泡/通知提示
        message_note: 提示渠道的备注（记日志用）
    """
    supports_icon_activation: bool
    supports_message: bool
    message_note: str = ""


class TrayBackend(ABC):
    """平台托盘后端：封装平台差异，供 TrayIconManager 调用。"""

    capabilities: TrayCapabilities

    @abstractmethod
    def is_tray_available(self) -> bool:
        """检测当前桌面环境的托盘可用性。

        Returns:
            托盘可用返回 True（如 GNOME 无托盘扩展时应返回 False）
        """

    @abstractmethod
    def activation_reasons(self) -> Tuple[QSystemTrayIcon.ActivationReason, ...]:
        """返回哪些激活原因应触发「恢复主窗口」。

        Returns:
            激活原因元组（Windows: 双击；generic/macOS: 空元组）
        """

    @abstractmethod
    def send_notification(self, tray: QSystemTrayIcon, title: str, message: str) -> bool:
        """按平台渠道发送托盘通知。

        Args:
            tray: 托盘图标实例
            title: 通知标题
            message: 通知正文

        Returns:
            是否实际发出（失败时门面降级为仅记日志）
        """


# ===================================================================
# 注册表与工厂
# 平台键（sys.platform 值）-> 后端类，由 backends/__init__.py 装配
TRAY_BACKEND_REGISTRY: Dict[str, Type[TrayBackend]] = {}


def register_tray_backend(platform_key: str, backend_class: Type[TrayBackend]) -> None:
    """登记平台键与后端类的映射。

    Args:
        platform_key: 平台键（sys.platform 值，如 "win32"）
        backend_class: TrayBackend 实现类
    """
    TRAY_BACKEND_REGISTRY[platform_key] = backend_class


def create_tray_backend(platform_key: Optional[str] = None) -> TrayBackend:
    """按 sys.platform 创建托盘后端；未注册平台回退 GenericTrayBackend。

    Args:
        platform_key: 平台键，缺省时取 sys.platform（可注入便于测试）

    Returns:
        对应平台的托盘后端实例
    """
    key = platform_key if platform_key is not None else sys.platform
    backend_class = TRAY_BACKEND_REGISTRY.get(key)
    if backend_class is None:
        LoggerManager().info(
            get_name(), f"当前平台 {key} 未注册托盘后端，回退到保守兜底后端"
        )
        backend_class = TRAY_BACKEND_REGISTRY[GENERIC_BACKEND_KEY]
    return backend_class()
