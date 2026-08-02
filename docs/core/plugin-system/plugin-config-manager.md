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

## 3. 配置文件读写 API

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

如果文件不存在或读取失败，返回空字典 `{"official_plugins": [], "thirdparty_plugins": []}`。

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
def update_official_order(self, plugin_uuids: List[str]) -> bool
```

更新官方插件的顺序。

**参数**:
- `plugin_uuids`: 官方插件的 UUID 列表（按新的显示顺序）

**返回**:
- 是否更新成功

### update_thirdparty_order()

```python
def update_thirdparty_order(self, plugin_uuids: List[str]) -> bool
```

更新第三方插件的顺序。

**参数**:
- `plugin_uuids`: 第三方插件的 UUID 列表（按新的显示顺序）

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

## 5. 插件顺序应用机制

### apply_custom_order()

> ⚠️ 此方法由 `PluginManager` 调用，不属于 `PluginConfigManager`。定义在 `PluginManager` 中。

```python
def apply_custom_order(self):
    """从配置文件加载并应用用户自定义的插件显示顺序"""
```

**排序规则**:
1. 按 `plugin_order.json` 中记录的 UUID 顺序排列插件
2. 配置中存在但当前未加载的插件会被跳过
3. **新安装的插件（UUID 不在配置中）自动追加到列表末尾**，而非插入到特定位置

> 详细说明参见 [PluginManager.apply_custom_order()](./plugin-manager.md)

### 重置顺序

通过 `PluginOrderDialog` 的"重置"按钮调用:

```python
config_manager.save_plugin_order([], [])  # 清空两个列表
```

清空后，`apply_custom_order()` 会将所有插件按默认加载顺序（目录扫描顺序）排列，新插件同样追加到末尾。

---

## 6. 跨模块 API 说明

> ⚠️ 以下两个方法不属于 `PluginConfigManager`，属于 `PluginManager`：
> - `get_official_plugin_ids()` — 见 [PluginManager.get_official_plugin_ids()](./plugin-manager.md)
> - `get_thirdparty_plugin_ids()` — 见 [PluginManager.get_thirdparty_plugin_ids()](./plugin-manager.md)

---

## 7. 插件 UUID 管理

插件 UUID 由 `core/plugin/plugin_identity.py` 中的 `PluginIdentity` 类管理。首次加载插件时自动生成 UUID 并存储在插件目录的 `.plugin_info.json` 文件中，后续加载时读取该文件以保持 ID 稳定。`plugin_order.json` 中存储的即为这些 UUID。

---

## 8. 相关文档

- [PluginManager](plugin-manager.md)
- [插件系统概述](overview.md)
