# 插件开发指南

> 从零开始开发自己的插件

---

## 1. 插件目录结构

```
my_plugin/                    # 插件文件夹（建议使用英文）
├── __init__.py              # Python 包标识（可为空）
├── entrance.py              # 插件入口（必需）
├── service.py               # 业务逻辑（必需）
├── information.py            # 插件元数据（必需）
├── config/                   # 插件配置目录（必需——开发规范要求；
│                             #   框架层面仅硬校验 entrance.py）
├── icons/                    # 图标目录（可选）
│   └── icon.png
└── assets/                   # 资源目录（可选）
    └── ...
```

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
        plugin_id = self.plugin_id or "my-plugin-default"

        # 创建服务实例（Service 的具体参数取决于其实现）
        service = Service()

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

业务逻辑层，不依赖 UI，纯 Python 实现。

硬性要求：**`service.py` 中的服务类名必须以 `Service` 结尾**（如 `Service`、`MyPluginService`）。框架在自动注册跨插件 API 时按此约定查找服务类。

框架自动实例化服务类时，按以下顺序匹配构造函数签名（尝试到成功为止）：

1. `(plugin_id, data_provider, llm_service, task_service)`
2. `(plugin_id, data_provider, llm_service)`
3. `(plugin_id, data_provider)`
4. `(plugin_id,)`
5. `()`

```python
from typing import Any

from core.data.data_provider import DataProvider, DataNamespace


class Service:
    """插件服务类"""

    def __init__(self):
        # DataProvider 为单例，直接获取实例
        self._data_provider = DataProvider()

    def my_method(self, param: str) -> str:
        """可被外部调用的方法"""
        return f"处理: {param}"

    def save_data(self, plugin_id: str, key: str, value: Any):
        """保存数据"""
        self._data_provider.set_plugin_data(
            plugin_id,
            key,
            value,
            DataNamespace.PRIVATE
        )

    def load_data(self, plugin_id: str, key: str, default=None):
        """加载数据"""
        return self._data_provider.get_plugin_data(
            plugin_id,
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
from core.data.data_provider import DataProvider, DataNamespace


class Service:
    """文本格式化服务"""

    def __init__(self):
        self._data_provider = DataProvider()

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
| `name` | string | 是 | 插件显示名称，允许中文与空格，仅用于界面展示 |
| `version` | string | 是 | 必须匹配 `^(release|pre-release|beta|alpha|internal)\.\d+\.\d+\.\d+$`（如 `release.1.0.0`）。类型优先级 `release > pre-release > beta > alpha > internal`：稳定发布用 `release`；正式发布前的候选版本用 `pre-release`；公开测试用 `beta`；内部测试用 `alpha`；仅限开发调试、不对外分发用 `internal` |
| `main` | string | 是 | 插件入口文件路径，固定为 `entrance.py` |
| `description` | string | 否 | 插件简短描述，展示在安装/管理界面 |
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
- `dependencies` 声明了未实际使用的包；
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
    def __init__(self):
        self._data_provider = DataProvider()

    def save_preference(self, plugin_id: str, key: str, value):
        self._data_provider.set_plugin_data(
            plugin_id,
            key,
            value,
            DataNamespace.PRIVATE  # 私有数据
        )

    def load_preference(self, plugin_id: str, key: str, default=None):
        return self._data_provider.get_plugin_data(
            plugin_id,
            key,
            DataNamespace.PRIVATE,
            default
        )
```

### 5.3 发布/订阅

```python
from core.data.data_provider import DataProvider


class Service:
    def __init__(self):
        self._data_provider = DataProvider()

    def subscribe_to_other_plugin(self, my_plugin_id: str, target_plugin_id: str):
        self._data_provider.subscribe(
            subscriber_id=my_plugin_id,
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

### 5.5 UIKit 主题规范

插件 UI **必须使用 InstructionX_UIKit 主题体系**（见 [UIKit 主题系统](../../utils/uikit-theme.md)），禁止在插件中自建主题或硬编码颜色/字号。仅当 UIKit 确实缺失所需组件时才允许自行设计，且必须遵循 UIKit 设计令牌（tokens），并支持 light / dark / auto 主题切换，保证与应用整体观感一致。

---

## 6. 调试技巧

### 6.1 打印日志

```python
def _create_widget(self, parent=None, data_provider=None):
    print(f"[_create_widget] plugin_id: {self.plugin_id}")
    print(f"[_create_widget] plugin_name: {self.plugin_name}")

    # ... 调试代码 ...

    return widget
```

### 6.2 测试 API 调用

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

## 7. 相关文档

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
