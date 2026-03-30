# PluginIdentity 插件身份标识

> 管理插件的唯一标识符（UUID），支持持久化和自动生成

---

## 1. 概述

`PluginIdentity` 负责为每个插件实例生成和管理唯一的 UUID，并将该标识符持久化到插件目录下的隐藏文件中。

**文件位置**: `core/plugin/plugin_identity.py`

---

## 2. 核心功能

- **自动生成 UUID**: 为新插件自动生成全局唯一的标识符
- **持久化存储**: 将 UUID 存储在 `{plugin_dir}/.plugin_info.json` 文件中
- **跨会话一致**: 应用重启后可通过加载已有 UUID 保持插件身份不变
- **ID 再生**: 支持在需要时重新生成 UUID

---

## 3. 数据存储

UUID 及注册时间存储在插件目录的 `.plugin_info.json` 文件中：

```json
{
    "plugin_id": "cded5a3d-09a9-4d8d-b8b0-6792eec4590d",
    "registered_at": "2026-03-01T10:00:00"
}
```

---

## 4. 核心 API

### load_or_create_id()

```python
def load_or_create_id(self) -> str
```

加载已存在的插件 ID，或创建新的 UUID。

**逻辑**:
1. 检查 `{plugin_dir}/.plugin_info.json` 是否存在
2. 如果存在，读取其中的 `plugin_id`
3. 如果不存在，生成新的 UUID，写入文件，返回

**返回**:
- 插件 UUID 字符串

**示例**:
```python
from core.plugin.plugin_identity import PluginIdentity

identity = PluginIdentity(plugin_dir="/path/to/plugin")
plugin_id = identity.load_or_create_id()
print(f"插件 ID: {plugin_id}")
```

### regenerate_id()

```python
def regenerate_id(self) -> str
```

重新生成插件 UUID（会覆盖已有 ID）。

> **警告**：重新生成 UUID 会导致该插件在 DataProvider 中的数据无法被正确加载，因为数据按实例 ID 索引。请谨慎使用。

**返回**:
- 新的插件 UUID 字符串

**示例**:
```python
identity = PluginIdentity(plugin_dir="/path/to/plugin")
new_id = identity.regenerate_id()
print(f"新插件 ID: {new_id}")
```

---

## 5. 使用场景

### PluginManager 中的使用

`PluginManager._load_plugin_from_directory()` 在加载插件时使用 `PluginIdentity`：

```python
identity = PluginIdentity(plugin_dir)
plugin_id = identity.load_or_create_id()
plugin_instance._plugin_id = plugin_id
```

### 获取当前插件 ID

在插件的 `entrance.py` 中，通过 `self.plugin_id` 属性访问由 `PluginManager` 设置的 UUID：

```python
class MyPlugin(IPlugin):
    def _create_widget(self, parent=None, data_provider=None):
        plugin_id = self.plugin_id  # 由 PluginManager 在加载时设置
        service = Service(plugin_id, data_provider)
        # ...
```

---

## 6. 相关文档

- [PluginManager](plugin-manager.md)
- [插件系统概述](overview.md)

---

*本文档由 Claude Code 自动生成*
