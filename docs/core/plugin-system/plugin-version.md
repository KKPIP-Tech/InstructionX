# PluginVersion 插件版本

> 语义化版本管理，支持类型前缀和中文显示

---

## 1. 概述

`PluginVersion` 是插件的版本管理类，采用语义化版本规范并支持类型前缀。

**文件位置**: `core/plugin/plugin_version.py`

---

## 2. 版本格式

版本字符串格式为 `<version_type>.<major>.<minor>.<patch>`，例如：

- `release.1.0.0` — 正式版 1.0.0
- `beta.2.1.0` — 测试版 2.1.0
- `alpha.1.0.0` — 内测版 1.0.0
- `internal.1.0.0` — 内部版 1.0.0

---

## 3. VersionType 枚举

```python
from core.plugin.plugin_version import VersionType, PluginVersion

class VersionType(Enum):
    """版本类型枚举，按优先级从高到低排列"""
    INTERNAL = "internal"      # 内部版
    ALPHA = "alpha"            # 内测版
    BETA = "beta"             # 测试版
    PRE_RELEASE = "pre_release"  # 预发布版
    RELEASE = "release"        # 正式版
```

### 优先级

`INTERNAL > ALPHA > BETA > PRE_RELEASE > RELEASE`

两个版本比较时，优先比较类型优先级，再比较主版本号、次版本号、修订号。

---

## 4. 核心 API

### from_string()

```python
@classmethod
def from_string(cls, version_str: str) -> "PluginVersion"
```

从版本字符串解析为 `PluginVersion` 对象。

**示例**:
```python
v1 = PluginVersion.from_string("release.1.0.0")
v2 = PluginVersion.from_string("beta.2.1.3")
v3 = PluginVersion.from_string("alpha.1.0.0")
```

### to_string()

```python
def to_string(self) -> str
```

将版本对象转换回字符串格式。

**示例**:
```python
v = PluginVersion.from_string("release.1.0.0")
print(v.to_string())  # "release.1.0.0"
```

### get_display_version()

```python
def get_display_version(self) -> str
```

获取中文显示版本字符串。

**示例**:
```python
v = PluginVersion.from_string("release.1.0.0")
print(v.get_display_version())  # "正式版 1.0.0"

v = PluginVersion.from_string("beta.2.1.0")
print(v.get_display_version())  # "测试版 2.1.0"
```

---

## 5. 比较运算

PluginVersion 支持完整的语义化版本比较：

```python
v1 = PluginVersion.from_string("release.1.0.0")
v2 = PluginVersion.from_string("release.1.0.1")
v3 = PluginVersion.from_string("beta.1.0.0")

print(v2 > v1)   # True（修订号更大）
print(v1 > v3)   # True（正式版 > 测试版）
print(v1 == v1)  # True
print(v3 < v1)   # True
```

---

## 6. 使用示例

```python
from core.plugin.plugin_version import PluginVersion

# 定义插件版本
class MyPluginInfo(IPluginInfo):
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")

# 比较版本
v1 = PluginVersion.from_string("beta.1.0.0")
v2 = PluginVersion.from_string("release.1.0.0")
print(f"当前版本: {v1.get_display_version()}")  # 测试版 1.0.0
```

---

## 7. 相关文档

- [IPluginInfo 接口](iplugin.md)
- [插件开发指南](plugin-development.md)

---

*本文档由 Claude Code 自动生成*
