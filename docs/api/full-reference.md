# API 完整参考

> 所有核心类的完整 API 索引

---

## 1. 核心模块导入

### 1.1 从 core 导入（核心实现类）

```python
# 插件系统
from core import PluginManager, IPlugin, IPluginInfo

# 数据层
from core import DataProvider, DataNamespace

# 后台任务
from core import BackgroundTaskManager, TaskType, TaskStatus, BackgroundTask, ScheduledTask, LongRunningTask
```

### 1.2 从 core.interfaces 导入（抽象接口，推荐）

```python
# 抽象接口层（推荐用于插件开发）
from core.interfaces import IPlugin, IPluginInfo, IDataProvider, ITaskManager
from core.interfaces import TaskType, TaskStatus
from core.interfaces import ILLMFacade, Message, ChatResponse, EmbeddingResponse, ModelInfo
from core.llm import UsageInfo  # UsageInfo 不在 core.interfaces.__all__ 中，需从 core.llm 导入
from core.interfaces import ILogger, PluginServices
```

### 1.3 从 core.data.data_provider 导入

```python
# 数据层
from core.data.data_provider import DataProvider, DataNamespace, DataProviderError
```
> 注意：`DataProviderError` 未从 `core` 主模块导出，需使用上述路径导入。

### 1.4 从 core.llm 导入

```python
# LLM 核心层
from core.llm import get_llm_provider

# LLM 插件服务层（推荐插件开发者使用）
from core.llm import get_llm_plugin_service

# LLM 数据类型（也可从 core.interfaces 导入，推荐方式）
from core.llm import Message, ChatResponse, EmbeddingResponse, ModelInfo, UsageInfo

# LLM 服务层数据类型
from core.llm import (
    Conversation, ToolResult, UsageStats, StreamChunk,
    ImageResult, AudioResult, ProviderInfo
)

# LLM 配置
from core.llm import LLMConfig, ProviderConfig

# LLM Provider 接口
from core.llm import ILLM

# LLM 用量持久化
from core.llm import UsageRecordStore, get_usage_record_store

# LLM 缓存相关
from core.llm import CacheInfo, CacheType, CacheAdapter, get_cache_adapter, DEFAULT_CACHE_CONFIG

# LLM 插件服务层类
from core.llm import LLMPluginService, get_llm_plugin_service
from core.llm import ConversationManager, ToolCallExecutor, ToolRegistry

# LLM 异常
from core.llm.exceptions import (
    LLMException, ConfigurationError, AuthenticationError, APIError,
    RateLimitError, InvalidRequestError, ModelNotSupportedError,
    ConnectionError, TimeoutError, StreamingError
)
```

### 1.5 从 core.mcp 导入

```python
# MCP 核心
from core.mcp import get_mcp_manager, MCPManager

# MCP 配置
from core.mcp import MCPConfig, MCPServerConfig, MCPRemoteServerConfig

# MCP Server / Client / Bridge
from core.mcp import MCPHostServer, MCPClientManager, MCPBridge, MCPServerConnection

# MCP 插件接口
from core.mcp import IMCPTool, IMCPClient
```

---

## 2. 插件系统 API

### 2.1 PluginManager

**文件**: `core/plugin/manager.py`

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get_plugin_manager()` | 获取单例实例 | PluginManager |
| `PluginManager()` | 获取单例实例 | PluginManager |
| `load_plugins()` | 加载所有插件 | None |
| `load_official_plugins()` | 加载官方插件 | List[IPlugin] |
| `load_thirdparty_plugins()` | 加载第三方插件 | List[IPlugin] |
| `get_all_plugins()` | 获取所有插件 | List[IPlugin] |
| `get_plugin_by_id(plugin_id)` | 根据 UUID 获取插件 | Optional[IPlugin] |
| `get_plugin_by_name(name)` | 根据名称获取插件 | Optional[IPlugin] |
| `get_plugin_id_by_name(name)` | 根据名称获取 UUID | Optional[str] |
| `get_plugin_id_by_type_id(plugin_type_id)` | 根据类型 ID 获取 UUID | Optional[str] |
| `get_plugin_by_type_id(plugin_type_id)` | 根据类型 ID 获取插件 | Optional[IPlugin] |
| `get_official_plugins()` | 获取官方插件列表 | List[IPlugin] |
| `get_thirdparty_plugins()` | 获取第三方插件列表 | List[IPlugin] |
| `reload_plugins()` | 重新加载所有插件 | None |
| `register_plugin(plugin, is_official)` | 手动注册插件 | None |
| `unregister_plugin(plugin_name)` | 移除插件 | None |
| `apply_custom_order()` | 应用自定义顺序 | None |
| `save_plugin_order(official_plugin_ids, thirdparty_plugin_ids)` | 保存插件顺序 | bool |
| `get_official_plugin_ids()` | 获取官方插件 UUID 列表 | List[str] |
| `get_thirdparty_plugin_ids()` | 获取第三方插件 UUID 列表 | List[str] |
| `get_plugin_api(plugin_id)` | 获取插件 API 信息 | Optional[Dict] |
| `get_all_apis()` | 获取所有 API | Dict |
| `unregister_plugin_api(plugin_id)` | 移除插件 API 注册 | None |
| `register_plugin_api(plugin_id, service_instance, api_descriptions)` | 注册插件 API | None |
| `get_api_description(plugin_id, method_name=None)` | 获取 API 结构化描述 | Dict |
| `call_plugin_method(caller_id, plugin_id, method_name, **kwargs)` | 跨插件调用 | Any |
| `get_all_function_tools()` | 获取 MCP 工具列表 | List[Dict] |

### 2.2 IPlugin

**文件**: `core/interfaces/i_plugin.py`（抽象接口定义）<br>推荐使用 `core/plugin/plugin_interface.py`（框架实现，含控件缓存）

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `plugin_name` | property (abstract) | 插件名称 |
| `plugin_id` | property | 插件 UUID |
| `skill_icon` | property | 技能按钮图标 |
| `skill_description` | property | 技能描述 |
| `skill_tooltip` | property | 工具提示 |
| `plugin_info` | property | 插件信息对象 |
| `llm_tools` | property | LLM 工具列表（用于 MCP/Function Calling） |
| `_create_widget(parent, data_provider)` | method (abstract) | 创建 UI |
| `get_widget(parent=None, data_provider=None)` | method | 获取 Widget（带缓存） |
| `on_plugin_loaded(plugin_id=None, **kwargs)` | method | 加载完成回调（PluginManager 调用时不传参数，向后兼容旧插件） |

### 2.3 IPluginInfo

**文件**: `core/interfaces/i_plugin_info.py`（推荐导入路径）

| 属性 | 类型 | 说明 |
|------|------|------|
| `version` | property | 插件版本 |
| `developer` | property | 开发者名称 |
| `developer_email` | property | 开发者邮箱 |
| `developer_website` | property | 开发者网站 |
| `is_free` | property | 是否免费 |
| `description` | property | 详细描述 |
| `service_api` | property | API 定义字典 |
| `skill_icon` | property | 技能图标 |
| `skill_description` | property | 技能描述 |
| `plugin_type_id` | property | 插件类型标识符（必选，用于代码层面识别） |
| `tags` | property | 标签列表（可选） |
| `dependencies` | property | 插件依赖项（可选） |

---

## 3. 数据层 API

### 3.1 DataProvider

**文件**: `core/data/data_provider.py`

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `DataProvider(data_dir=None, data_filename="data.json")` | 获取单例实例（参数均有默认值） | DataProvider |
| `register_plugin(instance_id, plugin_type)` | 注册插件 | None |
| `unregister_plugin(instance_id)` | 注销插件 | None |
| `get_active_instance(type)` | 获取活跃实例 | Optional[str] |
| `set_active_instance(instance_id)` | 设置活跃实例 | None |
| `get_plugin_data(instance_id, key, namespace, default)` | 获取数据 | Any |
| `set_plugin_data(instance_id, key, value, namespace, notify)` | 设置数据，notify 默认 True，控制是否通知订阅者 | None |
| `get_all_plugin_data(instance_id, namespace)` | 获取所有数据 | Dict |
| `subscribe(subscriber_id, target_plugin_id, target_key, callback)` | 订阅数据 | None |
| `unsubscribe(subscriber, target=None)` | 取消订阅，target 为空则取消所有订阅 | None |
| `publish(publisher, key, value, namespace)` | 发布数据 | None |
| `save_asset(plugin_id, filename, content)` | 保存资源 | str |
| `get_asset_path(relative_path)` | 获取绝对路径 | str |
| `load_asset(relative_path)` | 加载资源 | bytes |
| `get_plugin_assets_dir(plugin_id)` | 获取资源目录 | str |
| `load_data(force_reload)` | 加载数据 | Dict |
| `save_data()` | 保存数据 | None |
| `clear_cache()` | 清除缓存 | None |
| `get_all_plugins()` | 获取所有插件 | Dict |
| `get_plugin_info(instance_id)` | 获取插件信息 | Optional[Dict] |
| `reset_all_data()` | 重置所有数据 | None |

### 3.2 DataNamespace

**文件**: `core/data/data_provider.py`

| 枚举值 | 说明 |
|--------|------|
| `DataNamespace.PRIVATE` | 私有数据 |
| `DataNamespace.PUBLIC` | 公共数据 |

---

## 4. 后台任务 API

### 4.1 BackgroundTaskManager

**文件**: `core/task/background_task.py`

> 注意: `BackgroundTaskManager` 采用单例模式，直接调用 `BackgroundTaskManager()` 获取单例实例。

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `BackgroundTaskManager()` | 获取单例实例（单例模式） | BackgroundTaskManager |
| `register_sync_task(plugin_id, name, func, callback, args, kwargs)` | 注册同步任务 | str (task_id) |
| `register_async_task(plugin_id, name, func, callback, args, kwargs)` | 注册异步任务 | Optional[str]（task_id；shutdown 后为 None） |
| `register_scheduled_task(plugin_id, name, func, interval, callback, args, kwargs)` | 注册定时任务 | Optional[str]（task_id；shutdown 后为 None） |
| `register_scheduled_task_factory(plugin_id, func, callback)` | 注册任务工厂 | None |
| `restore_scheduled_tasks(plugin_id)` | 恢复定时任务 | int |
| `enable_scheduled_task(task_id)` | 启用定时任务 | bool |
| `disable_scheduled_task(task_id)` | 禁用定时任务 | bool |
| `unregister_scheduled_task(task_id)` | 注销定时任务 | bool |
| `register_long_running_task(plugin_id, name, func, callback, stop_callback, status_callback, auto_restart, args, kwargs)` | 注册长期任务 | str (task_id) |
| `register_long_running_task_factory(plugin_id, func, callback, stop_callback, status_callback, restore_callback)` | 注册长期任务工厂 | None |
| `restore_long_running_tasks(plugin_id)` | 恢复长期任务 | int |
| `stop_long_running_task(task_id, delete_from_storage)` | 停止长期任务 | bool |
| `update_long_running_task_status(task_id, status)` | 更新长期任务状态 | bool |
| `get_long_running_tasks(plugin_id)` | 获取长期任务列表 | List[LongRunningTask] |
| `get_task(task_id)` | 获取任务 | Optional[BackgroundTask] |
| `get_tasks_by_plugin(plugin_id)` | 获取插件任务 | List[BackgroundTask] |
| `get_all_tasks()` | 获取所有任务 | List[BackgroundTask] |
| `get_task_status(task_id)` | 获取任务状态 | Optional[TaskStatus] |
| `get_scheduled_tasks(plugin_id)` | 获取定时任务 | List[ScheduledTask] |
| `cancel_task(task_id)` | 取消任务 | bool |
| `clear_completed_tasks(plugin_id)` | 清理已完成任务 | int |
| `shutdown()` | 关闭任务管理器 | None |

### 4.2 TaskType

**文件**: `core/task/task_model.py`

| 枚举值 | 说明 |
|--------|------|
| `TaskType.SYNC` | 同步任务 |
| `TaskType.ASYNC` | 异步任务 |
| `TaskType.SCHEDULED` | 定时任务 |
| `TaskType.LONG_RUNNING` | 长期任务 |

### 4.3 TaskStatus

**文件**: `core/task/task_model.py`

| 枚举值 | 说明 |
|--------|------|
| `TaskStatus.PENDING` | 待执行 |
| `TaskStatus.RUNNING` | 执行中 |
| `TaskStatus.COMPLETED` | 已完成 |
| `TaskStatus.FAILED` | 执行失败 |
| `TaskStatus.CANCELLED` | 已取消 |
| `TaskStatus.STOPPED` | 已停止 |

---

## 5. LLM Provider API

### 5.1 LLMProvider

**文件**: `core/llm/llm_provider.py`

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `get_llm_provider()` | 获取单例实例 | LLMProvider |
| `chat(messages, provider, model, temperature, max_tokens, **kwargs)` | 同步聊天，支持 tools 等参数通过 kwargs 传递 | ChatResponse |
| `stream_chat(messages, provider, model, temperature, max_tokens, callback, **kwargs)` | 流式聊天 | Iterator 或 None |
| `async_chat(messages, provider, model, temperature, max_tokens, **kwargs)` | 异步聊天 | ChatResponse |
| `async_stream_chat(messages, provider, model, temperature, max_tokens, **kwargs)` | 异步流式聊天 | AsyncIterator |
| `embed(texts, provider, model, **kwargs)` | 文本嵌入 | List[EmbeddingResponse] |
| `async_embed(texts, provider, model)` | 异步文本嵌入 | List[EmbeddingResponse] |
| `get_models(provider)` | 获取模型列表 | Dict[str, List[ModelInfo]] |
| `refresh_provider_models(provider_name, force)` | 刷新指定 Provider 模型 | List[ModelInfo] |
| `refresh_all_models(force)` | 刷新所有模型 | Dict[str, List[ModelInfo]] |
| `get_cached_models(provider_name)` | 获取缓存模型 | List[ModelInfo] |
| `get_provider(name)` | 获取 Provider 实例 | Optional[ILLM] |
| `get_all_providers()` | 获取所有 Provider | Dict[str, ILLM] |
| `get_enabled_providers(feature)` | 获取启用的 Provider | Dict[str, ILLM] |
| `add_provider(name, config)` | 添加 Provider | None |
| `remove_provider(name)` | 移除 Provider | bool |
| `reload_config()` | 重新加载配置 | None |
| `close()` | 关闭所有提供商连接 | None |
| `config` | 配置管理器 | LLMConfig |
| `available_providers` | 可用 Provider 列表 | List[str] |

### 5.2 异常类

**文件**: `core/llm/exceptions.py`

| 异常类 | 说明 |
|--------|------|
| `LLMException` | 基础异常类 |
| `ConfigurationError` | 配置错误 |
| `AuthenticationError` | 认证错误 |
| `APIError` | API 调用错误 |
| `RateLimitError` | 速率限制 |
| `ModelNotSupportedError` | 模型不支持 |
| `ConnectionError` | 连接错误 |
| `TimeoutError` | 超时错误 |
| `InvalidRequestError` | 无效请求 |
| `StreamingError` | 流式输出错误 |

### 5.3 LLMPluginService（插件开发者主入口）

**文件**: `core/llm/plugin_service.py`

推荐通过 `PluginServices.llm_facade`（DI 注入）或 `get_llm_plugin_service()` 获取。

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `create_conversation(system_prompt?, provider?, model?, metadata?)` | 创建对话 | str (conv_id) |
| `send_message(conv_id, content, images?, ...)` | 同步发送消息 | str (回复内容) |
| `stream_send_message(conv_id, content, callback?, ...)` | 流式发送消息 | str (回复内容) |
| `chat(messages, provider?, model?, ...)` | 直接 chat（无对话状态） | ChatResponse |
| `stream_chat(messages, callback, provider?, ...)` | 流式 chat（无对话状态），callback 签名为 `(chunk: str, done: bool)` | None |
| `chat_with_tools(messages, provider?, model?, max_turns?, ...)` | 工具调用循环 | Tuple[List[Dict], List[ToolResult], Any] |
| `chat_with_tools_stream(messages, callback, provider?, ...)` | 流式工具调用（当前流式路径不会解析 `tool_calls`，实际暂不可用） | Tuple[List[Dict], List[ToolResult], str] |
| `get_tool_executor()` | 获取工具调用执行器 | ToolCallExecutor |
| `get_shared_tool_registry()` | 获取共享工具注册表 | ToolRegistry |
| `get_raw_provider(provider="default")` | 获取底层 ILLM Provider（高级用） | ILLM |
| `embed(texts, provider?, model?)` | 向量嵌入 | List[List[float]] |
| `generate_image(prompt, provider?, model?, size?, quality?)` | 图像生成 | ImageResult |
| `text_to_speech(text, provider?, model?, voice?)` | 文本转语音 | AudioResult |
| `load_image_as_base64(file_path)` | 图片文件转 base64 | str |
| `get_available_providers()` | 获取所有 Provider 信息 | List[ProviderInfo] |
| `get_usage_stats(conversation_id?)` | 获取用量统计 | UsageStats |
| `validate_provider(provider)` | 验证 Provider 配置 | Tuple[bool, str] |

详细文档: [LLM Provider API 参考](../core/llm-provider/api-reference.md)

### 5.4 ConversationManager

**文件**: `core/llm/conversation_manager.py`

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `create_conversation(system_prompt?, provider?, model?)` | 创建对话 | str (conv_id) |
| `get_conversation(conv_id)` | 获取对话 | Optional[Conversation] |
| `list_conversations()` | 列出所有对话 | List[Conversation] |
| `delete_conversation(conv_id)` | 删除对话 | bool |
| `get_usage_stats(conv_id?)` | 获取用量统计 | UsageStats |

### 5.5 ToolCallExecutor / ToolRegistry

**文件**: `core/llm/tool_call_executor.py`

| 组件 | 方法/属性 | 说明 |
|------|---------|------|
| `ToolRegistry` | `register(name, description, parameters, handler)` | 注册工具 |
| `ToolRegistry` | `unregister(name)` | 注销工具 |
| `ToolRegistry` | `get_handler(name)` | 获取工具处理器（callable） |
| `ToolRegistry` | `get_tools()` | 获取所有工具定义列表 |
| `ToolCallExecutor` | `chat_with_tools(messages, provider?, model?, max_turns?, ...)` | 工具调用循环 |
| `ToolCallExecutor` | `chat_with_tools(..., stream, stream_callback)` | 流式工具调用 |

### 5.6 MCPManager

**文件**: `core/mcp/manager.py`

| 方法 | 说明 |
|------|------|
| `get_mcp_manager()` | 获取 MCPManager 全局单例 |
| `start_server(transport=None)` | 启动 MCP Server（None 时使用配置默认值） |
| `stop_server()` | 停止 MCP Server |
| `is_server_running()` | Server 是否运行中 |
| `get_server_url()` | 返回 HTTP Server 地址 |
| `update_server_config(config)` | 更新 Server 配置 |
| `get_config()` | 获取当前 MCP 配置 |
| `get_server_config()` | 获取当前 Server 配置 |
| `get_server()` | 获取 MCPHostServer 实例 |
| `get_client_manager(tool_registry)` | 获取 MCPClientManager |
| `connect(config, tool_registry)` | 连接外部 MCP Server，返回 server_id |
| `disconnect(server_id)` | 断开外部 MCP Server |
| `list_connected_servers()` | 已连接 server_id 列表 |
| `list_remote_tools(server_id)` | 列出外部 Server 工具 |
| `add_remote_server(config)` | 添加外部 MCP Server 配置 |
| `remove_remote_server(server_id)` | 移除外部 MCP Server 配置 |
| `sync_plugin_tool(plugin_id, method_name, description, parameters)` | 同步插件工具到 MCP 系统 |
| `remove_plugin_tool(plugin_id, method_name)` | 从 MCP 系统移除插件工具 |
| `get_bridge()` | 获取 MCPBridge 实例 |
| `shutdown()` | 关闭所有资源 |

### 5.7 MCPClientManager

**文件**: `core/mcp/client.py`

| 方法 | 说明 |
|------|------|
| `connect(config)` | 同步连接外部 MCP Server |
| `disconnect(server_id)` | 断开连接 |
| `list_connected_servers()` | 列出已连接 server_id |
| `list_tools(server_id)` | 列出指定 Server 工具（带命名空间前缀 `mcp:{server_id}:{tool}`） |
| `get_connection(server_id)` | 获取指定连接的信息 |
| `shutdown()` | 关闭所有连接 |

---

## 6. 常用代码片段

### 6.1 获取核心单例

```python
# 插件管理器
plugin_manager = PluginManager()
# 或
plugin_manager = get_plugin_manager()

# 数据提供者
data_provider = DataProvider()

# 后台任务管理器
task_manager = BackgroundTaskManager()

# LLM 提供者
llm_provider = get_llm_provider()

# LLM 插件服务层（推荐）
llm_service = get_llm_plugin_service()

# MCP 管理器
mcp_manager = get_mcp_manager()
```

### 6.2 创建插件 Widget

```python
# 获取插件
plugin = plugin_manager.get_plugin_by_id("plugin-uuid")

# 获取 Widget（带缓存）
widget = plugin.get_widget(parent=parent_widget, data_provider=data_provider)
```

### 6.3 数据操作

```python
# 存储数据
data_provider.set_plugin_data(
    plugin_id,
    "key",
    value,
    DataNamespace.PRIVATE
)

# 读取数据
value = data_provider.get_plugin_data(
    plugin_id,
    "key",
    DataNamespace.PRIVATE,
    default="default_value"
)
```

### 6.4 发布/订阅

```python
# 订阅
# callback 签名: callback(target_plugin_id, key, old_value, new_value)
def my_callback(plugin_id, key, old_value, new_value):
    print(f"数据变更: {key} 从 {old_value} 变为 {new_value}")

data_provider.subscribe(
    subscriber_id="my-plugin",
    target_plugin_id="target-plugin",
    target_key="status",
    callback=my_callback
)

# 发布（namespace 默认为 DataNamespace.PUBLIC）
data_provider.publish(
    publisher_id="my-plugin",
    key="status",
    value="new_status"
)
```

### 6.5 跨插件调用

```python
# 获取目标插件 ID
target_id = plugin_manager.get_plugin_id_by_name("目标插件名称")

# 调用方法
result = plugin_manager.call_plugin_method(
    caller_id="my-plugin",
    plugin_id=target_id,
    method_name="method_name",
    param1="value1",
    param2="value2"
)
```

### 6.6 注册后台任务

```python
# 同步任务（立即在主线程执行）
task_id = task_manager.register_sync_task(
    plugin_id="my-plugin",
    name="同步任务",
    func=my_function,
    callback=my_callback,
    args=(arg1, arg2)
)

# 异步任务（在线程池中执行）
task_id = task_manager.register_async_task(
    plugin_id="my-plugin",
    name="后台任务",
    func=my_function,
    callback=my_callback,
    args=(arg1, arg2)
)

# 定时任务
task_id = task_manager.register_scheduled_task(
    plugin_id="my-plugin",
    name="定时任务",
    func=periodic_function,
    interval=60
)
```

---

## 7. 抽象接口层 API

### 7.1 概述

`core/interfaces/` 目录定义了框架的抽象接口层，将插件开发 API 与内部实现解耦。插件应该通过这些接口与核心服务交互，而非直接依赖具体实现。

详细概述：[接口层概述](../core/interfaces/overview.md)

### 7.2 IPlugin（插件接口）

**文件**: `core/interfaces/i_plugin.py`

与 `core/interfaces/i_plugin.py` 一致（`core/plugin/plugin_interface.py` 保留向后兼容）。

### 7.3 IPluginInfo（插件信息接口）

**文件**: `core/interfaces/i_plugin_info.py`

与 `core/interfaces/i_plugin_info.py` 一致（`core/plugin/plugin_info_interface.py` 保留向后兼容）。

### 7.4 IDataProvider（数据提供者接口）

**文件**: `core/interfaces/i_data_provider.py`

| 方法 | 说明 |
|------|------|
| `register_plugin(instance_id, plugin_type)` | 注册插件实例 |
| `unregister_plugin(instance_id)` | 注销插件实例 |
| `get_active_instance(plugin_type)` | 获取活跃插件实例 ID |
| `set_active_instance(instance_id)` | 设置活跃插件实例 |
| `get_plugin_data(instance_id, key, namespace, default)` | 获取插件数据 |
| `set_plugin_data(instance_id, key, value, namespace, notify)` | 设置插件数据（notify 默认为 True） |
| `get_all_plugin_data(instance_id, namespace)` | 获取插件所有数据 |
| `subscribe(subscriber_id, target_plugin_id, target_key, callback)` | 订阅数据变化，callback 签名 `(target_plugin_id, key, old_value, new_value)` |
| `unsubscribe(subscriber_id, target_plugin_id=None)` | 取消订阅，target_plugin_id 为 None 时取消所有订阅 |
| `publish(publisher_id, key, value, namespace)` | 发布数据变化 |
| `save_asset(plugin_id, filename, content)` | 保存资源文件（content 为 bytes） |
| `get_asset_path(relative_path)` | 获取资源绝对路径 |
| `load_asset(relative_path)` | 加载资源文件 |
| `get_plugin_assets_dir(plugin_id)` | 获取插件资源目录 | `str` |
| `clear_cache()` | 清除缓存，下次读取时重新从磁盘加载 |
| `load_data(force_reload=False)` | 从磁盘加载数据到缓存 |
| `save_data()` | 将当前缓存数据保存到磁盘 |
| `get_all_plugins()` | 获取所有插件信息 |
| `get_plugin_info(instance_id)` | 获取指定插件信息 |
| `reset_all_data()` | 重置所有数据（慎用！） |

### 7.5 ITaskManager（任务管理器接口）

**文件**: `core/interfaces/i_task_manager.py`

| 方法 | 说明 |
|------|------|
| `register_sync_task(plugin_id, name, func, callback, args, kwargs)` | 注册同步任务 |
| `register_async_task(plugin_id, name, func, callback, args, kwargs)` | 注册异步任务 |
| `register_scheduled_task(plugin_id, name, func, interval, callback, args, kwargs)` | 注册定时任务 |
| `register_scheduled_task_factory(plugin_id, func, callback)` | 注册定时任务工厂 |
| `restore_scheduled_tasks(plugin_id)` | 恢复定时任务 |
| `enable_scheduled_task(task_id)` | 启用定时任务 |
| `disable_scheduled_task(task_id)` | 禁用定时任务 |
| `unregister_scheduled_task(task_id)` | 注销定时任务 |
| `register_long_running_task(plugin_id, name, func, callback, stop_callback, status_callback, auto_restart, args, kwargs)` | 注册长期任务 |
| `register_long_running_task_factory(plugin_id, func, callback, stop_callback, status_callback, restore_callback)` | 注册长期任务工厂 |
| `restore_long_running_tasks(plugin_id)` | 恢复长期任务 |
| `stop_long_running_task(task_id, delete_from_storage)` | 停止长期任务 |
| `get_long_running_tasks(plugin_id)` | 获取长期任务列表 |
| `get_task(task_id)` | 获取任务 |
| `get_tasks_by_plugin(plugin_id)` | 获取插件所有任务 |
| `get_all_tasks()` | 获取所有任务 |
| `get_task_status(task_id)` | 获取任务状态 |
| `get_scheduled_tasks(plugin_id)` | 获取定时任务列表 |
| `cancel_task(task_id)` | 取消任务 |
| `clear_completed_tasks(plugin_id)` | 清理已完成任务 |
| `shutdown()` | 关闭任务管理器，释放所有资源 |

### 7.6 ILLMFacade（LLM 外观接口）

**文件**: `core/interfaces/i_llm_facade.py`

| 方法 | 说明 |
|------|------|
| `chat(messages, provider, model, temperature, max_tokens, **kwargs)` | 同步聊天 |
| `stream_chat(messages, provider, model, temperature, max_tokens, callback, **kwargs)` | 流式聊天（同步），`callback` 签名为 `(chunk: str, done: bool) -> None` |
| `embed(texts, provider, model, **kwargs)` | 文本嵌入 |
| `get_models(provider)` | 获取可用模型列表 |
| `get_provider(name)` | 获取 Provider 实例 |
| `get_all_providers()` | 获取所有 Provider |
| `get_cached_models(provider_name)` | 获取缓存模型 |
| `create_conversation(system_prompt, provider, model)` | 创建新对话 |
| `send_message(conv_id, content, images, temperature, max_tokens)` | 同步发送消息 |
| `stream_send_message(...)` | 流式发送消息 |
| `get_conversation(conv_id)` | 获取对话对象 |
| `list_conversations()` | 列出所有对话 |
| `delete_conversation(conv_id)` | 删除对话 |
| `get_tool_executor()` | 获取工具执行器 |
| `get_shared_tool_registry()` | 获取共享工具注册表 |
| `chat_with_tools(...)` | 带工具调用的对话 |
| `chat_with_tools_stream(...)` | 流式工具调用对话 |
| `get_available_providers()` | 获取可用 Provider 信息 |
| `get_usage_stats(conv_id)` | 获取用量统计 |
| `validate_provider(provider)` | 验证 Provider 配置 |
| `load_image_as_base64(path)` | 加载图片为 base64 |
| `get_raw_provider(provider)` | 获取底层 Provider 实例 |

### 7.7 PluginServices（插件服务封装）

**文件**: `core/interfaces/plugin_services.py`

详细文档：[接口层概述](../core/interfaces/overview.md)

`PluginServices` 是一个数据类（dataclass），将插件所需的核心服务聚合到一个对象中，通过依赖注入传递给插件。插件通过 `services.data_provider`、`services.task_manager` 等属性访问服务。

| 属性 | 类型 | 说明 |
|------|------|------|
| `data_provider` | `DataProvider` | 数据提供者实例（失败时为 `None`） |
| `task_manager` | `BackgroundTaskManager` | 后台任务管理器实例（失败时为 `None`） |
| `llm_facade` | `LLMPluginService` | LLM 服务实例 |
| `logger` | `ILogger` | 日志管理器实例（`LoggerManager` 实现） |
| `mcp_manager` | `MCPManager` | MCP 管理器实例（可能为 `None`） |
| `mcp_client` | `MCPClientManager` | MCP 客户端管理器实例（可能为 `None`） |

### 7.8 ILogger（日志接口）

**文件**: `utils/i_logger.py`（通过 `core/interfaces/__init__.py` 重导出）

详细文档：[ILogger 接口文档](../core/interfaces/ilogger.md)

| 方法 | 说明 |
|------|------|
| `debug(name, message)` | 记录调试日志 |
| `info(name, message)` | 记录信息日志 |
| `warning(name, message)` | 记录警告日志 |
| `error(name, message)` | 记录错误日志 |
| `critical(name, message)` | 记录严重错误日志 |

> 注意：ILogger 接口的所有方法均包含 `name` 参数（调用方模块名），与 LoggerManager 的日志方法保持一致。

---

## 8. 相关文档

- [文档索引](../README.md)
- [DataProvider 概述](../core/data-provider/overview.md)
- [DataProvider API 参考](../core/data-provider/api-reference.md)
- [后台任务概述](../core/background-task/overview.md)
- [后台任务 API 参考](../core/background-task/api-reference.md)
- [LLM Provider 概述](../core/llm-provider/overview.md)
- [LLM Provider API 参考](../core/llm-provider/api-reference.md)
- [插件系统概述](../core/plugin-system/overview.md)

---

*本文档由 Claude Code 自动生成*
