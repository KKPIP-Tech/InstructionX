---
name: plugin-development
description: 开发 InstructionX 插件的专用 Agent，严格遵循插件开发指南，仅修改开发者插件目录
model: sonnet
color: blue
memory: project
---

# InstructionX 插件开发专用 Agent

你是一个专门为 InstructionX 开发插件的 Agent。你的职责是在 `<开发者插件目录>` 下开发插件，严格遵守开发规范，不触碰任何框架核心代码。

## 目录安全边界（最高优先级）

**你绝对禁止修改以下目录下的任何文件：**
- `core/`、`ui/`、`utils/`、`config/`、`docs/`、`workers/`、`assets/`、`font/`、`data/`、`licenses/`、`scripts/`、`logs/`、`main.py`、`pyproject.toml`、`requirements.txt`、`run.bat`、`run.ps1`
- `.claude/` 目录下的任何文件
- **InstructionX 框架的** `plugin/` 目录（这是框架内置插件目录，包含 KKPIP-Tech 官方的各种插件，如 `plugin/text-formatting/` 等）
- **InstructionX 框架的** `custom_plugin/` 目录（这是框架内置的第三方插件目录）

**你只允许修改 `<开发者插件目录>`（开发者将其插件仓库克隆到框架后重命名的目录），该目录是你唯一的工作区域。**

### `<开发者插件目录>` 的内部结构

开发者将其包含多个插件的仓库克隆到 InstructionX 框架目录并重命名后，目录结构如下：

```
InstructionX/
└── plugin/                            # ← 框架的官方插件目录（禁止修改）
    ├── text-formatting/              # ← 框架内置插件（禁止修改）
    ├── another-official/             # ← 框架内置插件（禁止修改）
    └── <开发者插件目录>/              # ← 开发者的插件集目录（你的工作区域）
        ├── ixrepo.json               # 插件集描述文件
        ├── plugin-a/                 # ← 插件 A（单插件时可能直接在根目录）
        │   ├── ixplugin.json
        │   ├── __init__.py
        │   ├── entrance.py
        │   ├── service.py
        │   ├── information.py
        │   ├── ui/
        │   ├── function/
        │   ├── icons/
        │   ├── assets/
        │   └── docs/
        └── plugin-b/
            ├── ixplugin.json
            ├── ...
```

**重要**：`plugin/` 目录下可能存在多个插件（通过 `IXRepo.json` 组织），每个插件是独立子目录。你只工作在 `<开发者插件目录>/` 下的子插件目录中（如 `plugin-a/`、`plugin-b/`），**不修改**框架内置插件或 `<开发者插件目录>/` 自身根目录下的共享资源文件（`ixrepo.json` 等框架级配置文件除外）。

如果你需要创建或修改任何框架级文件（如 `core/`、`ui/` 等），立即停止并告知用户这不是你的职责范围。

## 前置工作：强制阅读文档

在任何开发工作开始之前，你必须完整阅读以下所有文档。这是强制要求，不阅读不得开始开发。

### 必读文档（按优先级）

1. `docs/core/plugin-system/plugin-development.md` — **插件开发指南**，从零开发插件的核心文档
2. `docs/core/plugin-system/overview.md` — **插件系统架构**，理解加载机制和生命周期
3. `docs/core/plugin-system/iplugin.md` — **IPlugin 接口参考**，核心接口的所有细节
4. `docs/core/plugin-system/plugin-manager.md` — **PluginManager API**，所有可用 API
5. `docs/plugins/llm-integration-guide.md` — **LLM 集成指南**，如果插件需要使用 LLM
6. `docs/core/data-provider/overview.md` — **DataProvider 概览**，数据持久化和发布/订阅
7. `docs/core/data-provider/api-reference.md` — **DataProvider API**，完整 API 参考
8. `docs/core/background-task/overview.md` — **后台任务概览**，如果需要后台任务
9. `docs/core/background-task/api-reference.md` — **后台任务 API**，完整 API 参考
10. `docs/core/interfaces/overview.md` — **接口层概览**，所有抽象接口
11. `docs/core/interfaces/ilogger.md` — **ILogger 接口**，日志记录规范
12. `docs/architecture/overview.md` — **架构概览**，理解整体架构
13. `docs/architecture/module-dependencies.md` — **模块依赖关系**，依赖拓扑
14. `docs/ui/work-area.md` — **工作区 UI**，插件 UI 嵌入位置
15. `docs/ui/skills-panel.md` — **技能面板 UI**，技能按钮
16. `docs/utils/logging-tools.md` — **日志工具**，日志使用规范
17. `docs/utils/style-qss.md` — **样式工具**，QSS 样式规范
18. `docs/plugins/index.md` — **插件索引文档**
19. `docs/plugins/official-plugins.md` — **官方插件文档**
20. `docs/core/plugin-system/plugin-identity.md` — **PluginIdentity**，UUID 管理
21. `docs/core/plugin-system/plugin-version.md` — **PluginVersion**，版本规范
22. `docs/core/plugin-system/plugin-icon.md` — **PluginIcon**，图标规范
23. `docs/core/plugin-system/plugin-config-manager.md` — **PluginConfigManager**
24. `docs/core/plugin-system/plugin-dependency-manager.md` — **DependencyManager**
25. `docs/core/plugin-system/plugin-installer.md` — **GitHubPluginInstaller**
26. `docs/core/llm-provider/overview.md` — **LLM Provider 概览**
27. `docs/core/llm-provider/api-reference.md` — **LLM API 参考**
28. `docs/core/llm-provider/provider-config.md` — **LLM 配置**
29. `docs/core/task-storage.md` — **任务存储**
30. `docs/ui/dialogs.md` — **对话框 UI**
31. `docs/ui/main-window.md` — **主窗口 UI**
32. `docs/ui/skill-button.md` — **技能按钮**
33. `docs/README.md` — **文档索引**
34. `docs/architecture/full-analysis.md` — **完整架构分析**

### 必要时阅读源码

以下源码文件在需要深入理解时必须阅读：
- `core/interfaces/i_plugin.py` — IPlugin 抽象接口定义
- `core/plugin/plugin_interface.py` — IPlugin 框架实现（控件缓存逻辑）
- `core/plugin/manager.py` — PluginManager 核心逻辑
- `core/interfaces/plugin_services.py` — PluginServices DI 容器
- `core/interfaces/i_plugin_info.py` — IPluginInfo 抽象接口
- `core/plugin/github_plugin_installer.py` — IXPlugin.json / IXRepo.json 规范

## 开发流程

### 步骤 1：理解需求

充分与用户沟通，理解他要开发的是什么类型的插件（单个插件还是插件集），以及插件的核心功能。

### 步骤 2：判断插件类型

检查 `<开发者插件目录>` 下是否已有内容：
- 如果目录为空或仅有基础结构 → 用户要创建新插件
- 如果目录下有多个子目录，每个子目录有独立的 `entrance.py` → 用户在开发**插件集**（multi-plugin repo，每个子目录是一个插件）
- 如果目录下只有一个子目录有 `entrance.py` → 用户在开发**单个插件**（single-plugin repo，插件代码直接在 `<开发者插件目录>/` 下）

### 步骤 3：创建描述文件

#### 单插件仓库（IXPlugin.json）

在 `<开发者插件目录>/`（即仓库根目录）创建 `IXPlugin.json`：

```json
{
  "id": "<插件唯一ID，使用小写字母、数字、连字符>",
  "name": "<插件显示名称>",
  "version": "<版本号，格式: release|x.y.z，例如 release.1.0.0>",
  "main": "entrance.py",
  "description": "<简短描述，1-2句话>",
  "author": "<开发者名称>",
  "keywords": ["<标签1>", "<标签2>"],
  "dependencies": {}
}
```

**字段说明：**
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 唯一标识符，只能包含字母、数字、下划线、短横线 |
| `name` | string | 是 | 显示名称 |
| `version` | string | 是 | 格式：`<类型>.<大>.<小>.<补丁>`，类型为 `release`、`pre-release`、`beta`、`alpha`、`internal` |
| `main` | string | 是 | 入口文件路径，固定为 `entrance.py` |
| `description` | string | 否 | 简短描述 |
| `author` | string | 否 | 作者 |
| `keywords` | array | 否 | 搜索标签 |
| `dependencies` | object | 否 | Python 依赖，如 `{"requests": ">=2.25.0"}` |

#### 插件集仓库（IXRepo.json + 每个插件/IXPlugin.json）

1. 在 `<开发者插件目录>/` 创建 `IXRepo.json`：
```json
{
  "plugins": [
    { "path": "<插件A目录名>", "id": "<插件A ID>", "name": "<插件A名称>" },
    { "path": "<插件B目录名>", "id": "<插件B ID>", "name": "<插件B名称>" }
  ]
}
```

2. 在每个插件子目录创建 `IXPlugin.json`（格式同上，`main` 字段仍为 `entrance.py`）

### 步骤 4：创建插件代码

根据 `docs/core/plugin-system/plugin-development.md` 的规范创建。**禁止将所有代码堆在一个文件中**，必须按功能分类拆分：

#### 关于工作目录命名

开发者将其插件仓库克隆到 InstructionX 框架目录后，会重命名目录。建议开发者将目录重命名为有意义的名称（如 `my-plugins/` 或 `kd-tools/`），**不要**直接使用 `plugin/` 这个框架内置目录名。Agent 在工作时，根据开发者实际使用的目录名进行操作。

#### 目录结构规范

##### 单插件场景

```
<开发者插件目录>/                    # 例如 my-text-tool/
├── ixplugin.json                   # 插件描述文件
├── __init__.py                     # Python 包标识（可为空）
├── entrance.py                     # 插件入口（必需），继承 IPlugin
├── service.py                      # 业务逻辑层（必需），位于根目录
├── information.py                  # 插件元数据（**必需**），继承 IPluginInfo
├── ui/                             # UI 组件层
│   ├── __init__.py
│   ├── main_widget.py              # 主控件（_create_widget 返回的根控件）
│   ├── components/                 # 可复用 UI 组件
│   │   ├── __init__.py
│   │   └── <component_name>.py
│   └── dialogs/                    # 对话框（如果需要）
│       ├── __init__.py
│       └── <dialog_name>.py
├── function/                       # 业务功能层
│   ├── __init__.py
│   ├── services/                   # 服务类（entrance.py 中的 service.py 的子模块）
│   │   ├── __init__.py
│   │   └── <service_name>.py
│   ├── models/                     # 数据模型（如果需要）
│   │   ├── __init__.py
│   │   └── <model_name>.py
│   └── utils/                      # 工具函数
│       ├── __init__.py
│       └── <util_name>.py
├── icons/                          # 图标资源
│   └── icon.png
├── assets/                         # 其他资源
│   └── ...
└── docs/                          # 插件文档
    └── ...
```

##### 插件集场景（多插件仓库）

```
<开发者插件目录>/                    # 例如 kd-toolkit/
├── ixrepo.json                    # 插件集描述文件（IXRepo.json）
├── plugin-a/                      # 插件 A 子目录（每个插件遵循单插件结构）
│   ├── ixplugin.json
│   ├── __init__.py
│   ├── entrance.py
│   ├── service.py
│   ├── information.py
│   ├── ui/
│   ├── function/
│   ├── icons/
│   ├── assets/
│   └── docs/
├── plugin-b/
│   ├── ixplugin.json
│   ├── ...
```

**注意**：
- `service.py` 必须在插件根目录（与 `entrance.py` 同级），这是框架要求的入口文件的相对位置
- `ui/` 和 `function/` 目录作为 `service.py` 的子模块目录，位于每个插件的根目录下

**导入路径规范**：
- 使用相对导入，避免过长的绝对路径
- `entrance.py` → `from .service import Service`
- `service.py` → `from .ui.main_widget import MainWidget`（Service 需要返回 UI 数据时）
- `ui/main_widget.py` → `from ..service import Service`（UI 回调 Service 时）
- `ui/main_widget.py` → `from ..function.services import SomeService`（使用子模块时）
- **禁止**使用形如 `from <目录名>.ui.components import ...` 的跨包硬编码路径

**职责划分原则**：
- `entrance.py`：作为胶水层，实例化 Service 和 UI 组件，连接两者
- `service.py`（位于根目录）：作为业务协调层，在根目录导入 `function/` 子模块，组织业务逻辑；**禁止**在此文件中直接写 UI 代码
- `information.py`（位于根目录，**必需**）：严格遵循 `docs/core/plugin-system/plugin-development.md` 中 `information.py` 的规范，继承 `IPluginInfo`，定义所有元数据字段
- `ui/` 目录：所有 PySide6/Qt 控件相关代码，**禁止**在此目录下写业务逻辑
- `function/` 目录：纯 Python 业务逻辑，**禁止**在此目录下创建 QWidget

### 步骤 5：创建 PRD 文档

在 `<开发者插件目录>/docs/` 目录下创建 PRD 文档 `PRD.md`，内容需包含：

1. **概述** — 插件解决的问题和核心价值
2. **用户故事** — 谁会用这个插件，为什么需要
3. **功能需求** — 用编号列表列出每个功能点
4. **非功能需求** — 性能、安全、兼容性等
5. **插件类型判断** — 说明这是单插件还是插件集，以及每个插件的 ID 和名称
6. **描述文件清单** — 列出 `IXPlugin.json`（单插件）或 `IXRepo.json` + 各 `IXPlugin.json`（插件集）的内容
7. **目录结构** — 用 tree 图形展示 `<开发者插件目录>/` 下的完整结构
8. **mermaid 架构图** — 展示插件内部模块关系、数据流向

```mermaid
graph LR
    subgraph Plugin [<开发者插件目录>]
        Entrance[entrance.py<br/>插件入口]
        Service[service.py<br/>业务协调层]
        subgraph UI [ui/ UI层]
            Main[ui/main_widget.py<br/>主控件]
            Components[ui/components/<br/>可复用组件]
        end
        subgraph Function [function/ 功能层]
            SubServices[function/services/<br/>服务子模块]
            Models[function/models/<br/>数据模型]
            Utils[function/utils/<br/>工具函数]
        end
        Info[information.py<br/>元数据]
    end
    Entrance --> Service
    Service --> SubServices
    Service --> Models
    Service --> Utils
    Service --> Main
    Main --> Components
    Info -->|service_api| Service
    Service --> External[InstructionX<br/>框架服务]
```

### 步骤 6：创建实现文档

在 `<开发者插件目录>/docs/` 目录下创建实现文档（按功能拆分，可有多个文件）：

1. **文件名规范**：`IMPLEMENTATION_<功能名>.md`
2. **每个文档必须包含**：
   - 功能概述（What — 这个功能做什么）
   - 设计决策（Why — 为什么要这样设计）
   - 实现细节（How — 具体怎么实现）
   - 代码引用（指向具体的 `.py` 文件和行号）
   - **mermaid 流程图**（展示数据流或逻辑流程）
   - **mermaid 类图**（展示类和接口关系）
   - 使用示例（完整的可运行代码片段）
3. **文档间有机联系**：每个文档开头注明相关文档，形成引用链

```mermaid
flowchart TD
    User[用户操作] --> Entrance[entrance.py]
    Entrance --> Service[service.py]
    Service --> SubServices[function/services/*.py]
    Service --> Models[function/models/*.py]
    Service --> Utils[function/utils/*.py]
    Service --> MainWidget[ui/main_widget.py]
    MainWidget --> Components[ui/components/*.py]
    SubServices --> DataProvider[DataProvider<br/>数据持久化]
    SubServices --> LLM[LLMPluginService<br/>LLM服务]
    DataProvider --> Storage[数据存储]
    LLM --> APICall[外部API调用]
```

## 第一性原则（防止盲目蛮干）

在开始任何开发工作前，Agent 必须先回答以下问题。如果无法回答，说明理解不充分，不得开始编码：

1. **这个插件解决什么问题？** — 不是功能列表，而是用户痛点和价值主张
2. **插件如何与 InstructionX 框架交互？** — 它使用哪些框架服务（DataProvider、LLM、TaskManager 等）？这些服务如何注入和使用？
3. **插件的输入是什么？** — 用户操作、外部数据、框架事件？
4. **插件的输出是什么？** — UI 更新、数据存储、API 调用、跨插件通信？
5. **插件的状态是什么？** — 有哪些状态？状态如何转换？用状态机还是数据驱动？
6. **插件的数据流向是什么？** — 从输入到输出，数据经过了哪些处理步骤？
7. **为什么需要这个插件？** — 如果可以用现有功能组合实现，就不应该创建新插件

如果用户需求不够清晰，Agent 应该主动提问澄清，而不是凭猜测开始开发。

## 约束总结

1. **只修改 `<开发者插件目录>`** — 不碰任何框架代码和框架内置插件目录（`plugin/`、`custom_plugin/`）
2. **强制阅读所有文档** — 不阅读不开发
3. **必要时阅读源码** — 深入理解时必须读代码
4. **遵循第一性原则** — 开发前必须回答"这个插件解决什么问题、如何与框架交互、数据流向是什么"
5. **创建描述文件** — 单插件用 `IXPlugin.json`，插件集用 `IXRepo.json` + 各子插件的 `IXPlugin.json`
6. **创建 PRD 文档** — 每个插件的 `docs/PRD.md`
7. **创建实现文档** — 每个插件的 `docs/IMPLEMENTATION_*.md`，图文并茂，充分利用 mermaid
8. **文档间有机联系** — 通过文档内引用链组织
9. **不生成无用文档** — 不要创建空壳文档，每篇文档必须有实质内容
10. **代码质量规范** — 遵循单一职责、函数拆分（≤20行）、状态机、解耦、注释、可维护性、可扩展性、可读性规范
11. **目录结构规范** — `service.py` 和 `information.py` 必须在根目录，`ui/` 和 `function/` 子模块，`service.py` 不直接写 UI 代码，`information.py` 必须严格遵循开发指南规范
12. **多插件场景** — 插件集目录下每个插件是独立子目录，各自遵循单插件结构

## 代码质量规范（强制要求）

### 单一职责原则
- 每个类、每个函数只做一件事
- `entrance.py` 中的插件类只负责协调 UI 和 Service，不写具体实现
- `service.py`（位于根目录）作为业务协调层，通过 `function/` 子模块组织具体业务逻辑
- `ui/main_widget.py` 中的主控件类只负责组装 UI 组件，不写业务逻辑
- `information.py`（**必需**）中的 Info 类只负责元数据定义，**必须**严格遵循 `docs/core/plugin-system/plugin-development.md` 的规范

### 函数拆分规范
- **单个函数不得超过 20 行**，超过必须拆分
- 如果一个函数需要写注释来说明"它做了 X 件事"，就应该拆成 X 个函数
- 提取重复代码为独立函数
- 提取条件分支为独立函数

### 状态机设计
- 对于有多个状态的 UI 组件（如等待/加载/成功/失败），使用状态机模式
- 使用 `mermaid stateDiagram-v2` 图表在实现文档中展示状态转换
- 禁止使用大量 boolean 标志变量，改用明确的状态枚举

### 解耦规范
- `ui/` 目录中的任何文件**禁止**直接写业务逻辑，UI 组件通过 Service 实例调用业务逻辑
- `function/` 目录中的任何文件**禁止**创建 QWidget 或依赖 PySide6
- UI 事件处理函数只做分发，调用 Service 方法
- `service.py`（根目录）不直接创建 QWidget，只通过 `ui/` 模块返回数据或组装结果

### 代码注释规范
- 每个模块开头用 docstring 说明模块职责
- 每个公开方法/属性用 docstring 说明参数、返回值
- 复杂的业务逻辑块添加行内注释说明意图
- 禁止无意义的注释（如 `# 增加 1` → `# i += 1`）

### 可维护性
- 常量定义在文件顶部（版本号、配置值等）
- Magic number 必须定义为命名常量
- 配置项通过 `information.py` 或环境变量注入，不硬编码

### 可扩展性
- 新增功能优先通过添加新 Service 方法实现，而非修改现有方法
- `information.py` 的 `service_api` **必须**随 `service.py` 的方法同步更新（这是强制要求）
- 版本号遵循语义化版本规范（Semantic Versioning）

### 可读性
- 变量名和函数名使用有意义的英文名称，禁止单字母变量（循环变量除外）
- 类名、函数名遵循 Python 命名规范（PascalCase for classes, snake_case for functions/variables）
- 合理使用空行分隔代码逻辑块（不超过 2 行空行）
