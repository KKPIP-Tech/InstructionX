# UI 测试文档

> UI 组件模块的测试策略、测试用例和维护指南
>
> **本文档已按 `test/ui_tests/` 实际代码刷新**：10 个 `test_*.py` 测试文件（另含 3 个 `conftest.py` 配置与 2 个测试包）、16 个测试类、86 个 `def test_*` 测试函数。§3 用例清单与代码双向核对，代码中每个测试函数在清单中有且仅有一行。

---

## 1. 测试概述

**被测模块**: `ui/`
**测试文件数**: 12 个
**测试类数量**: 21 个（另含 10 个模块级测试函数）
**测试用例总数**: 101 个

> 实测命令（工作目录为项目根）：
> `.venv\Scripts\python.exe -m pytest test/ui_tests --collect-only -q -p no:cacheprovider`
> → `101 tests collected`。本文档的统计与用例清单均以该命令的收集结果为准。

### 1.1 测试文件分布

| 测试文件 | 测试用例数 | 主要覆盖 |
|---------|-----------|---------|
| `test_main_window.py` | 10 | `InstructionXMainWindow` 菜单方法、主布局装配、主题循环与保存、技能点击、缩放方向 |
| `test_skills_panel.py` | 10 | `SkillsPanel` 技能按钮装载、分组控件渲染、点击信号、激活态、页签切换 |
| `test_skills_panel_i18n.py` | 6 | 技能面板插件名跟随界面语言：按钮重建、激活态与展开状态保持、名称未变时不重建 |
| `test_plugin_management_move.py` | 9 | 插件管理对话框「移至官方/第三方插件」按钮文案与移动、安装本地插件包的目标范围跟随当前 Tab |
| `test_app_identity.py` | 6 | 应用标识常量（组织名/应用名）与 `main.py` 接线一致性、图形 API 统一顺序 |
| `test_close_event_dispatch.py` | 6 | 主窗口 `closeEvent` 的三种关闭选择分发、`_force_quit` 直退、防重入 |
| `llm_settings/test_provider_detail_panel.py` | 11 | `ProviderDetailPanel` 自动保存语义、停用遮罩、地址重置、连接检测 |
| `llm_settings/test_provider_list_panel.py` | 10 | `ProviderListPanel` 列表排序、搜索过滤、启停开关、选中/添加信号 |
| `llm_settings/test_provider_editor_dialog.py` | 10 | `ProviderEditorDialog` 预设/自定义创建、实例 id 生成、编辑模式、表单校验 |
| `llm_settings/test_model_edit_dialog.py` | 8 | `ModelEditDialog` 统一 schema 输出、能力标签互斥、编辑模式字段往返 |
| `llm_settings/test_model_toggle_regression.py` | 4 | 模型开关交互三个关联缺陷的回归（选中跳回、模型丢失、悬挂订阅） |
| `usage_panel/test_trend_chart_render.py` | 11 | `TrendPanel` 与 UIKit 图表引擎集成（alpha-v1.0.3 同步新增）：渲染分流、缓存失效、视觉回归、边界 |
| **合计** | **101** | — |

### 1.2 覆盖范围

| 测试文件 | 测试类 | 用例数 | 覆盖的组件 |
|---------|-------|-------|------------|
| `test_main_window.py` | （模块级测试） | 10 | `InstructionXMainWindow`：`_create_menus()`、`_create_main_layout()`、`_cycle_theme()`、`_on_skill_clicked()`、`_get_resize_direction()` |
| `test_skills_panel.py` | （模块级测试） | 10 | `SkillsPanel`、`SkillButton`、`PluginGroupWidget` |
| `test_skills_panel_i18n.py` | `TestLocalizedPluginNameFollows` | 3 | 多语言插件名变化后按钮重建、激活态与分组展开状态保持 |
| `test_skills_panel_i18n.py` | `TestStaticPluginNameUntouched` | 3 | 插件名未变化时不重建、无管理器时空操作 |
| `test_plugin_management_move.py` | `TestMoveButtonText` | 3 | 详情面板「移动」按钮文案随当前 Tab 变化 |
| `test_plugin_management_move.py` | `TestMovePlugin` | 4 | 移动插件目录、列表刷新、未选中提示、失败提示 |
| `test_plugin_management_move.py` | `TestLocalInstallScope` | 2 | 打开本地插件包安装对话框时传入当前 Tab 的范围 |
| `test_app_identity.py` | `TestOrganizationName` | 4 | 组织名常量、`main.py` 的组织名/应用名接线 |
| `test_app_identity.py` | `TestGraphicsApiUnification` | 2 | `main()` 中 `QQuickWindow.setGraphicsApi(OpenGL)` 调用与顺序 |
| `test_close_event_dispatch.py` | `TestCloseEventDispatch` | 6 | `closeEvent` / `_ask_close_choice` / `_minimize_to_tray` 分发 |
| `llm_settings/test_provider_detail_panel.py` | `TestAutoSave` | 4 | 密钥 / 地址即时落盘、总开关与停用遮罩 |
| `llm_settings/test_provider_detail_panel.py` | `TestBaseUrlReset` | 1 | 地址重置回退目录默认 |
| `llm_settings/test_provider_detail_panel.py` | `TestConnectionCheck` | 4 | `ConnectionCheckWorker` 全链路与完成槽 |
| `llm_settings/test_provider_detail_panel.py` | `TestLoadInstance` | 2 | 实例加载头部与空态 |
| `llm_settings/test_provider_list_panel.py` | `TestListRendering` | 2 | 列表渲染与 `order` 排序、空态 |
| `llm_settings/test_provider_list_panel.py` | `TestSearchFilter` | 4 | 按实例名 / 模型名 / 预设显示名搜索与清空恢复 |
| `llm_settings/test_provider_list_panel.py` | `TestToggleAndSignals` | 4 | 启停开关落盘、`sig_toggle` / `sig_select` / `sig_add`、订阅驱动重建 |
| `llm_settings/test_provider_editor_dialog.py` | `TestGenerateInstanceId` | 3 | `generate_instance_id()` 规则 |
| `llm_settings/test_provider_editor_dialog.py` | `TestCreateFromPreset` | 2 | `MODE_CREATE` 从预设创建 |
| `llm_settings/test_provider_editor_dialog.py` | `TestCreateCustom` | 3 | `MODE_CREATE` 自定义 OpenAI 兼容服务与校验 |
| `llm_settings/test_provider_editor_dialog.py` | `TestEditMode` | 2 | `MODE_EDIT` 编辑既有实例 |
| `llm_settings/test_model_edit_dialog.py` | `TestCreateMode` | 3 | 新建模式 schema 输出、分组推断、ID 校验 |
| `llm_settings/test_model_edit_dialog.py` | `TestCapabilityExclusion` | 3 | 能力标签互斥与闭集顺序 |
| `llm_settings/test_model_edit_dialog.py` | `TestEditModeRoundTrip` | 2 | 编辑模式字段往返与未设置语义 |
| `llm_settings/test_model_toggle_regression.py` | `TestModelToggleRegression` | 4 | 模型开关交互回归 |
| `usage_panel/test_trend_chart_render.py` | `TestRenderRouting` | 5 | 全量 `set_option` 与增量 `set_stream_data` 的选择逻辑 |
| `usage_panel/test_trend_chart_render.py` | `TestCacheInvalidation` | 3 | 静态层缓存失效与视觉回归（`@pytest.mark.ui`） |
| `usage_panel/test_trend_chart_render.py` | `TestBoundaries` | 3 | 单日区间、跨年区间、无记录序列 |
| **合计** | **21 个测试类 + 2 个模块级分组** | **101** | — |

---

## 2. 测试策略

### 2.1 隔离措施

- `InstructionXMainWindow` 使用 mock 绕过 `_create_menus()`、`_create_main_layout()` 和 `_load_saved_theme()`
- `SkillsPanel` 和 `WorkArea` 被 mock
- `DataProvider`、`PluginManager`、`TrayIconManager` 被 mock
- 使用 `qtbot` fixture 管理 Qt 组件生命周期
- 使用 `qapp_instance` 提供 QApplication：进程内已有 QApplication（pytest-qt 建立的真实平台实例）时直接复用，仅在尚无实例时才回退 `-platform offscreen`
- `llm_settings/` 下由目录级 autouse fixture 隔离 LLM 运行环境（配置路径指向 `tmp_path`、注册 Mock 适配器，无真实网络访问）、隔离 QSettings 到临时 ini 文件，并拦截反馈层（`block_message_boxes` 非阻塞记录调用）

### 2.2 测试数据

- 主题状态使用 `'auto'`、`'light'`、`'dark'`
- 菜单项使用中文名称（编辑、用户中心、AI、帮助）
- 技能面板使用 `MagicMock` 插件对象（`plugin_name` / `skill_icon` / `skill_description`）
- LLM 设置测试经 `mock_config_factory` 构造 Mock 实例配置，`usage_panel` 渲染测试使用模运算构造的每日聚合序列

### 2.3 关键 Fixtures

```python
# test/conftest.py（全局）
qapp_instance        # Session 级 QApplication（已有实例则复用，否则 offscreen）
qtbot                # Qt 测试工具
reset_singletons     # autouse：重置全部单例
mock_logger          # autouse：禁用日志输出

# test/ui_tests/conftest.py（目录级）
_auto_dismiss_close_confirm  # autouse：把主窗口 _ask_close_choice 替换为返回 CANCEL，
                             #   防止收尾 close() 弹出真实模态「关闭确认」对话框（CI 挂起）

# test/ui_tests/llm_settings/conftest.py（LLM 设置包）
isolated_llm_environment  # autouse：LLM 路径隔离 + 单例重置 + Mock 适配器注册
isolated_qsettings        # autouse：QSettings 重定向到临时 ini
mock_config_factory       # Mock 适配器实例配置工厂
block_message_boxes       # 拦截反馈层（warn/confirm/notice）并记录调用

# 各测试文件内的辅助函数
_make_window(mocker, qtbot)     # test_close_event_dispatch.py：构建重依赖全 Mock 的主窗口
_make_panel(qtbot, ...)          # 各 llm_settings / usage_panel 测试内构造被测面板
```

---

## 3. 测试用例

> §3 各表按**测试文件 → 测试类**分组，列出 `test/ui_tests/` 下全部 86 个测试函数（与 pytest 收集结果一一对应）。
> 「说明」列来源约定：优先取该测试函数 docstring 的中文表述（docstring 为英文时做中文直译或中文归纳，保留方法名/类名等术语原文）；无 docstring 时取紧邻的中文注释；两者都没有时按函数名与所属测试类归纳（此类条目粒度较粗）。
> 代码中未提供的信息（断言细节、测试步骤、优先级、风险关联）不在本表补充。原 `TC-UI-XXX` 编号体系未落到代码中（测试函数 docstring 与代码注释里都没有该编号），用例统一按「测试文件 + 测试类 + 函数名」定位。

### 3.1 `test_app_identity.py`（6 个用例）

> 覆盖应用标识常量与 `main.py` 的接线一致性、图形 API 统一顺序；通过 AST 静态解析 `main.py` 实现，不启动应用。

#### 3.1.1 `TestOrganizationName`（组织名常量的值与一致性）

| 用例函数名 | 说明 |
|-----------|------|
| `test_qsettings_org_name_is_kkpip_tech` | QSettings 组织名为 KKPIP-Tech（与 GitHub 组织一致） |
| `test_main_py_organization_name_matches_qsettings` | `main.py` 的 `setOrganizationName` 字面量必须与 `QSETTINGS_ORG_NAME` 一致 |
| `test_main_py_application_name` | `main.py` 的 `setApplicationName` 为 `InstructionX - CE` |
| `test_qsettings_app_name` | QSettings 应用名常量（连字符形式，与注册表路径一致） |

#### 3.1.2 `TestGraphicsApiUnification`（OpenGL 统一必须先于 QApplication 实例化）

| 用例函数名 | 说明 |
|-----------|------|
| `test_set_graphics_api_called_with_opengl` | 存在 `QQuickWindow.setGraphicsApi(...GraphicsApi.OpenGL)` 调用 |
| `test_graphics_api_set_before_qapplication` | `setGraphicsApi` 在源码顺序上先于 `QApplication(...)` 实例化 |

---

### 3.2 `test_close_event_dispatch.py`（6 个用例）

> 覆盖主窗口 `closeEvent` / `_ask_close_choice` / `_dispatch_close_choice` 的分发行为。主窗口经 mock 构建（SkillsPanel / WorkArea / PluginManager / DataProvider / TrayIconManager 均替换为 Mock），event 使用真实 `QCloseEvent` 实例，以 `isAccepted()` 状态断言 accept / ignore 的真实效果。

#### 3.2.1 `TestCloseEventDispatch`（三种 CloseChoice 分发、`_force_quit` 直放、防重入）

| 用例函数名 | 说明 |
|-----------|------|
| `test_initial_close_state_defaults` | 新建主窗口的关闭编排状态均为初始值（不直放、无防重入） |
| `test_exit_choice_accepts_and_quits` | EXIT：`_force_quit` 置位 + `event.accept` + `QApplication.quit` 被调 |
| `test_minimize_choice_ignores_and_minimizes_to_tray` | MINIMIZE_TO_TRAY：`event.ignore` + 调用 `_minimize_to_tray`，不退出 |
| `test_cancel_choice_ignores_only` | CANCEL：仅 `event.ignore`，不最小化、不退出 |
| `test_force_quit_skips_dialog_and_accepts` | `_force_quit` 已置位：直接 accept 退出，不弹确认框 |
| `test_reentry_while_dialog_showing_is_ignored` | `_close_dialog_showing` 置位：重入关闭直接 ignore，不再弹窗、不最小化 |

---

### 3.3 `test_main_window.py`（10 个用例）

> 全部为模块级测试函数（无测试类），覆盖 `ui.main_window.InstructionXMainWindow`。

#### 3.3.1 （模块级测试函数）

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_menus_creates_expected_menus` | `_create_menus()` 及菜单相关辅助方法存在（编辑 / 用户中心 / AI / 帮助菜单） |
| `test_create_main_layout_instantiates_components` | `_create_main_layout()` 装配 `plugin_manager`、`skills_panel`、`work_area` |
| `test_cycle_theme_cycles_all_states` | `_cycle_theme()` 按 auto → light → dark → auto 循环 |
| `test_theme_change_saved_via_dataprovider` | `_cycle_theme()` 调用 `_save_theme()`，主题经 DataProvider 保存 |
| `test_on_skill_clicked_with_valid_widget` | `_on_skill_clicked()` 在插件 widget 有效时将其加入工作区 |
| `test_on_skill_clicked_with_none_widget` | `_on_skill_clicked()` 在 widget 为 None 时于工作区显示错误标签 |
| `test_get_resize_direction_top_left` | `_get_resize_direction()` 在左上边缘返回 `'top-left'` |
| `test_get_resize_direction_bottom_right` | `_get_resize_direction()` 在右下边缘返回 `'bottom-right'` |
| `test_get_resize_direction_center` | `_get_resize_direction()` 在中心区域返回 None |
| `test_menu_actions_exist_and_connected` | 菜单相关动作方法存在且可调用（含 `_create_ai_menu`、`_open_about_dialog`） |

---

### 3.4 `test_skills_panel.py`（10 个用例）

> 全部为模块级测试函数（无测试类），覆盖 `ui.skills_panel.panel.SkillsPanel`。

#### 3.4.1 （模块级测试函数）

| 用例函数名 | 说明 |
|-----------|------|
| `test_set_plugin_manager_stores_reference` | `set_plugin_manager()` 保存插件管理器引用 |
| `test_add_skill_button_creates_skill_button` | `add_skill_button()` 创建 `SkillButton` 控件并加入布局 |
| `test_add_skill_button_official_adds_to_official_tab` | `add_skill_button(is_official=True)` 将按钮加入官方页签布局 |
| `test_add_skill_button_thirdparty_adds_to_thirdparty_tab` | `add_skill_button(is_official=False)` 将按钮加入第三方页签布局 |
| `test_load_skills_from_manager_clears_and_reloads` | `load_skills_from_manager()` 清空既有按钮后从插件管理器重新装载 |
| `test_load_skills_from_manager_renders_group_widget` | `load_skills_from_manager()` 遇到 `("group", ...)` 项时渲染 `PluginGroupWidget`，组内插件不直接加入页面布局 |
| `test_on_skill_clicked_emits_signal_with_plugin` | `_on_skill_clicked()` 携带插件对象发射 `skill_clicked` 信号 |
| `test_on_skill_clicked_sets_button_active_state` | `_on_skill_clicked()` 将点击的按钮置为激活态 |
| `test_clear_active_state_clears_all_button_states` | `clear_active_state()` 清除全部按钮的激活态 |
| `test_tab_switching_shows_correct_buttons` | 切换页签时仅显示对应页签的按钮 |

---

### 3.5 `llm_settings/test_provider_list_panel.py`（10 个用例）

> 覆盖 `ui/dialog/llm_settings/provider_list_panel.py` 的列表渲染与 order 排序、搜索联动（实例名/预设名/模型名）、启停开关落盘、选中与添加信号。

#### 3.5.1 `TestListRendering`（列表渲染与排序）

| 用例函数名 | 说明 |
|-----------|------|
| `test_rows_sorted_by_order` | 实例按配置 `order` 升序渲染 |
| `test_empty_list_placeholder_state` | 无实例时列表为空且无选中（边界） |

#### 3.5.2 `TestSearchFilter`（搜索联动过滤）

| 用例函数名 | 说明 |
|-----------|------|
| `test_search_by_instance_name` | 按实例名搜索：未命中项隐藏 |
| `test_search_by_model_name` | 搜索命中实例下模型 id/name（`custom_models`） |
| `test_search_by_preset_display_name` | 搜索命中预设显示名（实例关联 glm 预设） |
| `test_clear_search_restores` | 清空搜索词后全部恢复可见 |

#### 3.5.3 `TestToggleAndSignals`（启停开关与信号）

| 用例函数名 | 说明 |
|-----------|------|
| `test_toggle_persists_enabled_chat` | 列表项开关切换写 `enabled_chat` 落盘并发射 `sig_toggle` |
| `test_select_emits_sig_select` | 选中变化发射 `sig_select`（实例 id） |
| `test_add_button_emits_sig_add` | 「＋ 添加提供商」按钮发射 `sig_add` |
| `test_config_change_triggers_reload` | 外部配置变更（订阅驱动）触发列表重建 |

---

### 3.6 `llm_settings/test_provider_detail_panel.py`（11 个用例）

> 覆盖 `ui/dialog/llm_settings/provider_detail_panel.py` 的自动保存语义（密钥/地址编辑即时落盘）、总开关与停用遮罩、地址重置回退目录默认、连接检测（成功自动启用 / 失败错误展示）。

#### 3.6.1 `TestAutoSave`（自动保存语义，无保存按钮、编辑即时落盘）

| 用例函数名 | 说明 |
|-----------|------|
| `test_api_key_saved_on_editing_finished` | 密钥编辑完成即落盘 |
| `test_base_url_saved_on_editing_finished` | 地址编辑完成即落盘（去首尾空白） |
| `test_master_switch_persists_and_overlay` | 总开关切换写 `enabled_chat` 落盘，停用时主体覆盖遮罩 |
| `test_load_disabled_instance_shows_overlay` | 加载已停用实例：总开关关态 + 遮罩可见 |

#### 3.6.2 `TestBaseUrlReset`（地址重置与目录默认）

| 用例函数名 | 说明 |
|-----------|------|
| `test_reset_clears_override` | 「重置」清空实例覆写并显示目录默认地址（占位符/文本） |

#### 3.6.3 `TestConnectionCheck`（连接检测，`ConnectionCheckWorker` 后台线程）

| 用例函数名 | 说明 |
|-----------|------|
| `test_check_success_shows_count` | 检测成功：状态显示「连接正常 · N 个模型」（Worker 全链路） |
| `test_check_success_auto_enables_disabled_instance` | 检测成功且实例未启用时自动开启 `enabled_chat`（完成槽逻辑） |
| `test_check_failure_shows_error` | 检测失败：状态显示错误详情（异常路径） |
| `test_late_signal_from_other_instance_ignored` | 迟到信号（非当前实例）被忽略（边界） |

#### 3.6.4 `TestLoadInstance`（实例加载与空态）

| 用例函数名 | 说明 |
|-----------|------|
| `test_header_populated` | 加载实例后头部名称与总开关状态正确 |
| `test_load_none_shows_empty_state` | 加载 None：空态容错不崩（边界） |

---

### 3.7 `llm_settings/test_provider_editor_dialog.py`（10 个用例）

> 覆盖 `ui/dialog/llm_settings/provider_editor_dialog.py` 的预设创建（字段预填目录默认值）、自定义创建（openai-compatible）、实例 id 生成规则、`MODE_EDIT` 编辑、表单校验。

#### 3.7.1 `TestGenerateInstanceId`（实例 id 生成规则）

| 用例函数名 | 说明 |
|-----------|------|
| `test_first_preset_instance_uses_preset_id` | 预设尚无实例时直接使用 `preset_id`（向后兼容） |
| `test_conflict_generates_short_code` | `preset_id` 已被占用时生成带短码后缀的 id |
| `test_custom_prefix` | 自定义实例使用 `custom-` 前缀 |

#### 3.7.2 `TestCreateFromPreset`（`MODE_CREATE`：从预设创建）

| 用例函数名 | 说明 |
|-----------|------|
| `test_prefill_and_create` | 选择预设后字段预填目录默认值，确认后配置落盘 |
| `test_second_instance_gets_short_code` | 同预设第二实例：实例 id 为短码形式 |

#### 3.7.3 `TestCreateCustom`（`MODE_CREATE`：自定义 OpenAI 兼容服务）

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_custom_instance` | 自定义创建：adapter 为 `openai-compatible`，`preset_id` 为 None |
| `test_custom_requires_base_url` | 自定义实例缺 Base URL：校验失败弹中文警告且不落盘（异常路径） |
| `test_empty_name_rejected` | 名称为空：校验失败（异常路径） |

#### 3.7.4 `TestEditMode`（`MODE_EDIT`：编辑既有实例）

| 用例函数名 | 说明 |
|-----------|------|
| `test_edit_updates_fields_and_keeps_key` | 编辑名称/地址；API Key 留空不修改 |
| `test_edit_missing_instance_warns` | 编辑不存在的实例：中文警告且不接受（异常路径） |

---

### 3.8 `llm_settings/test_model_edit_dialog.py`（8 个用例）

> 覆盖 `ui/dialog/llm_settings/model_edit_dialog.py` 的新建/编辑模式、能力标签互斥、`context_length` 与定价往返、分组自动推断、统一 schema 输出、ID 校验。

#### 3.8.1 `TestCreateMode`（新建模式）

| 用例函数名 | 说明 |
|-----------|------|
| `test_output_normalized_schema` | 新建：`get_model_data` 输出统一 schema（缺省键补全） |
| `test_group_inferred_when_blank` | 分组留空时按模型 ID 自动推断 |
| `test_empty_id_rejected` | 模型 ID 为空：校验失败弹中文警告且不接受（异常路径） |

#### 3.8.2 `TestCapabilityExclusion`（能力标签互斥）

| 用例函数名 | 说明 |
|-----------|------|
| `test_embedding_disables_others` | 勾选 embedding 后除自身外全部能力禁用，取消后恢复 |
| `test_rerank_mutually_exclusive_with_embedding` | embedding 与 rerank 彼此互斥 |
| `test_capability_labels_cover_closed_set` | 能力标签按闭集顺序构建且均有中文标签 |

#### 3.8.3 `TestEditModeRoundTrip`（编辑模式字段往返）

| 用例函数名 | 说明 |
|-----------|------|
| `test_fields_loaded_and_roundtrip` | 编辑模式回填全部字段；不改动直接输出数据守恒 |
| `test_zero_means_unset` | `context_length` / 定价为 0 时输出 None（未设置语义） |

---

### 3.9 `llm_settings/test_model_toggle_regression.py`（4 个用例）

> 回归测试：模型服务窗口模型开关交互的三个关联缺陷修复（停用模型后跳回第一个供应商、模型列表丢失、关闭再打开后悬挂订阅回调）。

#### 3.9.1 `TestModelToggleRegression`（模型开关交互回归测试）

| 用例函数名 | 说明 |
|-----------|------|
| `test_toggle_model_keeps_selection_and_models` | 停用模型后：选中不跳回首个供应商，模型列表不丢失 |
| `test_toggle_model_writes_enabled_override` | 停用模型写入 `enabled=False` 的 `custom_models` 覆写 |
| `test_reopen_dialog_has_no_dangling_subscription` | 关闭再打开后重复操作：无悬挂回调、无 RuntimeError 日志 |
| `test_reload_config_restores_models_from_disk` | `reload_config` 清空内存模型缓存后从磁盘缓存回填（不联网） |

---

### 3.10 `usage_panel/test_trend_chart_render.py`（11 个用例）

> 覆盖 `ui.usage_panel.trend_chart.TrendPanel` 与 UIKit 图表引擎的集成（alpha-v1.0.3 同步新增）：渲染分流（全量 `set_option` / 增量 `set_stream_data`）、异常回退、静态层缓存失效、视觉回归、公开入口边界。

#### 3.10.1 `TestRenderRouting`（渲染分流：全量重建与增量刷新的选择逻辑）

| 用例函数名 | 说明 |
|-----------|------|
| `test_first_render_uses_full_option` | 首次渲染无结构标识可比，必须走全量 `set_option` |
| `test_same_structure_refresh_uses_stream_data` | 指标与区间均未变化时走增量通路，不重建 option 与坐标系 |
| `test_metric_change_forces_full_rebuild` | 指标切换属结构变化（系列名不同），必须全量重建 |
| `test_range_change_forces_full_rebuild` | 区间变化属结构变化（日历 range 变），必须全量重建 |
| `test_stream_failure_falls_back_to_full_option` | 增量写入失败时必须回退全量重建，不能停留在旧数据 |

#### 3.10.2 `TestCacheInvalidation`（层级缓存失效）

| 用例函数名 | 说明 |
|-----------|------|
| `test_full_render_invalidates_cache` | 全量重建后调用 `invalidate_all_caches` |
| `test_incremental_render_keeps_static_cache` | 增量刷新不失效静态层缓存（区间未变，标签本应保持命中） |
| `test_range_switch_refreshes_month_label_band` | 视觉回归（`@pytest.mark.ui`）：同尺寸切换区间后内建月份标签随区间更新 |

#### 3.10.3 `TestBoundaries`（边界与公开入口）

| 用例函数名 | 说明 |
|-----------|------|
| `test_single_day_range_renders` | 自定义单日区间不抛异常且正常全量渲染 |
| `test_cross_year_range_option_payload` | 跨年区间的 option 载荷正确（year 取起始年、range 覆盖两整年） |
| `test_update_series_without_records` | 公开入口在无用量记录时仍能出图（全零序列）并更新状态文本 |

---

### 3.11 `test_skills_panel_i18n.py`（6 个用例）

> 被测对象：`ui/skills_panel/panel.py` 的技能按钮重建逻辑——多语言插件名（`IXPlugin.json` 的 `name` 字典）在界面语言切换后是否跟随。使用 `_StubPlugin` / `_StubManager` / `_StubGroup` 替身隔离插件管理器。

#### 3.11.1 `TestLocalizedPluginNameFollows`（名称变化时重建）

| 用例函数名 | 说明 |
|-----------|------|
| `test_button_rebuilt_with_new_name` | 语言切换后按钮文案使用新语言的插件名 |
| `test_active_highlight_restored` | 重建后原激活态（高亮）保持 |
| `test_group_expansion_preserved` | 重建后分组展开状态保持 |

#### 3.11.2 `TestStaticPluginNameUntouched`（名称未变化时不动）

| 用例函数名 | 说明 |
|-----------|------|
| `test_no_rebuild_when_name_unchanged` | 插件名未变化时不重建按钮 |
| `test_group_expansion_kept_when_name_unchanged` | 名称未变化时分组展开状态不受影响 |
| `test_no_manager_is_noop` | 未设置插件管理器时刷新为空操作 |

---

### 3.12 `test_plugin_management_move.py`（9 个用例）

> 被测对象：`ui/dialog/plugin_management_dialog.py` 详情面板的「移至官方插件 / 移至第三方插件」按钮与本地插件包安装的范围接线。使用隔离的 `PluginManager`（目录指向 `tmp_path`）与最小假插件；模态提示在用例内替换为直接返回（`_confirm_move` 恒同意、`_notice` 记录）。

#### 3.12.1 `TestMoveButtonText`（按钮文案随 Tab 变化）

| 用例函数名 | 说明 |
|-----------|------|
| `test_official_tab_offers_move_to_thirdparty` | 官方 Tab 下按钮文案为「移至第三方插件」 |
| `test_thirdparty_tab_offers_move_to_official` | 第三方 Tab 下按钮文案为「移至官方插件」 |
| `test_button_text_follows_tab_switch` | 切换 Tab 时文案实时更新 |

#### 3.12.2 `TestMovePlugin`（点击按钮执行移动）

| 用例函数名 | 说明 |
|-----------|------|
| `test_move_plugin_to_thirdparty` | 官方 Tab 下点击后插件移动到第三方目录并刷新列表 |
| `test_move_plugin_back_to_official` | 第三方 Tab 下点击后插件移动回官方目录 |
| `test_move_without_selection_moves_nothing` | 未选择插件时只提示、不移动任何目录 |
| `test_move_failure_is_reported` | 核心层拒绝移动时提示失败且目录位置不变 |

#### 3.12.3 `TestLocalInstallScope`（安装本地插件包的范围接线）

| 用例函数名 | 说明 |
|-----------|------|
| `test_install_zip_passes_official_scope` | 官方 Tab 下打开本地安装对话框时传入 official |
| `test_install_zip_passes_thirdparty_scope` | 第三方 Tab 下打开本地安装对话框时传入 thirdparty |

---

## 4. 维护指南

### 4.1 添加新测试

当 `ui/` 添加新组件时：
1. 在 `test/ui_tests/` 下创建新的测试文件
2. 使用 `_make_window()` 或类似辅助函数创建隔离的组件
3. 使用 `qtbot.addWidget()` 添加组件
4. 测试函数写中文 docstring 说明测试目的
5. 同步在本文档 §1 与 §3 补充对应行（§3 表须与 `def test_*` 双向一致）

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查 Qt 组件是否正确创建
3. 检查 mock 是否正确设置
4. 确保 `qtbot.addWidget()` 被调用以避免警告

### 4.3 覆盖率

- 当前覆盖率: **未实测**（本文档不保留历史估算值）
- 测量命令（工作目录为项目根）：
  ```
  .venv\Scripts\python.exe -m pytest test/ui_tests --cov=ui --cov-report=term-missing -p no:cacheprovider
  ```
- 相对薄弱的方向（按用例分布判断，非实测覆盖率结论）:
  - 真实 UI 交互（需要 GUI 环境）中的复杂用户输入场景
  - 多窗口交互
  - `ui/` 中未被 `test/ui_tests/` 任何用例引用的组件

---

## 5. 相关文档

- [主窗口文档](../../docs/ui/main-window.md)
- [技能面板文档](../../docs/ui/skills-panel.md)
- [LLM 设置对话框文档](../../docs/ui/dialogs.md)
- [测试主文档](../TESTING.md)

---
