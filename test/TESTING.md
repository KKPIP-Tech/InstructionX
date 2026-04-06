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

| 模块 | 测试文件数 | 测试用例数 | 覆盖范围 |
|------|-----------|-----------|---------|
| core.data | 1 | 30+ | DataProvider 全部公开 API |
| core.llm | 7 | 30+ | LLMProvider, ConversationManager, Config, Types, Exceptions, ToolCallExecutor, PluginService |
| core.mcp | 7 | 25+ | Manager, Client, Server, Bridge, Config, PluginInterface |
| core.plugin | 4 | 34+ | Manager, Identity, ConfigManager, Version |
| core.task | 2 | 27+ | BackgroundTaskManager, TaskModel |
| ui_tests | 3 | 15+ | MainWindow, SkillsPanel, LLMSettingsDialog |
| **合计** | **24** | **161+** | — |

### 1.3 测试环境要求

- Python 3.14+
- PySide6（offscreen 模式用于 CI）
- pytest 8.0+, pytest-mock, pytest-qt, pytest-asyncio
- 临时目录（由 fixtures 自动管理）

---

## 2. 测试策略

### 2.1 测试分层

```
       ┌─────────────────────────────────┐
       │         UI Tests (3)           │  ← qtbot, 模拟用户交互
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
| `qapp_instance` | session | QApplication 实例 (offscreen) |
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

阶段 0 代码审视识别的高风险区域对应的测试覆盖状态：

| 风险 ID | 描述 | 测试用例 | 状态 |
|---------|------|---------|------|
| R-01 | 插件 API 自动注册硬编码 "Service" | TC-PLUGIN-025~028 | 待实现 |
| R-02 | MCP 私有 API 依赖 `_tool_manager._tools` | TC-MCP-019, TC-MCP-020 | 待实现 |
| R-03 | shutdown `wait=False` 可能丢失任务 | TC-TASK-021, TC-TASK-022 | 待实现 |
| R-04 | MCP Client 60 秒超时硬编码 | TC-MCP-022 | 待实现 |
| R-05 | MCP Client 连接可能泄漏 | TC-MCP-021, TC-MCP-023 | 待实现 |
| R-06 | 定时任务恢复 `_restore_all_scheduled_tasks` 未在 init 调用 | TC-TASK-023, TC-TASK-024 | 待实现 |

**状态说明**：
- **待实现**：需在阶段 2 新增测试代码
- **部分覆盖**：有测试但未完全覆盖风险场景
- **已覆盖**：测试已完整覆盖风险场景

---

## 7. 模块测试文档

详细测试用例请参考各模块文档：

| 模块 | 测试文档 | 测试用例数 |
|------|----------|-----------|
| DataProvider | [data-testing.md](core/data/data-testing.md) | 30+ |
| LLM 模块 | [llm-testing.md](core/llm/llm-testing.md) | 30+ |
| MCP 模块 | [mcp-testing.md](core/mcp/mcp-testing.md) | 25+ |
| 插件系统 | [plugin-testing.md](core/plugin/plugin-testing.md) | 34+ |
| 任务系统 | [task-testing.md](core/task/task-testing.md) | 27+ |
| UI 组件 | [ui-testing.md](../ui_tests/ui-testing.md) | 15+ |

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
