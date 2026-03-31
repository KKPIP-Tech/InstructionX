# InstructionX 测试系统文档

## 目录

1. [概述](#1-概述)
2. [测试环境配置](#2-测试环境配置)
3. [测试目录结构](#3-测试目录结构)
4. [测试框架与依赖](#4-测试框架与依赖)
5. [测试用例设计](#5-测试用例设计)
6. [运行测试](#6-运行测试)
7. [测试标记与分类](#7-测试标记与分类)
8. [Fixtures 说明](#8-fixtures-说明)
9. [添加新测试](#9-添加新测试)
10. [最佳实践](#10-最佳实践)
11. [常见问题](#11-常见问题)

---

## 1. 概述

本文档详细介绍 InstructionX 项目的测试系统，包括测试框架选择、目录结构设计、测试用例覆盖范围以及运行方式。

### 1.1 测试目标

- 确保核心模块（插件系统、数据层、任务系统）的功能正确性
- 验证 LLM 提供商的 API 调用和错误处理
- 测试 UI 组件的基本功能
- 提供回归测试保障代码质量

### 1.2 测试类型

| 类型 | 说明 |
|------|------|
| 单元测试 | 针对单个模块/函数的独立测试 |
| 集成测试 | 测试多个模块之间的协作 |
| GUI 测试 | 测试 Qt UI 组件的行为 |

---

## 2. 测试环境配置

### 2.1 安装测试依赖

项目依赖通过 `requirements.txt` 管理，测试相关依赖：

```txt
# Testing dependencies
pytest==8.3.5
pytest-qt==4.4.0
pytest-mock==3.14.0
pytest-cov==6.1.1
```

安装命令：

```bash
pip install -r requirements.txt
```

### 2.2 虚拟环境

项目使用虚拟环境 (`.venv`)，确保在虚拟环境中运行测试：

```bash
# 激活虚拟环境
.venv\Scripts\activate

# 运行测试
pytest
```

---

## 3. 测试目录结构

```
InstructionX/
├── tests/                          # 测试根目录
│   ├── conftest.py                 # pytest 全局配置
│   ├── fixtures/                   # 共享 fixtures
│   │   ├── __init__.py
│   │   ├── app.py                  # QApplication fixture
│   │   ├── plugin_manager.py        # 插件管理器 fixture
│   │   └── data_provider.py         # 数据提供者 fixture
│   │
│   ├── unit/                       # 单元测试
│   │   ├── __init__.py
│   │   ├── test_plugin_system/     # 插件系统测试
│   │   │   ├── __init__.py
│   │   │   ├── test_plugin_interface.py
│   │   │   └── test_manager.py
│   │   ├── test_data_layer/        # 数据层测试
│   │   │   ├── __init__.py
│   │   │   └── test_data_provider.py
│   │   ├── test_task_system/       # 任务系统测试
│   │   │   ├── __init__.py
│   │   │   └── test_background_task.py
│   │   ├── test_llm_providers/     # LLM 提供商测试
│   │   │   ├── __init__.py
│   │   │   └── test_providers.py
│   │   └── test_utils/             # 工具类测试
│   │       ├── __init__.py
│   │       ├── test_logging.py
│   │       └── test_theme.py
│   │
│   ├── integration/                # 集成测试
│   │   ├── __init__.py
│   │   └── test_plugin_load.py
│   │
│   └── gui/                       # GUI 测试
│       ├── __init__.py
│       ├── test_main_window.py
│       └── test_panels.py
│
├── pytest.ini                     # pytest 配置
└── scripts/
    └── run_tests.bat              # 本地测试脚本
```

---

## 4. 测试框架与依赖

### 4.1 框架选择

| 框架 | 版本 | 用途 |
|------|------|------|
| pytest | 8.3.5 | 主测试框架 |
| pytest-qt | 4.4.0 | Qt/PySide6 GUI 测试 |
| pytest-mock | 3.14.0 | Mock 对象支持 |
| pytest-cov | 6.1.1 | 覆盖率统计 |

### 4.2 pytest.ini 配置

```ini
[pytest]
testpaths = tests                    # 测试目录
python_files = test_*.py              # 测试文件命名规则
python_classes = Test*                # 测试类命名规则
python_functions = test_*             # 测试函数命名规则
addopts = -v --strict-markers --tb=short  # 运行时选项
markers =
    slow: marks tests as slow
    gui: marks tests requiring GUI
    integration: marks integration tests
    unit: marks unit tests
    llm: marks tests requiring LLM API
filterwarnings =
    ignore::DeprecationWarning
    ignore::PendingDeprecationWarning
```

---

## 5. 测试用例设计

### 5.1 插件系统测试 (test_plugin_system)

#### 5.1.1 插件接口测试 (test_plugin_interface.py)

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_plugin_name_normal | 正常插件名称 | 名称正确返回 |
| test_plugin_name_empty | 空插件名称 | 空字符串处理 |
| test_plugin_name_special_chars | 特殊字符名称 | Unicode/特殊字符支持 |
| test_plugin_version_normal | 正常版本号 | 版本格式正确 |
| test_plugin_version_empty | 空版本号 | 默认值处理 |
| test_create_widget_normal | 创建 Widget | Widget 实例化成功 |
| test_create_widget_no_parent | 无父窗口创建 | None 参数处理 |
| test_plugin_enable_disable | 启用/禁用 | 状态切换正确 |

#### 5.1.2 插件管理器测试 (test_manager.py)

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_pm_07_get_all_plugins_empty | 空插件列表 | 返回空列表 |
| test_pm_07_get_all_plugins_with_mock | 多插件列表 | 插件数量正确 |
| test_pm_08_plugin_order_file | 插件排序文件 | 文件读写正确 |
| test_pm_03_get_plugin_by_id | 通过ID获取插件 | 不存在的ID返回None |
| test_pm_09_get_plugin_by_name | 通过名称获取插件 | 名称匹配正确 |
| test_pm_01_load_official_plugin | 加载官方插件 | 目录结构验证 |
| test_pm_04_broken_plugin | 损坏插件 | 语法错误处理 |
| test_pm_05_uuid_generation | UUID生成 | 格式正确 |

#### 5.1.3 插件身份测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_generate_uuid | UUID生成 | 生成唯一ID |
| test_uuid_format | UUID格式 | 8-4-4-4-12 格式 |

#### 5.1.4 插件信息接口测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_iplugin_info_is_abstract | 抽象类验证 | ABC继承正确 |
| test_iplugin_info_properties | 属性验证 | 所有抽象属性存在 |

### 5.2 数据层测试 (test_data_layer)

#### 5.2.1 DataProvider 测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_dp_01_basic_operations | 基本操作 | 缓存/订阅结构存在 |
| test_dp_02_cache_structure | 缓存结构 | 字典操作正确 |
| test_dp_03_pubsub_structure | 发布订阅结构 | 主题管理正确 |
| test_dp_04_serialization_nested | 嵌套序列化 | 复杂结构存储 |

#### 5.2.2 DAO 测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_dao_01_create_table | 创建表 | SQL执行成功 |
| test_dao_01_crud_operations | CRUD完整流程 | Create/Read/Update/Delete |
| test_dao_02_transaction_rollback | 事务回滚 | 错误时数据回滚 |
| test_dao_03_concurrent_access | 并发访问 | 多线程安全 |

### 5.3 任务系统测试 (test_task_system)

#### 5.3.1 任务管理器测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_btm_01_sync_task_creation | 同步任务创建 | 任务队列初始化 |
| test_btm_04_task_priority | 任务优先级 | 优先级设置正确 |
| test_btm_07_concurrency_limit | 并发限制 | 最大并发数正确 |
| test_btm_08_task_result_storage | 结果存储 | 存储结构正确 |

#### 5.3.2 任务模型测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_task_status_values | 状态枚举 | PENDING/RUNNING/COMPLETED/FAILED/CANCELLED |
| test_task_type_values | 类型枚举 | SYNC/ASYNC/SCHEDULED |
| test_background_task_creation | 任务创建 | 属性正确设置 |

#### 5.3.3 调度器测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_sc_01_cron_valid | 有效Cron | 表达式解析 |
| test_sc_01_cron_invalid | 无效Cron | 错误处理 |

### 5.4 LLM 提供商测试 (test_llm_providers)

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_llm_05_switch_provider | 提供商切换 | 切换逻辑正确 |
| test_llm_05_switch_during_request | 切换中请求 | 并发处理 |
| test_provider_creation_siliconflow | SiliconFlow创建 | 实例化成功 |
| test_provider_creation_ollama | Ollama创建 | 实例化成功 |
| test_provider_creation_minimax | MiniMax创建 | 实例化成功 |
| test_provider_creation_glm | GLM创建 | 实例化成功 |

### 5.5 工具类测试 (test_utils)

#### 5.5.1 日志测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_lm_01_log_debug | DEBUG级别 | 输出正确 |
| test_lm_01_log_info | INFO级别 | 输出正确 |
| test_lm_01_log_warning | WARNING级别 | 输出正确 |
| test_lm_01_log_error | ERROR级别 | 输出正确 |
| test_lm_04_multiple_modules | 多模块 | 模块隔离 |
| test_lm_05_format_json | JSON格式 | 格式化正确 |
| test_lm_06_concurrent_write | 并发写入 | 线程安全 |
| test_log_to_file | 文件日志 | 写入成功 |
| test_log_rotation_size | 日志轮转 | 轮转触发 |

#### 5.5.2 主题测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_th_01_theme_import | 模块导入 | 导入成功 |
| test_theme_switch_basic | 主题切换 | 切换逻辑 |
| test_th_03_load_valid_theme | 加载有效主题 | 文件解析 |
| test_th_03_load_invalid_theme | 加载无效主题 | 错误处理 |
| test_theme_colors_basic | 颜色值 | 格式正确 |

### 5.6 GUI 测试

#### 5.6.1 主窗口测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_mw_01_window_creation | 窗口创建 | 实例化成功 |
| test_mw_03_resize_window | 调整大小 | 尺寸正确 |
| test_mw_02_menu_exists | 菜单存在 | 菜单栏正确 |
| test_mw_02_menu_actions | 菜单动作 | 动作触发 |

#### 5.6.2 面板测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_sp_01_empty_list | 空列表 | 显示0个 |
| test_sp_01_single_plugin | 单插件 | 显示1个 |
| test_sp_01_multiple_plugins | 多插件 | 显示多个 |
| test_sp_02_search_normal | 正常搜索 | 过滤正确 |
| test_sp_04_plugin_enable_disable | 启用/禁用 | 状态切换 |
| test_wa_01_show_plugin | 显示插件 | Widget显示 |
| test_wa_02_multiple_tabs | 多标签 | 标签管理 |
| test_wa_03_layout_resolution | 分辨率布局 | 自适应 |

### 5.7 集成测试

| 用例ID | 测试场景 | 验证点 |
|--------|----------|--------|
| test_full_plugin_loading | 完整加载流程 | 插件目录结构 |
| test_plugin_dependency_resolution | 依赖解析 | JSON解析 |
| test_plugin_registry_structure | 注册表结构 | 管理器属性 |
| test_task_manager_structure | 任务管理器 | 单例模式 |
| test_complete_plugin_workflow | 完整工作流 | 端到端 |

---

## 6. 运行测试

### 6.1 基本命令

```bash
# 运行所有测试
pytest

# 运行特定目录
pytest tests/unit/
pytest tests/integration/
pytest tests/gui/

# 运行特定文件
pytest tests/unit/test_plugin_system/test_plugin_interface.py

# 运行特定测试类
pytest tests/unit/test_plugin_system/test_plugin_interface.py::TestIPluginInterface

# 运行特定测试函数
pytest tests/unit/test_plugin_system/test_plugin_interface.py::TestIPluginInterface::test_plugin_name_normal
```

### 6.2 常用选项

```bash
# 详细输出
pytest -v

# 显示简短的失败信息
pytest --tb=short

# 在第一个失败时停止
pytest -x

# 显示完整的回溯信息
pytest --tb=long

# 只运行失败的测试
pytest --lf (--last-failed)

# 显示测试覆盖率
pytest --cov=core --cov-report=html
```

### 6.3 使用标记过滤

```bash
# 只运行单元测试
pytest -m unit

# 只运行集成测试
pytest -m integration

# 只运行 GUI 测试
pytest -m gui

# 排除慢速测试
pytest -m "not slow"

# 排除 LLM 测试（可能产生费用）
pytest -m "not llm"
```

### 6.4 使用本地脚本

```bash
# Windows
scripts\run_tests.bat
```

脚本会依次执行：
1. 检查 Python 和依赖
2. 运行单元测试
3. 运行集成测试
4. 运行 GUI 测试
5. 生成覆盖率报告

---

## 7. 测试标记与分类

### 7.1 内置标记

在 `pytest.ini` 中定义：

```ini
markers =
    slow:        # 慢速测试
    gui:         # 需要 GUI 的测试
    integration: # 集成测试
    unit:        # 单元测试
    llm:         # LLM API 测试（可能产生费用）
```

### 7.2 使用标记

```python
@pytest.mark.slow
def test_something_slow():
    """这是一个慢速测试"""
    pass

@pytest.mark.gui
class TestMainWindow:
    """GUI 测试类"""
    pass

@pytest.mark.integration
def test_plugin_load():
    """集成测试"""
    pass

@pytest.mark.llm
def test_llm_api():
    """LLM API 测试"""
    pass
```

---

## 8. Fixtures 说明

### 8.1 全局 Fixtures (conftest.py)

```python
@pytest.fixture(scope="session")
def project_root_path():
    """返回项目根目录路径"""
    return project_root

@pytest.fixture
def temp_dir():
    """返回临时目录 fixture"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)

@pytest.fixture
def mock_qapp():
    """Mock QApplication"""
    ...

@pytest.fixture
def plugin_dirs(temp_dir):
    """创建临时插件目录"""
    ...

@pytest.fixture
def sample_plugin_info():
    """示例插件信息"""
    ...

@pytest.fixture
def mock_plugin():
    """模拟插件对象"""
    ...
```

### 8.2 App Fixtures (fixtures/app.py)

```python
@pytest.fixture(scope="session")
def qapp():
    """QApplication fixture for GUI tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

@pytest.fixture
def qapp_widget(qapp):
    """临时 QWidget"""
    widget = QWidget()
    yield widget
    widget.deleteLater()
```

### 8.3 Plugin Manager Fixtures (fixtures/plugin_manager.py)

```python
@pytest.fixture
def temp_plugin_dir(tmp_path):
    """创建临时插件目录"""
    ...

@pytest.fixture
def mock_plugin_manager(temp_plugin_dir):
    """模拟 PluginManager"""
    ...

@pytest.fixture
def sample_plugin_module():
    """示例插件代码"""
    ...
```

### 8.4 Data Provider Fixtures (fixtures/data_provider.py)

```python
@pytest.fixture
def temp_db(tmp_path):
    """临时数据库"""
    ...

@pytest.fixture
def in_memory_db():
    """内存数据库"""
    ...

@pytest.fixture
def mock_data_provider():
    """模拟 DataProvider"""
    ...

@pytest.fixture
def data_provider_with_data(mock_data_provider):
    """带数据的 DataProvider"""
    ...
```

---

## 9. 添加新测试

### 9.1 添加单元测试

1. 在 `tests/unit/<module>/` 目录下创建或修改测试文件
2. 命名规则：`test_*.py`
3. 测试类命名：`Test*`
4. 测试函数命名：`test_*`

示例：

```python
# tests/unit/test_example/test_module.py
import pytest

class TestModuleName:
    """测试模块名称"""

    @pytest.fixture
    def setup_object(self):
        """设置测试对象"""
        # 准备测试数据
        return SomeObject()

    def test_something(self, setup_object):
        """测试某个功能"""
        result = setup_object.do_something()
        assert result == expected
```

### 9.2 添加 GUI 测试

```python
import pytest
from PySide6.QtWidgets import QApplication

@pytest.mark.gui
class TestMyWidget:
    """测试自定义控件"""

    @pytest.fixture
    def qapp(self):
        """QApplication fixture"""
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_widget_creation(self, qapp):
        """测试控件创建"""
        from mymodule import MyWidget
        widget = MyWidget()
        assert widget is not None
        widget.deleteLater()
```

### 9.3 添加集成测试

```python
import pytest

@pytest.mark.integration
class TestFeature:
    """集成测试"""

    def test_full_workflow(self):
        """完整的业务流程测试"""
        # 模拟用户操作流程
        ...
```

---

## 10. 最佳实践

### 10.1 测试命名

- 测试函数名应清晰描述测试内容
- 使用下划线分隔单词
- 以 `test_` 开头

```python
# Good
def test_user_can_login_with_valid_credentials():
    ...

def test_plugin_manager_loads_official_plugins():
    ...

# Bad
def test_login():
    ...

def test_load():
    ...
```

### 10.2 测试结构

```python
class TestSomething:
    """测试某个功能"""

    def setup_method(self):
        """每个测试前执行"""
        self.obj = create_object()

    def teardown_method(self):
        """每个测试后执行"""
        self.obj.cleanup()

    def test_case_1(self):
        """测试场景1"""
        ...

    def test_case_2(self):
        """测试场景2"""
        ...
```

### 10.3 断言使用

```python
# Good - 清晰的断言消息
assert result == expected, f"Expected {expected}, got {result}"

# Good - 使用 pytest 内置断言
assert response.status_code == 200
assert "error" not in response.body

# Bad - 过于简单
assert result
```

### 10.4 Mock 使用

```python
from unittest.mock import MagicMock, patch

def test_with_mock():
    """使用 Mock 测试"""
    with patch("module.ClassName") as mock:
        mock.return_value = "mocked"
        # 测试代码
        ...

def test_with_magic_mock():
    """使用 MagicMock"""
    mock = MagicMock()
    mock.method.return_value = "value"
    # 测试代码
    ...
```

### 10.5 Fixture 复用

```python
# 在 conftest.py 中定义
@pytest.fixture
def common_setup():
    """通用设置"""
    return setup_data()

# 在测试文件中使用
def test_something(common_setup):
    """使用通用 fixture"""
    ...
```

---

## 11. 常见问题

### 11.1 QApplication 问题

**问题**: `QApplication instance has not been created yet`

**解决**: 使用 `qapp` fixture

```python
@pytest.fixture
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app
```

### 11.2 单例模式测试

**问题**: 测试间状态污染

**解决**: 在测试前重置单例

```python
@pytest.fixture(autouse=True)
def reset_singleton():
    """重置单例状态"""
    SomeClass._instance = None
    SomeClass._initialized = False
    yield
    SomeClass._instance = None
    SomeClass._initialized = False
```

### 11.3 导入错误

**问题**: `ImportError: cannot import name`

**解决**: 检查模块路径和导入顺序

```python
# 确保在 sys.path 中添加项目根目录
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
```

### 11.4 异步测试

**问题**: 异步函数测试

**解决**: 使用 `pytest-asyncio`

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result == expected
```

### 11.5 覆盖率查看

```bash
# 生成 HTML 覆盖率报告
pytest --cov=core --cov=ui --cov-report=html

# 查看报告
# 报告生成在 htmlcov/index.html
```

---

## 附录

### A. 测试结果解读

```
======================== 72 passed, 4 skipped in 0.72s ========================
```

| 状态 | 说明 |
|------|------|
| passed | 测试通过 |
| skipped | 测试跳过（通常因为依赖不可用） |
| failed | 测试失败 |
| error | 测试错误（通常是导入或设置问题） |

### B. 文件修改记录

以下文件被创建或修改以支持测试：

| 文件 | 操作 | 说明 |
|------|------|------|
| `requirements.txt` | 修改 | 添加测试依赖 |
| `pytest.ini` | 新建 | pytest 配置 |
| `tests/` | 新建 | 测试目录及文件 |
| `scripts/run_tests.bat` | 新建 | 本地测试脚本 |

### C. 相关文档

- [pytest 官方文档](https://docs.pytest.org/)
- [pytest-qt 文档](https://pytest-qt.readthedocs.io/)
- [Python unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
