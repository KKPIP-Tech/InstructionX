# MCP 模块测试文档

> MCP (Model Context Protocol) 模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/mcp/`
**测试文件数**: 7 个（含 conftest.py）
**测试用例总数**: 25+ 个

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试用例数 | 主要覆盖 |
|---------|---------|-----------|---------|
| `test_manager.py` | 4 | 6+ | MCPManager 单例、配置管理 |
| `test_server.py` | 5 | 12+ | MCPHostServer 初始化、工具管理 |
| `test_client.py` | 3+ | 6+ | MCPClient 连接/请求 |
| `test_bridge.py` | 2+ | 4+ | MCPBridge 桥接 |
| `test_config.py` | 2+ | 3+ | MCPConfig 配置 |
| `test_plugin_interface.py` | 2+ | 3+ | MCPPluginInterface |
| `conftest.py` | - | 4 fixtures | MCP 专用 fixtures |

### 1.2 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例模式 | 2 | `get_mcp_manager()` |
| 配置管理 | 4 | `get_config()`, `save_config()`, `_load_config()` |
| Server 生命周期 | 5 | `start()`, `stop()`, `add_tool()`, `remove_tool()` |
| Client 连接 | 3 | `connect()`, `disconnect()`, `send_request()` |
| Bridge 通信 | 2 | `bridge_request()`, `bridge_notification()` |
| 工具注册 | 4 | `register_tool()`, `unregister_tool()` |
| 异常处理 | 2 | 配置文件损坏、连接失败 |
| 工具注册公开 API (R-02) | 2 | FastMCP 私有 API 依赖 |
| Client 并发 (R-05) | 1 | 多 Client 同时连接 |
| Client 超时配置 (R-04) | 1 | 60 秒硬编码超时 |
| Client Session 泄漏 (R-05) | 1 | 异常时 session 正确关闭 |

---

## 2. 测试策略

### 2.1 隔离措施

- `MCPManager` 单例由 `reset_mcp_manager` fixture 重置
- 配置文件操作被 mock（`Path.exists`, `builtins.open`）
- 使用 `tmp_path` 创建临时配置文件
- `MCPHostServer` 使用懒加载（`_fastmcp` 初始为 None）

### 2.2 测试数据

- 配置文件使用临时 JSON 文件
- Server 参数使用默认值（host='127.0.0.1', port=8765）
- 工具注册使用模拟的 plugin_id 和 method_name

### 2.3 关键 Fixtures（test/core/mcp/conftest.py）

```python
# MCP 专用 fixtures
reset_mcp_manager      # 重置 MCPManager 单例
mock_tool_registry     # Mock ToolRegistry
mock_mcp_sdk           # Mock MCP SDK 导入
mock_mcp_host_server   # Mock MCPHostServer
```

---

## 3. 测试用例

### 3.1 MCPManager 单例模式

#### TC-MCP-001: get_mcp_manager 返回相同实例
- **测试类**: TestMCPManagerSingleton
- **测试函数**: `test_get_mcp_manager_returns_same_instance`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 重置模块级单例
  2. 调用 `get_mcp_manager()` 两次
  3. 验证返回同一对象引用
- **预期结果**: `inst1 is inst2`

---

### 3.2 配置管理

#### TC-MCP-002: 配置文件缺失时创建默认配置
- **测试类**: TestMCPManagerConfig
- **测试函数**: `test_load_config_creates_default_if_missing`
- **优先级**: P1
- **前置条件**: 配置文件不存在
- **测试步骤**:
  1. Mock `Path.exists` 返回 False
  2. 创建 MCPManager 实例
  3. 验证默认配置
- **预期结果**: `server.host == "127.0.0.1"`, `server.port == 8765`

#### TC-MCP-003: 从文件加载配置
- **测试类**: TestMCPManagerConfig
- **测试函数**: `test_load_config_from_file`
- **优先级**: P1
- **前置条件**: 存在有效的配置文件
- **测试步骤**:
  1. 创建临时配置文件（host="0.0.0.0", port=9000）
  2. Mock `Path.exists` 返回 True
  3. 创建 MCPManager 并调用 `_load_config()`
- **预期结果**: 配置已加载，host 和 port 正确

#### TC-MCP-004: 损坏的配置文件优雅降级
- **测试类**: TestMCPManagerConfig
- **测试函数**: `test_load_config_handles_corrupt_file`
- **优先级**: P1
- **前置条件**: 配置文件包含无效 JSON
- **测试步骤**:
  1. 创建包含 "invalid json content" 的配置文件
  2. Mock `Path.exists` 返回 True
  3. 创建 MCPManager 并调用 `_load_config()`
- **预期结果**: 优雅降级，使用默认配置

---

### 3.3 MCPHostServer 初始化

#### TC-MCP-005: 默认参数初始化
- **测试类**: TestMCPHostServer
- **测试函数**: `test_init_default_values`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `MCPHostServer()` 实例
  2. 验证各属性值
- **预期结果**:
  - `_name == "InstructionX"`
  - `_host == "127.0.0.1"`
  - `_port == 8765`

#### TC-MCP-006: 自定义参数初始化
- **测试类**: TestMCPHostServer
- **测试函数**: `test_init_stores_parameters`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `MCPHostServer(name="TestServer", host="0.0.0.0", port=9000)`
  2. 验证各属性值
- **预期结果**: 参数正确存储

#### TC-MCP-007: 初始状态 _running 为 False
- **测试类**: TestMCPHostServer
- **测试函数**: `test_init_running_false`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `MCPHostServer()` 实例
  2. 验证 `_running` 状态
- **预期结果**: `_running is False`

#### TC-MCP-008: 工具注册表初始为空
- **测试类**: TestMCPHostServer
- **测试函数**: `test_init_tool_registry_empty`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `MCPHostServer()` 实例
  2. 验证 `_tool_registry`
- **预期结果**: `_tool_registry` 为空字典

#### TC-MCP-009: FastMCP 懒加载初始化
- **测试类**: TestMCPHostServer
- **测试函数**: `test_init_fastmcp_none`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `MCPHostServer()` 实例
  2. 验证 `_fastmcp`
- **预期结果**: `_fastmcp is None`

---

### 3.4 Server 工具管理

#### TC-MCP-010: 添加工具到注册表
- **测试类**: TestMCPHostServerToolManagement
- **测试函数**: `test_add_tool_records_in_registry_directly`
- **优先级**: P1
- **前置条件**: Server 实例已创建
- **测试步骤**:
  1. 创建 `MCPHostServer()` 实例
  2. 手动添加工具到 `_tool_registry`
  3. 验证工具已注册
- **预期结果**: `"test-tool" in server._tool_registry`

#### TC-MCP-011: 从注册表移除工具
- **测试类**: TestMCPHostServerToolManagement
- **测试函数**: `test_remove_tool_removes_from_registry`
- **优先级**: P1
- **前置条件**: 工具已注册
- **测试步骤**:
  1. 创建 Server 并添加工具
  2. 移除工具
  3. 验证工具已移除
- **预期结果**: 工具不在注册表中

---

### 3.5 MCPClient 连接

#### TC-MCP-012: Client 连接到 Server
- **测试类**: TestMCPClientConnect
- **测试函数**: `test_client_connects_to_server`
- **优先级**: P1
- **前置条件**: Server 已启动
- **测试步骤**:
  1. 创建 Server 和 Client
  2. Client 调用 `connect()`
- **预期结果**: 连接成功

#### TC-MCP-013: Client 断开连接
- **测试类**: TestMCPClientDisconnect
- **测试函数**: `test_client_disconnects`
- **优先级**: P1
- **前置条件**: Client 已连接
- **测试步骤**:
  1. Client 调用 `disconnect()`
- **预期结果**: 断开成功

#### TC-MCP-014: Client 发送请求
- **测试类**: TestMCPClientRequest
- **测试函数**: `test_client_sends_request`
- **优先级**: P1
- **前置条件**: Client 已连接
- **测试步骤**:
  1. Client 调用 `send_request(method, params)`
- **预期结果**: 请求发送成功

---

### 3.6 Bridge 通信

#### TC-MCP-015: Bridge 桥接请求
- **测试类**: TestMCPBridgeRequest
- **测试函数**: `test_bridge_request_routes_correctly`
- **优先级**: P1
- **前置条件**: Bridge 已配置
- **测试步骤**:
  1. Bridge 调用 `bridge_request(request)`
- **预期结果**: 请求正确路由

#### TC-MCP-016: Bridge 发送通知
- **测试类**: TestMCPBridgeNotification
- **测试函数**: `test_bridge_notification_sends`
- **优先级**: P1
- **前置条件**: Bridge 已配置
- **测试步骤**:
  1. Bridge 调用 `bridge_notification(notification)`
- **预期结果**: 通知发送成功

---

### 3.7 异常处理

#### TC-MCP-017: 连接失败处理
- **测试类**: TestMCPClientError
- **测试函数**: `test_client_connection_failure`
- **优先级**: P1
- **前置条件**: Server 未启动
- **测试步骤**:
  1. Client 尝试连接未启动的 Server
- **预期结果**: 抛出连接异常或优雅处理

#### TC-MCP-018: 无效配置处理
- **测试类**: TestMCPManagerConfig
- **测试函数**: `test_invalid_config_handling`
- **优先级**: P1
- **前置条件**: 配置文件格式错误
- **测试步骤**:
  1. 使用无效配置创建 MCPManager
- **预期结果**: 使用默认配置或抛出有意义的异常

---

### 3.8 工具注册公开 API (R-02 风险覆盖)

#### TC-MCP-019: 工具注册使用公开 API 而非私有属性
- **测试类**: TestMCPHostServerToolRegistration
- **测试函数**: `test_tool_registration_via_public_api`
- **优先级**: P1
- **前置条件**: MCPHostServer 已初始化
- **测试步骤**:
  1. 创建 MCPHostServer 实例
  2. 调用公开的 `add_tool()` 方法
  3. 验证工具已注册
- **预期结果**: 工具通过公开 API 注册成功
- **风险关联**: R-02

#### TC-MCP-020: FastMCP 初始化延迟加载
- **测试类**: TestMCPHostServerFastMCPInit
- **测试函数**: `test_fastmcp_initialization_delayed`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 MCPHostServer 实例
  2. 验证 `_fastmcp` 为 None
  3. 调用需要 FastMCP 的操作
  4. 验证 FastMCP 被正确初始化
- **预期结果**: FastMCP 懒加载初始化
- **风险关联**: R-02

---

### 3.9 Client 并发连接 (R-05 风险覆盖)

#### TC-MCP-021: 多 Client 同时连接
- **测试类**: TestMCPClientConcurrency
- **测试函数**: `test_multiple_clients_connect_simultaneously`
- **优先级**: P1
- **前置条件**: Server 已启动
- **测试步骤**:
  1. 启动 MCPHostServer
  2. 创建 3 个 MCPClientManager
  3. 同时调用 `connect()`
- **预期结果**: 所有 Client 成功连接
- **风险关联**: R-05

---

### 3.10 Client 超时配置 (R-04 风险覆盖)

#### TC-MCP-022: Client 超时时间可配置
- **测试类**: TestMCPClientTimeout
- **测试函数**: `test_client_timeout_configurable`
- **优先级**: P1
- **前置条件**: Client 未连接
- **测试步骤**:
  1. 创建 MCPClientManager 并配置超时值
  2. 调用 `connect()` 并等待响应
  3. 验证超时行为
- **预期结果**: 超时时间可配置，非硬编码
- **风险关联**: R-04

---

### 3.11 Client Session 泄漏 (R-05 风险覆盖)

#### TC-MCP-023: Client 异常时 session 正确关闭
- **测试类**: TestMCPClientSessionLeak
- **测试函数**: `test_client_session_closed_on_exception`
- **优先级**: P1
- **前置条件**: Client 已连接
- **测试步骤**:
  1. Client 已连接
  2. 调用 `send_request()` 时抛出异常
  3. 验证 session 已关闭
- **预期结果**: 异常发生时 session 被正确关闭
- **风险关联**: R-05

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/mcp/` 添加新功能时：
1. 在对应的测试文件中找到测试类
2. 添加新测试函数，遵循命名规范
3. 使用 TC-MCP-XXX 格式的 docstring
4. 确保使用正确的 fixtures

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查 fixtures 是否正确

### 4.3 覆盖率目标

- 当前覆盖率: ~75%
- 目标覆盖率: 80%
- 未覆盖的关键路径:
  - 真实的网络通信
  - FastMCP 懒加载初始化
  - 多 Client 并发连接

---

## 5. 相关文档

- [MCP 协议概述](../../docs/core/mcp/overview.md)
- [MCP 配置文档](../../docs/core/mcp/config.md)
- [测试主文档](../TESTING.md)

---
