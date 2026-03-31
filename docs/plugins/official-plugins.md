# 官方插件

> InstructionX 内置的 11 个官方插件详细文档

---

## 1. LLM Chat {#llm-chat}

**文件位置**: `plugin/llm_chat/`

**类型 ID**: `llm-chat`

**版本**: `release.1.0.0`

**开发者**: InstructionX Team

### 功能描述

多提供商 LLM 对话插件，支持流式输出、图片上传、对话历史持久化。

### 核心特性

- 多 Provider 切换（MiniMax、SiliconFlow、GLM、Ollama）
- 流式输出（逐字显示）
- 多模态支持（发送图片，需 Provider 支持 Vision）
- 对话历史持久化
- 上下文长度控制（temperature、max_tokens）

### service_api

| 方法 | 功能 |
|------|------|
| `stream_send_message` | 流式发送消息（生成器，UI 主要使用此方法），返回 Dict 含 chunk/done/error 字段 |
| `send_message` | 发送非流式消息，返回 Dict 含 success/response/model/reasoning/tool_calls/error/error_type 字段 |
| `get_providers` | 获取可用 Provider 列表 |
| `get_models` | 获取指定 Provider 的模型列表 |
| `validate_provider` | 验证 Provider 配置是否正确，返回 Dict 含 valid/message/supports_vision 字段 |

### 界面布局

- 顶部配置栏：Provider 选择、模型选择、刷新/验证按钮
- 参数栏：Temperature 滑块、Max Tokens 下拉、图片上传按钮
- 垂直分割面板：对话历史列表 + 聊天区域
- 输入区：多行输入框（Enter 发送，Shift+Enter 换行）
- 底部：发送/停止按钮、状态标签

---

## 2. 示例 AI 插件 {#示例-ai-插件}

**文件位置**: `plugin/sample_ai_plugin/`

**类型 ID**: `sample-ai-plugin`

**版本**: `release.1.0.0`

**开发者**: InstructionX Team

### 功能描述

展示 `LLMPluginService` 完整能力的示例插件，涵盖对话管理、流式输出、工具调用、多模态等核心功能。

### 核心特性

- 对话管理（创建、发送消息、流式接收）
- 工具注册（私有注册表 + 共享注册表两种方式）
- 工具调用循环（自动两轮调用）
- 多模态（图片加载、TTS）
- 用量统计

### service_api

| 方法 | 功能 |
|------|------|
| `create_conversation` | 创建新对话，返回 conv_id |
| `send_message` | 同步发送消息，返回回复内容 |
| `stream_chat` | 无状态对话（流式） |

### LLM 集成方式

采用依赖注入（DI）方式访问 LLM 服务：

```python
from core.interfaces import IPlugin

class SampleAIPlugin(IPlugin):
    def __init__(self, services=None):
        super().__init__()
        self._llm = (services.llm_facade
                     if services
                     else get_llm_plugin_service())
```

详见 [LLM 集成开发指南](llm-integration-guide.md)。

### 界面布局

垂直分割面板：对话历史列表 + 聊天区域，输入区（多行输入框），发送按钮。

---

## 3. 文本格式化 {#文本格式化}

**文件位置**: `plugin/text_formatting/`

**类型 ID**: `text-formatting`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

提供基础的文本大小写转换功能。

### service_api

| 方法 | 功能 |
|------|------|
| `to_uppercase` | 转换为大写 |
| `to_lowercase` | 转换为小写 |

### 界面布局

两个 GroupBox 分别实现大写和小写转换：输入框 + 按钮。

---

## 4. 代码格式化 {#代码格式化}

**文件位置**: `plugin/code_formatter/`

**类型 ID**: `code-formatter`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

提供代码格式化工具，包括 JSON 格式化、XML 格式化、注释移除和代码压缩。

### service_api

| 方法 | 功能 |
|------|------|
| `format_json` | JSON 格式化（美化输出） |
| `format_xml` | XML 格式化（方法存在，但 UI 中未提供入口） |
| `remove_comments` | 移除代码注释（Python/JavaScript） |
| `compress_code` | 压缩代码（移除空行和多余空格） |

### 界面布局

输入框 + 操作按钮（格式化 JSON、移除注释、压缩代码），结果覆盖显示在输入框（format_xml 方法存在但 UI 中未暴露）。

---

## 5. 字符串工具 {#字符串工具}

**文件位置**: `plugin/string_tools/`

**类型 ID**: `string-tools`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

提供丰富的字符串处理工具，包括大小写转换、反转、统计等。

### service_api

| 方法 | 功能 |
|------|------|
| `to_uppercase` | 转换为大写 |
| `to_lowercase` | 转换为小写 |
| `reverse_text` | 反转文本 |
| `capitalize_words` | 单词首字母大写 |
| `count_words` | 统计单词数 |
| `count_chars` | 统计字符数（可选是否包含空格） |
| `remove_whitespace` | 移除所有空白字符 |

### 界面布局

输入/输出两个 `QTextEdit` + 6 个操作按钮（转大写、转小写、反转文本、首字母大写、移除空白、统计信息）。

---

## 6. 任务管理器 {#任务管理器}

**文件位置**: `plugin/task_manager/`

**类型 ID**: `task-manager`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

完整的任务管理功能，支持任务创建、状态切换/跟踪、优先级设置和导出。

### service_api

| 方法 | 功能 |
|------|------|
| `add_task` | 添加新任务 |
| `update_task_status` | 更新任务状态 |
| `get_tasks` | 获取任务列表 |
| `delete_task` | 删除任务 |
| `get_statistics` | 获取统计数据 |
| `export_tasks` | 导出任务为 JSON/CSV |

### 核心概念

- 使用 DataProvider 持久化任务数据（PRIVATE 命名空间）
- 发布/订阅机制：当任务状态变化时发布 `task_added`、`status_changed`、`task_deleted` 事件
- `TaskReporter` 插件可以订阅这些事件进行统计报告

### 界面布局

双击列表添加任务、优先级下拉框、过滤/刷新/删除/导出/完成按钮、统计信息标签。

---

## 7. 任务报告器 {#任务报告器}

**文件位置**: `plugin/task_reporter/`

**类型 ID**: `task-reporter`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

订阅 TaskManager 的数据变化，实时展示统计信息，生成 JSON/TXT/HTML 格式报告。

### service_api

| 方法 | 功能 |
|------|------|
| `subscribe_to_task_manager` | 订阅指定 TaskManager 的数据 |
| `unsubscribe_from_task_manager` | 取消订阅 |
| `get_statistics_report` | 获取统计数据报告 |
| `get_event_history` | 获取事件历史 |
| `generate_report` | 生成报告文件 |
| `clear_event_log` | 清除事件日志 |

### 核心概念

通过 DataProvider 的发布/订阅机制订阅 TaskManager 插件的 PUBLIC 数据变化。

### 界面布局

TaskManager ID 列表（双击编辑）、订阅/取消订阅按钮、统计信息文本区、报告格式选择、生成报告按钮、事件历史列表（自动刷新每 3 秒）、清除历史按钮。

---

## 8. 图片压缩 {#图片压缩}

**文件位置**: `plugin/image_compressor/`

**类型 ID**: `image-compressor`

**版本**: `release.1.0.0`

**开发者**: KKPIP-Tech

### 功能描述

图片压缩工具，支持质量控制和图片信息查看。

### service_api

| 方法 | 功能 |
|------|------|
| `compress_image` | 压缩图片（保留质量参数） |
| `get_image_info` | 获取图片信息（方法存在，但 UI 中未提供入口） |

### 界面布局

文件输入框 + 浏览按钮、质量滑块（1-100）、压缩按钮。

---

## 9. 后台任务演示 {#后台任务演示}

**文件位置**: `plugin/background_task_demo/`

**类型 ID**: `background-task-demo`

**版本**: `release.1.0.0`

**开发者**: InstructionX Team

### 功能描述

演示 BackgroundTaskManager 的所有任务类型（同步、异步、定时）。

### service_api

> 此插件没有独立的 service.py，所有任务创建逻辑内嵌于 entrance.py 中。
> information.py 中的 service_api 定义在 `methods` 键下，仅作为 API 文档用途，
> 不通过框架的跨插件 API 调用机制暴露。

| 方法 | 功能 |
|------|------|
| `get_tasks` | 获取任务列表（内嵌实现） |
| `get_scheduled_tasks` | 获取定时任务列表（内嵌实现） |
| `create_sync_task` | 创建同步任务（内嵌实现） |
| `create_async_task` | 创建异步任务（内嵌实现） |

### 核心概念

- 演示同步任务（立即完成）
- 演示异步任务（在线程池中执行，带回调）
- 演示定时任务（按间隔重复执行，含工厂机制用于重启恢复）

### 界面布局

任务类型选择、名称输入、持续时间/间隔配置、创建/取消按钮、任务列表（带状态图标）、日志文本区。

---

## 10. 本地服务器 {#本地服务器}

**文件位置**: `plugin/local_server/`

**类型 ID**: `local-server`

**版本**: `release.1.0.0`

**开发者**: InstructionX Team

### 功能描述

启动一个本地 HTTP 服务器，支持 Webhook 和 API 测试。

### service_api

| 方法 | 功能 |
|------|------|
| `get_status` | 获取服务器运行状态 |

### 核心概念

- 使用 `register_long_running_task()` 注册长期任务
- 包含 `stop_callback` 实现优雅停止
- 包含 `restore_callback` 实现应用重启后自动恢复

**实现细节补充**：
- `service.py` 中提供 `get_status()`、`increment_request_count()`、`set_running()`、`save_data()` / `load_data()` 方法
- `entrance.py` 通过 `SignalHolder`（跨线程通信）和 `DataProvider`（状态持久化）实现服务器状态管理
- `on_plugin_loaded()` 中调用 `register_long_running_task_factory()` 注册工厂，用于应用重启后自动恢复服务器
- 停止、状态、恢复三个回调通过 `stop_callback`、`status_callback`、`restore_callback` 参数注册

### 界面布局

端口号配置（1024-65535）、启动/停止按钮、运行状态标签、请求计数、URL 链接、日志文本区。

---

## 11. UI 演示 {#ui-演示}

**文件位置**: `plugin/ui_demo/`

**类型 ID**: `ui-demo`

**版本**: `release.1.0.0`

**开发者**: InstructionX

### 功能描述

展示 InstructionX 所使用的控件效果。

### service_api

> 此插件没有 service.py，API 方法定义在 information.py 中。

| 方法 | 功能 |
|------|------|
| `get_control_list` | 获取控件列表 |

### 界面布局

`QTabWidget` 包含 5 个标签页：

| 标签页 | 内容 |
|--------|------|
| 基础控件 | 按钮、复选框、单选按钮、滑块、进度条 |
| 输入控件 | 输入框、文本框、SpinBox、ComboBox |
| 容器控件 | TabWidget、GroupBox、ScrollArea |
| 列表控件 | ListWidget、TreeWidget、TableWidget |
| 菜单工具栏 | MenuBar、ToolBar、Splitter |

---

## 相关文档

- [第三方插件](thirdparty-plugins.md)
- [插件开发指南](../core/plugin-system/plugin-development.md)
- [插件系统概述](../core/plugin-system/overview.md)

---

*本文档由 Claude Code 自动生成*
