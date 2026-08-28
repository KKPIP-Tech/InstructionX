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
    """加载所有插件（包括官方插件和第三方插件），并回填版本注册表"""
    self.load_official_plugins()
    self.load_thirdparty_plugins()
    self._backfill_registry()
```

> **说明**：`_backfill_registry()` 会在加载完成后扫描已加载插件，为注册表（`config/plugin_registry.json`）中缺失记录的插件回填版本/来源信息；回填失败仅记录警告日志，不影响插件加载主流程（见 `core/plugin/manager.py` 的 `_backfill_registry()` 方法）。

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

    注意：此方法**不会调用 apply_custom_order()**——重新加载后的 `_official_plugins`
    / `_thirdparty_plugins` 按目录扫描顺序填充；如需恢复用户自定义顺序，
    调用方须显式调用 `apply_custom_order()`。`config/plugin_order.json`
    本身不会被此方法清空，仅用于按需重新读取。
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
                    "name": "plugin_id__method_name",
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

> **说明**：工具名由 `sanitize_tool_name(f"{plugin_id}__{method_name}")` 生成——以双下划线分隔插件 ID 与方法名，并净化为 OpenAI function 名允许的字符集（`[a-zA-Z0-9_-]`，最长 64 字符）。`call_plugin_method()` 仍使用原始 `(plugin_id, method_name)` 调用，不受净化影响。

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

### 3.8.1 完整卸载插件

#### uninstall_plugin()

```python
def uninstall_plugin(self, plugin_id: str, remove_data: bool = False) -> Dict[str, Any]:
    """
    完整卸载指定插件

    流程（六步独立容错，任一步骤失败不阻断其余清理）：
        1. 运行时卸载（生命周期回调、API/MCP、Widget、sys.modules）
        2. 从注册表与列表移除
        3. 删除插件目录
        4. 清理 UUID 持久化文件（`PluginIdentity.delete()`）
        5. 清理排序 / 分组 / 版本注册表 / 每插件语言覆盖
        6. 可选删除插件持久化数据

    Args:
        plugin_id: 插件 UUID
        remove_data: True 时同时调用 `DataProvider.unregister_plugin()` 删除插件数据

    Returns:
        Dict: {"success": bool, "message": str, "warnings": List[str]}
        - success=False 通常表示插件不存在或未加载
        - warnings 列出各步骤的非致命失败（如目录删除权限不足）
    """
```

#### PluginIdentity.delete()

`PluginIdentity(plugin_dir).delete()`：删除插件目录下优先生成的 `.plugin_info.json`，以及回退目录 `data/plugin_identity/{插件目录名}.json`（两者可能都存在）。

### 3.8.2 用户自定义分组与混排排序

#### get_groups()

```python
def get_groups(self, scope: str) -> List[PluginGroup]:
    """
    获取指定 scope 的用户自定义分组列表（顺序即显示顺序）

    Args:
        scope: "official" 或 "thirdparty"
    """
```

#### save_groups()

```python
def save_groups(self, scope: str, groups: List[PluginGroup],
                order: Optional[List[tuple]] = None) -> bool:
    """
    保存指定 scope 的分组配置与面板统一顺序

    Args:
        scope: "official" 或 "thirdparty"
        groups: PluginGroup 列表
        order: 面板统一顺序 [("group"|"plugin", id), ...]，
               None 时保留已有顺序（新分组追加在后）
    """
```

#### get_sorted_plugins()

```python
def get_sorted_plugins(self, scope: str) -> List[tuple]:
    """
    按面板统一顺序（分组与未分组插件混排）返回渲染序列

    Args:
        scope: "official" 或 "thirdparty"

    Returns:
        渲染项列表，每项为：
        - ("group", PluginGroup, [插件实例...])：一个分组及其组内插件
        - ("plugin", 插件实例)：未分组插件
    """
```

#### 生命周期钩子 IPlugin.on_plugin_unloaded()

`IPlugin.on_plugin_unloaded()`（`core/interfaces/i_plugin.py:111-119`）由 `PluginManager._unload_plugin_instance()` 在卸载/热重载前调用；子类可重写以释放资源（取消订阅、释放文件句柄等），默认空实现保证旧插件向后兼容。

### 3.9 依赖注入（PluginServices）

#### _create_plugin_services()

```python
def _create_plugin_services(self, plugin_id: str) -> PluginServices:
    """
    创建插件服务依赖注入容器

    创建包含所有核心服务的 PluginServices 对象，
    供插件在构造器和 on_plugin_loaded 回调中使用。

    Args:
        plugin_id: 插件 UUID（用于绑定多语言取词门面 `PluginI18nFacade`）

    Returns:
        PluginServices: 服务容器实例
    """
```

**服务容器内容**（`core/interfaces/plugin_services.py`，8 字段）：

| 服务 | 类型 | 说明 |
|------|------|------|
| `llm_facade` | `LLMPluginService` | LLM 服务入口（单例，无降级保护、始终注入） |
| `data_provider` | `DataProvider` | 数据持久化服务（失败时为 `None`） |
| `task_manager` | `BackgroundTaskManager` | 后台任务管理（失败时为 `None`） |
| `logger` | `ILogger` | 日志服务（`LoggerManager` 实例，无降级保护、始终注入） |
| `mcp_manager` | `MCPManager` | MCP Server 管理器（失败时为 `None`） |
| `mcp_client` | `MCPClientManager` | MCP 外部连接管理器（失败时为 `None`） |
| `font_manager` | `FontManager` | 字体管理器（`core/font`，无降级保护、始终注入） |
| `localization` | `ILocalizationFacade` | 多语言取词门面（绑定本插件 UUID，无降级保护、始终注入；实现为 `PluginI18nFacade`） |

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

**注入时机说明**: `_create_plugin_services()` 在 `_load_plugin_from_directory()` 遍历每个插件时调用，因此**每个插件都会获得一个独立的 `PluginServices` 实例**。容器内部的各个核心服务（如 `llm_facade`、`data_provider`、`task_manager`、`mcp_manager`、`mcp_client`）本身是单例或由全局管理器提供，因此插件之间共享的是这些核心服务实例，而不是共享同一个 `PluginServices` 容器对象。这种设计让每个插件拥有独立的服务容器引用，同时保证核心服务状态全局一致。

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

    注意: MCP 系统未初始化等异常仅记录 WARNING 日志，不阻断插件注册。
    """
```

#### _notify_mcp_remove_tools()

```python
def _notify_mcp_remove_tools(self, plugin_id: str) -> None:
    """
    通知 MCP 系统移除插件工具

    在注销插件 API 时调用，通过 MCPManager.remove_plugin_tool()
    清理已注册的工具。

    注意: MCP 系统未初始化等异常仅记录 WARNING 日志，不阻断 API 注销。
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

        # 已安装插件注册表（版本/来源，用于升级降级）
        self.registry = PluginRegistry()

        # 用户自定义分组存储
        self.group_store = PluginGroupStore()

        # 日志管理器
        self._logger = LoggerManager()
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

**插件系统内部**：
- [插件系统概述](overview.md)
- [IPlugin 接口](iplugin.md)（被 `PluginManager` 加载与实例化的抽象基类）
- [插件开发指南](plugin-development.md)（`PluginServices` 注入的消费者）
- [GitHub 插件安装器](plugin-installer.md)（`PluginManager.uninstall_plugin()` 的入口）

**接口层与 API 索引**：
- [接口层概述](../interfaces/overview.md)
- [完整 API 参考 §2.1 PluginManager](../../api/full-reference.md#21-pluginmanager)

**依赖的下游服务**（`PluginManager` 通过 `PluginServices` 注入给插件）：
- [DataProvider 概述](../data-provider/overview.md)（持久化 + Pub/Sub）
- [后台任务概述](../background-task/overview.md)（同步/异步/定时/长期任务）
- [LLM Provider 概述](../llm-provider/overview.md)（`LLMPluginService` 门面）
- [MCP 协议模块概述](../mcp/overview.md)（API 注册 → MCP 工具同步）

**架构分析**：
- [instructionx-architecture.md §3.1 插件系统](../../architecture/instructionx-architecture.md#31-插件系统-coreplugin)（含 `PluginManager` 单例架构图与插件加载完整链路时序图）
