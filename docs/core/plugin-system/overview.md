# 插件系统概述

> 插件系统的架构设计、加载机制和核心概念

---

## 1. 插件系统架构

```mermaid
graph TB
    subgraph PM [PluginManager 单例]
        Registry[插件注册表<br/>_plugin_registry]
        APIReg[API 注册表<br/>_api_registry]
    end

    subgraph Plugins [插件目录]
        Official[plugin/ 官方插件]
        ThirdParty[custom_plugin/ 第三方插件]
    end

    subgraph PluginFiles [插件文件结构]
        Entrance[entrance.py]
        Service[service.py]
        Info[information.py]
    end

    Registry -->|加载| Official
    Registry -->|加载| ThirdParty
    APIReg -->|注册| Info
    Official --> Entrance
    Official --> Service
    Official --> Info
    ThirdParty --> Entrance
    ThirdParty --> Service
    ThirdParty --> Info
```

---

## 2. 插件加载机制

### 2.1 加载流程

```mermaid
flowchart TD
    A[PluginManager.load_plugins] --> B[load_official_plugins]
    A --> C[load_thirdparty_plugins]

    B --> D[扫描 plugin/ 目录]
    C --> E[扫描 custom_plugin/ 目录]

    D --> F{对每个子目录}
    E --> F

    F -->|检查 entrance.py| G[动态导入模块]
    G --> H[查找 IPlugin 子类]
    H --> I[实例化插件]
    J[生成/加载 UUID] --> I[实例化插件]
    I --> K[调用 on_plugin_loaded]
    K --> L[写入注册表并自动注册 API]
```

> **说明**：`PluginManager` 的加载链路止于「写入 `_plugin_registry` 并调用 `_auto_register_plugin_api()`」。技能面板（SkillsPanel）不属于加载链路——它由 UI 层（`ui/main_window.py`）在 `load_plugins()` 完成后构建并通过 `load_skills_from_manager()` 从 `PluginManager` 读取已加载插件。

### 2.2 动态导入实现

```python
def _load_plugin_from_directory(self, plugin_dir: Path) -> Optional[IPlugin]:
    """从目录加载插件"""

    # 1. 查找入口文件
    entrance_file = plugin_dir / "entrance.py"

    # 2. 创建 __init__.py（如果不存在）
    init_file = plugin_dir / "__init__.py"
    if not init_file.exists():
        init_file.write_text("")

    # 3. 动态导入模块
    spec = importlib.util.spec_from_file_location(module_name, entrance_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # 4. 查找 IPlugin 子类（排除框架内置 IPlugin）
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if not (isinstance(attr, type) and issubclass(attr, IPlugin)) or attr is IPlugin:
            continue
        # 同时排除 core.plugin.plugin_interface.IPlugin（按 __module__ 判断）
        if getattr(attr, '__module__', '') == 'core.plugin.plugin_interface':
            continue
        plugin_class = attr
        break

    # 5. 生成 UUID
    identity = PluginIdentity(plugin_dir)
    plugin_id = identity.load_or_create_id()

    # 6. 创建服务容器
    services = self._create_plugin_services()

    # 7. 实例化插件（尝试注入 services）
    sig = inspect.signature(plugin_class)
    params = [p.name for p in sig.parameters.values()]
    if 'services' in params:
        plugin_instance = plugin_class(services=services)
    else:
        plugin_instance = plugin_class()

    # 8. 设置实例属性
    plugin_instance._plugin_dir = plugin_dir
    plugin_instance._plugin_id = plugin_id
    plugin_instance._services = services

    # 9. 调用加载完成回调（不传参数，向后兼容旧插件）
    plugin_instance.on_plugin_loaded()

    # 10. 维护注册表映射并尝试自动注册 API
    plugin_instance._plugin_name = plugin_instance.plugin_name
    self._plugin_registry[plugin_id] = plugin_instance
    self._plugin_name_to_id[plugin_instance.plugin_name] = plugin_id
    self._auto_register_plugin_api(plugin_dir, plugin_id)

    return plugin_instance
```

> **说明**：本片段为示意简化——`inspect`、`importlib.util` 等 import 均位于文件顶部（`core/plugin/manager.py`），且省略了插件名重复检测与异常处理；完整实现见 `PluginManager._load_plugin_from_directory()`。

> **注意**: `PluginManager` 调用 `on_plugin_loaded()` 时不传递任何参数。插件应通过 `self.plugin_id` 访问 UUID，通过 `self._services` 访问服务容器。详见 [IPlugin 接口](iplugin.md)。

---

## 3. 插件目录结构

### 3.1 标准插件结构

```
plugin_name/
├── __init__.py           # Python 包标识（可为空）
├── entrance.py           # 插件入口（必需）
│                          # 继承 IPlugin，实现 UI
├── service.py            # 业务逻辑（必需）
│                          # 定义可被调用的方法
├── information.py        # 插件元数据（必需）
│                          # 继承 IPluginInfo，定义 API
├── config/               # 配置文件目录（必需，开发规范）
├── icons/                # 图标目录（可选）
│   └── icon.png
└── assets/               # 资源目录（可选）
    └── ...
```

### 3.2 三个核心文件

| 文件 | 必需 | 职责 | 关键内容 |
|------|------|------|---------|
| **entrance.py** | ✅ 是（框架硬校验） | UI 入口 | 继承 `IPlugin`，实现 `_create_widget()` |
| **service.py** | ✅ 是（开发规范） | 业务逻辑 | 定义可被外部调用的方法，类名以 `Service` 结尾 |
| **information.py** | ✅ 是（开发规范） | 元数据 | 继承 `IPluginInfo`，定义 `service_api` |
| **config/** | ✅ 是（开发规范） | 配置 | 插件配置文件目录，禁止魔法数 |

> **说明**：框架加载时仅对 `entrance.py` 做硬性校验（缺失则跳过该插件）；缺少 `service.py`/`information.py` 不影响插件本体加载，仅会跳过 API 自动注册。`service.py`、`information.py`、`config/` 的"必需"是插件开发规范的强制要求，框架不兜底校验。

---

## 4. API 自动注册机制

### 4.1 注册流程

```mermaid
flowchart TD
    A[插件加载时] --> B[导入 information.py]

    B --> C[查找 IPluginInfo 子类]
    C --> D[获取 service_api 字典]
    D --> E[导入 service.py]
    E --> F[查找 Service 类]
    F --> G[注册到 _api_registry]
```

> **前置条件**：API 自动注册要求 `information.py` 与 `service.py` 同时存在、且 `service_api` 非空；任一不满足时框架仅跳过注册，插件本体仍可正常加载（框架仅对 `entrance.py` 做硬性加载校验）。按插件开发规范，`entrance.py`、`service.py`、`information.py`、`config/` 均为必需文件。

### 4.2 service_api 定义示例

```python
# information.py
class MyPluginInfo(IPluginInfo):
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "method_name": {
                "description": "方法描述",
                "parameters": {
                    "param1": {"type": "str", "required": True},
                    "param2": {"type": "int", "required": False}
                },
                "returns": {"type": "str"}
            }
        }
```

---

## 5. 插件分类

### 5.1 官方插件 vs 第三方插件

| 分类 | 目录 | 加载顺序 | 配置管理 |
|------|------|---------|---------|
| **官方插件** | `plugin/` | 先加载 | `plugin_order.json` |
| **第三方插件** | `custom_plugin/` | 后加载 | `plugin_order.json` |

### 5.2 插件顺序管理

```python
# config/plugin_order.json
{
    "official_plugins": [
        "uuid-1",
        "uuid-2",
        "uuid-3"
    ],
    "thirdparty_plugins": [
        "uuid-a",
        "uuid-b"
    ]
}
```

应用启动时，`PluginManager.apply_custom_order()` 会按照配置顺序排列插件。

---

## 6. 核心类图

```mermaid
classDiagram
    class IPlugin {
        <<abstract>>
        +plugin_name: str
        +plugin_id: Optional[str] (框架实现返回 self._plugin_id)
        +skill_icon: Optional[QIcon]
        +skill_description: str
        +skill_tooltip: str
        +plugin_info: IPluginInfo
        +llm_tools: List[Dict]
        +_create_widget(parent, data_provider): QWidget
        +get_widget(parent, data_provider): QWidget  (框架实现带缓存)
        +on_plugin_loaded(): None  (调用时不传参)
        +on_plugin_unloaded(): None  (卸载/热重载前调用)
    }

    class IPluginInfo {
        <<abstract>>
        +version: PluginVersion
        +developer: str
        +developer_email: str
        +developer_website: str
        +is_free: bool
        +description: str
        +service_api: Dict
        +skill_icon: PluginIcon
        +skill_description: str
        +plugin_type_id: str
        +tags: Optional[list]
        +dependencies: Optional[Dict]
    }

    class PluginManager {
        +load_plugins()
        +load_official_plugins()
        +load_thirdparty_plugins()
        +get_plugin_by_id(plugin_id)
        +get_plugin_by_name(name)
        +get_all_plugins()
        +get_official_plugins()
        +get_thirdparty_plugins()
        +apply_custom_order()
        +reload_plugins()
        +register_plugin_api()
        +call_plugin_method()
        +get_all_function_tools()
    }

    IPlugin --> PluginManager : 注册到
    IPlugin --> IPluginInfo : 通过 plugin_info 属性访问
```

### 6.1 PluginServices 架构

```mermaid
graph LR
    subgraph PluginServices [PluginServices 容器]
        LLM[llm_facade<br/>LLMPluginService]
        DP[data_provider<br/>DataProvider]
        TM[task_manager<br/>BackgroundTaskManager]
        LG[logger<br/>LoggerManager]
        MCM[mcp_manager<br/>MCPManager]
        MCC[mcp_client<br/>MCPClientManager]
        FTM[font_manager<br/>FontManager]
    end

    PluginServices --> LLM
    PluginServices --> DP
    PluginServices --> TM
    PluginServices --> LG
    PluginServices --> MCM
    PluginServices --> MCC
    PluginServices --> FTM
```

| 服务字段 | 类型 | 说明 |
|----------|------|------|
| `llm_facade` | `LLMPluginService` | LLM 服务入口（单例） |
| `data_provider` | `DataProvider` | 数据持久化服务 |
| `task_manager` | `BackgroundTaskManager` | 后台任务管理 |
| `logger` | `ILogger` | 日志服务 |
| `mcp_manager` | `MCPManager` | MCP Server 管理器 |
| `mcp_client` | `MCPClientManager` | MCP 外部连接管理器 |
| `font_manager` | `FontManager` | 字体管理器（安装/卸载/系统回退解析，`core/font`） |

---

## 7. 插件生命周期

```mermaid
stateDiagram-v2
    [*] --> 初始化: 应用启动
    初始化 --> 扫描目录: PluginManager 初始化
    扫描目录 --> 动态导入: 遍历子目录
    动态导入 --> 生成UUID: 找到 IPlugin 子类
    生成UUID --> 实例化: PluginIdentity 生成/加载
    实例化 --> 回调: on_plugin_loaded()
    回调 --> 注册表: 写入 _plugin_registry
    注册表 --> 注册API: _auto_register_plugin_api
    注册API --> 注册面板: UI 层构建 SkillsPanel
    注册面板 --> 等待点击: 用户交互
    等待点击 --> 创建UI: 首次点击
    等待点击 --> 返回缓存: 后续点击
    创建UI --> 缓存Widget: Widget 创建完成
    缓存Widget --> 等待点击
    返回缓存 --> 等待点击
```

> **说明**：「注册面板」及之后的状态属于 UI 层——`PluginManager` 的加载链路止于「写入 `_plugin_registry` 并调用 `_auto_register_plugin_api()`」；SkillsPanel 由 `ui/main_window.py` 在 `load_plugins()` 完成后构建，通过 `load_skills_from_manager()` 读取已加载插件。

---

## 8. 相关文档

- [IPlugin 接口](iplugin.md)
- [PluginManager](plugin-manager.md)
- [插件开发指南](plugin-development.md)
- [MCP 协议模块概述](../mcp/overview.md)
