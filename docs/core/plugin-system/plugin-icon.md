# PluginIcon 插件图标

> 支持多种图标加载策略：系统图标、文件图标、资源图标、Base64 编码

---

## 1. 概述

`PluginIcon` 封装了插件图标的各种加载方式，为插件提供灵活的图标配置能力。

**文件位置**: `core/plugin/plugin_icon.py`

---

## 2. IconType 枚举

```python
from core.plugin.plugin_icon import IconType

class IconType(Enum):
    """图标类型枚举"""
    BUILTIN = "builtin"   # 使用 Qt 系统内置图标
    FILE = "file"         # 从文件系统加载
    RESOURCE = "resource"  # 从 Qt 资源系统加载
    BASE64 = "base64"      # 从 Base64 编码字符串加载
    NONE = "none"          # 不使用图标
```

---

## 3. 工厂方法

### builtin()

```python
@classmethod
def builtin(cls, icon_name: str) -> "PluginIcon"
```

创建使用 Qt 系统内置图标的 PluginIcon。

**参数**:
- `icon_name`: Qt 标准图标名称（如 `"SP_FileIcon"`, `"SP_MessageBoxInformation"`, `"SP_ArrowForward"`）

**示例**:
```python
icon = PluginIcon.builtin("SP_FileIcon")
icon = PluginIcon.builtin("SP_MessageBoxInformation")
```

### from_file()

```python
@classmethod
def from_file(cls, relative_path: str) -> "PluginIcon"
```

创建从文件加载图标的 PluginIcon。

**参数**:
- `relative_path`: 相对于插件目录的图标文件路径

**示例**:
```python
icon = PluginIcon.from_file("icons/icon.png")
icon = PluginIcon.from_file("assets/logo.png")
```

### from_resource()

```python
@classmethod
def from_resource(cls, resource_path: str) -> "PluginIcon"
```

创建从 Qt 资源系统加载图标的 PluginIcon。

**示例**:
```python
icon = PluginIcon.from_resource(":/icons/plugin_icon.png")
```

### from_base64()

```python
@classmethod
def from_base64(cls, base64_data: str) -> "PluginIcon"
```

创建从 Base64 编码字符串加载图标的 PluginIcon。

**参数**:
- `base64_data`: 图标的 Base64 编码字符串

**示例**:
```python
icon = PluginIcon.from_base64("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
```

### none()

```python
@classmethod
def none(cls) -> "PluginIcon"
```

创建表示无图标的 PluginIcon。`load_icon()` 返回 `None`。

---

## 4. 加载图标

### load_icon()

```python
def load_icon(self, plugin_dir: Optional[Path] = None) -> Optional[QIcon]
```

根据图标类型加载并返回 `QIcon` 对象。所有异常均在内部捕获并记录日志，失败时静默返回 `None`。

**参数**:
- `plugin_dir`: 插件目录路径（用于解析相对路径）。`FILE` 类型必须传入此参数以解析相对路径；其他类型可不传。

**返回**:
- `QIcon` 对象，`NONE` 类型或加载失败时返回 `None`。注意：返回值无法区分"显式无图标"和"加载失败"。

**示例**:
```python
icon = PluginIcon.builtin("SP_FileIcon")
qicon = icon.load_icon()                          # BUILTIN/RESOURCE/BASE64 可不传 plugin_dir
qicon = icon.load_icon(plugin_dir=plugin_dir)     # FILE 类型必须传入 plugin_dir
```

---

## 5. 使用示例

### 在 information.py 中定义图标

```python
from core.plugin.plugin_icon import PluginIcon

class MyPluginInfo(IPluginInfo):
    @property
    def skill_icon(self) -> PluginIcon:
        # 使用 Qt 系统图标
        return PluginIcon.builtin("SP_FileIcon")

class AnotherPluginInfo(IPluginInfo):
    @property
    def skill_icon(self) -> PluginIcon:
        # 使用插件目录下的文件
        return PluginIcon.from_file("icons/logo.png")

class ImagePluginInfo(IPluginInfo):
    @property
    def skill_icon(self) -> PluginIcon:
        # 使用 Base64 编码的图标
        return PluginIcon.from_base64("iVBORw0KGgoAAAANS...")
```

---

### 5.2 IPlugin 中的图标加载机制

`IPlugin` 基类（`core/plugin/plugin_interface.py`）的 `skill_icon` 属性自动处理 `PluginIcon` 的加载与降级，开发者**无需手动调用 `load_icon()`**。

加载流程如下：

1. 调用 `_load_plugin_info()` 加载 `information.py`，获取其中的 `skill_icon` 属性返回值（`PluginIcon` 实例）
2. 调用 `plugin_info.skill_icon.load_icon(plugin_dir)` 获取 `QIcon`
3. 如果返回值为 `None` 或 `QIcon.isNull()`，降级为系统默认图标 `SP_FileIcon`

因此，开发者只需在 `information.py` 中按以下方式定义图标即可：

```python
class MyPluginInfo(IPluginInfo):
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_FileIcon")
        # 也可以使用:
        # return PluginIcon.from_file("icons/logo.png")
        # return PluginIcon.from_resource(":/icons/plugin_icon.png")
        # return PluginIcon.from_base64("iVBORw0KGgoAAAANS...")
        # return PluginIcon.none()
```

框架会自动调用 `load_icon()` 并处理所有边界情况，包括文件不存在、图标名无效等异常。

---

## 6. 常用系统图标名称

| 图标名称 | 说明 |
|---------|------|
| `SP_FileIcon` | 文件图标 |
| `SP_MessageBoxInformation` | 信息图标 |
| `SP_MessageBoxWarning` | 警告图标 |
| `SP_MessageBoxCritical` | 错误图标 |
| `SP_MessageBoxQuestion` | 问题图标 |
| `SP_ArrowForward` | 前进箭头 |
| `SP_ArrowBack` | 后退箭头 |
| `SP_ArrowUp` | 上箭头 |
| `SP_ArrowDown` | 下箭头 |
| `SP_DialogOpenButton` | 打开按钮 |
| `SP_DialogOkButton` | 确定按钮 |
| `SP_DesktopIcon` | 桌面图标 |
| `SP_ComputerIcon` | 计算机图标 |
| `SP_VistaShield` | 安全图标 |
| `SP_MediaPause` | 暂停图标 |

---

## 7. 相关文档

- [IPluginInfo 接口](iplugin.md)
- [插件开发指南](plugin-development.md)

---

*本文档由 Claude Code 自动生成*
