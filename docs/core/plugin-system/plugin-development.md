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
├── icons/                    # 图标目录（可选）
│   └── icon.png
└── assets/                   # 资源目录（可选）
    └── ...
```

---

## 2. 三个核心文件

### 2.1 entrance.py（必需）

这是插件的入口文件，必须继承 `IPlugin` 并实现核心方法。

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

```python
from core.data.data_provider import DataProvider, DataNamespace


class Service:
    """插件服务类"""

    def __init__(self):
        # DataProvider 为单例，直接获取实例
        self._data_provider = DataProvider()

    def my_method(self, param: str) -> str:
        """可被外部调用的方法"""
        return f"处理: {param}"

    def save_data(self, plugin_id: str, key: str, value: any):
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

如果要将插件发布到 GitHub 供他人通过「从 GitHub 安装插件」功能安装，需要在仓库中包含描述文件。

### 4.1 单插件仓库

在仓库根目录创建 `IXPlugin.json`：

```json
{
  "id": "my-awesome-plugin",
  "name": "My Awesome Plugin",
  "version": "release.1.0.0",
  "main": "entrance.py",
  "description": "一个强大的插件",
  "author": "Your Name",
  "keywords": ["text", "utility"]
}
```

### 4.2 多插件仓库

在仓库根目录创建 `IXRepo.json` 作为索引，每个插件子目录创建 `IXPlugin.json`：

```
multi-plugin-repo/
├── IXRepo.json              # 仓库索引
├── plugin-a/
│   ├── IXPlugin.json        # 插件 A 描述
│   └── entrance.py
└── plugin-b/
    ├── IXPlugin.json        # 插件 B 描述
    └── entrance.py
```

**IXRepo.json 示例**:
```json
{
  "plugins": [
    { "path": "plugin-a", "id": "plugin-a", "name": "Plugin A" },
    { "path": "plugin-b", "id": "plugin-b", "name": "Plugin B" }
  ]
}
```

### 4.3 描述文件字段说明

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 插件唯一标识符（字母、数字、下划线、短横线） |
| `name` | string | 是 | 插件显示名称 |
| `version` | string | 是 | 版本号，格式：`<类型>.<大>.<小>.<补丁>`，如 `release.1.0.0` |
| `main` | string | 是 | 插件入口文件路径 |
| `description` | string | 否 | 插件简短描述 |
| `author` | string | 否 | 插件作者 |

### 4.4 安装目录规则

| GitHub 组织 | 安装目录 |
|------------|---------|
| `KKPIP-Tech` | `plugin/`（官方插件目录） |
| 其他所有 | `custom_plugin/`（第三方插件目录） |

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

---

*本文档由 Claude Code 自动生成*
