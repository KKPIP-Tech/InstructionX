# InstructionX 技术架构分析文档

> 深入分析 InstructionX 项目各模块的职责边界、模块间有机结合、数据流转与调用链路。
> **以代码为准**：若文档描述与代码实现不一致，以代码为准。

---

## 目录

1. [概述](#1-概述)
2. [系统架构总览](#2-系统架构总览)
3. [接口层详解](#3-接口层详解)
4. [插件系统](#4-插件系统)
5. [数据层](#5-数据层)
6. [后台任务系统](#6-后台任务系统)
7. [LLM 框架](#7-llm-框架)
8. [UI 层](#8-ui-层)
9. [样式系统](#9-样式系统)
10. [通信模式与调用链](#10-通信模式与调用链)
11. [设计模式分析](#11-设计模式分析)
12. [代码与文档不一致问题](#12-代码与文档不一致问题)
13. [插件开发指南](#13-插件开发指南)
14. [附录](#14-附录)

---

## 1. 概述

### 1.1 项目背景与定位

**InstructionX** 是一个基于 **PySide6** 的插件式桌面应用程序框架，定位为"AI 助手桌面客户端"。它将 LLM 对话、工具插件、后台任务统一整合在一个 Qt 界面中，支持热插拔插件和 MCP（Model Context Protocol）函数调用。

### 1.2 技术栈

| 技术 | 版本 | 角色 |
|------|------|------|
| Python | >=3.14 | 编程语言 |
| PySide6 | >=6.10 | Qt for Python，UI 框架 |
| SQLite + WAL | — | DataProvider 默认持久化后端（插件数据） |
| JSON | — | TaskStorage 持久化格式；DataProvider 应急回退后端 |
| Windows | 10 / 11 | 目标平台 |

### 1.3 核心设计原则

- **单例模式**：6 个核心服务 + 2 个内部单例，全部以单例形式运行
  - **核心服务**：PluginManager、DataProvider、BackgroundTaskManager、LLMProvider、LLMPluginService、MCPManager
  - `DataProvider`、`BackgroundTaskManager`、`LLMProvider` 使用 `__new__` + `threading.Lock` 双重检查锁定
  - `PluginManager` 使用 `__new__` + `_initialized` 标志简化模式（无独立 `_lock`）
  - `LLMPluginService`、`MCPManager` 使用模块级锁 + 全局变量工厂函数（`get_llm_plugin_service()` / `get_mcp_manager()`）
  - **内部单例**：`TaskStorage`（BackgroundTaskManager 内部使用）、`LoggerManager`（框架日志中枢）
- **LLM 双重入口**：`LLMProvider` 为底层核心，`LLMPluginService` 为插件开发者入口，两者通过 `get_llm_provider()` / `get_llm_plugin_service()` 获取
- **接口契约优于实现**：`core/interfaces/` 定义所有核心接口，插件通过接口与框架交互
- **Widget 缓存复用**：IPlugin 的 `get_widget()` 实现控件缓存，避免重复创建
- **原子写入**：DataProvider 默认使用 SQLite WAL + 事务保证数据一致性；TaskStorage 等 JSON 持久化仍使用 temp-file + `os.replace()` 保证数据不损坏
- **MCP 导出能力**：所有插件 API 可通过 `get_all_function_tools()` 导出为 OpenAI 风格的 function calling 工具

### 1.4 术语表

| 术语 | 含义 |
|------|------|
| IPlugin | 插件抽象基类，定义插件必须实现的契约 |
| Widget 缓存 | IPlugin.get_widget() 的控件复用机制 |
| Provider | LLM 提供商实现（MiniMax/GLM/SiliconFlow/Ollama/OpenAI） |
| MCP | Model Context Protocol，函数调用规范 |
| QSS | Qt Style Sheets，Qt 样式表 |
| 单例 | 全局唯一实例设计模式 |
| Pub/Sub | 发布-订阅通信模式 |

---

## 2. 系统架构总览

### 2.1 整体架构图

```mermaid
graph TB
    subgraph UI ["UI Layer"]
        MW[InstructionXMainWindow]
        TB[CustomTitleBar]
        SP[SkillsPanel]
        WA[WorkArea]
        DL[Dialog]
    end

    subgraph Core ["Core Layer"]
        subgraph CorePlugin ["Plugin System"]
            PM[PluginManager]
            IPlugin[IPlugin]
        end
        subgraph CoreData ["Data Layer"]
            DP[DataProvider]
        end
        subgraph CoreTask ["Task System"]
            BTM[BackgroundTaskManager]
            TS[TaskStorage]
        end
        subgraph CoreLLM ["LLM Layer"]
            LLMS[LLMPluginService<br/>插件开发者入口]
            LLMP[LLMProvider<br/>LLM 核心层]
            subgraph CoreLLMProv ["Providers (全部5家)"]
                MINIMAX[MiniMaxProvider]
                GLM[GLMProvider]
                SF[SiliconFlowProvider]
                OLLAMA[OllamaProvider]
                OPENAI[OpenAIProvider]
            end
        end
        subgraph CoreFont ["Font System"]
            FM[FontManager<br/>core/font]
        end
    end

    subgraph Interfaces ["Interface Layer"]
        IPlugin_IF[IPlugin]
        IPluginInfo_IF[IPluginInfo]
        IDataProvider_IF[IDataProvider]
        ITaskManager_IF[ITaskManager]
        ILLMService_IF[ILLMService]
        ILogger_IF[ILogger]
        PS[PluginServices<br/>DI 容器]
    end

    subgraph Plugins ["Plugins"]
        OFFICIAL[官方/示例插件<br/>plugin/（仅用于本地开发验证，非框架捆绑列表）]
        OTHER[第三方插件<br/>（通过 GitHub 安装至 custom_plugin/）]
    end

    subgraph Utils ["Utils"]
        UKIT[InstructionX_UIKit + uikit_theme<br/>全局主题]
        LOGGING[LoggerManager]
    end

    MW --> TB
    MW --> SP
    MW --> WA
    MW --> DL

    SP -->|skill_clicked| MW
    MW -->|activate| WA

    PM -.->|创建并注入| PS
    PS -.->|llm_facade| LLMS
    PS -.->|font_manager| FM
    PM -->|load/manage| Plugins
    PM -->|API registry| IPlugin_IF

    DP -->|pub/sub| Plugins

    BTM -->|task scheduling| TS

    LLMS --> LLMP
    LLMP -->|route| CoreLLMProv
    LLMP -->|config| CoreLLM

    UI -->|access| CorePlugin
    UI -->|access| CoreData
    UI -->|access| CoreLLM

    Plugins -->|inherit| IPlugin
    Plugins -->|depend on| IDataProvider_IF
    Plugins -->|depend on| ITaskManager_IF
    Plugins -->|depend on| ILLMService_IF

    Interfaces -->|define| Core
    UKIT -->|style| UI
```

### 2.2 四大核心子系统关系

```mermaid
graph LR
    PM[PluginManager] -->|lifecycle| DP[DataProvider]
    PM -->|lifecycle| BTM[BackgroundTaskManager]
    PM -->|lifecycle| LLMP[LLMProvider]
    PM -->|lifecycle| LLMS[LLMPluginService]

    DP -.->|persist| storage[data/data.db]
    BTM -.->|persist| taskstore[data/tasks.json]
    LLMP -.->|config| llmcfg[llm_providers.json]
    LLMS --> LLMP
    PM -.->|order| porder[plugin_order.json]
```

| 核心服务 | 职责 | 单例获取方式 |
|----------|------|-------------|
| PluginManager | 插件加载/注册/排序/API | `PluginManager()` |
| DataProvider | 数据持久化/PubSub | `DataProvider()` |
| BackgroundTaskManager | 任务调度/执行 | `BackgroundTaskManager()` |
| LLMProvider | LLM 多提供商门面 | `get_llm_provider()` |
| LLMPluginService | LLM 插件服务层 | `get_llm_plugin_service()` |
| MCPManager | MCP 协议协调器 | `get_mcp_manager()` |

### 2.3 单例实例一览

| 单例 | 文件 | 用途 | 类型 |
|------|------|------|------|
| PluginManager | `core/plugin/manager.py` | 插件生命周期管理 | 核心服务 |
| DataProvider | `core/data/data_provider.py` | 数据中枢与通信 | 核心服务 |
| BackgroundTaskManager | `core/task/background_task.py` | 任务调度执行 | 核心服务 |
| LLMProvider | `core/llm/llm_provider.py` | LLM 核心层（底层） | 核心服务 |
| LLMPluginService | `core/llm/plugin_service.py` | LLM 插件服务层（开发者入口） | 核心服务 |
| MCPManager | `core/mcp/manager.py` | MCP 协议协调器 | 核心服务 |
| TaskStorage | `core/task/task_storage.py` | 任务状态持久化 | 内部单例 |
| LoggerManager | `utils/logging_tools.py` | 日志记录 | 内部单例 |

---

## 3. 接口层详解

### 3.1 接口层设计理念

接口层（`core/interfaces/`）定义了所有核心服务与插件之间的契约。框架通过接口实现了**依赖倒置**：插件依赖抽象接口而非具体实现，从而实现了插件的热插拔能力。

### 3.2 IPlugin 接口

**文件**：`core/interfaces/i_plugin.py`（纯接口）与 `core/plugin/plugin_interface.py`（带缓存实现）

**重要**：存在**两套 IPlugin**：
- `core/interfaces/i_plugin.py` —— 纯抽象基类，无实现
- `core/plugin/plugin_interface.py` —— 带 Widget 缓存实现的版本，是**实际被插件继承**的类。其 docstring 注明"此文件已迁移至 core/interfaces/i_plugin.py，此处保留作为向后兼容的导入路径"

**核心方法**：

| 方法 | 用途 |
|------|------|
| `plugin_name` (property) | 插件显示名称 |
| `_create_widget(parent, data_provider)` | 创建 Qt 控件（抽象方法） |
| `get_widget(parent, data_provider)` | 获取控件（含缓存复用逻辑） |
| `skill_icon` (property) | 技能面板图标 |
| `skill_description` (property) | 技能描述 |
| `skill_tooltip` (property) | 悬浮提示 |
| `plugin_id` (property) | UUID 标识符 |
| `on_plugin_loaded(plugin_id=None, **kwargs)` | 加载完成回调（可重写，services 通过 self._services 访问） |
| `plugin_info` (property) | 获取 IPluginInfo 实例 |

**我依赖谁**：
- `core/plugin/plugin_interface.py` 的 `IPlugin` 依赖 `core/plugin/plugin_info_interface.py` 的 `IPluginInfo`

**谁依赖我**：
- `core/plugin/manager.py` 的 `PluginManager` 依赖 `IPlugin`（`isinstance` 检查）
- 所有插件继承 `IPlugin`

### 3.3 IPluginInfo 接口

**文件**：`core/interfaces/i_plugin_info.py` 与 `core/plugin/plugin_info_interface.py`

定义插件元数据：

| 属性 | 用途 |
|------|------|
| `version` | PluginVersion 版本对象 |
| `developer` | 开发者名称 |
| `service_api` | API 方法描述字典（格式：`{method_name: {description, parameters, returns}}`） |
| `skill_icon` | PluginIcon 图标对象 |
| `skill_description` | 技能描述 |
| `plugin_type_id` | 插件类型标识符 |

### 3.4 IDataProvider 接口

**文件**：`core/interfaces/i_data_provider.py`

```python
class IDataProvider(ABC):
    # 插件管理
    def register_plugin(instance_id, plugin_type) -> None
    def unregister_plugin(instance_id) -> None
    def set_active_instance(instance_id) -> None
    def get_active_instance(plugin_type) -> str

    # 数据读写
    def get_plugin_data(instance_id, key, namespace=PRIVATE, default=None) -> Any
    def set_plugin_data(instance_id, key, value, namespace=PRIVATE, notify=True) -> None
    def get_all_plugin_data(instance_id, namespace=PRIVATE) -> Dict

    # 发布/订阅
    def subscribe(subscriber_id, target_plugin_id, target_key, callback) -> None
    def unsubscribe(subscriber_id, target_plugin_id=None) -> None
    def publish(publisher_id, key, value, namespace=PUBLIC) -> None

    # 资源管理
    def save_asset(plugin_id, filename, content) -> str
    def get_asset_path(relative_path) -> str
    def load_asset(relative_path) -> bytes
```

### 3.5 ITaskManager 接口

**文件**：`core/interfaces/i_task_manager.py`

定义 4 类任务类型（`TaskType`）：`SYNC`、`ASYNC`、`SCHEDULED`、`LONG_RUNNING`。

### 3.6 ILLMService 接口

**文件**：`core/interfaces/i_llm_service.py`（取代已删除的 `i_llm_facade.py`）

定义插件访问 LLM 能力的唯一抽象契约，`LLMPluginService` **显式继承**该接口（接口即契约，不再是 Duck Typing）。所有 `provider` 参数语义为**实例 id**，取 `"default"`（`DEFAULT_PROVIDER`）时由底层按功能维度（chat/embedding）解析为默认实例；`model` 参数取 `"default"`（`DEFAULT_MODEL`）时使用实例配置中的默认模型。

**注意**：接口层在运行时不导入 `core.llm`（类型仅 `TYPE_CHECKING` 导入，避免循环依赖与重量依赖），因此签名默认值以字面量 `"default"` 标注。以下方法签名以代码为准：

```python
# 直接对话（无会话状态）
def chat(messages, provider="default", model="default", ...) -> ChatResponse
def stream_chat(messages, callback, provider="default", ...) -> str
def embed(texts, provider="default", model="default") -> List[EmbeddingResponse]

# 会话管理
def create_conversation(system_prompt=None, provider="default", ...) -> str
def send_message(conv_id, content, images=None, model=None, provider=None, ...) -> str
def stream_send_message(conv_id, content, callback=None, ...) -> str
def get_conversation(conv_id) -> Optional[Conversation]
def list_conversations() -> List[Conversation]
def delete_conversation(conv_id) -> bool

# 工具调用
def get_tool_executor() -> ToolCallExecutor
def get_shared_tool_registry() -> ToolRegistry
def chat_with_tools(messages, provider="default", max_turns=5, ...) -> ToolChatResult
def chat_with_tools_stream(messages, callback, ...) -> ToolChatResult

# 多模态
def generate_image(prompt, provider="default", ...) -> ImageResult
def text_to_speech(text, provider="default", ...) -> AudioResult

# 实例与模型查询
def list_providers() -> List[ProviderInfo]
def get_models(provider="default") -> List[ModelInfo]
def resolve_provider_id(provider) -> str
def get_default_provider_id(feature="chat") -> Optional[str]

# 统计与校验
def get_usage_stats(conversation_id=None) -> Optional[UsageStats]
def validate_provider(provider) -> Tuple[bool, str]
@property
def last_stream_response() -> Optional[ChatResponse]
```

**已移除的旧接口方法**（底层泄漏，破坏性切换）：`get_provider` / `get_all_providers` / `get_raw_provider` / `get_cached_models` / `load_image_as_base64`（后者迁至 `utils/image_utils.py`）。旧 `get_available_providers()` 由 `list_providers()` 取代。迁移对照见 `temp/llm-api-v2-migration.md`。

### 3.7 PluginServices（依赖注入容器）

**文件**：`core/interfaces/plugin_services.py`

```python
@dataclass
class PluginServices:
    llm_facade: "ILLMService"              # LLM 服务（必需字段，实际为 LLMPluginService 单例）
    data_provider: "DataProvider"               # 数据服务（必需字段）
    task_manager: "BackgroundTaskManager"       # 任务服务（必需字段）
    logger: "ILogger"                           # 日志服务（必需字段）
    mcp_manager: "MCPManager" = field(default=None)       # MCP Server 管理器
    mcp_client: "MCPClientManager" = field(default=None)  # MCP Client 管理器
    font_manager: "FontManager" = field(default=None)     # 字体管理器（core/font，无降级保护、始终注入）
    localization: "ILocalizationFacade" = field(default=None)  # 多语言取词门面（绑定本插件 UUID，无降级保护、始终注入；实现为 PluginI18nFacade）
```

**使用方式**：PluginManager 通过 `_create_plugin_services(plugin_id)` 创建容器实例（传入 `plugin_id` 用于绑定取词门面），在加载插件时通过 `services` 参数注入。详见 [PluginManager](../core/plugin-system/plugin-manager.md)。

---

## 4. 插件系统

### 4.1 PluginManager 单例架构

**文件**：`core/plugin/manager.py`

**核心职责**：动态加载插件、管理插件注册表、提供跨插件 API 调用能力。

**关键属性**：

| 属性 | 类型 | 用途 |
|------|------|------|
| `_official_plugins` | `List[IPlugin]` | 官方插件实例列表 |
| `_thirdparty_plugins` | `List[IPlugin]` | 第三方插件实例列表 |
| `_plugin_registry` | `Dict[str, IPlugin]` | UUID → 插件实例映射 |
| `_plugin_name_to_id` | `Dict[str, str]` | 插件名 → UUID 映射 |
| `_api_registry` | `Dict[str, PluginAPI]` | UUID → API 容器映射 |

**我依赖谁**：
- `core/plugin/plugin_interface.py` 的 `IPlugin`
- `core/plugin/config_manager.py` 的 `PluginConfigManager`
- `core/plugin/plugin_identity.py` 的 `PluginIdentity`

**谁依赖我**：
- `ui/main_window.py` 的 `InstructionXMainWindow` —— 加载插件
- `ui/skills_panel/panel.py` 的 `SkillsPanel` —— 获取插件列表
- 所有通过 `call_plugin_method()` 发起跨插件调用的插件

### 4.2 插件发现与加载流程

```mermaid
sequenceDiagram
    participant PM as PluginManager
    participant Identity as PluginIdentity
    participant PI as IPlugin instance

    PM->>PM: load_plugins()
    PM->>PM: load_official_plugins() / load_thirdparty_plugins()
    loop for each plugin directory
        PM->>PM: load plugin from directory
        Note over PM: 1. check entrance.py exists
        Note over PM: 2. dynamic importlib import
        Note over PM: 3. isinstance check for IPlugin subclass
        PM->>Identity: PluginIdentity(plugin_dir)
        Identity->>Identity: load_or_create_id to generate/load UUID
        PM->>PI: plugin_instance = plugin_class()
        PM->>PI: set plugin_id on instance
        PM->>PI: plugin_instance.on_plugin_loaded()
        PM->>PM: add to plugin_registry by UUID
        PM->>PM: auto_register plugin API
        Note over PM: register service_api from information.py
    end
```

### 4.3 Widget 缓存复用机制

**文件**：`core/plugin/plugin_interface.py:54-98`

```mermaid
flowchart TD
    A[IPlugin.get_widget] --> G{cached_widget != None<br>但 C++ 对象已销毁?}
    G -->|是| H[丢弃失效缓存并 WARNING 日志]
    H --> B{cached_widget != None?}
    G -->|否| B
    B -->|"parent unchanged"| C[return cached widget]
    B -->|"parent changed"| D[setParent parent]
    D --> C
    B -->|"first creation"| E[_create_widget]
    E --> F[cache widget + parent]
    F --> C
```

> **失效缓存守卫**：`WorkArea.clear()` 的 `deleteLater()` 等路径会销毁控件的
> C++ 对象而不通知插件缓存。`get_widget()` 返回缓存前用 `shiboken6.isValid()`
> 校验存活，已销毁则丢弃缓存走重建路径，避免
> `RuntimeError: Internal C++ object already deleted`。

### 4.4 插件 API 注册与跨插件 RPC

**文件**：`core/plugin/manager.py`

```mermaid
flowchart LR
    subgraph AutoRegister [auto_register_plugin_api]
        A1[scan information.py] --> A2[find IPluginInfo subclass]
        A2 --> A3[read service_api dict]
        A3 --> A4[scan service.py]
        A4 --> A5[find class ending with 'Service']
        A5 --> A6[register_plugin_api]
    end

    subgraph CrossPlugin [call_plugin_method]
        B1[Plugin A calls] --> B2[find api_registry entry]
        B2 --> B3[find api_methods key]
        B3 --> B4[execute method]
    end
```

**⚠️ API 注册类名偏好**：`service.py` 中的类优先选择**名称以 `Service` 结尾**的类（如 `MyService`），如果未找到，则回退到第一个有效候选类。不再强制要求类名严格为 `Service`。

### 4.5 MCP 函数工具导出

**文件**：`core/plugin/manager.py`

```python
def get_all_function_tools(self) -> List[Dict[str, Any]]:
    # 格式: {type: "function", function: {name: "uuid.method", description, parameters}}
```

---

## 5. 数据层

### 5.1 DataProvider 单例架构

**文件**：`core/data/data_provider.py`

**核心职责**：插件数据的持久化、内存缓存、命名空间隔离、发布/订阅通信。

**持久化路径**：`data/data.db`（由 `core/data/data_provider.py` 确定；JSON 应急模式下为 `data/data.json`）

**SQLite 表结构**（默认后端）：
- `plugins`：插件实例元数据（`instance_id`, `plugin_type`, `active`）
- `plugin_data`：插件键值数据（`instance_id`, `namespace`, `key`, `value`）
- `active_instances`：当前活跃实例映射（`plugin_type`, `instance_id`）
- `db_metadata`：schema 版本与迁移来源

> 详细 schema 与迁移说明参见 [`docs/core/data-provider/overview.md`](../core/data-provider/overview.md)。

**JSON 应急后端格式**（仅当 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 时生效）：
```json
{
  "plugins": {
    "<instance_id>": {
      "type": "VideoEditor",
      "active": false,
      "private": {"key": "value"},
      "public": {"key": "value"}
    }
  },
  "active_instances": {"VideoEditor": "<instance_id>"}
}
```

### 5.2 原子写入机制

默认 SQLite 后端通过 `PRAGMA journal_mode = WAL` 与 SQLite 语句级/显式事务保证一致性：
- `set_plugin_data` 等单条写入使用 UPSERT 语句级原子性。
- `save_data` / `reset_all_data` / `set_active_instance` 使用 `BEGIN IMMEDIATE` 显式事务，异常时自动回滚。

JSON 应急后端仍保留旧的原子写入实现：
```python
# 仅 INSTRUCTIONX_DATAPROVIDER_BACKEND=json 时生效
def _json_write_to_disk(self, data):
    with open(self.temp_file, 'w') as f:   # 写入 data.json.tmp
        json.dump(data, f, ...)
    os.replace(self.temp_file, self.data_file)  # 原子重命名
```

**我依赖谁**：
- `core/interfaces/i_data_provider.py` 的 `IDataProvider`（实现该接口）

**谁依赖我**：
- 所有插件通过 `DataProvider()` 单例访问
- `core/task/task_storage.py` 的 `TaskStorage` 使用类似模式（独立持久化）

### 5.3 发布/订阅通信模型

```mermaid
sequenceDiagram
    participant Sub as Plugin B
    participant DP as DataProvider
    participant Pub as Plugin A

    Sub->>DP: subscribe(B, A, "data_key", callback)
    DP-->>DP: register (B, A, "data_key") to callback
    Pub->>DP: set_plugin_data(A, "data_key", new_value, PUBLIC, notify=True)
    DP->>DP: notify subscribers for key
    DP->>Sub: callback(A, "data_key", old, new)
```

---

## 6. 后台任务系统

### 6.1 BackgroundTaskManager 单例架构

**文件**：`core/task/background_task.py`

**核心职责**：管理 SYNC/ASYNC/SCHEDULED/LONG_RUNNING 四类任务的注册、执行、调度和持久化。

**线程模型**：
- 主线程：任务注册/控制
- `ThreadPoolExecutor`：4 个 worker 线程执行 ASYNC/SCHEDULED/LONG_RUNNING 任务
- daemon 线程 `_schedule_check_thread`：每秒检查 SCHEDULED 任务是否到期

### 6.2 三类任务模型

| 模型 | 文件 | 持久化 | 用途 |
|------|------|--------|------|
| `BackgroundTask` | `core/task/task_model.py` 的 `BackgroundTask` 类 | ✅ `data/tasks.json` 的 `tasks` 段 | 一次性同步/异步任务 |
| `ScheduledTask` | `core/task/task_model.py` 的 `ScheduledTask` 类 | ✅ `data/tasks.json` 的 `scheduled_tasks` 段 | 定时循环任务 |
| `LongRunningTask` | `core/task/task_model.py` 的 `LongRunningTask` 类 | ✅ `data/tasks.json` 的 `long_running_tasks` 段 | 长期驻留任务 |

**⚠️ 重要限制**：持久化时 `func` 和 `callback` 不序列化（`repr=False`），仅存储 args/kwargs。任务重启后必须通过**工厂注册机制**重新注入函数引用。

### 6.3 任务工厂恢复机制

```mermaid
sequenceDiagram
    participant App as Application
    participant BTM as BackgroundTaskManager
    participant Storage as TaskStorage
    participant Factory as Plugin

    App->>BTM: __init__()
    Note over BTM: scheduled_task_factories init<br/>daemon thread starts

    Factory->>BTM: register_scheduled_task_factory(plugin_id, func, callback)
    BTM->>BTM: save to scheduled_task_factories[plugin_id]
    BTM->>BTM: restore_scheduled_tasks(plugin_id)
    BTM->>Storage: get_scheduled_tasks_by_plugin(plugin_id)
    Storage-->>BTM: [stored_task_1, stored_task_2]
    loop for each stored_task
        BTM->>BTM: inject func and callback into task
        BTM->>BTM: add to runtime task list
    end

    Note over BTM: daemon checks periodically<br/>_check_scheduled_tasks()
    Note over BTM: restore func from factory if None
```

### 6.4 任务状态机

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING : task starts
    RUNNING --> COMPLETED : success
    RUNNING --> FAILED : exception
    RUNNING --> CANCELLED : cancelled

    Note right of PENDING: BackgroundTask created
    Note right of RUNNING: running in ThreadPoolExecutor
    Note right of COMPLETED: result stored, callback called

    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]

    PENDING --> CANCELLED : cancelled before execution
```

### 6.5 TaskScheduler 现状（轻量生命周期占位）

**文件**：`core/task/scheduler.py`

`TaskScheduler` 在 `BackgroundTaskManager` 中被实例化为 `self._scheduler` 并调用 `start()`。历史版本曾在后台线程中周期调用 `_check_and_run_tasks()`（空实现，线程每秒空醒一次）；该空转线程已**整体移除**，当前 `TaskScheduler` 仅保留 `start()`/`stop()` 生命周期接口以保持兼容，不承担调度职责。

**实际定时任务检查**由 `BackgroundTaskManager._check_scheduled_tasks()` daemon 线程承担，它使用 `SchedulerCallback` 类（同文件）判断并执行到期任务。

**结论**：`TaskScheduler` 是一个**轻量生命周期占位类**，`SchedulerCallback` 是实际工作的组件。

---

## 7. LLM 框架

### 7.1 LLMProvider 多提供商门面

**文件**：`core/llm/llm_provider.py`

**核心职责**：作为多提供商统一门面，路由 chat/stream_chat/embed 请求到具体 Provider。

**初始化流程**：
```
__init__() → LLMConfig() → _init_providers() → _fetch_all_models()
```

**我依赖谁**：
- `core/llm/config.py` 的 `LLMConfig`
- `core/llm/providers/__init__.py` 的 `get_provider_class()` + `PROVIDER_REGISTRY`

**谁依赖我**：
- `ui/dialog/llm_settings/` 包的各面板与 Worker（LLM 设置界面）
- `core/llm/plugin_service.py` 的 `LLMPluginService`
- 所有需要 LLM 能力的插件（经 `ILLMService` 门面间接使用）

### 7.2 适配器注册机制

**文件**：`core/llm/providers/__init__.py`

注册表 `PROVIDER_REGISTRY` 的键为**适配器家族（adapter）**而非厂商：多个预设可共享同一适配器；自定义实例（`preset_id=None`）固定使用 `openai-compatible` 兜底适配器。

```mermaid
graph LR
    A[register_adapter] -->|"adapter=glm"| B[PROVIDER_REGISTRY-glm-GLMProvider]
    C[register_adapter] -->|"adapter=minimax"| D[PROVIDER_REGISTRY-minimax-MiniMaxProvider]
    F[register_adapter] -->|"adapter=openai-compatible"| G[PROVIDER_REGISTRY-openai-compatible-OpenAICompatibleProvider]
    E[get_adapter_class] -->|query registry| B
```

模块导入时自动注册全部适配器（minimax / siliconflow / glm / ollama / openai / openai-compatible）。`register_provider` / `get_provider_class` / `get_all_provider_types` 为保留的旧名薄别名（语义同为适配器家族）。

`LLMProvider._create_provider()` 按实例配置中的 `adapter` 键查注册表创建实例；未知适配器记 ERROR 日志并跳过该实例，不影响其余实例。

### 7.3 内置预设与适配器

提供商元数据（显示名、默认端点、帮助链接、Logo、预设模型）外移到 `core/llm/catalog/` 目录数据（`ProviderPreset` + `PROVIDER_PRESETS`，共 5 家）；用户配置中的每个 Provider 是实例，经 `preset_id` 关联预设。

| 预设 | preset_id | 适配器 | 模型获取方式 | 特殊处理 |
|------|-----------|--------|------------|---------|
| MiniMax | `minimax` | `minimax` | 预设模型目录（目录层 PRESET_MODELS） | 图片需 base64 前缀 |
| GLM | `glm` | `glm` | 预设模型目录（7 类模型，含视频/音频） | 支持 function calling |
| SiliconFlow | `siliconflow` | `siliconflow` | API `/models` 动态获取 | 模型类型从 ID 推断 |
| Ollama | `ollama` | `ollama` | API `/api/tags` 动态获取 | 不需要 api_key（auth_optional） |
| OpenAI | `openai` | `openai` | API `/models` 动态获取 | OpenAI 兼容协议 |
| 自定义实例 | `null` | `openai-compatible` | 端点 `/models` 或 custom_models | 任意 OpenAI 兼容端点零代码接入 |

### 7.4 BaseProvider 模板方法

**文件**：`core/llm/providers/base.py`

```mermaid
classDiagram
    class ILLM {
        <<ABC>>
        +chat()
        +stream_chat()
        +embed()
        +async_chat()
    }

    class BaseProvider {
        -_session: requests.Session
        -_async_session: aiohttp.ClientSession
        +_make_request()
        +_make_stream_request()
        +_prepare_messages()
        +_get_fallback_models()
        +refresh_models()
        +close()
        +chat()*
        +embed()*
    }

    class MiniMaxProvider {
        +CHAT_MODELS: list
        +EMBEDDING_MODELS: list
        +chat()
    }

    class GLMProvider {
        +CHAT_MODELS: list
        +EMBEDDING_MODELS: list
        +fetch_and_cache_models()
    }

    ILLM <|.. BaseProvider
    BaseProvider <|-- MiniMaxProvider
    BaseProvider <|-- SiliconFlowProvider
    BaseProvider <|-- GLMProvider
    BaseProvider <|-- OllamaProvider
    BaseProvider <|-- OpenAIProvider
```

---

## 8. UI 层

### 8.1 无边框窗口设计

**文件**：`ui/main_window.py`（`InstructionXMainWindow.__init__`）

```python
self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
```

配合 `CustomTitleBar` 实现自定义窗口控制按钮（最小化/最大化/关闭）。

### 8.2 SkillsPanel 信号链

```mermaid
sequenceDiagram
    participant SB as SkillButton
    participant SP as SkillsPanel
    participant MW as InstructionXMainWindow
    participant WA as WorkArea
    participant Plugin as IPlugin

    SB->>SB: mousePressEvent / click
    SB->>SP: skill_clicked Signal(IPlugin)
    SP->>MW: skill_clicked Signal(IPlugin)
    MW->>WA: clear_keep_highlight()
    WA-->>MW: clear done (keep highlight)
    MW->>Plugin: plugin.get_widget(parent=work_area.get_widget())
    Plugin-->>MW: QWidget (cached)
    MW->>WA: add_widget(widget)
    WA-->>MW: widget displayed
```

### 8.3 WorkArea Widget 缓存策略

**文件**：`ui/work_area/work_area.py`

| 方法 | 行为 | 用途 |
|------|------|------|
| `clear()` | `deleteLater()` 删除控件 | 强制重建 |
| `clear_keep_highlight()` | `hide()` 隐藏控件 | 复用缓存，保留激活高亮 |

此设计配合 `IPlugin.get_widget()` 的缓存机制，实现**真正的 Widget 复用**。

---

## 9. 主题系统

### 9.1 UIKit 主题架构

**文件**：`ui/uikit_theme.py`（全局主题入口）+ `ui/InstructionX_UIKit/`（组件库：设计令牌 + ThemeManager）

```mermaid
flowchart TD
    A[apply_uikit_theme] --> B[auto 时 detect_system_theme - 读 Windows 注册表]
    B --> C[ThemeManager.apply - Fusion + QPalette + 全局字体]
    C --> D[ThemeManager.set_mode - 切换 LIGHT/DARK 令牌]
    D --> E[build_qss tokens - 令牌参数化生成全局 QSS]
    E --> F[app.setStyleSheet - build_qss + 排除区兼容附录]
```

### 9.2 排除区兼容附录

**文件**：`ui/uikit_theme.py` 的 `_build_compat_qss()`

为三个不做 UI 迁移的区域（CustomTitleBar、SkillsPanel/SkillButton、WorkArea 占位标签）保留原选择器结构/尺寸/字号，颜色全部实时取 UIKit 令牌 `T()`；附录拼接在全局 QSS 之后，凭更具体的选择器（objectName / 类名 / 动态属性）天然胜出。详见 [UIKit 主题系统](../utils/uikit-theme.md)。

---

## 10. 通信模式与调用链

### 10.1 四种通信模式对比

| 模式 | 适用场景 | 特点 |
|------|---------|------|
| **Qt Signals/Slots** | UI 内通信 | 线程安全（需QueuedConnection跨线程），同步 |
| **DataProvider Pub/Sub** | 插件间响应式通信 | 同线程同步执行，跨插件数据变化通知 |
| **PluginManager API Registry** | 插件间同步调用 | 同步 RPC，基于 UUID + 方法名查找 |
| **Task Callbacks** | 后台任务完成通知 | 线程池回调，可能跨线程 |

### 10.2 典型调用链：LLM 聊天请求

```mermaid
sequenceDiagram
    participant UI as Chat UI
    participant Worker as ChatWorker
    participant Service as LLMChatService
    participant LLMP as LLMProvider
    participant Prov as Provider

    UI->>Worker: send_message(messages)
    Worker->>Service: stream_send_message / sync_send_message
    Service->>LLMP: provider.stream_chat / chat
    LLMP->>LLMP: get_enabled_providers("chat")
    LLMP->>Prov: provider.stream_chat(messages)
    Prov-->>Prov: make HTTP stream request
    Prov-->>Service: ChatResponse chunks
    Service-->>Worker: chunk_received signal
    Worker-->>UI: update UI
    Prov-->>Service: ChatResponse final
    Service-->Worker: finished signal
    Worker-->>UI: display final result
```

### 10.3 典型调用链：定时任务注册与执行

```mermaid
sequenceDiagram
    participant Plugin as Plugin
    participant BTM as BackgroundTaskManager
    participant Storage as TaskStorage
    participant Daemon as Daemon Thread

    Note over Plugin,BTM: Registration phase at startup
    Plugin->>BTM: register_scheduled_task_factory(plugin_id, func, callback)
    BTM->>BTM: save to scheduled_task_factories[plugin_id]
    BTM->>BTM: restore_scheduled_tasks(plugin_id)
    BTM->>Storage: get_scheduled_tasks_by_plugin(plugin_id)
    Storage-->>BTM: stored_tasks (args/kwargs only, no func)
    BTM->>BTM: inject func and callback from factory
    BTM->>BTM: add to runtime task list

    Note over Daemon: Execution phase (checks every second)
    Daemon->>BTM: check scheduled tasks
    loop for each scheduled_task
        alt func is None
            BTM->>BTM: restore from factory
        end
        alt should_run is True
            BTM->>BTM: execute scheduled task
            BTM->>BTM: executor.submit with callback
            BTM->>Storage: update next_run timestamp
        end
    end
```

---

## 11. 设计模式分析

| 模式 | 应用位置 | 实现方式 |
|------|---------|---------|
| **单例** | 4 个核心服务 | `__new__` + `_lock` 双重检查锁定 |
| **模板方法** | `BaseProvider` | 基类提供 HTTP 骨架，子类实现 API 端点/响应解析 |
| **观察者/Pub-Sub** | `DataProvider` | `_subscriptions` 字典 + 回调分发 |
| **门面/Facade** | `LLMProvider` | 路由到具体 Provider，隐藏复杂度 |
| **工厂方法** | 任务恢复 | `_scheduled_task_factories[plugin_id]` 注册函数引用 |
| **装饰器** | `@register_provider` | `PROVIDER_REGISTRY` 全局注册表 |
| **Widget 缓存** | `IPlugin.get_widget()` | `_cached_widget` + `_cached_parent` 判断 |

---

## 12. 代码与文档不一致问题

### 12.1 TaskStatus.STOPPED 枚举（已修复）

| 位置 | 内容 |
|------|------|
| `core/interfaces/i_task_manager.py` | `TaskStatus` 枚举的**单一来源**，含 `STOPPED = "stopped"` |
| `core/task/task_model.py` | 从接口层 re-export（`from ..interfaces.i_task_manager import TaskType, TaskStatus`），保持旧导入路径可用 |
| `core/task/background_task.py` | 长期任务状态使用 `LONG_TASK_STATUS_*` 字符串常量比较（`LONG_TASK_STATUS_COMPLETED/FAILED/STOPPED`） |

**判断**：`STOPPED` 状态枚举的唯一定义在接口层 `i_task_manager.py`，`task_model.py` 仅 re-export。附录 B 中已标记为"已修复"。`LongRunningTask.current_status` 仍使用字符串常量比较而非枚举，但这是局部实现细节，不影响枚举本身的可用性。

### 12.2 TaskScheduler 轻量生命周期占位

`core/task/scheduler.py` 的 `TaskScheduler` 类：
- 在 `BackgroundTaskManager.__init__` 中被实例化为 `self._scheduler`，启动时调用 `self._scheduler.start()`
- 历史版本的空转线程（周期调用空实现的 `_check_and_run_tasks()`）已**整体移除**
- 当前仅保留 `start()`/`stop()` 生命周期接口以保持兼容，不承担调度职责

**实际工作者**：`BackgroundTaskManager._check_scheduled_tasks()` daemon 线程 + 同文件的 `SchedulerCallback` 类。

### 12.3 定时任务恢复由工厂注册触发

定时任务恢复**没有全局恢复入口**：插件调用 `register_scheduled_task_factory()` 注册工厂时，内部自动调用 `restore_scheduled_tasks(plugin_id)` 按插件恢复（见 `core/task/background_task.py`）。历史版本中遗留的 `_restore_all_scheduled_tasks()` 方法已随重构移除。

### 12.4 PluginServices DI 容器

PluginManager 通过 `_create_plugin_services(plugin_id)` 创建 `PluginServices` 容器（传入 `plugin_id` 用于绑定 `PluginI18nFacade` 取词门面），并通过构造器参数注入到各插件中。新版插件通过 `self._services` 访问服务，旧版插件可通过直接导入单例兼容访问。

### 12.5 API 注册类名偏好

`core/plugin/manager.py` 的 API 自动注册逻辑：
```python
if attr.__name__.endswith('Service'):
    service_class = attr
    break
```
优先选择名称以 `Service` 结尾的类，未找到时回退到第一个有效候选类。

---

## 13. 插件开发指南

### 13.1 插件目录结构

```
plugin_name/
├── __init__.py          # 空文件，Python 包标识
├── entrance.py          # 必需：定义 IPlugin 子类
├── information.py       # 必需：定义 IPluginInfo 子类 + service_api
├── service.py           # 必需：定义 Service 类（类名以 Service 结尾优先）
├── config/              # 必需：插件配置文件目录
└── assets/              # 可选：静态资源文件
```

### 13.2 entrance.py 编写规范

```python
from core.plugin.plugin_interface import IPlugin

class MyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        return "我的插件"

    def _create_widget(self, parent=None, data_provider=None) -> QWidget:
        widget = QWidget(parent)
        # ... 构建 UI ...
        return widget

    def on_plugin_loaded(self) -> None:
        # 注册定时任务工厂（导入位于文件顶部，本例仅示意调用方式）
        BackgroundTaskManager().register_scheduled_task_factory(
            self.plugin_id, self.my_task_func, self.on_task_done
        )
```

### 13.3 information.py service_api 定义

```python
from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon

class MyPluginInfo(IPluginInfo):
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")

    @property
    def service_api(self) -> dict:
        return {
            "do_something": {
                "description": "执行某个操作",
                "parameters": {
                    "input": {"type": "string", "description": "输入内容", "required": True}
                },
                "returns": {"type": "string"}
            }
        }
```

### 13.4 service.py 编写规范

```python
# 类名建议以 "Service" 结尾（优先选择），未找到时回退到第一个有效类
class Service:
    def __init__(self):
        pass

    def do_something(self, input: str) -> str:
        return f"处理结果: {input}"
```

---

## 14. 附录

### 附录 A：文件清单

#### 核心接口层 (`core/interfaces/`)

| 文件 | 核心职责 |
|------|---------|
| `i_plugin.py` | IPlugin 纯接口定义 |
| `i_plugin_info.py` | IPluginInfo 接口定义 |
| `i_data_provider.py` | IDataProvider 接口 + DataNamespace 枚举 |
| `i_task_manager.py` | ITaskManager 接口 + TaskType/TaskStatus 枚举 |
| `i_llm_service.py` | ILLMService 接口（LLM 插件服务抽象契约） |
| `i_logger.py` | ILogger 接口 |
| `plugin_services.py` | PluginServices DI 容器 |

#### 插件系统 (`core/plugin/`)

| 文件 | 核心职责 |
|------|---------|
| `manager.py` | PluginManager 单例，插件加载/API 注册 |
| `plugin_interface.py` | IPlugin 带缓存实现 |
| `plugin_info_interface.py` | IPluginInfo 实现（向后兼容导出） |
| `config_manager.py` | PluginConfigManager，插件排序持久化 |
| `plugin_groups.py` | PluginGroup + PluginGroupStore，用户自定义分组存储（config/plugin_groups.json） |
| `plugin_registry.py` | 已安装插件注册表（config/plugin_registry.json：版本/来源/安装时间，升级降级依据） |
| `tool_name.py` | 工具命名/清洗工具 |
| `plugin_identity.py` | PluginIdentity，UUID 生成/持久化 |
| `plugin_version.py` | PluginVersion 版本解析与比较 |
| `plugin_icon.py` | PluginIcon 图标处理（5 种来源） |

#### 数据层 (`core/data/`)

| 文件 | 核心职责 |
|------|---------|
| `data_provider.py` | DataProvider 单例，pub/sub/原子写入/后端路由 |
| `sqlite_backend.py` | SQLiteBackend：连接、DDL、事务、按 key CRUD、LRU 缓存、迁移 |
| `sql_map.py` | SQLMap：SQL 语句集中管理 |
| `schema_migrations.py` | Schema 版本注册表与迁移脚本 |

#### 任务系统 (`core/task/`)

| 文件 | 核心职责 |
|------|---------|
| `background_task.py` | BackgroundTaskManager 单例，调度核心 |
| `task_model.py` | BackgroundTask/ScheduledTask/LongRunningTask 模型 |
| `scheduler.py` | TaskScheduler（轻量生命周期占位，空转线程已移除）+ SchedulerCallback |
| `__init__.py` | 模块导出 |

#### 字体子系统 (`core/font/`)

| 文件 | 核心职责 |
|------|---------|
| `manager.py` | FontManager 单例：字体安装/卸载、注册表持久化（data/fonts/fonts.json 原子写）、QFontDatabase 应用级注册、系统字体回退解析 |
| `font_record.py` | FontRecord 字体注册记录（frozen dataclass） |
| `exceptions.py` | FontInstallError 字体安装失败异常 |

#### LLM 层 (`core/llm/`)

| 文件 | 核心职责 |
|------|---------|
| `llm_provider.py` | LLMProvider 单例，多提供商门面（adapter 分发 / check_* / 惰性刷新） |
| `provider_interface.py` | ILLM 抽象基类 + 数据类型（Message、ChatResponse、ToolCall、ModelInfo、ModelCheckResult 等） |
| `model_schema.py` | 统一模型 schema（capabilities 闭集、normalize、三路合并、分组推断） |
| `catalog/` | 提供商预设目录（ProviderPreset / PROVIDER_PRESETS / PRESET_MODELS / logos/） |
| `config.py` | LLMConfig（单例 + 变更订阅 + schema v2 迁移）/ ProviderConfig（实例配置） |
| `exceptions.py` | LLM 异常体系（9 类） |
| `types.py` | LLM 服务层数据类型（Conversation、ProviderInfo、ToolChatResult、ToolDefinition、UsageStats、UsageRecord 等） |
| `pricing.py` | DEFAULT_PRICING 定价表 |
| `conversation_manager.py` | ConversationManager 对话生命周期管理 |
| `tool_call_executor.py` | ToolCallExecutor / ToolRegistry 工具调用自动化 |
| `plugin_service.py` | LLMPluginService 插件开发者主入口（ILLMService 实现） |
| `types_cache.py` | CacheInfo / CacheType 缓存信息类型 |
| `cache_adapter.py` | CacheAdapter 缓存适配器 + DEFAULT_CACHE_CONFIG |
| `usage_record_store.py` | UsageRecordStore 用量记录持久化（data/llm_usage.json） |
| `providers/__init__.py` | PROVIDER_REGISTRY（adapter→类）+ register_adapter + 旧名薄别名 |
| `providers/base.py` | BaseProvider 模板方法基类 |
| `providers/minimax.py` | MiniMaxProvider 实现 |
| `providers/glm.py` | GLMProvider 实现 |
| `providers/siliconflow.py` | SiliconFlowProvider 实现 |
| `providers/ollama.py` | OllamaProvider 实现 |
| `providers/openai.py` | OpenAIProvider 实现 |
| `providers/openai_compatible.py` | OpenAICompatibleProvider（自定义 OpenAI 兼容兜底适配器） |

#### UI 层 (`ui/`)

| 文件 | 核心职责 |
|------|---------|
| `InstructionX_UIKit/` | UIKit 组件库（设计令牌 + ThemeManager + 组件/布局/图表，同步副本不修改） |
| `uikit_bootstrap.py` | sys.path 引导（使 UIKit 以顶层包可导入） |
| `uikit_theme.py` | 全局主题入口（apply_uikit_theme + 排除区兼容附录） |
| `main_window.py` | InstructionXMainWindow 主窗口 |
| `title_bar.py` | CustomTitleBar 自定义标题栏 |
| `usage_panel/` | UsagePanel 用量查询面板（包：panel/kpi_card/trend_chart/history_table/formatting） |
| `skills_panel/panel.py` | SkillsPanel 技能面板 |
| `skills_panel/plugin_group_widget.py` | 分组折叠控件 |
| `skills_panel/skill_button.py` | SkillButton 技能按钮 |
| `tray/` | 系统托盘子系统（TrayIconManager 门面 + TrayBackend 后端注册表） |
| `work_area/work_area.py` | WorkArea 工作区 |
| `dialog/about_dialog.py` | 关于对话框 |
| `dialog/license_dialog.py` | 开源许可对话框 |
| `dialog/close_confirm_dialog.py` | 关闭确认对话框（退出/最小化到托盘/取消） |
| `dialog/llm_settings/` | LLM 设置对话框包（dialog/provider_list_panel/provider_detail_panel/model_section/provider_editor_dialog/model_edit_dialog/health_check_dialog/sync_models_dialog/workers/theme/feedback/icons/widgets/constants） |
| `dialog/plugin_management_dialog.py` | 插件管理对话框（安装/升级/降级/卸载 + 分组与排序） |
| `dialog/plugin_order_dialog.py` | 插件排序对话框（拖拽） |
| `dialog/github_plugin_install_dialog.py` | GitHub 插件安装对话框 |

#### 工具层 (`utils/`)

| 文件 | 核心职责 |
|------|---------|
| `logging_tools.py` | LoggerManager 单例，旋转日志 |
| `i_logger.py` | ILogger 接口 |
| `image_utils.py` | 图片工具（load_image_as_base64） |
| `thread_utils.py` | 工作线程 → UI 线程封送 |

#### 配置文件结构

| 文件 | 结构 |
|------|------|
| `config/plugin_order.json` | `{official_plugins: [uuid], thirdparty_plugins: [uuid]}` |
| `config/plugin_groups.json` | schema v2：`{version: 2, official: {groups, order}, thirdparty: {groups, order}}`（分组定义 + 面板统一顺序，分组与未分组插件混排） |
| `config/plugin_registry.json` | 已安装插件注册表：`{version, plugins: {uuid: {descriptor_id, name, scope, version, installed_at, source_type, source_url}}}`（升级降级与更新检查依据） |
| `config/llm_providers.json` | schema v2：`{version: 2, providers: {instance_id: {preset_id, adapter, api_key, base_url, chat_model, order, ...}}}` |
| `config/llm_models_cache.json` | `{instance_id: [ModelInfo] 或 {timestamp, models}}`（键为实例 id） |
| `config/mcp_config.json` | `{server: {...}, remote_servers: [...]}` |
| `data/data.db` | SQLite 数据库：plugins、plugin_data、active_instances 表 |
| `data/data.json` | `{plugins: {id: {type, active, private, public}}, active_instances: {}}`（JSON 应急后端） |
| `data/tasks.json` | `{tasks: {}, scheduled_tasks: {}, long_running_tasks: {}}`（任务记录含 `func_name` 字段，用于重启后精确匹配工厂函数） |
| `data/llm_usage.json` | `{"version": 1, "records": [UsageRecord, ...]}`（schema v1：顶层对象 + records 数组） |
| `data/conversations.json` | LLM 会话持久化 |

### 附录 B：已知问题汇总

| # | 问题 | 严重程度 | 位置 | 状态 |
|---|------|---------|------|------|
| 1 | ~~TaskStatus.STOPPED 存在于接口但不在实现枚举~~ | ~~已修复~~ | 单一来源为 `core/interfaces/i_task_manager.py`，`task_model.py` re-export | ✅ 已修复 |
| 2 | TaskScheduler 为轻量生命周期占位（空转线程已移除） | 低 | `scheduler.py` 仅保留 start/stop 生命周期接口，实际调度由 `_check_scheduled_tasks()` daemon 线程 + SchedulerCallback 承担 | 📝 已文档化 |
| 3 | 定时任务恢复无全局入口 | 低 | 恢复由 `register_scheduled_task_factory()` 自动触发（按插件恢复）；历史遗留的 `_restore_all_scheduled_tasks()` 已移除 | 📝 已文档化 |
| 4 | PluginServices DI 已启用 | 低 | PluginManager._create_plugin_services() 已实现 DI 注入 | 📝 已完成 |
| 5 | API 注册优先选择名称以 'Service' 结尾的类 | 低 | `manager.py` API 自动注册逻辑含注释说明 | 📝 已文档化 |
| 6 | ~~DAO/database 模块为占位桩~~ | ~~低~~ | ~~SQLite 迁移已完成：`sqlite_backend.py` + `sql_map.py` + `schema_migrations.py`~~ | ✅ 已修复 |

---

## 15. 相关文档

- [模块依赖关系](module-dependencies.md)
- [完整 API 参考](../api/full-reference.md)
- [后台任务概述](../core/background-task/overview.md)
- [后台任务 API 参考](../core/background-task/api-reference.md)
- [后台任务存储](../core/background-task/task-storage.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [插件开发指南](../core/plugin-system/plugin-development.md)
- [接口层概述](../core/interfaces/overview.md)
- [DataProvider 概述](../core/data-provider/overview.md)
- [LLM Provider 概述](../core/llm-provider/overview.md)
