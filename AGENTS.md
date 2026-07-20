# AGENTS.md — InstructionX

> 本文件面向 AI 编码代理，介绍项目背景、结构、构建/测试方式与开发约定。所有信息以当前代码为准。
>
> **职责范围**：本文件约束的 Agent 只负责 **InstructionX 框架本身**的开发（`core/`、`ui/`、`utils/`、`workers/`、`scripts/`、`test/` 等框架代码），**不负责 `plugin/` 和 `custom_plugin/` 目录下的插件代码开发**——不修改、不重构这两个目录中的代码（阅读其实现以理解框架被如何使用除外）。

## 项目概述

**InstructionX** 是一个基于 **PySide6** 的**插件式桌面应用框架**（应用型项目，不作为库分发），支持：

- 插件热加载 / 热卸载，GitHub 插件一键安装
- 多厂商 LLM 集成（MiniMax、SiliconFlow、智谱 GLM、Ollama、OpenAI 兼容接口等），多会话管理、工具调用自动化（ToolCallExecutor）、多模态、用量统计
- MCP 协议双向支持（内置 MCP Server 暴露插件 API；MCP Client 连接外部 MCP Server）
- SQLite WAL 数据持久化层（DataProvider）、后台任务系统（BackgroundTaskManager）
- StyleQSS 主题系统（light/dark/auto）、FontMap 多字体系统

- 应用标识：`InstructionX - CE`（组织名 `LumenThread`），当前版本 **Alpha 1.0.2**
- **版本号单一来源为 `core/version.py` 的 `VERSION` 常量**（pyproject 通过 AST 静态读取，修改版本只改这里）
- 平台：**仅支持 Windows 10/11**，Python **>= 3.14**
- 许可证：**InstructionX Commercial Source License（商业源码许可证，非开源）**，详见 `LICENSE`
- 项目主要语言（代码注释、文档、提交信息）：**中文**

## 技术栈与依赖

| 依赖 | 用途 |
|------|------|
| PySide6 >= 6.10 | Qt GUI 框架 |
| requests / aiohttp | HTTP / 异步 HTTP |
| mcp >= 1.0.0 | MCP 协议（FastMCP） |
| orjson | JSON 序列化（SQLite 后端） |
| matplotlib | 保留依赖（旧用量面板图表曾使用；现用量面板已改用 PySide6.QtCharts，暂为第三方插件兼容保留） |
| packaging | 插件依赖版本检查 |

- 依赖单一来源是 `pyproject.toml` 的 `[project].dependencies`；`requirements.txt` 与其保持同步（供 `run.ps1` 使用），**改依赖时两处都要改**。
- 环境管理使用 **uv**（存在 `uv.lock`、`.python-version`、`.venv/`）。

## 构建与运行命令

```powershell
# 安装依赖（uv 虚拟环境）
uv venv
uv pip install -r requirements.txt

# 运行应用（推荐入口，自动建 venv + 装依赖 + 启动）
.\run.bat            # 内部调用 run.ps1

# 或直接运行
.venv\Scripts\python.exe main.py
```

- 入口：`main.py` → `ui.main_window.InstructionXMainWindow`，退出时关闭 `BackgroundTaskManager`。
- 首次运行自动创建 `data/` 和 `config/` 目录。
- **没有 lint / format 配置**（无 ruff/black/mypy/pre-commit），遵循现有代码风格即可。

## 测试

测试框架为 **pytest**（配置在 `pyproject.toml` 的 `[tool.pytest.ini_options]`）。

> **分支约定**：pytest 测试代码仅存在于 **`test` 分支**，`dev` 分支为纯开发分支、不含测试代码（详见「框架开发流程与注意事项 → 分支约定」）。

```powershell
# 安装测试依赖
pip install -e ".[test]"     # pytest>=9.0.3, pytest-qt, pytest-mock, pytest-cov, pytest-asyncio

# 运行测试（与 CI 一致）
python -m pytest test/ -q --tb=short -p no:cacheprovider
```

- 约定：`testpaths = ["test"]`，文件 `test_*.py`、类 `Test*`、函数 `test_*`。
- 已声明 marker：`slow`、`integration`、`ui`（`--strict-markers` 开启，自定义 marker 必须先注册）。
- **注意**：`test/` 下当前仅保留 `test/core/data/test_data_provider.py` 一个有效测试文件（其余旧测试已在重构中删除，残留的 `__pycache__` 是过期产物，不要参考）。现有测试约定：中文 docstring、`tmp_path` fixture、测试单例类时需重置 `XxxManager._instance = None`。
- UI 测试不配置 offscreen 平台，CI 跑在 `windows-latest` 上使用真实 GUI。
- 项目还有一类**独立验证脚本**（非 pytest，放在 `scripts/`，用 `.venv\Scripts\python.exe scripts\<name>.py` 直接运行）：
  - `smoke_*.py`：核心链路无网冒烟测试（LLM、task、utils）
  - `screenshot_*.py`：对话框截图对比脚本（输出到 `scripts/screenshots/`）
  - `_mcp_smoke*.py`：真实 MCP SDK 冒烟测试
  - `demo_*.py`：功能演示脚本
- 另外，`scripts/` 下有 4 个 `test_*.py` 文件属 UI 验证脚本（`test_debug_cluster_framework_api_demo.py`、`test_long_running_task.py`、`test_model_edit_sync.py`、`test_provider_switch_rendering.py`），命名虽似 pytest 测试，但不在 `testpaths = ["test"]` 的收集范围内，需直接运行。

## CI / 部署

- 唯一工作流：`.github/workflows/test.yml`，push 到 `dev`/`main` 及所有 PR 触发，在 `windows-latest` + Python 3.14 上执行 `pip install -e ".[test]"` 后跑 pytest。
- 无打包/发布流程；本项目以源码方式直接运行。

## 框架开发流程与注意事项（重要）

> 本节规范 **InstructionX 框架本身**（`core/`、`ui/`、`utils/` 等）的迭代开发流程，适用于所有框架级改动。插件开发请遵循 `plugin-development.md`。

### 分支约定（重要）

- **`dev` 分支为纯开发分支**：只包含框架源代码，**不允许提交测试代码**（`test/` 目录内容）。
- **测试代码仅存在于 `test` 分支**：所有 pytest 测试代码在 `test` 分支上编写与维护。
- 在 `dev` 上开发时若需运行测试，可切换到 `test` 分支或将测试分支的测试代码合入本地验证，但**不要把测试代码提交进 `dev`**。
- `main` 为发布分支，不直接开发。
- **当前例外**：`test/core/data/test_data_provider.py` 作为 CI 冒烟基线暂存于 `dev` 分支（CI 工作流直接运行 `pytest test/`，依赖该文件存在）；其余测试代码仍只允许在 `test` 分支。待 CI 流程调整后该文件迁回 `test` 分支。

### 版本号与发布说明

- **禁止擅自修改程序版本号**：`core/version.py` 的 `VERSION` 只能由开发者明确指示后修改，任何开发任务都不得顺带变更版本号；
- **发布说明生成**：当开发者将 `dev` 分支提交（合并）到 `main` 分支时，应在提交完成后于**根目录**生成两份发布说明文档，供开发者提交 PR 时书写 Describe 使用：
  1. **本次提交说明**：上一次提交到 `main` 与本次提交之间的全部程序改动、功能改动；
  2. **累计发布说明**：上一次发布 Tag 到本次提交之间的全部程序改动、功能改动；
- 两份文档都**必须注明上一次发布 Tag 的名称**；内容按功能模块分类归纳，使用中文，突出用户可感知的功能变化与重要的内部改动。

### 插件接口兼容性（重要）

- 面向插件的公开接口（`core/interfaces/` 中的 `IPlugin`、`IPluginInfo`、`PluginServices`，以及 `PluginManager`、`DataProvider`、`LLMPluginService`、`MCPManager` 等暴露给插件的 API、插件文件结构约定、自动注册机制）**必须保持良好的向后兼容性**；
- **任何影响插件兼容性的修改**（接口签名变更、行为语义变化、废弃旧 API、插件目录/文件约定调整等），必须先向开发者说明影响范围与迁移成本，**征得开发者同意后方可实施**；
- 确需演进接口时，优先采用新增接口/参数默认值/兼容层等方式平滑过渡，避免直接破坏既有插件。

### 临时文件约定

- 开发过程中产生的**所有临时文件**（调试脚本、试验代码、中间产物、临时数据等）必须存放在根目录 **`temp/`** 目录下，不得散落在项目其他目录；
- `temp/` 已加入 `.gitignore`，**禁止提交**该目录内容；
- 验证完毕的临时文件应及时清理，正式代码与脚本应归入正式目录（如 `scripts/`、`test/`）。

### 开发流程（严格按序执行）

1. **第一性原则，禁止乱猜**：
   - 不臆测需求、不凭空假设实现细节；
   - 先对用户提出的问题/要求进行**总结归纳**，梳理出明确的目标与不确定点；
   - 存在歧义或信息不足时，**先向用户提问澄清**，确认无误后再动手。
2. **理解先行**：阅读 `docs/` 文档和相关程序代码，确认改动边界与受影响面。
3. **最小化改动**：仅修改/创建达成目标所必需的代码，不引入无关重构、不扩大改动范围。
4. **每完成一个小功能就立即测试该功能**：
   - 在 `dev` 分支完成功能后，先通过运行应用 / `scripts/smoke_*.py` 冒烟脚本做即时验证；
   - 为该功能编写或更新的 pytest 测试代码**提交到 `test` 分支**（遵循现有测试约定），并运行 `python -m pytest test/ -q --tb=short -p no:cacheprovider` 确保通过；
   - **修改既有测试**：如确有必要更新 `test` 分支中已有的测试程序，必须先向用户**说明修改目的与必要性**，获得认可后再执行；
   - **新增功能**：必须为其设计**完善的测试用例**（正常路径、边界条件、异常路径），不允许只写“跑通即可”的形式化测试；
   - **不允许**把多个功能堆在一起最后才测试，发现问题时无法定位是哪一个改动引入的。
5. **按功能颗粒度提交 Commit**：
   - 单个功能测试通过后即以**功能为颗粒度**提交一次 Commit，不积压多个功能一起提交；
   - **Commit 风格（语言、格式、是否带前缀等）必须在任务开启前询问用户**，确认后全程保持一致；
   - 执行 `git commit` 等变更操作前必须获得用户确认。
6. **文档同步与交叉验证**：
   - 整体任务完成后，同步更新相关文档（`docs/`、`AGENTS.md`、docstring 等）；
   - 进行交叉验证：对照代码逐一核对文档描述，确保文档能**准确反映程序的实际设计与行为**。

### 代码设计硬性原则

- **严格遵循单一职责原则（SRP）**：一个类/函数只做一件事。新增功能优先考虑新建独立模块/类，而不是塞进现有类。
- **避免巨型类、巨型方法与巨型代码文件**：
  - **硬性限制：每个方法/函数禁止超过 40 行**；超过时必须按职责拆分为多个小方法；
  - 类承担过多职责时应按职责边界拆分为多个协作类；
  - **避免出现巨型代码文件**：单个 `.py` 文件只承载一个内聚的职责主题；文件明显臃肿时（如已接近千行、包含多个互不相关的类/功能块），应按职责拆分为同包下的多个模块文件，并在包级 `__init__.py` 中按需 re-export 保持外部引用稳定；
  - 修改现有代码时若发现目标类/方法/文件已经臃肿，不要继续往里加代码，先评估是否需要拆分。
- **该解耦的就要解耦**：
  - 模块间依赖通过 `core/interfaces/` 的抽象接口交互，不直接依赖具体实现；
  - UI 层不写业务逻辑，业务逻辑下沉到 core/ 或独立的 service 层；
  - 禁止用函数级 import 规避循环导入——出现循环导入说明职责划分有问题，应重新设计依赖方向（函数级 import 的唯一例外见「代码风格」一节，需开发者许可）。
- **避免深层嵌套（倒三角代码）**：
  - 代码嵌套层级**不得超过 3 层**（if/for/while/try 等累计计算）；
  - 善用卫语句（guard clause）提前返回、条件表达式、拆分小方法等手段消除“倒三角”式层层缩进的代码；
  - 复杂分支逻辑优先考虑查表（字典映射）、策略分发替代 if-elif 长链。
- **熟练运用软件工程设计模式**：
  - 根据场景妥善应用工厂模式、状态机、策略、注册表、观察者（发布订阅）、门面等经典设计模式，参考项目既有实践：`core/llm/providers/` 的 `PROVIDER_REGISTRY`（注册表/工厂）、`utils/font_map.py`（状态机）、`DataProvider` 的发布订阅、`LLMPluginService`（门面）；
  - 模式服务于解决问题，不为用模式而用模式；选择模式时优先考虑与项目现有实现的一致性。
- **完善且合理的错误处理机制**：
  - 不得使用裸 `except`、不得静默吞掉异常（`except: pass`）；捕获异常后必须处理或继续抛出，避免程序在异常状态下“带病运行”；
  - **不影响用户使用**：非致命错误不允许导致程序崩溃或卡死，需有降级/恢复路径；后台任务、工作线程中的异常必须捕获并妥善上报，不得跨线程抛出导致 UI 无响应；
  - **该弹窗的要弹窗**：直接影响用户当前操作结果的错误（如操作失败、配置错误、安装失败）必须通过对话框/通知明确告知用户，文案使用中文、说明原因与建议操作；
  - **该记日志的要记日志**：使用 `LoggerManager` 合理分级记录——DEBUG 调试细节、INFO 关键流程节点、WARNING 可自愈的异常、ERROR 影响功能的错误、CRITICAL 致命错误；日志必须包含上下文信息（模块、操作、关键参数），便于定位问题；
  - 弹窗与日志互为补充：面向用户的错误两者都要做（用户看到弹窗，开发者能从日志追溯）。
- **禁止魔法数**：
  - 程序中禁止出现无命名的魔法数字/魔法字符串（如硬编码的 `3000`、`"success"`、索引 `data[2]` 等）；
  - 所有有业务含义的字面量必须定义为**命名常量**（模块级常量、枚举、类常量），命名需表达其含义；
  - 可变的配置型数值（超时、重试次数、阈值、端口等）应进入配置而非硬编码；
  - 仅 `0`/`1`/`None`/空字符串等无语义字面量，以及含义自明的场景（如 `range(3)` 由常量名说明）可豁免。
- **良好的可读性与文档化**：
  - 命名自解释：变量/函数/类名准确表达用途，不使用无意义命名（`a`、`tmp1`、`do_it` 等）；
  - **类介绍**：每个类必须有 docstring，说明职责、设计意图与典型用法；
  - **方法解释**：公开方法与复杂私有方法必须有 docstring，说明功能、**参数**（类型与含义）、返回值、可能抛出的异常；
  - **程序注释**：复杂逻辑、非显而易见的决策、变通方案（workaround）必须有中文注释说明“为什么这样做”，而不是复述代码做了什么；
  - 注释/docstring 使用中文，与代码同步维护——代码变更时注释必须一并更新，禁止出现与代码不符的过期注释。
- **注重未来的可扩展性**：
  - 新能力优先以“可插拔”方式实现（注册表、接口、策略模式等），参考 `core/llm/providers/` 的 `PROVIDER_REGISTRY` 模式；
  - 不硬编码可变的业务参数（路径、超时、阈值等），该配置的进配置，无常量的定义为命名常量；
  - 对外暴露的接口保持向后兼容，破坏性变更需同步更新文档与调用方。

### Code Review 规范

进行 Code Review 时，除功能正确性外，必须重点检查以下方面：

- **文档与代码的一致性**：
  - 代码行为、接口、配置项、目录结构等发生变化时，检查对应文档（`docs/`、`README`、`AGENTS.md`、代码 docstring）是否同步更新；
  - 文档描述必须与实际程序行为保持一致，发现“文档说的是一套、代码做的是另一套”必须指出并修正；
  - 版本号、依赖清单等单一来源约束（`core/version.py`、`pyproject.toml` 与 `requirements.txt`）是否被破坏。
- **是否符合本文件的约束要求**：
  - 分支约定（测试代码不得进入 `dev` 分支）；
  - 代码设计硬性原则（SRP、方法 ≤ 40 行、嵌套 ≤ 3 层、无巨型文件、解耦、错误处理、可扩展性）；
  - 核心设计约定（单例模式、接口与实现分离、UI 线程封送）；
  - 插件接口兼容性（面向插件的公开接口不得被未经许可地破坏）。
- **是否符合编程规范**：
  - 代码风格（中文注释/docstring、type hints、import 置顶分组、无魔法数字）；
  - 可读性与文档化（命名自解释，类/方法 docstring 完整，参数与返回值说明准确）；
  - 安全注意事项（不泄露 API Key、MCP 鉴权、数据层向后兼容）；
  - 是否附带了对应的测试，且测试真实覆盖了本次改动。

### 修改既有代码时的注意事项

- 不破坏现有公共接口；必须修改接口时，更新**所有**调用方（用 Grep 全量检索确认）。
- 单例类保持 `XxxManager._instance` + `get_xxx()` 的既有模式，不要引入新的生命周期管理方式。
- 涉及 `data/`、`config/`、`logs/` 读写逻辑的改动必须保持向后兼容（SQLite 改表结构需新增 migration）。
- 重构只修复接口变化导致的错误，**不改变既有业务逻辑**，尤其不要改动测试中的断言语义。

## 代码组织

```
main.py                     # 应用入口
core/
  __init__.py               # PEP-562 惰性导出，避免 import core 时拉起 PySide6
  version.py                # VERSION 常量（版本单一来源）
  interfaces/               # 抽象接口层：IPlugin、IPluginInfo、IDataProvider、ITaskManager、
                            #   ILLMFacade、PluginServices（依赖注入容器）
  plugin/                   # 插件系统核心
    manager.py              # PluginManager 单例：加载/注册插件、跨插件 API 注册
    plugin_identity.py      # 插件 UUID（优先 {插件目录}/.plugin_info.json，不可写时回退 data/plugin_identity/{插件目录名}.json）
    config_manager.py       # 插件显示顺序（config/plugin_order.json）
    plugin_version.py       # PluginVersion（如 release.1.0.0）、VersionType
    dependency_manager.py   # 插件 Python 依赖检查/自动安装
    github_plugin_installer.py  # GitHub 插件安装（IXPlugin.json / IXRepo.json 描述文件）
  data/                     # 数据持久化层
    data_provider.py        # DataProvider 单例：PRIVATE/PUBLIC 双命名空间、发布订阅、内存缓存
    sqlite_backend.py       # SQLite WAL 后端（默认），schema 迁移
  task/                     # 后台任务系统
    background_task.py      # BackgroundTaskManager 单例：4 线程池、定时/长期任务、优雅关闭
    task_storage.py         # 任务状态持久化（data/tasks.json）
  llm/                      # LLM 框架
    llm_provider.py         # LLMProvider 单例：对话/流式/embedding/模型列表缓存
    plugin_service.py       # LLMPluginService 单例：插件侧门面（会话管理、工具调用）
    tool_call_executor.py   # ToolRegistry + ToolCallExecutor（工具调用多轮循环，默认 max_turns=5）
    providers/              # 各厂商实现 + PROVIDER_REGISTRY
    config.py / secure_keys.py  # Provider 配置（config/llm_providers.json）、API Key 混淆存储
  mcp/                      # MCP 协议
    manager.py              # MCPManager 单例：start_server / connect
    server.py               # MCPHostServer（FastMCP，默认 127.0.0.1:8765，可选 Bearer 鉴权）
    client.py               # 连接外部 MCP Server，工具注册进 ToolRegistry
    bridge.py               # 插件 API 注册表 ↔ MCP Server 双向同步
ui/                         # 界面层
  main_window.py / title_bar.py / usage_panel/
  skills_panel/             # 插件技能面板
  work_area/                # 插件 Widget 宿主区（切换插件时缓存 UI 状态）
  dialog/                   # 各类对话框（LLM 设置、插件顺序、GitHub 安装等）
utils/
  logging_tools.py          # LoggerManager 单例（滚动文件日志，输出 logs/application.log）、get_name()
  themes.py + style_qss/    # StyleQSS 主题系统（30+ 控件样式，light/dark/auto）
  font_map.py               # 字体映射状态机（font/ 目录下 5 个字体家族）
  thread_utils.py           # 工作线程 → UI 线程封送（run_in_ui_thread 等）
plugin/                     # 官方/示例插件（kebab-case 目录，15 个）
custom_plugin/              # 第三方插件目录
workers/                    # 预留扩展
scripts/                    # 冒烟/截图/演示脚本（见“测试”一节）
test/                       # pytest 测试
docs/                       # 完整中文技术文档（架构、核心模块、API、插件开发）
config/ data/ logs/         # 运行时生成：配置、数据、日志
```

### 核心设计约定

- **单例模式**：`PluginManager`、`DataProvider`、`BackgroundTaskManager`、`LLMProvider`、`LLMPluginService`、`MCPManager`、`LoggerManager` 均为单例（`XxxManager._instance`，部分提供 `get_xxx()` 访问器）。测试中重置单例要清 `_instance`。
- **接口与实现分离**：共享类型统一定义在 `core/interfaces/`，其他模块从这里 re-export，避免循环导入。
- 后台任务回调在**工作线程**执行，更新 UI 必须通过 `utils/thread_utils.py` 封送到 UI 线程。

### 插件开发约定（重要）

框架从 `plugin/`（官方）和 `custom_plugin/`（第三方）的**一级子目录**加载插件（跳过 `_` 前缀目录）。每个插件：

- 必需文件：
  - `entrance.py`：定义 `IPlugin` 子类（插件入口/胶水层），构造函数可接收 `services: PluginServices` 注入
  - `information.py`：定义 `IPluginInfo` 子类（版本用 `PluginVersion.from_string("release.x.y.z")`、`service_api` 工具描述等）；提供 `service_api` + `service.py`（类名以 `Service` 结尾）时，框架**自动注册跨插件 API 并转换为 LLM 可调用工具**
  - `service.py`：插件服务/公开 API 层
  - `config/`：插件配置目录
- 硬性规则（见根目录 `plugin-development.md`，注意该文件是面向插件开发代理的规范）：
  - **`ui/` 中不写业务逻辑**：槽函数不超过 5 行，委托给 `service.py` / `function/`
  - **所有 import 必须放在文件顶部**（PEP 8 顺序：标准库/第三方/本地），禁止函数级 import（包括为规避循环导入）
  - 无魔法数字
- GitHub 安装描述文件：`IXPlugin.json`（单插件仓库，文件名大小写敏感）、`IXRepo.json`（多插件仓库）；KKPIP-Tech 组织下的插件自动归类为官方插件。
- 详细文档：`docs/core/plugin-system/plugin-development.md`、`docs/plugins/llm-integration-guide.md`。
- 参考示例：`plugin/api-demo/`（最小完整结构）、`plugin/llm-chat/`。

## 配置与数据文件（运行时生成，勿手改结构）

| 文件 | 用途 |
|------|------|
| `config/llm_providers.json` | LLM Provider 配置（API Key 经 `secure_keys.py` 混淆存储） |
| `config/llm_models_cache.json` | 模型列表缓存 |
| `config/mcp_config.json` | MCP Server/Client 配置 |
| `config/plugin_order.json` | 插件显示顺序 |
| `data/data.db` | 插件数据（SQLite + WAL；另有 `-wal`/`-shm` 伴生文件） |
| `data/tasks.json` | 后台任务状态 |
| `data/llm_usage.json` | LLM 用量记录 |
| `data/conversations.json` | LLM 会话持久化 |
| `{插件目录}/.plugin_info.json` 或 `data/plugin_identity/{插件目录名}.json` | 插件 UUID（优先前者，插件目录不可写时回退后者） |
| `logs/application.log` | 应用日志 |

### 环境变量

| 变量 | 作用 |
|------|------|
| `INSTRUCTIONX_DATAPROVIDER_BACKEND` | `sqlite`（默认）/ `json`（回退旧 JSON 后端，写 `data/data.json`） |
| `INSTRUCTIONX_MCP_CONFIG` | 覆盖 MCP 配置文件路径 |

## 代码风格

- 注释、docstring、日志文案一律使用**中文**（与现有代码一致）。
- 类型标注：新代码应带 type hints。
- import 一律放文件顶部，按标准库 → 第三方 → 本地分组（项目多处用 `# =====...=====` 分隔注释标注分组，见 `main.py`）。**禁止函数级 import**；确有不可避免的必要（如可选依赖的延迟加载）时，必须先向开发者说明必要性并获得许可，且在注释中说明原因。
- 单例访问优先使用已有的 `get_xxx()` 访问器。
- 最小化改动：遵循既有模块边界，UI 层不放业务逻辑。

## 安全注意事项

- **不要提交真实 API Key**：LLM Key 存于 `config/llm_providers.json`（混淆存储，非加密），该目录为运行时数据。
- MCP Server 默认仅监听 `127.0.0.1`；对外开放时务必启用 Bearer token 鉴权（`MCPHostServer` 内置中间件）。
- `dependency_manager.py` 会自动 `pip install` 插件声明的依赖——审查第三方插件的依赖声明。
- `data/`、`config/`、`logs/` 含用户数据，改动其读写逻辑时保持向后兼容（SQLite 后端有 schema 迁移机制，改表结构需新增 migration）。
- 商业源码许可证：再分发、SaaS 化、大规模部署需书面授权，勿将代码当作开源项目处理。

## 文档地图（docs/）

- 架构：`docs/architecture/overview.md`、`module-dependencies.md`
- 插件系统：`docs/core/plugin-system/`（含 `plugin-development.md`）
- 数据层：`docs/core/data-provider/`
- 后台任务：`docs/core/background-task/`
- LLM：`docs/core/llm-provider/`、`docs/plugins/llm-integration-guide.md`
- MCP：`docs/core/mcp/overview.md`
- API 参考：`docs/api/full-reference.md`
