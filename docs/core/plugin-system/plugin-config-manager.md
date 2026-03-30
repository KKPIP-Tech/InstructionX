# PluginConfigManager 插件配置管理器

> 管理插件的显示顺序配置，持久化到 `config/plugin_order.json`

---

## 1. 概述

`PluginConfigManager` 负责管理插件的显示顺序配置，将插件的排列顺序持久化存储。

**文件位置**: `core/plugin/config_manager.py`

---

## 2. 配置文件格式

配置文件位置: `config/plugin_order.json`

```json
{
    "official_plugins": [
        "uuid-1",
        "uuid-2",
        "uuid-3"
    ],
    "thirdparty_plugins": [
        "uuid-a",
        "uuid-b"
    ]
}
```

---

## 3. 核心 API

### load_plugin_order()

```python
def load_plugin_order(self) -> Dict[str, List[str]]
```

加载插件顺序配置。

**返回**:
```python
{
    "official_plugins": ["uuid-1", "uuid-2", ...],
    "thirdparty_plugins": ["uuid-a", "uuid-b", ...]
}
```

如果文件不存在或读取失败，返回空列表。

### save_plugin_order()

```python
def save_plugin_order(self, official_plugins: List[str], thirdparty_plugins: List[str]) -> bool
```

保存插件顺序配置。

**参数**:
- `official_plugins`: 官方插件的 UUID 列表（按显示顺序）
- `thirdparty_plugins`: 第三方插件的 UUID 列表（按显示顺序）

**返回**:
- 是否保存成功

### update_official_order()

```python
def update_official_order(self, plugin_names: List[str]) -> bool
```

更新官方插件的顺序。

**参数**:
- `plugin_names`: 官方插件的 UUID 列表（按新的显示顺序）

**返回**:
- 是否更新成功

### update_thirdparty_order()

```python
def update_thirdparty_order(self, plugin_names: List[str]) -> bool
```

更新第三方插件的顺序。

**参数**:
- `plugin_names`: 第三方插件的 UUID 列表（按新的显示顺序）

**返回**:
- 是否更新成功

---

## 4. 使用示例

### 保存当前顺序

```python
from core.plugin.config_manager import PluginConfigManager

config_manager = PluginConfigManager()

# 获取当前顺序
order = config_manager.load_plugin_order()
print(f"官方插件: {order['official_plugins']}")
print(f"第三方插件: {order['thirdparty_plugins']}")

# 更新顺序
config_manager.update_official_order(["uuid-2", "uuid-1", "uuid-3"])
```

### 通过 PluginManager 保存

```python
from core.plugin.manager import PluginManager

manager = PluginManager()
manager.load_plugins()

# 重新排序后保存
manager.save_plugin_order(
    official_plugins=["uuid-2", "uuid-1", "uuid-3"],
    thirdparty_plugins=["uuid-b", "uuid-a"]
)
```

---

## 5. 相关文档

- [PluginManager](plugin-manager.md)
- [插件系统概述](overview.md)

---

*本文档由 Claude Code 自动生成*
