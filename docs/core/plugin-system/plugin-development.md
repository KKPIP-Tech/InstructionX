# 插件开发指南

> 从零开始开发自己的插件

---

## 1. 插件目录结构

```
my_plugin/                    # 插件文件夹（建议使用英文）
├── __init__.py              # Python 包标识（可为空）
├── entrance.py              # 插件入口（必需）：胶水层，协调 UI 与 Service
├── service.py               # 接口层（必需）：仅对外暴露 API，业务逻辑下沉 function/
├── information.py           # 插件元数据（必需）
├── config/                  # 插件配置目录（必需——开发规范要求；
│                            #   框架层面仅硬校验 entrance.py；配置型数值集中于此，禁止魔法数）
├── text/                    # 语言包目录（必需）：<语言代码>.xml，一个语言一个文件，见 §6
├── function/                # 业务逻辑层（推荐）：承载全部业务实现，禁止依赖 PySide6
├── ui/                      # 视图层（推荐）：只做界面渲染与事件分发，禁止业务逻辑
├── icons/                   # 图标目录（可选）
│   └── icon.png
├── assets/                  # 资源目录（可选）
│   └── ...
└── docs/                    # 插件自带文档（可选；PRD/SPEC 存放于 docs/req/<YYYY-MM-DD>/）
```

> **位置约束**：每个插件必须是 `plugin/`（官方）或 `custom_plugin/`（第三方）的**一级子目录**——框架只扫描这两个目录的一级子目录（跳过 `_` 前缀目录），不会递归扫描更深层级。

---

## 2. 三个核心文件

### 2.1 entrance.py（必需）

这是插件的入口文件，必须继承 `IPlugin` 并实现核心方法。

**IPlugin 的导入路径**（重要）：

| 导入路径 | 说明 |
|---------|------|
| `from core.plugin.plugin_interface import IPlugin` | 含控件缓存的框架实现（**推荐**）：切换插件时框架自动缓存 Widget，再次切回时 UI 状态自动保留 |
| `from core import IPlugin` | `core` 包惰性导出，导出的同样是含控件缓存的框架实现，与上一条等价 |
| `from core.interfaces import IPlugin` | 无控件缓存的抽象基类，仅用于接口定义与类型约束，插件开发不建议使用 |

本文档所有示例统一使用推荐的 `from core.plugin.plugin_interface import IPlugin`。

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton

from core.plugin.plugin_interface import IPlugin  # 框架实现（含控件缓存）
from .service import Service


class MyPlugin(IPlugin):
    """我的插件"""

    @property
    def plugin_name(self) -> str:
        """插件名称"""
        return "我的\n插件"

    def _create_widget(self, parent=None, data_provider=None):
        """创建插件 UI"""
        # 创建服务实例：框架服务统一经 self._services 注入获取，
        # 不在插件内自行实例化框架单例的替代品
        service = Service(self.plugin_id, self._services.data_provider)

        # 创建 UI
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        label = QLabel("Hello from My Plugin!")
        layout.addWidget(label)

        # 添加更多控件...
        button = QPushButton("点击我")
        layout.addWidget(button)

        return widget

    def on_plugin_loaded(self):
        """插件加载完成回调（可选）"""
        print(f"插件 {self.plugin_name} 已加载")
```

### 2.2 service.py（必需）

插件**对框架的接口层**：只对外暴露 API，不依赖 UI。全部业务逻辑应下沉到 `function/` 目录的独立子模块（`function/` 内禁止依赖 PySide6），`service.py` 中的服务类以门面/委托方式调用它们。

硬性要求：**`service.py` 中的服务类名必须以 `Service` 结尾**（如 `Service`、`MyPluginService`）。框架在自动注册跨插件 API 时按此约定查找服务类。

> **💡 允许的代理模式**：当插件业务实现分散在多个子模块（如 `function/services/`、`function/utils/` 等）时，`service.py` 中的 `Service` 类可通过 `__getattr__` 转发属性访问到底层实现（典型写法：`Service.__getattr__` 转发到 `function/services/core_service.py`）。**框架对此模式无限制**——只要 `Service` 类存在于 `service.py` 中、类名以 `Service` 结尾即可。

框架自动实例化服务类时，按以下顺序匹配构造函数签名（尝试到成功为止）：

1. `(plugin_id, data_provider, llm_service, task_service)`
2. `(plugin_id, data_provider, llm_service)`
3. `(plugin_id, data_provider)`
4. `(plugin_id,)`
5. `()`

```python
from typing import Any, Optional

from core.data.data_provider import DataProvider, DataNamespace


class Service:
    """插件服务类（接口层门面，业务实现委托给 function/ 子模块）"""

    def __init__(self, plugin_id: Optional[str] = None,
                 data_provider: Optional[DataProvider] = None):
        # 框架自动实例化时按上述签名候选注入依赖；手动创建时
        # 从插件的 self._services 容器获取传入——框架服务统一经
        # 注入获取，不在插件内自行实例化框架单例的替代品
        self._plugin_id = plugin_id
        self._data_provider = data_provider

    def my_method(self, param: str) -> str:
        """可被外部调用的方法"""
        return f"处理: {param}"

    def save_data(self, key: str, value: Any):
        """保存数据（使用注入的 plugin_id 与 data_provider）"""
        self._data_provider.set_plugin_data(
            self._plugin_id,
            key,
            value,
            DataNamespace.PRIVATE
        )

    def load_data(self, key: str, default=None):
        """加载数据"""
        return self._data_provider.get_plugin_data(
            self._plugin_id,
            key,
            DataNamespace.PRIVATE,
            default
        )
```

### 2.3 information.py（必需）

插件元数据，定义 API 接口。

```python
from core.interfaces import IPluginInfo  # 推荐导入路径
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class MyPluginInfo(IPluginInfo):
    """插件信息"""

    @property
    def version(self) -> PluginVersion:
        """插件版本"""
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        """开发者名称"""
        return "Your Name"

    @property
    def developer_email(self) -> str:
        return "email@example.com"

    @property
    def developer_website(self) -> str:
        return "https://example.com"

    @property
    def is_free(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "这是我的插件的详细描述"

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符（必需）

        用于代码层面的插件识别，应保持稳定不随显示名称变化。
        建议使用小写字母、数字、连字符格式。
        """
        return "my-plugin"

    @property
    def service_api(self) -> Dict[str, Any]:
        """
        定义可被其他插件调用的方法

        这个字典定义了插件的公开 API。
        """
        return {
            "my_method": {
                "description": "我的方法的描述",
                "parameters": {
                    "param": {
                        "type": "str",
                        "description": "参数描述",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "返回值描述"
                }
            },
            "another_method": {
                "description": "另一个方法的描述",
                "parameters": {
                    "value": {"type": "int", "required": False}
                },
                "returns": {"type": "bool"}
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        """技能按钮图标"""
        return PluginIcon.builtin("SP_FileIcon")
        # 或使用自定义图标:
        # return PluginIcon.from_file("icons/icon.png")

    @property
    def skill_description(self) -> str:
        """技能简短描述"""
        return "我的插件功能描述"

    @property
    def tags(self) -> Optional[list[str]]:
        """插件标签（可选）"""
        return ["工具", "示例"]
```

**service_api 的自动注册链路**：插件同时提供 `service_api` 与 `service.py`（含以 `Service` 结尾的服务类）后，框架自动完成：

1. **跨插件 API 注册**：其他插件可通过 `PluginManager().call_plugin_method(caller_id, plugin_id, method_name, **kwargs)` 调用本插件公开的方法；
2. **同步为 MCP 工具**：自动注册为 MCP 工具（工具名 `{plugin_id}__{method_name}`），经内置 MCP Server 对外暴露。

注意：这些 API **不会自动进入 LLM 的 ToolRegistry**。若需要 LLM 直接调用，插件需实现 `IPlugin.llm_tools` 属性（返回 OpenAI function 格式的工具定义），或经 `llm_facade.get_shared_tool_registry()` 自行注册。

---

### 2.3.5 通过 IMCPTool 定义 MCP 工具（**当前未自动注册**）

`IMCPTool` 抽象接口（`core/mcp/plugin_interface.py`）已定义，插件开发者可继承它声明 MCP 工具。

> **⚠️ 当前未实现自动注册**：当前版本 `PluginManager` / `MCPBridge` **尚未实现**对 `IMCPTool` 子类的自动扫描与注册。继承 `IMCPTool` 不会自动将工具暴露到 MCP Server。
>
> 如需将插件能力暴露为 MCP 工具，请改用：
> 1. **推荐**：`information.py` 的 `service_api` 声明（自动注册为跨插件 API 并同步为 MCP 工具，见 §2.3）；或
> 2. **手动**：`on_plugin_loaded()` 中通过 `self._services.mcp_manager` 手动注册。
>
> 详细说明参见 [`docs/core/mcp/overview.md` §7.2](../mcp/overview.md#72-通过-imcptool-定义-mcp-工具)。

---

### 2.4 使用 PluginServices

`PluginServices` 是框架自动注入的服务容器，包含 LLM、数据持久化、任务管理、日志和 MCP 等核心服务。

```python
from core.interfaces import PluginServices  # 类型提示用
from core.plugin.plugin_interface import IPlugin


class MyPlugin(IPlugin):
    def __init__(self, services=None):
        super().__init__()
        # PluginManager 会自动将 services 注入到 self._services
        self._services = services

    def on_plugin_loaded(self):
        """插件加载完成后调用"""
        if self._services:
            # LLM 服务
            llm = self._services.llm_facade

            # 数据持久化
            data_provider = self._services.data_provider

            # 后台任务管理
            task_manager = self._services.task_manager

            # 日志服务
            logger = self._services.logger

            # MCP Server 管理（可能为 None）
            mcp_manager = self._services.mcp_manager

            # MCP 外部客户端（可能为 None）
            mcp_client = self._services.mcp_client
```

**注意**：即使 `__init__` 不接收 `services` 参数，`PluginManager` 仍会在实例化后通过 `self._services` 注入服务容器。

**判空要求**：`data_provider` / `task_manager` 在初始化失败时会被注入为 `None`，使用前必须判空；`mcp_manager` / `mcp_client` 本身就是 Optional，同样需要判空后再使用。`on_plugin_loaded` 由框架无参调用，不要在其中依赖外部传参。

### 2.5 生命周期与热重载

插件的主要生命周期回调：

- `on_plugin_loaded()`：插件加载完成后由框架无参调用，可在此做初始化（订阅数据、注册工具等）；
- `on_plugin_unloaded()`：插件卸载/热重载前由框架调用，可在此做清理（取消订阅、释放资源等）。

热重载（如更新插件后）时框架会完整销毁旧实例：销毁缓存的 Widget、清理 `sys.modules` 中的插件模块、注销已注册的跨插件 API 与 MCP 工具，然后重新加载新版本。插件不应在模块级或全局变量中持有无法重建的状态。

### 2.6 LLM 能力概览

通过 `PluginServices.llm_facade` 可使用框架的 LLM 能力：`chat` / `stream_chat` / `embed`、会话管理、`chat_with_tools`（工具调用多轮循环，`max_turns` 默认 5）、多模态（`generate_image`、`text_to_speech`）、`list_providers` / `get_models`、`get_usage_stats`、`validate_provider` 等。详细用法见 [LLM 集成指南](../../plugins/llm-integration-guide.md)。

---

## 3. 完整示例：文本格式化插件

> **说明**：本示例为最简教学形态——业务逻辑直接写在 `Service` 中，并省略了 `function/` 分层与 `config/` 目录。实际项目请按 §1 目录结构与 §5.6 硬性约束将业务逻辑放入 `function/`。

### 3.1 目录结构

```
text_formatting/
├── __init__.py
├── entrance.py
├── service.py
└── information.py
```

### 3.2 service.py

```python
class Service:
    """文本格式化服务"""

    def to_uppercase(self, text: str) -> str:
        """转换为大写"""
        return text.upper()

    def to_lowercase(self, text: str) -> str:
        """转换为小写"""
        return text.lower()
```

### 3.3 information.py

```python
from core.interfaces import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any, Optional


class TextFormattingPluginInfo(IPluginInfo):
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")

    @property
    def developer(self) -> str:
        return "KKPIP-Tech"

    @property
    def developer_email(self) -> str:
        return "support@example.com"

    @property
    def developer_website(self) -> str:
        return "https://github.com/KKPIP-Tech/InstructionX"

    @property
    def is_free(self) -> bool:
        return True

    @property
    def description(self) -> str:
        return "提供文本格式化工具"

    @property
    def plugin_type_id(self) -> str:
        """插件类型标识符，用于代码层面的插件识别"""
        return "text-formatting"

    @property
    def tags(self) -> Optional[list[str]]:
        return ["text", "formatting", "utility"]

    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {"type": "str", "required": True}
                },
                "returns": {"type": "str"}
            },
            "to_lowercase": {
                "description": "将文本转换为小写",
                "parameters": {
                    "text": {"type": "str", "required": True}
                },
                "returns": {"type": "str"}
            }
        }

    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_ArrowForward")

    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
```

### 3.4 entrance.py

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel
)
from PySide6.QtCore import Qt

from core.plugin.plugin_interface import IPlugin
from .service import Service


class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""

    @property
    def plugin_name(self) -> str:
        return "文本\n格式化"

    def _create_widget(self, parent=None, data_provider=None):
        # 创建服务实例
        service = Service()

        # 创建 UI
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        # 输入区域
        layout.addWidget(QLabel("输入:"))
        self.input_edit = QTextEdit()
        self.input_edit.setPlaceholderText("请输入文本...")
        layout.addWidget(self.input_edit)

        # 按钮区域
        btn_layout = QHBoxLayout()

        btn_upper = QPushButton("大写")
        btn_upper.clicked.connect(lambda: self._format(service, 'upper'))
        btn_layout.addWidget(btn_upper)

        btn_lower = QPushButton("小写")
        btn_lower.clicked.connect(lambda: self._format(service, 'lower'))
        btn_layout.addWidget(btn_lower)

        layout.addLayout(btn_layout)

        # 输出区域
        layout.addWidget(QLabel("输出:"))
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        layout.addWidget(self.output_edit)

        return widget

    def _format(self, service, mode):
        text = self.input_edit.toPlainText()
        if not text:
            return

        if mode == 'upper':
            result = service.to_uppercase(text)
        elif mode == 'lower':
            result = service.to_lowercase(text)
        else:
            result = text

        self.output_edit.setPlainText(result)
```

---

## 4. 远程插件描述文件

如果要将插件发布到 GitHub 供他人通过「从 GitHub 安装插件」功能安装，需要在仓库中包含描述文件。描述文件名**大小写敏感**，必须为 `IXPlugin.json` / `IXRepo.json`。

### 4.1 IXPlugin.json 逐字段使用规范（单插件仓库）

在仓库根目录创建 `IXPlugin.json`：

```json
{
  "id": "my-awesome-plugin",
  "name": "My Awesome Plugin",
  "version": "release.1.0.0",
  "main": "entrance.py",
  "description": "一个强大的插件",
  "author": "Your Name",
  "homepage": "https://example.com/my-awesome-plugin",
  "keywords": ["text", "utility"],
  "dependencies": {
    "requests": ">=2.31.0"
  }
}
```

| 字段 | 类型 | 必需 | 使用规范 |
|------|------|------|----------|
| `id` | string | 是 | 插件唯一标识符，必须匹配正则 `^[a-zA-Z0-9_-]+$`（仅限字母、数字、下划线、短横线），建议 kebab-case。`id` 是升级/降级的匹配依据，**发布后不可变更**，否则框架会视为另一个插件 |
| `name` | string 或 object | 是 | 插件显示名称，允许中文与空格，仅用于界面展示；支持多语言字典形式 `{"zh": "...", "en": "..."}`（见 §6.4） |
| `version` | string | 是 | 必须匹配 `^(release|pre-release|beta|alpha|internal)\.\d+\.\d+\.\d+$`（如 `release.1.0.0`）。类型优先级 `release > pre-release > beta > alpha > internal`：稳定发布用 `release`；正式发布前的候选版本用 `pre-release`；公开测试用 `beta`；内部测试用 `alpha`；仅限开发调试、不对外分发用 `internal` |
| `main` | string | 是 | 插件入口文件路径，固定为 `entrance.py` |
| `description` | string 或 object | 否 | 插件简短描述，展示在安装/管理界面；支持多语言字典形式（见 §6.4） |
| `author` | string | 否 | 插件作者/组织名称 |
| `homepage` | string | 否 | 插件主页 URL（文档、问题反馈页等） |
| `keywords` | array | 否 | 关键词数组，便于检索与分类 |
| `dependencies` | object | 否 | Python 依赖声明，格式 `{"包名": "PEP 440 版本约束"}`（如 `"requests": ">=2.31.0"`）。安装时由框架 DependencyManager 自动检查并安装。**只声明真实使用的依赖**，避免拖慢安装、引入不必要的安全风险 |

### 4.2 IXRepo.json 使用规范（多插件仓库）

在仓库根目录创建 `IXRepo.json` 作为索引，每个插件子目录内创建独立的 `IXPlugin.json`：

```
multi-plugin-repo/
├── IXRepo.json              # 仓库索引
├── plugin-a/
│   ├── IXPlugin.json        # 插件 A 描述（必需，逐字段规范同 §4.1）
│   └── entrance.py
└── plugin-b/
    ├── IXPlugin.json        # 插件 B 描述
    └── entrance.py
```

**IXRepo.json 示例**：
```json
{
  "plugins": [
    { "path": "plugin-a", "id": "plugin-a", "name": "Plugin A" },
    { "path": "plugin-b", "id": "plugin-b", "name": "Plugin B" }
  ]
}
```

`plugins` 数组各项的字段约束：

| 字段 | 使用规范 |
|------|----------|
| `path` | 插件子目录路径，**必须与磁盘上的子目录名完全一致** |
| `id` | **必须等于该子目录内 IXPlugin.json 的 `id`**，两者不一致会导致安装/识别异常 |
| `name` | 插件显示名称，用于安装界面列表展示 |

每个子目录必须有自己独立的 IXPlugin.json，IXRepo.json 仅作为索引，不能替代子目录描述文件。

### 4.3 常见误用清单

- `id` 含空格或中文字符（违反 `^[a-zA-Z0-9_-]+$`，安装会被拒绝）；
- IXRepo.json 的 `path` 与实际子目录名不符（如大小写不一致、多了前缀）；
- `version` 缺少类型前缀（写成 `1.0.0` 而非 `release.1.0.0`）；
- `dependencies` 声明了未实际使用的包，或把 Python 标准库写进依赖；
- 发布后修改 `id`，导致老用户无法升级；
- 描述文件名大小写错误（如 `ixplugin.json`）；
- 多插件仓库只在根目录放一个 IXPlugin.json，子目录缺少独立描述文件。

### 4.4 安装目录规则

| GitHub 组织 | 安装目录 |
|------------|---------|
| `KKPIP-Tech` | `plugin/`（官方插件目录） |
| 其他所有 | `custom_plugin/`（第三方插件目录） |

除 GitHub 一键安装外，框架还支持**本地 zip 安装**（zip 内须包含 IXPlugin.json）。

从 GitHub 安装或检查 Release 更新时，可设置环境变量 `INSTRUCTIONX_GITHUB_TOKEN` 提供 GitHub API Token 用于鉴权，提升 API 限流阈值并支持私有仓库。

---

## 5. 最佳实践

### 5.1 插件注册

> **注意**: 插件注册由 `PluginManager` 在加载时自动处理，通常不需要在 `_create_widget()` 中手动调用。
> 以下代码仅在有特殊需求（如在插件内部主动注册）时参考。

```python
from core.data.data_provider import DataProviderError

def _create_widget(self, parent=None, data_provider=None):
    plugin_id = self.plugin_id or "my-plugin-default"

    if data_provider:
        try:
            # 注册插件（可选，通常由 PluginManager 自动处理）
            data_provider.register_plugin(plugin_id, "MyPlugin")
            # 设置为活跃实例
            data_provider.set_active_instance(plugin_id)
        except DataProviderError as e:
            # 插件可能已存在，忽略错误
            print(f"注册插件: {e}")
```

### 5.2 数据持久化

```python
from core.data.data_provider import DataProvider, DataNamespace


class Service:
    """经构造函数注入框架服务（框架自动实例化时按签名候选注入；
    手动创建时从插件的 self._services 容器获取传入）"""

    def __init__(self, plugin_id: str, data_provider: DataProvider):
        self._plugin_id = plugin_id
        self._data_provider = data_provider

    def save_preference(self, key: str, value):
        self._data_provider.set_plugin_data(
            self._plugin_id,
            key,
            value,
            DataNamespace.PRIVATE  # 私有数据
        )

    def load_preference(self, key: str, default=None):
        return self._data_provider.get_plugin_data(
            self._plugin_id,
            key,
            DataNamespace.PRIVATE,
            default
        )
```

### 5.3 发布/订阅

```python
from core.data.data_provider import DataProvider


class Service:
    def __init__(self, plugin_id: str, data_provider: DataProvider):
        self._plugin_id = plugin_id
        self._data_provider = data_provider

    def subscribe_to_other_plugin(self, target_plugin_id: str):
        self._data_provider.subscribe(
            subscriber_id=self._plugin_id,
            target_plugin_id=target_plugin_id,
            target_key="status",
            callback=self._on_status_changed
        )

    def _on_status_changed(self, target_plugin_id, key, old_value, new_value):
        print(f"插件 {target_plugin_id} 的 {key} 从 {old_value} 变更为 {new_value}")
```

### 5.4 线程模型（订阅回调与 UI 封送）

DataProvider 的 `subscribe` 回调在**工作线程**中执行，回调签名为 `(publisher_id, key, old_value, new_value)`。严禁在回调中直接操作 Qt 控件，UI 更新必须通过 `utils.thread_utils` 封送到 UI 线程：

```python
from utils.thread_utils import run_in_ui_thread, run_in_ui_thread_sync


def _on_status_changed(self, publisher_id, key, old_value, new_value):
    # 异步封送：立即返回，不等待 UI 更新完成
    run_in_ui_thread(self.status_label.setText, str(new_value))

    # 同步封送：阻塞等待并获取返回值
    # text = run_in_ui_thread_sync(self.input_edit.toPlainText, timeout=1.0)
```

- `run_in_ui_thread(func, *args, **kwargs)`：异步封送，立即返回；
- `run_in_ui_thread_sync(func, *args, timeout=None, **kwargs)`：同步封送，阻塞直到 UI 线程执行完毕并返回结果，可用 `timeout` 限制等待时长。

#### 相关线程契约

本节是框架级"工作线程 → UI 线程封送"约定的权威说明。**框架中其他所有"回调运行在工作线程"的接口都在各自文档加了相同警告**（含代码示例），点击下方链接可跳转：

- **DataProvider.subscribe() 回调**：[`docs/core/data-provider/api-reference.md` §subscribe()](../data-provider/api-reference.md#subscribe) — 回调运行在 `set_plugin_data(PUBLIC, notify=True)` 的调用线程（不保证主线程），UI 更新必须封送
- **LLMConfig.subscribe() 回调**：[`docs/core/llm-provider/provider-config.md` §3.2](../llm-provider/provider-config.md#32-单例与变更订阅) — 回调运行在 `add_provider` / `remove_provider` / `save_config` 的调用线程（不保证主线程），UI 更新必须封送

> **统一规则**：任何框架 API 的"回调签名表"如未显式说明线程，**默认**回调运行在调用方的触发线程中。如回调需要更新 UI，**必须**经 `utils.thread_utils.run_in_ui_thread` 封送。

### 5.5 UIKit 主题规范

插件 UI **必须使用 InstructionX_UIKit 主题体系**（见 [UIKit 主题系统](../../utils/uikit-theme.md)），禁止在插件中自建主题或硬编码颜色/字号。仅当 UIKit 确实缺失所需组件时才允许自行设计，且必须遵循 UIKit 设计令牌（tokens），并支持 light / dark / auto 主题切换，保证与应用整体观感一致。

### 5.6 插件开发硬性约束

本指南聚焦插件接口与机制；插件开发的**工程约束以仓库根目录 [AGENTS-for-PLUGIN-DEV.md](../../../AGENTS-for-PLUGIN-DEV.md) 为基准**——两者表述不一致时，以该文件为准。核心约束摘要：

- **分层职责**：`entrance.py` 只做胶水层；`service.py` 只做接口层；`function/` 承载全部业务逻辑（禁止依赖 PySide6）；`ui/` 只做视图渲染与事件分发（禁止业务逻辑）；`information.py` 只做元数据；
- **函数/方法 ≤ 20 行**、**嵌套 ≤ 3 层**、**禁止魔法数**（配置型数值统一放入插件 `config/` 目录注入）；
- **框架服务统一经 `self._services`（PluginServices）注入获取**并正确判空，不自行实例化框架单例的替代品、不在插件内自造全局单例或模块级全局状态；
- **所有 import 位于文件顶部**（PEP 8 分组：标准库 → 第三方 → 本地），严禁函数级 import（唯一例外须开发者许可并注释原因）；插件内部模块间一律使用相对导入；
- **`service_api` 必须随 `function/` 子模块的方法同步更新**；已发布插件的公开接口（`service_api` 签名、订阅 key、配置项含义）保持向后兼容；
- **开发流程**：编码前创建 PRD/SPEC（存放于插件 `docs/req/<YYYY-MM-DD>/`）；测试代码仅存在于插件仓库的 `test` 分支；临时文件统一放框架根目录 `temp/`（禁止放入插件目录）；Commit 按功能颗粒度提交，格式 `<type>(<scope>): <中文描述>`。

---

## 6. 插件多语言（i18n）

框架提供多语言子系统（`core/i18n`），完整机制见 [多语言（i18n）子系统概述](../i18n/overview.md)。插件**必须**提供 `text/` 语言包目录；框架对未提供语言包的存量插件保持兼容（行为与旧版本完全一致）。

### 6.1 语言包目录

在插件目录下创建 `text/<语言代码>.xml`，**一个语言一个文件**（语言代码为 ISO 639-1，可带区域子标签如 `zh-CN`/`zh-TW`）；文件内以 `<group>` 分组、`<text key="...">` 为条目，占位符仅支持命名式 `{name}`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<texts language="zh">
  <group name="main">
    <text key="title">我的插件</text>
    <text key="welcome">你好，{name}</text>
  </group>
</texts>
```

各语言文件的分组与键命名必须一致；其他语言允许缺键（运行时回退），但**插件默认语言文件必须覆盖全部键**——它是回退终点，缺失时界面直接显示 `ERROR_TEXT`（不静默）。框架加载插件时自动扫描注册，插件无需登记代码；可运行 `scripts/check_i18n_completeness.py` 校验完整性。

### 6.2 取词与默认语言声明

经 `PluginServices.localization`（`ILocalizationFacade`，始终注入）取词：

```python
def __init__(self, services: PluginServices | None = None):
    super().__init__()
    self._i18n = services.localization if services else None

def _create_widget(self, parent=None, data_provider=None):
    title = self._i18n.tr("main", "title")                # 分组/键取词
    hint = self._i18n.tr("main", "welcome", name="User")  # 命名占位符
```

插件未提供语言包时 `tr()` 优雅降级返回键名本身。有效语言按「用户语言覆盖 → 框架当前语言 → 插件默认语言」三级解析；插件默认语言经 `IPluginInfo.default_language` 声明（可选，默认 `None` = 跟随框架默认语言 `zh`）。

### 6.3 语言切换刷新约定

框架不替插件重绘 UI。需要跟随语言切换的插件 Widget，自行 connect `LanguageManager` 信号（`language_changed(str)` / `plugin_language_changed(str, str)`）并重取词，详见 [i18n 概述 §7.5](../i18n/overview.md)。

### 6.4 IXPlugin.json 多语言字段

`name` 与 `description` 除纯字符串外支持字典形式 `{"zh": "...", "en": "..."}`，安装与展示时按「目标语言（支持区域子标签解析）→ 默认语言 → 字典第一个值」解析，详见 §4.1 与 [i18n 概述 §7.4](../i18n/overview.md)。

---

## 7. 调试技巧

### 7.1 打印日志

```python
def _create_widget(self, parent=None, data_provider=None):
    print(f"[_create_widget] plugin_id: {self.plugin_id}")
    print(f"[_create_widget] plugin_name: {self.plugin_name}")

    # ... 调试代码 ...

    return widget
```

### 7.2 测试 API 调用

```python
from core.data.data_provider import DataProviderError
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取插件 API
api = manager.get_plugin_api("plugin-uuid")
print("可用方法:", api["methods"])

# 调用方法（method_name 为目标方法名，其余关键字参数应与目标方法的
# 实际参数名对应，此处假设目标方法声明了 param 参数）
result = manager.call_plugin_method(
    caller_id="test",
    plugin_id="plugin-uuid",
    method_name="my_method",
    param="test"
)
print("结果:", result)
```

---

## 8. 相关文档

- [多语言（i18n）子系统概述](../i18n/overview.md)
- [插件开发工程约束基准（AGENTS-for-PLUGIN-DEV.md）](../../../AGENTS-for-PLUGIN-DEV.md)
- [插件系统概述](overview.md)
- [IPlugin 接口](iplugin.md)
- [PluginManager](plugin-manager.md)
- [PluginIdentity](plugin-identity.md)
- [GitHub 插件安装器](plugin-installer.md)
- [接口层概述](../interfaces/overview.md)
- [DataProvider 概述](../data-provider/overview.md)
- [后台任务概述](../background-task/overview.md)
- [后台任务 API 参考](../background-task/api-reference.md)
- [MCP 协议模块概述](../mcp/overview.md)
- [UIKit 主题系统](../../utils/uikit-theme.md)
- [LLM 集成指南](../../plugins/llm-integration-guide.md)
