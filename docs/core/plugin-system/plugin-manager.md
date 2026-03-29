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

### 3.1 插件加载

#### load_plugins()

```python
def load_plugins(self):
    """加载所有插件（官方和第三方）"""
    self.load_official_plugins()
    self.load_thirdparty_plugins()
```

#### load_official_plugins()

```python
def load_official_plugins(self) -> List[IPlugin]:
    """
    加载官方插件

    扫描 plugin/ 目录，加载所有有效的插件。

    Returns:
        官方插件列表
    """
```

#### load_thirdparty_plugins()

```python
def load_thirdparty_plugins(self) -> List[IPlugin]:
    """
    加载第三方插件

    扫描 custom_plugin/ 目录，加载所有有效的插件。

    Returns:
        第三方插件列表
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

    清空当前注册的插件，然后重新扫描并加载所有插件。
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
        target_plugin_id: 目标插件 ID
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

---

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

        # 目录配置
        self.official_plugin_dir = Path("plugin/")
        self.thirdparty_plugin_dir = Path("custom_plugin/")

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

---

*本文档由 Claude Code 自动生成*
