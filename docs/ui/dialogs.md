# 对话框组件

> InstructionX 应用程序中使用的六个对话框组件的完整说明

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
- 版本号: "版本 Alpha 1.0.2"（次要样式）
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
- 用量统计文字（从 `LLMPluginService.get_usage_stats()` 获取，显示 `"累计使用：$X.XXXX"`（美元））
- 取消按钮、**保存** 按钮（修改后才可用）

### 2.5 自定义组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `ProviderListItemWidget` | `llm_settings_components.py` | Provider 列表项，含圆形 Logo、名称、已启用/未启用状态标签 |
| `CollapsibleGroup` | `llm_settings_components.py` | 可折叠分组容器 |
| `ActionButton` | `llm_settings_components.py` | 统一操作按钮样式（蓝色圆角） |
| `ModelDetailItem` | `llm_settings_components.py` | 预设模型 / API 获取模型的详情列表项（含上下文长度、能力标签） |

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

- **拖拽排序**: 使用自定义 `OrderListWidget`（继承自 `QListWidget`）的 `InternalMove` 拖拽模式
- **编号图标**: 每个插件项左侧显示编号图标（格式: 编号 + 插件图标）
- **独立排序**: 官方插件和第三方插件分别独立排序
- **重置功能**: 将排序恢复到默认顺序

### 3.5 使用方式

```python
from ui.dialog.plugin_order_dialog import PluginOrderDialog

dialog = PluginOrderDialog(plugin_manager, parent_window)
if dialog.exec() == QDialog.DialogCode.Accepted:
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
┌──────────────────────────────────────────────────────────────────────────┐
│  设置                                                        [×]        │
├────────────────┬─────────────────────┬──────────────────────────────────┤
│ 设置分类       │  Provider 列表       │  详情区                          │
│ (170px)       │  (260px)            │                                  │
│ ─────────────│ ──────────────────│ ─────────────────────────────────│
│ 🤖 模型服务     │ ▶ MiniMax-1        │  [MiniMax]  启用 ✓               │
│ ⭐ 默认模型     │   SiliconFlow-1     │  ──────────────────────────────│
│ ⚙️ 常规设置     │   GLM-1            │  API 密钥 [...]                 │
│ 🖥️ 显示设置     │   Ollama-1         │  ──────────────────────────────│
│ 💾 数据设置     │                     │  模型                            │
│ ...           │ + 添加               │  ▼ deepseek-ai                  │
│               │                     │    └─ MiniMax-M2.5              │
│               │                     │  ▼ pro                          │
│               │                     │    └─ ...                       │
│               │                     │  ──────────────────────────────│
│               │                     │  [保存]                          │
└───────────────┴─────────────────────┴──────────────────────────────────┘
```

- **左栏**（170px）：15 个设置分类（模型服务、默认模型、常规设置、显示设置、数据设置、MCP 服务器等）
- **中栏**（260px）：Provider 列表，含图标、名称、启用状态标签；支持添加新 Provider（按钮文字：`+ 添加`）
- **右栏**：详情区，含 Logo、操作按钮、折叠模型分组（按 deepseek-ai / pro / 其他分组，源自 `_group_models` 方法按 model_id 关键字匹配）
- **底部栏**：用量统计（格式：`用量: Token X | 费用 ¥X.XXXX | 请求 X 次`，人民币）、重置用量按钮、取消按钮、**保存** 按钮

> **注意**：目前仅实现了"模型服务"分类的完整功能，其他分类选中后显示"功能开发中..."占位提示。

### 4.4 信号

```python
default_changed = Signal(str, str)  # (provider_name, chat_model)
```

Provider 默认模型变更时发射 `default_changed(provider_name, chat_model)` 信号。

### 4.5 自定义组件

| 组件 | 文件 | 说明 |
|------|------|------|
| `ProviderListItemWidget` | `llm_settings_components.py` | Provider 列表项，含圆形 Logo、名称、已启用/未启用状态标签 |
| `ModelListItem` | `llm_settings_components.py` | 模型列表项（含固定、设置、删除操作按钮） |
| `SettingsCategoryItem` | `llm_settings_components.py` | 左侧设置分类项（含图标、文字、选中状态） |
| `CollapsibleGroup` | `llm_settings_components.py` | 可折叠分组容器 |
| `ActionButton` | `llm_settings_components.py` | 统一操作按钮样式 |
| `IconLineEdit` | `llm_settings_components.py` | 带图标按钮的输入框（用于 API 密钥输入） |

### 4.6 使用方式

```python
from ui.dialog.llm_model_service_dialog import LLMModelServiceDialog

dialog = LLMModelServiceDialog(parent_window)
dialog.default_changed.connect(lambda provider, model: print(f"{provider}: {model}"))
dialog.exec()
```

---

## 5. GitHubPluginInstallDialog GitHub 插件安装对话框

**文件位置**: `ui/dialog/github_plugin_install_dialog.py`

### 5.1 概述

`GitHubPluginInstallDialog` 是从 GitHub 仓库安装插件的对话框，支持单插件和多插件仓库的用户选择性安装。

### 5.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 600 x 450 |
| 布局 | 垂直布局 + 堆叠窗口 |

### 5.3 布局结构

```
┌─────────────────────────────────────────────┐
│  从 GitHub 安装插件                           │
├─────────────────────────────────────────────┤
│  GitHub URL: [________________________] [检查] │
│                                             │
│  ── 插件信息 ──────────────────────────────  │
│  将安装到: 第三方插件目录 (custom_plugin/)    │
│                                             │
│  单插件模式:                                 │
│  ┌─────────────────────────────────────┐   │
│  │ 名称: My Awesome Plugin               │   │
│  │ 版本: release.1.0.0                   │   │
│  │ 描述: 一个强大的插件...                │   │
│  └─────────────────────────────────────┘   │
│                                             │
│  多插件模式:                                 │
│  ☑ plugin-a  (Plugin A)                    │
│  ☑ plugin-b  (Plugin B)                    │
│  ☐ plugin-c  (Plugin C)  ← 未选中          │
│                                             │
│              [取消]  [安装]                  │
└─────────────────────────────────────────────┘
```

### 5.4 功能特性

- **仓库检查**: 输入 URL 后点击「检查」分析仓库类型
- **单/多插件识别**: 自动识别单插件仓库（IXPlugin.json）或多插件仓库（IXRepo.json）
- **选择性安装**: 多插件时显示复选框列表
- **自动目录判定**: 根据 GitHub 组织自动判定安装目录（KKPIP-Tech → plugin/，其他 → custom_plugin/）
- **后台下载**: 使用 QThread 后台下载，不阻塞 UI

### 5.5 信号

```python
plugin_installed = Signal(list)  # List[InstallResult]
```

安装完成后发射，携带每个插件的安装结果。

### 5.6 使用方式

```python
from ui.dialog.github_plugin_install_dialog import GitHubPluginInstallDialog

dialog = GitHubPluginInstallDialog(parent_window)
dialog.plugin_installed.connect(self._on_plugin_installed)
dialog.exec()

def _on_plugin_installed(self, results):
    # 重新加载技能面板
    self.skills_panel.load_skills_from_manager()
```

---

## 6. LicenseDialog 许可信息对话框

**文件位置**: `ui/dialog/license_dialog.py`

### 6.1 概述

`LicenseDialog` 是开源许可证信息展示对话框，以分类卡片列表的形式展示项目中使用的所有字体和第三方依赖的许可证详情。

### 6.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 900 x 600 |
| 默认尺寸 | 950 x 650 |

### 6.3 布局结构

```
┌────────────────────────────────────────────────────────────────────────────┐
│  许可信息  Licenses                                                          │
├──────────────────────┬─────────────────────────────────────────────────────┤
│  [搜索名称...]        │                                                      │
│  ─────────────────   │  MiniMax-Plus2 (MiniMax-M2.5)                       │
│  字体项              │  ────────────────────────────                         │
│  依赖项              │  [MIT]  v1.0.0 | 依赖                               │
│  ...                 │  © xxxx                                             │
│                      │  https://example.com                                │
│                      │                                                      │
│                      │  ┌──────────────────────────────────────────────┐   │
│                      │  │  license 文件内容（等宽字体，可复制）          │   │
│                      │  └──────────────────────────────────────────────┘   │
│                      ├─────────────────────────────────────────────────────┤
│                      │                    [复制全文] [打开文件夹] [关闭]    │
└──────────────────────┴─────────────────────────────────────────────────────┘
```

- **左栏**（320px）：搜索框 + 滚动列表，每个列表项显示名称、许可证徽章、版本；支持按名称过滤
- **右栏**：详情区，含标题、许可证标签、版本、分类、版权信息、链接，下方为许可文件内容（代码块样式，支持复制）
- **底部栏**：操作按钮（复制全文、打开 licenses 文件夹、关闭）

### 6.4 数据来源

许可证数据从 `licenses/manifest.json` 读取，分为 `fonts`（字体）和 `dependencies`（依赖）两类。每项包含 `name`、`display_name`、`license_type`、`version`、`url`、`copyright` 等字段。

### 6.5 功能特性

- **搜索过滤**：输入名称实时过滤列表项（基于字符串包含匹配）
- **空状态提示**：无匹配结果时显示"未找到匹配的许可证"
- **许可证颜色标签**：根据许可证类型显示不同颜色的徽章（MIT/GPL/Apache 等）
- **复制全文**：将当前显示的许可证全文复制到剪贴板，按钮文字临时变为"已复制！"
- **打开文件夹**：直接打开 `licenses/` 目录

### 6.6 使用方式

```python
from ui.dialog.license_dialog import LicenseDialog

dialog = LicenseDialog(parent_window)
dialog.exec()
```

---

## 7. 相关文档

- [主窗口](main-window.md)
- [技能面板](skills-panel.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)

---

*本文档由 Claude Code 自动生成*
