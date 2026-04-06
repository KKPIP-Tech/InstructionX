# LLM 模块测试文档

> LLM 模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/llm/`
**测试文件数**: 7 个
**测试用例总数**: 30+ 个

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试用例数 | 主要覆盖 |
|---------|---------|-----------|---------|
| `test_llm_provider.py` | 6 | 10+ | LLMProvider 单例、provider 管理、chat/stream_chat/embed 路由 |
| `test_conversation_manager.py` | 5 | 10+ | 对话创建、消息管理、历史记录 |
| `test_tool_call_executor.py` | 3 | 8+ | ToolRegistry、ToolCallExecutor |
| `test_llm_config.py` | 3+ | 5+ | LLMConfig 配置管理 |
| `test_plugin_service.py` | 2+ | 5+ | LLMPluginService 插件服务 |
| `test_llm_exceptions.py` | 2+ | 3+ | LLM 异常类 |
| `test_llm_types.py` | 2+ | 3+ | LLM 类型定义 |

### 1.2 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例模式 | 3 | `LLMProvider()` 双重检查锁定 |
| Provider 管理 | 4 | `get_provider()`, `register_provider()`, `_create_provider()` |
| Chat 路由 | 3 | `chat()`, 默认 provider 选择 |
| Stream Chat 路由 | 2 | `stream_chat()` 路由 |
| Embed 路由 | 2 | `embed()` 路由 |
| 对话管理 | 10+ | `create_conversation()`, `add_message()`, `get_conversation()` |
| 工具注册 | 6+ | `register()`, `unregister()`, `get_tools()` |
| 工具调用执行 | 4+ | `execute_tool_call()`, `execute_tool_calls()` |
| 配置管理 | 5+ | `LLMConfig` 各方法 |
| 异常处理 | 3+ | `LLMError`, `ConfigurationError` |
| 类型定义 | 3+ | `Message`, `ChatResponse`, `ToolResult` |

---

## 2. 测试策略

### 2.1 隔离措施

- `LLMConfig` 被 mock 以避免文件系统访问
- 使用 `_make_provider()` 辅助函数创建隔离的 LLMProvider 实例
- `ConversationManager` 使用 mock LLM 返回可预测的 `ChatResponse`
- 单例由 `reset_singletons` fixture 自动重置

### 2.2 测试数据

- Mock LLM 返回可配置的 `content` 和 `usage`
- 工具测试使用简单的 handler 函数（如 `lambda x: x * 2`）
- 对话测试使用 UUID 格式验证

### 2.3 关键测试辅助函数

```python
# test_llm_provider.py
def _make_provider(mocker):
    """返回隔离的 LLMProvider 实例，LLMConfig 被 mock"""
    mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
    mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
    mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)
    return lp_module.LLMProvider()

# test_conversation_manager.py
def _make_mock_llm(content="hello", usage=None, tool_calls=None):
    """返回可预测的 mock LLM"""
    mock.chat.return_value = ChatResponse(content=content, ...)
    return mock
```

---

## 3. 测试用例

### 3.1 LLMProvider 单例模式

#### TC-LLM-001: 单例返回相同实例
- **测试类**: TestSingleton
- **测试函数**: `test_singleton_returns_same_instance`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 重置单例状态
  2. 调用 `LLMProvider()` 两次
  3. 验证返回同一对象引用
- **预期结果**: `inst1 is inst2`

#### TC-LLM-002: 多次调用只执行一次初始化
- **测试类**: TestSingleton
- **测试函数**: `test_singleton_idempotent_init`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 多次调用 `LLMProvider()`
  2. 验证 `LLMConfig.__init__` 只被调用一次
- **预期结果**: `init_mock.call_count == 1`

#### TC-LLM-003: 双重检查锁定多线程安全
- **测试类**: TestSingleton
- **测试函数**: `test_singleton_double_checked_locking`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 启动两个线程同时调用 `LLMProvider()`
  2. 验证两个线程返回同一实例
- **预期结果**: `results[0] is results[1]`

---

### 3.2 Provider 创建

#### TC-LLM-004: 未知 provider_type 抛出 ConfigurationError
- **测试类**: TestCreateProvider
- **测试函数**: `test_create_provider_raises_unknown_type`
- **优先级**: P1
- **前置条件**: Provider 已清空
- **测试步骤**:
  1. Mock `get_provider_class` 返回 None
  2. 调用 `_create_provider("bad", {"provider_type": "nonexistent"})`
- **预期结果**: 抛出 `ConfigurationError`，匹配 "Unknown provider type"

#### TC-LLM-005: 成功创建 provider
- **测试类**: TestCreateProvider
- **测试函数**: `test_create_provider_success`
- **优先级**: P1
- **前置条件**: Provider 已清空
- **测试步骤**:
  1. Mock `get_provider_class` 返回 mock_provider
  2. 调用 `_create_provider("test", {"provider_type": "mock"})`
  3. 验证 provider 被存储
- **预期结果**: `"test" in inst._providers`

---

### 3.3 Chat 路由

#### TC-LLM-006: chat 默认选择第一个 enabled provider
- **测试类**: TestChat
- **测试函数**: `test_chat_default_selects_first_enabled`
- **优先级**: P0
- **前置条件**: 已注册 enabled provider
- **测试步骤**:
  1. 创建 mock provider 并设置 `chat` 返回值
  2. 调用 `chat([Message("user", "hello")])`
- **预期结果**: 调用 mock provider 的 chat 方法

#### TC-LLM-007: chat 调用指定 provider
- **测试类**: TestChat
- **测试函数**: `test_chat_with_specific_provider`
- **优先级**: P0
- **前置条件**: 已注册多个 provider
- **测试步骤**:
  1. 注册 "provider-a" 和 "provider-b"
  2. 调用 `chat(..., provider="provider-b")`
- **预期结果**: 调用 "provider-b" 的 chat 方法

---

### 3.4 Stream Chat 路由

#### TC-LLM-008: stream_chat 路由到正确 provider
- **测试类**: TestStreamChat
- **测试函数**: `test_stream_chat_routes_correctly`
- **优先级**: P1
- **前置条件**: 已注册 provider
- **测试步骤**:
  1. 创建 mock provider
  2. 调用 `stream_chat([Message("user", "hello")])`
- **预期结果**: 调用 mock provider 的 stream_chat 方法

#### TC-LLM-009: stream_chat callback 被正确调用
- **测试类**: TestStreamChat
- **测试函数**: `test_stream_chat_callback_invoked`
- **优先级**: P1
- **前置条件**: 已注册 provider
- **测试步骤**:
  1. 定义 callback 函数
  2. 调用 `stream_chat(messages, callback=callback)`
- **预期结果**: callback 被多次调用，收到增量内容

---

### 3.5 对话管理

#### TC-LLM-010: 创建对话返回 UUID
- **测试类**: TestCreateConversation
- **测试函数**: `test_creates_conversation_and_returns_uuid`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `create_conversation()`
  2. 验证返回值格式为 UUID（36 字符）
  3. 验证对话 ID 存在于 `_conversations`
- **预期结果**: UUID 格式正确，对话已存储

#### TC-LLM-011: 创建带 system prompt 的对话
- **测试类**: TestCreateConversation
- **测试函数**: `test_create_conversation_with_system_prompt`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `create_conversation(system_prompt="You are helpful.")`
  2. 验证对话的 system_prompt 已设置
- **预期结果**: `conv.system_prompt == "You are helpful."`

#### TC-LLM-012: 获取存在的对话
- **测试类**: TestGetConversation
- **测试函数**: `test_returns_conversation_when_exists`
- **优先级**: P0
- **前置条件**: 已创建对话
- **测试步骤**:
  1. 调用 `create_conversation()` 获取 ID
  2. 调用 `get_conversation(conv_id)`
- **预期结果**: 返回 Conversation 对象，ID 匹配

#### TC-LLM-013: 获取不存在的对话返回 None
- **测试类**: TestGetConversation
- **测试函数**: `test_returns_none_for_missing_id`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `get_conversation("nonexistent-id")`
- **预期结果**: 返回 None

#### TC-LLM-014: 列出所有对话
- **测试类**: TestListConversations
- **测试函数**: `test_returns_list_of_all_conversations`
- **优先级**: P1
- **前置条件**: 已创建多个对话
- **测试步骤**:
  1. 创建 3 个对话
  2. 调用 `list_conversations()`
- **预期结果**: 返回包含 3 个对话的列表

---

### 3.6 工具注册

#### TC-LLM-015: 注册工具存储到 registry
- **测试类**: TestToolRegistry
- **测试函数**: `test_register_stores_tool`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 ToolRegistry
  2. 注册一个工具 handler
  3. 调用 `get_tools()` 和 `get_handler()`
- **预期结果**: 工具已存储，handler 可获取

#### TC-LLM-016: 重复注册抛出 ValueError
- **测试类**: TestToolRegistry
- **测试函数**: `test_register_raises_on_duplicate_name`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 注册名为 "foo" 的工具
  2. 再次注册同名 "foo" 的工具
- **预期结果**: 抛出 `ValueError`，匹配 "Tool already registered: foo"

#### TC-LLM-017: 注销工具从两个字典中移除
- **测试类**: TestToolRegistry
- **测试函数**: `test_unregister_removes_from_both_dicts`
- **优先级**: P1
- **前置条件**: 已注册工具
- **测试步骤**:
  1. 注册工具 "my_tool"
  2. 调用 `unregister("my_tool")`
  3. 验证 handler 为 None，工具不在列表中
- **预期结果**: `result is True`，工具已移除

#### TC-LLM-018: 注销不存在的工具返回 False
- **测试类**: TestToolRegistry
- **测试函数**: `test_unregister_returns_false_for_missing_name`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `unregister("nonexistent")`
- **预期结果**: 返回 False

---

### 3.7 工具调用执行

#### TC-LLM-019: 执行单个工具调用
- **测试类**: TestToolCallExecutor
- **测试函数**: `test_execute_single_tool_call`
- **优先级**: P0
- **前置条件**: 已注册工具
- **测试步骤**:
  1. 注册 handler 返回 "result"
  2. 创建 ToolCall 对象
  3. 调用 `execute_tool_call()`
- **预期结果**: 返回 ToolResult，结果为 "result"

#### TC-LLM-020: 执行多个工具调用
- **测试类**: TestToolCallExecutor
- **测试函数**: `test_execute_multiple_tool_calls`
- **优先级**: P1
- **前置条件**: 已注册多个工具
- **测试步骤**:
  1. 注册多个工具
  2. 调用 `execute_tool_calls([tool_call_1, tool_call_2])`
- **预期结果**: 返回包含多个结果的列表

#### TC-LLM-021: 调用不存在的工具抛出异常
- **测试类**: TestToolCallExecutor
- **测试函数**: `test_execute_unknown_tool_raises`
- **优先级**: P1
- **前置条件**: 未注册工具
- **测试步骤**:
  1. 创建指向未知工具的 ToolCall
  2. 调用 `execute_tool_call()`
- **预期结果**: 抛出异常

---

### 3.8 配置管理

#### TC-LLM-022: LLMConfig 加载所有 providers
- **测试类**: TestLLMConfig
- **测试函数**: `test_loads_all_providers`
- **优先级**: P1
- **前置条件**: 配置文件存在
- **测试步骤**:
  1. 创建 LLMConfig 实例
  2. 调用 `get_all_providers()`
- **预期结果**: 返回 provider 字典

#### TC-LLM-023: 更新配置后重新加载
- **测试类**: TestLLMConfig
- **测试函数**: `test_update_config_reloads`
- **优先级**: P1
- **前置条件**: 已加载配置
- **测试步骤**:
  1. 调用 `update_config(new_config)`
  2. 验证配置已更新
- **预期结果**: 新配置生效

---

### 3.9 异常处理

#### TC-LLM-024: LLMError 正确抛出
- **测试类**: TestLLMExceptions
- **测试函数**: `test_llm_error_raises`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 触发 LLMError 条件
- **预期结果**: 抛出 LLMError

#### TC-LLM-025: ConfigurationError 正确抛出
- **测试类**: TestLLMExceptions
- **测试函数**: `test_configuration_error_raises`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 触发 ConfigurationError 条件（如未知 provider type）
- **预期结果**: 抛出 ConfigurationError

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/llm/` 添加新功能时：
1. 在对应的测试文件中找到测试类
2. 添加新测试函数，遵循命名规范
3. 使用 TC-LLM-XXX 格式的 docstring
4. 使用 `_make_provider()` 或 `_make_mock_llm()` 辅助函数

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查辅助函数是否正确

### 4.3 覆盖率目标

- 当前覆盖率: ~80%
- 目标覆盖率: 85%
- 未覆盖的关键路径:
  - 真实 API 调用（需要网络）
  - 复杂错误恢复场景

---

## 5. 相关文档

- [LLM Provider API 参考](../../docs/core/llm-provider/api-reference.md)
- [LLM Provider 概述](../../docs/core/llm-provider/overview.md)
- [测试主文档](../TESTING.md)

---
