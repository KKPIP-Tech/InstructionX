# IPlugin 接口

> 插件抽象基类的完整说明

---

## 1. 概述

`IPlugin` 是所有插件必须继承的抽象基类，定义了插件的标准接口和行为。

**文件位置**:
- 抽象接口定义: `core/interfaces/i_plugin.py`
- 框架实现（含缓存）: `core/plugin/plugin_interface.py`（推荐导入）

推荐导入方式:
```python
from core.plugin import IPlugin              # 推荐：框架实现，含控件缓存和动态加载
# 或等价路径:
from core.plugin.plugin_interface import IPlugin
```

> **重要**: 本文档混合描述了抽象接口规范和框架实现行为。以下标注了"框架实现"的内容
> （如 `get_widget()`、控件缓存、`skill_icon` 动态加载等）定义在 `core/plugin/plugin_interface.py` 中。
> `core/interfaces/i_plugin.py` 仅定义纯抽象接口（无缓存），供框架内部和高级场景使用。
>
> 插件开发者应始终从 `core.plugin` 或 `core.plugin.plugin_interface` 导入 `IPlugin`，
> 以确保获得控件缓存、图标动态加载等完整框架能力。

框架实现（`core/plugin/plugin_interface.py`）在纯抽象接口基础上额外提供：
- 控件缓存机制（`_cached_widget`）
- 插件信息动态加载（`_load_plugin_info`）
- `skill_icon` / `skill_description` 从 `information.py` 自动加载

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

    在插件加载时由 PluginManager 自动设置（存放在内部字段 `_plugin_id`）。
    可用于 DataProvider 等需要唯一标识的场景。

    Returns:
        UUID 字符串，如果未设置则返回 None
    """
    return self._plugin_id
```

> 注意: 上述 `return self._plugin_id` 行为定义在框架实现 `core/plugin/plugin_interface.py` 中。
> 抽象接口 `core/interfaces/i_plugin.py` 中该属性直接返回 `None`。
> 插件应始终由 PluginManager 加载以确保 `plugin_id` 正确设置。

### 2.3 skill_icon

```python
@property
def skill_icon(self) -> Optional[QIcon]:
    """
    技能按钮图标

    从 information.py 中的 PluginInfo 动态加载。
    如果未定义或加载失败，返回系统默认文件图标（`QStyle.StandardPixmap.SP_FileIcon`）。

    Returns:
        QIcon 对象
    """
    # 动态从 information.py 加载
    ...
```

> 注意: 抽象接口 `core/interfaces/i_plugin.py` 中该属性直接返回 `None`。
> 动态加载行为由框架实现 `core/plugin/plugin_interface.py` 提供。
> 插件开发者应在 `information.py` 中配置 `PluginInfo.skill_icon`。

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

> 注意: 抽象接口 `core/interfaces/i_plugin.py` 中该属性直接返回 `self.plugin_name`。
> 动态加载行为由框架实现 `core/plugin/plugin_interface.py` 提供。

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

> 注意: 抽象接口 `core/interfaces/i_plugin.py` 中该属性直接返回 `None`。
> 动态加载行为由框架实现 `core/plugin/plugin_interface.py` 提供（通过 `_load_plugin_info()` 内部方法）。

> 注意：`tags` 不是 `IPlugin` 的属性，而是 `IPluginInfo` 的可选属性（默认返回 `None`）。
> 如需使用标签功能，可在 `information.py` 的 `PluginInfo` 类中覆盖 `tags` 属性。

---

## 3. 核心方法

### 3.1 _create_widget()

```python
@abstractmethod
def _create_widget(self, parent=None, data_provider=None) -> "QWidget":
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

> **重要说明**: `get_widget()` 是**框架实现方法**，定义在 `core/plugin/plugin_interface.py` 中，**不属于抽象接口** `core/interfaces/i_plugin.py`。
> 开发者只需实现抽象方法 `_create_widget()`，框架会自动提供带缓存的 `get_widget()` 能力。

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
def on_plugin_loaded(self, plugin_id: Optional[str] = None, **kwargs) -> None:
    """
    插件加载完成回调

    在插件被框架加载且 plugin_id 已设置后调用。
    子类可重写此方法执行初始化逻辑，例如：
    - 注册定时任务工厂
    - 初始化后台服务
    - 订阅其他插件的数据

    注意：
    - 框架调用此方法时**不传任何参数**（向后兼容旧插件）。
    - plugin_id 通过 `self.plugin_id` 访问（而非通过形参）。
    - services 已通过 `self._services` 实例属性注入（由 PluginManager 设置）。
    - 此时插件的 UI 尚未创建，禁止在此方法中实例化 QWidget。

    Args:
        plugin_id: 插件唯一标识符（仅用于向后兼容，实际通过 self.plugin_id 访问）
        **kwargs: 预留参数（services 等通过实例属性 self._services 访问）

    Example:
        def __init__(self, services=None):
            # 在 __init__ 中通过 services 参数注入
            super().__init__()
            self._llm = services.llm_facade if services else None

        def on_plugin_loaded(self, plugin_id=None, **kwargs):
            # plugin_id 通过 self.plugin_id 访问
            # services 已通过 self._services 访问
            print(f"插件 {self.plugin_id} 已加载")
    """
    pass
```

### 3.4 llm_tools

```python
@property
def llm_tools(self) -> List[Dict[str, Any]]:
    """
    获取插件暴露的 LLM 工具列表

    返回符合 OpenAI function calling 规范的工具定义列表。
    插件可通过重写此属性来声明自己暴露的工具。

    Returns:
        工具定义列表，每项包含 name、description、parameters 字段
    """
    return []
```

---

## 4. 插件生命周期

### 4.1 加载流程

插件加载由 `PluginManager` 触发，完整流程详见 [PluginManager](plugin-manager.md)。

主要阶段：
1. 动态导入 `entrance.py` 模块，查找 `IPlugin` 子类
2. 实例化插件（尝试注入 `services`）
3. 由 PluginManager 设置 `_plugin_id` 和 `_services` 实例属性
4. 调用 `on_plugin_loaded()` 回调
5. 注册到插件注册表

### 4.2 实例属性注入

PluginManager 在加载完成后会直接设置以下实例属性（无需插件接收形参）：

| 属性 | 来源 | 访问方式 |
|------|------|---------|
| `self._plugin_id` | PluginManager 生成/读取 | `self.plugin_id` |
| `self._services` | PluginManager 创建并注入 | `self._services.llm_facade` 等 |
| `self._plugin_dir` | PluginManager 设置 | 用于 `_load_plugin_info()` |

### 4.3 卸载

当前框架不提供显式的插件卸载回调。若需清理资源，可在 Python 对象销毁时依赖 `__del__`（不推荐用于关键逻辑）。

---

## 5. Widget 缓存机制

### 5.1 原理

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

### 5.2 实现细节

缓存机制在 `core/plugin/plugin_interface.py` 中实现（**框架实现，非抽象接口**）：

```python
class IPlugin(ABC):
    def __init__(self):
        # 缓存的 Widget 实例
        self._cached_widget = None
        # 缓存的 parent 引用
        self._cached_parent = None
        # 插件信息缓存 (mtime, instance)
        self._info_cache = None
        self._info_cache_path = None

    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """
        获取插件控件（带缓存）
        
        首次调用时创建 Widget 并缓存，后续调用返回缓存的实例。
        如果传入了不同的 parent，会重新设置 Widget 的 parent。
        """
        # 情况1: 缓存存在且 parent 相同，直接返回
        if self._cached_widget is not None and self._cached_parent is parent:
            return self._cached_widget
        
        # 情况2: 缓存存在但 parent 不同，更新 parent
        if self._cached_widget is not None:
            self._cached_widget.setParent(parent)
            self._cached_parent = parent
            return self._cached_widget
        
        # 情况3: 缓存不存在，创建新的 widget
        widget = self._create_widget(parent, data_provider)
        self._cached_widget = widget
        self._cached_parent = parent
        return widget
```

### 5.3 优势

1. **状态保持**: 切换插件再回来时，UI 状态（如输入框内容、选中的选项等）不会丢失
2. **性能优化**: 无需重复创建 Widget，节省内存和 CPU 资源
3. **开发者透明**: 框架自动管理缓存，开发者无需编写额外代码
4. **内存可控**: Widget 在插件卸载时会被清理，不会永久占用内存

### 5.4 注意事项

- `_create_widget()` 只在首次调用 `get_widget()` 时执行（框架实现提供的能力）
- 缓存的 Widget 会被隐藏（`hide()`）但不会被销毁
- Widget 的生命周期与插件实例绑定
- 如果需要在 Widget 创建时执行额外逻辑，可以重写 `get_widget()` 方法（仅在框架实现 `plugin_interface.py` 中有效）

### 5.5 缓存失效策略

当前实现的缓存策略是**永久缓存**（直到插件卸载），适用于大多数场景。如果需要实现更复杂的缓存策略，可以考虑：

1. **基于时间的缓存**: 设置缓存过期时间
2. **基于内存压力的缓存**: 当内存不足时自动清理
3. **手动清除**: 提供方法让开发者手动清除缓存

### 5.6 自定义缓存行为示例

```python
class CustomPlugin(IPlugin):
    def __init__(self):
        super().__init__()
        self._cache_enabled = True
    
    def get_widget(self, parent=None, data_provider=None) -> QWidget:
        """自定义缓存逻辑"""
        if not self._cache_enabled:
            # 禁用缓存，每次都重新创建
            return self._create_widget(parent, data_provider)
        
        # 使用默认缓存逻辑
        return super().get_widget(parent, data_provider)
    
    def clear_cache(self):
        """手动清除缓存"""
        if self._cached_widget is not None:
            self._cached_widget.deleteLater()
            self._cached_widget = None
            self._cached_parent = None
```

---

## 6. 完整示例

### 6.1 entrance.py

```python
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QTextEdit
from PySide6.QtCore import Signal

from core.plugin import IPlugin  # 推荐导入路径（框架实现，含缓存）


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
        """插件加载完成回调（plugin_id 通过 self.plugin_id 访问）"""
        print(f"插件已加载: {self.plugin_name}")
```

---

## 7. 相关文档

- [插件系统概述](overview.md)
- [PluginManager](plugin-manager.md)
- [插件开发指南](plugin-development.md)

---

*本文档由 Claude Code 自动生成*
