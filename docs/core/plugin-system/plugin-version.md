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

`VersionType` 是 `core/plugin/plugin_version.py` 中定义的枚举类，直接导入使用，无需自行定义：

```python
from core.plugin.plugin_version import VersionType, PluginVersion

# 查看所有可用版本类型
for vt in VersionType:
    print(vt.name, vt.value)
```

### 枚举成员

| 枚举值 | 中文名 | 优先级 |
|--------|--------|--------|
| `INTERNAL` | 内部版 | 1（最低） |
| `ALPHA` | 内测版 | 2 |
| `BETA` | 测试版 | 3 |
| `PRE_RELEASE` | 预发布版 | 4 |
| `RELEASE` | 正式版 | 5（最高） |

### 辅助方法

`VersionType` 枚举实例提供以下方法：

```python
vt = VersionType.BETA
vt.get_priority()        # 返回优先级整数，3
vt.get_display_name()    # 返回中文显示名，"测试版"
```

### 优先级

`RELEASE > PRE_RELEASE > BETA > ALPHA > INTERNAL`

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

## 5. 比较运算与字符串表示

PluginVersion 支持完整的语义化版本比较：

```python
v1 = PluginVersion.from_string("release.1.0.0")
v2 = PluginVersion.from_string("release.1.0.1")
v3 = PluginVersion.from_string("beta.1.0.0")

print(v2 > v1)   # True（修订号更大）
print(v1 > v3)   # True（正式版 > 测试版）
print(v1 == v1)  # True
print(v3 < v1)   # True
print(v1 != v2)  # True
print(v1 <= v1)  # True（小于等于）
print(v2 >= v1)  # True（大于等于）
```

### 字符串转换

```python
v = PluginVersion.from_string("release.1.0.0")

print(str(v))        # "release.1.0.0"（通过 __str__）
print(repr(v))       # "PluginVersion('release.1.0.0')"（通过 __repr__）
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
