# 对话框组件

> InstructionX 应用程序中使用的十个对话框组件的完整说明

---

## 1. AboutDialog 关于对话框

**文件位置**: `ui/dialog/about_dialog.py`

### 1.1 概述

`AboutDialog` 是应用程序的关于对话框，显示项目名称、版本和版权信息。

### 1.2 属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 尺寸 | 最小尺寸 400 x 350，默认尺寸相同（用最小尺寸而非固定尺寸，保证高 DPI/大字体下内容不被裁切） |
| Logo 尺寸 | 128 x 128 |
| Logo 缩放模式 | KeepAspectRatio |

### 1.3 内容

- 项目 Logo（居中显示）
- 项目名称: "InstructionX - CE"（加粗，字号取 UIKit 令牌 `font.title.lg` = 20px）
- 版本号: "版本 Alpha 1.1.0"（次要样式）
- 版权声明: "© 2025-2026 dakuang 版权所有，保留所有权利。"
- 专有软件声明（中文摘要 + 英文法律声明，代码中以 `\n` 换行，实际显示为三行）:
  ```
  本软件为专有软件，商业使用超过阈值需获得授权。
  Proprietary software.
  Commercial use requires authorization if thresholds are exceeded.
  ```

### 1.4 使用方式

```python
from ui.dialog.about_dialog import AboutDialog

dialog = AboutDialog(parent_window)
dialog.exec()
```

---

## 2. LLMSettingsDialog LLM 设置对话框

**文件位置**: `ui/dialog/llm_settings/`（包，旧 `llm_settings_dialog.py` / `llm_settings_components.py` 已删除）

### 2.1 概述

`LLMSettingsDialog` 是 LLM Provider 实例的配置管理对话框，采用 **QSplitter 两栏布局**：
- **左栏**（固定 248px）：`ProviderListPanel`，实例列表 + 搜索 + 添加入口
- **右栏**：`QStackedWidget`（空态占位页 / `ProviderDetailPanel` 详情页）

**核心交互语义**：
- **自动保存**：全部编辑（API 密钥、地址、启停开关、模型开关、默认模型等）即时经 `get_llm_config()` 落盘，无「取消/保存」按钮；删除类操作保留中文确认弹窗。
- **预设/实例体系**：每个 Provider 是一个实例，经 `preset_id` 关联目录预设（`core/llm/catalog/`）；「＋ 添加提供商」弹出两页创建对话框（选预设或「自定义 OpenAI 兼容服务」→ 填名称/地址/密钥）。
- **配置变更联动**：`LLMConfig` 变更订阅驱动左栏刷新；`LLMProvider` 惰性刷新保证运行时实例同步。
- **主题跟随**：包内自主主题 token 体系（`theme.py` 的 `Theme` dataclass），token 值不再硬编码，而由 `_theme_from_uikit()` 从 UIKit 设计令牌（`T()`）按全局当前模式（`ui.uikit_theme.current_theme_mode()`）实时构建；`apply_dialog_theme()` 为对话框换肤并连接 UIKit `theme_changed` 信号，实现对话框打开期间实时跟随，作用域仅限对话框自身，不触碰 QApplication 全局样式。
- **统一反馈**：包内 `feedback.py` 提供 `confirm` / `notice` / `info` / `warn` / `success`（基于 UIKit Dialog / Message），替代原 QMessageBox 确认框与轻提示。
- **记住选中**：上次选中的实例经 QSettings（组织 `KKPIP-Tech` / 应用 `InstructionX-CE`）记忆，下次打开时恢复。

### 2.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 900 x 600 |
| 默认尺寸 | 1050 x 700 |
| 布局 | QSplitter 水平两栏（左栏固定 248px，右栏自适应） |
| 打开方式 | 菜单 **AI > LLM 设置...**（Ctrl+L） |

### 2.3 左侧面板（ProviderListPanel）

- **标题**: "模型服务" 小标题
- **搜索框**: 实时过滤，匹配实例名 / 实例 id / 预设显示名 / 实例下模型 id 与 name（缓存模型 + custom_models）
- **实例列表**: 按配置 `order` 升序渲染，每项为 `ProviderItemWidget`（品牌图标 + 名称 + 自绘启停开关，选中为圆角 pill）；开关切换直接写 `enabled_chat` 落盘
- **添加按钮**: 「＋ 添加提供商」，弹出 `ProviderEditorDialog`（MODE_CREATE 两页流程）
- 重命名 / 删除操作在右栏头部「更多菜单」中（删除保留中文确认弹窗）

### 2.4 右侧面板（ProviderDetailPanel）

按从上到下分为以下区域：

#### 头部区（Header）
品牌图标、实例名称、类型徽章（适配器家族；自定义实例显示「自定义」）、**总开关**（`SwitchButton`，关闭时主体覆盖停用遮罩）、更多菜单（重命名 / 删除提供商）

#### API 配置区
- **API 密钥**：`QLineEdit`（密码模式 + 眼睛图标切换可见性），即时落盘
- **连接检测**：「检测」按钮，经 `ConnectionCheckWorker`（QThread）调用 `LLMProvider.check_provider()`；成功显示「连接正常 · N 个模型」且未启用时自动开启 `enabled_chat`，失败显示错误详情
- **API 地址**：`QLineEdit`（占位符显示目录默认地址）+「重置」按钮（清空实例覆写、回退目录默认）；输入完成即时落盘
- **获取密钥**：`_key_link_btn` 链接，指向 `preset.api_key_url`（目录预设元数据驱动）。注意：`docs_url` 虽在预设中定义，但框架 UI 当前**无消费点**；预设亦无 homepage 字段，UI 不存在「官网」链接

#### 模型区（ModelSection）
- **标题栏**: 计数 / 「↻ 刷新」（`FetchModelsWorker` 后台拉取，内部走 `check_provider()`）/ 「＋ 添加」/ 「检查」（健康检查对话框）/ 「同步」（模型同步对话框）/ 「管理」
- **管理模式**: 工具条（全选 / 删除选中），支持批量操作
- **分组展示**: 模型列表为 `merge_model_entries()`（目录预设 + API 拉取/缓存 + 用户覆写 custom_models）三路合并结果，按主类型（对话/视觉/嵌入/重排序）分组渲染 `ModelRow`（名称、能力徽章、上下文长度、启停开关、删除按钮）
- 模型开关写 `enabled` 覆写、非自定义模型删除写 `hidden` 覆写（均落进 custom_models）；双击模型行打开 `ModelEditDialog` 编辑

#### 默认模型区
- **聊天模型** / **嵌入模型** 两个 `QComboBox`（含「未设置」项），按能力过滤候选模型，选择即时落盘

### 2.5 子对话框

| 对话框 | 文件 | 说明 |
|------|------|------|
| `ProviderEditorDialog` | `provider_editor_dialog.py` | 实例添加/编辑：MODE_CREATE 两页流程（选预设列表或「自定义 OpenAI 兼容服务」→ 填名称/Base URL/API Key，按预设预填）；MODE_EDIT 编辑既有实例；实例 id 由 `generate_instance_id()` 生成（预设首实例直接用 preset_id，否则短码 id） |
| `ModelEditDialog` | `model_edit_dialog.py` | 模型条目编辑：能力标签开关组（遵循 embedding/rerank 互斥规则）、context_length、定价与币种；输出经 `normalize_model_entry()` 规范化的统一 schema |
| `HealthCheckDialog` | `health_check_dialog.py` | 逐模型可用性探测（`HealthCheckWorker` 后台调 `LLMProvider.check_model()`）：每行状态（等待/检查中/正常/失败/跳过）+ 延迟 ms + 进度条 + 顶部汇总计数 |
| `SyncModelsDialog` | `sync_models_dialog.py` | 远端模型对比：新增（绿标，可批量添加）/ 已存在（灰标）/ 已失效（红标，可批量清理）三区分组；无远端模型 API 的预设（如 MiniMax）提示「无需同步」 |

### 2.6 包结构与通用组件

| 文件 | 说明 |
|------|------|
| `dialog.py` | 主壳（两栏协调、选中记忆、模型编辑接入、Worker 回收） |
| `constants.py` | 全部尺寸/超时/QSettings 键等命名常量 |
| `theme.py` | 主题 token（LIGHT/DARK `Theme` dataclass）+ QSS 生成 + `apply_dialog_theme()` |
| `icons.py` | 品牌 SVG 图标渲染/着色（`icons/` 资源目录，缺失时降级为字母方块） |
| `widgets.py` | 通用控件（`SwitchButton` 自绘开关、徽章、`ProviderItemWidget`、`ModelRow`、`_BaseFormDialog` 表单基类、焦点光环） |
| `workers.py` | 后台 Worker 线程（`FetchModelsWorker` / `ConnectionCheckWorker` / `HealthCheckWorker`，规范 parent 归属与自销毁） |

### 2.7 使用方式

```python
from ui.dialog.llm_settings import LLMSettingsDialog
from core.llm.llm_provider import get_llm_provider

dialog = LLMSettingsDialog(parent_window)
if dialog.exec() == QDialog.DialogCode.Accepted:
    # 自动保存语义下编辑已即时落盘；reload_config() 为幂等保底调用
    get_llm_provider().reload_config()
# exec() 返回后对话框仅被隐藏，需显式销毁，防止隐藏对话框与信号连接累积
dialog.deleteLater()
```

### 2.8 信号与配置同步

`LLMSettingsDialog` 不对外发射 `config_changed` 信号。编辑经 `get_llm_config()` 即时落盘并触发 `LLMConfig` 变更通知（`version + 1`）；`LLMProvider` 各公开入口比对版本惰性刷新，主窗口 `exec()` 返回后的 `reload_config()` 仅为幂等保底。

---

## 3. PluginManagementDialog 插件管理对话框

**文件位置**: `ui/dialog/plugin_management_dialog.py`

### 3.1 概述

`PluginManagementDialog` 是插件的统一管理对话框，集成插件的安装、升级/降级、卸载与自定义分组/排序管理，通过 **编辑 > 插件管理...**（Ctrl+P）打开。

### 3.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 860 x 560 |
| 布局 | QTabWidget 两页（「插件管理」/「分组与排序」）+ 底部「关闭」按钮 |

### 3.3 功能特性

- **插件管理页**: 官方/第三方两个插件列表 + 右侧详情面板（名称/版本/来源/语言状态行）；工具栏提供「从 GitHub 安装插件…」（内嵌 `GitHubPluginInstallDialog`）、「安装本地插件包…」（本地 zip）、「刷新」；详情面板提供「语言…」（打开 `PluginLanguageDialog` 设置每插件语言覆盖，插件无语言包时置灰并显示 tooltip，见 §10）、「检查更新 / 升级 / 降级…」（列出 GitHub Release 版本供选择，降级二次确认并警告数据不兼容风险）与「卸载…」（确认弹窗，可选「同时删除插件数据」）
- **分组与排序页**: 官方/第三方各一个 `GroupEditorWidget`——左侧「面板顺序」为分组与未分组插件的统一混排列表（新建/重命名/设置图标/删除分组、上移/下移），右侧穿梭框编辑选中分组的组内成员与组内顺序；「保存分组与排序」统一提交两个 scope，「重置」放弃工作副本重新加载
- **后台执行**: 下载/安装等耗时操作经 `_Worker`（QThread）后台执行，期间禁用对话框防止并发操作
- **确认与提示**: 统一使用 UIKit Dialog / Message（模块级 `_confirm` / `_notice` / `_prompt_text` / `_prompt_item` 辅助函数），替代 QMessageBox / QInputDialog

### 3.4 信号

```python
plugins_changed = Signal()
```

插件集合或分组/排序发生变化（安装/升级/降级/卸载完成、分组与排序保存）时发射；主窗口连接该信号统一刷新技能面板并清空工作区。

### 3.5 使用方式

```python
from ui.dialog.plugin_management_dialog import PluginManagementDialog

dialog = PluginManagementDialog(plugin_manager, parent_window)
dialog.plugins_changed.connect(self._on_plugins_changed)
dialog.exec()
```

---

## 4. PluginOrderDialog 插件排序对话框（遗留）

**文件位置**: `ui/dialog/plugin_order_dialog.py`

### 4.1 概述

`PluginOrderDialog` 是插件顺序配置对话框，允许用户通过拖拽调整官方插件和第三方插件的显示顺序。

> **注意**：本对话框为遗留代码，无菜单入口、无实际调用方（仅 `ui/dialog/__init__.py` 仍残留 re-export）；其排序功能已被 `PluginManagementDialog` 的「分组与排序」页取代，本节内容仅供参考。

### 4.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 700 x 500 |

### 4.3 布局

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

### 4.4 功能特性

- **拖拽排序**: 使用自定义 `OrderListWidget`（继承自 `QListWidget`）的 `InternalMove` 拖拽模式
- **编号图标**: 每个插件项左侧显示编号图标（格式: 编号 + 插件图标）
- **独立排序**: 官方插件和第三方插件分别独立排序
- **重置功能**: 将排序恢复到默认顺序

### 4.5 使用方式

```python
from ui.dialog.plugin_order_dialog import PluginOrderDialog

dialog = PluginOrderDialog(plugin_manager, parent_window)
if dialog.exec() == QDialog.DialogCode.Accepted:
    # 排序已保存，SkillsPanel 需要刷新
    skills_panel.load_skills_from_manager()
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

## 6. LicenseDialog 开源组件许可对话框

**文件位置**: `ui/dialog/license_dialog.py`

### 6.1 概述

`LicenseDialog` 是开源组件许可展示对话框，以卡片列表的形式展示项目使用的第三方开源组件（依赖）的许可证详情。窗口标题与页头均为「开源组件许可」。

### 6.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog |
| 最小尺寸 | 900 x 600 |
| 默认尺寸 | 950 x 650 |

### 6.3 布局结构

```
┌────────────────────────────────────────────────────────────────────────────┐
│  开源组件许可                                                                │
├──────────────────────┬─────────────────────────────────────────────────────┤
│  [搜索名称...]        │                                                      │
│  ─────────────────   │  MiniMax-Plus2 (MiniMax-M2.5)                       │
│  依赖项              │  ────────────────────────────                         │
│  ...                 │  [MIT]  v1.0.0 | 依赖                               │
│                      │  © xxxx                                             │
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

许可证数据从 `licenses/manifest.json` 的 `dependencies`（依赖）数组读取（框架不自带第三方字体，原 `fonts` 分类已移除）。每项包含 `name`、`display_name`、`license_type`、`version`、`url`、`copyright` 等字段。

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

## 7. FontManagerDialog 字体管理对话框

**文件位置**: `ui/dialog/font_manager_dialog.py`

### 7.1 概述

`FontManagerDialog` 是框架字体的管理入口：左栏展示已安装字体（框架管理，来自 `FontManager` 注册记录）与系统字体两个分组，右栏提供实时预览（示例文本可编辑、字号可调），底部提供安装/卸载操作。底层能力由 `core/font` 的 `FontManager` 单例提供（详见 [字体子系统概述](../core/font-manager/overview.md)）。

### 7.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog，模态 |
| 最小尺寸 | 860 x 560 |
| 默认尺寸 | 920 x 620 |
| 窗口标题 | 字体管理 |

### 7.3 布局结构

```
┌────────────────────────────────────────────────────────────────────────────┐
│  字体管理                                                                    │
├──────────────────────┬─────────────────────────────────────────────────────┤
│  [搜索字体...]        │  [示例文本输入框]                                     │
│  ─────────────────   │  字号 [ 24 ] (8-72)                                 │
│  已安装字体（分组标题）│  ┌──────────────────────────────────────────────┐   │
│   · SmileySans       │  │                                              │   │
│  系统字体（分组标题）  │  │        预览卡片（示例文本实时渲染）            │   │
│   · Microsoft YaHei  │  │                                              │   │
│   · ...（只读）       │  └──────────────────────────────────────────────┘   │
│                      │  当前字体：X / 字体 X 不可用，已回退到系统字体：Y      │
├──────────────────────┴─────────────────────────────────────────────────────┤
│  [安装字体...] [卸载]                                              [关闭]    │
└────────────────────────────────────────────────────────────────────────────┘
```

- **左栏**（280px）：搜索框 + 字体列表，分「已安装字体」「系统字体」两个分组（分组标题行不可选）；系统字体分组来自 `QFontDatabase.families()`，只读
- **右栏**：示例文本编辑（默认「InstructionX 字体预览 Font Preview 0123 ABCabc」）+ 字号 QSpinBox（8-72，默认 24）+ 预览卡片 + 解析结果提示
- **底部栏**：安装字体... / 卸载 / 关闭（主按钮）

### 7.4 功能特性

- **搜索过滤**：按家族名实时过滤列表项（分组标题恒显示）
- **实时预览**：预览经 `FontManager.get_font()` 构造，选中字体不可用时自动回退并提示「字体 X 不可用，已回退到系统字体：Y」
- **安装字体**：`QFileDialog` 多选（过滤器 `字体文件 (*.ttf *.otf *.ttc)`），逐个安装；失败经 `Message.warning` 弹窗并记日志，不阻断其余文件
- **卸载**：仅选中「已安装字体」分组项时可用，经 `feedback.confirm` 确认后执行；卸载后使用该字体的界面自动回退系统字体

### 7.5 使用方式

```python
from ui.dialog import FontManagerDialog

dialog = FontManagerDialog(parent_window)
dialog.exec()
```

菜单入口：主窗口「编辑 → 字体管理...」（`InstructionXMainWindow._open_font_manager_dialog()`）。

---

## 8. CloseConfirmDialog 关闭确认对话框

**文件位置**: `ui/dialog/close_confirm_dialog.py`

### 8.1 概述

`CloseConfirmDialog` 是主窗口关闭行为的确认对话框：所有关闭路径（自绘叉子 / 标题栏右键「关闭(C)」/ Alt+F4 / 任务栏右键「关闭窗口」）统一经主窗口 `closeEvent` 拦截后弹出，**每次必问**，不提供「记住我的选择」。

说明文案：「您希望退出程序，还是最小化到系统托盘继续运行？托盘运行期间插件与后台任务将继续工作。」

### 8.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog，WindowModal（父窗口为主窗口） |
| 最小宽度 | 420 |
| 按钮 | 退出程序（primary，默认按钮）/ 最小化到托盘 / 取消 |
| 样式 | 按钮 `variant` 由 UIKit 全局 QSS 驱动（`set_property(btn, "variant", ...)`），随全局主题自动切换 |

### 8.3 行为语义

- **退出程序**：真正退出（`closeEvent` accept + 经 `_request_application_quit()` 显式退出）
- **最小化到托盘**：隐藏主窗口、托盘图标驻留、弹通知提示（每次都弹，详见 [系统托盘与关闭行为](system-tray.md)）
- **取消**：Esc、对话框叉号、「取消」按钮统一走 `reject()`，等价于取消关闭，窗口保持原状

### 8.4 使用方式

```python
from ui.dialog.close_confirm_dialog import CloseChoice, CloseConfirmDialog

# 一站式：模态弹出并返回三值枚举
choice = CloseConfirmDialog.ask(parent_window)

# 或分步使用
dialog = CloseConfirmDialog(parent_window)
dialog.exec()
choice = dialog.selected_choice()
```

`CloseChoice` 三值枚举：`EXIT`（退出程序）/ `MINIMIZE_TO_TRAY`（最小化到托盘）/ `CANCEL`（取消）；对话框被 reject（Esc / 叉号 / 取消按钮）时 `selected_choice()` 恒为 `CANCEL`。

---

## 9. LanguageDialog 界面语言对话框

**文件位置**: `ui/dialog/language_dialog.py`

### 9.1 概述

`LanguageDialog` 是框架界面语言的选择对话框：列出 `LanguageManager.available_languages()` 扫描到的全部可用语言（`ui/text/*.xml`），确定后实时切换、无需重启。底层能力由 `core/i18n` 的 `LanguageManager` 单例提供（详见 [多语言（i18n）子系统概述](../core/i18n/overview.md)）。

### 9.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog，WindowModal（父窗口为主窗口） |
| 最小宽度 | 360 |
| 打开方式 | 菜单 **编辑 > 语言**（位于「切换主题」之后） |
| 样式 | 按钮 `variant` 由 UIKit 全局 QSS 驱动，随全局主题自动切换 |

### 9.3 行为语义

- 语言列表每行显示「语言自称 (语言代码)」，自称取自该语言文件 `common/language.self_name` 键；当前语言默认选中；语言代码存入 `UserRole`，确定时据此切换（不解析显示文本）；
- **确定**：选中语言与当前不同时经 `LanguageManager.set_language()` 实时切换——持久化到 `config/i18n.json` 并发射 `language_changed` 信号，主窗口/标题栏/技能面板/工作区/用量面板/托盘经各自的 `_retranslate_ui()` 重取词；
- **取消**：`reject()`，不改动当前语言。

### 9.4 使用方式

```python
from ui.dialog.language_dialog import LanguageDialog

dialog = LanguageDialog(main_window)
dialog.exec()
```

---

## 10. PluginLanguageDialog 插件语言对话框

**文件位置**: `ui/dialog/plugin_language_dialog.py`

### 10.1 概述

`PluginLanguageDialog` 为单个插件设置语言覆盖（每插件语言自定义）。由插件管理对话框详情面板的「语言…」按钮打开（插件无语言包时该按钮置灰）。

### 10.2 窗口属性

| 属性 | 值 |
|------|------|
| 窗口类型 | QDialog，WindowModal（父窗口通常为插件管理对话框） |
| 最小宽度 | 360 |
| 构造参数 | `PluginLanguageDialog(plugin_id, plugin_name, parent)` |

### 10.3 行为语义

- 选项列表第一项固定为「跟随框架（默认）」（`UserRole` 存 None，即清除覆盖），其后仅列出该插件 `text/` 目录实际提供的语言（`LanguageManager.plugin_available_languages()`），显示「语言自称 (语言代码)」；
- 当前生效项默认选中（按 `plugin_language_override()` 判断）；
- **确定**：经 `LanguageManager.set_plugin_language()` 持久化覆盖到 `config/plugin_languages.json` 并发射 `plugin_language_changed` 信号，实时生效；插件 Widget 是否跟随刷新由插件自行 connect 信号实现（框架不替插件重绘）；
- **取消**：`reject()`，不改动现有覆盖。

### 10.4 使用方式

```python
from ui.dialog.plugin_language_dialog import PluginLanguageDialog

dialog = PluginLanguageDialog(plugin_id, plugin_name, parent)
dialog.exec()
```

---

## 11. 相关文档

- [主窗口](main-window.md)
- [系统托盘与关闭行为](system-tray.md)
- [技能面板](skills-panel.md)
- [字体子系统概述](../core/font-manager/overview.md)
- [多语言（i18n）子系统概述](../core/i18n/overview.md)
- [插件系统概述](../core/plugin-system/overview.md)
- [GitHub 插件安装器](../core/plugin-system/plugin-installer.md)
