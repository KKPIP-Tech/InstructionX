# MCP 模块测试文档

## 概述

本目录包含 `core/mcp/` 模块的完整测试套件。

## 测试结构

```
test/core/mcp/
├── README.md              # 本文档
├── __init__.py
├── conftest.py            # MCP 专用 fixtures
├── test_config.py         # MCPServerConfig, MCPRemoteServerConfig, MCPConfig
├── test_plugin_interface.py  # IMCPTool, IMCPClient 抽象接口
├── test_manager.py        # MCPManager 测试
├── test_client.py         # MCPClientManager, MCPServerConnection
├── test_bridge.py         # MCPBridge 测试
└── test_server.py        # MCPHostServer 测试
```

## 运行测试

```bash
# 运行所有 MCP 测试
pytest test/core/mcp/ -v

# 运行特定测试文件
pytest test/core/mcp/test_manager.py -v

# 运行特定测试类
pytest test/core/mcp/test_manager.py::TestMCPManagerSingleton -v

# 运行特定测试方法
pytest test/core/mcp/test_manager.py::TestMCPManagerSingleton::test_get_mcp_manager_returns_same_instance -v

# 生成覆盖率报告
pytest test/core/mcp/ --cov=core.mcp --cov-report=html
```

## Fixtures

| Fixture | 类型 | 说明 |
|---------|------|------|
| `reset_mcp_manager` | autouse | 每个测试前后重置 MCPManager 单例 |
| `mock_tool_registry` | function | Mock ToolRegistry |
| `mock_mcp_sdk` | function | Mock MCP SDK 组件 (FastMCP, ClientSession 等) |
| `mock_mcp_host_server` | function | Mock MCPHostServer 避免真实服务器启动 |
| `mcp_manager` | function | 创建 MCPManager 实例 |
| `client_manager` | function | 创建 MCPClientManager 实例 |

## Mock 策略

由于 MCP 模块依赖外部 MCP SDK 和内部单例，测试使用以下 mock 策略：

1. **MCP SDK Mock**: 所有 `mcp.*` 导入被 mock，避免需要真实 MCP 环境
2. **单例重置**: 每个测试通过 `reset_mcp_manager` fixture 重置模块级单例
3. **PluginManager Mock**: 使用 `PluginManager()` 模式替代 `get_plugin_manager()`

## 测试覆盖

| 文件 | 测试类 | 覆盖率 |
|------|--------|--------|
| `test_config.py` | `TestMCPServerConfig`, `TestMCPRemoteServerConfig`, `TestMCPConfig` | 配置类 to_dict/from_dict 往返、默认值、字段验证 |
| `test_plugin_interface.py` | `TestIMCPTool`, `TestIMCPClient` | 抽象方法必须重写、具体实现可实例化 |
| `test_manager.py` | `TestMCPManagerSingleton`, `TestMCPManagerConfig`, `TestMCPManagerServerLifecycle`, `TestMCPManagerClientLifecycle`, `TestMCPManagerBridge`, `TestMCPManagerShutdown` | 单例、配置管理、Server/Client 生命周期、桥接器、关闭 |
| `test_client.py` | `TestMCPServerConnection`, `TestMCPClientManager` | 连接字段、事件循环管理、工具注册/注销 |
| `test_bridge.py` | `TestMCPBridge`, `TestMCPBridgeSyncPluginAPI`, `TestMCPBridgeSyncNewTool`, `TestMCPBridgeRemoveTool` | 初始化、插件 API 同步、工具同步/移除 |
| `test_server.py` | `TestMCPHostServer`, `TestMCPHostServerToolManagement`, `TestMCPHostServerLifecycle`, `TestMCPHostServerDeferredRegistration` | 初始化、工具管理、生命周期、延迟注册 |

## 关键测试场景

| 组件 | 场景 | 预期 |
|-----|------|-----|
| `MCPManager` | config 文件不存在 | 创建默认配置 |
| `MCPManager` | config 文件 JSON 损坏 | 回退到默认配置 |
| `MCPManager` | `start_server(transport="invalid")` | 抛出 ValueError |
| `MCPManager` | 首次调用 `get_client_manager()` 不传 tool_registry | 抛出 ValueError |
| `MCPBridge` | server 未初始化时同步 | 优雅忽略，记录 warning |
| `MCPBridge` | 工具名格式无效 (无 ".") | 跳过该工具 |
| `MCPClientManager` | 连接失败超时 | 60秒后抛出异常 |
| `MCPHostServer` | 重复启动 | 警告日志，不执行 |

## 已知问题

- `bridge.py` 和 `server.py` 中的 `get_plugin_manager()` 调用已被修复为 `PluginManager()` 模式
- 测试使用 mock 避免依赖真实的 MCP SDK 环境
