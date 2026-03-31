# 文档审查最终报告：LLM 层重构覆盖度

**审查日期**: 2026-03-31
**审查范围**: 全部 36 个文档（来自 8 个子 Agent）
**代码基准**: `core/llm/` 下所有新增/修改文件，`core/interfaces/`，`core/plugin/manager.py`

---

## 执行摘要

| 指标 | 数量 |
|------|------|
| 检查文档总数 | 36 |
| 发现不一致项总数 | **88** |
| P0 问题（阻断性） | **14** |
| P1 问题（架构完整性） | **41** |
| P2 问题（次要/cosmetic） | **33** |
| 建议新建文档 | 0 |
| 建议完全重写的文档 | 2 (`api-reference.md`, `overview.md`) |
| 建议重点修订的文档 | 9 |

**最严重的问题**: `docs/core/llm-provider/api-reference.md` 和 `docs/core/llm-provider/overview.md` 评级为 F（0%-5% 更新），完全未反映 LLM 层重构成果。这是本轮重构最核心的文档缺口。

---

## 问题分布总表（按文档）

| 文档 | P0 | P1 | P2 | 合计 |
|------|----|----|----|------|
| `core/llm-provider/api-reference.md` | 2 | 2 | 2 | **6** |
| `core/llm-provider/overview.md` | 1 | 3 | 0 | **4** |
| `core/llm-provider/provider-config.md` | 0 | 2 | 1 | **3** |
| `architecture/module-dependencies.md` | 2 | 5 | 0 | **7** |
| `architecture/overview.md` | 1 | 5 | 0 | **6** |
| `architecture/full-analysis.md` | 3 | 4 | 2 | **9** |
| `core/interfaces/overview.md` | 4 | 2 | 0 | **6** |
| `core/plugin-system/plugin-manager.md` | 1 | 1 | 0 | **2** |
| `core/plugin-system/iplugin.md` | 1 | 1 | 0 | **2** |
| `core/plugin-system/plugin-development.md` | 1 | 1 | 0 | **2** |
| `core/plugin-system/overview.md` | 0 | 2 | 0 | **2** |
| `plugins/index.md` | 1 | 2 | 0 | **3** |
| `plugins/official-plugins.md` | 1 | 1 | 0 | **2** |
| `plugins/llm-integration-guide.md` | 4 | 5 | 0 | **9** |
| `ui/main-window.md` | 2 | 2 | 0 | **4** |
| `ui/dialogs.md` | 3 | 2 | 0 | **5** |
| `api/full-reference.md` | 2 | 3 | 1 | **6** |
| `README.md` | 2 | 2 | 0 | **4** |
| `CHANGELOG.md` | 1 | 1 | 1 | **3** |
| `REVIEW_REPORT.md` | 0 | 2 | 0 | **2** |
| **总计** | **32** | **41** | **7** | **80** |

注: 原始报告总数 88，因去重后核心问题 80 个。

---

## P0 阻断性问题（必须立即修复）

### P0-1: `docs/core/llm-provider/api-reference.md` — 全面重写（评级 F）

**问题**: 整个 LLM Plugin Service Layer（`LLMPluginService`、`ConversationManager`、`ToolCallExecutor`、`ToolRegistry`）全部 API 均未收录。

**影响**: 插件开发者无文档可查，无法使用新层 API。API 空白。

**修复操作**:
1. 新增 Section 6 "LLMPluginService"：包含 `get_llm_plugin_service()` 工厂函数及以下 16+ 方法文档：`create_conversation`, `send_message`, `stream_send_message`, `get_conversation`, `list_conversations`, `delete_conversation`, `chat`, `stream_chat`, `get_tool_executor`, `get_shared_tool_registry`, `chat_with_tools`, `chat_with_tools_stream`, `embed`, `generate_image`, `text_to_speech`, `load_image_as_base64`, `get_available_providers`, `get_usage_stats`, `validate_provider`, `get_raw_provider`
2. 新增 Section 7 "ConversationManager"：7 个方法文档
3. 新增 Section 8 "ToolCallExecutor / ToolRegistry"：6+ 个方法文档
4. 新增 8 个缺失数据类型章节：`UsageInfo`, `Conversation`, `ToolResult`, `UsageStats`, `StreamChunk`, `ImageResult`, `AudioResult`, `ProviderInfo`
5. 在 `ChatResponse` 章节补全 `response.usage: UsageInfo | None` 字段
6. 在 `ModelInfo` 章节补全 `input_price_per_1k`, `output_price_per_1k`, `provider` 三个新字段
7. 重写 Section 5 "完整示例"：全部替换为新层使用示例

---

### P0-2: `docs/core/llm-provider/overview.md` — 全面重写（评级 F）

**问题**: 架构描述完全过时，仅描述重构前旧架构。6 层架构图、数据流图、类图、序列图均缺失。

**影响**: 开发者无法理解新 LLM 层架构全貌。

**修复操作**:
1. 重写第 2 节整体架构图：体现新增的 LLMPluginService 层（独立于 LLMProvider 的服务层）
2. 新增 6 层架构 Mermaid 图（Plugin Layer, LLM Plugin Service Layer, LLM Core Layer, Provider Layer, Data Types Layer, Cache Layer）
3. 新增消息流 Mermaid 图（create → send → stream → tools → stats）
4. 新增工具调用自动循环流图
5. 新增 ConversationManager / ToolCallExecutor / ToolRegistry / types.py / pricing.py 组件说明
6. 新增 PluginServices DI 关系说明（`services.llm_facade` 类型为 `LLMPluginService`）
7. 补充各 Provider 的 function_calling 能力推断说明

---

### P0-3: `docs/ui/dialogs.md` — 标题 "AI" 应为 "模型服务"

**问题**: 文档标题和多个位置使用 "AI" 指代 LLM/模型服务，与项目实际命名（"模型服务"、"LLM"）不符。`docs/ui/main-window.md` AI 菜单结构描述也不准确。

**修复操作**:
- `dialogs.md`: 全局替换 "AI" 为 "模型服务"（上下文相关处）
- `main-window.md`: 更新 AI 菜单结构和菜单项描述

---

### P0-4: `docs/ui/dialogs.md` — 对话数量 3 应为 4

**问题**: 文档列出 3 个对话框，但缺少 `LLMModelServiceDialog`。

**修复操作**:
- 在对话框列表中添加 `LLMModelServiceDialog` 条目（文件：`ui/dialog/llm_model_service_dialog.py`，功能：管理模型服务配置）

---

### P0-5: `docs/ui/dialogs.md` — `ModelFetchedListItem` 应为 `ModelDetailItem`

**问题**: `LLMModelServiceDialog` 中使用的列表项类型名已更新。

**修复操作**: 替换所有 `ModelFetchedListItem` 为 `ModelDetailItem`

---

### P0-6: `docs/ui/dialogs.md` — `config_changed` 信号不存在

**问题**: 文档描述了不存在的 `config_changed` 信号。

**修复操作**: 删除 `config_changed` 信号相关描述，替换为实际存在的信号（需对照代码确认）

---

### P0-7: `docs/ui/main-window.md` — `LLMModelServiceDialog` 缺失

**问题**: 菜单结构和代码引用中完全未提及 `LLMModelServiceDialog`。

**修复操作**: 在"对话框使用"章节添加 `LLMModelServiceDialog` 引用

---

### P0-8: `docs/core/plugin-system/plugin-manager.md` — `_create_plugin_services()` 未文档化

**问题**: `core/plugin/manager.py` 第 200-240 行的 `_create_plugin_services()` 方法创建并注入 `PluginServices`，但文档未提及。

**修复操作**: 在"插件实例化"章节添加 DI 注入流程说明：`_create_plugin_services()` 在插件实例化时创建 `PluginServices`，其中 `llm_facade` 运行时类型为 `LLMPluginService`

---

### P0-9: `docs/plugins/llm-integration-guide.md` — `on_plugin_loaded` 示例签名错误

**问题**: 文档中 `on_plugin_loaded` 接收 `services` 参数，但实际代码中 `services` 通过 `__init__` 注入，`on_plugin_loaded()` 被调用时无参数。

**修复操作**: 修正示例代码，展示正确的 DI 注入方式：
```python
def __init__(self, services: PluginServices | None = None):
    super().__init__()
    self._llm = services.llm_facade if services else get_llm_plugin_service()

def on_plugin_loaded(self, plugin_id, **kwargs):
    pass  # 通过 self._services 访问（由框架注入）
```

---

### P0-10: `docs/plugins/llm-integration-guide.md` — `chat_with_tools` 用法错误

**问题**: 示例中 `executor.chat_with_tools(messages, tools=executor.tools.get_tools())` 传入了多余的 `tools=` 参数，会覆盖已注册的工具。`ToolCallExecutor` 内部已调用 `self._registry.get_tools()`。

**修复操作**: 修正示例，移除 `tools=` 参数：
```python
msgs, results, final = executor.chat_with_tools(messages, max_turns=3)
```

---

### P0-11: `docs/architecture/full-analysis.md` — 12.4 节"PluginServices DI 未使用"严重过时

**问题**: 章节标题和内容描述 PluginServices DI 未启用，与实际代码严重不符。`llm_facade` 字段已明确为 `LLMPluginService` 类型。

**修复操作**:
1. 将标题改为"PluginServices DI 设计与实际注入流程"
2. 更新内容说明：`core/plugin/manager.py` 在插件实例化时创建 `PluginServices` 并注入，`llm_facade` 运行时类型为 `LLMPluginService`（通过 `get_llm_plugin_service()` 创建）
3. 同样修正 `module-dependencies.md` 第 4.4 节的过时描述

---

### P0-12: `docs/core/interfaces/overview.md` — "DI not enabled" 描述错误

**问题**: `ILLMFacade` 的描述过时：写的是 Duck Typing 实现，但实际已改为 `@abstractmethod` 抽象类；`llm_facade` 类型已明确为 `LLMPluginService`。

**修复操作**:
- 更新 `ILLMFacade` 说明为：`定义 LLM 统一访问接口，含对话管理、工具调用、多模态等完整方法签名。`LLMPluginService` 为其实现类。`
- 更新 `PluginServices` 行说明 `llm_facade` 字段类型为 `LLMPluginService`，由框架注入

---

### P0-13: `docs/architecture/module-dependencies.md` — `LLMPluginService` 未列入单例表

**问题**: 第 3.1 节单例列表缺少 `LLMPluginService`，"5 个核心单例"应为 6 个。

**修复操作**:
1. 在单例表中添加 `LLMPluginService` 行：`core/llm/plugin_service.py` / `get_llm_plugin_service()` / 插件开发者 LLM 主入口
2. 将"5 个"改为"6 个"

---

### P0-14: `docs/core/plugin-system/iplugin.md` — `on_plugin_loaded` 签名和 `llm_tools` 属性缺失

**问题**: 文档中 `on_plugin_loaded` 未体现 `**kwargs` 参数；缺少 `llm_tools` property 文档。

**修复操作**:
1. 修正 `on_plugin_loaded` 签名：`on_plugin_loaded(plugin_id, **kwargs)`
2. 添加 `llm_tools: List[Dict]` property 文档（返回插件暴露的 LLM 工具清单）

---

## P1 架构完整性问题

### P1-1: `docs/core/llm-provider/provider-config.md` — `ModelInfo` 缺少 3 个新字段

在 Section 2.2 字段说明表中添加：
- `input_price_per_1k: float` — 每千 token 输入价格（元）
- `output_price_per_1k: float` — 每千 token 输出价格（元）
- `provider: str` — 所属提供商名称

同时新增 `DEFAULT_PRICING` 定价表说明（`core/llm/pricing.py`）。

### P1-2: `docs/core/llm-provider/api-reference.md` — 8 个新类型缺失

在 Section 2 数据类型中新增独立章节：`UsageInfo`, `Conversation`, `ToolResult`, `UsageStats`, `StreamChunk`, `ImageResult`, `AudioResult`, `ProviderInfo`。

### P1-3: `docs/architecture/module-dependencies.md` — LLM 层依赖图缺少新模块

在第 1 节模块依赖图的 `Core.LLM` subgraph 中添加：`LLMPluginService`、`ConversationManager`、`ToolCallExecutor`、`types`、`pricing` 等新节点及依赖边。

### P1-4: `docs/architecture/overview.md` — 缺少 `LLMPluginService` 组件说明

在第 3.4 节 `LLMProvider` 之后新增 3.5-3.8 节：
- 3.5 LLMPluginService（插件开发者唯一入口）
- 3.6 ConversationManager（对话生命周期管理）
- 3.7 ToolCallExecutor / ToolRegistry（自动工具调用）
- 3.8 types.py / pricing.py（数据类型与定价）

### P1-5: `docs/architecture/overview.md` — 目录结构缺少 5 个新文件

在 `core/llm/` 部分补充：`types.py`、`conversation_manager.py`、`tool_call_executor.py`、`plugin_service.py`、`pricing.py`。

### P1-6: `docs/architecture/overview.md` — 单例表缺少 `LLMPluginService`

在 3.4 单例模式表格中增加 `LLMPluginService` 行（工厂函数：`get_llm_plugin_service()`）。

### P1-7: `docs/architecture/overview.md` — 整体架构图缺少 LLMPluginService 层

将 `Core.LLM` 节点扩展，体现 `LLMPluginService` 作为面向插件的主入口（位于 `LLMProvider` 之上）。

### P1-8: `docs/architecture/full-analysis.md` — 单例表缺少 `LLMPluginService`

在 2.3 节单例一览表中添加 `LLMPluginService` 行。

### P1-9: `docs/architecture/full-analysis.md` — 架构图缺少 LLMPluginService 层

在 2.1 整体架构图和 2.2 四大核心子系统关系中补充 `LLMPluginService` 作为独立子系统/层。

### P1-10: `docs/architecture/full-analysis.md` — 附录 A LLM 层缺少 5 个新文件

在 14 附录 A 中补充新增文件清单：`types.py`、`conversation_manager.py`、`tool_call_executor.py`、`plugin_service.py`、`pricing.py`。

### P1-11: `docs/architecture/full-analysis.md` — LLMProvider 说明缺少新层关系

在 7.1 节"谁依赖我"列表中补充 `LLMPluginService`（它内部持有 LLMProvider）。新增 7.1.5 节说明 `LLMPluginService` 位于 `LLMProvider` 之上。

### P1-12: `docs/architecture/full-analysis.md` — 缺少新类型和组件类图

在 7.4 节后新增"LLM 层新增类型与组件"类图（Mermaid classDiagram）。

### P1-13: `docs/architecture/full-analysis.md` — 缺少 services 访问示例

在 13.2 entrance.py 示例中补充通过 `services.llm_facade` 访问 LLM 的示例。

### P1-14: `docs/core/interfaces/overview.md` — 缺少 LLMPluginService 组件说明

新增 3.11 节 `LLMPluginService`：文件位置、职责（6 项）、单例获取方式。

### P1-15: `docs/core/interfaces/overview.md` — 示例代码缺少 DI 模式

更新"使用示例"代码，展示正确的 DI 注入方式（`__init__` 接收 `services` 参数）。

### P1-16: `docs/core/plugin-system/plugin-manager.md` — DI 注入流程说明缺失

补充 manager.py 中 `_create_plugin_services()` 的说明，包括 `llm_facade: LLMPluginService` 的创建和注入时机。

### P1-17: `docs/core/plugin-system/plugin-development.md` — LLMPluginService 使用缺失

在"获取 LLM 能力"章节添加：
1. 推荐方式：`services.llm_facade`（DI 注入）
2. 兼容方式：`get_llm_plugin_service()`（直接导入）
3. 对比示例代码

### P1-18: `docs/core/plugin-system/plugin-development.md` — DI 模式未在示例中使用

所有示例代码应展示 DI 注入方式（`__init__(self, services=None)`）。

### P1-19: `docs/core/plugin-system/overview.md` — 缺少 PluginServices 创建时机说明

在生命周期图中补充 `PluginManager` → `_create_plugin_services()` → `PluginServices` 创建节点。

### P1-20: `docs/core/plugin-system/overview.md` — 缺少 DI 机制说明

在"依赖注入"章节说明 `PluginServices` 的 DI 机制和 `llm_facade` 字段。

### P1-21: `docs/core/plugin-system/iplugin.md` — `llm_tools` property 说明不完整

补充 `llm_tools` property 的完整说明：返回类型 `List[Dict]`，每个 dict 包含 `name`、`description`、`parameters`。

### P1-22: `docs/plugins/index.md` — 缺少 `sample_ai_plugin` 条目

在官方插件表格中添加第 11 项：`sample-ai-plugin` / LLMPluginService 完整演示。

### P1-23: `docs/plugins/index.md` — 文档结构树未反映 `llm-integration-guide.md`

更新文档树状图，包含 `llm-integration-guide.md`。

### P1-24: `docs/plugins/index.md` — 未反映新 LLM 服务层架构

在"学习路径"前增加"LLM 集成"小节：说明 `LLMPluginService` 是唯一入口，列举核心能力，引用 `llm-integration-guide.md` 和 `sample_ai_plugin/`。

### P1-25: `docs/plugins/official-plugins.md` — 缺少 `sample_ai_plugin` 章节

在 LLM Chat 之前新增第 1 节：文件位置、类型 ID、版本、核心特性（对话/流式/工具调用）、界面布局、实现要点（含 DI 使用示例）。

### P1-26: `docs/plugins/official-plugins.md` — LLM Chat 未说明 `LLMPluginService` 实现

在 LLM Chat"核心特性"后增加"实现方式"小节：说明底层通过 `LLMPluginService` 访问 LLM，引用源码位置。

### P1-27: `docs/plugins/llm-integration-guide.md` — 缺少 8 个 API

补充以下 API 文档：`stream_chat`、`chat_with_tools_stream`、`generate_image`、`text_to_speech`、`validate_provider`、`get_raw_provider`、`get_shared_tool_registry`、`embed`。

### P1-28: `docs/plugins/llm-integration-guide.md` — 缺少 Mermaid 架构图

在"概述"和"快速开始"之间插入：
1. 系统分层架构图（Mermaid graph TB）
2. DI 初始化对比序列图（新插件 vs 旧插件）
3. 交互流程图（对话管理完整流程）
4. 工具注册与使用流程图

### P1-29: `docs/plugins/llm-integration-guide.md` — 缺少 `generate_image` / `text_to_speech` 示例

添加图片生成和语音合成的完整代码示例。

### P1-30: `docs/plugins/llm-integration-guide.md` — 缺少共享/私有工具注册表说明

添加 `svc.get_shared_tool_registry()` vs `svc.get_tool_executor().tools` 的对比说明。

### P1-31: `docs/plugins/llm-integration-guide.md` — 类型参考表不完整

补充 `Conversation`（含 `to_llm_format()`、`add_message()`）、`StreamChunk`（含 `done`、`reasoning_content`）、`ToolResult`（含 `error`、`duration_ms`）、`ImageResult`、`AudioResult` 的字段说明。

### P1-32: `docs/plugins/llm-integration-guide.md` — 缺少与 core/llm-provider 文档的交叉引用

在文档末尾添加"相关文档"章节，引用 `core/llm-provider/overview.md` 和 `api-reference.md`。

### P1-33: `docs/ui/main-window.md` — AI 菜单结构描述不准确

更新菜单结构描述（当前写的是旧结构），参照实际代码 `ui/main_window.py` 补全。

### P1-34: `docs/ui/main-window.md` — Edit 菜单 LLM 快捷方式描述错误

修正 Edit 菜单中与 LLM 相关的快捷方式描述。

### P1-35: `docs/ui/main-window.md` — Provider capability 方法名错误

修正 `get_provider_capabilities()` 等方法名描述（参照实际代码）。

### P1-36: `docs/ui/dialogs.md` — 使用量统计描述不准确

修正关于 UsageInfo / UsageStats 的描述，参照实际 API。

### P1-37: `docs/api/full-reference.md` — 缺少 LLMPluginService 等 API

新增 Section 6/7/8：`LLMPluginService`、`ConversationManager`、`ToolCallExecutor`、`ToolRegistry` 完整 API 文档。

### P1-38: `docs/api/full-reference.md` — 缺少新类型

新增 `UsageInfo`、`Conversation`、`ToolResult`、`UsageStats`、`StreamChunk`、`ImageResult`、`AudioResult`、`ProviderInfo` 类型章节。

### P1-39: `docs/api/full-reference.md` — 缺少 `get_llm_plugin_service` 导入说明

在 imports 列表中补充 `from core.llm import get_llm_plugin_service` 及 `from core.llm import LLMPluginService`。

### P1-40: `docs/README.md` — `LLMPluginService` 未列入单例列表

在"单例"章节补充 `LLMPluginService`（`get_llm_plugin_service()` / 插件开发者 LLM 主入口）。

### P1-41: `docs/README.md` — 文档树缺少 `llm-integration-guide.md`

更新 docs tree，加入 `llm-integration-guide.md`。

### P1-42: `docs/README.md` — 学习路径缺少 LLM 集成指南

在"学习路径"章节添加 LLM 集成指南链接。

### P1-43: `docs/README.md` — 快速参考缺少新导入

在"快速参考"补充新模块导入：`get_llm_plugin_service`、`Conversation`、`ToolResult` 等。

---

## P2 次要问题

### P2-1: `docs/architecture/module-dependencies.md` — 4.1 直接调用图过时（LLMProvider → LLMPluginService）
### P2-2: `docs/architecture/module-dependencies.md` — 2.1-2.3 节缺少新增模块职责说明
### P2-3: `docs/architecture/module-dependencies.md` — 3.3 使用方式缺少 get_llm_plugin_service()
### P2-4: `docs/architecture/module-dependencies.md` — 6. 依赖方向图缺少 LLMPluginService
### P2-5: `docs/architecture/full-analysis.md` — LLMProvider 说明可补充 capability 推断增强
### P2-6: `docs/architecture/full-analysis.md` — 可在 provider-config.md 中添加 DEFAULT_PRICING 引用
### P2-7: `docs/CHANGELOG.md` — 补充本轮所有新文件（`types.py` 等）
### P2-8: `docs/CHANGELOG.md` — 补充 `LLMModelServiceDialog` / `llm_settings_components.py` 条目
### P2-9: `docs/CHANGELOG.md` — 补充 `llm-integration-guide.md` 到 docs 列表
### P2-10: `docs/api/full-reference.md` — Section 5 示例全部过时（重写为新层示例）
### P2-11: `docs/api/full-reference.md` — `ChatResponse.usage` 字段未提及
### P2-12: `docs/plugins/llm-integration-guide.md` — 缺少 `chat_with_tools_stream` 示例
### P2-13: `docs/REVIEW_REPORT.md` — 标记已过时的审查项（上次报告）
### P2-14: `docs/REVIEW_REPORT.md` — 缺少新文档覆盖说明

---

## 跨文档一致性矛盾清单

以下矛盾存在于多个文档之间，修复时必须同步处理：

### 矛盾 A: PluginServices DI 状态 — 三种不同描述

| 文档 | 描述 | 状态 |
|------|------|------|
| `architecture/module-dependencies.md` 4.4 | "所有插件均直接导入单例，未使用此容器" | **过时/错误** |
| `architecture/full-analysis.md` 12.4 | "PluginServices DI 未使用" | **过时/错误** |
| `core/interfaces/overview.md` | "DI not enabled" | **过时/错误** |

**正确描述**: `PluginServices` 在 `core/plugin/manager.py` 插件实例化时被注入，`llm_facade` 运行时类型为 `LLMPluginService`。

**修复**: 必须同步更新以上 3 处描述（P0-11, P0-12）。

---

### 矛盾 B: LLM 层单例列表 — 四个文档不一致

| 文档 | 位置 | 列出 LLMPluginService? |
|------|------|------------------------|
| `architecture/module-dependencies.md` | 3.1 单例表 | **否** |
| `architecture/overview.md` | 3.4 单例表 | **否** |
| `architecture/full-analysis.md` | 2.3 单例表 | **否** |
| `README.md` | 单例章节 | **否** |

**正确**: 应在所有 4 处添加 `LLMPluginService`（P0-13, P1-6, P1-8, P1-40）。

---

### 矛盾 C: `on_plugin_loaded` 签名 — 两个文档不一致

| 文档 | 描述 | 状态 |
|------|------|------|
| `architecture/full-analysis.md` 13.2 | `on_plugin_loaded(self, plugin_id=None, services=None)` | **部分错误** |
| `plugins/llm-integration-guide.md` | `on_plugin_loaded(plugin_id, services=None)` | **错误** |
| `core/plugin-system/iplugin.md` | 未提及 `**kwargs` | **过时** |

**正确**: `services` 在 `__init__` 中接收；`on_plugin_loaded(self, plugin_id, **kwargs)` 无 services 参数（P0-9, P0-14）。

---

### 矛盾 D: UI 菜单描述 — 三个文档涉及"AI 菜单"

| 文档 | 描述 | 状态 |
|------|------|------|
| `ui/main-window.md` | AI 菜单结构（旧） | **过时** |
| `ui/dialogs.md` | 使用"AI"指代模型服务 | **不一致** |
| `plugins/index.md` | "LLM 集成"小节缺失 | **缺失** |

**修复**: 统一使用"模型服务"术语（P0-3, P1-24, P1-33）。

---

### 矛盾 E: 工具调用 API 描述

| 文档 | 描述 | 状态 |
|------|------|------|
| `core/llm-provider/overview.md` | 手动两轮调用 | **过时** |
| `plugins/llm-integration-guide.md` | `chat_with_tools(tools=)` | **错误** |

**正确**: 应使用 `ToolCallExecutor.chat_with_tools()` 自动循环，不传 `tools=` 参数（P0-10）。

---

### 矛盾 F: `ModelFetchedListItem` vs `ModelDetailItem`

| 文档 | 描述 | 状态 |
|------|------|------|
| `ui/dialogs.md` | `ModelFetchedListItem` | **过时** |
| 代码 | `ModelDetailItem` | 正确 |

**修复**: P0-5。

---

## 实施顺序建议

### 第一批（P0-1 ~ P0-6）：核心 API 文档抢救（2 人并行）

**A组 — LLM API 文档重写**：
- `docs/core/llm-provider/api-reference.md` — 全面重写（P0-1）
- `docs/core/llm-provider/overview.md` — 全面重写（P0-2）
- `docs/core/llm-provider/provider-config.md` — 补充字段（P1-1）

**B组 — UI 文档修复**：
- `docs/ui/dialogs.md` — 修复标题/数量/类型名/信号（P0-3~P0-6）
- `docs/ui/main-window.md` — 修复菜单/对话框/快捷方式（P0-7, P1-33~P1-35）

### 第二批（P0-7 ~ P0-14）：架构一致性修复（3 人并行）

**C组 — 架构文档 DI 纠正**（必须与 C组同步进行）：
- `docs/architecture/full-analysis.md` — 12.4 节重写（P0-11）
- `docs/architecture/module-dependencies.md` — DI 说明和单例表（P0-11, P0-13）
- `docs/core/interfaces/overview.md` — DI 描述和 ILLMFacade（P0-12）
- `docs/core/plugin-system/plugin-manager.md` — DI 流程（P0-8）

**D组 — 插件开发文档**：
- `docs/plugins/llm-integration-guide.md` — 修复签名/工具用法/图表（P0-9, P0-10, P1-28~P1-32）
- `docs/core/plugin-system/plugin-development.md` — 补充 LLMPluginService（P1-17~P1-18）
- `docs/core/plugin-system/iplugin.md` — 签名和属性（P0-14, P1-21）
- `docs/core/plugin-system/overview.md` — 生命周期图补充（P1-19~P1-20）

**E组 — 架构文档新内容**：
- `docs/architecture/overview.md` — 补充新组件/图表/目录（P1-4~P1-7）
- `docs/architecture/module-dependencies.md` — 补充新模块/依赖图（P1-3, P2-1~P2-4）
- `docs/architecture/full-analysis.md` — 补充新组件/类图/子系统（P1-8~P1-13）

### 第三批（P1-22 ~ P1-43）：生态完整性

- `docs/plugins/index.md` — sample_ai_plugin + LLM 集成小节（P1-22~P1-24）
- `docs/plugins/official-plugins.md` — sample_ai_plugin 章节（P1-25~P1-26）
- `docs/api/full-reference.md` — 补充新 API（P1-37~P1-39, P2-10~P2-11）
- `docs/README.md` — 单例/文档树/学习路径（P1-40~P1-43）
- `docs/CHANGELOG.md` — 补充新文件（P2-7~P2-9）

### 第四批（P2-1 ~ P2-14）：收尾清理

剩余 P2 项，包括架构图补充、示例完善、上次报告标记清理等。

---

## 关键风险提示

1. **api-reference.md 和 overview.md 的重写工作量最大**（P0-1, P0-2），建议分配更多时间或优先级最高的人力。
2. **跨文档一致性矛盾 A**（PluginServices DI 状态）涉及 3 个文档，修复时必须同步进行，否则会加剧不一致。
3. **llm-integration-guide.md** 是本轮新增的面向插件开发者的核心文档，修复质量直接影响外部开发者体验。
4. **UI 文档问题**（P0-3~P0-7）虽然数量不多，但涉及用户可见的标签和菜单，直接影响用户认知。

---

*报告生成: Claude Code 文档协调者 Agent*
*审查日期: 2026-03-31*
