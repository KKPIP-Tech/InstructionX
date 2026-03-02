# DataProvider 使用指南

## 概述

`DataProvider` 是插件式桌面应用程序的核心数据中枢和 API 网关，负责为所有插件提供统一的数据管理服务。它实现了数据持久化、缓存管理、插件注册、发布/订阅通信和资源文件管理等功能。

### 核心特性

- **单例模式**：全局唯一实例，确保数据一致性
- **线程安全**：使用可重入锁（RLock）保证多线程环境下的安全性
- **原子写入**：采用临时文件 + 原子重命名机制，防止数据损坏
- **内存缓存**：减少磁盘 I/O，提升性能
- **命名空间隔离**：严格区分私有数据和公共数据
- **发布/订阅模式**：支持插件间的实时数据通信
- **资源管理**：统一的插件资源文件存储和管理

---

## 架构设计

### 数据结构

```json
{
  "plugins": {
    "plugin_id": {
      "type": "PluginType",
      "active": true,
      "private": { "key": "value" },
      "public": { "key": "value" }
    }
  },
  "active_instances": {
    "PluginType": "plugin_id"
  }
}
```

### 文件组织

```
data/
├── data.json              # 主数据文件
├── data.json.tmp          # 临时文件（用于原子写入）
└── assets/
    └── plugins/
        ├── plugin_id_1/
        │   └── file.ext
        └── plugin_id_2/
            └── file.ext
```

---

## 快速开始

### 基本使用

```python
from core.data.data_provider import DataProvider, DataNamespace

# 获取单例实例
provider = DataProvider()

# 注册插件
provider.register_plugin("my-plugin-id", "MyPluginType")

# 设置私有数据
provider.set_plugin_data("my-plugin-id", "internal_key", "value", DataNamespace.PRIVATE)

# 设置公共数据（可被其他插件订阅）
provider.set_plugin_data("my-plugin-id", "shared_key", "value", DataNamespace.PUBLIC)

# 读取数据
value = provider.get_plugin_data("my-plugin-id", "shared_key", DataNamespace.PUBLIC)
```

### 发布/订阅通信

```python
# 定义回调函数
def on_data_change(target_plugin_id: str, key: str, old_value: Any, new_value: Any):
    print(f"数据变更: {key} 从 {old_value} 变为 {new_value}")

# 订阅其他插件的数据
provider.subscribe(
    subscriber_id="my-plugin-id",
    target_plugin_id="other-plugin-id",
    target_key="video_duration",
    callback=on_data_change
)

# 发布数据变更（会触发订阅者的回调）
provider.publish("other-plugin-id", "video_duration", 150)
```

### 资源文件管理

```python
# 保存资源文件
content = b"binary file content"
relative_path = provider.save_asset("my-plugin-id", "thumbnail.png", content)

# 获取绝对路径
absolute_path = provider.get_asset_path(relative_path)

# 加载资源文件
loaded_content = provider.load_asset(relative_path)
```

---

## API 参考

### 类：DataProvider

#### 构造函数

```python
DataProvider(data_dir: Optional[str] = None, data_filename: str = "data.json")
```

**参数：**
- `data_dir`：数据文件存储目录，默认为项目根目录下的 `data` 文件夹
- `data_filename`：数据文件名，默认为 `data.json`

**示例：**
```python
# 使用默认路径
provider = DataProvider()

# 自定义路径
provider = DataProvider(data_dir="/custom/path", data_filename="my_data.json")
```

---

### 插件管理方法

#### register_plugin

注册插件实例。

```python
register_plugin(instance_id: str, plugin_type: str) -> None
```

**参数：**
- `instance_id`：插件实例的唯一标识符
- `plugin_type`：插件类型（如 "VideoEditor"、"Exporter"）

**异常：**
- `DataProviderError`：插件已存在时抛出

**示例：**
```python
provider.register_plugin("video-editor-001", "VideoEditor")
```

---

#### unregister_plugin

注销插件实例。

```python
unregister_plugin(instance_id: str) -> None
```

**参数：**
- `instance_id`：插件实例的唯一标识符

**异常：**
- `DataProviderError`：插件不存在时抛出

**注意：** 注销插件时会自动清理相关的订阅关系。

**示例：**
```python
provider.unregister_plugin("video-editor-001")
```

---

#### get_active_instance

根据插件类型获取当前活跃的实例 ID。

```python
get_active_instance(plugin_type: str) -> Optional[str]
```

**参数：**
- `plugin_type`：插件类型

**返回：**
- 活跃实例 ID，如果不存在则返回 `None`

**示例：**
```python
active_id = provider.get_active_instance("VideoEditor")
if active_id:
    print(f"当前活跃的视频编辑器: {active_id}")
```

---

#### set_active_instance

将某实例标记为当前活跃实例。

```python
set_active_instance(instance_id: str) -> None
```

**参数：**
- `instance_id`：插件实例的唯一标识符

**异常：**
- `DataProviderError`：插件不存在时抛出

**注意：** 同一插件类型只能有一个活跃实例，设置新活跃实例会自动将同类型的其他实例标记为非活跃。

**示例：**
```python
provider.set_active_instance("video-editor-001")
```

---

### 数据访问方法

#### get_plugin_data

获取插件数据。

```python
get_plugin_data(
    instance_id: str,
    key: str,
    namespace: DataNamespace = DataNamespace.PRIVATE,
    default: Any = None
) -> Any
```

**参数：**
- `instance_id`：插件实例 ID
- `key`：数据键
- `namespace`：命名空间（`DataNamespace.PRIVATE` 或 `DataNamespace.PUBLIC`）
- `default`：默认值，如果键不存在则返回该值

**返回：**
- 数据值

**异常：**
- `DataProviderError`：插件不存在时抛出

**示例：**
```python
# 获取私有数据
project_name = provider.get_plugin_data("plugin-id", "project_name", DataNamespace.PRIVATE)

# 获取公共数据，带默认值
duration = provider.get_plugin_data("plugin-id", "duration", DataNamespace.PUBLIC, 0)
```

---

#### set_plugin_data

设置插件数据。

```python
set_plugin_data(
    instance_id: str,
    key: str,
    value: Any,
    namespace: DataNamespace = DataNamespace.PRIVATE,
    notify: bool = True
) -> None
```

**参数：**
- `instance_id`：插件实例 ID
- `key`：数据键
- `value`：数据值
- `namespace`：命名空间
- `notify`：是否通知订阅者（仅对 public 数据有效）

**异常：**
- `DataProviderError`：插件不存在时抛出

**注意：** 当 `namespace` 为 `PUBLIC` 且 `notify=True` 时，会自动触发订阅者的回调函数。

**示例：**
```python
# 设置私有数据（不会通知）
provider.set_plugin_data("plugin-id", "config", {"theme": "dark"}, DataNamespace.PRIVATE)

# 设置公共数据（会通知订阅者）
provider.set_plugin_data("plugin-id", "status", "ready", DataNamespace.PUBLIC)

# 设置公共数据但不通知
provider.set_plugin_data("plugin-id", "status", "ready", DataNamespace.PUBLIC, notify=False)
```

---

#### get_all_plugin_data

获取插件的所有数据（指定命名空间）。

```python
get_all_plugin_data(
    instance_id: str,
    namespace: DataNamespace = DataNamespace.PRIVATE
) -> Dict[str, Any]
```

**参数：**
- `instance_id`：插件实例 ID
- `namespace`：命名空间

**返回：**
- 数据字典的副本

**示例：**
```python
public_data = provider.get_all_plugin_data("plugin-id", DataNamespace.PUBLIC)
print(public_data)
```

---

### 发布/订阅方法

#### subscribe

订阅其他插件的 public 数据变化。

```python
subscribe(
    subscriber_id: str,
    target_plugin_id: str,
    target_key: str,
    callback: Callable[[str, str, Any, Any], None]
) -> None
```

**参数：**
- `subscriber_id`：订阅者插件 ID
- `target_plugin_id`：目标插件 ID
- `target_key`：要订阅的数据键
- `callback`：回调函数，签名为 `callback(target_plugin_id, key, old_value, new_value)`

**异常：**
- `DataProviderError`：目标插件不存在时抛出

**示例：**
```python
def on_duration_change(target_plugin_id, key, old_value, new_value):
    print(f"视频时长从 {old_value} 秒变为 {new_value} 秒")

provider.subscribe(
    subscriber_id="exporter-plugin",
    target_plugin_id="video-editor",
    target_key="video_duration",
    callback=on_duration_change
)
```

---

#### unsubscribe

取消订阅。

```python
unsubscribe(subscriber_id: str, target_plugin_id: Optional[str] = None) -> None
```

**参数：**
- `subscriber_id`：订阅者插件 ID
- `target_plugin_id`：可选，目标插件 ID。如果为 `None`，则取消该订阅者的所有订阅

**示例：**
```python
# 取消对特定插件的所有订阅
provider.unsubscribe("my-plugin-id", "target-plugin-id")

# 取消该订阅者的所有订阅
provider.unsubscribe("my-plugin-id")
```

---

#### publish

发布数据更新（等同于 `set_plugin_data` 的别名）。

```python
publish(
    publisher_id: str,
    key: str,
    value: Any,
    namespace: DataNamespace = DataNamespace.PUBLIC
) -> None
```

**参数：**
- `publisher_id`：发布者插件 ID
- `key`：数据键
- `value`：数据值
- `namespace`：命名空间（默认为 public）

**示例：**
```python
# 发布公共数据更新
provider.publish("video-editor", "video_duration", 180)
```

---

### 资源文件管理方法

#### save_asset

保存资源文件。

```python
save_asset(
    plugin_id: str,
    filename: str,
    content: bytes
) -> str
```

**参数：**
- `plugin_id`：插件 ID
- `filename`：文件名
- `content`：文件内容（bytes）

**返回：**
- 相对路径（相对于 assets 目录）

**异常：**
- `DataProviderError`：保存失败时抛出

**示例：**
```python
# 保存图片
with open("thumbnail.png", "rb") as f:
    content = f.read()

relative_path = provider.save_asset("video-editor", "thumbnail.png", content)
print(f"已保存到: {relative_path}")
```

---

#### get_asset_path

将相对路径转换为绝对路径。

```python
get_asset_path(relative_path: str) -> str
```

**参数：**
- `relative_path`：相对路径（例如：`assets/plugins/plugin_id/filename.ext`）

**返回：**
- 绝对路径

**异常：**
- `DataProviderError`：路径无效或文件不存在时抛出

**注意：** 会检查路径是否包含危险的路径遍历（如 `..`）。

**示例：**
```python
absolute_path = provider.get_asset_path("assets/plugins/video-editor/thumbnail.png")
print(f"绝对路径: {absolute_path}")
```

---

#### load_asset

加载资源文件内容。

```python
load_asset(relative_path: str) -> bytes
```

**参数：**
- `relative_path`：相对路径

**返回：**
- 文件内容（bytes）

**异常：**
- `DataProviderError`：加载失败时抛出

**示例：**
```python
content = provider.load_asset("assets/plugins/video-editor/thumbnail.png")
# 处理二进制内容...
```

---

#### get_plugin_assets_dir

获取插件的资源目录路径。

```python
get_plugin_assets_dir(plugin_id: str) -> str
```

**参数：**
- `plugin_id`：插件 ID

**返回：**
- 资源目录的绝对路径

**注意：** 如果目录不存在，会自动创建。

**示例：**
```python
assets_dir = provider.get_plugin_assets_dir("video-editor")
print(f"插件资源目录: {assets_dir}")
```

---

### 工具方法

#### load_data

从磁盘加载数据到缓存。

```python
load_data(force_reload: bool = False) -> Dict[str, Any]
```

**参数：**
- `force_reload`：是否强制重新加载，忽略缓存

**返回：**
- 数据字典

**示例：**
```python
data = provider.load_data()
print(data["plugins"])
```

---

#### save_data

将当前缓存数据保存到磁盘。

```python
save_data() -> None
```

**异常：**
- `DataProviderError`：保存失败时抛出

**示例：**
```python
provider.save_data()
```

---

#### clear_cache

清除缓存，下次读取时将重新从磁盘加载。

```python
clear_cache() -> None
```

**示例：**
```python
provider.clear_cache()
```

---

#### get_all_plugins

获取所有插件信息。

```python
get_all_plugins() -> Dict[str, Dict[str, Any]]
```

**返回：**
- 插件信息字典 `{instance_id: {type, active, private, public}}`

**示例：**
```python
plugins = provider.get_all_plugins()
for pid, info in plugins.items():
    print(f"插件 {pid} (类型: {info['type']}, 活跃: {info['active']})")
```

---

#### get_plugin_info

获取指定插件的信息。

```python
get_plugin_info(instance_id: str) -> Optional[Dict[str, Any]]
```

**参数：**
- `instance_id`：插件实例 ID

**返回：**
- 插件信息字典，如果不存在则返回 `None`

**示例：**
```python
info = provider.get_plugin_info("video-editor-001")
if info:
    print(f"插件类型: {info['type']}")
    print(f"公共数据: {info['public']}")
```

---

#### reset_all_data

重置所有数据（慎用！）。

```python
reset_all_data() -> None
```

**警告：** 此操作会删除所有插件数据和订阅关系，不可恢复！

**示例：**
```python
provider.reset_all_data()
```

---

## 完整示例

### 示例 1：视频编辑器与导出器插件

```python
from core.data.data_provider import DataProvider, DataNamespace

# 获取 DataProvider 实例
provider = DataProvider()

# ==================== 视频编辑器插件 ====================
video_editor_id = "video-editor-001"
provider.register_plugin(video_editor_id, "VideoEditor")
provider.set_active_instance(video_editor_id)

# 存储私有配置
provider.set_plugin_data(video_editor_id, "project_name", "My Video", DataNamespace.PRIVATE)
provider.set_plugin_data(video_editor_id, "resolution", "1920x1080", DataNamespace.PRIVATE)

# 存储公共数据（供其他插件使用）
provider.set_plugin_data(video_editor_id, "video_duration", 120, DataNamespace.PUBLIC)
provider.set_plugin_data(video_editor_id, "frame_rate", 30, DataNamespace.PUBLIC)

# ==================== 导出器插件 ====================
exporter_id = "exporter-001"
provider.register_plugin(exporter_id, "Exporter")

# 定义回调函数
def on_video_data_change(target_plugin_id, key, old_value, new_value):
    print(f"[导出器] 注意到视频编辑器的 {key} 变更: {old_value} -> {new_value}")
    # 可以在这里触发导出操作...

# 订阅视频编辑器的数据变化
provider.subscribe(exporter_id, video_editor_id, "video_duration", on_video_data_change)
provider.subscribe(exporter_id, video_editor_id, "frame_rate", on_video_data_change)

# ==================== 模拟数据变更 ====================
print("修改视频时长...")
provider.publish(video_editor_id, "video_duration", 150)  # 会触发回调

print("\n修改帧率...")
provider.publish(video_editor_id, "frame_rate", 60)  # 会触发回调

# ==================== 资源文件管理 ====================
# 保存缩略图
thumbnail = b"fake thumbnail image data"
thumb_path = provider.save_asset(video_editor_id, "thumbnail.png", thumbnail)
print(f"\n缩略图已保存到: {thumb_path}")

# ==================== 查询数据 ====================
print(f"\n当前视频时长: {provider.get_plugin_data(video_editor_id, 'video_duration', DataNamespace.PUBLIC)} 秒")
print(f"当前帧率: {provider.get_plugin_data(video_editor_id, 'frame_rate', DataNamespace.PUBLIC)} fps")
```

---

## 最佳实践

### 1. 命名空间使用

- **私有数据（PRIVATE）**：用于插件内部配置、临时数据、状态信息等
- **公共数据（PUBLIC）**：用于需要与其他插件共享的关键数据、事件、状态变化等

```python
# ✅ 推荐
provider.set_plugin_data("plugin-id", "internal_config", {...}, DataNamespace.PRIVATE)
provider.set_plugin_data("plugin-id", "current_status", "ready", DataNamespace.PUBLIC)

# ❌ 避免将敏感数据放入公共命名空间
provider.set_plugin_data("plugin-id", "api_key", "secret-key", DataNamespace.PUBLIC)
```

### 2. 发布/订阅模式

- 回调函数应该快速执行，避免阻塞
- 在回调中处理异常，防止影响其他订阅者
- 不再需要订阅时及时取消订阅

```python
def on_data_change(target_plugin_id, key, old_value, new_value):
    try:
        # 快速处理
        print(f"数据变更: {key}")
        # 触发轻量级操作
    except Exception as e:
        print(f"处理回调时出错: {e}")

# 使用完毕后取消订阅
try:
    provider.subscribe("my-id", "target-id", "key", on_data_change)
    # ... 使用 ...
finally:
    provider.unsubscribe("my-id")
```

### 3. 资源文件管理

- 使用有意义的文件名，避免冲突
- 及时清理不再需要的资源文件
- 考虑资源文件的版本管理

```python
# ✅ 推荐：使用时间戳或版本号
filename = f"thumbnail_{timestamp}.png"
path = provider.save_asset("plugin-id", filename, content)

# ❌ 避免：固定文件名可能被覆盖
path = provider.save_asset("plugin-id", "thumbnail.png", content)
```

### 4. 性能优化

- 合理使用缓存，频繁读取的数据会自动缓存
- 批量更新时可以暂时禁用通知

```python
# 批量更新，避免频繁通知
data = provider.load_data()
data["plugins"]["plugin-id"]["public"]["key1"] = value1
data["plugins"]["plugin-id"]["public"]["key2"] = value2
data["plugins"]["plugin-id"]["public"]["key3"] = value3

# 最后一次性保存
provider._cache = data
provider.save_data()

# 手动通知（如果需要）
provider._notify_subscribers("plugin-id", "key1", old_value1, value1)
# ...
```

### 5. 错误处理

- 始终捕获 `DataProviderError`
- 提供有意义的错误消息
- 考虑重试机制（对于文件 I/O 操作）

```python
from core.data.data_provider import DataProvider, DataProviderError

provider = DataProvider()

try:
    provider.register_plugin("plugin-id", "PluginType")
except DataProviderError as e:
    print(f"注册插件失败: {e}")
    # 处理错误...
```

---

## 注意事项

### 线程安全

`DataProvider` 使用 `RLock`（可重入锁）保证线程安全，但在多线程环境中仍需注意：

- 避免在回调函数中持有 DataProvider 锁
- 长时间运行的操作应在回调外执行
- 注意潜在的死锁风险

### 数据一致性

- 数据持久化是异步的，调用 `save_data()` 确保数据写入磁盘
- 程序异常退出时，原子写入机制能保证数据文件不损坏
- 但最后一次未保存的缓存数据可能丢失

### 内存管理

- 缓存会占用内存，频繁读写大文件时注意内存使用
- 可以定期调用 `clear_cache()` 释放内存
- 插件数量过多时考虑分批处理

### 安全性

- 公共数据可以被任何插件读取，避免存储敏感信息
- 资源文件路径已做安全检查，但仍需验证文件内容
- 考虑实现插件权限管理（如需要）

---

## 故障排查

### 问题：插件注册失败

**原因：** 插件 ID 已存在

**解决：** 检查插件 ID 是否重复，或先注销旧插件

```python
try:
    provider.register_plugin("plugin-id", "Type")
except DataProviderError as e:
    print(f"错误: {e}")
    if "已存在" in str(e):
        provider.unregister_plugin("plugin-id")
        provider.register_plugin("plugin-id", "Type")
```

### 问题：数据未持久化

**原因：** 只修改了缓存，未调用 `save_data()`

**解决：** 显式调用保存方法

```python
provider.set_plugin_data("plugin-id", "key", "value")
provider.save_data()  # 确保数据写入磁盘
```

### 问题：回调未被触发

**原因：**
1. 订阅的键不匹配
2. 数据设置时 `notify=False`
3. 私有数据变化不会触发通知

**解决：**
```python
# 检查订阅
provider.subscribe("subscriber", "target", "key", callback)

# 确保是公共数据且启用通知
provider.set_plugin_data("target", "key", "value", DataNamespace.PUBLIC, notify=True)
```

### 问题：资源文件无法加载

**原因：**
1. 文件不存在
2. 相对路径错误
3. 文件权限问题

**解决：**
```python
try:
    content = provider.load_asset("assets/plugins/plugin-id/file.png")
except DataProviderError as e:
    print(f"加载失败: {e}")
    # 检查文件是否存在、路径是否正确
```

---

## 常见问题（FAQ）

**Q: DataProvider 是单例，如何在不同模块中使用？**

A: 直接实例化即可，会返回同一个实例：

```python
# 模块 A
from core.data.data_provider import DataProvider
provider1 = DataProvider()

# 模块 B
from core.data.data_provider import DataProvider
provider2 = DataProvider()

# provider1 和 provider2 是同一个对象
assert provider1 is provider2
```

**Q: 如何实现插件间的复杂通信？**

A: 除了发布/订阅模式，还可以：
1. 使用结构化的公共数据
2. 在回调中传递额外上下文信息
3. 结合事件总线模式（在应用层实现）

**Q: 可以直接修改 `data.json` 文件吗？**

A: 不建议直接修改，因为：
1. 可能导致缓存不一致
2. 程序运行时修改可能被覆盖
3. 原子写入机制会被破坏

**Q: 如何备份和恢复数据？**

A: 直接复制 `data.json` 文件：

```python
import shutil
from pathlib import Path

# 备份
shutil.copy("data/data.json", "data/data.json.backup")

# 恢复
shutil.copy("data/data.json.backup", "data/data.json")
# 清除缓存使更改生效
DataProvider().clear_cache()
```

**Q: 支持数据迁移和版本升级吗？**

A: DataProvider 本身不提供迁移功能，建议：
1. 在应用层实现数据迁移逻辑
2. 在 `load_data()` 后检查数据版本
3. 按需执行迁移脚本

---

## 扩展阅读

- [PLUGIN_DESIGN.md](PLUGIN_DESIGN.md) - 插件架构设计文档
- [SKILLS_PANEL_GUIDE.md](SKILLS_PANEL_GUIDE.md) - 技能面板使用指南

---

## 版本历史

- **v1.0.0** (2026-03-01)
  - 初始版本
  - 实现核心数据管理功能
  - 支持发布/订阅模式
  - 资源文件管理

---

## 许可证

本项目遵循主项目的许可证。