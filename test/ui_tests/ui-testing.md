# UI 测试文档

> UI 组件模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `ui/`
**测试文件数**: 3 个
**测试用例总数**: 15+ 个

### 1.1 测试文件分布

| 测试文件 | 测试用例数 | 主要覆盖 |
|---------|-----------|---------|
| `test_main_window.py` | 6+ | InstructionXMainWindow 菜单、主题切换、布局 |
| `test_skills_panel.py` | 5+ | SkillsPanel 插件加载、技能显示 |
| `test_llm_settings_dialog.py` | 4+ | LLMSettingsDialog 配置保存、Provider 选择 |

### 1.2 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的组件 |
|---------|-----------|------------|
| MainWindow 创建 | 2 | `InstructionXMainWindow` 初始化 |
| 菜单创建 | 1 | `_create_menus()` |
| 主题切换 | 2 | `_cycle_theme()` |
| 布局创建 | 1 | `_create_main_layout()` |
| SkillsPanel 加载 | 3 | 插件加载、技能显示 |
| SkillsPanel 交互 | 2 | 技能点击、刷新 |
| LLM 设置对话框 | 3 | 配置保存、Provider 选择 |
| 窗口关闭 | 1 | closeEvent |

---

## 2. 测试策略

### 2.1 隔离措施

- `InstructionXMainWindow` 使用 mock 绕过 `_create_menus()` 和 `_load_saved_theme()`
- `SkillsPanel` 和 `WorkArea` 被 mock
- `DataProvider` 和 `PluginManager` 被 mock
- 使用 `qtbot` fixture 管理 Qt 组件生命周期
- 使用 `qapp_instance` 提供 QApplication（offscreen 模式）

### 2.2 测试数据

- Mock `get_style_qss()` 返回 `MockStyleQSS`
- 主题状态使用 'auto', 'light', 'dark'
- 菜单项使用中文名称（编辑、用户中心、AI、帮助）

### 2.3 关键 Fixtures

```python
# test/conftest.py
qapp_instance  # Session 级 QApplication（offscreen）
qtbot          # Qt 测试工具

# test_ui_tests/
def _make_window(mocker):  # 创建完全 mock 的 MainWindow
def _make_skills_panel(mocker):  # 创建 mock 的 SkillsPanel
```

---

## 3. 测试用例

### 3.1 MainWindow 创建

#### TC-UI-001: MainWindow 创建成功
- **测试类**: (模块级测试)
- **测试函数**: `test_main_window_creation`
- **优先级**: P0
- **前置条件**: QApplication 已创建
- **测试步骤**:
  1. 使用 `_make_window()` 创建窗口
  2. 使用 `qtbot.addWidget()` 添加窗口
  3. 验证窗口属性
- **预期结果**: 窗口创建成功，属性正确

#### TC-UI-002: MainWindow 初始化所有组件
- **测试类**: (模块级测试)
- **测试函数**: `test_create_main_layout_instantiates_components`
- **优先级**: P0
- **前置条件**: QApplication 已创建
- **测试步骤**:
  1. 创建窗口
  2. 验证 `plugin_manager`, `skills_panel`, `work_area` 存在
- **预期结果**: 所有组件被正确初始化

---

### 3.2 菜单创建

#### TC-UI-003: _create_menus 创建预期菜单
- **测试类**: (模块级测试)
- **测试函数**: `test_create_menus_creates_expected_menus`
- **优先级**: P1
- **前置条件**: QApplication 已创建
- **测试步骤**:
  1. 验证窗口类有 `_create_menus` 方法
  2. 验证相关方法存在
- **预期结果**: 所有菜单创建方法存在

---

### 3.3 主题切换

#### TC-UI-004: _cycle_theme 循环切换主题
- **测试类**: (模块级测试)
- **测试函数**: `test_cycle_theme_cycles_all_states`
- **优先级**: P1
- **前置条件**: 窗口已创建
- **测试步骤**:
  1. 创建窗口
  2. 调用 `_cycle_theme()` 多次
  3. 验证主题状态变化
- **预期结果**: auto → light → dark → auto 循环

#### TC-UI-005: 主题切换应用样式
- **测试类**: (模块级测试)
- **测试函数**: `test_theme_switch_applies_style`
- **优先级**: P1
- **前置条件**: 窗口已创建
- **测试步骤**:
  1. 创建窗口
  2. 切换主题
  3. 验证 `set_style_qss_theme` 被调用
- **预期结果**: 样式被正确应用

---

### 3.4 SkillsPanel 加载

#### TC-UI-006: SkillsPanel 加载插件
- **测试类**: TestSkillsPanel
- **测试函数**: `test_skills_panel_loads_plugins`
- **优先级**: P0
- **前置条件**: SkillsPanel 已创建
- **测试步骤**:
  1. 创建 SkillsPanel
  2. 验证插件列表
- **预期结果**: 插件被正确加载

#### TC-UI-007: SkillsPanel 显示技能
- **测试类**: TestSkillsPanel
- **测试函数**: `test_skills_panel_displays_skills`
- **优先级**: P1
- **前置条件**: SkillsPanel 已创建，插件已加载
- **测试步骤**:
  1. 创建 SkillsPanel
  2. 验证技能项显示
- **预期结果**: 技能项正确显示

#### TC-UI-008: SkillsPanel 插件点击
- **测试类**: TestSkillsPanel
- **测试函数**: `test_skills_panel_plugin_click`
- **优先级**: P1
- **前置条件**: SkillsPanel 已创建
- **测试步骤**:
  1. 创建 SkillsPanel
  2. 点击插件项
  3. 验证响应
- **预期结果**: 点击事件被正确处理

---

### 3.5 SkillsPanel 交互

#### TC-UI-009: SkillsPanel 刷新
- **测试类**: TestSkillsPanelRefresh
- **测试函数**: `test_skills_panel_refresh`
- **优先级**: P1
- **前置条件**: SkillsPanel 已创建
- **测试步骤**:
  1. 调用 refresh 方法
  2. 验证插件重新加载
- **预期结果**: 插件列表刷新

#### TC-UI-010: SkillsPanel 状态保存
- **测试类**: TestSkillsPanelState
- **测试函数**: `test_skills_panel_state_persistence`
- **优先级**: P2
- **前置条件**: SkillsPanel 已创建
- **测试步骤**:
  1. 修改面板状态
  2. 重新创建面板
  3. 验证状态
- **预期结果**: 状态未持久化（每次新建）

---

### 3.6 LLM 设置对话框

#### TC-UI-011: LLMSettingsDialog 创建
- **测试类**: TestLLMSettingsDialog
- **测试函数**: `test_llm_settings_dialog_creation`
- **优先级**: P0
- **前置条件**: QApplication 已创建
- **测试步骤**:
  1. 创建 LLMSettingsDialog
  2. 验证对话框创建
- **预期结果**: 对话框创建成功

#### TC-UI-012: LLM 配置保存
- **测试类**: TestLLMSettingsDialog
- **测试函数**: `test_llm_config_save`
- **优先级**: P0
- **前置条件**: LLMSettingsDialog 已创建
- **测试步骤**:
  1. 修改配置
  2. 点击保存
  3. 验证配置保存
- **预期结果**: 配置被正确保存

#### TC-UI-013: Provider 选择
- **测试类**: TestLLMSettingsDialog
- **测试函数**: `test_provider_selection`
- **优先级**: P1
- **前置条件**: LLMSettingsDialog 已创建
- **测试步骤**:
  1. 选择不同的 Provider
  2. 验证配置更新
- **预期结果**: Provider 正确切换

#### TC-UI-014: Provider 配置字段显示
- **测试类**: TestLLMSettingsDialog
- **测试函数**: `test_provider_config_fields`
- **优先级**: P1
- **前置条件**: LLMSettingsDialog 已创建
- **测试步骤**:
  1. 选择不同 Provider
  2. 验证相关配置字段显示
- **预期结果**: 根据 Provider 显示不同字段

---

### 3.7 窗口关闭

#### TC-UI-015: MainWindow 关闭
- **测试类**: TestMainWindowClose
- **测试函数**: `test_main_window_close`
- **优先级**: P1
- **前置条件**: 窗口已显示
- **测试步骤**:
  1. 显示窗口
  2. 触发关闭事件
  3. 验证窗口关闭
- **预期结果**: 窗口正确关闭

---

## 4. 维护指南

### 4.1 添加新测试

当 `ui/` 添加新组件时：
1. 在 `test/ui_tests/` 下创建新的测试文件
2. 使用 `_make_window()` 或类似辅助函数创建隔离的组件
3. 使用 `qtbot.addWidget()` 添加组件
4. 使用 TC-UI-XXX 格式的 docstring

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查 Qt 组件是否正确创建
3. 检查 mock 是否正确设置
4. 确保 `qtbot.addWidget()` 被调用以避免警告

### 4.3 覆盖率目标

- 当前覆盖率: ~60%
- 目标覆盖率: 70%
- 未覆盖的关键路径:
  - 真实 UI 交互（需要 GUI 环境）
  - 复杂的用户输入场景
  - 多窗口交互

---

## 5. 相关文档

- [主窗口文档](../../docs/ui/main-window.md)
- [技能面板文档](../../docs/ui/skills-panel.md)
- [LLM 设置对话框文档](../../docs/ui/dialogs.md)
- [测试主文档](../TESTING.md)

---
