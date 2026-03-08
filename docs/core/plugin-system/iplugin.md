# IPlugin 接口

> 插件抽象基类的完整说明

---

## 1. 概述

`IPlugin` 是所有插件必须继承的抽象基类，定义了插件的标准接口和行为。

**文件位置**: `core/plugin/plugin_interface.py`

```python
from abc import ABC, abstractmethod

class IPlugin(ABC):
    """插件抽象基类"""
    pass
```

---

## 2. 核心属性

### 2.1 plugin_name

```python
@property
@abstractmethod
def plugin_name(self) -> str:
    """
    插件名称（必需属性）

    用于在技能面板显示和插件标识。
    建议使用简洁的名称，可包含换行符（如 "文本\n格式化"）

    Returns:
        插件名称字符串
    """
    pass
```

### 2.2 plugin_id

```python
@property
def plugin_id(self) -> Optional[str]:
    """
    插件唯一标识符 (UUID)

    在插件加载时由 PluginManager 自动设置。
    可用于 DataProvider 等需要唯一标识的场景。

    Returns:
        UUID 字符串，如果未设置则返回 None
    """
    return self._plugin_id
```

### 2.3 skill_icon

```python
@property
def skill_icon(self) -> Optional[QIcon]:
    """
    技能按钮图标

    从 information.py 中的 PluginInfo 动态加载。
    如果未定义，返回默认系统图标。

    Returns:
        QIcon 对象
    """
    # 动态从 information.py 加载
    ...
```

### 2.4 skill_description

```python
@property
def skill_description(self) -> str:
    """
    技能简短描述

    显示在技能按钮下方或提示信息中。
    从 information.py 中的 PluginInfo 动态加载。

    Returns:
        描述字符串，默认返回 plugin_name
    """
    # 动态从 information.py 加载
    ...
```

### 2.5 skill_tooltip

```python
@property
def skill_tooltip(self) -> str:
    """
    技能按钮工具提示

    鼠标悬停时显示的提示信息。

    Returns:
        格式: "{plugin_name}\n{skill_description}"
    """
    return f"{self.plugin_name}\n{self.skill_description}"
```

### 2.6 plugin_info

```python
@property
def plugin_info(self) -> Optional['IPluginInfo']:
    """
    插件信息对象

    从 information.py 动态加载。

    Returns:
        IPluginInfo 实例，如果插件未提供 information.py 则返回 None
    """
    # 动态从 information.py 加载
    ...
```

---

## 3. 核心方法

### 3.1 _create_widget()

```python
@abstractmethod
def _create_widget(self, parent=None, data_provider=None) -> QWidget:
    """
    创建插件控件的内部方法（抽象方法）

    这是插件的核心方法，必须由子类实现。
    首次创建 Widget 时调用，之后会缓存结果。

    Args:
        parent: 父控件，通常是 WorkArea
        data_provider: DataProvider 实例，可用于数据持久化

    Returns:
        插件的 QWidget 控件

    Example:
        def _create_widget(self, parent=None, data_provider=None):
            plugin_id = self.plugin_id or "default-id"

            # 创建服务实例
            service = Service(plugin_id)

            # 注册插件
            if data_provider:
                try:
                    data_provider.register_plugin(plugin_id, "MyPlugin")
                except:
                    pass

            # 构建 UI
            widget = QWidget(parent)
            layout = QVBoxLayout(widget)

            # 添加控件...
            label = QLabel("Hello Plugin")
            layout.addWidget(label)

            return widget
    """
    pass
```

### 3.2 get_widget()

```python
def get_widget(self, parent=None, data_provider=None) -> QWidget:
    """
    获取插件控件（带缓存）

    首次调用时创建 Widget 并缓存，后续调用返回缓存的实例。
    如果传入了不同的 parent，会重新设置 Widget 的 parent。

    Args:
        parent: 父控件
        data_provider: DataProvider 实例

    Returns:
        插件的 QWidget 控件

    Note:
        开发者通常不需要重写此方法，
        只需实现 _create_widget() 即可享受缓存机制。
    """
    # 如果有缓存的 widget 且 parent 相同，直接返回
    if self._cached_widget is not None and self._cached_parent is parent:
        return self._cached_widget

    # 如果有缓存的 widget 但 parent 不同，更新 parent
    if self._cached_widget is not None:
        self._cached_widget.setParent(parent)
        self._cached_parent = parent
        return self._cached_widget

    # 创建新的 widget
    widget = self._create_widget(parent, data_provider)
    self._cached_widget = widget
    self._cached_parent = parent
    return widget
```

### 3.3 on_plugin_loaded()

```python
def on_plugin_loaded(self) -> None:
    """
    插件加载完成回调

    在插件被加载且 plugin_id 已设置后调用。
    可用于注册定时任务工厂等初始化操作。

    注意：此时插件的 UI 尚未创建，不要在此方法中创建 QWidget。

    Example:
        def on_plugin_loaded(self):
            # 注册定时任务工厂
            task_manager = BackgroundTaskManager()
            task_manager.register_scheduled_task_factory(
                self.plugin_id,
                self.my_task_func,
                self.my_callback
            )
    """
    pass
```

---

## 4. Widget 缓存机制

### 4.1 原理

```
用户点击技能按钮
    │
    ▼
get_widget(parent, data_provider)
    │
    ├── 检查 _cached_widget 是否存在
    │
    ├── 情况1: 缓存存在且 parent 相同
    │       └── 直接返回缓存的 Widget
    │
    ├── 情况2: 缓存存在但 parent 不同
    │       └── 更新 parent，返回缓存的 Widget
    │
    └── 情况3: 缓存不存在
            └── 调用 _create_widget() 创建
                └── 缓存并返回
```

### 4.2 优势

1. **状态保持**: 切换插件再回来时，UI 状态不会丢失
2. **性能优化**: 无需重复创建 Widget
3. **开发者透明**: 无需编写额外代码

### 4.3 注意事项

- `_create_widget()` 只在首次调用时执行
- 缓存的 Widget 会被隐藏但不会被销毁
- 如果需要在 Widget 创建时执行逻辑，可以重写 `get_widget()`

---

## 5. 完整示例

### 5.1 entrance.py

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Signal

from core.plugin.plugin_interface import IPlugin


class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""

    # 信号定义
    text_formatted = Signal(str)

    @property
    def plugin_name(self) -> str:
        return "文本\n格式化"

    def _create_widget(self, parent=None, data_provider=None):
        plugin_id = self.plugin_id or "text-formatting-default"

        # 创建服务实例
        service = Service(plugin_id, data_provider)

        # 注册插件
        if data_provider:
            try:
                data_provider.register_plugin(plugin_id, "TextFormatting")
            except Exception as e:
                print(f"注册插件失败: {e}")

        # 创建 UI
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)

        # 输入框
        self.input_edit = QTextEdit()
        layout.addWidget(self.input_edit)

        # 格式化按钮
        btn_upper = QPushButton("转大写")
        btn_upper.clicked.connect(lambda: self._format_text(service, 'upper'))
        layout.addWidget(btn_upper)

        btn_lower = QPushButton("转小写")
        btn_lower.clicked.connect(lambda: self._format_text(service, 'lower'))
        layout.addWidget(btn_lower)

        # 输出框
        self.output_edit = QTextEdit()
        self.output_edit.setReadOnly(True)
        layout.addWidget(self.output_edit)

        return widget

    def _format_text(self, service, mode):
        text = self.input_edit.toPlainText()
        if mode == 'upper':
            result = service.to_uppercase(text)
        else:
            result = service.to_lowercase(text)
        self.output_edit.setPlainText(result)
        self.text_formatted.emit(result)

    def on_plugin_loaded(self):
        """插件加载完成回调"""
        print(f"插件已加载: {self.plugin_name}")
```

---

## 6. 相关文档

- [插件系统概述](overview.md)
- [PluginManager](plugin-manager.md)
- [插件开发指南](plugin-development.md)

---

*本文档由 Claude Code 自动生成*
