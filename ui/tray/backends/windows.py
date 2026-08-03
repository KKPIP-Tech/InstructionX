"""Windows 平台托盘后端

Windows 任务栏通知区域完整支持 QSystemTrayIcon：
双击恢复是平台惯例，通知走系统 Toast（可能被专注助手屏蔽，
不作为功能正确性依赖）。
"""

from typing import Tuple

# ===================================================================
# PySide 相关
from PySide6.QtWidgets import QSystemTrayIcon

# ===================================================================
# 本地
from ..backend import TrayBackend, TrayCapabilities

# 托盘通知在屏幕上的驻留时长（毫秒）
TRAY_NOTIFICATION_TIMEOUT_MS = 5000


class WindowsTrayBackend(TrayBackend):
    """Windows 托盘后端：双击恢复 + Toast 通知提示。"""

    capabilities = TrayCapabilities(
        supports_icon_activation=True,
        supports_message=True,
        message_note="Windows Toast 通知（可能被专注助手或通知设置屏蔽）",
    )

    def is_tray_available(self) -> bool:
        """检测 Windows 通知区域是否可用。

        Returns:
            系统托盘可用返回 True
        """
        return QSystemTrayIcon.isSystemTrayAvailable()

    def activation_reasons(self) -> Tuple[QSystemTrayIcon.ActivationReason, ...]:
        """Windows 惯例：双击托盘图标恢复主窗口。

        Returns:
            仅包含 DoubleClick 的激活原因元组
        """
        return (QSystemTrayIcon.ActivationReason.DoubleClick,)

    def send_notification(self, tray: QSystemTrayIcon, title: str, message: str) -> bool:
        """通过 QSystemTrayIcon.showMessage 发送 Toast 通知。

        Args:
            tray: 托盘图标实例
            title: 通知标题
            message: 通知正文

        Returns:
            系统不支持气泡消息时返回 False（门面降级为仅记日志）
        """
        if not tray.supportsMessages():
            return False
        tray.showMessage(
            title, message,
            QSystemTrayIcon.MessageIcon.Information,
            TRAY_NOTIFICATION_TIMEOUT_MS,
        )
        return True
