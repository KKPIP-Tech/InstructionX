# PluginManager 插件管理器详解

本文档详细介绍 InstructionX 的插件管理系统核心组件 PluginManager，包括其架构设计、核心功能和使用方法。

---

## 1. 概述

**PluginManager** 是 InstructionX 的插件管理系统核心，采用单例模式运行，负责插件的加载、排序、API 注册和跨插件调用。

```
┌─────────────────────────────────────────────────────────────────────┐
│                        PluginManager                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     插件加载层                                │   │
│  │  ┌─────────────────┐        ┌─────────────────┐          │   │
│  │  │ plugin/         │        │ custom_plugin/  │          │   │
│  │  │ (官方插件)      │        │ (第三方插件)     │          │   │
│  │  └────────┬────────┘        └────────┬────────┘          │   │
│  │           │                           │                    │   │
│  │           ▼                           ▼                    │   │
│  │  ┌─────────────────────────────────────────────┐          │   │
│  │  │         动态导入 (importlib)                │          │   │
│  │  │    - entrance.py 加载                       │          │   │
│  │  │    - IPlugin 子类发现                       │          │   │
│  │  │    - 实例化插件                             │          │   │
│  │  └──────────────────────┬──────────────────────┘          │   │
│  └─────────────────────────┼───────────────────────────────────┘   │
│                            │                                        │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     插件注册层                                │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐  │   │
│  │  │_official_     │  │_thirdparty_   │  │_plugin_       │  │   │
│  │  │plugins[]      │  │plugins[]      │  │registry{}     │  │   │
│  │  └───────────────┘  └───────────────┘  └───────────────┘  │   │
│  └─────────────────────────┬───────────────────────────────────┘   │
│                            │                                        │
│                            ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │                     API 注册层                               │   │
│  │  ┌───────────────────────────────────────────────┐          │   │
│  │  │              _api_registry{}                  │          │   │
│  │  │   {plugin_id: {methods: {...}, service: ...}} │          │   │
│  │  └───────────────────────────────────────────────┘          │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心特性

### 2.1 单例模式

PluginManager 采用单例模式，确保全局唯一实例：

```python
class PluginManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**获取实例**：

```python
from core.plugin.manager import PluginManager

manager = PluginManager()  # 全局唯一实例
```

### 2.2 插件分类管理

- **官方插件** (`plugin/`): 由官方开发和维护
- **第三方插件** (`custom_plugin/`): 由社区开发者提供

### 2.3 插件唯一性保障

使用 UUID 机制确保插件唯一性：
- 首次加载时生成 UUID 并保存
- 后续加载读取已有 UUID
- 插件重命名/移动后仍可识别

---

## 3. 核心 API

### 3.1 插件加载

#### `load_plugins() -> None`

扫描并加载所有插件。

**加载流程**：

```
┌─────────────────────────────────────────────────────────────┐
│  load_plugins() 调用                                         │
└──────────────────────────┬──────────────────────────────────┘
                           │
           ┌───────────────┴───────────────┐
           ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│  扫描 plugin/      │         │ 扫描 custom_plugin/│
│  (官方插件)        │         │ (第三方插件)        │
└─────────┬───────────┘         └─────────┬───────────┘
          │                               │
          ▼                               ▼
┌─────────────────────────────────────────────────────────────┐
│  _load_plugin_from_directory(plugin_dir)                  │
│  ├── 检查 entrance.py 存在                                 │
│  ├── 动态 import entrance.py                               │
│  ├── 查找 IPlugin 子类                                     │
│  ├── 实例化插件                                             │
│  ├── 生成/加载 UUID                                        │
│  ├── 注册到管理器                                           │
│  └── 自动注册 API (如有)                                    │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  加载完成，插件可使用                                        │
└─────────────────────────────────────────────────────────────┘
```

**示例**：

```python
manager = PluginManager()
manager.load_plugins()
print(f"已加载 {len(manager.get_all_plugins())} 个插件")
```

---

#### `reload_plugin(plugin_id: str) -> bool`

重新加载指定插件。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `bool`: 是否重新加载成功

---

### 3.2 插件获取

#### `get_all_plugins() -> List[IPlugin]`

获取所有已加载的插件。

**返回**：
- `List[IPlugin]`: 插件列表

**示例**：

```python
all_plugins = manager.get_all_plugins()
for plugin in all_plugins:
    print(f"{plugin.plugin_id}: {plugin.plugin_name}")
```

---

#### `get_o List[IPlugin]fficial_plugins() ->`

获取官方插件列表。

**返回**：
- `List[IPlugin]`: 官方插件列表

---

#### `get_thirdparty_plugins() -> List[IPlugin]`

获取第三方插件列表。

**返回**：
- `List[IPlugin]`: 第三方插件列表

---

#### `get_plugin(plugin_id: str) -> Optional[IPlugin]`

根据插件 ID 获取插件实例。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `Optional[IPlugin]`: 插件实例，不存在则返回 None

---

### 3.3 插件排序

#### `set_plugin_order(plugin_ids: List[str]) -> None`

设置插件加载/显示顺序。

**参数**：
- `plugin_ids`: 插件 ID 列表

**示例**：

```python
manager.set_plugin_order([
    "text_formatting",
    "code_formatter",
    "string_tools",
    "task_manager"
])
```

**保存位置**: `config/plugin_order.json`

---

#### `get_plugin_order() -> List[str]`

获取当前插件顺序。

**返回**：
- `List[str]`: 插件 ID 列表

---

### 3.4 API 管理

#### `get_plugin_api(plugin_id: str) -> Optional[Dict]`

获取指定插件的 API 定义。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `Optional[Dict]`: API 定义字典，包含 `methods` 和 `service`

**示例**：

```python
api = manager.get_plugin_api("string_tools")
print(api)
# 输出:
# {
#     "methods": {
#         "format_uppercase": {...},
#         "format_lowercase": {...},
#         ...
#     },
#     "service": <Service class>
# }
```

---

#### `get_all_apis() -> Dict[str, Dict]`

获取所有插件的 API 定义。

**返回**：
- `Dict[str, Dict]`: 所有插件的 API 定义

---

#### `get_api_description(plugin_id: str, method_name: str) -> Optional[str]`

获取指定 API 方法的描述。

**参数**：
- `plugin_id`: 插件 ID
- `method_name`: 方法名

**返回**：
- `Optional[str]`: 方法描述

---

### 3.5 跨插件调用

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
# 调用 string_tools 插件的大写格式化方法
result = manager.call_plugin_method(
    caller_id="my_plugin",
    plugin_id="string_tools",
    method_name="format_uppercase",
    text="hello world"
)
# result = "HELLO WORLD"

# 调用带多个参数的方法
result = manager.call_plugin_method(
    caller_id="my_plugin",
    plugin_id="color_converter",
    method_name="convert_rgb_to_hex",
    r=255, g=87, b=51
)
# result = "#FF5733"
```

**调用流程**：

```
┌─────────────────────────────────────────────────────────────┐
│  call_plugin_method() 调用                                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  1. 查找目标插件                                             │
│  2. 查找 Service 实例                                       │
│  3. 获取方法                                                 │
│  4. 调用方法                                                 │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  返回结果                                                    │
└─────────────────────────────────────────────────────────────┘
```

---

### 3.6 插件信息

#### `get_plugin_info(plugin_id: str) -> Optional[IPluginInfo]`

获取插件元数据信息。

**参数**：
- `plugin_id`: 插件 ID

**返回**：
- `Optional[IPluginInfo]`: 插件元数据

---

#### `get_plugin_id(plugin_name: str) -> Optional[str]`

根据插件名称获取插件 ID。

**参数**：
- `plugin_name`: 插件名称

**返回**：
- `Optional[str]`: 插件 ID

---

## 4. 数据结构

### 4.1 插件注册表

```python
_plugin_registry = {
    "string_tools_001": <StringToolsPlugin instance>,
    "task_manager_002": <TaskManagerPlugin instance>,
    "color_converter_003": <ColorConverterPlugin instance>
}
```

### 4.2 API 注册表

```python
_api_registry = {
    "string_tools": {
        "methods": {
            "format_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {"type": "string", "required": True}
                }
            },
            "format_lowercase": {...}
        },
        "service": <StringToolsService instance>
    },
    "color_converter": {...}
}
```

### 4.3 插件分类

```python
_official_plugins = [<TextFormattingPlugin>, <CodeFormatterPlugin>, ...]
_thirdparty_plugins = [<ColorConverterPlugin>, <UnitConverterPlugin>, ...]
```

---

## 5. 使用模式

### 5.1 初始化插件系统

```python
# main.py 或应用初始化时
from core.plugin.manager import PluginManager

manager = PluginManager()
manager.load_plugins()

# 之后可以获取插件列表
plugins = manager.get_all_plugins()
print(f"已加载 {len(plugins)} 个插件")
```

### 5.2 跨插件调用场景

```
┌─────────────────────────────────────────────────────────────────┐
│                      跨插件调用场景                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────────┐         ┌──────────────────┐           │
│   │   API Demo       │         │   String Tools   │
│   │  (调用者)        │         │   (提供者)        │
│   └────────┬─────────┘         └────────┬─────────┘           │
│            │                             │                     │
│            │ call_plugin_method(        │                     │
│            │   caller_id="api_demo",    │                     │
│            │   plugin_id="string_tools",│                     │
│            │   method_name="format_     │                     │
│            │     uppercase",            │                     │
│            │   text="hello"             │                     │
│            │ )                          │                     │
│            │───────────────────────────►│                     │
│            │                             │                     │
│            │        返回 "HELLO"        │                     │
│            │◄───────────────────────────│                     │
│            │                             │                     │
└────────────┴─────────────────────────────┴──────────────────────┘
```

### 5.3 API 调用示例

**调用方插件 (api_demo)**：

```python
class ApiDemoPlugin(IPlugin):
    def _create_widget(self, parent=None, data_provider=None):
        widget = QWidget(parent)
        layout = QVBoxLayout()

        # 调用其他插件的 API
        result = PluginManager().call_plugin_method(
            caller_id="api_demo",
            plugin_id="string_tools",
            method_name="format_uppercase",
            text="hello world"
        )

        layout.addWidget(QLabel(f"结果: {result}"))
        widget.setLayout(layout)
        return widget
```

---

## 6. API 自动注册机制

### 6.1 注册流程

```
┌─────────────────────────────────────────────────────────────┐
│                 API 自动注册流程                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 加载插件                                                 │
│         │                                                    │
│         ▼                                                    │
│  2. 检查 information.py 是否存在                            │
│         │                                                    │
│         ├── 不存在 ──► 跳过 API 注册                         │
│         │                                                    │
│         ▼                                                    │
│  3. 检查 service_api 定义                                   │
│         │                                                    │
│         ├── 不存在 ──► 跳过 API 注册                         │
│         │                                                    │
│         ▼                                                    │
│  4. 导入 service.py 的 Service 类                          │
│         │                                                    │
│         ▼                                                    │
│  5. 实例化 Service                                          │
│         │                                                    │
│         ▼                                                    │
│  6. 注册到 _api_registry                                    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 API 定义示例

**information.py**：

```python
class MyPluginInfo(IPluginInfo):
    @property
    def service_api(self) -> Dict:
        return {
            "methods": {
                "do_something": {
                    "description": "执行某个操作",
                    "parameters": {
                        "param1": {"type": "string", "required": True},
                        "param2": {"type": "integer", "required": False}
                    }
                },
                "calculate": {
                    "description": "执行计算",
                    "parameters": {
                        "a": {"type": "number", "required": True},
                        "b": {"type": "number", "required": True}
                    }
                }
            }
        }
```

**service.py**：

```python
class Service:
    def do_something(self, param1: str, param2: int = 0) -> str:
        return f"{param1} - {param2}"

    def calculate(self, a: float, b: float) -> float:
        return a + b
```

---

## 7. 最佳实践

### 7.1 插件开发建议

```python
# 1. 在插件初始化时确保插件已加载
def some_function():
    manager = PluginManager()
    if not manager.get_all_plugins():
        manager.load_plugins()

# 2. 使用 plugin_id 而非 plugin_name
plugin = manager.get_plugin("string_tools_001")  # 推荐

# 3. 调用 API 时处理异常
try:
    result = manager.call_plugin_method(
        caller_id="my_plugin",
        plugin_id="target_plugin",
        method_name="some_method",
        param="value"
    )
except Exception as e:
    print(f"API 调用失败: {e}")
```

### 7.2 错误处理

```python
# 检查插件是否存在
plugin = manager.get_plugin("string_tools")
if plugin is None:
    print("插件不存在")
    return

# 检查 API 是否存在
api = manager.get_plugin_api("string_tools")
if api and "format_uppercase" in api.get("methods", {}):
    # 调用 API
    result = manager.call_plugin_method(...)
else:
    print("API 不存在")
```

---

## 8. 注意事项

1. **加载时机**：PluginManager 在应用启动时自动加载插件
2. **线程安全**：PluginManager 方法应在主线程调用
3. **插件依赖**：确保被调用的插件已加载
4. **API 版本**：API 定义应保持稳定，升级时注意兼容性
5. **插件卸载**：目前不支持动态卸载插件，需重启应用

---

## 9. API 速查表

| 方法 | 说明 |
|------|------|
| `load_plugins()` | 加载所有插件 |
| `reload_plugin()` | 重新加载指定插件 |
| `get_all_plugins()` | 获取所有插件 |
| `get_official_plugins()` | 获取官方插件 |
| `get_thirdparty_plugins()` | 获取第三方插件 |
| `get_plugin()` | 获取指定插件 |
| `set_plugin_order()` | 设置插件顺序 |
| `get_plugin_order()` | 获取插件顺序 |
| `get_plugin_api()` | 获取插件 API |
| `get_all_apis()` | 获取所有 API |
| `get_api_description()` | 获取 API 描述 |
| `call_plugin_method()` | 跨插件调用 |
| `get_plugin_info()` | 获取插件元数据 |
| `get_plugin_id()` | 根据名称获取 ID |
