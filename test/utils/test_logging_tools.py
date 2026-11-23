"""
utils/logging_tools.py 单元测试

所有 LoggerManager 测试都在 patched_logger_env fixture 中运行：
- os.makedirs / os.path.exists 被拦截
- RotatingFileHandler 被 DummyHandler 替换
因此不会创建 logs/ 目录或 application.log 文件。
"""

from __future__ import annotations

import inspect
import logging
import subprocess
import sys
import types
from pathlib import Path

import pytest

from utils.logging_tools import get_name


def test_logger_manager_singleton(real_logger_manager_class, patched_logger_env):
    """LoggerManager 应为单例。"""
    a = real_logger_manager_class()
    b = real_logger_manager_class()
    assert a is b


def test_initialization_creates_log_dir_when_missing(
    real_logger_manager_class, patched_logger_env
):
    """logs 目录不存在时应调用 os.makedirs('./logs')。"""
    patched_logger_env["config"]["exists_return"] = False
    real_logger_manager_class()
    assert patched_logger_env["calls"]["makedirs"] == ["./logs"]


def test_initialization_does_not_create_log_dir_when_existing(
    real_logger_manager_class, patched_logger_env
):
    patched_logger_env["config"]["exists_return"] = True
    real_logger_manager_class()
    assert patched_logger_env["calls"]["makedirs"] == []


def test_logger_configuration(fresh_logger_manager):
    logger = fresh_logger_manager.get_logger()
    assert logger.name == "ApplicationLogger"
    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1


def test_console_handler_added_in_development_mode(
    real_logger_manager_class, patched_logger_env, monkeypatch
):
    monkeypatch.setenv("DEVELOPMENT_MODE", "true")
    manager = real_logger_manager_class()
    assert len(manager.get_logger().handlers) == 2


def test_console_handler_not_added_without_development_mode(fresh_logger_manager):
    assert len(fresh_logger_manager.get_logger().handlers) == 1


def test_log_method_forwards_to_underlying_logger(fresh_logger_manager):
    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    fresh_logger_manager.get_logger().addHandler(ListHandler())
    fresh_logger_manager.log("INFO", "TestModule", "hello")

    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert records[0].message == "hello"
    assert getattr(records[0], "module_name", None) == "TestModule"


def test_level_methods_emit_correct_levels(fresh_logger_manager):
    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record)

    fresh_logger_manager.get_logger().addHandler(ListHandler())

    fresh_logger_manager.debug("M", "d")
    fresh_logger_manager.info("M", "i")
    fresh_logger_manager.warning("M", "w")
    fresh_logger_manager.error("M", "e")
    fresh_logger_manager.critical("M", "c")

    assert [r.levelno for r in records] == [
        logging.DEBUG,
        logging.INFO,
        logging.WARNING,
        logging.ERROR,
        logging.CRITICAL,
    ]
    for r in records:
        assert getattr(r, "module_name", None) == "M"


def test_log_invalid_level_raises(fresh_logger_manager):
    with pytest.raises(AttributeError):
        fresh_logger_manager.log("INVALID_LEVEL", "M", "msg")


def test_get_logger_returns_internal_logger(fresh_logger_manager):
    assert fresh_logger_manager.get_logger() is fresh_logger_manager._logger


# ---------------------------------------------------------------------------
# get_name 测试
# ---------------------------------------------------------------------------


def helper_get_name():
    """辅助函数：在模块内调用 get_name。"""
    return get_name()


class HelperClass:
    def method(self):
        return get_name()


def test_get_name_from_module_function():
    assert helper_get_name() == __name__


def test_get_name_from_class_method():
    assert HelperClass().method() == __name__


def test_get_name_direct_call_in_module():
    assert get_name() == __name__


def test_get_name_from_main_script(tmp_path):
    """在 __main__ 脚本中应返回去掉扩展名的文件名。"""
    script = tmp_path / "my_test_script.py"
    script.write_text(
        f"import sys\n"
        f"sys.path.insert(0, r'{Path(__file__).parent.parent.parent}')\n"
        f"from utils.logging_tools import get_name\n"
        f"print(get_name())\n"
    )
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "my_test_script"


def test_get_name_from_main_without_file():
    """通过 python -c 运行时 __main__.__file__ 为 '<string>'，返回该 basename。"""
    code = (
        f"import sys; sys.path.insert(0, r'{Path(__file__).parent.parent.parent}'); "
        f"from utils.logging_tools import get_name; print(get_name())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "<string>"


def test_get_name_returns_unknown_when_currentframe_none(monkeypatch):
    monkeypatch.setattr(inspect, "currentframe", lambda: None)
    assert get_name() == "unknown"


def test_get_name_returns_unknown_when_no_caller_frame(monkeypatch):
    monkeypatch.setattr(
        inspect, "currentframe", lambda: types.SimpleNamespace(f_back=None)
    )
    assert get_name() == "unknown"


def test_get_name_returns_unknown_when_getmodule_raises(monkeypatch):
    def raise_exception(frame):
        raise RuntimeError("inspect failure")

    monkeypatch.setattr(inspect, "getmodule", raise_exception)
    assert get_name() == "unknown"


def test_get_name_returns_unknown_when_no_filename(monkeypatch):
    """无法获取模块且 caller 的 code object 也没有文件名时返回 'unknown'。"""

    class FakeCode:
        co_filename = None

    class FakeFrame:
        f_back = types.SimpleNamespace(f_code=FakeCode())

    monkeypatch.setattr(inspect, "currentframe", lambda: FakeFrame())
    monkeypatch.setattr(inspect, "getmodule", lambda frame: None)
    assert get_name() == "unknown"
