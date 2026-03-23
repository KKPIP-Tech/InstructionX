# Framework API Demo 插件

## 概述

Framework API Demo 插件用于演示 InstructionX 框架提供的所有核心 API 接口的使用方法。

这是一个学习工具，帮助开发者了解如何使用框架的各种功能。

## 使用的接口列表

### 1. DataProvider (core/data/data_provider.py)

| 接口 | 功能 | 正常状态 | 错误状态 |
|-----|------|---------|---------|
| `register_plugin()` | 注册插件实例 | 返回 None | `DataProviderError`: 插件已存在 |
| `unregister_plugin()` | 注销插件实例 | 返回 None | `DataProviderError`: 插件不存在 |
| `set_active_instance()` | 设置活跃实例 | 返回 None | `DataProviderError`: 插件不存在 |
| `get_active_instance()` | 获取活跃实例 | 返回 instance_id 或 None | - |
| `get_plugin_data()` | 读取插件数据 | 返回数据值或默认值 | `DataProviderError`: 插件不存在 |
| `set_plugin_data()` | 写入插件数据 | 返回 None | `DataProviderError`: 插件不存在 |
| `get_all_plugin_data()` | 获取所有数据 | 返回数据字典 | `DataProviderError`: 插件不存在 |
| `subscribe()` | 订阅数据变化 | 返回 None | `DataProviderError`: 目标插件不存在 |
| `unsubscribe()` | 取消订阅 | 返回 None | - |
| `save_asset()` | 保存资源文件 | 返回相对路径 | `DataProviderError`: 保存失败 |
| `load_asset()` | 加载资源文件 | 返回 bytes | `DataProviderError`: 加载失败 |

### 2. BackgroundTaskManager (core/task/background_task.py)

| 接口 | 功能 | 正常状态 | 错误状态 |
|-----|------|---------|---------|
| `register_sync_task()` | 注册同步任务 | 返回 task_id (str) | - |
| `register_async_task()` | 注册异步任务 | 返回 task_id (str) | - |
| `register_scheduled_task()` | 注册定时任务 | 返回 task_id (str) | - |
| `register_long_running_task()` | 注册长期任务 | 返回 task_id (str) | - |
| `get_tasks_by_plugin()` | 获取插件任务列表 | 返回 List[BackgroundTask] | - |
| `get_scheduled_tasks()` | 获取定时任务列表 | 返回 List[ScheduledTask] | - |
| `get_task_status()` | 获取任务状态 | 返回 TaskStatus 或 None | - |
| `cancel_task()` | 取消任务 | 返回 True/False | - |
| `clear_completed_tasks()` | 清理已完成任务 | 返回清理数量 (int) | - |

### 3. LLMProvider (core/llm/llm_provider.py)

| 接口 | 功能 | 正常状态 | 错误状态 |
|-----|------|---------|---------|
| `chat()` | 发送聊天请求 | 返回 ChatResponse | `ConfigurationError`: 无可用 Provider |
| `stream_chat()` | 流式聊天 | 返回生成器 | `ConfigurationError`: Provider 不存在 |
| `async_chat()` | 异步聊天 | 返回 ChatResponse | `ConfigurationError`: 无可用 Provider |
| `embed()` | 发送嵌入请求 | 返回 EmbeddingResponse[] | `ConfigurationError`: 无可用 Provider |
| `get_all_providers()` | 获取所有 Provider | 返回 Dict[str, ILLM] | - |
| `get_enabled_providers()` | 获取已启用 Provider | 返回 Dict[str, ILLM] | - |
| `get_cached_models()` | 获取缓存模型列表 | 返回 List[ModelInfo] | - |
| `get_models()` | 获取模型列表 | 返回 Dict[str, List[ModelInfo]] | - |
| `get_provider()` | 获取指定 Provider | 返回 ILLM 或 None | - |

### 4. PluginManager (core/plugin/manager.py)

| 接口 | 功能 | 正常状态 | 错误状态 |
|-----|------|---------|---------|
| `get_all_plugins()` | 获取所有插件 | 返回 List[IPlugin] | - |
| `get_plugin_by_id()` | 通过 ID 获取插件 | 返回 IPlugin 或 None | - |
| `get_plugin_by_name()` | 通过名称获取插件 | 返回 IPlugin 或 None | - |
| `register_plugin_api()` | 注册插件 API | 返回 None | `ValueError`: 插件不存在 |
| `call_plugin_method()` | 跨插件调用 | 返回方法返回值 | `ValueError`/`RuntimeError` |
| `get_plugin_api()` | 获取插件 API 信息 | 返回 Dict 或 None | - |
| `get_all_apis()` | 获取所有 API | 返回 Dict | - |
| `get_all_function_tools()` | 获取所有 Function Tools (MCP/OpenAI格式) | 返回 List[Dict] | - |
| `get_api_description()` | 获取 API 描述 | 返回 Dict | - |

### 5. LoggerManager (utils/logging_tools.py)

| 接口 | 功能 | 正常状态 | 错误状态 |
|-----|------|---------|---------|
| `debug()` | 调试日志 | 返回 None | - |
| `info()` | 信息日志 | 返回 None | - |
| `warning()` | 警告日志 | 返回 None | - |
| `error()` | 错误日志 | 返回 None | - |
| `critical()` | 严重错误日志 | 返回 None | - |

### 6. IPlugin 基类

| 属性/方法 | 功能 | 正常状态 | 错误状态 |
|----------|------|---------|---------|
| `plugin_name` | 插件名称 | 返回 str | - |
| `plugin_id` | 插件 UUID | 返回 str 或 None | - |
| `_create_widget()` | 创建 UI | 返回 QWidget | - |
| `on_plugin_loaded()` | 加载完成回调 | 返回 None | - |
| `skill_icon` | 技能图标 | 返回 QIcon 或 None | - |
| `skill_description` | 技能描述 | 返回 str | - |
| `skill_tooltip` | 技能工具提示 | 返回 str | - |
| `plugin_info` | 插件信息对象 | 返回 IPluginInfo 或 None | - |

## 使用说明

### 启动插件

1. 运行 InstructionX 主程序
2. 在插件列表中找到 "Framework API Demo" 插件
3. 点击切换到该插件

### 功能标签页

插件包含以下功能标签页：

1. **DataProvider** - 演示数据存取、发布订阅、资源管理
2. **Task** - 演示同步/异步/定时任务
3. **LLM** - 演示聊天、嵌入、模型查询
4. **API** - 演示插件查询、API 发现、Function Calling、跨插件调用
5. **Info** - 框架信息

### 注意事项

1. **LLM 功能**: 需要先在主程序中配置 LLM Provider 才能使用聊天和嵌入功能
2. **定时任务**: 定时任务会在后台自动执行，不需要保持插件界面打开
3. **资源管理**: 保存的资源文件存储在 `data/assets/plugins/` 目录下
4. **日志**: 所有操作都会记录在底部的日志区域

## 文件结构

```
framework_api_demo/
├── __init__.py        # 包初始化
├── entrance.py        # 插件入口
├── service.py         # 服务层
├── information.py    # 插件信息
└── README.md         # 本文档
```

## 依赖

本插件不依赖额外的第三方库，仅使用 InstructionX 框架提供的内置模块。

## 版本

- **版本**: release.1.0.0
- **开发者**: InstructionX
- **许可**: 免费
