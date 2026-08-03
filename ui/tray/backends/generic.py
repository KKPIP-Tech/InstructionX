"""保守兜底托盘后端

用于未在注册表中登记的平台（macOS/Linux 专用后端接入前的回退）：
仅保留菜单恢复这条各平台公共保底路径，不做图标激活恢复、
不弹气泡通知，避免在不熟悉的桌面环境上产生误导行为。
"""

from typing import Tuple

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import QSystemTrayIcon

# ===================================================================
# 本地
from ..backend import TrayBackend, TrayCapabilities


class GenericTrayBackend(TrayBackend):
    """保守兜底托盘后端：仅菜单恢复、不弹通知。"""

    capabilities = TrayCapabilities(
        supports_icon_activation=False,
        supports_message=False,
        message_note="未注册平台的保守兜底：仅菜单恢复，不弹气泡通知",
    )

    def is_tray_available(self) -> bool:
        """以 Qt 层检测结果兜底（如裸 GNOME 桌面返回 False）。

        Returns:
            系统托盘可用返回 True
        """
        return QSystemTrayIcon.isSystemTrayAvailable()

    def activation_reasons(self) -> Tuple[QSystemTrayIcon.ActivationReason, ...]:
        """兜底平台不假设图标点击语义（macOS 状态栏项点击弹菜单、
        Linux SNI 行为不统一），恢复只能走菜单项。

        Returns:
            空元组（门面据此完全不接 activated 信号）
        """
        return ()

    def send_notification(self, tray: QSystemTrayIcon, title: str, message: str) -> bool:
        """兜底后端不发送通知（渠道可用性不可假设）。

        Args:
            tray: 托盘图标实例（未使用）
            title: 通知标题（未使用）
            message: 通知正文（未使用）

        Returns:
            固定返回 False，门面降级为仅记日志
        """
        return False
