# 对话框组件

> InstructionX 应用程序中使用的四个对话框组件的完整说明

---

## 1. AboutDialog 关于对话框

**文件位置**: `ui/dialog/about_dialog.py`

### 1.1 概述

`AboutDialog` 是应用程序的关于对话框，显示项目名称、版本和版权信息。

### 1.2 属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog，固定大小 |
| 尺寸 | 400 x 350 |
| Logo 尺寸 | 128 x 128 |
| Logo 缩放模式 | KeepAspectRatio |

### 1.3 内容

- 项目 Logo（居中显示）
- 项目名称: "InstructionX - CE"（加粗，16pt）
- 版本号: "版本 0.1.0"（次要样式）
- 版权声明: "© 2025-2026 dakuang. 保留所有权利。"
- 专有软件声明:
  ```
  Proprietary software.
  Commercial use requires authorization if thresholds are exceeded.
  ```
  （代码中以 `\n` 换行，实际显示为两行）
- 关闭按钮

### 1.4 使用方式

```python
from ui.dialog.about_dialog import AboutDialog

dialog = AboutDialog(parent_window)
dialog.exec()
```

---

## 2. LLMSettingsDialog LLM 设置对话框

**文件位置**: `ui/dialog/llm_settings_dialog.py`
**辅助组件**: `ui/dialog/llm_settings_components.py`

### 2.1 概述

`LLMSettingsDialog` 是 LLM Provider 的配置管理对话框，采用 **两栏布局**：
- **左栏**（250px）：Provider 列表，点击切换选中项
- **右栏**：滚动区域，显示选中 Provider 的完整配置

### 2.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 900 x 600 |
| 默认尺寸 | 1050 x 700 |
| 布局 | 水平两栏（左侧固定 250px，右侧自适应） |

### 2.3 左侧面板

- **标题**: "模型服务"
- **Provider 列表**: `QScrollArea` + `QVBoxLayout`，通过 `ProviderListItem` 组件渲染每个 Provider（图标 + 名称 + ON/OFF 状态标签）
- **添加按钮**: "+ 添加供应商"，虚线边框，点击弹出类型选择对话框
- **删除操作**: 通过右侧详情区的保存逻辑管理（无独立删除按钮）

### 2.4 右侧面板（配置详情，滚动区域）

按从上到下分为以下区域：

#### 头部区（Header）
Provider 徽标（`ProviderLogoLabel`，程序化彩色方块）、名称、子类型标签、**启用** 复选框

#### API 密钥区
- `QLineEdit`（密码模式），带眼睛图标切换可见性
- 链接标签 "点击这里获取密钥"，点击打开对应平台官网

#### API 地址区
- `QLineEdit`，占位符提示示例地址

#### 检测供应商有效性
- "检测供应商有效性" 按钮，调用 `provider.validate_config()`

#### 模型列表区
- **来源切换**: 单选按钮 "使用本地预设列表" / "从 API 获取"
  - minimax / glm 强制使用预设列表（单选禁用）
  - 其他 Provider 可二选一
- **预设视图** (`_preset_view`): `CollapsibleGroup` 按类别分组展示模型（Chat / Embedding / Vision / 其他），每项显示名称、类别徽章（`CategoryBadge`）、能力徽章（`CapabilityBadge`）、上下文长度
- **API 视图** (`_api_view`): "从 API 获取模型列表" 按钮 + 300px 高滚动区域，通过 `ModelDetailItem` 渲染每条模型

#### 模型选择区
- **当前聊天模型**: `QComboBox`（最小宽度 300px）
- **当前 Embedding 模型**: `QComboBox`（最小宽度 300px）
- 两个下拉框自动合并预设模型 + API 获取模型（去重）

#### 底部栏（固定高度 52px）
- 用量统计文字（从 `LLMPluginService.get_usage_stats()` 获取，显示 "累计使用: $X.XXXX"）
- 取消按钮、**保存** 按钮（修改后才可用）

### 2.5 自定义组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `ProviderListItem` | `llm_settings_components.py` | Provider 列表项，含图标、名称、ON/OFF 状态 |
| `ProviderLogoLabel` | `llm_settings_components.py` | 程序化 Provider 徽标（彩色方块 + 首字母） |
| `CapabilityBadge` | `llm_settings_components.py` | 能力徽章（Vision / Thinking / Tools） |
| `CategoryBadge` | `llm_settings_components.py` | 类别徽章（Chat / Embedding） |
| `CollapsibleGroup` | `llm_settings_components.py` | 可折叠分组容器 |
| `ModelDetailItem` | `llm_settings_components.py` | API 获取模型的列表项（含勾选状态） |

### 2.6 使用方式

```python
from ui.dialog.llm_settings_dialog import LLMSettingsDialog
from core.llm.llm_provider import get_llm_provider

dialog = LLMSettingsDialog(parent_window)
if dialog.exec() == QDialog.DialogCode.Accepted:
    # 配置已保存，重新加载 LLM Provider
    get_llm_provider().reload_config()
```

### 2.7 信号

`LLMSettingsDialog` 不对外发射 `config_changed` 信号。主窗口通过 `exec()` 返回值判断配置是否保存，然后手动调用 `get_llm_provider().reload_config()` 重新加载配置。

---

## 3. PluginOrderDialog 插件排序对话框

**文件位置**: `ui/dialog/plugin_order_dialog.py`

### 3.1 概述

`PluginOrderDialog` 是插件顺序配置对话框，允许用户通过拖拽调整官方插件和第三方插件的显示顺序。

### 3.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 700 x 500 |

### 3.3 布局

左右分栏布局：

```
┌──────────────────────────────────────────────────────┐
│  拖动插件项来调整顺序                                    │
├──────────────────────────────────────────────────────┤
│  官方插件                       │  第三方插件            │
│  ┌─────────────────────────┐  │  ┌─────────────────┐  │
│  │ 1 LLM Chat              │  │  │ 1 API Demo     │  │
│  │ 2 文本格式化              │  │  │ 2 单位转换     │  │
│  │ ...                     │  │  │ ...            │  │
│  └─────────────────────────┘  │  └─────────────────┘  │
├──────────────────────────────────────────────────────┤
│              [重置]     [取消]     [保存]                │
└──────────────────────────────────────────────────────┘
```

### 3.4 功能特性

- **拖拽排序**: 使用 `QListWidget` 的 `InternalMove` 拖拽模式
- **编号图标**: 每个插件项左侧显示编号图标（格式: 编号 + 插件图标）
- **独立排序**: 官方插件和第三方插件分别独立排序
- **重置功能**: 将排序恢复到默认顺序

### 3.5 使用方式

```python
from ui.dialog.plugin_order_dialog import PluginOrderDialog

dialog = PluginOrderDialog(plugin_manager, parent_window)
if dialog.exec():
    # 排序已保存，SkillsPanel 需要刷新
    skills_panel.load_skills_from_manager()
```

---

## 4. LLMModelServiceDialog 模型服务设置对话框

**文件位置**: `ui/dialog/llm_model_service_dialog.py`

### 4.1 概述

`LLMModelServiceDialog` 是新版设置对话框，采用 **三栏布局**，提供更丰富的设置分类和 Provider 管理能力。

### 4.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 1100 x 700 |
| 默认尺寸 | 1200 x 800 |

### 4.3 三栏布局

```
┌──────────────────────────────────────────────────────────────────────┐
│  设置                                                    [×]         │
├────────────┬─────────────────┬──────────────────────────────────────┤
│ 设置分类   │  Provider 列表  │  详情区                              │
│ ─────────│ ───────────────│ ─────────────────────────────────────│
│ 🤖 模型服务 │ ▶ MiniMax-1    │  [MiniMax]  启用 ✓                  │
│ ⭐ 默认模型 │   SiliconFlow-1│  ──────────────────────────────────│
│ ⚙️ 常规设置 │   GLM-1        │  API 密钥 [...]                     │
│ 🖥️ 显示设置 │   Ollama-1     │  ──────────────────────────────────│
│ 💾 数据设置 │                 │  模型列表                           │
│ ...        │ + 添加供应商    │  ▼ Chat 模型                       │
│            │                │    ├─ MiniMax-M2.5  [Chat][Tools] │
│            │                │    └─ ...                             │
│            │                │  ▼ Embedding 模型                    │
│            │                │    └─ ...                             │
│            │                │  ──────────────────────────────────│
│            │                │  当前聊天模型 [MiniMax-M2.5     ▼]  │
│            │                │  [保存]                               │
└────────────┴─────────────────┴──────────────────────────────────────┘
```

- **左栏**：14 个设置分类（模型服务、默认模型、常规设置、显示设置、数据设置、MCP 服务器等）
- **中栏**：Provider 列表，含图标、名称、启用状态标签；支持添加新 Provider
- **右栏**：详情区，含 Logo、操作按钮、折叠模型分组（Chat / Embedding / Vision）

### 4.4 信号

```python
default_changed = Signal(str, str)  # (provider_name, chat_model)
```

Provider 默认模型变更时发射 `default_changed(provider_name, chat_model)` 信号。

### 4.5 自定义组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `ProviderListItem` | `llm_settings_components.py` | Provider 列表项，含图标、名称、启用状态 |
| `ModelListItem` | `llm_settings_components.py` | 模型列表项（含勾选状态） |
| `SettingsCategoryItem` | `llm_settings_components.py` | 左侧设置分类项 |
| `CollapsibleGroup` | `llm_settings_components.py` | 可折叠分组容器 |
| `ActionButton` | `llm_settings_components.py` | 统一操作按钮样式 |

### 4.6 使用方式

```python
from ui.dialog.llm_model_service_dialog import LLMModelServiceDialog

dialog = LLMModelServiceDialog(parent_window)
dialog.default_changed.connect(lambda provider, model: print(f"{provider}: {model}"))
dialog.exec()
```

---

## 5. 相关文档

- [主窗口](main-window.md)
- [技能面板](skills-panel.md)
- [插件系统概述](../core/plugin-system/overview.md)

---

*本文档由 Claude Code 自动生成*
