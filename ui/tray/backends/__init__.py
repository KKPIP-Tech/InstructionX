"""托盘平台后端装配点

顶部导入各平台后端实现并向 TRAY_BACKEND_REGISTRY 登记
（与 core/llm/providers/__init__.py 装配 PROVIDER_REGISTRY 同一模式）。
新增平台支持时：新建后端文件 + 在此处登记一行，门面与主窗口零改动。
"""

# ===================================================================
# 本地
from ..backend import GENERIC_BACKEND_KEY, register_tray_backend
from .windows import WindowsTrayBackend
from .generic import GenericTrayBackend

# Windows 平台后端
register_tray_backend("win32", WindowsTrayBackend)
# 未注册平台的保守兜底后端（create_tray_backend 的回退目标）
register_tray_backend(GENERIC_BACKEND_KEY, GenericTrayBackend)
# 未来扩展点：
# register_tray_backend("darwin", MacOSTrayBackend)
# register_tray_backend("linux", LinuxTrayBackend)
