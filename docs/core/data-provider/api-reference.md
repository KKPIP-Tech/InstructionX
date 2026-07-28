# DataProvider API 参考

> DataProvider 的完整 API 列表和详细说明

---

## 1. 类定义

```python
# 推荐导入方式
from core.data import DataProvider, DataNamespace, DataProviderError

# 获取单例实例
provider = DataProvider()
```

> **导入说明**：`core/__init__.py` 导出了 `DataProvider` 和 `DataNamespace`，但**未导出 `DataProviderError`**。如需使用异常类，请从 `core.data` 导入。

> **DataNamespace 来源**：`core/interfaces/i_data_provider.py`（第 12-16 行）为规范定义位置；`core/data/data_provider.py` 中包含同名枚举，与接口定义一致。

---

## 2. 枚举

### DataNamespace

```python
class DataNamespace(Enum):
    """数据命名空间枚举"""
    PRIVATE = "private"  # 仅插件内部使用
    PUBLIC = "public"    # 允许其他插件访问
```

---

## 3. 构造函数

```python
DataProvider(data_dir: Optional[str] = None, data_filename: str = "data.json")
```

**参数**:
- `data_dir`: 数据文件存储目录，默认为项目根目录下的 `data` 文件夹
- `data_filename`: 数据文件名，默认为 `data.json`。默认后端为 SQLite，该文件名仅用于推导数据库文件名；回退到 JSON 后端时则作为实际 JSON 文件名

**后端选择**:
- 默认使用 **SQLite** 后端，数据库文件由 `data_filename` 推导（见下表），启用 WAL 模式
- 设置环境变量 `INSTRUCTIONX_DATAPROVIDER_BACKEND=json` 可回退到旧 JSON 后端（临时文件 + 原子重命名），仅建议应急排查使用

**数据库文件路径推导**（SQLite 后端）:
- 若 `data_filename` 以 `.json` 结尾，数据库文件名为 `data_filename[:-5] + ".db"`
- 否则，数据库文件名为 `data_filename + ".db"`

示例：

| `data_filename` | 数据库文件 |
|-----------------|------------|
| `data.json`     | `data.db`  |
| `my_data.json`  | `my_data.db` |
| `app_data`      | `app_data.db` |

**示例**:
```python
# 使用默认路径（SQLite）
provider = DataProvider()
# 数据库文件: data/data.db

# 自定义路径
provider = DataProvider(data_dir="/custom/path", data_filename="my_data.json")
# 数据库文件: /custom/path/my_data.db

# 回退到 JSON 后端（需先设置环境变量）
# import os
# os.environ["INSTRUCTIONX_DATAPROVIDER_BACKEND"] = "json"
# provider = DataProvider()
```

**环境变量**:

| 环境变量 | 取值 | 说明 |
|----------|------|------|
| `INSTRUCTIONX_DATAPROVIDER_BACKEND` | `sqlite`（默认） / `json` | 指定 `DataProvider` 持久化后端。`sqlite` 使用 `data/data.db` + WAL；`json` 回退到旧 JSON 文件后端 |

---

## 4. 插件管理方法

### register_plugin()

```python
def register_plugin(self, instance_id: str, plugin_type: str) -> None
```

注册插件实例。

**参数**:
- `instance_id`: 插件实例的唯一标识符（通常使用 UUID）
- `plugin_type`: 插件类型（如 "VideoEditor"、"TaskManager"）

**异常**:
- `DataProviderError`: 插件已存在时抛出

**示例**:
```python
provider.register_plugin("video-editor-001", "VideoEditor")
```

---

### unregister_plugin()

```python
def unregister_plugin(self, instance_id: str) -> None
```

注销插件实例。

**参数**:
- `instance_id`: 插件实例的唯一标识符

**异常**:
- `DataProviderError`: 插件不存在时抛出

**注意**: 注销插件时会自动清理相关的订阅关系。

**示例**:
```python
provider.unregister_plugin("video-editor-001")
```

---

### get_active_instance()

```python
def get_active_instance(self, plugin_type: str) -> Optional[str]
```

根据插件类型获取当前活跃的实例 ID。

**参数**:
- `plugin_type`: 插件类型

**返回**:
- 活跃实例 ID，如果不存在则返回 `None`

**示例**:
```python
active_id = provider.get_active_instance("VideoEditor")
```

---

### set_active_instance()

```python
def set_active_instance(self, instance_id: str) -> None
```

将某实例标记为当前活跃实例。

**参数**:
- `instance_id`: 插件实例的唯一标识符

**异常**:
- `DataProviderError`: 插件不存在时抛出

**注意**: 同一插件类型只能有一个活跃实例，设置新活跃实例会自动将同类型的其他实例标记为非活跃。

**示例**:
```python
provider.set_active_instance("video-editor-001")
```

---

## 5. 数据访问方法

### get_plugin_data()

```python
def get_plugin_data(
    self,
    instance_id: str,
    key: str,
    namespace: DataNamespace = DataNamespace.PRIVATE,
    default: Any = None
) -> Any
```

获取插件数据。

**参数**:
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `namespace`: 命名空间（`PRIVATE` 或 `PUBLIC`）
- `default`: 默认值，如果键不存在则返回该值

**返回**:
- 数据值

**异常**:
- `DataProviderError`: 插件不存在时抛出

**示例**:
```python
# 获取私有数据
project_name = provider.get_plugin_data(
    "plugin-id",
    "project_name",
    DataNamespace.PRIVATE
)

# 获取公共数据，带默认值
duration = provider.get_plugin_data(
    "plugin-id",
    "duration",
    DataNamespace.PUBLIC,
    0
)
```

---

### set_plugin_data()

```python
def set_plugin_data(
    self,
    instance_id: str,
    key: str,
    value: Any,
    namespace: DataNamespace = DataNamespace.PRIVATE,
    notify: bool = True
) -> None
```

设置插件数据。

**参数**:
- `instance_id`: 插件实例 ID
- `key`: 数据键
- `value`: 数据值
- `namespace`: 命名空间
- `notify`: 是否通知订阅者（仅对 `PUBLIC` 数据有效）

**异常**:
- `DataProviderError`: 插件不存在时抛出

**注意**: 当 `namespace` 为 `PUBLIC` 且 `notify=True` 时，会自动触发订阅者的回调函数。

**示例**:
```python
# 设置私有数据（不会通知）
provider.set_plugin_data(
    "plugin-id",
    "config",
    {"theme": "dark"},
    DataNamespace.PRIVATE
)

# 设置公共数据（会通知订阅者）
provider.set_plugin_data(
    "plugin-id",
    "status",
    "ready",
    DataNamespace.PUBLIC
)

# 设置公共数据但不通知
provider.set_plugin_data(
    "plugin-id",
    "status",
    "ready",
    DataNamespace.PUBLIC,
    notify=False
)
```

---

### get_all_plugin_data()

```python
def get_all_plugin_data(
    self,
    instance_id: str,
    namespace: DataNamespace = DataNamespace.PRIVATE
) -> Dict[str, Any]
```

获取插件的所有数据（指定命名空间）。

**参数**:
- `instance_id`: 插件实例 ID
- `namespace`: 命名空间

**返回**:
- 数据字典的副本

**示例**:
```python
public_data = provider.get_all_plugin_data("plugin-id", DataNamespace.PUBLIC)
```

---

## 6. 发布/订阅方法

### subscribe()

```python
def subscribe(
    self,
    subscriber_id: str,
    target_plugin_id: str,
    target_key: str,
    callback: Callable[[str, str, Any, Any], None]
) -> None
```

订阅其他插件的 `PUBLIC` 数据变化。

**参数**:
- `subscriber_id`: 订阅者插件 ID
- `target_plugin_id`: 目标插件 ID
- `target_key`: 要订阅的数据键
- `callback`: 回调函数，签名为 `callback(target_plugin_id, key, old_value, new_value)`

**异常**:
- `DataProviderError`: 目标插件不存在时抛出

**注意**: 系统不阻止订阅任意 key，仅在 `notify=True` 且 `namespace=PUBLIC` 时才会触发回调通知。

**示例**:
```python
def on_duration_change(plugin_id, key, old_value, new_value):
    print(f"视频时长从 {old_value} 变为 {new_value}")

provider.subscribe(
    subscriber_id="exporter-plugin",
    target_plugin_id="video-editor",
    target_key="video_duration",
    callback=on_duration_change
)
```

---

### unsubscribe()

```python
def unsubscribe(
    self,
    subscriber_id: str,
    target_plugin_id: Optional[str] = None
) -> None
```

取消订阅。

**参数**:
- `subscriber_id`: 订阅者插件 ID
- `target_plugin_id`: 可选，目标插件 ID。如果为 `None`，则取消该订阅者的所有订阅

**示例**:
```python
# 取消对特定插件的所有订阅
provider.unsubscribe("my-plugin-id", "target-plugin-id")

# 取消该订阅者的所有订阅
provider.unsubscribe("my-plugin-id")
```

---

### publish()

```python
def publish(
    self,
    publisher_id: str,
    key: str,
    value: Any,
    namespace: DataNamespace = DataNamespace.PUBLIC
) -> None
```

发布数据更新（等同于 `set_plugin_data` 的别名）。

**参数**:
- `publisher_id`: 发布者插件 ID
- `key`: 数据键
- `value`: 数据值
- `namespace`: 命名空间（默认为 `PUBLIC`）

**示例**:
```python
provider.publish("video-editor", "video_duration", 180)
```

---

## 7. 资源文件管理方法

### save_asset()

```python
def save_asset(
    self,
    plugin_id: str,
    filename: str,
    content: bytes
) -> str
```

保存资源文件。

**参数**:
- `plugin_id`: 插件 ID
- `filename`: 文件名
- `content`: 文件内容（bytes）

**返回**:
- 相对路径（相对于 assets 目录）

**异常**:
- `DataProviderError`: 保存失败时抛出

**示例**:
```python
with open("thumbnail.png", "rb") as f:
    content = f.read()

relative_path = provider.save_asset("video-editor", "thumbnail.png", content)
```

---

### get_asset_path()

```python
def get_asset_path(self, relative_path: str) -> str
```

将相对路径转换为绝对路径。

**参数**:
- `relative_path`: 相对路径（例如：`assets/plugins/plugin_id/filename.ext`）

**返回**:
- 绝对路径

**异常**:
- `DataProviderError`: 路径无效、文件不存在或读取失败时抛出

**注意**: 会检查路径是否包含危险的路径遍历（如 `..`）。其他异常也会被统一包装为 `DataProviderError` 后抛出。

**示例**:
```python
absolute_path = provider.get_asset_path("assets/plugins/video-editor/thumbnail.png")
```

---

### load_asset()

```python
def load_asset(self, relative_path: str) -> bytes
```

加载资源文件内容。

**参数**:
- `relative_path`: 相对路径

**返回**:
- 文件内容（bytes）

**异常**:
- `DataProviderError`: 加载失败时抛出

**示例**:
```python
content = provider.load_asset("assets/plugins/video-editor/thumbnail.png")
```

---

### get_plugin_assets_dir()

```python
def get_plugin_assets_dir(self, plugin_id: str) -> str
```

获取插件的资源目录路径。

**参数**:
- `plugin_id`: 插件 ID

**返回**:
- 资源目录的绝对路径

**注意**: 如果目录不存在，会自动创建。

**示例**:
```python
assets_dir = provider.get_plugin_assets_dir("video-editor")
```

---

## 8. 工具方法

### load_data()

```python
def load_data(self, force_reload: bool = False) -> Dict[str, Any]
```

从 SQLite 重建完整数据字典（包含 `plugins` 和 `active_instances`）。

**参数**:
- `force_reload`: 是否强制重新加载，忽略 `_cache`

**返回**:
- 数据字典的深拷贝

**说明**:
- 首次调用或 `force_reload=True` 时，从 `plugins`、`plugin_data`、`active_instances` 三张表全量读取并组装为与旧 JSON 结构一致的字典。
- 反序列化结果会同时填充 `_cache` 与 LRU 缓存，供后续 `get_plugin_data` 使用。
- 返回值是深拷贝，外部修改不会影响内部缓存或数据库。

**示例**:
```python
data = provider.load_data()
```

---

### save_data()

```python
def save_data(self) -> None
```

将当前 `_cache` 中的完整数据字典同步到 SQLite。

**异常**:
- `DataProviderError`: `_cache` 为空或保存失败时抛出

**说明**:
- 在一个 SQLite 事务中先清空 `plugin_data`、`active_instances`、`plugins`，再按 `_cache` 内容重新插入。
- 执行后清空 LRU 缓存，确保缓存与数据库一致。
- 该路径在正常使用中频率极低；日常写操作由 `set_plugin_data` 通过点写完成。

**示例**:
```python
provider.save_data()
```

---

### clear_cache()

```python
def clear_cache(self) -> None
```

清除缓存，下次读取时将重新从磁盘加载。

**示例**:
```python
provider.clear_cache()
```

---

### get_all_plugins()

```python
def get_all_plugins(self) -> Dict[str, Dict[str, Any]]
```

获取所有插件信息。

**返回**:
- 插件信息字典 `{instance_id: {type, active, private, public}}`

**示例**:
```python
plugins = provider.get_all_plugins()
```

---

### get_plugin_info()

```python
def get_plugin_info(self, instance_id: str) -> Optional[Dict[str, Any]]
```

获取指定插件的信息。

**参数**:
- `instance_id`: 插件实例 ID

**返回**:
- 插件信息字典，如果不存在则返回 `None`

**示例**:
```python
info = provider.get_plugin_info("video-editor-001")
```

---

### reset_all_data()

```python
def reset_all_data(self) -> None
```

重置所有数据（**慎用！**）

**警告**: 此操作会删除所有插件数据和订阅关系，不可恢复！

> **注意**：此方法是 `IDataProvider` 接口契约的一部分，由 `DataProvider` 实现类提供。

**示例**:
```python
provider.reset_all_data()
```

---

## 9. 完整示例

```python
from core.data.data_provider import DataProvider, DataNamespace

# 获取 DataProvider 实例
provider = DataProvider()

# ==================== 插件注册 ====================
video_editor_id = "video-editor-001"
provider.register_plugin(video_editor_id, "VideoEditor")
provider.set_active_instance(video_editor_id)

# ==================== 数据操作 ====================
# 私有数据
provider.set_plugin_data(video_editor_id, "project_name", "My Video", DataNamespace.PRIVATE)

# 公共数据
provider.set_plugin_data(video_editor_id, "video_duration", 120, DataNamespace.PUBLIC)
provider.set_plugin_data(video_editor_id, "frame_rate", 30, DataNamespace.PUBLIC)

# ==================== 发布/订阅 ====================
def on_video_change(plugin_id, key, old_value, new_value):
    print(f"视频 {key} 变更: {old_value} -> {new_value}")

provider.subscribe("exporter-001", video_editor_id, "video_duration", on_video_change)

# 发布变更
provider.publish(video_editor_id, "video_duration", 150)

# ==================== 资源管理 ====================
thumbnail = b"fake image data"
thumb_path = provider.save_asset(video_editor_id, "thumbnail.png", thumbnail)
print(f"已保存到: {thumb_path}")
```

---

## 10. 相关文档

- [DataProvider 概述](overview.md)
- [插件开发指南](../plugin-system/plugin-development.md)
