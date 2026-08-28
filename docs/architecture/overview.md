# 系统架构概述

> InstructionX 项目的整体架构设计介绍

---

## 1. 项目简介

**InstructionX** 是一个基于 **PySide6** 构建的插件式桌面应用程序框架。它采用模块化设计，支持插件热插拔、数据持久化、任务调度和跨插件 API 调用。

### 技术栈

| 技术 | 用途 |
|------|------|
| **PySide6** | Qt 图形界面框架 |
| **Python 3.14** | 编程语言 |
| **SQLite** | 数据持久化（默认 SQLite + WAL；JSON 仅应急回退） |
| **Threading** | 多线程支持 |

---

## 2. 整体架构图

```mermaid
graph TB
    subgraph MainWindow ["应用主窗口 InstructionXMainWindow"]
        direction TB
        Menu[菜单栏] --> SP[SkillsPanel<br/>技能面板 高度最小125px / 最大135px]
        SP --> Divider[分割线]
        Divider --> WA[WorkArea<br/>工作区]
    end

    subgraph Plugins ["插件层"]
        PA[插件 A<br/>entrance.py<br/>service.py<br/>information.py]
        PB[插件 B<br/>entrance.py<br/>service.py<br/>information.py]
        PC[插件 C<br/>entrance.py<br/>service.py<br/>information.py]
    end

    subgraph Core ["核心层"]
        PM[PluginManager<br/>插件管理器]
        DP[DataProvider<br/>数据提供者]
        BTM[BackgroundTaskManager<br/>后台任务管理器]
    end

    subgraph MCP ["MCP 层"]
        MCPM[MCPManager<br/>MCP 协议协调器]
        MCPB[MCPBridge<br/>桥接器]
        MCPC[MCPClientManager<br/>MCP 客户端]
    end

    subgraph LLM ["LLM 层"]
        LLMS[LLMPluginService<br/>插件开发者入口]
        LLMP[LLMProvider<br/>LLM 核心层]
        PS[PluginServices<br/>DI 容器]
        TR[ToolRegistry<br/>工具注册表]
    end

    subgraph I18N ["i18n 层"]
        LMM[LanguageManager<br/>单例 QObject]
        PIF[PluginI18nFacade<br/>绑定插件 UUID]
    end

    subgraph Font ["字体子系统"]
        FM[FontManager<br/>单例]
    end

    subgraph Storage ["持久化层"]
        DB[data/data.db]
        DBWAL[data.db-wal]
        DBSHM[data.db-shm]
        TasksJSON[data/tasks.json]
        Assets[data/assets/]
        LLMConfig[config/llm_providers.json]
        MCPConfig[config/mcp_config.json]
    end

    MainWindow --> Plugins
    Plugins --> PM
    Plugins --> DP
    Plugins --> BTM
    Plugins --> LLMS
    Plugins --> MCPM
    PM -.->|创建并注入| PS
    PS -.->|llm_facade| LLMS
    PS -.->|mcp_manager / mcp_client| MCPM
    PS -.->|localization| PIF
    PIF --> LMM
    PS -.->|font_manager| FM
    LLMS --> LLMP
    LLMS --> TR
    MCPC --> TR
    LLMP -->|LLM API| LLMConfig
    PM -->|插件加载| Plugins
    PM -->|MCP 工具同步| MCPM
    PM -->|注册插件语言包| LMM
    DP -->|数据持久化| DB
    DBWAL -.->|WAL| DB
    DBSHM -.->|WAL| DB
    BTM -->|任务存储| TasksJSON
    MCPM -->|配置| MCPConfig
    LMM -->|读写| I18NCfg[config/i18n.json<br/>config/plugin_languages.json]
```

---

## 3. 核心组件

### 3.1 PluginManager（插件管理器）

**文件位置**: `core/plugin/manager.py`

**职责**:
- 扫描并加载官方插件（`plugin/` 目录）
- 扫描并加载第三方插件（`custom_plugin/` 目录）
- 管理插件实例和 API 注册
- 提供跨插件方法调用
- MCP 工具同步（注册/注销插件 API 时自动通知 MCP 层）

**单例模式**: 整个应用只有一个 PluginManager 实例

### 3.2 DataProvider（数据提供者）

**文件位置**: `core/data/data_provider.py`

**职责**:
- 插件数据持久化（SQLite + WAL，保留 JSON 应急开关）
- 内存缓存管理
- 命名空间隔离（PRIVATE / PUBLIC）
- 发布/订阅通信机制
- 资源文件管理

**单例模式**: 全局唯一的数据访问入口

### 3.3 BackgroundTaskManager（后台任务管理器）

**文件位置**: `core/task/background_task.py`

**职责**:
- 同步任务执行
- 异步任务调度
- 定时任务管理
- 任务状态持久化

**单例模式**: 全局任务调度中心

### 3.4 LLM 层（LLMProvider + LLMPluginService）

**文件位置**:
- `core/llm/llm_provider.py` — LLM 核心层（底层）
- `core/llm/plugin_service.py` — LLM 插件服务层（插件开发者入口）

**LLMProvider（核心层）**:
- 多提供商实例管理（内置预设：MiniMax、SiliconFlow、GLM、Ollama、OpenAI；自定义 OpenAI 兼容实例）
- 按实例 `adapter` 查询适配器注册表创建实例（注册表键为适配器家族）
- 统一 API 接口（chat、stream_chat、embed）
- 模型列表获取与缓存（缓存键为实例 id）
- 连通性检查（`check_provider` / `check_model`）与健康跟踪
- 配置版本比对惰性刷新（无需手动 `reload_config()`）
- Function Calling 支持

**LLMPluginService（插件服务层）**:
- 插件开发者唯一入口（推荐使用 `get_llm_plugin_service()`），显式继承 `ILLMService`
- 对话管理（创建/发送/流式/统计）
- 工具调用自动化（ToolCallExecutor，返回 ToolChatResult）
- 多模态（图片/TTS）
- 实例与模型查询（`list_providers` / `get_models` / `get_default_provider_id`），不泄漏底层实例与 api_key

**DI 注入**: `PluginManager` 通过 `PluginServices.llm_facade` 注入到各插件

#### 3.4.1 ConversationManager

**文件位置**: `core/llm/conversation_manager.py`

**职责**:
- 对话生命周期管理（创建、更新、查询）
- 上下文截断（超出 `max_context_tokens`（默认 120000）时自动从最早的用户/助手消息开始截断，system prompt 与最近消息保留；旧参数名 `max_context` 为废弃兼容参数）
- Token 估算（CJK（中/日/韩）字符按 ~1 token/字，其余字符按 ~4 字符/token 估算）
- 费用计算（基于 `DEFAULT_PRICING` 定价表，随配置变更热更新）

#### 3.4.2 ToolCallExecutor / ToolRegistry

**文件位置**: `core/llm/tool_call_executor.py`

**职责**:
- `ToolRegistry`: 集中管理所有可用工具（`register()` / `register_typed()` / `unregister()` / `get_handler()`）
- `ToolCallExecutor`: 自动工具调用循环（`chat_with_tools()`，返回 `ToolChatResult`），支持流式版本

**数据文件**:
- `core/llm/types.py` — 集中管理 LLMPluginService 相关数据类型（Conversation、ProviderInfo、ToolChatResult、ToolDefinition、UsageStats 等）
- `core/llm/model_schema.py` — 统一模型 schema（capabilities 闭集、normalize、三路合并、分组推断）
- `core/llm/catalog/` — 提供商预设目录（ProviderPreset / PROVIDER_PRESETS / PRESET_MODELS / logos/，随程序发布只读）
- `core/llm/pricing.py` — 提供 `DEFAULT_PRICING` 定价表
- `core/llm/types_cache.py` — 统一缓存信息类型（CacheInfo、CacheType）
- `core/llm/cache_adapter.py` — 各 Provider 缓存适配器
- `core/llm/usage_record_store.py` — 用量记录持久化（`data/llm_usage.json`）

### 3.5 PluginVersion（版本管理）

**文件位置**: `core/plugin/plugin_version.py`

**职责**: 语义化版本管理，支持五种类型前缀（release/pre-release/beta/alpha/internal）和中文显示。

### 3.6 PluginIcon（图标管理）

**文件位置**: `core/plugin/plugin_icon.py`

**职责**: 支持多种图标加载策略（BUILTIN、FILE、RESOURCE、BASE64、NONE）。

### 3.7 PluginIdentity（身份标识）

**文件位置**: `core/plugin/plugin_identity.py`

**职责**: 为每个插件生成和管理唯一 UUID，持久化到 `.plugin_info.json`。

### 3.8 PluginConfigManager（配置管理）

**文件位置**: `core/plugin/config_manager.py`

**职责**: 管理插件显示顺序配置，持久化到 `config/plugin_order.json`。

### 3.9 TaskStorage（任务持久化）

**文件位置**: `core/task/task_storage.py`

**职责**: 任务数据持久化层，管理 `data/tasks.json`，支持原子写入和缓存。

### 3.10 GitHubPluginInstaller（GitHub 插件安装器）

**文件位置**: `core/plugin/github_plugin_installer.py`

**职责**: 从 GitHub 仓库远程安装插件，支持单插件和多插件仓库。

**功能特性**:
- 检测仓库类型（单插件 `IXPlugin.json` / 多插件 `IXRepo.json`）
- 解析 GitHub URL 支持多种格式
- 自动判定安装目录（KKPIP-Tech → plugin/，其他 → custom_plugin/）
- 后台下载，不阻塞 UI

**详细文档**: [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)

### 3.11 多语言子系统（i18n）

**文件位置**: `core/i18n/`（9 个模块）

**职责**: 框架与插件文案的统一取词、当前语言状态管理、语言变更通知、每插件语言覆盖。

**核心模块**:

| 模块 | 职责 |
|------|------|
| `language_manager.py` | `LanguageManager` 单例（QObject）：`tr(group, key, /, **params)` 取词、`set_language()` 实时切换（`language_changed` 信号）、每插件语言覆盖三级解析 |
| `facade.py` | `PluginI18nFacade`：绑定插件 UUID 的取词门面（`ILocalizationFacade` 实现，由 `PluginServices.localization` 注入） |
| `plugin_registry.py` | `PluginTextRegistry`：插件语言包自动注册表（扫 `<插件目录>/text/*.xml`） |
| `settings_store.py` | `I18nSettingsStore`：`config/i18n.json` + `config/plugin_languages.json` 读写（原子写 + 损坏备份 `.json.corrupt.bak` 重建） |
| `loader.py` | `load_catalog()` + `CatalogCache`：XML 解析 + 目录级惰性加载（含负缓存） |
| `catalog.py` | `TextCatalog`（frozen dataclass）：单语言文案目录数据模型 |
| `fallback.py` | 语言代码解析（`zh-TW → zh`）、取词回退链、`ERROR_TEXT` 常量 |
| `ixplugin_i18n.py` | `resolve_i18n_field`：IXPlugin.json / IXRepo.json 多语言字段解析 |
| `exceptions.py` | `I18nError`（仅编程错误，正常路径走回退链） |

**语言文件约定**: 框架语言文件位于 `ui/text/<语言代码>.xml`（`zh.xml` 默认语言必须完整）；插件语言文件位于各插件的 `text/` 目录（**插件必需项**，对未提供语言包的存量插件保持兼容）。

**回退链**: `当前语言 → 默认语言（DEFAULT_LANGUAGE="zh"，开发者设定用户不可改）→ ERROR_TEXT`。

**启动集成**: `main.py` 在 `apply_uikit_theme()` 之后、主窗口构造之前调用 `get_language_manager()` 完成初始化（依赖 `QObject`，需 `QCoreApplication` 已创建）；插件加载期由 `PluginManager` 自动调用 `register_plugin_texts(plugin_id, plugin_dir)`。

**UI 入口**: 主窗口「编辑 → 语言」打开 `LanguageDialog`（`ui/dialog/language_dialog.py`）；插件管理对话框详情面板「语言…」按钮打开 `PluginLanguageDialog`（无语言包时置灰）。

**详细文档**: [多语言（i18n）子系统概述](../core/i18n/overview.md)

### 3.12 抽象接口层

**文件位置**: `core/interfaces/`

**职责**: 定义框架的抽象接口层，将插件开发 API 与内部实现解耦。这是框架设计的核心层，确保插件只依赖接口而非具体实现。

**设计目标**:
- **解耦**: 插件通过接口与核心服务交互，不依赖具体实现类
- **契约**: 明确每个服务的能力边界和使用方式
- **测试**: 可以为接口创建 mock 实现进行单元测试
- **扩展**: 未来可以替换实现而无需修改插件代码

**接口清单**:

| 接口 | 文件 | 说明 | 对应实现 |
|------|------|------|--------|
| `IPlugin` | `i_plugin.py` | 插件抽象基类 | `core/plugin/plugin_interface.py` |
| `IPluginInfo` | `i_plugin_info.py` | 插件信息抽象基类 | `core/plugin/plugin_info_interface.py` |
| `IDataProvider` | `i_data_provider.py` | 数据提供者接口 | `core/data/data_provider.py` |
| `ITaskManager` | `i_task_manager.py` | 任务管理器接口 | `core/task/background_task.py` |
| `ILLMService` | `i_llm_service.py` | LLM 插件服务接口 | `core/llm/plugin_service.py`（`LLMPluginService` 显式继承） |
| `ILogger` | `i_logger.py`（`core/interfaces/` 重导出） | 日志接口 | `utils/logging_tools.py`（LoggerManager） |
| `ILocalizationFacade` | `i_localization.py` | 插件文案取词门面接口（绑定插件 UUID） | `core/i18n/facade.py` 的 `PluginI18nFacade` |
| `PluginServices` | `plugin_services.py` | 服务封装（依赖注入容器，8 字段） | — |

**导入指南**:
```python
# 从 core.interfaces 导入所有接口（推荐）
from core.interfaces import (
    IPlugin,
    IPluginInfo,
    IDataProvider,
    ITaskManager,
    ILLMService,
    ILogger,
    PluginServices,
    TaskType,
    TaskStatus,
    DataNamespace
)
```

**详细文档**: [接口层概述](../core/interfaces/overview.md)

---

## 4. 数据流

### 4.1 插件数据流

```mermaid
sequenceDiagram
    participant A as 插件 A
    participant DP as DataProvider
    participant B as 插件 B

    A->>DP: set_plugin_data()
    DP->>DP: 更新缓存
    DP->>DP: 写入 SQLite
    A->>DP: get_plugin_data()
    DP-->>A: 返回数据

    B->>DP: subscribe()
    DP-->>B: 订阅成功
    A->>DP: set_plugin_data(PUBLIC)
    DP->>DP: 通知订阅者
    DP-->>B: 回调函数
```

### 4.2 插件调用流

```mermaid
sequenceDiagram
    participant A as 插件 A
    participant PM as PluginManager
    participant B as 插件 B

    A->>PM: call_plugin_method()
    PM->>B: 路由到目标插件
    B-->>PM: 执行方法
    PM-->>A: 返回结果
```

---

## 5. 目录结构

```
InstructionX/
├── main.py                    # 应用入口
│
├── core/                      # 核心模块
│   ├── interfaces/           # 抽象接口定义
│   │   ├── __init__.py      # 导出所有接口（含 ILogger 重导出）
│   │   ├── i_plugin.py       # IPlugin 抽象基类
│   │   ├── i_plugin_info.py  # IPluginInfo 抽象基类
│   │   ├── i_data_provider.py    # IDataProvider 抽象接口
│   │   ├── i_task_manager.py      # ITaskManager 抽象接口
│   │   ├── i_llm_service.py      # ILLMService 抽象接口（LLM 插件服务契约）
│   │   ├── i_logger.py           # ILogger 接口重导出（向后兼容）
│   │   └── plugin_services.py    # PluginServices 服务封装
│   ├── plugin/               # 插件系统实现
│   │   ├── manager.py       # PluginManager
│   │   ├── plugin_interface.py  # IPlugin（向后兼容导入路径）
│   │   ├── plugin_info_interface.py  # IPluginInfo（向后兼容导入路径）
│   │   ├── plugin_version.py
│   │   ├── plugin_icon.py
│   │   ├── plugin_identity.py
│   │   ├── config_manager.py
│   │   ├── plugin_groups.py   # 用户自定义分组存储（config/plugin_groups.json）
│   │   ├── plugin_registry.py # 已安装插件注册表（config/plugin_registry.json）
│   │   ├── tool_name.py       # 工具命名/清洗工具
│   │   ├── dependency_manager.py  # 插件依赖管理
│   │   └── github_plugin_installer.py  # GitHub 插件安装器
│   ├── data/                 # 数据层实现
│   │   ├── data_provider.py # DataProvider（核心）
│   │   ├── sqlite_backend.py # SQLite 后端（连接、DDL、事务、CRUD）
│   │   ├── sql_map.py       # SQL 语句映射
│   │   ├── schema_migrations.py # Schema 版本与迁移脚本
│   │   └── __init__.py
│   ├── task/                 # 后台任务实现
│   │   ├── background_task.py
│   │   ├── task_model.py
│   │   ├── task_storage.py
│   │   └── scheduler.py
│   ├── mcp/                  # MCP 协议模块
│   │   ├── __init__.py
│   │   ├── client.py         # MCPClientManager（MCP 客户端）
│   │   ├── server.py         # MCPHostServer（MCP 主机）
│   │   ├── manager.py        # MCPManager（单例协调器）
│   │   ├── bridge.py         # MCPBridge（桥接器）
│   │   ├── config.py         # MCP 配置
│   │   └── plugin_interface.py  # MCP 插件接口
│   ├── font/                 # 字体子系统（框架不自带字体）
│   │   ├── manager.py        # FontManager 单例（安装/卸载/注册表持久化/系统回退）
│   │   ├── font_record.py    # FontRecord 字体注册记录
│   │   └── exceptions.py     # FontInstallError
│   ├── i18n/                 # 多语言子系统（XML 语言文件 + 回退链取词）
│   │   ├── catalog.py        # TextCatalog 数据模型（frozen dataclass）
│   │   ├── loader.py         # load_catalog + CatalogCache（目录级惰性加载缓存）
│   │   ├── fallback.py       # resolve_language_code / lookup_template / ERROR_TEXT 常量
│   │   ├── settings_store.py # I18nSettingsStore（config/i18n.json + config/plugin_languages.json）
│   │   ├── plugin_registry.py # PluginTextRegistry 插件语言包注册表
│   │   ├── facade.py         # PluginI18nFacade（ILocalizationFacade 实现）
│   │   ├── ixplugin_i18n.py  # resolve_i18n_field（IXPlugin.json 多语言字段解析）
│   │   ├── exceptions.py     # I18nError（仅编程错误）
│   │   └── language_manager.py # LanguageManager 单例（QObject）：tr() / set_language / language_changed
│   └── llm/                  # LLM 提供者实现
│       ├── llm_provider.py  # LLMProvider 核心层（adapter 分发、check_*、惰性刷新）
│       ├── provider_interface.py  # ILLM + Message/ChatResponse/ToolCall/ModelInfo/ModelCheckResult
│       ├── model_schema.py  # 统一模型 schema（capabilities 闭集/normalize/三路合并）
│       ├── catalog/         # 提供商预设目录（ProviderPreset/PROVIDER_PRESETS/PRESET_MODELS/logos）
│       ├── plugin_service.py # LLMPluginService 插件服务层（ILLMService 实现）
│       ├── conversation_manager.py  # 对话管理
│       ├── tool_call_executor.py   # 工具调用自动化（ToolChatResult / register_typed）
│       ├── types.py        # 数据类型（DEFAULT_PROVIDER/ProviderInfo/ToolChatResult 等）
│       ├── types_cache.py  # 类型缓存
│       ├── cache_adapter.py # 缓存适配器
│       ├── pricing.py      # 定价表
│       ├── config.py       # ProviderConfig / LLMConfig 单例（schema v2 + 迁移 + 订阅）
│       ├── secure_keys.py  # API Key 混淆存储
│       ├── usage_record_store.py # 用量记录存储
│       ├── exceptions.py
│       └── providers/       # 适配器注册表 + 各 Provider 实现
│           ├── __init__.py  # PROVIDER_REGISTRY（adapter→类）+ register_adapter 等
│           ├── base.py
│           ├── minimax.py
│           ├── siliconflow.py
│           ├── glm.py
│           ├── ollama.py
│           ├── openai.py
│           └── openai_compatible.py  # 自定义 OpenAI 兼容兜底适配器
│
├── ui/                       # UI 模块
│   ├── InstructionX_UIKit/  # UIKit 组件库（设计令牌 + ThemeManager + 58 组件/布局/图表，同步副本不修改）
│   ├── uikit_bootstrap.py   # sys.path 引导（使 UIKit 以顶层包可导入，main.py 第一个业务 import）
│   ├── uikit_theme.py       # 全局主题入口（apply_uikit_theme 三模式 + 排除区兼容附录）
│   ├── main_window.py       # 主窗口
│   ├── title_bar.py        # 自定义标题栏
│   ├── usage_panel/         # 用量查询面板（包：panel/kpi_card/trend_chart/history_table/formatting）
│   ├── tray/                # 系统托盘子系统（TrayIconManager 门面 + TrayBackend 后端注册表）
│   ├── skills_panel/        # 技能面板
│   │   ├── panel.py        # SkillsPanel 面板
│   │   ├── plugin_group_widget.py  # 分组折叠控件
│   │   └── skill_button.py  # SkillButton 按钮组件
│   ├── work_area/           # 工作区
│   │   └── work_area.py
│   ├── text/                # 框架语言文件目录（<语言代码>.xml）
│   └── dialog/              # 对话框
│       ├── __init__.py
│       ├── about_dialog.py      # 关于对话框
│       ├── license_dialog.py    # 开源许可对话框
│       ├── close_confirm_dialog.py  # 关闭确认对话框（退出/最小化到托盘/取消）
│       ├── font_manager_dialog.py   # 字体管理对话框（安装/卸载/预览/系统字体回退）
│       ├── language_dialog.py       # 界面语言选择对话框（编辑菜单「语言」打开）
│       ├── plugin_language_dialog.py # 插件语言选择对话框（每插件语言覆盖）
│       ├── llm_settings/        # LLM 设置对话框包（两栏：列表 + 详情，自动保存语义）
│       ├── plugin_management_dialog.py  # 插件管理对话框（安装/升级/降级/卸载 + 分组与排序）
│       ├── plugin_order_dialog.py  # 插件排序对话框（遗留，排序功能已迁入 plugin_management_dialog）
│       └── github_plugin_install_dialog.py  # GitHub 插件安装对话框
│
├── workers/                  # 预留扩展目录（当前为空，框架后台线程统一由 BackgroundTaskManager 管理）
│
├── plugin/                   # 官方插件安装目录（.gitignore 忽略 plugin/*/，git 仅跟踪 __init__.py；
│                             #   插件内容经 GitHub 安装器获取，本地开发副本中另有若干官方/示例插件）
│
├── custom_plugin/            # 第三方插件（通过 GitHub 安装器获取，不再捆绑）
│
├── data/                     # 数据存储
│   ├── data.db               # SQLite 主数据库
│   ├── data.db-wal           # WAL 日志（运行时自动生成）
│   ├── data.db-shm           # WAL 共享内存索引（运行时自动生成）
│   ├── tasks.json
│   ├── llm_usage.json
│   ├── conversations.json    # LLM 会话持久化
│   ├── fonts/                # 框架安装字体目录（fonts.json 注册表，schema v1）
│   ├── plugin_identity/      # 插件 UUID 回退存储（{插件目录名}.json）
│   └── assets/
│       └── plugins/          # 插件资源文件
│
├── config/                   # 配置目录
│   ├── plugin_order.json
│   ├── plugin_groups.json    # 用户自定义插件分组
│   ├── plugin_registry.json  # 已安装插件注册表（版本/来源/安装时间）
│   ├── llm_providers.json
│   ├── llm_models_cache.json
│   ├── mcp_config.json      # MCP 协议配置
│   ├── i18n.json            # 框架语言设置（schema v1：default_language + current_language）
│   └── plugin_languages.json # 每插件语言覆盖（schema v1：overrides）
│
├── utils/                    # 工具类
│   ├── logging_tools.py     # 日志管理
│   ├── i_logger.py         # ILogger 接口
│   ├── image_utils.py      # 图片工具（load_image_as_base64）
│   ├── thread_utils.py     # 工作线程 → UI 线程封送
│   └── macos_dock_icon.py  # macOS Dock 栏应用图标设置（非 macOS 空操作）
│
├── scripts/                  # 独立验证脚本（冒烟/截图/演示/校验，运行方式：.venv\Scripts\python.exe scripts\<name>.py）
│
├── temp/                     # 临时文件目录（gitignore，禁止提交）
│
└── docs/                     # 技术文档
```

---

## 6. 启动流程

```mermaid
flowchart TD
    A[main] --> B[QApplication 创建]
    B --> B1[QQuickWindow.setGraphicsApi OpenGL<br/>统一图形 API，避免 GL/Qt Quick 混用]
    B1 --> B2[uikit_bootstrap 扩展 sys.path<br/>使 InstructionX_UIKit 以顶层包可导入]
    B2 --> C[apply_uikit_theme<br/>UIKit 全局主题，auto 自动检测系统主题]
    C --> D[LoggerManager 初始化]
    D --> D2[sys.excepthook 兜底异常记录]
    D2 --> D3[get_language_manager 初始化 i18n<br/>主窗口构造前完成]
    D3 --> E[InstructionXMainWindow 创建]
    E --> F[创建自定义标题栏 + 菜单栏]
    F --> G[_create_main_layout]
    G --> G0[_prewarm_blueprint_viewport<br/>预创建隐藏蓝图画布<br/>让顶层原生句柄首次创建即含 GL 子控件]
    G0 --> G1[初始化 PluginManager]
    G1 --> G2[load_plugins<br/>加载官方 + 第三方插件<br/>注册插件语言包]
    G2 --> G3[apply_custom_order<br/>应用自定义排序]
    G3 --> H[创建 SkillsPanel]
    H --> I[从 PluginManager 加载技能按钮]
    I --> J[创建 WorkArea]
    J --> K[show 主窗口]
    K --> L[等待用户交互]
```

> **托盘与退出**：`main.py` 通过 `setQuitOnLastWindowClosed(False)` 切断「最后一个窗口关闭即退出」的隐式链路，退出时机完全由代码显式控制。主窗口 `closeEvent` 拦截全部关闭路径（自绘叉号 / Alt+F4 / 任务栏关闭），每次弹出 `CloseConfirmDialog` 询问「退出程序 / 最小化到托盘 / 取消」；托盘菜单「退出」与 Windows 注销/关机（`commitDataRequest` 守卫置 `_force_quit`）静默直退。`application.exec()` 返回后依次执行 `BackgroundTaskManager.shutdown()` 与 LLM 用量记录冲刷（`UsageRecordStore.flush()`）。详见 [系统托盘](../ui/system-tray.md)。

---

## 7. 关键技术特性

### 7.1 单例模式

核心组件采用单例模式，实现方式分为两类：

**类型 A：`__new__` + `_initialized` 标志（PluginManager）**

```python
class PluginManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if PluginManager._initialized:
            return
        # 初始化代码...
        PluginManager._initialized = True
```

**类型 B：`__new__` + `threading.Lock` 双重检查锁定（DataProvider、BackgroundTaskManager、LLMProvider、LLMConfig、UsageRecordStore、TaskStorage、LoggerManager）**

```python
class DataProvider:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
```

**类型 C：模块级锁 + 全局变量（MCPManager、LLMPluginService）**

```python
_module_lock = threading.Lock()
_module_instance = None

def get_mcp_manager() -> "MCPManager":
    global _module_instance
    if _module_instance is None:
        with _module_lock:
            if _module_instance is None:
                _module_instance = MCPManager()
    return _module_instance
```

### 7.2 线程安全

- DataProvider 使用 `_file_lock`（`RLock`）保护数据库访问与缓存 + `_subscription_lock`（`Lock`）保护订阅表（`core/data/data_provider.py:83-84`）
- BackgroundTaskManager 使用线程池

### 7.3 原子写入

`DataProvider` 默认使用 SQLite 事务保证原子性：

- 单条写入（`set_plugin_data`）由 SQLite 语句级原子性（UPSERT）保证。
- 全量写入（`save_data` / `reset_all_data`）与活跃实例切换（`set_active_instance`）使用 `BEGIN IMMEDIATE` 显式事务，异常时自动回滚。

临时文件 + 原子重命名机制仍保留在 `TaskStorage` 等以 JSON 为后端的组件中使用。

---

## 相关文档

- [模块依赖关系](module-dependencies.md)
- [完整架构分析](full-analysis.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [DataProvider 概述](../core/data-provider/overview.md)
- [后台任务概述](../core/background-task/overview.md)
- [LLM Provider 概述](../core/llm-provider/overview.md)
- [MCP 协议模块概述](../core/mcp/overview.md)
