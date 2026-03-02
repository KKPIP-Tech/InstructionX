# 任务管理器 & 任务报告生成器插件演示文档

## 概述

本文档演示如何使用两个互相协作的插件来展示 `DataProvider` 的所有核心功能。

**重要提示**:
- `.plugin_info.json` 配置文件由程序自动生成，无需手动创建
- 插件首次加载时，系统会自动扫描并生成该文件

### 插件介绍

#### 1. 任务管理器插件 (TaskManager)
- **功能**: 管理任务列表、跟踪任务状态、数据持久化
- **展示的 DataProvider 功能**:
  - ✅ 数据持久化（原子写入）
  - ✅ 命名空间隔离（private/public 数据）
  - ✅ 发布/订阅模式（发布事件）
  - ✅ 资源文件管理（保存导出文件）
  - ✅ 缓存机制
  - ✅ 线程安全

#### 2. 任务报告生成器插件 (TaskReporter)
- **功能**: 实时监控任务变更、生成统计报告、事件历史记录
- **展示的 DataProvider 功能**:
  - ✅ 订阅数据变更（观察者模式）
  - ✅ 跨插件数据访问
  - ✅ 资源文件管理（保存报告文件）
  - ✅ 缓存机制
  - ✅ 线程安全

## 数据流架构

```
┌─────────────────┐      publish       ┌─────────────────┐
│   TaskManager   │ ──────────────────▶│   DataProvider  │
│                 │  (public data)     │                 │
└─────────────────┘                    └────────┬────────┘
                                              │
                                              │ notify
                                              │
                                              ▼
                                     ┌─────────────────┐
                                     │   TaskReporter  │
                                     │   (subscriber)  │
                                     └─────────────────┘
```

## 演示步骤

### 步骤 1: 启动应用程序

```bash
python main.py
```

### 步骤 2: 打开任务管理器插件

1. 在技能面板中找到"任务管理器"插件
2. 点击打开插件界面

**此时 DataProvider 会自动执行**:
- 注册插件实例（`register_plugin`）
- 设置为活跃实例（`set_active_instance`）
- 创建私有数据空间存储任务列表
- 创建公共数据空间存储统计信息

### 步骤 3: 添加任务

1. 在任务管理器中点击"添加任务"按钮
2. 输入任务标题（例如："完成文档编写"）
3. 选择优先级（low/normal/high）
4. 点击确定

**DataProvider 执行的操作**:
```python
# 1. 使用原子写入保存任务到 private 数据
data_provider.set_plugin_data(
    plugin_id="task-manager-default",
    key="tasks",
    value=[...tasks...],
    namespace=DataNamespace.PRIVATE
)

# 2. 更新统计信息到 public 数据
data_provider.publish(
    publisher_id="task-manager-default",
    key="statistics",
    value={"total": 1, "pending": 1, ...},
    namespace=DataNamespace.PUBLIC
)

# 3. 发布任务添加事件
data_provider.publish(
    publisher_id="task-manager-default",
    key="last_event",
    value={"type": "task_added", "task_id": "..."},
    namespace=DataNamespace.PUBLIC
)
```

### 步骤 4: 打开任务报告生成器插件

1. 在技能面板中找到"任务报告"插件
2. 点击打开插件界面

### 步骤 5: 订阅任务管理器

1. 确认任务管理器插件ID为 `task-manager-default`
2. 点击"订阅"按钮

**DataProvider 执行的操作**:
```python
# 订阅统计信息变更
data_provider.subscribe(
    subscriber_id="task-reporter-default",
    target_plugin_id="task-manager-default",
    target_key="statistics",
    callback=_on_statistics_changed
)

# 订阅事件变更
data_provider.subscribe(
    subscriber_id="task-reporter-default",
    target_plugin_id="task-manager-default",
    target_key="last_event",
    callback=_on_task_event
)
```

### 步骤 6: 在任务管理器中添加更多任务

添加几个任务，例如：
- "代码审查"（high 优先级）
- "单元测试"（normal 优先级）
- "文档更新"（low 优先级）

**观察到的现象**:
- ✅ 任务报告生成器自动接收到统计信息更新
- ✅ 事件历史记录显示所有任务添加事件
- ✅ 统计报告实时更新（每3秒自动刷新）

### 步骤 7: 更新任务状态

1. 在任务管理器中选择一个任务
2. 点击"标记完成"按钮

**DataProvider 执行的操作**:
```python
# 1. 更新任务状态
task["status"] = "completed"
data_provider.set_plugin_data(..., DataNamespace.PRIVATE)

# 2. 发布统计信息更新
data_provider.publish(..., DataNamespace.PUBLIC)

# 3. 发布状态变更事件
data_provider.publish(
    key="last_event",
    value={"type": "status_changed", ...}
)
```

**观察到的现象**:
- ✅ 任务报告生成器接收到状态变更事件
- ✅ 统计信息中的"已完成"计数增加
- ✅ 完成率自动重新计算

### 步骤 8: 筛选和删除任务

1. 使用筛选功能查看特定状态的任务
2. 删除一些不需要的任务

**DataProvider 执行的操作**:
- 使用原子写入更新任务列表
- 发布删除事件通知订阅者
- 重新计算统计信息

### 步骤 9: 生成报告

1. 在任务报告生成器中选择报告格式（json/txt/html）
2. 点击"生成报告"按钮

**DataProvider 执行的操作**:
```python
# 保存报告文件到资源目录
path = data_provider.save_asset(
    plugin_id="task-reporter-default",
    filename="report_20260301_220000.json",
    content=report_bytes
)

# 文件保存位置: assets/plugins/task-reporter-default/report_*.json
```

**报告内容示例**:
```json
{
  "generated_at": "2026-03-01T22:00:00",
  "task_manager_id": "task-manager-default",
  "statistics_report": {
    "statistics": {
      "total": 5,
      "pending": 2,
      "in_progress": 1,
      "completed": 2,
      "cancelled": 0
    },
    "metrics": {
      "completion_rate": 40.0,
      "pending_ratio": 40.0,
      "in_progress_ratio": 20.0
    }
  },
  "recent_events": [...]
}
```

### 步骤 10: 导出任务数据

1. 在任务管理器中点击"导出任务"按钮
2. 查看导出的 JSON 文件

**DataProvider 执行的操作**:
- 读取所有任务数据（从缓存或磁盘）
- 生成 JSON 格式的导出文件
- 使用原子写入保存到资源目录

## DataProvider 核心功能验证清单

### ✅ 数据持久化 (data.json)

**验证方法**:
1. 添加几个任务
2. 关闭应用程序
3. 重新启动应用程序
4. 打开任务管理器，任务应该仍然存在

**技术细节**:
- 使用临时文件 (`data.tmp`) + `os.replace` 实现原子写入
- 防止程序崩溃时 JSON 文件损坏
- 自动创建 `data.json` 文件（如果不存在）

### ✅ 缓存机制

**验证方法**:
- 多次刷新任务列表，观察磁盘 I/O
- 数据在首次读取后被缓存
- 数据更新时缓存自动失效

**技术细节**:
- 使用 `dict` 实现内存缓存
- 缓存键: `(plugin_id, key, namespace)`
- 数据更新时清除相关缓存

### ✅ 命名空间隔离

**验证方法**:
- 任务管理器的 `private` 数据包含完整任务列表
- 任务管理器的 `public` 数据只包含统计信息
- 任务报告生成器无法访问任务管理器的 `private` 数据

**技术细节**:
```python
# 任务管理器存储完整任务列表（private）
data_provider.set_plugin_data(..., "tasks", [...], DataNamespace.PRIVATE)

# 任务管理器只发布统计信息（public）
data_provider.publish(..., "statistics", {...}, DataNamespace.PUBLIC)

# 任务报告生成器只能访问 public 数据
stats = data_provider.get_plugin_data(..., "statistics", DataNamespace.PUBLIC)
```

### ✅ 发布/订阅模式

**验证方法**:
- 任务报告生成器订阅任务管理器
- 在任务管理器中添加/更新/删除任务
- 任务报告生成器实时接收通知

**技术细节**:
```python
# 订阅
data_provider.subscribe(subscriber_id, target_plugin_id, target_key, callback)

# 发布
data_provider.publish(publisher_id, key, value, namespace)

# 自动触发所有订阅者的回调函数
```

### ✅ 资源文件管理

**验证方法**:
- 生成报告文件（保存到 `assets/plugins/task-reporter-default/`）
- 导出任务数据（保存到 `assets/plugins/task-manager-default/`）
- 使用相对路径访问资源文件

**技术细节**:
```python
# 保存资源
relative_path = data_provider.save_asset(plugin_id, filename, content)
# 返回: "assets/plugins/task-manager-default/report.json"

# 转换为绝对路径
absolute_path = data_provider.get_asset_path(relative_path)
# 返回: "C:/.../InstructionX/assets/plugins/task-manager-default/report.json"
```

### ✅ 线程安全

**验证方法**:
- 同时在多个操作中添加/更新/删除任务
- 使用多线程并发访问 DataProvider
- 数据应该保持一致性，不会出现竞态条件

**技术细节**:
- 使用 `threading.Lock` 保护所有文件读写操作
- 锁的粒度：每次文件读写操作独立加锁

### ✅ 错误处理

**验证方法**:
- 尝试订阅不存在的插件（应该抛出 `DataProviderError`）
- 尝试访问不存在的数据键（返回默认值）
- 尝试保存无效的文件名（应该抛出异常）

**技术细节**:
```python
class DataProviderError(Exception):
    """DataProvider 专用异常类"""
    pass
```

## 数据文件结构

### data.json

```json
{
  "plugins": {
    "task-manager-default": {
      "type": "TaskManager",
      "active": true,
      "private": {
        "tasks": [
          {
            "id": "task_20260301_220000000000",
            "title": "完成文档编写",
            "description": "",
            "priority": "normal",
            "status": "pending",
            "created_at": "2026-03-01T22:00:00",
            "updated_at": "2026-03-01T22:00:00"
          }
        ]
      },
      "public": {
        "statistics": {
          "total": 1,
          "pending": 1,
          "in_progress": 0,
          "completed": 0,
          "cancelled": 0
        },
        "last_event": {
          "type": "task_added",
          "task_id": "task_20260301_220000000000",
          "timestamp": "2026-03-01T22:00:00"
        }
      }
    },
    "task-reporter-default": {
      "type": "TaskReporter",
      "active": true,
      "private": {
        "event_log": [
          {
            "timestamp": "2026-03-01T22:00:00",
            "type": "task_event",
            "plugin_id": "task-manager-default",
            "event_type": "task_added",
            "event_data": {...}
          }
        ]
      },
      "public": {}
    }
  },
  "subscriptions": {
    "task-reporter-default": [
      {
        "target_plugin_id": "task-manager-default",
        "target_key": "statistics",
        "callback": "_on_statistics_changed"
      },
      {
        "target_plugin_id": "task-manager-default",
        "target_key": "last_event",
        "callback": "_on_task_event"
      }
    ]
  }
}
```

## 技术要点总结

### 1. 原子写入实现

```python
def _save_data_atomically(self, data: Dict[str, Any]) -> None:
    """使用临时文件 + os.replace 实现原子写入"""
    temp_path = self.data_path.with_suffix('.tmp')
    
    # 写入临时文件
    with open(temp_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 原子替换（确保要么完全成功，要么完全失败）
    os.replace(temp_path, self.data_path)
```

### 2. 发布/订阅回调

```python
def publish(self, publisher_id: str, key: str, value: Any, namespace: DataNamespace = DataNamespace.PUBLIC):
    """发布数据变更并通知所有订阅者"""
    # 1. 保存数据
    self.set_plugin_data(publisher_id, key, value, namespace)
    
    # 2. 通知所有订阅者
    for subscriber_id, subscriptions in self._subscriptions.items():
        for sub in subscriptions:
            if sub.target_plugin_id == publisher_id and sub.target_key == key:
                # 调用订阅者的回调函数
                sub.callback(publisher_id, key, old_value, value)
```

### 3. 缓存失效

```python
def set_plugin_data(self, plugin_id: str, key: str, value: Any, namespace: DataNamespace):
    """设置数据并失效相关缓存"""
    # 1. 清除缓存
    cache_key = (plugin_id, key, namespace)
    self._cache.pop(cache_key, None)
    
    # 2. 保存到磁盘
    with self._lock:
        # ... 原子写入 ...
```

## 扩展建议

### 可以添加的功能

1. **任务优先级排序**
   - 按优先级显示任务
   - 高优先级任务提醒

2. **任务到期日期**
   - 添加截止日期
   - 过期任务标记

3. **任务标签系统**
   - 为任务添加标签
   - 按标签筛选

4. **图表可视化**
   - 使用 matplotlib 生成图表
   - 任务完成趋势分析

5. **多用户支持**
   - 每个用户独立的数据空间
   - 任务分配和协作

## 常见问题

### Q: 为什么任务报告生成器看不到任务管理器的 private 数据？

A: 这是命名空间隔离的设计。只有插件自身才能访问其 private 数据，其他插件只能访问 public 数据。这样可以保护插件内部数据的安全性。

### Q: 如何在多个插件之间共享数据？

A: 使用 `public` 命名空间发布数据，其他插件可以通过 `get_plugin_data` 访问。或者使用发布/订阅模式实现实时数据同步。

### Q: 数据持久化失败怎么办？

A: DataProvider 使用原子写入，数据不会损坏。如果写入失败，可以：
1. 检查磁盘空间
2. 检查文件权限
3. 查看错误日志

### Q: 如何提高性能？

A: DataProvider 已经实现了缓存机制。对于高频访问的数据，建议：
1. 使用缓存（默认已启用）
2. 批量操作减少磁盘 I/O
3. 合理设置缓存大小

## 总结

这两个插件完美展示了 `DataProvider` 的所有核心功能：

1. **数据持久化**: 任务数据安全保存到 `data.json`
2. **缓存机制**: 减少磁盘 I/O，提高性能
3. **命名空间隔离**: private/public 数据分离
4. **发布/订阅模式**: 实现插件间实时通信
5. **资源文件管理**: 管理报告和导出文件
6. **线程安全**: 并发访问保护
7. **错误处理**: 完善的异常处理机制

通过这两个插件的协作，你可以清晰地看到数据如何在插件之间流动，以及 DataProvider 如何提供一个可靠、高效、安全的数据管理解决方案。