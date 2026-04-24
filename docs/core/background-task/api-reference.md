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
    LONG_RUNNING = "long_running"  # 长期任务
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
    STOPPED = "stopped"      # 已停止（长期任务被主动停止）
```

> **注意**：`STOPPED = "stopped"` 状态在 `core/interfaces/i_task_manager.py` 和 `core/task/task_model.py` 中均有定义，用于表示长期任务被主动停止的状态。

### TaskThreadLocal

```python
class TaskThreadLocal:
    """线程本地任务存储

    利用线程本地存储机制，在多线程环境下安全传递当前任务信息。
    用于在任务执行的子线程中获取关联的任务上下文。
    """

    @classmethod
    def set_current_task(cls, task: BackgroundTask) -> None:
        """设置当前线程的关联任务"""

    @classmethod
    def get_current_task(cls) -> Optional[BackgroundTask]:
        """获取当前线程关联的任务"""

    @classmethod
    def clear_current_task(cls) -> None:
        """清除当前线程的任务关联"""
```

**使用场景**：在任务执行的子线程中获取关联的任务上下文，例如记录任务 ID 到日志中。

```python
from core.task.task_model import TaskThreadLocal

# 在任务执行函数中
def my_task_func(task_id):
    task = TaskThreadLocal.get_current_task()
    if task:
        print(f"当前任务: {task.name}")
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

> **注意**: `SchedulerCallback.execute_scheduled_task()` 在执行时优先检查 `args`，当 `args` 和 `kwargs` 同时存在时，`kwargs` 会被忽略。如需同时使用两者，请在 `args` 中传递字典并在 `func` 内部解包。

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

用于在应用启动时恢复定时任务。插件应该在 `on_plugin_loaded()` 中调用此方法注册工厂。

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

# 在插件的 on_plugin_loaded 中注册工厂
manager.register_scheduled_task_factory(
    plugin_id=self.plugin_id,
    func=periodic_func,
    callback=periodic_callback
)
```

---

## 4. 长期任务注册方法

### register_long_running_task()

```python
def register_long_running_task(
    self,
    plugin_id: str,
    name: str,
    func: Callable,
    callback: Optional[Callable] = None,
    stop_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    auto_restart: bool = True,
    args: tuple = (),
    kwargs: dict = None
) -> str
```

注册长期任务（会持续运行直到被显式停止）。

**参数**:
- `plugin_id`: 插件 UUID
- `name`: 任务名称
- `func`: 执行函数（阻塞函数，会持续运行）
- `callback`: 可选的完成回调
- `stop_callback`: 可选的停止回调，用于优雅关闭
- `status_callback`: 可选的状态更新回调
- `auto_restart`: 失败后是否自动重启，默认 True
- `args`: 位置参数元组
- `kwargs`: 关键字参数字典

**返回**:
- 任务 ID

**示例**:
```python
import threading
import time

stop_flag = threading.Event()

def web_service():
    """Web 服务任务"""
    while not stop_flag.is_set():
        # 处理请求
        time.sleep(1)

def on_stop():
    """优雅停止回调"""
    stop_flag.set()
    print("服务已停止")

def on_status_update(task_id, status):
    """状态更新回调"""
    print(f"任务 {task_id} 状态: {status}")

task_id = manager.register_long_running_task(
    plugin_id="my-plugin",
    name="Web服务",
    func=web_service,
    stop_callback=on_stop,
    status_callback=on_status_update,
    auto_restart=True
)
```

---

### register_long_running_task_factory()

```python
def register_long_running_task_factory(
    self,
    plugin_id: str,
    func: Callable,
    callback: Optional[Callable] = None,
    stop_callback: Optional[Callable] = None,
    status_callback: Optional[Callable] = None,
    restore_callback: Optional[Callable] = None
) -> None
```

注册长期任务工厂函数。

用于在应用启动时恢复长期任务。插件应该在 `on_plugin_loaded()` 中调用此方法注册工厂。

**参数**:
- `plugin_id`: 插件 UUID
- `func`: 任务执行函数
- `callback`: 可选的回调函数
- `stop_callback`: 可选的停止回调
- `status_callback`: 可选的状态更新回调
- `restore_callback`: 可选的恢复回调，任务从持久化存储恢复并开始运行时触发

**示例**:
```python
import threading

stop_flag = threading.Event()

def service_func():
    while not stop_flag.is_set():
        time.sleep(1)

def stop_callback():
    stop_flag.set()

def status_callback(task_id, status):
    print(f"状态: {status}")

def restore_callback(task_id, task):
    """恢复回调：任务从存储恢复并启动时调用"""
    print(f"任务 {task_id} 已恢复运行")

# 在插件的 on_plugin_loaded 中注册工厂
manager.register_long_running_task_factory(
    plugin_id=self.plugin_id,
    func=service_func,
    stop_callback=stop_callback,
    status_callback=status_callback,
    restore_callback=restore_callback
)
```

---

## 5. 长期任务控制方法

### restore_long_running_tasks()

```python
def restore_long_running_tasks(self, plugin_id: str) -> int
```

恢复指定插件的长期任务。

**参数**:
- `plugin_id`: 插件 UUID

**返回**:
- 恢复的任务数量

---

### stop_long_running_task()

```python
def stop_long_running_task(self, task_id: str, delete_from_storage: bool = True) -> bool
```

停止长期任务（会调用 stop_callback 进行优雅关闭）。

**参数**:
- `task_id`: 任务 ID
- `delete_from_storage`: 是否从持久化存储中删除任务，默认为 True

**返回**:
- 是否成功停止

---

### update_long_running_task_status()

```python
def update_long_running_task_status(self, task_id: str, status: str) -> bool
```

更新长期任务的状态。

**参数**:
- `task_id`: 任务 ID
- `status`: 状态描述

**返回**:
- 是否成功更新

> **注意**：此方法在 `BackgroundTaskManager` 实现和 `ITaskManager` 抽象接口（`core/interfaces/i_task_manager.py:157`）中均有声明。

---

### get_long_running_tasks()

```python
def get_long_running_tasks(self, plugin_id: Optional[str] = None) -> List[LongRunningTask]
```

获取长期任务列表。

**参数**:
- `plugin_id`: 可选，插件 UUID。如果提供，则只返回该插件的长期任务

**返回**:
- 长期任务列表

---

## 6. 定时任务控制方法

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

## 7. 任务查询方法

### get_task()

```python
def get_task(self, task_id: str) -> Optional[BackgroundTask]
```

获取指定任务（不包括长期任务）。

**参数**:
- `task_id`: 任务 ID

**返回**:
- BackgroundTask 对象，如果不存在则返回 None

> **注意**: 长期任务需通过 `get_long_running_tasks()` 获取。

---

### get_tasks_by_plugin()

```python
def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]
```

获取指定插件的所有任务（不包括长期任务）。

**参数**:
- `plugin_id`: 插件 UUID

**返回**:
- 任务列表

> **注意**: 长期任务需通过 `get_long_running_tasks()` 获取。

---

### get_all_tasks()

```python
def get_all_tasks(self) -> List[BackgroundTask]
```

获取所有任务（不包括长期任务）。

> **注意**: 长期任务需通过 `get_long_running_tasks()` 获取。

**返回**:
- 任务列表（不含长期任务）

---

### get_task_status()

```python
def get_task_status(self, task_id: str) -> Optional[TaskStatus]
```

获取任务状态（不包括长期任务）。

**参数**:
- `task_id`: 任务 ID

**返回**:
- TaskStatus 枚举值，如果任务不存在则返回 None

> **注意**: 长期任务状态需通过 `get_long_running_tasks()` 获取。

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

## 8. 任务控制方法

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

## 9. 完整示例

### 9.1 注册各类任务

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

# 4. 长期任务
import threading

# 停止标志
stop_flag = threading.Event()

def long_running_service():
    """长期运行的服务"""
    while not stop_flag.is_set():
        # 处理业务逻辑
        print("服务运行中...")
        time.sleep(1)

def service_stop_callback():
    """优雅停止回调"""
    print("正在停止服务...")
    stop_flag.set()
    print("服务已停止")

def service_status_callback(task_id, status):
    """状态更新回调"""
    print(f"任务 {task_id} 状态: {status}")

def service_callback(task_id, status, result, error):
    """任务完成回调"""
    print(f"任务完成: {status}")

def service_restore_callback(task_id, task):
    """恢复回调：任务从存储恢复并启动时调用"""
    print(f"任务 {task_id} 已从存储恢复并开始运行")

# 先注册工厂（应用启动时）
manager.register_long_running_task_factory(
    plugin_id="service-plugin",
    func=long_running_service,
    stop_callback=service_stop_callback,
    status_callback=service_status_callback,
    callback=service_callback,
    restore_callback=service_restore_callback
)

# 然后注册长期任务
long_running_id = manager.register_long_running_task(
    plugin_id="service-plugin",
    name="Web服务",
    func=long_running_service,
    stop_callback=service_stop_callback,
    status_callback=service_status_callback,
    callback=service_callback,
    auto_restart=True  # 失败后自动重启
)
```

### 9.2 查询任务状态

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

### 9.3 控制任务

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

### 9.4 长期任务控制

```python
# 获取长期任务列表
long_tasks = manager.get_long_running_tasks()
for task in long_tasks:
    print(f"{task.name}: {task.current_status}, 重启次数: {task.restart_count}")

# 获取指定插件的长期任务
plugin_tasks = manager.get_long_running_tasks("service-plugin")

# 更新任务状态（从任务内部调用）
# manager.update_long_running_task_status(task_id, "正在处理请求")

# 停止长期任务（会调用 stop_callback）
manager.stop_long_running_task(long_running_id)
```

## 10. 生命周期管理

### shutdown()

```python
def shutdown(self) -> None
```

关闭任务管理器，释放所有资源。

此方法应在应用程序退出前调用，以确保所有任务正确停止。

**示例**:
```python
# 在应用程序退出时调用
manager.shutdown()
print("任务管理器已关闭")
```

---

## 11. 相关文档

- [后台任务概述](overview.md)
- [插件开发指南](../plugin-system/plugin-development.md)

---

*本文档由 Claude Code 自动生成*
