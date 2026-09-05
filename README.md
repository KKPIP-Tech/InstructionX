<div align="center">

<img src="./assets/logo.png" alt="InstructionX Logo" width="100%">


**基于 PySide6 的插件式桌面应用框架 —— LLM 集成 · MCP 协议双向支持 · 热插拔插件系统**

[![CI](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml/badge.svg)](https://github.com/KKPIP-Tech/InstructionX/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10+-green.svg)](https://doc.qt.io/qtforpython/)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey.svg)](#)
[![Version](https://img.shields.io/badge/Alpha-1.1.0%20CE-red.svg)](#)
[![License](https://img.shields.io/badge/License-AGPL--3.0%2B%20%2B%20%C2%A77%20Terms-blue.svg)](LICENSE)

中文版 | [English Version](README_EN.md)

</div>

---

## 简介

InstructionX 是一个基于 PySide6 的**插件式桌面应用框架**。它将插件热插拔、多厂商大语言模型（LLM）集成、MCP 协议双向支持、数据持久化与后台任务管理等能力整合为统一的基础设施，使用户能够按自身工作流程自由组合工具插件，构建专属的一站式工具集（Tools Cluster）。

框架本身不绑定具体业务功能：所有业务能力均以插件形式接入，并通过 GitHub 插件仓库生态分发。开发者可以基于框架提供的标准化插件接口、依赖注入服务容器与 UIKit 组件库，快速开发并发布自己的插件。

> 本项目为应用型项目，以源码方式直接运行，不作为库分发。

## 核心特性

### 插件系统

- **生命周期管理**：插件热加载 / 热卸载 / 热重载，无需重启应用；卸载时自动清理插件身份标识与语言覆盖等关联数据
- **安装与更新**：内置 GitHub 安装器支持单插件仓库（IXPlugin.json）与多插件仓库（IXRepo.json），后台安装并显示进度；支持本地 zip 安装、GitHub Release 升级 / 降级与版本关系检测；KKPIP-Tech 组织仓库自动归类为官方插件
- **版本与身份治理**：语义化插件版本（alpha / beta / pre-release / release）与每插件 UUID 身份标识；已安装插件注册表记录版本 / 来源 / 安装时间，作为升级与更新检查依据；插件声明的 Python 依赖由框架自动安装（优先 uv，回退 pip）
- **跨插件协作**：插件声明 `service_api` 即自动注册跨插件 API 并同步暴露为 MCP 工具；插件亦可通过 `llm_tools` 直接向 LLM 注册工具
- **面板组织**：技能面板支持自定义分组、折叠与混排顺序；切换插件时自动缓存界面状态，返回时完整恢复

### LLM 集成

- **多厂商支持**：内置 MiniMax、SiliconFlow、智谱 GLM、Ollama、OpenAI 共 5 家供应商预设，另有 `openai-compatible` 兜底适配器，任意 OpenAI 兼容端点零代码接入
- **多会话管理**：会话创建 / 切换 / 持久化，上下文超出窗口时基于 token 估算自动截断（保留 system prompt 与最近消息）
- **工具调用自动化**：ToolCallExecutor 自动处理工具调用多轮循环（默认 `max_turns=5`），插件只需注册工具
- **多模态**：图片理解（Vision）、图片生成、TTS 语音合成、Embedding 向量嵌入
- **用量统计**：按会话与全局统计 Token 消耗与费用估算，内置可视化用量查询面板（AI → 用量查询）

### MCP 协议双向支持

- **MCP Server**：将全部插件 API 自动暴露为 MCP 工具，支持 stdio 与 HTTP 传输，可选 Bearer 鉴权；Claude Code 等 MCP Client 可直接调用插件能力
- **MCP Client**：连接外部 MCP Server，将其工具注册进本地 ToolRegistry，供 LLM 调用
- **双向桥接**：MCPBridge 自动同步插件 API 注册表与 MCP Server

### 数据持久化

- **SQLite WAL + 显式事务**：默认后端，意外中断不损坏数据；可通过环境变量回退至 JSON 后端
- **双命名空间**：PRIVATE 空间仅插件内部可见，PUBLIC 空间支持跨插件共享
- **发布 / 订阅**：插件可订阅数据变更，实现响应式交互；内存缓存减少磁盘 I/O

### 后台任务系统

- **线程池异步任务**：4 个工作线程，避免阻塞 UI
- **定时任务与长期任务**：固定间隔重复执行；长期任务支持优雅停止与自动重启
- **任务持久化**：任务状态跨重启保留，配合任务工厂机制自动重建

### 多语言（i18n）

- **XML 语言文件**：框架与插件均采用「一个语言一个 XML 文件」的约定，内置中文（默认）与英文
- **实时切换**：编辑菜单「语言」即时切换界面语言，无需重启
- **回退链取词**：当前语言缺失条目自动回退至默认语言
- **每插件语言覆盖**：单个插件可使用与框架不同的界面语言

### 界面体系

- **InstructionX_UIKit 组件库**：58 个组件 + 13 种布局 + 52 个动画，含原生图表引擎、蓝图节点图与 Mermaid 渲染；light / dark / auto 三种全局主题模式，设计令牌（Design Tokens）随主题实时换肤
- **字体管理器**：应用级字体安装 / 卸载 / 预览（进程内生效，不写系统字体目录），字体缺失时自动回退系统字体
- **系统托盘**：托盘菜单实时呈现运行中的插件与后台任务；关闭主窗口时弹出确认对话框，可选择退出程序或最小化到托盘

## 快速开始

### 环境要求

- Windows 10 / 11
- Python 3.14 或更高版本
- [uv](https://docs.astral.sh/uv/)（Python 虚拟环境与依赖管理器）

### 安装 uv

```bash
# Windows（PowerShell）
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 安装依赖

首次运行 `uv run main.py` 时会自动创建虚拟环境并按 `uv.lock` 同步依赖；也可先显式安装：

```bash
uv venv
uv pip install -r requirements.txt
```

> 注意：请勿使用 `uv sync` —— 它会严格对齐 `uv.lock` 并**移除**环境中额外安装的包（如插件经框架 DependencyManager 安装的依赖、测试依赖等）。

### 运行

```bash
uv run main.py
```

首次运行会自动创建 `data/` 与 `config/` 目录。

## 插件生态

InstructionX 是插件框架，本身不内置业务插件。获取插件的途径：

- **GitHub 安装**：菜单「编辑 → 从 GitHub 安装插件...」，输入插件仓库 URL 一键安装
- **手动安装**：将从第三方开发者处获取的插件复制到 `custom_plugin/` 目录

### 插件结构

每个插件为 `plugin/`（官方）或 `custom_plugin/`（第三方）下的一个一级子目录：

```
my_plugin/
├── entrance.py      # 必需：插件入口，定义 IPlugin 子类
├── information.py   # 必需：插件元信息（IPluginInfo 子类：版本、图标、service_api 等）
├── service.py       # 必需：插件服务 / 公开 API 层
├── config/          # 必需：插件配置目录
├── text/            # 必需：语言包目录（<语言代码>.xml，一个语言一个文件）
└── assets/          # 可选：静态资源目录
```

提供 `service_api` 且服务类名以 `Service` 结尾时，框架自动注册跨插件 API 并同步为 MCP 工具。

### 插件元数据

插件仓库通过 `IXPlugin.json` 描述插件，其中 `name` 与 `description` 支持多语言字段：

```json
{
    "id": "my-plugin",
    "name": {"zh": "我的插件", "en": "My Plugin"},
    "version": "release.1.0.0",
    "main": "entrance.py",
    "description": {"zh": "插件简介", "en": "Short description."},
    "author": "Your Name",
    "keywords": ["instructionx", "plugin"]
}
```

多插件仓库需额外提供 `IXRepo.json` 索引文件。

### 插件可用框架服务

框架创建插件实例时自动注入 `PluginServices` 服务容器，插件可直接使用框架的全部基础设施：

| 服务 | 说明 |
|------|------|
| `services.llm_facade` | LLM 插件服务门面：多会话对话、工具调用、多模态、用量统计 |
| `services.data_provider` | DataProvider 数据层：PRIVATE / PUBLIC 命名空间、发布订阅 |
| `services.task_manager` | BackgroundTaskManager 后台任务：异步 / 定时 / 长期任务 |
| `services.logger` | 日志接口（ILogger） |
| `services.mcp_manager` | MCP Server 管理：将插件 API 暴露为 MCP 工具 |
| `services.mcp_client` | MCP Client：连接外部 MCP Server |
| `services.font_manager` | 字体管理器：带回退链的字体解析 |
| `services.localization` | 多语言取词门面（绑定插件 UUID） |

### 最小插件示例

```python
from core import IPlugin
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout

class MyPlugin(IPlugin):
    @property
    def plugin_name(self) -> str:
        """显示在技能面板的名称"""
        return "我的\n插件"

    @property
    def skill_description(self) -> str:
        return "这是一个示例插件"

    def _create_widget(self, parent=None, data_provider=None):
        """创建插件界面"""
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        layout.addWidget(QLabel("Hello from MyPlugin!"))
        return widget
```

### 示例插件

仓库 `plugin/` 目录提供本地开发参考示例：[framework-api-demo](plugin/framework-api-demo)（框架核心 API 演示：数据持久化、后台任务、LLM、MCP、跨插件调用）、[ui-demo](plugin/ui-demo)、[blueprint-opencv](plugin/blueprint-opencv)。详见[插件索引](docs/plugins/index.md)。

### 插件开发文档

- [插件开发快速入门](插件开发流程.md)（环境初始化 / 插件仓库配置 / AI 辅助提示词模板）
- [插件开发指南](docs/core/plugin-system/plugin-development.md)（[English](Plugin-Development-Guide.md)）
- [IPlugin 接口详解](docs/core/plugin-system/iplugin.md)
- [LLM 集成开发指南](docs/plugins/llm-integration-guide.md)

## 文档

完整的中文技术文档位于 [docs/](docs/README.md)，涵盖：

- **架构设计**：[系统架构概述](docs/architecture/overview.md)、[模块依赖关系](docs/architecture/module-dependencies.md)
- **核心模块**：[插件系统](docs/core/plugin-system/overview.md)、[DataProvider 数据层](docs/core/data-provider/overview.md)、[后台任务](docs/core/background-task/overview.md)、[LLM Provider](docs/core/llm-provider/overview.md)、[MCP 协议](docs/core/mcp/overview.md)、[多语言子系统](docs/core/i18n/overview.md)、[字体管理器](docs/core/font-manager/overview.md)
- **界面**：[主窗口](docs/ui/main-window.md)、[系统托盘与关闭行为](docs/ui/system-tray.md)、[UIKit 主题系统](docs/utils/uikit-theme.md)
- **API 参考**：[完整 API 索引](docs/api/full-reference.md)

## 项目结构

```
main.py            # 应用入口
core/              # 框架核心：接口层 / 插件系统 / 数据层 / 后台任务 / LLM / MCP / 字体 / i18n
ui/                # 界面层：主窗口 / 技能面板 / 工作区 / 系统托盘 / 对话框 / InstructionX_UIKit
utils/             # 工具模块（日志、线程封送等）
plugin/            # 官方 / 示例插件目录（本地开发验证用）
custom_plugin/     # 第三方插件目录
scripts/           # 冒烟 / 截图 / 演示脚本
test/              # pytest 测试
docs/              # 技术文档
config/            # 运行时生成：配置文件
data/              # 运行时生成：数据库、任务状态、字体等
logs/              # 运行时生成：应用日志
```

## 配置与数据

以下文件在运行时生成，请勿手动修改其结构：

| 文件 | 用途 |
|------|------|
| `config/llm_providers.json` | LLM Provider 实例配置（API Key 混淆存储） |
| `config/llm_models_cache.json` | 模型列表缓存 |
| `config/mcp_config.json` | MCP Server / Client 配置 |
| `config/plugin_order.json` | 未分组插件的显示顺序 |
| `config/plugin_groups.json` | 用户自定义插件分组与面板顺序 |
| `config/plugin_registry.json` | 已安装插件注册表（升级 / 降级依据） |
| `config/i18n.json` | 框架语言设置 |
| `config/plugin_languages.json` | 每插件语言覆盖 |
| `data/data.db` | 插件数据（SQLite + WAL） |
| `data/tasks.json` | 后台任务状态 |
| `data/llm_usage.json` | LLM 用量记录 |
| `data/conversations.json` | LLM 会话持久化 |
| `data/fonts/` | 框架安装的字体及注册表 |
| `logs/application.log` | 应用日志 |

### 环境变量

| 变量 | 作用 |
|------|------|
| `INSTRUCTIONX_DATAPROVIDER_BACKEND` | 数据层后端：`sqlite`（默认）/ `json` |
| `INSTRUCTIONX_MCP_CONFIG` | 覆盖 MCP 配置文件路径 |
| `INSTRUCTIONX_GITHUB_TOKEN` | GitHub API Token：提升插件安装 / 更新检查的限流阈值 |
| `INSTRUCTIONX_LOG_DIR` | 覆盖日志输出目录 |
| `INSTRUCTIONX_LOG_LEVEL` | 覆盖日志级别（`DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL`） |
| `DEVELOPMENT_MODE` | 开发模式开关 |

## 测试与 CI

```bash
pip install -e ".[test]"
python -m pytest test/ -q --tb=short -p no:cacheprovider
```

- CI 运行于 GitHub Actions（`windows-latest` + Python 3.14），push 至 `dev` / `main` 及所有 PR 触发
- `scripts/` 目录提供核心链路无网冒烟脚本（`smoke_*.py`）、语言文件完整性校验（`check_i18n_completeness.py`）与 MCP SDK 冒烟测试等独立验证脚本

## 贡献与支持

- **问题反馈**：如遇到问题或有功能建议，欢迎提交 [Issue](https://github.com/KKPIP-Tech/InstructionX/issues)
- **贡献代码**：向本项目提交贡献即表示你同意 [InstructionX 个人贡献者许可协议（ICLA）](ICLA.md)——你保留自己贡献的版权，并授予生产者双重许可（AGPL 社区版 + 专有商业版）所需的许可
- **分支约定**：`dev` 为开发分支（不含测试代码），pytest 测试代码仅存在于 `test` 分支，`main` 为发布分支
- **文档语言**：项目文档与代码注释以中文为主

## 技术栈

| 技术 | 用途 | 版本 |
|------|------|------|
| Python | 编程语言 | >= 3.14 |
| PySide6 | Qt GUI 框架 | >= 6.10 |
| mcp | MCP 协议（FastMCP） | >= 1.28.1, < 2 |
| requests / aiohttp | HTTP / 异步 HTTP | >= 2.32 / >= 3.11 |
| orjson | 高性能 JSON 序列化 | >= 3.11.0, < 4 |
| matplotlib | 用量统计与 UIKit MarkdownView LaTeX 公式渲染 | >= 3.10 |
| packaging | 插件依赖版本检查 | >= 23.0 |
| qrcode[pil] | UIKit QRCodeView 组件 | >= 7.4 |
| InstructionX_UIKit | 界面主题与组件库 | 内置（alpha-v1.0.2） |

## 许可证

InstructionX 是开源软件，采用 **GNU AGPL v3**（或更高版本）授权，并附两条依 AGPL 第 7 条加入的附加条款：

- **署名与品牌标识保留**（§7b）：任何包含框架用户界面（`./ui/` 目录）的副本或网络交互版本，必须保留 InstructionX 名称、LOGO、版权信息与框架标识性描述
- **商标不授权**（§7e）：本许可证不授予 InstructionX 名称与 LOGO 的任何商标使用权

**商业授权（双重许可）**——以下场景需另行取得书面商业授权（联系 dakuang2002@126.com）：

1. 闭源运营 SaaS / 多租户服务（1 租户 = 1 工作区）
2. 将 InstructionX 嵌入第三方商业产品或平台（不遵守 copyleft 义务）
3. 将 InstructionX 作为第三方 SaaS / 平台的后端服务（不遵守 copyleft 义务）
4. 白标使用：移除、修改框架 LOGO、名称、版权信息或框架标识性描述
5. 将框架与插件批量捆绑销售（无论是否开放捆绑体源码）

独立开发、仅经框架公开插件接口交互的插件为独立作品，许可由插件作者自定。

完整条款见 [LICENSE](LICENSE)。
