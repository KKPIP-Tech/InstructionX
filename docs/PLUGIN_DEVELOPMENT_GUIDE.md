# 插件系统开发指南

> 本文档旨在帮助开发者快速理解 InstructionX 的插件系统架构，掌握核心概念，并能够独立开发插件。

---

## 1. 整体架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                           应用主窗口                                 │
│                    (SkillsPanel + WorkArea + Dialogs)                │
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        │                           │                           │
        ▼                           ▼                           ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│   插件 A        │      │   插件 B        │      │   插件 C        │
│ (TaskManager)   │      │ (TextFormatting)│      │ (CodeFormatter) │
│                 │      │                 │      │                 │
│ entrance.py     │      │ entrance.py     │      │ entrance.py     │
│ service.py      │      │ service.py      │      │ service.py      │
│ information.py  │      │ information.py  │      │ information.py  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
        ┌───────────────────┐           ┌───────────────────┐
        │   PluginManager   │           │   DataProvider   │
        │   (插件管理层)     │           │   (数据层)        │
        │                   │           │                   │
        │ • 加载插件        │           │ • 数据持久化       │
        │ • 注册 API       │           │ • 插件数据管理     │
        │ • 跨插件调用     │           │ • 发布/订阅        │
        │ • API 发现      │           │ • 资源管理        │
        └───────────────────┘           └───────────────────┘
                    │                               │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
                        ┌───────────────────────┐
                        │      持久化层         │
                        │                       │
                        │  data/data.json       │
                        │  data/assets/         │
                        └───────────────────────┘
```

---

## 2. 核心组件

本系统有两个核心组件：**DataProvider** 和 **PluginManager**。它们各司其职，共同支撑整个插件系统。

### 2.1 DataProvider - 数据层

> 定位：应用及插件的数据提供者和持久化方案解决者

**文件位置**：`core/data/data_provider.py`

**核心职责**：

| 功能 | 说明 | 典型 API |
|------|------|---------|
| **数据持久化** | 将数据保存到 JSON 文件，支持原子写入，防止数据损坏 | `save_data()` |
| **插件数据管理** | 注册/注销插件实例 | `register_plugin()`, `unregister_plugin()` |
| **数据读写** | 读取和设置插件数据 | `get_plugin_data()`, `set_plugin_data()` |
| **命名空间隔离** | 区分私有数据(PRIVATE)和公共数据(PUBLIC) | `DataNamespace` 枚举 |
| **发布/订阅** | 插件间数据变更通知 | `subscribe()`, `publish()` |
| **资源管理** | 插件资源文件存储 | `save_asset()`, `load_asset()` |

**数据命名空间**：

```python
from core.data.data_provider import DataProvider, DataNamespace

provider = DataProvider()

# PRIVATE：仅插件内部使用，其他插件无法访问
provider.set_plugin_data("my-plugin", "internal_config", {...}, DataNamespace.PRIVATE)

# PUBLIC：可被其他插件访问和订阅
provider.set_plugin_data("my-plugin", "status", "ready", DataNamespace.PUBLIC)
```

### 2.2 PluginManager - 插件管理层

> 定位：插件的加载、注册、API 管理和跨插件调用

**文件位置**：`core/plugin/manager.py`

**核心职责**：

| 功能 | 说明 | 典型 API |
|------|------|---------|
| **插件加载** | 扫描并加载官方/第三方插件 | `load_plugins()` |
| **插件注册** | 注册 IPlugin 实例 | `register_plugin()` |
| **API 注册** | 注册 Service 方法供其他插件调用 | `register_plugin_api()` |
| **API 查询** | 获取其他插件的 API 说明 | `get_plugin_api()`, `get_all_apis()` |
| **跨插件调用** | 直接调用其他插件的方法 | `call_plugin_method()` |
| **MCP 工具生成** | 生成符合 OpenAI Function Calling 规范的接口 | `get_all_function_tools()` |

---

## 3. 数据存储与访问

### 3.1 数据流概览

```
┌──────────────┐     set_plugin_data()      ┌──────────────┐
│   插件 A      │ ──────────────────────▶  │ DataProvider │
│ (TaskManager) │                           │              │
└──────────────┘                           │  ┌────────┐  │
                                            │  │ PRIVATE│  │
                                            │  │ PUBLIC │  │
┌──────────────┐     get_plugin_data()     │  └────────┘  │
│   插件 B      │ ◀──────────────────────  └──────────────┘
│ (Reporter)   │
└──────────────┘
```

### 3.2 基本使用示例

**在 Service 中使用 DataProvider**：

```python
# plugin/my_plugin/service.py
from core.data.data_provider import DataProvider, DataNamespace

class Service:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()

    def save_task(self, title: str):
        """保存任务到数据存储"""
        tasks = self.data_provider.get_plugin_data(
            self.plugin_id, "tasks", DataNamespace.PRIVATE, []
        )
        tasks.append({"title": title, "status": "pending"})

        self.data_provider.set_plugin_data(
            self.plugin_id, "tasks", tasks, DataNamespace.PRIVATE
        )

    def get_tasks(self):
        """获取任务列表"""
        return self.data_provider.get_plugin_data(
            self.plugin_id, "tasks", DataNamespace.PRIVATE, []
        )

    def update_status(self, new_status: str):
        """更新状态并通知其他插件"""
        self.data_provider.publish(
            self.plugin_id, "status", new_status, DataNamespace.PUBLIC
        )
```

**在 entrance.py 中注册插件**：

```python
# plugin/my_plugin/entrance.py
class MyPlugin(IPlugin):
    def _create_widget(self, parent=None, data_provider=None):
        plugin_id = self.plugin_id or "my-plugin-default"

        # 创建服务实例
        service = Service(plugin_id)

        # 注册插件（如果还没注册）
        if data_provider:
            try:
                data_provider.register_plugin(plugin_id, "MyPlugin")
                data_provider.set_active_instance(plugin_id)
            except:
                pass

        # 构建 UI...
        return widget
```

---

## 4. 插件间通信

插件间有两种通信方式：**发布/订阅** 和 **直接 API 调用**。

### 4.1 发布/订阅模式

适用于**事件通知**场景，如"任务状态变更"、"数据更新"等。

```
┌──────────────┐     subscribe()      ┌──────────────┐
│   插件 B      │ ◀──────────────────  │ DataProvider │
│ (订阅者)     │                      │              │
└──────────────┘                      └──────┬───────┘
       │                                        │
       │ 回调函数                                │ publish()
       │ on_status_change()                    │
       │                                        ▼
       │                                 ┌──────────────┐
       └─────────────────────────────────│   插件 A     │
                                 (发布者)│              │
                                        └──────────────┘
```

**示例：订阅其他插件的数据变更**

```python
# plugin/reporter/service.py
class ReporterService:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()

    def subscribe_to_task_manager(self, task_manager_id: str):
        """订阅任务管理器的数据变更"""
        # 订阅统计信息变更
        self.data_provider.subscribe(
            subscriber_id=self.plugin_id,
            target_plugin_id=task_manager_id,
            target_key="statistics",
            callback=self._on_statistics_changed
        )

    def _on_statistics_changed(self, plugin_id, key, old_value, new_value):
        """统计信息变更回调"""
        print(f"任务统计更新: {old_value} → {new_value}")
```

### 4.2 直接 API 调用

适用于**调用功能**场景，如"添加任务"、"转换文本"等。

```
┌──────────────┐ call_plugin_method() ┌──────────────┐
│   插件 A      │ ──────────────────▶ │   插件 B      │
│              │    method="add_task" │ (TaskManager) │
│              │    title="新任务"     │              │
└──────────────┘ ◀────────────────────└──────────────┘
        │         返回: task 对象
        │
        ▼
    处理结果
```

**示例：调用其他插件的方法**

```python
# plugin/reporter/service.py
class ReporterService:
    def generate_report(self, task_manager_id: str):
        """生成任务报告 - 调用 TaskManager 的 API"""

        # 直接调用 TaskManager 的 list_tasks 方法
        all_tasks = self.data_provider.call_plugin_method(
            caller_id=self.plugin_id,
            plugin_id=task_manager_id,
            method_name="list_tasks",
            status="completed"
        )

        return {
            "total_completed": len(all_tasks),
            "tasks": all_tasks
        }
```

---

## 5. 插件开发快速指南

### 5.1 目录结构

```
plugin/                          # 官方插件目录
├── my_plugin/                  # 插件文件夹
│   ├── __init__.py            # Python 包标识（可为空）
│   ├── entrance.py            # UI 界面入口
│   ├── service.py             # 业务逻辑
│   └── information.py          # 插件元数据
└── ...

custom_plugin/                   # 第三方插件目录
└── ...
```

### 5.2 三个核心文件

| 文件 | 职责 | 关键点 |
|------|------|-------|
| **entrance.py** | UI 界面 | 实现 `IPlugin` 接口，构建 Qt 界面 |
| **service.py** | 业务逻辑 | 不依赖 UI，纯 Python 实现 |
| **information.py** | 元数据 | 实现 `IPluginInfo` 接口，定义 API |

### 5.3 最小示例

**service.py** - 业务逻辑层
```python
class Service:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()

    def to_uppercase(self, text: str) -> str:
        return text.upper()

    def to_lowercase(self, text: str) -> str:
        return text.lower()
```

**information.py** - 元数据层
```python
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any

class TextFormattingPluginInfo(IPluginInfo):
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        return "Your Name"

    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {"text": {"type": "str", "required": True}},
                "returns": {"type": "str"}
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_FileIcon")

    @property
    def skill_description(self) -> str:
        return "文本格式化工具"
```

**entrance.py** - UI 层
```python
from PySide6.QtWidgets import QWidget, QVBoxLayout
from core.plugin.plugin_interface import IPlugin
from .service import Service

class TextFormattingPlugin(IPlugin):
    @property
    def plugin_name(self):
        return "文本\n格式化"

    def _create_widget(self, parent=None, data_provider=None):
        plugin_id = self.plugin_id or "text-formatting-default"
        service = Service(plugin_id)

        # 注册插件
        if data_provider:
            try:
                data_provider.register_plugin(plugin_id, "TextFormatting")
            except:
                pass

        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        # 构建 UI...
        # button.clicked.connect(lambda: ...)

        return widget
```

### 5.4 UI 持久化机制

从系统层面支持插件 UI 状态持久化。当用户切换插件再切换回来时，插件的 UI 状态会自动保持，无需开发者额外编写代码。

**实现原理：**
- `IPlugin` 基类中会自动缓存插件创建的 Widget 实例
- 切换插件时，Widget 会被隐藏但不会被销毁
- 再次切换回来时，会自动复用缓存的 Widget

**开发者注意事项：**
- 无需修改任何代码即可享受此功能
- `_create_widget` 方法只会在首次创建 Widget 时调用，后续切换会直接返回缓存的实例
- 如果需要在 Widget 创建时执行特定逻辑，可以重写 `get_widget` 方法（需调用父类方法）

---

## 6. 相关文档索引

| 文档 | 说明 |
|------|------|
| [PLUGIN_DESIGN.md](PLUGIN_DESIGN.md) | 详细的插件架构设计文档，包含完整代码示例 |
| [DATAPROVIDER_GUIDE.md](DATAPROVIDER_GUIDE.md) | DataProvider 完整 API 参考 |
| [API_CALLING_GUIDE.md](API_CALLING_GUIDE.md) | 跨插件 API 调用和 MCP 集成指南 |
| [PLUGIN_API_GUIDE.md](PLUGIN_API_GUIDE.md) | PluginManager API 详解 |
| [SKILLS_PANEL_GUIDE.md](SKILLS_PANEL_GUIDE.md) | 技能面板使用指南 |
| [TASK_PLUGINS_DEMO.md](TASK_PLUGINS_DEMO.md) | 任务插件演示说明 |

---

## 7. 快速参考

### DataProvider 常用 API

```python
# 获取实例
provider = DataProvider()

# 插件注册
provider.register_plugin("plugin-id", "PluginType")
provider.set_active_instance("plugin-id")

# 数据操作
provider.get_plugin_data("plugin-id", "key", DataNamespace.PRIVATE)
provider.set_plugin_data("plugin-id", "key", value, DataNamespace.PUBLIC)

# 发布/订阅
provider.subscribe("my-id", "target-id", "key", callback)
provider.publish("my-id", "key", value)

# 资源管理
provider.save_asset("plugin-id", "filename", content)
```

### PluginManager 常用 API

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 插件查询
plugin = manager.get_plugin_by_id("plugin-id")
plugin_id = manager.get_plugin_id_by_name("插件名称")

# API 调用
manager.call_plugin_method("caller-id", "target-id", "method_name", arg=value)

# API 查询
api = manager.get_plugin_api("plugin-id")
all_apis = manager.get_all_apis()
```
