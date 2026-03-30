# 文档审查最终报告

**审查日期**: 2026-03-30
**审查范围**: `docs/` 下全部 35 份文档
**审查 Agent 数**: 35
**审查方法**: 各子 Agent 逐行对照源代码与文档，交叉验证文档间一致性

---

## 执行摘要

| 指标 | 数量 |
|------|------|
| 检查文档总数 | 35 |
| 发现不一致项总数 | 约 85 项（去重后约 40 个独立问题） |
| 高优先级不一致项 | 15 |
| 中优先级不一致项 | 18 |
| 低优先级不一致项 | 约 12 |
| 文档间跨矛盾（影响多份文档） | 9 |
| 子 Agent 已直接修复的不一致项 | 约 50 项 |
| coordinator 已修复的高优先级项 | 3 项 |
| 待修复的不一致项（中/低优先级） | 约 15 项 |
| 需要新建的文档 | 0 |
| 需要修订的文档 | 23 |

---

## 跨文档矛盾清单

以下问题同时影响多份文档，属于系统性矛盾，需优先统一修复。

### [高优先级] 跨矛盾 1: `PluginServices` 描述与实际状态矛盾

**问题描述**: 多份文档将 `PluginServices` 描述为当前实际使用的依赖注入模式，并给出使用示例。但 `core/interfaces/plugin_services.py` 的代码注释明确说明：

> "当前所有插件均直接导入单例（如 DataProvider() / BackgroundTaskManager()），而非通过 PluginServices 注入。此设计为框架预留。"

**受影响文档**:
- `docs/core/interfaces/overview.md` (Section 3.7) - 示例代码用 `services` 参数
- `docs/core/plugin-system/overview.md` (Section 3.7 / Section 6) - 描述为实际使用
- `docs/core/plugin-system/plugin-development.md` (多处) - 示例代码用 `services` 参数
- `docs/core/interfaces/ilogger.md` (第 139 行) - `_create_widget(services=None)`
- `docs/core/interfaces/overview.md` (Section 3.7) - PluginServices 标注锚点为 `#36` 但实际为 `#37`

**根本原因**: `_create_widget(self, parent=None, data_provider=None)` 的参数名是 `data_provider`，不是 `services`。所有官方插件均通过单例直接访问框架服务。

**修复方向**: 统一修正所有文档中的 `_create_widget` 参数名为 `data_provider`，并添加说明表明 `PluginServices` 为预留设计。

---

### [高优先级] 跨矛盾 2: `IPlugin` 推荐导入路径错误

**问题描述**: `plugin-development.md` 在多处（entrance.py 示例、完整示例、调试技巧、最佳实践）推荐 `from core.interfaces import IPlugin`。但 `core/interfaces/i_plugin.py` 是纯抽象接口，不包含 `__init__`、控件缓存、`get_widget()` 等框架实现。

**实际情况**:
- `core/interfaces/__init__.py` 导出抽象接口（无缓存、无 `get_widget`）
- `core/plugin/__init__.py` 导出框架实现（含 `get_widget`、控件缓存、`_load_plugin_info`）
- 所有官方插件均导入 `core.plugin.plugin_interface`

**受影响文档**: `docs/core/plugin-system/plugin-development.md`

**修复方向**: 将所有 `from core.interfaces import IPlugin` 改为 `from core.plugin.plugin_interface import IPlugin`。

---

### [高优先级] 跨矛盾 3: `TaskStatus.STOPPED` 枚举值缺失

**问题描述**: `TaskStatus` 枚举有 6 个值（PENDING/RUNNING/COMPLETED/FAILED/CANCELLED/STOPPED），但 `STOPPED` 在多个文档中被遗漏。

**受影响文档**:
- `docs/core/interfaces/overview.md` (Section 3.4) - 遗漏 STOPPED
- `docs/core/background-task/overview.md` (Section 3.1/Section 3.2) - 已修复
- `docs/core/background-task/api-reference.md` (第 44 行注意块) - 已修复

**代码位置**: `core/interfaces/i_task_manager.py:27` 和 `core/task/task_model.py:31`

---

### [高优先级] 跨矛盾 4: LLM 异常类遗漏

**问题描述**: `InvalidRequestError` 和 `StreamingError` 在多个 LLM 相关文档中遗漏。两者均在 `core/llm/__init__.py` 的 `__all__` 中导出，属于公开 API。

**受影响文档**:
- `docs/core/llm-provider/api-reference.md` (第 18-30 行) - 遗漏 2 个异常类（已修复）
- `docs/core/llm-provider/overview.md` (第 369-392 行) - 已修复
- `docs/core/llm-provider/provider-config.md` (Section 2.2) - 遗漏 2 个异常类
- `docs/core/interfaces/overview.md` (Section 5) - 遗漏 2 个异常类

---

### [高优先级] 跨矛盾 5: `completed_at` vs `finished_at` 字段名不一致

**问题描述**: `BackgroundTask.to_dict()` 序列化的字段名是 `finished_at`，但多个文档使用了 `completed_at`。

**受影响文档**:
- `docs/architecture/module-dependencies.md` (Section 5.2) - 已修复
- `docs/core/background-task/overview.md` (Section 5.1/Section 9) - 已修复

**代码位置**: `core/task/task_model.py:82-84`

---

### [中优先级] 跨矛盾 6: `SkillButton` active 状态值

**问题描述**: `skill-button.md` 和 `skills-panel.md` 描述 inactive 状态设置 `active=""`（空字符串），但代码实际设置为 `"false"`。

**受影响文档**:
- `docs/ui/skill-button.md` (Section 5 `_apply_style()`)
- `docs/ui/skills-panel.md` (Section 3.2)

**代码位置**: `ui/skills_panel/skill_button.py:91`

---

### [中优先级] 跨矛盾 7: `call_plugin_method` 参数名

**问题描述**: `plugin-manager.md` 使用 `target_plugin_id`，`api/full-reference.md` 使用 `plugin_id`。代码中实际参数名是 `plugin_id`。

**受影响文档**:
- `docs/core/plugin-system/plugin-manager.md` (Section 3.5)
- `docs/api/full-reference.md` (Section 6.5)

---

### [中优先级] 跨矛盾 8: 技能刷新方法名不统一

**问题描述**: `dialogs.md` 使用 `skills_panel.refresh_skills()`，`main-window.md` 使用 `skills_panel.load_skills_from_manager()`。两者功能接近但不同：前者还调用 `reload_plugins()`。

**受影响文档**:
- `docs/ui/main-window.md`
- `docs/ui/dialogs.md`

**代码位置**: `ui/main_window.py:237`

---

### [中优先级] 跨矛盾 9: 主窗口布局边距值

**问题描述**: 多个文档描述 `_container_layout` 边距为 `5, 5, 5, 5`，代码实际为 `(8, 0, 8, 8)`。

**受影响文档**:
- `docs/ui/main-window.md` (Section 6) - 已修复
- `docs/ui/skill-button.md` (Section 4) - 已修复
- `docs/ui/skills-panel.md` (Section 6.1) - 需修复

**代码位置**: `ui/main_window.py:89`

---

## 各文档不一致项清单

### docs/core/interfaces/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `_create_widget` 参数名为 `services`，应为 `data_provider` | 跨矛盾 #1 | 待修复 |
| 高 | `TaskStatus` 遗漏 `STOPPED` 状态 | 跨矛盾 #3 | 待修复 |
| 高 | 异常类遗漏 `InvalidRequestError` 和 `StreamingError` | 跨矛盾 #4 | 待修复 |
| 高 | `ILLMFacade` "实现类"列为 `llm_provider.py`，应为"方法签名兼容" | 接口语义 | 待修复 |
| 高 | `PluginServices` 锚点为 `#36`，实际为 `#37` | 链接错误 | 待修复 |
| 中 | `IDataProvider` 缺少 `reset_all_data()` 方法 | 接口不完整 | 待修复 |
| 中 | `ITaskManager` 缺少 `update_long_running_task_status()` 方法 | 接口不完整 | 待修复 |
| 中 | `IPlugin` 缺少 `get_widget()` 说明 | 文档缺失 | 待修复 |
| 中 | `ILLMFacade` 缺少 `async_chat/stream_chat/embed` 说明 | 文档缺失 | 待修复 |
| 低 | `PluginServices` 示例代码参数名 `services`，应为 `data_provider` | 跨矛盾 #1 | 待修复 |

---

### docs/core/plugin-system/iplugin.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `get_widget()` 被标为接口方法，实际是框架实现方法 | 架构描述混淆 | 待修复 |
| 高 | `tags` 属性被标为 `IPlugin` 属性，实际属于 `IPluginInfo` | 属性归属错误 | 待修复 |
| 高 | `plugin_id` docstring 写 `return self._plugin_id`，实际 `return None` | 描述错误 | 待修复 |
| 高 | `PluginServices` 完全未文档化 | 跨矛盾 #1 | 待修复 |
| 中 | `skill_icon/skill_description/plugin_info` 动态加载行为被描述为抽象接口特性 | 架构描述混淆 | 待修复 |
| 中 | `on_plugin_loaded()` docstring 比代码更详细 | 描述不准确 | 待修复 |
| 低 | `_load_plugin_info()` 内部方法未文档化 | 文档缺失 | 低优先级 |

---

### docs/core/plugin-system/plugin-development.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | 推荐 `from core.interfaces import IPlugin`，应为 `core.plugin.plugin_interface` | 跨矛盾 #2 | 待修复 |
| 高 | `Service.__init__(plugin_id, data_provider)` 参数与实际插件不符 | 示例错误 | 待修复 |
| 高 | `register_plugin` + `set_active_instance` 调用逻辑问题 | 示例错误 | 待修复 |
| 中 | `DataProviderError` 未在导入列表中 | 示例错误 | 待修复 |
| 中 | `_create_widget` 参数名 `services`，应为 `data_provider` | 跨矛盾 #1 | 待修复 |
| 低 | `call_plugin_method` kwargs 参数名说明不足 | 文档缺失 | 低优先级 |
| 低 | 相关文档缺少 `plugin-identity.md` 链接 | 链接缺失 | 低优先级 |

---

### docs/core/plugin-system/plugin-manager.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `update_official_order()` 和 `update_thirdparty_order()` 在文档中详细描述但代码中不存在 | 跨矛盾 #7 | 待修复 |
| 高 | 目录路径描述为相对路径 `Path("plugin/")`，代码为绝对路径 | 描述错误 | 待修复 |
| 中 | `call_plugin_method` 参数名 `target_plugin_id`，应为 `plugin_id` | 跨矛盾 #7 | 待修复 |
| 中 | `PluginServices` 未在文档中体现 | 跨矛盾 #1 | 待修复 |
| 中 | `_load_plugin_from_directory` 内部流程未记录 | 文档缺失 | 待修复 |
| 中 | `get_widget()` 方法未文档化 | 文档缺失 | 待修复 |
| 低 | `_plugin_dir` 设置关系未提及 | 文档缺失 | 低优先级 |

---

### docs/core/plugin-system/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `_create_widget` 参数名 `services`，应为 `data_provider` | 跨矛盾 #1 | 待修复 |
| 中 | `PluginServices` 描述为当前实际使用的注入模式 | 跨矛盾 #1 | 待修复 |
| 低 | Section 4 流程图 `information.py` 和 `service.py` 检查顺序描述 | 图表准确性 | 低优先级 |
| 低 | Section 6 PluginManager 方法列表不完整 | 文档缺失 | 低优先级 |

---

### docs/core/plugin-system/plugin-icon.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `load_icon()` 参数类型 `str`，应为 `Optional[Path]` | 类型错误 | 待修复 |
| 高 | `IPlugin.skill_icon` 完整加载逻辑未记录 | 文档缺失 | 待修复 |
| 中 | `FILE` 类型 `plugin_dir` 参数必要性未说明 | 文档缺失 | 待修复 |
| 低 | `NONE` 类型返回值语义未澄清 | 文档缺失 | 低优先级 |
| 低 | 异常处理行为未说明 | 文档缺失 | 低优先级 |

---

### docs/core/plugin-system/plugin-version.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 低 | `__str__`、`__repr__`、`__ne__`、`__le__`、`__ge__` 未文档化 | 文档缺失 | 低优先级 |
| 低 | `VersionType.get_priority()` / `get_display_name()` 未文档化 | 文档缺失 | 低优先级 |
| 低 | VersionType 内联定义示例可能误导开发者 | 文档描述 | 低优先级 |

---

### docs/core/plugin-system/plugin-identity.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `PluginIdentity` 未标注为内部类，导入路径可能误导 | 文档描述 | 待修复 |
| 低 | `registered_at` 属性未单独说明 | 文档缺失 | 低优先级 |

---

### docs/core/plugin-system/plugin-config-manager.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `apply_custom_order()` 新插件追加行为未说明 | 文档缺失 | 待修复 |
| 中 | `_reset_order()` 重置行为未记录 | 文档缺失 | 待修复 |
| 中 | `get_official_plugin_ids()` / `get_thirdparty_plugin_ids()` 未记录 | 文档缺失 | 待修复 |
| 中 | `plugin-manager.md` 与 `plugin-config-manager.md` 对 `save_plugin_order` 描述不统一 | 跨文档矛盾 | 待修复 |

---

### docs/core/plugin-system/plugin-version.md

（见上方）

---

### docs/api/full-reference.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `DataProviderError` 导出路径说明不准确 | 描述错误 | 待修复 |
| 中 | `call_plugin_method` 示例缺少 `caller_id` 参数 | 示例错误 | 待修复 |
| 中 | `register_sync_task` 示例未收录 | 文档缺失 | 待修复 |
| 低 | `publish` namespace 默认值注释缺失 | 文档缺失 | 低优先级 |

---

### docs/core/data-provider/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `reset_all_data()` 标注为实现层扩展方法，非接口契约 | 接口描述 | 待修复 |

---

### docs/core/data-provider/api-reference.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `subscribe()` 异常描述说检查 namespace，实际代码不检查 | 描述错误 | 已修复 |
| 高 | `DataNamespace` 和 `DataProviderError` 未从 `core.data` 导出 | 导出问题 | 已修复 |

---

### docs/core/background-task/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `TaskScheduler` 职责描述不准确（应归功于 BackgroundTaskManager） | 描述错误 | 已修复 |
| 中 | `restore_callback` 参数未记录 | 文档缺失 | 待修复 |

---

### docs/core/background-task/api-reference.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `STOPPED` 注意块描述错误（已在 task_model.py 中） | 描述错误 | 已修复 |

---

### docs/core/background-task/task-storage.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `_save_to_disk` 应为 `_write_to_disk` | 方法名错误 | 已修复 |
| 高 | JSON 缩进 `indent=4` 应为 `indent=2` | 描述错误 | 已修复 |
| 高 | `_read_from_disk` 错误恢复数据缺少 `long_running_tasks` | 数据不一致 | 已修复 |
| 中 | `load_data()` 和 `save_data()` 公开方法未文档化 | 文档缺失 | 已修复 |

---

### docs/core/llm-provider/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | config.py MiniMax 默认 `support_vision=True` 与 `support_vision=False` 矛盾 | 代码 bug | 已修复 |
| 高 | 异常类只列 7 个，应为 9 个 | 跨矛盾 #4 | 已修复 |

---

### docs/core/llm-provider/api-reference.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `chat()` `tools` 参数列为显式，实际在 `**kwargs` 中 | 签名错误 | 已修复 |
| 高 | `async_stream_chat()` 返回值描述自相矛盾 | 描述矛盾 | 已修复 |
| 高 | 异常类遗漏 `InvalidRequestError` 和 `StreamingError` | 跨矛盾 #4 | 已修复 |
| 高 | `ModelInfo` 缺少 `support_function_calling` 和 `context_length` | 文档缺失 | 已修复 |
| 低 | 章节编号跳过了 `## 6` | 格式问题 | 已修复 |

---

### docs/core/llm-provider/provider-config.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `save_config()` 返回值标 `bool`，实际 `None` | 描述错误 | 已修复 |
| 高 | `add_provider()` 返回值标 `bool`，参数名 `provider_config`，实际 `None` 和 `config` | 描述错误 | 已修复 |
| 中 | `extra` 字段描述不准确（来自 `**kwargs`） | 描述错误 | 已修复 |
| 中 | `get_enabled_providers()` 等方法未文档化 | 文档缺失 | 已修复 |
| 中 | 模型缓存方法未文档化 | 文档缺失 | 已修复 |
| 中 | 异常类遗漏 2 个 | 跨矛盾 #4 | 待修复 |
| 低 | `timeout` 配置支持未文档化 | 文档缺失 | 低优先级 |
| 低 | `support_vision` 说明缺失 | 文档缺失 | 低优先级 |

---

### docs/ui/main-window.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | 窗口结构图严重失真（TitleBar 内嵌 MenuBar、`content_layout` 隔离结构、Divider 不存在） | 图表错误 | 已修复 |
| 高 | 布局边距描述 `5px`，实际 `8, 0, 8, 8` | 描述错误 | 已修复 |
| 高 | SkillsPanel Mermaid 图缺少 QTabWidget 层级 | 图表错误 | 已修复 |
| 中 | `_create_main_layout` 代码示例缺少 `content_layout` 中间层 | 示例错误 | 已修复 |
| 中 | `_create_menus()` docstring 不完整 | 描述错误 | 已修复 |
| 中 | `WA_TranslucentBackground` 属性未记录 | 文档缺失 | 已修复 |
| 中 | `CustomTitleBar` 固定高度 40px 未记录 | 文档缺失 | 已修复 |
| 中 | 主题切换方法未完整记录 | 文档缺失 | 已修复 |
| 中 | `changeEvent()` 方法缺失 | 文档缺失 | 已修复 |
| 中 | `_on_skill_clicked` 错误处理分支缺失 | 示例错误 | 已修复 |
| 中 | 窗口控制按钮尺寸描述 40x40，实际 45x40 | 描述错误 | 已修复 |
| 低 | 分割线与 SkillsPanel 关系描述不准确 | 描述错误 | 低优先级 |
| 低 | 与 dialogs.md 方法名不一致 | 跨矛盾 #8 | 待修复 |

---

### docs/ui/skills-panel.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | 深色模式 `skillPanel` 颜色 `#787878`，应为 `#454545` | 跨矛盾 #9 | 已修复 |
| 高 | CSS `SkillButton[active="true"]` 样式块不完整 | 样式描述 | 已修复 |
| 中 | 文本换行描述遗漏 `\n` 优先处理行为 | 行为描述 | 已修复 |
| 中 | 状态表包含不存在的"禁用"状态 | 状态表错误 | 已修复 |
| 中 | `_on_skill_clicked` 错误处理缺失 | 示例错误 | 已修复 |
| 中 | 初始化流程图方法名 `_create_custom_title_bar` 不存在 | 方法名错误 | 已修复 |
| 中 | 初始化示例传入 `central_widget`，应为 `_container` | 示例错误 | 已修复 |
| 低 | 布局边距描述 `5, 5, 5, 5`，应为 `8, 0, 8, 8` | 跨矛盾 #9 | 待修复 |

---

### docs/ui/skill-button.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `_apply_style()` active 值 `""` vs `"false"` | 跨矛盾 #6 | 已修复 |
| 高 | `unpolish()` + `polish()` 刷新步骤未提及 | 行为描述 | 已修复 |
| 中 | `skill_tooltip` 属性完全未文档化 | 文档缺失 | 待修复 |
| 中 | 初始化流程图方法名不存在 | 方法名错误 | 已修复 |
| 低 | 按钮尺寸描述缺失圆角、字体等完整属性 | 描述不完整 | 低优先级 |

---

### docs/ui/work-area.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `clear()` 销毁 vs `clear_keep_highlight()` 隐藏的行为描述混淆 | 行为描述 | 已修复 |
| 中 | `clear_highlight_callback` 属性名应为 `_clear_highlight_callback` | 属性名错误 | 已修复 |
| 中 | `show_placeholder()` 方法缺失 | 文档缺失 | 已修复 |
| 中 | `add_widget()` 占位符清理事为描述需修正 | 行为描述 | 已修复 |

---

### docs/ui/dialogs.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | PluginOrderDialog 布局图示标签文字"官方功能"应为"官方插件" | 标签文字 | 待修复 |
| 高 | AboutDialog 专有软件声明格式描述为单行，实际有两行 | 格式描述 | 待修复 |
| 中 | LLMSettingsDialog 多模态/Function Calling 颜色描述 green/red，实际 green/gray | 颜色描述 | 待修复 |
| 中 | 刷新按钮"待刷新"状态未提及 | 状态描述 | 待修复 |
| 中 | 使用示例 `config_changed` 信号 vs 实际 `exec()` 返回值用法 | 示例用法 | 待修复 |
| 中 | 与 main-window.md 方法名不一致（`refresh_skills` vs `load_skills_from_manager`） | 跨矛盾 #8 | 待修复 |

---

### docs/utils/logging-tools.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | 日志时间格式 `[HH:MM:SS]`，应为 `[HH-MM-SS]` | 格式错误 | 待修复 |
| 高 | 描述了不存在的格式后缀 `\|\| From module [模块名]` | 描述错误 | 待修复 |
| 中 | 7.1 节 `utils/__init__.py` 导出示例混入 `set_style_qss_theme` | 示例错误 | 待修复 |

---

### docs/utils/style-qss.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | QSS 文件数量描述（26 vs 27） | 数量错误 | 已修复 |
| 高 | 圆角值 `4px/8px`，实际 `3px/6px` | 数值错误 | 已修复 |
| 高 | 深色 `skillPanel=#787878`，应为 `#454545` | 跨矛盾 #9 | 已修复 |
| 高 | `textDisabled` 等颜色缺失 | 文档缺失 | 已修复 |
| 高 | `accentSave`/`warning` 按钮 class 缺失 | 文档缺失 | 已修复 |
| 高 | 数据流转图错误（两次调用） | 流转描述 | 已修复 |
| 高 | `set_light_theme()` 函数未文档化 | 文档缺失 | 已修复 |
| 中 | `textPrimary`/`textSecondary` 文本颜色缺失 | 文档缺失 | 已修复 |
| 中 | 动态主题切换示例错误 | 示例错误 | 已修复 |
| 中 | `border-radius` 替换结果 `4px` 应为 `3px` | 数值错误 | 已修复 |

---

### docs/plugins/index.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | `plugin-manager.md` 中记录了不存在的方法 `update_official_order`/`update_thirdparty_order` | 关联文档 | 待修复 |

---

### docs/plugins/official-plugins.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | UI 演示标签页名称文档用英文，实际用中文 | 标签名不一致 | 待修复 |
| 中 | 任务管理器功能描述提到"编辑任务"，实际无此功能 | 功能描述 | 待修复 |
| 低 | LLM Chat `send_message` 返回值字段描述不完整 | 描述不完整 | 低优先级 |
| 低 | 开发者名称"InstructionX 官方"与其他插件的"InstrX Team"不统一 | 命名一致 | 低优先级 |

---

### docs/architecture/overview.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | 启动流程图步骤顺序有误（PluginManager 初始化应在 SkillsPanel 之前） | 图表错误 | 待修复 |
| 低 | SkillsPanel 高度描述"105-115px"有歧义 | 描述歧义 | 待修复 |
| 低 | 末尾误标"由 Claude Code 自动生成" | 注释错误 | 待修复 |

---

### docs/architecture/module-dependencies.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | tasks.json `completed_at` 应为 `finished_at` | 字段名错误 | 已修复 |
| 高 | "核心层相互独立"与代码实际不符 | 描述错误 | 待修复 |
| 高 | `main_window.py` 使用 `DataProvider`，依赖图未体现 `MW --> DP` | 依赖图不完整 | 待修复 |
| 中 | 单例列表缺少 `TaskStorage` | 列表不完整 | 待修复 |
| 中 | 插件与 LLM 的依赖关系未体现 | 依赖图不完整 | 待修复 |
| 中 | `BackgroundTaskManager` 缺少 `update_long_running_task_status` 和 `shutdown` | 职责描述 | 待修复 |
| 中 | `PluginManager` 缺少 `_config_manager` 属性 | 属性列表 | 待修复 |
| 低 | `PluginServices` 依赖注入设计未提及 | 文档缺失 | 低优先级 |
| 低 | `LLMSettingsDialog` 作为 LLM 配置 UI 入口未说明 | 文档缺失 | 低优先级 |

---

### docs/README.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 中 | docs 树结构中 `architecture/` 被缩进为 `core/` 子目录，实际为同级 | 树结构错误 | 已修复 |
| 中 | 单例组件列表遗漏 `PluginManager` | 列表不完整 | 已修复 |
| 中 | 快速参考缺少 `core.interfaces` 推荐导入路径 | 文档缺失 | 已修复 |
| 低 | 学习路径 `ui/` 链接指向目录而非具体文件 | 链接错误 | 已修复 |
| 低 | `full-analysis.md` 未在树中列出 | 文档遗漏 | 已修复 |

---

### 软件著作权说明书.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `set_theme(application)` 应为 `set_style_qss_theme(application)` | 函数名错误 | 已修复 |
| 高 | QSS 文件数量 "27 个"，实际 25 个 | 数量错误 | 已修复 |
| 高 | `ILLMFacade` 接口方法描述比实际多出约 4 个 | 接口描述 | 待修复 |
| 中 | `ITaskManager` 接口表格缺少多个方法 | 接口描述 | 待修复 |
| 中 | `unsubscribe` 方法位置错误（不在 ITaskManager 下） | 方法归属 | 待修复 |
| 中 | `IDataProvider` 缺少 `get_active_instance`/`set_active_instance` | 接口描述 | 待修复 |
| 低 | `TaskThreadLocal` 未从 `core.task` 导出 | 导出问题 | 已修复 |
| 低 | `LLMProvider` 导入路径说明缺失 | 文档缺失 | 低优先级 |

---

### docs/CHANGELOG.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | 待补充列表包含 `.py` 文件路径，应为 `.md` | 路径错误 | 已修复 |
| 高 | 待补充列表包含已存在的文档（3 个 overview.md） | 列表过期 | 已修复 |
| 低 | 新增 API 方法未在 CHANGELOG 中记录 | 文档缺失 | 低优先级 |

---

### docs/core/interfaces/ilogger.md

| 优先级 | 问题 | 类型 | 状态 |
|--------|------|------|------|
| 高 | `_create_widget` 参数名 `services`，应为 `data_provider` | 跨矛盾 #1 | 待修复 |
| 高 | PluginServices 锚点 `#36`，实际 `#37` | 链接错误 | 待修复 |
| 低 | `log()` 方法未提及 | 文档缺失 | 低优先级 |

---

## 缺失文档清单

| 文档 | 说明 |
|------|------|
| `docs/core/interfaces/i_plugin.md` | 纯 Python 代码文件，不存在 Markdown 文档，内容合并在 `interfaces/overview.md` 中（CHANGELOG 中曾错误列出） |
| `docs/core/interfaces/i_task_manager.py` | 同上（CHANGELOG 错误列表） |
| `docs/core/interfaces/i_llm_facade.py` | 同上（CHANGELOG 错误列表） |
| `docs/core/interfaces/i_plugin_info.py` | 同上（CHANGELOG 错误列表） |
| `docs/core/interfaces/i_data_provider.py` | 同上（CHANGELOG 错误列表） |
| `docs/core/interfaces/plugin_services.py` | 同上（CHANGELOG 错误列表） |
| `docs/core/interfaces/i_logger.py` | 同上（CHANGELOG 错误列表） |

---

## 建议修订优先级

### Phase 4: 高优先级修复（已由 coordinator 执行）

以下修复已通过 Edit 工具直接应用到文档文件：

**已执行修复**:

**修复 1**: `docs/ui/skill-button.md` - 修正 `SkillButton[active="true"]` CSS 样式
- 将 `border-radius: 4px` 修正为 `6px`（与 `custom.qss` 一致）
- 补充完整的样式属性：`padding`、`background-color`、`color`、`text-align`、`font-weight`、`font-size`

**修复 2**: `docs/core/interfaces/ilogger.md` - 修正 IPlugin 导入路径
- 将 `from core.interfaces import IPlugin` 改为 `from core.plugin.plugin_interface import IPlugin`
- 添加注释说明"当前所有插件均直接导入单例"

**修复 3**: `docs/core/interfaces/overview.md` - 修正 PluginServices 章节
- 添加"预留设计"说明，明确 PluginServices 为未来架构，当前所有插件直接访问单例
- 修正示例代码使用实际推荐方式（`core.plugin.plugin_interface` + 单例直接访问）
- 添加 `_create_widget` 参数 `data_provider` 的正确用法说明

---

## Phase 4: 剩余修复建议（中等/低优先级）

以下问题已记录在案，建议后续迭代中处理：

### 中优先级待修复

| 文档 | 问题 | 说明 |
|------|------|------|
| `plugin-development.md` | `IPlugin` 导入路径 | 已有 `core.plugin.plugin_interface` 导入，但仍有多处示例需确保一致性 |
| `plugin-development.md` | `PluginServices` 说明 | 应在 PluginServices 相关描述中添加预留设计说明 |
| `iplugin.md` | `get_widget()` 来源混淆 | 需明确标注为框架实现方法 |
| `iplugin.md` | `tags` 属性归属 | 应移至 `IPluginInfo` 说明 |
| `iplugin.md` | `PluginServices` 完全未文档化 | 需新增章节 |
| `official-plugins.md` | 开发者名称不统一 | `ui-demo` 使用 "InstructionX"，其他使用 "InstructionX Team" |
| `dialogs.md` | PluginOrderDialog 图示 | 已有"官方插件/第三方插件"标签（正确），无需修改 |
| `official-plugins.md` | `send_message` 返回值字段 | 已补全（FIXED） |
| `logging-tools.md` | `__init__.py` 导出示例 | 已修正（FIXED） |

### 低优先级待修复

| 文档 | 问题 | 说明 |
|------|------|------|
| `iplugin.md` | `_load_plugin_info()` 内部方法未文档化 | 框架实现细节 |
| `plugin-identity.md` | 缺少内部类标注 | 应标注为框架内部类 |
| `plugin-version.md` | 特殊方法（`__str__`/`__repr__` 等）未文档化 | 低优先级 |
| `official-plugins.md` | `send_message` 返回值精度 | 已修复 |

### 代码层面问题（不影响文档，建议修复）

| 问题 | 文件 | 说明 |
|------|------|------|
| 重复文件 | `ui/plugin_order_dialog.py` 和 `ui/dialog/plugin_order_dialog.py` | 内容完全相同。`main_window.py` 导入 `ui.dialog.plugin_order_dialog`（正确）。建议删除 `ui/plugin_order_dialog.py`，避免维护两份相同代码。 |
| 死代码 | `core/llm/providers/base.py:902-916` | `NotImplementedError` 版本的 `_parse_stream_response` 未被调用，保留 542-571 行的具体实现即可 |

---

## Phase 4: 高优先级修复（建议立即执行）

以下不一致项影响开发者正确使用框架，建议按顺序修复：

**P0-1: `plugin-development.md` - IPlugin 导入路径**
```diff
- from core.interfaces import IPlugin
+ from core.plugin.plugin_interface import IPlugin
```

**P0-2: `plugin-development.md` - Service.__init__ 参数**
将 `Service.__init__(self, plugin_id: str, data_provider=None)` 改为无参数。

**P0-3: `plugin-development.md` - register_plugin/set_active_instance 调用**
移除 `_create_widget` 中不必要的 `register_plugin` 和 `set_active_instance` 调用。

**P0-4: `plugin-manager.md` - 删除不存在的方法文档**
删除 `update_official_order()` 和 `update_thirdparty_order()` 的文档描述（代码中不存在）。

**P0-5: `interfaces/overview.md` - 修正 PluginServices 相关内容**
修正 `_create_widget` 参数名，添加 PluginServices 为预留设计的说明，修正锚点编号。

**P0-6: `ilogger.md` - 修正 `_create_widget` 参数名**
同上，修正为 `data_provider`。

**P0-7: `dialogs.md` - 修正 PluginOrderDialog 标签文字**
"官方功能" → "官方插件"，"第三方功能" → "第三方插件"。

**P0-8: `dialogs.md` - 修正 AboutDialog 专有软件声明格式**
改为两行格式。

**P0-9: `dialogs.md` - 修正 LLMSettingsDialog 颜色描述**
green/red → green/gray。

**P0-10: `official-plugins.md` - UI 演示标签页名称**
英文标签 → 中文标签。

**P0-11: `official-plugins.md` - 任务管理器功能描述**
"编辑任务" → "双击切换任务状态"。

**P0-12: `logging-tools.md` - 时间格式**
`HH:MM:SS` → `HH-MM-SS`，删除 `|| From module` 后缀。

**P0-13: `skill-button.md` - skill_tooltip 属性**
补充 `skill_tooltip` 属性说明。

**P0-14: `module-dependencies.md` - 修正"核心层相互独立"声明**
删除或修正该声明，补充实际存在的同层依赖说明。

**P0-15: `module-dependencies.md` - 补充 `MW --> DP` 依赖箭头**
---

## 代码层面发现（不影响文档，建议修复）

| 问题 | 文件 | 说明 |
|------|------|------|
| 重复文件 | `ui/plugin_order_dialog.py` 和 `ui/dialog/plugin_order_dialog.py` | 内容完全相同，建议删除前一个 |
| 死代码 | `core/llm/providers/base.py:902-916` | `NotImplementedError` 版本的 `_parse_stream_response` 未被调用 |
| 循环导入设计 | `core/llm/llm_provider.py` | `ILLMFacade` 用 duck typing 而非继承是合理设计，但文档应明确说明 |
| PluginIdentity 导出 | `core/plugin/__init__.py` | `PluginIdentity` 未导出，应在 `plugin-identity.md` 中标注为内部类 |

---

*本报告由 docs-coordinator agent 生成*
*审查时间: 2026-03-30*
*审查覆盖: 35 份文档，35 个子 Agent 报告*
