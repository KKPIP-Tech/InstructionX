"""
pytest 全局配置文件

提供测试所需的全部 fixtures，包括：
- 单例重置（autouse）
- QApplication 实例
- 临时目录 fixtures
- Mock logger
"""
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，确保跨目录导入正常
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import pytest


# ============================================================================
# 1. 单例重置 fixtures
# ============================================================================

@pytest.fixture(autouse=True)
def reset_singletons():
    """
    每个测试前后重置所有单例，保证测试隔离。

    重置目标：
    - PluginManager._instance / _initialized
    - DataProvider._instance
    - BackgroundTaskManager._instance / _initialized
    - TaskStorage._instance
    - LLMProvider._instance
    - LLMPluginService (模块级 _instance)
    """
    import core.plugin.manager
    import core.data.data_provider
    import core.task.background_task
    import core.task.task_storage
    import core.llm.llm_provider
    import core.llm.plugin_service
    import core.llm.usage_record_store

    # 重置前先执行 shutdown（如果实例存在）
    for btm in [core.task.background_task.BackgroundTaskManager._instance]:
        if btm is not None:
            try:
                btm.shutdown()
            except Exception:
                pass

    # 重置 PluginManager
    core.plugin.manager.PluginManager._instance = None
    core.plugin.manager.PluginManager._initialized = False

    # 重置 DataProvider
    core.data.data_provider.DataProvider._instance = None

    # 重置 BackgroundTaskManager
    if core.task.background_task.BackgroundTaskManager._instance is not None:
        try:
            core.task.background_task.BackgroundTaskManager._instance.shutdown()
        except Exception:
            pass
    core.task.background_task.BackgroundTaskManager._instance = None
    core.task.background_task.BackgroundTaskManager._initialized = False

    # 重置 TaskStorage
    core.task.task_storage.TaskStorage._instance = None

    # 重置 UsageRecordStore
    core.llm.usage_record_store.UsageRecordStore._instance = None

    # 重置 LLMProvider
    if core.llm.llm_provider.LLMProvider._instance is not None:
        try:
            core.llm.llm_provider.LLMProvider._instance.close()
        except Exception:
            pass
    core.llm.llm_provider.LLMProvider._instance = None

    # 重置 LLMPluginService
    core.llm.plugin_service._instance = None

    # 重置 MCPManager 模块级单例
    import core.mcp.manager as mcp_manager_module
    mcp_manager_module._module_instance = None

    # 等待 UsageRecordStore 后台线程完成，避免测试间污染
    import core.llm.usage_record_store as urs
    if urs.UsageRecordStore._instance is not None:
        try:
            urs.UsageRecordStore._instance._pending_write = False
        except Exception:
            pass

    yield

    # 测试后清理
    try:
        if core.task.background_task.BackgroundTaskManager._instance is not None:
            core.task.background_task.BackgroundTaskManager._instance.shutdown()
    except Exception:
        pass
    core.task.background_task.BackgroundTaskManager._instance = None
    core.task.background_task.BackgroundTaskManager._initialized = False

    # 等待 UsageRecordStore 后台保存线程完成，避免写入真实 data/llm_usage.json
    import threading
    import time
    for t in threading.enumerate():
        if t.name == "UsageRecordStore-async-save":
            try:
                t.join(timeout=0.5)
            except Exception:
                pass


# ============================================================================
# 2. 临时目录 fixtures
# ============================================================================

@pytest.fixture
def temp_data_dir(tmp_path, mocker):
    """
    临时数据目录，用于 DataProvider / TaskStorage。

    同时 patch 相关的路径常量。
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    yield data_dir


@pytest.fixture
def temp_config_dir(tmp_path, mocker):
    """
    临时配置目录，用于 LLMConfig / PluginConfigManager。
    """
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    yield cfg_dir


@pytest.fixture
def temp_plugin_dir(tmp_path):
    """
    临时插件目录结构，返回顶层目录。
    测试用例可调用 create_minimal_plugin() 填充内容。
    """
    p = tmp_path / "plugins"
    p.mkdir(parents=True)
    return p


# ============================================================================
# 3. Mock Logger (autouse)
# ============================================================================

@pytest.fixture(autouse=True)
def mock_logger(mocker):
    """
    全局禁用 LoggerManager 写日志。

    替换所有模块中的 LoggerManager 引用，防止测试时写入 logs/ 目录。
    """
    logger_mock = mocker.MagicMock()
    mocker.patch("utils.logging_tools.LoggerManager", return_value=logger_mock)
    mocker.patch("core.plugin.manager.LoggerManager", return_value=logger_mock)
    mocker.patch("core.plugin.plugin_identity.LoggerManager", return_value=logger_mock)
    mocker.patch("core.plugin.config_manager.LoggerManager", return_value=logger_mock)
    mocker.patch("core.data.data_provider.LoggerManager", return_value=logger_mock)
    mocker.patch("core.task.background_task.LoggerManager", return_value=logger_mock)
    mocker.patch("core.task.task_storage.LoggerManager", return_value=logger_mock)
    mocker.patch("core.task.scheduler.LoggerManager", return_value=logger_mock)
    mocker.patch("core.llm.llm_provider.LoggerManager", return_value=logger_mock)
    return logger_mock


# ============================================================================
# 4. PySide6 QApplication fixture
# ============================================================================

@pytest.fixture(scope="session")
def qapp_instance():
    """
    Session 级 QApplication 实例，使用 offscreen 平台避免 GUI 渲染。

    所有 UI 测试共享同一个 QApplication 实例。
    """
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(["-platform", "offscreen"])
    yield app


@pytest.fixture
def qtbot(qtbot):
    """
    提供 qtbot 实例，确保每个测试后清理 widget。
    """
    return qtbot


@pytest.fixture
def app_instance(qtbot):
    """
    组合 fixture：QApplication + 单例重置。

    UI 测试使用此 fixture 确保 Qt 上下文和单例隔离同时生效。
    """
    return qtbot
