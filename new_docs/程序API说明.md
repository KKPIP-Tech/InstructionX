# InstructionX 程序 API 说明

本文档详细介绍 InstructionX 核心框架提供的编程接口，包括插件接口、插件管理器 API 和数据提供者 API。

---

## 1. IPlugin 接口

`IPlugin` 是插件必须实现的抽象基类，定义在 [core/plugin/plugin_interface.py](core/plugin/plugin_interface.py)。

### 1.1 核心属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `plugin_name` | `str` | 插件名称，必须唯一 |

### 1.2 核心方法

#### `_create_widget(parent=None, data_provider=None) -> QWidget`

创建并返回插件的 UI 控件。

**参数**：
- `parent`: 父控件，默认为 None
- `data_provider`: DataProvider 实例，用于数据存取

**返回**：
- `QWidget`: 插件的 UI 控件

**示例**：

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from core.plugin.plugin_interface import IPlugin

class MyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "我的插件"

    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        layout = QVBoxLayout()
        layout.addWidget(QLabel("这是我的插件内容"))
        widget.setLayout(layout)
        return widget
```

#### `get_widget(parent=None, data_provider=None) -> QWidget`

获取插件控件（带缓存机制）。

**说明**：该方法内部会检查缓存，如果插件控件已创建且父控件相同，直接返回缓存的控件，避免重复创建。

---

## 2. IPluginInfo 接口

`IPluginInfo` 是插件元数据接口，定义在 [core/plugin/plugin_info_interface.py](core/plugin/plugin_info_interface.py)。

### 2.1 核心属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `version` | `PluginVersion` | 插件版本号 |
| `developer` | `str` | 开发者名称 |
| `description` | `str` | 插件详细描述 |
| `service_api` | `Dict` | 插件提供的 API 定义 |
| `skill_icon` | `PluginIcon` | 技能面板显示的图标 |
| `skill_description` | `str` | 技能面板显示的描述 |

### 2.2 版本号定义 (PluginVersion)

```python
from core.plugin.plugin_version import PluginVersion

version = PluginVersion(major=1, minor=0, patch=0)
```

### 2.3 图标定义 (PluginIcon)

```python
from core.plugin.plugin_icon import PluginIcon

# 从文件加载图标
icon = PluginIcon.from_file(":/icons/my_plugin.png")

# 从资源名称加载
icon = PluginIcon.from_resource("my_plugin_icon")
```

### 2.4 API 定义示例

```python
# information.py
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class MyPluginInfo(IPluginInfo):
    @property
    def version(self) -> PluginVersion:
        return PluginVersion(major=1, minor=0, patch=0)

    @property
    def developer(self) -> str:
        return "开发者名称"

    @property
    def description(self) -> str:
        return "这是一个示例插件"

    @property
    def service_api(self) -> Dict:
        return {
            "methods": {
                "do_something": {
                    "description": "执行某个操作",
                    "parameters": {
                        "param1": {"type": "string", "required": True}
                    }
                }
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.from_resource("my_plugin_icon")

    @property
    def skill_description(self) -> str:
        return "插件简短描述"
```

---

## 3. PluginManager API

`PluginManager` 是插件管理系统单例，定义在 [core/plugin/manager.py](core/plugin/manager.py)。

### 3.1 获取实例

```python
from core.plugin.manager import PluginManager

manager = PluginManager()
```

### 3.2 核心方法

#### `load_plugins() -> None`

扫描并加载所有插件。

```python
manager.load_plugins()
```

**加载流程**：
1. 扫描 `plugin/` 目录（官方插件）
2. 扫描 `custom_plugin/` 目录（第三方插件）
3. 动态导入每个插件的 `entrance.py`
4. 实例化 IPlugin 子类
5. 自动注册 API（如果定义了 service_api）

---

#### `get_all_plugins() -> List[IPlugin]`

获取所有已加载的插件。

**返回**：
- `List[IPlugin]`: 插件列表

```python
all_plugins = manager.get_all_plugins()
for plugin in all_plugins:
    print(plugin.plugin_name)
```

---

#### `get_official_plugins() -> List[IPlugin]`

获取官方插件列表。

**返回**：
- `List[IPlugin]`: 官方插件列表

---

#### `get_thirdparty_plugins() -> List[IPlugin]`

获取第三方插件列表。

**返回**：
- `List[IPlugin]`: 第三方插件列表

---

#### `call_plugin_method(caller_id: str, plugin_id: str, method_name: str, **kwargs) -> Any`

跨插件方法调用。

**参数**：
- `caller_id`: 调用者插件 ID
- `plugin_id`: 目标插件 ID
- `method_name`: 方法名
- `**kwargs`: 方法参数

**返回**：
- `Any`: 方法返回值

**示例**：

```python
# 从 string_tools 插件调用 format_uppercase 方法
result = manager.call_plugin_method(
    caller_id="my_plugin",
    plugin_id="string_tools",
    method_name="format_uppercase",
    text="hello world"
)
# result = "HELLO WORLD"
```

---

#### `get_plugin_api(plugin_id: str) -> Optional[Dict]`

获取指定插件的 API 定义。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `Optional[Dict]`: API 定义字典，不存在则返回 None

```python
api = manager.get_plugin_api("string_tools")
print(api)
# {'methods': {'format_uppercase': {...}, 'format_lowercase': {...}, ...}}
```

---

#### `get_all_apis() -> Dict[str, Dict]`

获取所有插件的 API 定义。

**返回**：
- `Dict[str, Dict]`: 所有插件的 API 定义

```python
all_apis = manager.get_all_apis()
for plugin_id, api in all_apis.items():
    print(f"{plugin_id}: {list(api.get('methods', {}).keys())}")
```

---

#### `get_api_description(plugin_id: str, method_name: str) -> Optional[str]`

获取指定 API 方法的描述。

**参数**：
- `plugin_id`: 插件 ID
- `method_name`: 方法名

**返回**：
- `Optional[str]`: 方法描述

---

#### `set_plugin_order(plugin_ids: List[str]) -> None`

设置插件加载顺序。

**参数**：
- `plugin_ids`: 插件 ID 列表

```python
manager.set_plugin_order(["text_formatting", "code_formatter", "string_tools"])
```

---

#### `get_plugin_order() -> List[str]`

获取当前插件加载顺序。

**返回**：
- `List[str]`: 插件 ID 列表

---

## 4. DataProvider API

`DataProvider` 是应用的数据中枢单例，定义在 [core/data/data_provider.py](core/data/data_provider.py)。

### 4.1 获取实例

```python
from core.data.data_provider import DataProvider

data_provider = DataProvider()
```

### 4.2 核心方法

#### `register_plugin(instance_id: str, plugin_type: str) -> None`

注册插件实例。

**参数**：
- `instance_id`: 插件实例 ID（通常使用 plugin_name）
- `plugin_type`: 插件类型

```python
data_provider.register_plugin("my_plugin", "custom")
```

---

#### `set_plugin_data(instance_id: str, key: str, value: Any, namespace: str = "PRIVATE") -> None`

设置插件数据。

**参数**：
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `value`: 数据值
- `namespace`: 命名空间 ("PRIVATE" 或 "PUBLIC")

**示例**：

```python
# 私有数据（仅插件自身可访问）
data_provider.set_plugin_data(
    instance_id="my_plugin",
    key="settings",
    value={"theme": "dark"},
    namespace="PRIVATE"
)

# 公共数据（其他插件可访问）
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
- `Any`: 数据值

**示例**：

```python
tasks = data_provider.get_plugin_data(
    instance_id="task_manager",
    key="tasks",
    namespace="PUBLIC"
)
```

---

#### `subscribe(subscriber_id: str, target_plugin_id: str, target_key: str, callback: Callable, namespace: str = "PUBLIC") -> None`

订阅数据变化。

**参数**：
- `subscriber_id`: 订阅者 ID
- `target_plugin_id`: 目标插件 ID
- `target_key`: 目标数据键
- `callback`: 回调函数 `callback(old_value, new_value)`
- `namespace`: 命名空间

**示例**：

```python
def on_tasks_changed(old_value, new_value):
    print(f"任务列表变化: {old_value} -> {new_value}")

data_provider.subscribe(
    subscriber_id="task_reporter",
    target_plugin_id="task_manager",
    target_key="tasks",
    callback=on_tasks_changed,
    namespace="PUBLIC"
)
```

---

#### `publish(publisher_id: str, value: Any, key: str, namespace: str = "PUBLIC") -> None`

发布数据更新。

**参数**：
- `publisher_id`: 发布者 ID
- `key`: 数据键
- `value`: 新数据值
- `namespace`: 命名空间

**示例**：

```python
data_provider.publish(
    publisher_id="task_manager",
    key="tasks",
    value=[{"title": "新任务", "done": False}],
    namespace="PUBLIC"
)
```

---

#### `save_asset(plugin_id: str, asset_name: str, data: bytes) -> str`

保存资源文件。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名
- `data`: 二进制数据

**返回**：
- `str`: 资源文件路径

```python
# 保存图片
with open("image.png", "rb") as f:
    image_data = f.read()

file_path = data_provider.save_asset("my_plugin", "image.png", image_data)
```

---

#### `load_asset(plugin_id: str, asset_name: str) -> Optional[bytes]`

加载资源文件。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名

**返回**：
- `Optional[bytes]`: 二进制数据，不存在则返回 None

```python
image_data = data_provider.load_asset("my_plugin", "image.png")
```

---

#### `delete_asset(plugin_id: str, asset_name: str) -> bool`

删除资源文件。

**参数**：
- `plugin_id`: 插件 ID
- `asset_name`: 资源文件名

**返回**：
- `bool`: 是否删除成功

---

### 4.3 命名空间说明

| 命名空间 | 说明 | 访问权限 |
|----------|------|----------|
| `PRIVATE` | 私有数据 | 仅插件自身 |
| `PUBLIC` | 公共数据 | 所有插件可读写 |

---

## 5. 使用示例

### 5.1 在插件中使用 DataProvider

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from core.plugin.plugin_interface import IPlugin
from core.data.data_provider import DataProvider

class TaskManagerPlugin(IPlugin):
    def __init__(self):
        self._cached_widget = None
        self._data_provider = DataProvider()
        self._data_provider.register_plugin("task_manager", "official")

    @property
    def plugin_name(self) -> str:
        return "task_manager"

    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        layout = QVBoxLayout()

        # 显示任务列表
        self.task_label = QLabel("暂无任务")
        layout.addWidget(self.task_label)

        # 添加任务按钮
        add_btn = QPushButton("添加任务")
        add_btn.clicked.connect(self.add_task)
        layout.addWidget(add_btn)

        widget.setLayout(layout)

        # 订阅数据变化
        self._data_provider.subscribe(
            subscriber_id="task_manager",
            target_plugin_id="task_manager",
            target_key="tasks",
            callback=self.on_tasks_changed,
            namespace="PUBLIC"
        )

        return widget

    def add_task(self):
        tasks = self._data_provider.get_plugin_data(
            "task_manager", "tasks", "PUBLIC"
        ) or []
        tasks.append({"title": "新任务", "done": False})
        self._data_provider.publish(
            publisher_id="task_manager",
            key="tasks",
            value=tasks,
            namespace="PUBLIC"
        )

    def on_tasks_changed(self, old_value, new_value):
        self.task_label.setText(f"任务数量: {len(new_value)}")
```

### 5.2 跨插件调用

```python
# 在一个插件中调用另一个插件的 API
from core.plugin.manager import PluginManager

manager = PluginManager()

# 调用 string_tools 插件的大写格式化方法
result = manager.call_plugin_method(
    caller_id="my_plugin",
    plugin_id="string_tools",
    method_name="format_uppercase",
    text="hello world"
)
print(result)  # 输出: HELLO WORLD
```

---

## 6. API 快速参考

### PluginManager 方法速查

| 方法 | 说明 |
|------|------|
| `load_plugins()` | 加载所有插件 |
| `get_all_plugins()` | 获取所有插件 |
| `get_official_plugins()` | 获取官方插件 |
| `get_thirdparty_plugins()` | 获取第三方插件 |
| `call_plugin_method()` | 跨插件调用 |
| `get_plugin_api()` | 获取插件 API |
| `get_all_apis()` | 获取所有 API |
| `set_plugin_order()` | 设置插件顺序 |

### DataProvider 方法速查

| 方法 | 说明 |
|------|------|
| `register_plugin()` | 注册插件 |
| `set_plugin_data()` | 设置数据 |
| `get_plugin_data()` | 获取数据 |
| `subscribe()` | 订阅变化 |
| `publish()` | 发布更新 |
| `save_asset()` | 保存资源 |
| `load_asset()` | 加载资源 |
| `delete_asset()` | 删除资源 |
