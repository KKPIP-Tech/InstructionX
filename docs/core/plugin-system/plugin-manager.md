# PluginManager

> 插件管理器的完整说明

---

## 1. 概述

`PluginManager` 是插件系统的核心组件，负责插件的加载、注册、API 管理和跨插件调用。

**文件位置**: `core/plugin/manager.py`

**模式**: 单例模式（全局唯一实例）

---

## 2. 核心职责

| 功能 | 说明 | 典型 API |
|------|------|---------|
| **插件加载** | 扫描并加载官方/第三方插件 | `load_plugins()`, `load_official_plugins()` |
| **实例管理** | 维护插件实例注册表 | `get_all_plugins()`, `get_plugin_by_id()` |
| **API 注册** | 自动扫描 service.py 注册可调用方法 | `_auto_register_plugin_api()` |
| **API 查询** | 获取其他插件的 API 说明 | `get_plugin_api()`, `get_all_apis()` |
| **跨插件调用** | 直接调用其他插件的方法 | `call_plugin_method()` |
| **MCP 工具生成** | 生成符合 OpenAI Function Calling 规范的接口 | `get_all_function_tools()` |

---

## 3. 核心 API

### 3.0 访问入口

#### get_plugin_manager()

```python
def get_plugin_manager() -> "PluginManager":
    """获取插件管理器单例实例

    Returns:
        PluginManager: 插件管理器单例实例
    """
    return PluginManager()
```

**使用示例**:

```python
from core.plugin.manager import get_plugin_manager

# 获取单例实例
manager = get_plugin_manager()
```

> 注意: 也可以直接通过 `PluginManager()` 获取单例实例（`__new__` 保证全局唯一）。

### 3.1 插件加载

#### load_plugins()

```python
def load_plugins(self) -> None:
    """加载所有插件（官方和第三方）"""
    self.load_official_plugins()
    self.load_thirdparty_plugins()
```

#### load_official_plugins()

```python
def load_official_plugins(self) -> List[IPlugin]:
    """
    扫描并加载 plugin 目录下的所有官方插件

    Returns:
        已加载的官方插件列表
    """
```

#### load_thirdparty_plugins()

```python
def load_thirdparty_plugins(self) -> List[IPlugin]:
    """
    扫描并加载 custom_plugin 目录下的所有第三方插件

    Returns:
        已加载的第三方插件列表
    """
```

### 3.2 插件查询

#### get_all_plugins()

```python
def get_all_plugins(self) -> List[IPlugin]:
    """
    获取所有插件（官方 + 第三方）

    Returns:
        所有插件列表
    """
```

#### get_plugin_by_id()

```python
def get_plugin_by_id(self, plugin_id: str) -> Optional[IPlugin]:
    """
    根据 UUID 获取插件

    Args:
        plugin_id: 插件的 UUID

    Returns:
        插件实例，如果不存在则返回 None
    """
```

#### get_plugin_by_name()

```python
def get_plugin_by_name(self, name: str) -> Optional[IPlugin]:
    """
    根据名称获取插件

    Args:
        name: 插件名称

    Returns:
        插件实例，如果不存在则返回 None
    """
```

#### get_plugin_id_by_name()

```python
def get_plugin_id_by_name(self, plugin_name: str) -> Optional[str]:
    """
    根据插件名称获取 UUID

    Args:
        plugin_name: 插件名称

    Returns:
        UUID 字符串，如果不存在则返回 None
    """
```

#### get_plugin_id_by_type_id()

```python
def get_plugin_id_by_type_id(self, plugin_type_id: str) -> Optional[str]:
    """
    通过插件类型标识符（plugin_type_id）获取插件 UUID

    Args:
        plugin_type_id: 插件类型标识符（如 "string-tools"）

    Returns:
        插件 UUID，如果不存在则返回 None
    """
```

#### get_plugin_by_type_id()

```python
def get_plugin_by_type_id(self, plugin_type_id: str) -> Optional[IPlugin]:
    """
    通过插件类型标识符获取插件实例

    Args:
        plugin_type_id: 插件类型标识符（如 "string-tools"）

    Returns:
        插件实例，如果不存在则返回 None
    """
```

#### get_official_plugins()

```python
def get_official_plugins(self) -> List[IPlugin]:
    """
    获取所有官方插件实例

    Returns:
        官方插件列表
    """
```

#### get_thirdparty_plugins()

```python
def get_thirdparty_plugins(self) -> List[IPlugin]:
    """
    获取所有第三方插件实例

    Returns:
        第三方插件列表
    """
```

#### reload_plugins()

```python
def reload_plugins(self):
    """
    重新加载所有插件

    清空内存中的插件注册表（包括 _official_plugins、_thirdparty_plugins、
    _plugin_registry、_plugin_name_to_id、_api_registry），然后重新扫描
    并加载所有插件。

    注意：此方法不会清空插件顺序配置（plugin_order.json），用户自定义的
    插件显示顺序在重新加载后仍然有效（通过 apply_custom_order() 恢复）。
    """
```

#### register_plugin()

```python
def register_plugin(self, plugin: IPlugin, is_official: bool = False):
    """
    手动注册插件到管理器

    Args:
        plugin: 插件实例
        is_official: 是否为官方插件，默认为 False
    """
```

#### unregister_plugin()

```python
def unregister_plugin(self, plugin_name: str):
    """
    从管理器移除插件

    Args:
        plugin_name: 插件名称
    """
```

### 3.3 插件顺序管理

#### apply_custom_order()

```python
def apply_custom_order(self):
    """应用自定义插件顺序（从配置文件加载）"""
    # 从 config/plugin_order.json 读取配置
    # 按照配置的 UUID 顺序排列插件
    # 未在配置中的新插件自动追加到列表末尾
```

#### save_plugin_order()

```python
def save_plugin_order(self,
                     official_plugin_ids: List[str],
                     thirdparty_plugin_ids: List[str]) -> bool:
    """
    保存插件顺序到配置文件

    Args:
        official_plugin_ids: 官方插件 UUID 列表
        thirdparty_plugin_ids: 第三方插件 UUID 列表

    Returns:
        保存是否成功
    """
```

#### get_official_plugin_ids()

```python
def get_official_plugin_ids(self) -> List[str]:
    """获取所有官方插件 UUID（按当前顺序）"""
```

#### get_thirdparty_plugin_ids()

```python
def get_thirdparty_plugin_ids(self) -> List[str]:
    """获取所有第三方插件 UUID（按当前顺序）"""
```

### 3.4 API 管理

#### register_plugin_api()

```python
def register_plugin_api(self,
                       plugin_id: str,
                       service_instance: Any,
                       api_descriptions: Dict[str, Dict[str, Any]]) -> None:
    """
    注册插件的 API 方法

    注册完成后会自动调用 `_notify_mcp_new_tools()`，
    将新注册的 API 方法同步到 MCP 系统。

    Args:
        plugin_id: 插件实例 ID
        service_instance: Service 类实例
        api_descriptions: API 描述字典
    """
```

#### get_plugin_api()

```python
def get_plugin_api(self, plugin_id: str) -> Optional[Dict[str, Any]]:
    """
    获取插件的 API 信息

    Args:
        plugin_id: 插件实例 ID

    Returns:
        插件 API 信息字典，如果不存在则返回 None

    Example:
        {
            "plugin_id": "uuid",
            "plugin_name": "TaskManager",
            "plugin_type": "TaskManager",
            "methods": ["add_task", "list_tasks", "delete_task"],
            "descriptions": {...}
        }
    """
```

#### get_all_apis()

```python
def get_all_apis(self) -> Dict[str, Dict[str, Any]]:
    """
    获取所有已注册的 API

    Returns:
        所有 API 信息字典 {plugin_id: {...}}
    """
```

### 3.5 跨插件调用

#### call_plugin_method()

```python
def call_plugin_method(self,
                      caller_id: str,
                      plugin_id: str,
                      method_name: str,
                      **kwargs) -> Any:
    """
    跨插件调用方法

    Args:
        caller_id: 调用者插件 ID（用于日志）
        plugin_id: 目标插件的唯一标识符
        method_name: 方法名
        **kwargs: 方法参数

    Returns:
        方法返回值

    Raises:
        ValueError: 插件或方法不存在时抛出
        RuntimeError: 方法执行失败时抛出
    """
```

**使用示例**:

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取 TaskManager 插件 ID
task_manager_id = manager.get_plugin_id_by_name("任务管理器")

# 调用方法
result = manager.call_plugin_method(
    caller_id="my-plugin-id",
    plugin_id=task_manager_id,
    method_name="add_task",
    title="新任务",
    description="任务描述"
)
```

### 3.6 MCP 工具生成

#### get_all_function_tools()

```python
def get_all_function_tools(self) -> List[Dict[str, Any]]:
    """
    获取所有可用的 function tools（用于 MCP）

    Returns:
        function tools 列表，格式符合 MCP/OpenAI function calling 规范

    Example:
        [
            {
                "type": "function",
                "function": {
                    "name": "uuid.method_name",
                    "description": "[插件名] 方法描述",
                    "parameters": {
                        "type": "object",
                        "properties": {...},
                        "required": ["param1"]
                    }
                }
            }
        ]
    """
```

### 3.7 API 描述查询

#### get_api_description()

```python
def get_api_description(self,
                     plugin_id: str,
                     method_name: Optional[str] = None) -> Dict[str, Any]:
    """
    获取 API 的结构化描述（适用于 MCP 或函数工具）

    Args:
        plugin_id: 插件唯一标识符
        method_name: 可选，指定方法名。None 时返回所有方法的描述

    Returns:
        API 描述字典，包含方法名、参数、返回值等信息

    Example:
        # 获取所有方法描述
        desc = manager.get_api_description("plugin-uuid")
        
        # 获取单个方法描述
        method_desc = manager.get_api_description("plugin-uuid", "add_task")
    """
```

### 3.8 API 注销

#### unregister_plugin_api()

```python
def unregister_plugin_api(self, plugin_id: str) -> None:
    """
    移除插件的 API 注册

    Args:
        plugin_id: 插件唯一标识符

    Note:
        通常在插件卸载时调用，清理 API 注册表
    """
```

### 3.9 依赖注入（PluginServices）

#### _create_plugin_services()

```python
def _create_plugin_services(self) -> PluginServices:
    """
    创建插件服务依赖注入容器

    创建包含所有核心服务的 PluginServices 对象，
    供插件在构造器和 on_plugin_loaded 回调中使用。

    Returns:
        PluginServices: 服务容器实例
    """
```

**服务容器内容**：

| 服务 | 类型 | 说明 |
|------|------|------|
| `llm_facade` | `LLMPluginService` | LLM 服务入口（单例） |
| `data_provider` | `DataProvider` | 数据持久化服务（失败时为 `None`） |
| `task_manager` | `BackgroundTaskManager` | 后台任务管理（失败时为 `None`） |
| `logger` | `ILogger` | 日志服务（`LoggerManager` 实例） |
| `mcp_manager` | `MCPManager` | MCP Server 管理器（失败时为 `None`） |
| `mcp_client` | `MCPClientManager` | MCP 外部连接管理器（失败时为 `None`） |

**使用流程**（见 `manager.py` 的 `_load_plugin_from_directory()` 方法）：

```python
# 1. PluginManager 在加载插件前创建服务容器
services = self._create_plugin_services()

# 2. 将 services 注入插件（构造器参数为条件注入，实例属性为强制注入）
# 仅当插件的 __init__ 包含 services 参数时才通过构造器传入
if 'services' in [p.name for p in inspect.signature(plugin_class).parameters.values()]:
    plugin = plugin_class(services=services)
else:
    plugin = plugin_class()
plugin._plugin_id = plugin_id  # 框架内部赋值
plugin._services = services  # 框架内部赋值（强制注入，与构造器参数无关）

# 3. 调用生命周期回调（不传参数，向后兼容旧插件）
plugin.on_plugin_loaded()
```

**注入时机说明**: `_create_plugin_services()` 在 `_load_plugin_from_directory()` 遍历每个插件时调用，而非全局一次性创建。这意味着每个插件加载时共享同一个 `PluginServices` 实例（DI 容器），因此旧版插件即便不使用 DI 也能通过 `get_llm_plugin_service()` 等单例函数访问服务。

> **注意**：无论插件的 `__init__` 是否接收 `services` 参数，`PluginManager` 都会在实例化后通过
> `plugin_instance._services = services` 强制注入服务容器。因此插件始终可以通过 `self._services`
> 访问服务。旧版插件（不支持 DI）也可通过直接导入单例访问服务。

---

### 3.10 MCP 通知（内部方法）

#### _notify_mcp_new_tools()

```python
def _notify_mcp_new_tools(
    self,
    plugin_id: str,
    api_descriptions: Dict[str, Dict[str, Any]],
) -> None:
    """
    通知 MCP 系统有新插件工具注册

    将 service_api 中定义的方法转换为 MCP 工具格式，
    通过 MCPManager.sync_plugin_tool() 同步到 MCP 系统。

    注意: MCP 系统未初始化时静默忽略错误。
    """
```

#### _notify_mcp_remove_tools()

```python
def _notify_mcp_remove_tools(self, plugin_id: str) -> None:
    """
    通知 MCP 系统移除插件工具

    在注销插件 API 时调用，通过 MCPManager.remove_plugin_tool()
    清理已注册的工具。

    注意: MCP 系统未初始化时静默忽略错误。
    """
```

## 4. 内部结构

### 4.1 属性

```python
class PluginManager:
    def __init__(self):
        # 插件列表
        self._official_plugins: List[IPlugin] = []
        self._thirdparty_plugins: List[IPlugin] = []

        # 插件注册表
        self._plugin_registry: Dict[str, IPlugin] = {}  # plugin_id (UUID) -> plugin
        self._plugin_name_to_id: Dict[str, str] = {}    # plugin_name -> plugin_id

        # API 注册表
        self._api_registry: Dict[str, PluginAPI] = {}   # plugin_id -> PluginAPI

        # 目录配置（基于 manager.py 位置向上定位到项目根目录）
        self.official_plugin_dir = Path(__file__).parent.parent.parent / "plugin"
        self.thirdparty_plugin_dir = Path(__file__).parent.parent.parent / "custom_plugin"

        # 配置管理器
        self.config_manager = PluginConfigManager()
```

### 4.2 PluginAPI 类

```python
class PluginAPI:
    """插件 API 信息"""

    def __init__(self, plugin_id: str, plugin_name: str, plugin_type: str):
        self.plugin_id = plugin_id
        self.plugin_name = plugin_name
        self.plugin_type = plugin_type
        self.api_methods: Dict[str, Callable] = {}
        self.api_descriptions: Dict[str, Dict[str, Any]] = {}
```

---

## 5. 使用示例

### 5.1 基础使用

```python
from core.plugin.manager import PluginManager

# 获取单例实例
manager = PluginManager()

# 加载插件
manager.load_plugins()

# 获取所有插件
all_plugins = manager.get_all_plugins()

# 根据 ID 获取插件
plugin = manager.get_plugin_by_id("plugin-uuid")
```

### 5.2 跨插件调用

```python
# 假设 TaskManager 插件有一个 add_task 方法
task_manager_id = manager.get_plugin_id_by_name("任务管理器")

if task_manager_id:
    result = manager.call_plugin_method(
        caller_id="my-plugin",
        plugin_id=task_manager_id,
        method_name="add_task",
        title="完成报告",
        due_date="2026-01-15"
    )
```

### 5.3 查询 API

```python
# 获取所有 API
all_apis = manager.get_all_apis()

# 获取特定插件的 API
api = manager.get_plugin_api("plugin-uuid")

# 获取 MCP 工具列表
tools = manager.get_all_function_tools()
```

---

## 6. 相关文档

- [插件系统概述](overview.md)
- [IPlugin 接口](iplugin.md)
- [插件开发指南](plugin-development.md)
- [GitHub 插件安装器](plugin-installer.md)
- [MCP 协议模块概述](../mcp/overview.md)

---

*本文档由 Claude Code 自动生成*
