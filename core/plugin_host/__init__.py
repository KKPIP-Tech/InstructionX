"""可选关键插件进程隔离能力；默认插件加载路径不受影响。"""

from .proxy import RemotePluginProxy
from .supervisor import (
    HostConfig,
    HostSnapshot,
    HostState,
    PluginHandle,
    PluginHost,
    PluginHostError,
    StopReport,
)

__all__ = [
    "HostConfig",
    "HostSnapshot",
    "HostState",
    "PluginHandle",
    "PluginHost",
    "PluginHostError",
    "RemotePluginProxy",
    "StopReport",
]
