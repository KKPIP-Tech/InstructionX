# DataProvider 数据层

> 数据提供者的架构设计和核心概念

---

## 1. 概述

`DataProvider` 是 InstructionX 项目的核心数据组件，负责插件数据的持久化、缓存管理、插件注册、发布/订阅通信和资源文件管理。

**文件位置**: `core/data/data_provider.py`

**模式**: 单例模式（全局唯一实例）

---

## 2. 核心特性

| 特性 | 说明 |
|------|------|
| **单例模式** | 全局唯一实例，确保数据一致性 |
| **线程安全** | 使用 RLock（可重入锁）保证多线程安全 |
| **原子写入** | 临时文件 + 原子重命名，防止数据损坏 |
| **内存缓存** | 减少磁盘 I/O，提升性能 |
| **命名空间隔离** | 严格区分私有数据和公共数据 |
| **发布/订阅** | 支持插件间的实时数据通信 |
| **资源管理** | 统一的插件资源文件存储 |
| **插件实例管理** | 支持多实例注册、活跃实例切换、插件注销 |
| **重置机制** | `reset_all_data()` 支持清空所有数据（实现层扩展方法，非 `IDataProvider` 接口契约） |

---

## 3. 架构图

```mermaid
graph TB
    subgraph DP["DataProvider 单例"]
        Cache["内存缓存<br/>_cache"]
        Subs["订阅管理器<br/>_subscriptions"]
    end

    subgraph Plugins["插件"]
        PA["插件 A<br/>PRIVATE 数据"]
        PB["插件 B<br/>订阅者"]
        PC["插件 C<br/>PUBLIC 数据"]
    end

    subgraph Storage["持久化层"]
        JSON["data/data.json<br/>原子写入"]
    end

    DP -->|读写数据| PA
    DP -->|读写数据| PB
    DP -->|读写数据| PC
    PB -->|subscribe| DP
    PC -->|publish| DP
    DP -->|保存| JSON
```

---

## 4. 数据命名空间

### 4.1 命名空间类型

```python
class DataNamespace(Enum):
    """数据命名空间枚举"""
    PRIVATE = "private"  # 仅插件内部使用
    PUBLIC = "public"    # 允许其他插件访问
```

### 4.2 PRIVATE（私有数据）

- **用途**: 插件内部配置、临时数据、状态信息
- **访问**: 仅插件自身可以读写
- **示例**:
  ```python
  # 保存私有配置
  provider.set_plugin_data(
      plugin_id,
      "internal_config",
      {"theme": "dark"},
      DataNamespace.PRIVATE
  )
  ```

### 4.3 PUBLIC（公共数据）

- **用途**: 需要与其他插件共享的数据、事件、状态变化
- **访问**: 所有插件可以读取
- **订阅**: 其他插件可以订阅数据变化
- **示例**:
  ```python
  # 保存公共数据
  provider.set_plugin_data(
      plugin_id,
      "current_status",
      "ready",
      DataNamespace.PUBLIC
  )
  ```

---

## 5. 发布/订阅模式

### 5.1 原理

```mermaid
sequenceDiagram
    participant A as 插件 A (发布者)
    participant DP as DataProvider
    participant B as 插件 B (订阅者)

    B->>DP: subscribe()
    DP-->>B: 订阅成功

    A->>DP: set_plugin_data(PUBLIC)
    DP->>DP: 更新缓存
    DP->>DP: 保存到磁盘
    DP->>DP: 通知订阅者
    DP-->>B: 回调函数
    B->>B: 处理变更
```

### 5.2 使用场景

| 场景 | 推荐方式 |
|------|---------|
| 事件通知 | 发布/订阅 |
| 状态变化 | 发布/订阅 |
| 功能调用 | API 调用 |

### 5.3 示例代码

**订阅者（插件 B）**:

```python
class SubscriberService:
    def __init__(self, plugin_id, data_provider):
        self.plugin_id = plugin_id
        self.data_provider = data_provider

    def subscribe_to_publisher(self, publisher_id):
        """订阅发布者的数据变化"""
        self.data_provider.subscribe(
            subscriber_id=self.plugin_id,
            target_plugin_id=publisher_id,
            target_key="status",
            callback=self._on_status_change
        )

    def _on_status_change(self, plugin_id, key, old_value, new_value):
        print(f"状态从 {old_value} 变为 {new_value}")
```

**发布者（插件 A）**:

```python
class PublisherService:
    def __init__(self, plugin_id, data_provider):
        self.plugin_id = plugin_id
        self.data_provider = data_provider

    def update_status(self, new_status):
        """更新状态（会自动通知订阅者）"""
        self.data_provider.set_plugin_data(
            self.plugin_id,
            "status",
            new_status,
            DataNamespace.PUBLIC
        )
```

---

## 6. 资源管理

### 6.1 资源目录结构

```
data/
├── data.json
├── data.json.tmp           # 临时文件（原子写入用）
└── assets/
    └── plugins/
        ├── plugin_uuid_1/
        │   ├── thumbnail.png
        │   └── config.json
        └── plugin_uuid_2/
            └── ...
```

### 6.2 资源 API

```python
# 保存资源
relative_path = provider.save_asset(
    plugin_id="plugin-uuid",
    filename="thumbnail.png",
    content=b"图片二进制数据"
)

# 获取绝对路径
absolute_path = provider.get_asset_path(relative_path)

# 加载资源
content = provider.load_asset(relative_path)

# 获取插件资源目录
assets_dir = provider.get_plugin_assets_dir("plugin-uuid")
```

---

## 7. 核心流程

### 7.1 数据读写流程

```mermaid
flowchart TD
    subgraph Read["读取数据"]
        R1[get_plugin_data] --> R2[load_data 加载缓存]
        R2 --> R3[返回缓存中的值]
    end

    subgraph Write["写入数据"]
        W1[set_plugin_data] --> W2[更新缓存]
        W2 --> W3[save_data 写入磁盘]
        W3 --> W4{PUBLIC & notify?}
        W4 -->|是| W5[_notify_subscribers 通知]
        W4 -->|否| W6[结束]
    end
```

### 7.2 原子写入机制

```python
def _write_to_disk(self, data):
    """原子写入数据到磁盘"""

    # 1. 写入临时文件
    with open(temp_file, 'w') as f:
        json.dump(data, f)

    # 2. 原子重命名（在 Windows 和 Unix 上都是原子操作）
    os.replace(temp_file, data_file)
```

---

## 8. 数据结构

### 8.1 data.json

```json
{
    "plugins": {
        "plugin-uuid-1": {
            "type": "TaskManager",
            "active": true,
            "private": {
                "config": {"theme": "dark"},
                "cache": []
            },
            "public": {
                "statistics": {"total": 10},
                "status": "ready"
            }
        }
    },
    "active_instances": {
        "TaskManager": "plugin-uuid-1"
    }
}
```

---

## 9. 线程安全

### 9.1 锁的使用

```python
class DataProvider:
    def __init__(self):
        # 可重入锁 - 同一线程可多次获取
        self._file_lock = threading.RLock()
        self._subscription_lock = threading.RLock()
```

### 9.2 注意事项

- 避免在回调函数中持有 DataProvider 锁
- 长时间运行的操作应在回调外执行
- 注意潜在的死锁风险

---

## 10. 相关文档

- [DataProvider API 参考](api-reference.md)
- [插件开发指南](../plugin-system/plugin-development.md)
- [系统架构概述](../../architecture/overview.md)

---

*本文档由 Claude Code 自动生成*
