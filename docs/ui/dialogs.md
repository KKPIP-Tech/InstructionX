# 对话框组件

> InstructionX 应用程序中使用的三个对话框组件的完整说明

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

### 2.1 概述

`LLMSettingsDialog` 是 LLM Provider 的配置管理对话框，采用左右分栏布局，左侧为 Provider 列表，右侧为配置表单。

### 2.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 尺寸 | 800 x 550 |
| 布局 | 水平左右分栏 |

### 2.3 左侧面板

- **Provider 列表**: `QListWidget`，显示已配置的 Provider 名称
- **添加按钮**: 添加新的 Provider
- **删除按钮**: 删除选中的 Provider

### 2.4 右侧面板（配置表单）

| 字段 | 控件类型 | 说明 |
|------|---------|------|
| Provider 名称 | QLineEdit（只读） | Provider 标识名 |
| Provider 类型 | QLineEdit（只读） | provider_type |
| API Key | QLineEdit（密码模式） | 输入后需刷新模型 |
| Base URL | QLineEdit | API 端点地址 |
| Chat 模型 | QComboBox（可编辑） | 聊天模型选择 |
| Embedding 模型 | QComboBox（可编辑） | 嵌入模型选择 |
| 启用 Chat | QCheckBox | 是否启用聊天功能 |
| 启用 Embedding | QCheckBox | 是否启用嵌入功能 |
| 多模态 | QLabel（只读） | 显示是否支持视觉（绿色文字"支持" / 灰色文字"不支持"） |
| Function Calling | QLabel（只读） | 显示是否支持函数调用（绿色文字"支持" / 灰色文字"不支持"） |
| Context Length | QLabel（只读） | 最大上下文长度 |

### 2.5 底部按钮

- **刷新模型**: 强制从 API 重新获取模型列表；填写 API Key 后按钮变为"待刷新"，需点击此按钮刷新模型
- **测试连接**: 测试 Provider 连接是否正常
- **保存**: 保存当前配置
- **取消**: 关闭对话框，不保存

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

```python
config_changed = Signal()  # 配置保存后发射，可供自定义使用
```

> **备注**: `config_changed` 信号在保存成功后发射。如需在主窗口中使用此信号，可连接自定义槽函数；主窗口默认通过 `exec()` 返回值判断并手动调用 `get_llm_provider().reload_config()`。

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

## 4. 相关文档

- [主窗口](main-window.md)
- [技能面板](skills-panel.md)
- [插件系统概述](../core/plugin-system/overview.md)

---

*本文档由 Claude Code 自动生成*
