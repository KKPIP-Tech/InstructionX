"""系统托盘子系统

平台无关门面 TrayIconManager + 平台后端抽象（注册表/工厂模式）。
外部只需从本包导入 TrayIconManager。
"""

from .manager import TrayIconManager

__all__ = ["TrayIconManager"]
