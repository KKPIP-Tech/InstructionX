# DataProvider 数据层详解

本文档详细介绍 InstructionX 的数据层核心组件 DataProvider，包括其架构设计、核心功能和使用方法。

---

## 1. 概述

**DataProvider** 是 InstructionX 的数据中枢，采用单例模式运行，负责应用数据的存储、缓存、跨插件通信和资源管理。

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DataProvider                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│  │   插件 A    │  │   插件 B    │  │   插件 C    │                │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │
│         │                │                │                         │
│         ▼                ▼                ▼                         │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                    数据访问层                            │       │
│  │  ┌───────────────┐  ┌───────────────┐  ┌─────────────┐  │       │
│  │  │ set_plugin_   │  │ get_plugin_   │  │ subscribe/ │  │       │
│  │  │ data()        │  │ data()        │  │ publish()  │  │       │
│  │  └───────┬───────┘  └───────┬───────┘  └──────┬──────┘  │       │
│  └──────────┼──────────────────┼─────────────────┼──────────┘       │
│             │                  │                 │                  │
│             ▼                  ▼                 ▼                  │
│  ┌─────────────────────────────────────────────────────────┐       │
│  │                   缓存层 (Memory Cache)                 │       │
│  │              _cache: Dict[namespace][key]               │       │
│  └──────────────────────────┬──────────────────────────────┘       │
│                             │                                       │
│             ┌───────────────┴───────────────┐                      │
│             ▼                               ▼                      │
│  ┌─────────────────────┐      ┌─────────────────────┐              │
│  │   持久化层          │      │   发布/订阅层        │              │
│  │   (data.json)      │      │   (_subscriptions)  │              │
│  └─────────────────────┘      └─────────────────────┘              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心特性

### 2.1 单例模式

DataProvider 采用线程安全的单例模式，确保全局唯一实例：

```python
class DataProvider:
    _instance: Optional['DataProvider'] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

**获取实例**：

```python
from core.data.data_provider import DataProvider

data_provider = DataProvider()  # 全局唯一实例
```

### 2.2 线程安全

- 使用 `threading.Lock` 保护并发访问
- 原子写入机制：先写临时文件，再重命名，避免数据损坏

### 2.3 内存缓存

- 所有数据操作先访问内存缓存
- 缓存与持久化文件保持同步
- 提高数据访问性能

### 2.4 命名空间隔离

| 命名空间 | 说明 | 访问权限 |
|----------|------|----------|
| `PRIVATE` | 私有数据 | 仅插件自身可读写 |
| `PUBLIC` | 公共数据 | 所有插件可读写 |

---

## 3. 核心 API

### 3.1 插件注册

#### `register_plugin(instance_id: str, plugin_type: str) -> None`

注册插件实例，建立插件与数据层的连接。

**参数**：
- `instance_id`: 插件唯一标识（通常使用 plugin_name）
- `plugin_type`: 插件类型 (`"official"` 或 `"custom"`)

**示例**：

```python
data_provider = DataProvider()
data_provider.register_plugin("color_converter", "custom")
```

---

### 3.2 数据存取

#### `set_plugin_data(instance_id: str, key: str, value: Any, namespace: str = "PRIVATE") -> None`

设置插件数据。

**参数**：
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `value`: 数据值（必须是 JSON 可序列化的类型）
- `namespace`: 命名空间 (`"PRIVATE"` 或 `"PUBLIC"`)

**示例**：

```python
# 保存私有配置（仅自身可访问）
data_provider.set_plugin_data(
    instance_id="my_plugin",
    key="settings",
    value={"theme": "dark", "language": "zh-CN"},
    namespace="PRIVATE"
)

# 保存公共数据（其他插件可访问）
data_provider.set_plugin_data(
    instance_id="task_manager",
    key="tasks",
    value=[{"title": "任务1", "done": False}],
    namespace="PUBLIC"
)
```

---

#### `get_plugin_data(instance_id: str, key: str, namespace: str = "PRIVATE") -> Any`

获取插件数据。

**参数**：
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `namespace`: 命名空间

**返回**：
- 数据值，不存在则返回 `None`

**示例**：

```python
# 读取私有配置
settings = data_provider.get_plugin_data(
    instance_id="my_plugin",
    key="settings",
    namespace="PRIVATE"
)

# 读取公共数据
tasks = data_provider.get_plugin_data(
    instance_id="task_manager",
    key="tasks",
    namespace="PUBLIC"
)
```

---

#### `get_all_plugin_data(instance_id: str, namespace: str = "PRIVATE") -> Dict`

获取插件的所有数据。

**参数**：
- `instance_id`: 插件实例 ID
- `namespace`: 命名空间

**返回**：
- `Dict[str, Any]`: 所有数据的字典

---

#### `delete_plugin_data(instance_id: str, key: str, namespace: str = "PRIVATE") -> bool`

删除指定数据。

**参数**：
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `namespace`: 命名空间

**返回**：
- `bool`: 是否删除成功

---

### 3.3 发布/订阅

#### `subscribe(subscriber_id: str, target_plugin_id: str, target_key: str, callback: Callable, namespace: str = "PUBLIC") -> None`

订阅数据变化。

**参数**：
- `subscriber_id`: 订阅者 ID（通常使用 plugin_name）
- `target_plugin_id`: 目标插件 ID
- `target_key`: 目标数据键
- `callback`: 回调函数，签名为 `callback(old_value, new_value)`
- `namespace`: 命名空间

**示例**：

```python
def on_tasks_changed(old_value, new_value):
    print(f"任务列表从 {len(old_value)} 个变为 {len(new_value)} 个")
    # 更新 UI 等操作

data_provider.subscribe(
    subscriber_id="task_reporter",
    target_plugin_id="task_manager",
    target_key="tasks",
    callback=on_tasks_changed,
    namespace="PUBLIC"
)
```

---

#### `unsubscribe(subscriber_id: str, target_plugin_id: str, target_key: str, namespace: str = "PUBLIC") -> None`

取消订阅。

**参数**：
- `subscriber_id`: 订阅者 ID
- `target_plugin_id`: 目标插件 ID
- `target_key`: 目标数据键
- `namespace`: 命名空间

---

#### `publish(publisher_id: str, key: str, value: Any, namespace: str = "PUBLIC") -> None`

发布数据更新，触发所有订阅者的回调。

**参数**：
- `publisher_id`: 发布者 ID
- `key`: 数据键
- `value`: 新数据值
- `namespace`: 命名空间

**示例**：

```python
# 发布任务更新
data_provider.publish(
    publisher_id="task_manager",
    key="tasks",
    value=[
        {"title": "任务1", "done": False},
        {"title": "任务2", "done": True}
    ],
    namespace="PUBLIC"
)
```

**执行流程**：

```
┌─────────────────────────────────────────────────────────────┐
│  publish() 调用                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 获取旧值                                                  │
│  2. 更新缓存                                                  │
│  3. 持久化到文件                                              │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  遍历所有订阅者                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 回调函数 A  │  │ 回调函数 B  │  │ 回调函数 C  │       │
│  │ (old, new)  │  │ (old, new)  │  │ (old, new)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.4 资源管理

#### `save_asset(plugin_id: str, asset_name: str, data: bytes) -> str`

保存资源文件（如图片、配置文件等）。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名
- `data`: 二进制数据

**返回**：
- `str`: 保存的文件路径

**示例**：

```python
# 保存图片
with open("image.png", "rb") as f:
    image_data = f.read()

file_path = data_provider.save_asset(
    plugin_id="my_plugin",
    asset_name="image.png",
    data=image_data
)
# file_path = "data/assets/my_plugin/image.png"
```

---

#### `load_asset(plugin_id: str, asset_name: str) -> Optional[bytes]`

加载资源文件。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名

**返回**：
- `Optional[bytes]`: 二进制数据，不存在则返回 `None`

---

#### `delete_asset(plugin_id: str, asset_name: str) -> bool`

删除资源文件。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名

**返回**：
- `bool`: 是否删除成功

---

#### `list_assets(plugin_id: str) -> List[str]`

列出插件的所有资源文件。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `List[str]`: 资源文件名列表

---

### 3.5 工具方法

#### `get_all_subscriptions(subscriber_id: str) -> List[Dict]`

获取订阅者的所有订阅信息。

**参数**：
- `subscriber_id`: 订阅者 ID

**返回**：
- `List[Dict]`: 订阅信息列表

---

#### `clear_cache() -> None`

清空内存缓存（谨慎使用）。

---

#### `reload_from_disk() -> None`

从磁盘重新加载数据。

---

## 4. 数据结构

### 4.1 内存缓存结构

```python
_cache = {
    "PRIVATE": {
        "plugin_a": {
            "key1": value1,
            "key2": value2
        },
        "plugin_b": {...}
    },
    "PUBLIC": {
        "plugin_a": {...},
        "plugin_b": {...}
    }
}
```

### 4.2 订阅结构

```python
_subscriptions = {
    ("PUBLIC", "task_manager", "tasks"): [
        {
            "subscriber_id": "task_reporter",
            "callback": callback_function
        },
        {
            "subscriber_id": "another_plugin",
            "callback": another_callback
        }
    ]
}
```

### 4.3 持久化文件结构 (data.json)

```json
{
  "PRIVATE": {
    "plugin_a": {
      "settings": {"theme": "dark"}
    }
  },
  "PUBLIC": {
    "task_manager": {
      "tasks": [
        {"title": "任务1", "done": false}
      ]
    }
  }
}
```

---

## 5. 使用模式

### 5.1 典型插件初始化

```python
from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider

class MyPlugin(IPlugin):
    def __init__(self):
        self._cached_widget = None
        self._data_provider = DataProvider()
        # 注册插件
        self._data_provider.register_plugin("my_plugin", "custom")

    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        # ... 创建 UI
        return widget
```

### 5.2 发布/订阅模式

```
┌─────────────────────────────────────────────────────────────────┐
│                      插件协作场景                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────┐            ┌──────────────┐                 │
│   │ TaskManager  │            │TaskReporter  │                 │
│   │  (发布者)    │            │  (订阅者)    │                 │
│   └──────┬───────┘            └──────┬───────┘                 │
│          │                           │                          │
│          │ publish("tasks", [...])   │                          │
│          │──────────────────────────►│                          │
│          │                           │                          │
│          │                           │ on_tasks_changed()       │
│          │                           │ ◄─ 回调触发               │
│          │                           │                          │
└──────────┴───────────────────────────┴──────────────────────────┘
```

**TaskManager 插件（发布者）**：

```python
def add_task(self, title):
    tasks = self._data_provider.get_plugin_data(
        "task_manager", "tasks", "PUBLIC"
    ) or []
    tasks.append({"title": title, "done": False})

    # 发布更新，触发订阅者回调
    self._data_provider.publish(
        publisher_id="task_manager",
        key="tasks",
        value=tasks,
        namespace="PUBLIC"
    )
```

**TaskReporter 插件（订阅者）**：

```python
def _create_widget(self, parent=None, data_provider=None):
    # ... 创建 UI

    # 订阅任务变化
    self._data_provider.subscribe(
        subscriber_id="task_reporter",
        target_plugin_id="task_manager",
        target_key="tasks",
        callback=self.on_tasks_changed,
        namespace="PUBLIC"
    )

    return widget

def on_tasks_changed(self, old_value, new_value):
    # 生成任务报告
    self.generate_report(new_value)
```

---

### 5.3 数据隔离示例

```python
# 插件 A 的私有数据
data_provider.set_plugin_data("plugin_a", "config", {"key": "value"}, "PRIVATE")

# 插件 B 无法访问插件 A 的私有数据
data_provider.get_plugin_data("plugin_a", "config", "PRIVATE")  # 返回 None

# 插件 B 可以访问插件 A 的公共数据
data_provider.set_plugin_data("plugin_a", "shared_data", "hello", "PUBLIC")
data_provider.get_plugin_data("plugin_a", "shared_data", "PUBLIC")  # 返回 "hello"
```

---

## 6. 最佳实践

### 6.1 数据命名规范

```python
# 推荐：使用有意义的键名
data_provider.set_plugin_data("my_plugin", "user_preferences", {...}, "PRIVATE")
data_provider.set_plugin_data("task_manager", "tasks", [...], "PUBLIC")

# 避免：过于简单的键名
data_provider.set_plugin_data("my_plugin", "data", {...}, "PRIVATE")  # 不推荐
```

### 6.2 订阅管理

```python
class MyPlugin(IPlugin):
    def __init__(self):
        # ...
        self._subscriptions = []

    def _create_widget(self, parent=None, data_provider=None):
        # 订阅数据变化
        sub_id = self._data_provider.subscribe(
            subscriber_id="my_plugin",
            target_plugin_id="other_plugin",
            target_key="data",
            callback=self.on_data_changed,
            namespace="PUBLIC"
        )
        self._subscriptions.append(sub_id)

    def cleanup(self):
        # 插件销毁时取消订阅
        for sub in self._subscriptions:
            self._data_provider.unsubscribe(...)
```

### 6.3 错误处理

```python
def save_data(self):
    try:
        self._data_provider.set_plugin_data(
            "my_plugin", "data", self.data, "PRIVATE"
        )
    except Exception as e:
        print(f"保存数据失败: {e}")
```

---

## 7. 注意事项

1. **线程安全**：所有 DataProvider 方法都是线程安全的，但 UI 更新必须在主线程进行
2. **数据序列化**：存储的值必须是 JSON 可序列化的（dict、list、str、int、float、bool、None）
3. **命名空间选择**：
   - 使用 `PRIVATE` 存储插件私有配置
   - 使用 `PUBLIC` 存储需要跨插件共享的数据
4. **发布频率**：频繁发布可能导致性能问题，建议批量更新
5. **订阅清理**：插件销毁时记得取消订阅，避免内存泄漏

---

## 8. API 速查表

| 方法 | 说明 |
|------|------|
| `register_plugin()` | 注册插件实例 |
| `set_plugin_data()` | 设置数据 |
| `get_plugin_data()` | 获取数据 |
| `get_all_plugin_data()` | 获取所有数据 |
| `delete_plugin_data()` | 删除数据 |
| `subscribe()` | 订阅数据变化 |
| `unsubscribe()` | 取消订阅 |
| `publish()` | 发布数据更新 |
| `save_asset()` | 保存资源文件 |
| `load_asset()` | 加载资源文件 |
| `delete_asset()` | 删除资源文件 |
| `list_assets()` | 列出资源文件 |
