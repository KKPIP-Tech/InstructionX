# 后台任务 API 参考

> BackgroundTaskManager 的完整 API 列表和详细说明

---

## 1. 类定义

```python
from core.task.background_task import BackgroundTaskManager
from core.task.task_model import TaskType, TaskStatus

# 获取单例实例
manager = BackgroundTaskManager()
```

---

## 2. 数据模型

### TaskType

```python
class TaskType(Enum):
    """任务类型枚举"""
    SYNC = "sync"            # 同步任务
    ASYNC = "async"          # 异步任务
    SCHEDULED = "scheduled"  # 定时任务
```

### TaskStatus

```python
class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 执行失败
    CANCELLED = "cancelled"  # 已取消
```

---

## 3. 任务注册方法

### register_sync_task()

```python
def register_sync_task(
    self,
    plugin_id: str,
    name: str,
    func: Callable,
    callback: Optional[Callable] = None,
    args: tuple = (),
    kwargs: dict = None
) -> str
```

注册并立即执行同步任务。

**参数**:
- `plugin_id`: 插件 UUID
- `name`: 任务名称
- `func`: 执行函数
- `callback`: 可选的回调函数
- `args`: 位置参数元组
- `kwargs`: 关键字参数字典

**返回**:
- 任务 ID

**示例**:
```python
def my_task():
    print("执行同步任务")
    return "完成"

task_id = manager.register_sync_task(
    plugin_id="my-plugin",
    name="同步任务",
    func=my_task
)
```

---

### register_async_task()

```python
def register_async_task(
    self,
    plugin_id: str,
    name: str,
    func: Callable,
    callback: Optional[Callable] = None,
    args: tuple = (),
    kwargs: dict = None
) -> str
```

注册异步任务（在线程池中执行）。

**参数**:
- `plugin_id`: 插件 UUID
- `name`: 任务名称
- `func`: 执行函数
- `callback`: 可选的回调函数
- `args`: 位置参数元组
- `kwargs`: 关键字参数字典

**返回**:
- 任务 ID

**示例**:
```python
def heavy_task():
    import time
    time.sleep(5)  # 模拟耗时操作
    return "处理完成"

def on_complete(task_id, status, result, error):
    print(f"任务 {task_id} 状态: {status}")

task_id = manager.register_async_task(
    plugin_id="my-plugin",
    name="异步任务",
    func=heavy_task,
    callback=on_complete
)
```

---

### register_scheduled_task()

```python
def register_scheduled_task(
    self,
    plugin_id: str,
    name: str,
    func: Callable,
    interval: int,
    callback: Optional[Callable] = None,
    args: tuple = (),
    kwargs: dict = None
) -> str
```

注册定时任务。

**参数**:
- `plugin_id`: 插件 UUID
- `name`: 任务名称
- `func`: 执行函数
- `interval`: 执行间隔（秒）
- `callback`: 可选的回调函数
- `args`: 位置参数元组
- `kwargs`: 关键字参数字典

**返回**:
- 任务 ID

**示例**:
```python
def backup_task():
    print("执行备份")
    return "备份完成"

task_id = manager.register_scheduled_task(
    plugin_id="my-plugin",
    name="定时备份",
    func=backup_task,
    interval=3600  # 每小时执行一次
)
```

---

### register_scheduled_task_factory()

```python
def register_scheduled_task_factory(
    self,
    plugin_id: str,
    func: Callable,
    callback: Optional[Callable] = None
) -> None
```

注册定时任务工厂函数。

用于在应用启动时恢复定时任务。插件应该在 `_create_widget` 中调用此方法注册工厂。

**参数**:
- `plugin_id`: 插件 UUID
- `func`: 任务执行函数
- `callback`: 可选的回调函数

**示例**:
```python
def periodic_func():
    print("定时任务执行")

def periodic_callback(task_id, status, result, error):
    print(f"任务 {task_id} 完成")

# 在插件的 _create_widget 中注册工厂
manager.register_scheduled_task_factory(
    plugin_id=self.plugin_id,
    func=periodic_func,
    callback=periodic_callback
)
```

---

## 4. 定时任务控制方法

### restore_scheduled_tasks()

```python
def restore_scheduled_tasks(self, plugin_id: str) -> int
```

恢复指定插件的定时任务。

**参数**:
- `plugin_id`: 插件 UUID

**返回**:
- 恢复的任务数量

---

### enable_scheduled_task()

```python
def enable_scheduled_task(self, task_id: str) -> bool
```

启用定时任务。

**参数**:
- `task_id`: 任务 ID

**返回**:
- 是否成功

---

### disable_scheduled_task()

```python
def disable_scheduled_task(self, task_id: str) -> bool
```

禁用定时任务。

**参数**:
- `task_id`: 任务 ID

**返回**:
- 是否成功

---

### unregister_scheduled_task()

```python
def unregister_scheduled_task(self, task_id: str) -> bool
```

注销定时任务。

**参数**:
- `task_id`: 任务 ID

**返回**:
- 是否成功

---

## 5. 任务查询方法

### get_task()

```python
def get_task(self, task_id: str) -> Optional[BackgroundTask]
```

获取指定任务。

**参数**:
- `task_id`: 任务 ID

**返回**:
- BackgroundTask 对象，如果不存在则返回 None

---

### get_tasks_by_plugin()

```python
def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]
```

获取指定插件的所有任务。

**参数**:
- `plugin_id`: 插件 UUID

**返回**:
- 任务列表

---

### get_all_tasks()

```python
def get_all_tasks(self) -> List[BackgroundTask]
```

获取所有任务。

**返回**:
- 任务列表

---

### get_task_status()

```python
def get_task_status(self, task_id: str) -> Optional[TaskStatus]
```

获取任务状态。

**参数**:
- `task_id`: 任务 ID

**返回**:
- TaskStatus 枚举值，如果任务不存在则返回 None

---

### get_scheduled_tasks()

```python
def get_scheduled_tasks(self, plugin_id: Optional[str] = None) -> List[ScheduledTask]
```

获取定时任务列表。

**参数**:
- `plugin_id`: 可选，插件 UUID。如果提供，则只返回该插件的定时任务

**返回**:
- 定时任务列表

---

## 6. 任务控制方法

### cancel_task()

```python
def cancel_task(self, task_id: str) -> bool
```

取消任务。

**参数**:
- `task_id`: 任务 ID

**返回**:
- 是否成功（如果任务已执行完成则返回 False）

---

### clear_completed_tasks()

```python
def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int
```

清理已完成的任务。

**参数**:
- `plugin_id`: 可选，插件 UUID。如果提供，则只清理该插件的任务

**返回**:
- 清理的任务数量

---

## 7. 完整示例

### 7.1 注册各类任务

```python
from core.task.background_task import BackgroundTaskManager
from core.task.task_model import TaskType, TaskStatus

manager = BackgroundTaskManager()

# 1. 同步任务
def sync_task():
    result = 1 + 2
    return result

sync_id = manager.register_sync_task(
    plugin_id="my-plugin",
    name="同步计算",
    func=sync_task
)

# 2. 异步任务
def async_task(data):
    import time
    time.sleep(2)
    return f"处理: {data}"

def task_callback(task_id, status, result, error):
    if status == TaskStatus.COMPLETED:
        print(f"任务完成，结果: {result}")
    elif status == TaskStatus.FAILED:
        print(f"任务失败: {error}")

async_id = manager.register_async_task(
    plugin_id="my-plugin",
    name="异步处理",
    func=async_task,
    callback=task_callback,
    args=("test data",)
)

# 3. 定时任务
def scheduled_backup():
    print("执行备份...")
    return "备份完成"

def backup_callback(task_id, status, result, error):
    print(f"备份任务 {status}")

# 先注册工厂（应用启动时）
manager.register_scheduled_task_factory(
    plugin_id="backup-plugin",
    func=scheduled_backup,
    callback=backup_callback
)

# 然后注册定时任务
scheduled_id = manager.register_scheduled_task(
    plugin_id="backup-plugin",
    name="定时备份",
    func=scheduled_backup,
    interval=3600,
    callback=backup_callback
)
```

### 7.2 查询任务状态

```python
# 获取单个任务
task = manager.get_task(sync_id)
print(f"任务状态: {task.status}")
print(f"任务结果: {task.result}")

# 获取插件的所有任务
plugin_tasks = manager.get_tasks_by_plugin("my-plugin")
for task in plugin_tasks:
    print(f"{task.name}: {task.status}")

# 获取定时任务
scheduled = manager.get_scheduled_tasks()
for task in scheduled:
    print(f"{task.name} - 下次执行: {task.next_run}")
```

### 7.3 控制任务

```python
# 取消任务
manager.cancel_task(async_id)

# 禁用定时任务
manager.disable_scheduled_task(scheduled_id)

# 重新启用定时任务
manager.enable_scheduled_task(scheduled_id)

# 清理已完成的任务
manager.clear_completed_tasks("my-plugin")
```

---

## 8. 相关文档

- [后台任务概述](overview.md)
- [插件开发指南](../plugin-system/plugin-development.md)

---

*本文档由 Claude Code 自动生成*
