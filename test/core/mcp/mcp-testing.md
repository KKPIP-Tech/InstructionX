# MCP 模块测试文档

> MCP (Model Context Protocol) 模块的测试策略、测试用例和维护指南
>
> 本文件的用例清单为**代码实测值**（不使用编写计划态描述）：文件名 / 测试类 / 用例函数名由 `pytest --collect-only` 采集，「说明」列由各测试函数 docstring 首句翻译/归纳为中文（术语保留原文，详见 §3 前言）。引用覆盖状态前请以代码为准。

---

## 1. 测试概述

**被测模块**: `core/mcp/`
**测试文件数**: 6 个（`test_*.py`），另有 `conftest.py` 提供模块级 fixtures
**测试类总数**: 21 个
**测试用例总数**: 93 个（无 `parametrize`；93 个 `def test_*` = 93 个用例，去重后为 84 个函数名）

实测命令（工作目录 = 项目根）：

```powershell
.venv\Scripts\python.exe -m pytest test/core/mcp --collect-only -q -p no:cacheprovider
```

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试用例数 | 主要覆盖 |
|---------|---------|-----------|---------|
| `test_manager.py` | 6 | 27 | MCPManager 单例、配置管理、Server/Client 生命周期、Bridge 协调、shutdown |
| `test_server.py` | 4 | 15 | MCPHostServer 初始化、工具注册表管理、生命周期、延迟注册 |
| `test_client.py` | 2 | 13 | MCPClientManager、MCPServerConnection |
| `test_bridge.py` | 4 | 16 | MCPBridge 初始化、插件 API 全量同步、单工具同步/移除 |
| `test_config.py` | 3 | 18 | MCPServerConfig、MCPRemoteServerConfig、MCPConfig |
| `test_plugin_interface.py` | 2 | 4 | IMCPTool、IMCPClient 抽象接口 |
| **合计** | **21** | **93** | — |
| `conftest.py` | - | 4 fixtures | MCP 专用 fixtures（不参与用例计数） |

### 1.2 覆盖范围

按测试类实测分布（用例数与 §3 清单逐行对应）：

| 测试文件 | 测试类 | 用例数 | 覆盖主题 |
|---------|--------|-------|---------|
| `test_manager.py` | `TestMCPManagerSingleton` | 1 | 单例行为 |
| `test_manager.py` | `TestMCPManagerConfig` | 8 | 配置加载/保存、远端 Server 增删 |
| `test_manager.py` | `TestMCPManagerServerLifecycle` | 7 | Server 创建与启停、transport 校验、Server 状态与配置查询 |
| `test_manager.py` | `TestMCPManagerClientLifecycle` | 4 | Client Manager 获取与查询 |
| `test_manager.py` | `TestMCPManagerBridge` | 4 | Bridge 获取与同步/移除委派 |
| `test_manager.py` | `TestMCPManagerShutdown` | 3 | 关闭流程 |
| `test_server.py` | `TestMCPHostServer` | 5 | 初始化默认值 / 参数存储 / 初始状态 |
| `test_server.py` | `TestMCPHostServerToolManagement` | 4 | 工具注册表增删与只读副本 |
| `test_server.py` | `TestMCPHostServerLifecycle` | 4 | 重复启动 no-op、停止、运行状态 |
| `test_server.py` | `TestMCPHostServerDeferredRegistration` | 2 | 延迟注册信息存储与清除 |
| `test_client.py` | `TestMCPServerConnection` | 2 | 连接记录字段 |
| `test_client.py` | `TestMCPClientManager` | 11 | 事件循环管理、连接查询、断开、shutdown、handler 构建 |
| `test_bridge.py` | `TestMCPBridge` | 2 | 初始化 |
| `test_bridge.py` | `TestMCPBridgeSyncPluginAPI` | 6 | 插件 API 全量同步与计数 |
| `test_bridge.py` | `TestMCPBridgeSyncNewTool` | 4 | 单工具同步 |
| `test_bridge.py` | `TestMCPBridgeRemoveTool` | 4 | 单工具移除 |
| `test_config.py` | `TestMCPServerConfig` | 5 | 本机 Server 配置序列化 |
| `test_config.py` | `TestMCPRemoteServerConfig` | 7 | 远端 Server 配置序列化（stdio / HTTP） |
| `test_config.py` | `TestMCPConfig` | 6 | 顶层配置嵌套序列化 |
| `test_plugin_interface.py` | `TestIMCPTool` | 2 | 抽象方法约束与具体实现 |
| `test_plugin_interface.py` | `TestIMCPClient` | 2 | 抽象方法约束与具体实现 |

> **风险覆盖结论**（R-02 部分覆盖 / R-04 未覆盖 / R-05 部分覆盖）及依据见 **§3.7**；请勿按旧版文档结论推断覆盖状态。

---

## 2. 测试策略

### 2.1 隔离措施

- `MCPManager` 单例由 `reset_mcp_manager` fixture（`autouse`）在**每个用例前后**把 `core.mcp.manager._module_instance` 重置为 `None`（`conftest.py:12-23`）
- 配置文件 I/O 逐用例 mock：`pathlib.Path.exists`、`pathlib.Path.mkdir`、`builtins.open`（`test_manager.py:16-18` 等，配置类用例几乎都设置）
- `tmp_path` 生成真实临时配置文件（仅 `test_manager.py` 使用，共 4 处，例如 `test_load_config_from_file`、`test_load_config_handles_corrupt_file`）
- MCP SDK 导入由 `mock_mcp_sdk` fixture mock：`FastMCP`、`ClientSession`、`stdio_client`、`StdioServerParameters`、`streamable_http_client`（`conftest.py:39-76`）
- `MCPHostServer` 使用懒加载（`_fastmcp` 初始为 `None`，`test_server.py:51-57`）
- **无任何用例启动真实 Server 或发起真实网络 / 子进程通信**：`test_server.py::TestMCPHostServerLifecycle` 的 `run_stdio` / `run_http` 用例只覆盖「已运行时告警并 no-op」的早返回分支

### 2.2 测试数据

- Server 参数使用默认值（host=`127.0.0.1`, port=`8765`，`test_server.py:10-18`）
- 工具注册使用模拟的 plugin_id 和 method_name（`test_server.py:69-72`）
- session / config / 连接对象等外部依赖用 `MagicMock` 充当（`test_client.py:14-24`）
- 配置类用例直接构造配置对象后走 `to_dict` / `from_dict` 往返（`test_config.py`）

### 2.3 关键 Fixtures（test/core/mcp/conftest.py）

```python
# MCP 专用 fixtures
reset_mcp_manager      # autouse：每个用例前后重置 MCPManager 模块级单例
mock_tool_registry     # Mock ToolRegistry
mock_mcp_sdk           # Mock MCP SDK 导入（FastMCP / ClientSession / stdio / HTTP）
mock_mcp_host_server   # Mock MCPHostServer（避免真实启动）
```

> 另有 2 个**文件内局部 fixture**（不在 `conftest.py` 中，仅定义文件内可用）：
>
> - `mcp_manager`（`test_manager.py:8-22`）：构造 mock 依赖后的 `MCPManager`。**当前无任何用例引用它**——各用例改为在函数体内自行 `mocker.patch("pathlib.Path.exists"/"mkdir"/"builtins.open")`，该 fixture 属未被使用的冗余脚手架。
> - `client_manager`（`test_client.py:50-55`）：依赖 `mock_tool_registry` 构造 `MCPClientManager`，被 `TestMCPClientManager` 的多数用例使用。

---

## 3. 测试用例

> 以下「说明」列由代码中对应测试函数的 **docstring 首句翻译 / 归纳为中文**：保留方法名、类名、字段名等术语原文（如 `from_dict()`、`server.add_tool`、`_tool_registry`），语义与原文一致，**不增删断言细节、测试步骤或优先级**。仅当 docstring 缺失时才按函数名与所属测试类归纳（本模块 93 例均有 docstring，未触发该回退）。各文件用例数与 §1.1 实测值一致。

### 3.1 test_manager.py（MCPManager，27 例）

#### TestMCPManagerSingleton

> 类 docstring：Tests for MCPManager singleton behavior.

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_mcp_manager_returns_same_instance` | 验证重复调用返回同一实例。 |

#### TestMCPManagerConfig

> 类 docstring：Tests for MCPManager config management.

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_config_creates_default_if_missing` | 验证配置文件缺失时使用默认配置。 |
| `test_load_config_from_file` | 验证加载已存在的配置文件。 |
| `test_load_config_handles_corrupt_file` | 验证 JSON 解析出错时优雅回退。 |
| `test_update_server_config` | 验证更新并保存 Server 配置。 |
| `test_add_remote_server` | 验证新增远端 Server。 |
| `test_add_remote_server_duplicate_id_replaces` | 验证 server_id 重复时替换已有项。 |
| `test_remove_remote_server` | 验证删除成功时返回 True。 |
| `test_remove_remote_server_not_found` | 验证删除不存在的 id 时返回 False。 |

#### TestMCPManagerServerLifecycle

> 类 docstring：Tests for MCPManager server lifecycle.

| 用例函数名 | 说明 |
|-----------|------|
| `test_init_server_creates_mcp_host_server` | 验证 Server 已创建。 |
| `test_init_server_creates_bridge` | 验证 Bridge 已创建。 |
| `test_start_server_invalid_transport` | 验证未知 transport 抛出 ValueError。 |
| `test_stop_server_when_not_running` | 验证 Server 未运行时不做任何操作。 |
| `test_is_server_running` | 验证运行状态查询。 |
| `test_get_server_url_when_not_started` | 验证 Server 为 None 时返回空字符串。 |
| `test_get_server_config` | 验证返回 MCPServerConfig。 |

#### TestMCPManagerClientLifecycle

> 类 docstring：Tests for MCPManager client lifecycle.

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_client_manager_requires_tool_registry_on_first_call` | 验证首次调用未提供 tool_registry 时抛出 ValueError。 |
| `test_get_client_manager_returns_same_instance` | 验证 Client Manager 为单例。 |
| `test_list_connected_servers_empty` | 验证无 Client 时返回空列表。 |
| `test_list_remote_tools_empty` | 验证无 Client 时返回空列表。 |

#### TestMCPManagerBridge

> 类 docstring：Tests for MCPManager bridge coordination.

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_bridge_returns_none_before_init` | 验证 Server 初始化前 Bridge 为 None。 |
| `test_get_bridge_returns_bridge_after_init` | 验证 Server 初始化后 Bridge 已存在。 |
| `test_sync_plugin_tool_delegates_to_bridge` | 验证 sync_plugin_tool 调用 Bridge。 |
| `test_remove_plugin_tool_delegates_to_bridge` | 验证 remove_plugin_tool 调用 Bridge。 |

#### TestMCPManagerShutdown

> 类 docstring：Tests for MCPManager shutdown.

| 用例函数名 | 说明 |
|-----------|------|
| `test_shutdown_stops_server` | 验证调用了 stop_server。 |
| `test_shutdown_calls_client_manager_shutdown` | 验证关闭 Client Manager。 |
| `test_shutdown_when_not_started` | 验证各组件未初始化时不做任何操作。 |

---

### 3.2 test_server.py（MCPHostServer，15 例）

#### TestMCPHostServer

> 类 docstring：Tests for MCPHostServer initialization.

| 用例函数名 | 说明 |
|-----------|------|
| `test_init_default_values` | 验证 name='InstructionX'、host='127.0.0.1'、port=8765。 |
| `test_init_stores_parameters` | 验证参数被正确存储。 |
| `test_init_running_false` | 验证初始 `_running` 为 False。 |
| `test_init_tool_registry_empty` | 验证 `_tool_registry` 为空字典。 |
| `test_init_fastmcp_none` | 验证 `_fastmcp` 为 None（懒加载）。 |

#### TestMCPHostServerToolManagement

> 类 docstring：Tests for MCPHostServer tool management.

| 用例函数名 | 说明 |
|-----------|------|
| `test_add_tool_records_in_registry_directly` | 验证不经 FastMCP 即可把工具写入 `_tool_registry`。 |
| `test_remove_tool_removes_from_registry` | 验证工具已从 `_tool_registry` 移除。 |
| `test_remove_tool_not_found` | 验证工具不存在时不报错。 |
| `test_registered_tools_returns_copy` | 验证返回字典副本而非原引用。 |

#### TestMCPHostServerLifecycle

> 类 docstring：Tests for MCPHostServer lifecycle.

| 用例函数名 | 说明 |
|-----------|------|
| `test_run_stdio_already_running` | 验证已运行时仅告警且不做任何操作。 |
| `test_run_http_already_running` | 验证已运行时仅告警且不做任何操作。 |
| `test_stop_sets_running_false` | 验证 stop 后 `_running` 为 False。 |
| `test_is_running_property` | 验证该属性返回 `_running` 状态。 |

#### TestMCPHostServerDeferredRegistration

> 类 docstring：Tests for deferred tool registration.

| 用例函数名 | 说明 |
|-----------|------|
| `test_tool_registry_stores_deferred_info` | 验证延迟注册的工具信息被存入注册表。 |
| `test_remove_tool_clears_deferred_info` | 验证移除工具时清除延迟注册信息。 |

---

### 3.3 test_client.py（MCPClientManager / MCPServerConnection，13 例）

#### TestMCPServerConnection

> 类 docstring：Tests for MCPServerConnection dataclass.

| 用例函数名 | 说明 |
|-----------|------|
| `test_connection_fields` | 验证 server_id、name、config、session、tools 被正确存储。 |
| `test_tool_name_map_initialized` | 验证 tool_name_map 为字典。 |

#### TestMCPClientManager

> 类 docstring：Tests for MCPClientManager.

| 用例函数名 | 说明 |
|-----------|------|
| `test_init_requires_tool_registry` | 验证 tool_registry 被存储。 |
| `test_ensure_loop_creates_new_loop` | 验证事件循环为 None 时新建事件循环。 |
| `test_ensure_loop_reuses_existing_loop` | 验证复用已有事件循环。 |
| `test_ensure_loop_creates_new_loop_if_closed` | 验证已有事件循环已关闭时新建事件循环。 |
| `test_list_connected_servers_empty` | 验证初始为空列表。 |
| `test_list_tools_server_not_found` | 验证未知 Server 返回空列表。 |
| `test_get_connection_server_not_found` | 验证未知 Server 返回 None。 |
| `test_get_connection_exists` | 验证连接存在时返回该连接。 |
| `test_disconnect_not_found` | 验证未知 Server 时不做任何操作。 |
| `test_shutdown_closes_all_connections` | 验证所有连接均已关闭。 |
| `test_make_handler_creates_callable` | 验证 `_make_handler` 生成可调用的 handler。 |

---

### 3.4 test_bridge.py（MCPBridge，16 例）

#### TestMCPBridge

> 类 docstring：Tests for MCPBridge initialization.

| 用例函数名 | 说明 |
|-----------|------|
| `test_init_stores_manager` | 验证 manager 被存储。 |
| `test_init_synced_tools_empty` | 验证 `_synced_tools` 为空字典。 |

#### TestMCPBridgeSyncPluginAPI

> 类 docstring：Tests for MCPBridge.sync_plugin_api_to_mcp_server().

| 用例函数名 | 说明 |
|-----------|------|
| `test_sync_plugin_api_server_not_init` | 验证 server 为 None 时优雅处理。 |
| `test_sync_plugin_api_skips_already_synced` | 验证已同步的工具被跳过。 |
| `test_sync_plugin_api_parses_plugin_id_method_name` | 验证 'plugin_id.method_name' 的解析。 |
| `test_sync_plugin_api_skips_invalid_name_format` | 验证不含 '.' 的名称被跳过。 |
| `test_get_synced_tool_count_initial` | 验证计数初始为 0。 |
| `test_get_synced_tool_count_after_sync` | 验证同步后计数增加。 |

#### TestMCPBridgeSyncNewTool

> 类 docstring：Tests for MCPBridge.sync_new_plugin_tool().

| 用例函数名 | 说明 |
|-----------|------|
| `test_sync_new_plugin_tool_adds_to_server` | 验证调用了 server.add_tool。 |
| `test_sync_new_plugin_tool_marks_as_synced` | 验证工具被标记到 `_synced_tools`。 |
| `test_sync_new_plugin_tool_skips_already_synced` | 验证重复时跳过。 |
| `test_sync_new_plugin_tool_server_not_init` | 验证 server 为 None 时不做任何操作。 |

#### TestMCPBridgeRemoveTool

> 类 docstring：Tests for MCPBridge.remove_plugin_tool().

| 用例函数名 | 说明 |
|-----------|------|
| `test_remove_plugin_tool_calls_server_remove_tool` | 验证调用了 server.remove_tool。 |
| `test_remove_plugin_tool_removes_from_synced_tools` | 验证工具已从 `_synced_tools` 移除。 |
| `test_remove_plugin_tool_server_not_init` | 验证 server 为 None 时不做任何操作。 |
| `test_remove_plugin_tool_not_in_synced` | 验证工具不在 `_synced_tools` 中时不报错。 |

---

### 3.5 test_config.py（配置数据类，18 例）

#### TestMCPServerConfig

> 类 docstring：Tests for MCPServerConfig.to_dict / from_dict.

| 用例函数名 | 说明 |
|-----------|------|
| `test_default_values` | 验证默认值：host、port、transport、enabled。 |
| `test_to_dict` | to_dict() 生成正确的字典。 |
| `test_from_dict` | from_dict() 正确反序列化。 |
| `test_from_dict_with_overrides` | from_dict() 对缺失的键使用默认值。 |
| `test_roundtrip` | to_dict → from_dict 往返保留全部字段。 |

#### TestMCPRemoteServerConfig

> 类 docstring：Tests for MCPRemoteServerConfig.to_dict / from_dict.

| 用例函数名 | 说明 |
|-----------|------|
| `test_required_fields` | 验证 server_id 与 name 为必填（无默认值）。 |
| `test_default_values` | 验证默认值：transport、enabled、args。 |
| `test_to_dict_stdio` | to_dict() 保留 stdio 字段。 |
| `test_to_dict_http` | to_dict() 保留 HTTP 字段。 |
| `test_to_dict_excludes_none_url` | to_dict() 输出中省略 None 值。 |
| `test_from_dict` | from_dict() 正确反序列化全部字段。 |
| `test_roundtrip` | to_dict → from_dict 往返保留全部字段。 |

#### TestMCPConfig

> 类 docstring：Tests for MCPConfig.to_dict / from_dict.

| 用例函数名 | 说明 |
|-----------|------|
| `test_default_server` | 验证创建默认 MCPServerConfig。 |
| `test_default_remote_servers` | 验证默认为空列表。 |
| `test_to_dict` | to_dict() 生成嵌套序列化结果。 |
| `test_from_dict` | from_dict() 正确反序列化嵌套配置。 |
| `test_from_dict_empty_remote_servers` | from_dict() 处理空的 remote_servers 列表。 |
| `test_roundtrip` | to_dict → from_dict 往返保留全部字段。 |

---

### 3.6 test_plugin_interface.py（抽象接口，4 例）

#### TestIMCPTool

> 类 docstring：Tests for IMCPTool abstract interface.

| 用例函数名 | 说明 |
|-----------|------|
| `test_abstract_methods_require_override` | 验证未实现抽象方法时 IMCPTool 无法实例化。 |
| `test_concrete_implementation` | 验证实现全部方法的子类可以实例化。 |

#### TestIMCPClient

> 类 docstring：Tests for IMCPClient abstract interface.

| 用例函数名 | 说明 |
|-----------|------|
| `test_abstract_methods_require_override` | 验证未实现抽象方法时 IMCPClient 无法实例化。 |
| `test_concrete_implementation` | 验证实现全部方法的子类可以实例化。 |

> 说明：`test_abstract_methods_require_override` 与 `test_concrete_implementation` 在 `TestIMCPTool`、`TestIMCPClient` 两个类中**各存在一份**（共 4 例）——同名但属于不同测试类，因此本文档共 93 行、去重后 84 个函数名。

---

### 3.7 风险覆盖标注（R-02 / R-04 / R-05）

> 本节结论按 `test/core/mcp/` 下**实际存在的用例**重新核对，不沿用旧版文档结论。旧版文档中的 `TC-MCP-019` ~ `TC-MCP-023` 编号不对应任何真实测试函数（计划态残留），已由「真实用例函数名 + 文件:行号」取代；`test/TESTING.md` §6.1 中引用这些 TC 编号的位置需按本表口径理解。

| 风险 ID | 描述 | 结论 | 依据（文件:行号） |
|---------|------|------|------------------|
| R-02 | MCP 私有 API 依赖 `_tool_manager._tools` | **部分覆盖** | 相关用例：`test/core/mcp/test_server.py:63` `test_add_tool_records_in_registry_directly`、`:78` `test_remove_tool_removes_from_registry`、`:102` `test_registered_tools_returns_copy`——均只操作 Server 自身的公开注册表 API 与 `_tool_registry`，**没有**「不依赖私有属性」的专用断言。源码私有依赖：`core/mcp/server.py:293-294`、`core/mcp/server.py:334-335`（`getattr(self._fastmcp, "_tool_manager")` / `getattr(tool_manager, "_tools")`）；`conftest.py:49-51` 的 mock 反而固化了该私有结构 |
| R-04 | MCP Client 60 秒超时硬编码 | **未覆盖** | `test/core/mcp/` 下**没有任何超时相关用例**：对 6 个 `test_*.py` 检索 `timeout` / `TIMEOUT` / `60` 命中 **0** 处。源码侧：`core/mcp/client.py:44` `DEFAULT_MCP_CLIENT_TIMEOUT = 60.0`，可由构造参数 `timeout` 覆盖（`core/mcp/client.py:86`、`:93`），并作用于 `future.result(timeout=self._timeout)`（`:131`、`:356`、`:375`）——该可配置行为无测试守护 |
| R-05 | MCP Client 连接可能泄漏 | **部分覆盖** | 相关用例：`test/core/mcp/test_client.py:126` `test_shutdown_closes_all_connections`、`:121` `test_disconnect_not_found`。其中 `test_shutdown_closes_all_connections` **未调用 `shutdown()`**，而是自行 `_connections.clear()` 后断言字典为空（`test_client.py:138-142`），断言强度不足（自证式）；**异常路径的 session 释放无专用用例**。源码关闭路径：`core/mcp/client.py:397` `shutdown()`、`:305-329` `_async_disconnect()`（经 `exit_stack.aclose()` 释放，`:323-326`）、`:179` / `:210` 以 `AsyncExitStack` 持有 session 上下文 |

**结论口径**：

- **已覆盖**：代码中存在针对该风险的用例
- **部分覆盖**：有相关用例，但未覆盖该风险场景的全部路径（含仅间接覆盖、断言强度不足）
- **未覆盖**：暂无对应用例，属待补测试

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/mcp/` 添加新功能时：

1. 在对应的测试文件中找到测试类（§3 的清单即当前全集，共 21 个测试类）
2. 添加新测试函数，遵循命名规范（`test_<场景描述>`）
3. 编写 docstring——**其首句会被翻译 / 归纳写入本文档「说明」列**（术语保留原文），因此需用一句话点明被验证的行为
4. 确保使用正确的 fixtures（§2.3）
5. 同步更新本文档：§1.1 / §1.2 的计数与 §3 对应表格，「用例数」必须与 `--collect-only` 实测一致

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查 fixtures 是否正确

### 4.3 覆盖率与已知未覆盖路径

- 本文档**不记录覆盖率数字**（未实测的百分比不写入文档）；需要时按下式实测：

  ```powershell
  .venv\Scripts\python.exe -m pytest test/core/mcp --cov=core.mcp --cov-report=term-missing -q -p no:cacheprovider
  ```

- 按当前代码逐项比对，以下路径**未覆盖或仅间接覆盖**（与 §3.7 的 R-02 / R-04 / R-05 结论一致）：
  - **超时配置与超时行为**：0 例（R-04）
  - **异常路径的 session 释放**：无专用用例；关闭路径用例断言强度不足（R-05）
  - **「不依赖 FastMCP 私有属性 `_tool_manager._tools`」**：无专用断言（R-02）
  - **真实 MCP 通信**：stdio 子进程 / streamable HTTP 网络链路均无覆盖，全部经 mock 隔离（§2.1）
  - **`MCPHostServer.run_stdio()` / `run_http()` 的实际启动路径**：仅覆盖「已运行时告警并 no-op」分支
  - **`MCPClientManager.connect()` / `_async_connect()` 的连接成功与失败路径**：无直接用例（现有用例覆盖 `_ensure_loop`、连接查询、断开、关闭等本地路径）

---

## 5. 相关文档

- [MCP 协议概述](../../../docs/core/mcp/overview.md)
- [测试主文档](../../TESTING.md)（§6.1 风险覆盖清单、§7 模块测试文档）
- [本目录 README](README.md)（目录结构、fixtures 与 mock 策略）

> 旧版本节曾链接 `../../docs/core/mcp/config.md`，该文件在仓库中不存在（`docs/core/mcp/` 下仅有 `overview.md`），故不再列出。

---
