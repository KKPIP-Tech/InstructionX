"""
test/utils/ 专用 pytest 配置

- 覆盖根 conftest 的 autouse mock_logger，避免 LoggerManager 类被替换。
- 保存 LoggerManager 原始类，供测试直接实例化。
- 提供 QssRegistry 清理和 LoggerManager 零副作用初始化 fixture。
"""

from __future__ import annotations

import logging
import os
import sys
import types
from pathlib import Path

import pytest

# pytest 会把 test/ 目录加入 sys.path，导致 `import utils` 解析到 test/utils/，
# 从而遮蔽项目根目录的 utils 包。先移除该路径，再把项目根目录放到最前。
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_test_dir = str(_PROJECT_ROOT / "test")
if _test_dir in sys.path:
    sys.path.remove(_test_dir)
if str(_PROJECT_ROOT) in sys.path:
    sys.path.remove(str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT))

# 在全局 autouse mock 生效前捕获真实的 LoggerManager 类
import utils.logging_tools as _logging_tools_module

# utils/style_qss（registry/colors）与 utils/themes 已在 dev 分支重构中删除
# （由 ui/uikit_theme.py 取代），对应测试文件已失效：此处容错导入，
# 并用 collect_ignore 跳过失效测试文件的收集（文件本体保留，
# 待开发者确认后再删除）。
try:
    import utils.style_qss.registry as _registry_module
except ModuleNotFoundError:
    _registry_module = None

collect_ignore = [
    "test_style_qss_colors.py",
    "test_style_qss_registry.py",
    "test_themes.py",
]

_REAL_LOGGER_MANAGER = _logging_tools_module.LoggerManager


@pytest.fixture(autouse=True)
def mock_logger(mocker):
    """
    覆盖根 conftest 的 autouse mock_logger，避免替换 utils.logging_tools.LoggerManager。

    在 utils/ 测试中我们需要直接实例化真实的 LoggerManager 单例。
    """
    yield mocker.MagicMock()


@pytest.fixture
def real_logger_manager_class():
    """返回未被打补丁的 LoggerManager 类。"""
    return _REAL_LOGGER_MANAGER


@pytest.fixture
def patched_logger_env(real_logger_manager_class, monkeypatch):
    """
    提供一个零文件系统副作用的 LoggerManager 运行环境。

    - 重置单例状态
    - 拦截 os.makedirs / os.path.exists（不创建 logs/）
    - 用 DummyHandler 替换 RotatingFileHandler（不创建 application.log）
    """
    # 重置单例
    real_logger_manager_class._instance = None
    real_logger_manager_class._initialized = False

    calls = {"makedirs": [], "exists": []}
    config = {"exists_return": True}

    def fake_makedirs(path):
        calls["makedirs"].append(path)

    def fake_exists(path):
        calls["exists"].append(path)
        return config["exists_return"]

    fake_path = types.SimpleNamespace(
        exists=fake_exists,
        join=os.path.join,
    )
    fake_os = types.SimpleNamespace(
        makedirs=fake_makedirs,
        path=fake_path,
        environ=os.environ,
    )
    monkeypatch.setattr(_logging_tools_module, "os", fake_os)

    class DummyHandler(logging.Handler):
        def __init__(self, *args, **kwargs):
            super().__init__()

        def emit(self, record):
            pass

    monkeypatch.setattr(_logging_tools_module, "RotatingFileHandler", DummyHandler)

    yield {"calls": calls, "config": config}

    # 测试后彻底清理单例与底层 logger
    real_logger_manager_class._instance = None
    real_logger_manager_class._initialized = False
    app_logger = logging.getLogger("ApplicationLogger")
    app_logger.handlers.clear()
    app_logger.setLevel(logging.NOTSET)


@pytest.fixture
def fresh_logger_manager(real_logger_manager_class, patched_logger_env):
    """返回一个已经重置并 patched 的全新 LoggerManager 实例。"""
    return real_logger_manager_class()


@pytest.fixture(autouse=True)
def reset_qss_registry():
    """每个测试前后清空 QssRegistry 的类级状态（模块已删除时为空操作）。"""
    if _registry_module is None:
        yield
        return
    _registry_module.QssRegistry.clear()
    yield
    _registry_module.QssRegistry.clear()
