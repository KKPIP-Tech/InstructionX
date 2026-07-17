# 延迟导出（PEP 562）：按需加载，避免 import utils 或仅使用 utils.i_logger 等
# 轻量子模块时牵入 themes / PySide6 等重量依赖。
# 既有导入路径保持不变：from utils import set_style_qss_theme, LoggerManager, get_name

_LAZY_EXPORTS = {
    "set_style_qss_theme": ("utils.themes", "set_style_qss_theme"),
    "LoggerManager": ("utils.logging_tools", "LoggerManager"),
    "get_name": ("utils.logging_tools", "get_name"),
    "is_ui_thread": ("utils.thread_utils", "is_ui_thread"),
    "run_in_ui_thread": ("utils.thread_utils", "run_in_ui_thread"),
    "run_in_ui_thread_sync": ("utils.thread_utils", "run_in_ui_thread_sync"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    import importlib
    module = importlib.import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value  # 缓存到模块命名空间，后续访问不再触发 __getattr__
    return value


__all__ = [
    "set_style_qss_theme",

    "LoggerManager",
    "get_name",

    "is_ui_thread",
    "run_in_ui_thread",
    "run_in_ui_thread_sync",
]
