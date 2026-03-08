# API 完整参考

> 所有核心类的完整 API 索引

---

## 1. 核心模块导入

### 1.1 从 core 导入

```python
# 插件系统
from core import PluginManager, IPlugin, IPluginInfo

# 数据层
from core import DataProvider, DataNamespace

# 后台任务
from core import BackgroundTaskManager, TaskType, TaskStatus, BackgroundTask, ScheduledTask
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
| `apply_custom_order()` | 应用自定义顺序 | None |
| `save_plugin_order(official, thirdparty)` | 保存插件顺序 | bool |
| `get_official_plugin_ids()` | 获取官方插件 UUID 列表 | List[str] |
| `get_thirdparty_plugin_ids()` | 获取第三方插件 UUID 列表 | List[str] |
| `get_plugin_api(plugin_id)` | 获取插件 API 信息 | Optional[Dict] |
| `get_all_apis()` | 获取所有 API | Dict |
| `call_plugin_method(caller, plugin, method, **kwargs)` | 跨插件调用 | Any |
| `get_all_function_tools()` | 获取 MCP 工具列表 | List[Dict] |

### 2.2 IPlugin

**文件**: `core/plugin/plugin_interface.py`

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

**文件**: `core/plugin/plugin_info_interface.py`

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
| `tags` | property | 标签列表 |

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
| `set_plugin_data(instance_id, key, value, namespace, notify)` | 设置数据 | None |
| `get_all_plugin_data(instance_id, namespace)` | 获取所有数据 | Dict |
| `subscribe(subscriber, target, key, callback)` | 订阅数据 | None |
| `unsubscribe(subscriber, target)` | 取消订阅 | None |
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
| `get_task(task_id)` | 获取任务 | Optional[BackgroundTask] |
| `get_tasks_by_plugin(plugin_id)` | 获取插件任务 | List[BackgroundTask] |
| `get_all_tasks()` | 获取所有任务 | List[BackgroundTask] |
| `get_task_status(task_id)` | 获取任务状态 | Optional[TaskStatus] |
| `get_scheduled_tasks(plugin_id)` | 获取定时任务 | List[ScheduledTask] |
| `cancel_task(task_id)` | 取消任务 | bool |
| `clear_completed_tasks(plugin_id)` | 清理已完成任务 | int |

### 4.2 TaskType

**文件**: `core/task/task_model.py`

| 枚举值 | 说明 |
|--------|------|
| `TaskType.SYNC` | 同步任务 |
| `TaskType.ASYNC` | 异步任务 |
| `TaskType.SCHEDULED` | 定时任务 |

### 4.3 TaskStatus

**文件**: `core/task/task_model.py`

| 枚举值 | 说明 |
|--------|------|
| `TaskStatus.PENDING` | 待执行 |
| `TaskStatus.RUNNING` | 执行中 |
| `TaskStatus.COMPLETED` | 已完成 |
| `TaskStatus.FAILED` | 执行失败 |
| `TaskStatus.CANCELLED` | 已取消 |

---

## 5. 常用代码片段

### 5.1 获取核心单例

```python
# 插件管理器
plugin_manager = PluginManager()

# 数据提供者
data_provider = DataProvider()

# 后台任务管理器
task_manager = BackgroundTaskManager()
```

### 5.2 创建插件 Widget

```python
# 获取插件
plugin = plugin_manager.get_plugin_by_id("plugin-uuid")

# 获取 Widget（带缓存）
widget = plugin.get_widget(parent=parent_widget, data_provider=data_provider)
```

### 5.3 数据操作

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

### 5.4 发布/订阅

```python
# 订阅
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

### 5.5 跨插件调用

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

### 5.6 注册后台任务

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

## 6. 相关文档

- [文档索引](../README.md)
- [DataProvider 概述](../core/data-provider/overview.md)
- [DataProvider API 参考](../core/data-provider/api-reference.md)
- [后台任务概述](../core/background-task/overview.md)
- [后台任务 API 参考](../core/background-task/api-reference.md)

---

*本文档由 Claude Code 自动生成*
