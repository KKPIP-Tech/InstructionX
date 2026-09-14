# InstructionX 测试文档

> 测试策略、规范和快速参考指南

---

## 1. 测试概述

### 1.1 测试目标

- 确保核心组件（PluginManager、DataProvider、BackgroundTaskManager、LLMProvider、MCPManager）的行为正确
- 验证插件系统的加载、注册、调用机制
- 保证 UI 组件的基本交互逻辑
- 实现持续集成中的自动化回归检测

### 1.2 测试范围

> 下表为实测值（`pytest test/<模块> --collect-only -q` 统计，随测试增删需同步更新）。

| 模块 | 测试文件数 | 测试用例数 | 覆盖范围 |
|------|-----------|-----------|---------|
| core.data | 1 | 36 | DataProvider 全部公开 API（含单例/注册表/迁移/LRU/并发/资源路径） |
| core.font | 1 | 16 | FontManager 安装/卸载/注册表持久化/系统字体回退 |
| core.llm | 18 | 283 | LLMProvider, ConversationManager, Config, Types, Exceptions, ToolCallExecutor, PluginService, 适配器注册表, 模型 schema, 用量记录 |
| core.mcp | 6 | 93 | Manager, Client, Server, Bridge, Config, PluginInterface |
| core.plugin | 7 | 153 | Manager, Identity, ConfigManager, Version, DependencyManager, 插件 API 自动注册, 插件图标 |
| core.task | 4 | 72 | BackgroundTaskManager, TaskModel, TaskStorage, 优雅关闭 |
| core（版本号） | 1 | 9 | `core/version.py` 单一来源与 pyproject 动态版本约束 |
| ui_tests | 10 | 86 | MainWindow, SkillsPanel, 关闭事件分发, 应用标识, LLM 设置对话框（列表/详情/编辑器/模型编辑）, 用量趋势面板渲染通路 |
| uikit | 2 | 33 | 蓝图节点注册表命名空间隔离；UIKit 同步副本守卫（版本钉子/导入契约/新增能力） |
| utils | 5 | 29 | LoggerManager, 线程工具, 旧样式表兼容与主题 |
| **合计** | **55** | **810** | — |

### 1.3 测试环境要求

- Python 3.14+
- PySide6（UI 测试使用**真实图形平台**；`qapp_instance` 仅在进程尚无 QApplication 时才回退 `-platform offscreen`，CI 在 windows-latest 上跑真实 GUI）
- pytest 9.0+, pytest-mock, pytest-qt, pytest-asyncio（`pip install -e ".[test]"`）
- 临时目录（由 fixtures 自动管理）

---

## 2. 测试策略

### 2.1 测试分层

```
       ┌─────────────────────────────────┐
       │        UI Tests (10)           │  ← qtbot, 模拟用户交互
       │   test/ui_tests/test_*.py      │
       └─────────────────────────────────┘
                       │
       ┌─────────────────────────────────┐
       │    Integration Tests (部分)     │  ← 多组件交互
       │   PluginManager + DataProvider  │
       └─────────────────────────────────┘
                       │
       ┌─────────────────────────────────┐
       │      Unit Tests (主要)          │  ← 单组件隔离测试
       │   test/core/*/test_*.py         │
       └─────────────────────────────────┘
```

### 2.2 测试分类标记

| 类别 | 标记 | 说明 |
|------|------|------|
| 单元测试 | (默认) | 隔离测试单个类/函数，使用 mock |
| UI 测试 | `@pytest.mark.ui` | 需要 PySide6 组件 |
| 集成测试 | `@pytest.mark.integration` | 多组件交互测试 |
| 慢速测试 | `@pytest.mark.slow` | 执行时间 > 5s |
| 风险测试 | `@pytest.mark.risk` | 针对阶段 0 识别的风险点 |

### 2.3 测试原则

1. **隔离性**: 每个测试独立运行，通过 `reset_singletons` fixture 保证
2. **可重复性**: 使用 `tmp_path` 创建临时目录，不依赖外部资源
3. **可观测性**: 测试名称清晰描述测试场景，失败时容易定位
4. **Mock 策略**: 外部依赖（文件 I/O、网络、日志）统一 mock

---

## 3. 测试规范

### 3.1 文件结构规范

```
test/
├── conftest.py              # 全局 fixtures (必须)
├── conftest_utils.py        # 测试工具函数 (必须)
├── core/
│   └── <module>/
│       ├── conftest.py     # 模块级 fixtures (可选)
│       └── test_<被测类>.py # 按被测类名命名
└── ui_tests/
    └── test_<被测组件>.py   # UI 测试
```

### 3.2 命名规范

| 元素 | 规范 | 示例 |
|------|------|------|
| 测试文件 | `test_<被测模块名>.py` | `test_data_provider.py` |
| 测试类 | `Test<被测类名>` | `TestDataProvider` |
| 测试函数 | `test_<场景描述>` | `test_singleton_returns_same_instance` |
| Fixture | `<描述性名称>` | `temp_data_dir`, `qtbot` |
| 测试文档 | `<模块>-testing.md` | `data-testing.md` |

### 3.3 注释规范

- 测试文件头部: 中文描述测试目标和范围
- 测试类头部: 中文描述被测类和测试分组
- 测试函数: 中文 docstring 说明测试目的
- 复杂测试逻辑: 行内注释解释关键步骤

### 3.4 Mock 规范

- 使用 `mocker.patch` / `mocker.patch.object` 进行 mock
- 避免直接 `unittest.mock.patch`（使用 pytest-mock 的 mocker fixture）
- Mock 日志: 由全局 `mock_logger` fixture 处理
- Mock 单例: 由 `reset_singletons` fixture 处理

### 3.5 断言规范

- 使用具体的断言消息，便于定位问题
- 优先使用 `assert actual == expected` 而非 `assert actual`
- 异常测试使用 `pytest.raises()`

---

## 4. Fixtures 参考

### 4.1 全局 Fixtures（test/conftest.py）

| Fixture | 作用域 | 说明 |
|---------|--------|------|
| `reset_singletons` | autouse | 每个测试前后重置所有单例 |
| `mock_logger` | autouse | 禁用日志输出 |
| `qapp_instance` | session | QApplication 实例；进程内无实例时才以 `-platform offscreen` 创建，通常由 pytest-qt 先建好真实平台实例 |
| `qtbot` | function | Qt 测试工具 |
| `temp_data_dir` | function | 临时数据目录 |
| `temp_config_dir` | function | 临时配置目录 |
| `temp_plugin_dir` | function | 临时插件目录 |
| `app_instance` | function | 组合 fixture（QApplication + 单例重置） |

### 4.2 工具函数（test/conftest_utils.py）

| 函数 | 说明 |
|------|------|
| `create_minimal_plugin(plugin_dir, plugin_name, has_service, service_methods, has_information)` | 创建最小有效测试插件 |
| `write_config_json(path, data)` | 原子写入 JSON 配置文件 |

### 4.3 MCP Fixtures（test/core/mcp/conftest.py）

| Fixture | 说明 |
|---------|------|
| `reset_mcp_manager` | 重置 MCPManager 单例 |
| `mock_tool_registry` | Mock ToolRegistry |
| `mock_mcp_sdk` | Mock MCP SDK 导入 |
| `mock_mcp_host_server` | Mock MCPHostServer |

---

## 5. 运行测试

### 5.1 运行所有测试

```bash
pytest test/ -v
```

### 5.2 运行特定模块

```bash
pytest test/core/llm/ -v
pytest test/core/plugin/test_plugin_manager.py -v
```

### 5.3 跳过慢速测试

```bash
pytest test/ -v -m "not slow"
```

### 5.4 仅运行 UI 测试

```bash
pytest test/ -v -m ui
```

### 5.5 仅运行集成测试

```bash
pytest test/ -v -m integration
```

### 5.6 生成覆盖率报告

```bash
pytest test/ --cov=core --cov=ui --cov-report=html
```

### 5.7 使用 qtbot 运行 Qt 测试

```python
def test_example(qtbot):
    window = MyWindow()
    qtbot.addWidget(window)
    qtbot.click(button)
```

---

## 6. 测试覆盖率

| 模块 | 覆盖率目标 | 已覆盖文件 |
|------|-----------|-----------|
| core.data | 85%+ | data_provider.py |
| core.llm | 80%+ | llm_provider.py, conversation_manager.py 等 |
| core.plugin | 80%+ | manager.py, plugin_identity.py 等 |
| core.task | 80%+ | background_task.py, task_model.py |
| core.mcp | 75%+ | manager.py, client.py, server.py 等 |
| ui | 60%+ | main_window.py, skills_panel.py |

---

## 6.1 风险覆盖清单

阶段 0 代码审视识别的高风险区域，下表按**当前套件实测**核对（状态以代码中实际存在的用例为准，不采信计划态描述）：

| 风险 ID | 描述 | 实际落地用例 | 状态 |
|---------|------|-------------|------|
| R-01 | 插件 API 自动注册硬编码 "Service" | `core/plugin/test_plugin_api_auto_register.py`：`test_auto_register_with_custom_service_class`、`test_auto_register_only_service_methods`、空 / 全私有 Service 共 4 例 | 已覆盖 |
| R-02 | MCP 私有 API 依赖 `_tool_manager._tools` | `core/mcp/test_server.py` 覆盖公开注册表 API（`test_add_tool_records_in_registry_directly`、`test_remove_tool_removes_from_registry`、`test_registered_tools_returns_copy`）；**无「不依赖私有属性」的专用断言**，`conftest.py` 的 mock 反而固化了私有结构 | 部分覆盖 |
| R-03 | shutdown `wait=False` 可能丢失任务 | **源码已修复**：`core/task/background_task.py` 现为 `shutdown(wait=True, cancel_futures=True)`；用例 `test_shutdown_waits_for_tasks_to_prevent_data_loss`（断言该调用）、`test_shutdown_cleans_up_resources` | 已覆盖 |
| R-04 | MCP Client 60 秒超时硬编码 | **未找到对应用例**；源码 `core/mcp/client.py` 的 `DEFAULT_MCP_CLIENT_TIMEOUT` 已可经构造函数注入，但无测试守护 | 未覆盖 |
| R-05 | MCP Client 连接可能泄漏 | `core/mcp/test_client.py`：`test_shutdown_closes_all_connections` —— 该用例**未调用 `shutdown()`**，自行清空 `_connections` 后断言字典为空（自证式弱断言）；异常路径 session 释放无专用用例 | 部分覆盖 |
| R-06 | 定时任务恢复 `_restore_all_scheduled_tasks` 未在 init 调用 | **风险前提已失效**：检索 `core/` 无该方法，实际恢复路径为 `register_scheduled_task_factory()` → `restore_scheduled_tasks()`；用例 `test_scheduled_tasks_restore_after_init`、`test_restore_called_during_init` 锁定当前行为 | 已覆盖（前提已失效） |

> 早期计划中的 `TC-XXX-NN` 编号未落到代码中（测试函数 docstring 与代码注释里都没有该编号；仅 `test/core/task/test_background_task_shutdown.py` 的段落注释保留了 TC-TASK 编号），各模块文档已改为按「测试文件 → 测试类 → 用例函数名」定位，本表同样只引用真实存在的函数名。

**状态说明**：
- **已覆盖**：代码中存在针对该风险的用例
- **部分覆盖**：有相关用例但未覆盖风险场景的全部路径（含仅间接覆盖）
- **未覆盖**：暂无对应用例，属待补测试

> **模块文档状态**：`data-testing.md`、`llm-testing.md`、`mcp-testing.md`、`plugin-testing.md`、`task-testing.md`、`ui-testing.md` 六份文档的用例清单已按代码重建（原为编写期计划，与代码严重不符，例如 `data-testing.md` 的 32 个函数名在代码中一个都不存在）。当前六份文档与代码**唯一名双向零差异、类级归属全部正确**，可用 `temp/check_testing_docs.py` 与 `temp/check_testing_docs_by_class.py` 复核。
> `test/修订说明.md` 是该轮修订（2026-04-06）的**历史记录**，其中同一张表标注的"待实现"反映当时状态，按历史文档保留、不再回改。

## 6.2 隐性断言用例清单

下列用例不含显式 `assert`，其正确性依赖「不抛异常 / 不死锁 / 不挂起」（AST 扫描：`temp/find_assertionless_tests.py`）。当前**保留现状**，在此登记以便后续按需补强；改动这些用例时请勿删除其「不应抛异常」的语义。

| 位置 | 用例 | 隐式判定依据 |
|------|------|-------------|
| `core/data/test_data_provider.py` | `test_callback_can_reenter_dataprovider` | 回调内重入读取不死锁 |
| `core/mcp/test_bridge.py` | `test_sync_plugin_api_server_not_init`、`test_sync_new_plugin_tool_server_not_init`、`test_remove_plugin_tool_server_not_init` | server 未初始化时优雅返回、不抛异常 |
| `core/mcp/test_bridge.py` | `test_remove_plugin_tool_not_in_synced` | 移除未同步的工具不抛异常 |
| `core/mcp/test_client.py` | `test_disconnect_not_found` | 断开不存在的 server 不抛异常 |
| `core/mcp/test_manager.py` | `test_stop_server_when_not_running`、`test_shutdown_when_not_started` | 未启动时停止 / 关闭不抛异常 |
| `core/mcp/test_server.py` | `test_remove_tool_not_found` | 移除不存在的工具不抛异常 |
| `core/plugin/test_plugin_manager.py` | `test_unregister_plugin_idempotent` | 重复卸载幂等、不抛异常 |
| `core/task/test_task_model.py` | `test_uuid_is_auto_generated` | `uuid.UUID(task_id)` 对非法值即抛（隐式校验） |

> 扫描另命中 `core/llm/test_tool_call_executor.py` 的 `test_tool`——它是用例内部定义的**本地工具函数**（非测试用例，pytest 不收集），不属本清单。

---

## 7. 模块测试文档

详细测试用例请参考各模块文档（下表用例数为 `pytest --collect-only` 实测值，模块文档已与代码同步，见 §6.1 说明）：

| 模块 | 测试文档 | 测试用例数 |
|------|----------|-----------|
| DataProvider | [data-testing.md](core/data/data-testing.md) | 36 |
| LLM 模块 | [llm-testing.md](core/llm/llm-testing.md) | 283 |
| MCP 模块 | [mcp-testing.md](core/mcp/mcp-testing.md) | 93 |
| 插件系统 | [plugin-testing.md](core/plugin/plugin-testing.md) | 153 |
| 任务系统 | [task-testing.md](core/task/task-testing.md) | 72 |
| UI 组件 | [ui-testing.md](ui_tests/ui-testing.md) | 86 |
| 蓝图与 UIKit 同步守卫 | —（暂无模块文档，见 `test/uikit/`） | 33 |
| 字体子系统 | —（暂无模块文档，见 `test/core/font/`） | 16 |
| 版本号单一来源 | —（暂无模块文档，见 `test/core/test_version.py`） | 9 |
| 工具与日志 | —（暂无模块文档，见 `test/utils/`） | 29 |

---

## 8. 添加新测试

### 8.1 步骤

1. 确定测试目标类和测试场景
2. 检查是否有现成的 fixture 可用
3. 按命名规范创建/编辑测试文件
4. 确保测试独立、可重复
5. 运行测试验证

### 8.2 模板

```python
"""
<被测模块名> 测试

测试目标: <被测类/函数>
测试范围: <覆盖的功能列表>
"""
import pytest
from unittest.mock import MagicMock


class Test<被测类名>:
    """验证 <被测类> 的 <功能分组>"""

    def test_<场景描述>(self):
        """
        <测试目的>: <具体验证什么>

        前提条件: <需要的设置>
        操作步骤: <执行的步骤>
        预期结果: <期望的行为>
        """
        # Arrange
        ...
        # Act
        ...
        # Assert
        ...
```

---

## 9. 常见问题

### Q: 如何测试单例类?

A: 使用 `reset_singletons` fixture，每个测试自动重置单例状态。

### Q: 如何测试需要 QApplication 的 Qt 代码?

A: 使用 `qapp_instance` + `qtbot` fixtures，Qt 组件会自动清理。

### Q: 如何创建临时插件进行测试?

A: 使用 `create_minimal_plugin()` 工具函数。

```python
from test.conftest_utils import create_minimal_plugin

def test_example(temp_plugin_dir):
    plugin_path = temp_plugin_dir / "TestPlugin"
    create_minimal_plugin(plugin_path, "TestPlugin")
```

### Q: 测试失败如何调试?

A: 使用 `pytest -v --tb=long` 查看详细错误信息；使用 `pytest --pdb` 进入交互式调试。

### Q: 如何添加新的 fixture?

A: 在 `test/conftest.py`（全局）或对应模块的 `conftest.py` 中定义。

---

## 相关文档

- [系统架构概述](../docs/architecture/overview.md)
- [核心模块文档索引](../docs/README.md)
- [插件开发指南](../docs/core/plugin-system/plugin-development.md)
- [DataProvider API 参考](../docs/core/data-provider/api-reference.md)
- [LLM Provider API 参考](../docs/core/llm-provider/api-reference.md)

---
