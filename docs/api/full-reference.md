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
from core.interfaces import ILogger, PluginServices
```

### 1.3 从 core.data.data_provider 导入

```python
# 数据层
from core.data.data_provider import DataProvider, DataNamespace, DataProviderError
```

### 1.4 从 core.llm 导入

```python
# LLM 提供者
from core.llm import get_llm_provider

# LLM 数据类型（也可从 core.interfaces 导入，推荐方式）
from core.llm import Message, ChatResponse, EmbeddingResponse, ModelInfo

# LLM 异常
from core.llm.exceptions import (
    LLMException, ConfigurationError, AuthenticationError, APIError,
    RateLimitError, InvalidRequestError, ModelNotSupportedError,
    ConnectionError, TimeoutError, StreamingError
)
```

---

## 2. 插件系统 API

### 2.1 PluginManager

**文件**: `core/plugin/manager.py`

| 方法 | 说明 | 返回值 |
|------|------|--------|
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
| `save_plugin_order(official, thirdparty)` | 保存插件顺序 | bool |
| `get_official_plugin_ids()` | 获取官方插件 UUID 列表 | List[str] |
| `get_thirdparty_plugin_ids()` | 获取第三方插件 UUID 列表 | List[str] |
| `get_plugin_api(plugin_id)` | 获取插件 API 信息 | Optional[Dict] |
| `get_all_apis()` | 获取所有 API | Dict |
| `unregister_plugin_api(plugin_id)` | 移除插件 API 注册 | None |
| `register_plugin_api(plugin_id, instance, descriptions)` | 注册插件 API | None |
| `get_api_description(plugin_id, method_name=None)` | 获取 API 结构化描述 | Dict |
| `call_plugin_method(caller_id, plugin_id, method_name, **kwargs)` | 跨插件调用 | Any |
| `get_all_function_tools()` | 获取 MCP 工具列表 | List[Dict] |

### 2.2 IPlugin

**文件**: `core/interfaces/i_plugin.py`（推荐导入路径）

| 属性/方法 | 类型 | 说明 |
|-----------|------|------|
| `plugin_name` | property (abstract) | 插件名称 |
| `plugin_id` | property | 插件 UUID |
| `skill_icon` | property | 技能按钮图标 |
| `skill_description` | property | 技能描述 |
| `skill_tooltip` | property | 工具提示 |
| `plugin_info` | property | 插件信息对象 |
| `_create_widget(parent, data_provider)` | method (abstract) | 创建 UI |
| `get_widget(parent, data_provider)` | method | 获取 Widget（带缓存） |
| `on_plugin_loaded()` | method | 加载完成回调 |

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
| `DataProvider(data_dir, filename)` | 获取单例实例 | DataProvider |
| `register_plugin(instance_id, type)` | 注册插件 | None |
| `unregister_plugin(instance_id)` | 注销插件 | None |
| `get_active_instance(type)` | 获取活跃实例 | Optional[str] |
| `set_active_instance(instance_id)` | 设置活跃实例 | None |
| `get_plugin_data(instance_id, key, namespace, default)` | 获取数据 | Any |
| `set_plugin_data(instance_id, key, value, namespace, notify)` | 设置数据，notify 默认 True，控制是否通知订阅者 | None |
| `get_all_plugin_data(instance_id, namespace)` | 获取所有数据 | Dict |
| `subscribe(subscriber, target, key, callback)` | 订阅数据 | None |
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

| 方法 | 说明 | 返回值 |
|------|------|--------|
| `BackgroundTaskManager()` | 获取单例实例 | BackgroundTaskManager |
| `register_sync_task(plugin_id, name, func, callback, args, kwargs)` | 注册同步任务 | str (task_id) |
| `register_async_task(plugin_id, name, func, callback, args, kwargs)` | 注册异步任务 | str (task_id) |
| `register_scheduled_task(plugin_id, name, func, interval, callback, args, kwargs)` | 注册定时任务 | str (task_id) |
| `register_scheduled_task_factory(plugin_id, func, callback)` | 注册任务工厂 | None |
| `restore_scheduled_tasks(plugin_id)` | 恢复定时任务 | int |
| `enable_scheduled_task(task_id)` | 启用定时任务 | bool |
| `disable_scheduled_task(task_id)` | 禁用定时任务 | bool |
| `unregister_scheduled_task(task_id)` | 注销定时任务 | bool |
| `register_long_running_task(plugin_id, name, func, callback, stop_callback, status_callback, auto_restart)` | 注册长期任务 | str (task_id) |
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
| `shutdown()` | 关闭任务管理器（不在 ITaskManager 接口中） | None |

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

> **注意**：`STOPPED` 状态仅存在于 `ITaskManager` 接口定义中，`TaskStatus` 枚举实际不包含此值。

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
| `remove_provider(name)` | 移除 Provider | None |
| `reload_config()` | 重新加载配置 | None |
| `close()` | 关闭连接 | None |
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
| `InvalidRequestError` | 无效请求 |
| `ModelNotSupportedError` | 模型不支持 |
| `ConnectionError` | 连接错误 |
| `TimeoutError` | 超时错误 |
| `StreamingError` | 流式输出错误 |

---

## 6. 常用代码片段

### 6.1 获取核心单例

```python
# 插件管理器
plugin_manager = PluginManager()

# 数据提供者
data_provider = DataProvider()

# 后台任务管理器
task_manager = BackgroundTaskManager()

# LLM 提供者
llm_provider = get_llm_provider()
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

# 发布
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
    param1="value1"
)
```

### 6.6 注册后台任务

```python
# 异步任务
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
| `subscribe(subscriber_id, target_plugin_id, target_key, callback)` | 订阅数据变化 |
| `unsubscribe(subscriber_id, target_plugin_id)` | 取消订阅 |
| `publish(publisher_id, key, value, namespace)` | 发布数据变化 |
| `save_asset(plugin_id, filename, content)` | 保存资源文件 |
| `get_asset_path(relative_path)` | 获取资源绝对路径 |
| `load_asset(relative_path)` | 加载资源文件 |
| `get_plugin_assets_dir(plugin_id)` | 获取插件资源目录 |
| `get_all_plugins()` | 获取所有插件信息 |
| `get_plugin_info(instance_id)` | 获取指定插件信息 |

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

> **注意**：`update_long_running_task_status(task_id, status)` 存在于 `BackgroundTaskManager` 实现中，但未在 `ITaskManager` 接口中声明。

### 7.6 ILLMFacade（LLM 外观接口）

**文件**: `core/interfaces/i_llm_facade.py`

| 方法 | 说明 |
|------|------|
| `chat(messages, provider, model, temperature, max_tokens, **kwargs)` | 同步聊天 |
| `stream_chat(messages, provider, model, temperature, max_tokens, callback, **kwargs)` | 流式聊天（同步） |
| `embed(texts, provider, model, **kwargs)` | 文本嵌入 |
| `get_models(provider)` | 获取可用模型列表 |
| `get_provider(name)` | 获取 Provider 实例 |
| `get_all_providers()` | 获取所有 Provider |
| `get_cached_models(provider_name)` | 获取缓存模型 |

### 7.7 PluginServices（插件服务封装）

**文件**: `core/interfaces/plugin_services.py`

详细文档：[接口层概述](../core/interfaces/overview.md)

`PluginServices` 是一个数据类（dataclass），将插件所需的核心服务聚合到一个对象中，通过依赖注入传递给插件。插件通过 `services.data_provider`、`services.task_manager` 等属性访问服务。

| 属性 | 类型 | 说明 |
|------|------|------|
| `data_provider` | `IDataProvider` | 数据提供者实例 |
| `task_manager` | `ITaskManager` | 后台任务管理器实例 |
| `llm_facade` | `ILLMFacade` | LLM 外观接口（可选） |
| `logger` | `ILogger` | 日志接口（可选） |

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
