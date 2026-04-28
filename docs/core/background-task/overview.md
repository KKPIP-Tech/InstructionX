# 后台任务系统概述

> BackgroundTaskManager 的架构设计和核心概念

---

## 1. 概述

`BackgroundTaskManager` 是 InstructionX 项目的后台任务调度组件，负责管理插件提交的后台任务和定时任务。

**文件位置**: `core/task/background_task.py`

**模式**: 单例模式（全局唯一实例）

**核心功能**:
- 同步任务执行
- 异步任务调度
- 定时任务管理
- 长期任务管理
- 任务状态持久化

---

## 2. 任务类型

### 2.1 任务类型枚举

```python
class TaskType(Enum):
    """任务类型枚举"""
    SYNC = "sync"        # 同步任务
    ASYNC = "async"      # 异步任务
    SCHEDULED = "scheduled"  # 定时任务
    LONG_RUNNING = "long_running"  # 长期任务
```

### 2.2 同步任务 (SYNC)

- **特点**: 立即执行，在主线程中运行
- **适用场景**: 快速完成的小任务
- **持久化注意**: 同步任务的 `RUNNING` 状态**不会被持久化**到存储中。`mark_running()` 后没有调用 `save_task()`，任务完成后才在 `finally` 块中保存最终状态（`COMPLETED` 或 `FAILED`）。因此，如果应用在同步任务执行期间崩溃，任务将不会留下运行中的记录。
- **示例**:
  ```python
  task_id = manager.register_sync_task(
      plugin_id="my-plugin",
      name="同步任务",
      func=my_function,
      callback=my_callback
  )
  ```

### 2.3 异步任务 (ASYNC)

- **特点**: 提交到线程池执行，不阻塞主线程
- **适用场景**: 耗时较长的操作
- **示例**:
  ```python
  task_id = manager.register_async_task(
      plugin_id="my-plugin",
      name="异步任务",
      func=heavy_function,
      callback=my_callback
  )
  ```

### 2.4 定时任务 (SCHEDULED)

- **特点**: 按固定间隔重复执行
- **适用场景**: 定期备份、自动同步等
- **参数限制**: `SchedulerCallback.execute_scheduled_task()` 在执行时优先检查 `args`。当 `args` 和 `kwargs` 同时存在时，`kwargs` 会被忽略。如需同时使用两者，请在 `args` 中传递字典并在 `func` 内部解包。
- **示例**:
  ```python
  task_id = manager.register_scheduled_task(
      plugin_id="my-plugin",
      name="定时任务",
      func=periodic_function,
      interval=60,  # 每 60 秒执行一次
      callback=my_callback
  )
  ```

### 2.5 长期任务 (LONG_RUNNING)

- **特点**: 持续运行直到被显式停止，支持优雅停止和自动重启
- **适用场景**: Web 服务器、长期驻留服务、持续监听任务等
- **示例**:
  ```python
  import threading

  stop_flag = threading.Event()

  def my_service():
      """长期运行的服务"""
      while not stop_flag.is_set():
          # 处理请求
          time.sleep(1)

  def on_stop():
      """停止回调，用于优雅关闭"""
      stop_flag.set()

  task_id = manager.register_long_running_task(
      plugin_id="my-plugin",
      name="Web服务",
      func=my_service,
      stop_callback=on_stop,  # 优雅停止回调
      auto_restart=True       # 失败后自动重启
  )
  ```

---

## 3. 任务状态

### 3.1 状态枚举

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

> **注意**：`STOPPED` 状态在 `TaskStatus` 枚举中定义，但目前代码中尚未实际赋值。该状态预留用于长期任务的主动停止场景。

### 3.2 状态转换图

```mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> RUNNING: 执行
    PENDING --> CANCELLED: 取消
    RUNNING --> COMPLETED: 成功
    RUNNING --> FAILED: 失败
    COMPLETED --> [*]
    FAILED --> [*]
    CANCELLED --> [*]
    Note: STOPPED 状态预留但未在代码中实际赋值
```

---

## 4. 架构图

```mermaid
graph TB
    subgraph BTM [BackgroundTaskManager 单例]
        Pool[线程池<br/>ThreadPoolExecutor<br/>max_workers=4]
        RunningTasks[运行中的任务<br/>_running_tasks]
        ScheduledTasks[定时任务<br/>_running_scheduled_tasks]
        LongRunningTasks[长期任务<br/>_running_long_running_tasks]
        ScheduledFactories[定时任务工厂<br/>_scheduled_task_factories]
        LongRunningFactories[长期任务工厂<br/>_long_running_task_factories]
        ScheduleChecker[定时任务检查线程<br/>_check_scheduled_tasks]
    end

    subgraph Storage [存储层]
        JSON[data/tasks.json]
    end

    subgraph Plugin [插件]
        Register[注册任务]
    end

    Pool -->|执行任务| RunningTasks
    Pool -->|执行任务| ScheduledTasks
    Pool -->|执行任务| LongRunningTasks
    ScheduleChecker -->|检查到期| ScheduledTasks
    Register -->|注册| BTM
    BTM -->|持久化| JSON
    BTM -->|恢复| JSON
```

> **注意**：`TaskScheduler` 类虽然被初始化并启动，但其 `_check_and_run_tasks()` 方法目前为空实现（`pass`）。实际的定时任务检查逻辑在 `BackgroundTaskManager._check_scheduled_tasks()` daemon 线程（`ScheduledTaskChecker`）中执行，该线程使用 `SchedulerCallback.should_run()` 判断到期，并通过 `SchedulerCallback.execute_scheduled_task()` 执行任务。

---

## 5. 任务数据模型

### 5.1 BackgroundTask

```python
class BackgroundTask:
    """后台任务"""
    task_id: str              # 任务唯一 ID
    plugin_id: str            # 插件 ID
    name: str                 # 任务名称
    task_type: TaskType       # 任务类型
    status: TaskStatus        # 任务状态
    func: Callable            # 执行函数
    callback: Optional[Callable]  # 回调函数
    args: tuple               # 函数参数
    kwargs: dict              # 关键字参数
    result: Any               # 执行结果
    error: str                # 错误信息
    created_at: datetime      # 创建时间
    started_at: Optional[datetime]  # 开始时间
    finished_at: Optional[datetime]  # 完成时间
```

### 5.2 ScheduledTask

```python
class ScheduledTask:
    """定时任务"""
    task_id: str              # 任务唯一 ID
    plugin_id: str            # 插件 ID
    name: str                 # 任务名称
    interval: int             # 执行间隔（秒）
    enabled: bool              # 是否启用
    last_run: Optional[datetime]  # 上次执行时间
    next_run: Optional[datetime]  # 下次执行时间
    func: Optional[Callable]   # 执行函数
    callback: Optional[Callable]  # 回调函数
```

### 5.3 LongRunningTask

```python
class LongRunningTask:
    """长期任务"""
    task_id: str              # 任务唯一 ID
    plugin_id: str            # 插件 ID
    name: str                 # 任务名称
    enabled: bool             # 是否启用
    auto_restart: bool        # 失败后是否自动重启

    # 运行时属性（不参与序列化）
    func: Optional[Callable]          # 执行函数
    callback: Optional[Callable]       # 完成回调
    stop_callback: Optional[Callable]  # 停止回调（用于优雅关闭）
    status_callback: Optional[Callable]  # 状态更新回调
    args: tuple                # 函数参数
    kwargs: dict              # 关键字参数

    # 状态
    current_status: str       # 当前状态描述
    error: Optional[str]      # 错误信息

    # 时间戳
    created_at: datetime      # 创建时间
    last_started_at: Optional[datetime]  # 上次启动时间
    last_stopped_at: Optional[datetime]  # 上次停止时间
    restart_count: int       # 重启次数
```

---

## 6. 任务工厂机制

### 6.1 问题背景

定时任务和长期任务需要持久化存储（保存到 `tasks.json`），但函数和回调无法序列化。

### 6.2 解决方案

使用**任务工厂**机制：

```python
# 1. 定时任务工厂 - 插件加载时注册
manager.register_scheduled_task_factory(
    plugin_id,
    func=periodic_task_func,
    callback=periodic_callback
)

# 2. 长期任务工厂 - 插件加载时注册
manager.register_long_running_task_factory(
    plugin_id,
    func=long_running_service,
    stop_callback=cleanup_function,  # 优雅停止回调
    status_callback=status_updater    # 状态更新回调
)

# 3. 应用重启时恢复任务
# BackgroundTaskManager 会在工厂注册后自动恢复
```

### 6.3 工厂注册限制

> **重要限制**：一个插件只能注册**一个定时任务工厂**和**一个长期任务工厂**。后注册的工厂会覆盖先注册的工厂（以 `plugin_id` 为键的字典存储）。
>
> 如果插件需要多个定时任务，应在工厂函数内部通过参数区分不同的任务逻辑，或使用多个异步任务替代。

### 6.4 恢复流程

```mermaid
flowchart TD
    A[应用启动] --> B[BTM 初始化]
    B --> C[加载 tasks.json]
    C --> D[插件调用 register_*_task_factory]
    D --> E{查找工厂}
    E -->|找到| F[恢复 func 和 callbacks]
    E -->|未找到| G[func=None]
    F --> H[启动任务]
    G --> H
```

**注意**：长期任务工厂应在 `on_plugin_loaded()` 中注册，而非 `_create_widget()` 中。

---

## 7. 长期任务状态管理

### 7.1 更新任务状态

```python
def update_long_running_task_status(self, task_id: str, status: str) -> bool:
    """
    更新长期任务的状态描述

    Args:
        task_id: 任务 ID
        status: 状态描述字符串

    Returns:
        是否成功更新

    Example:
        manager.update_long_running_task_status(
            task_id="long-task-001",
            status="正在处理第 5/10 个文件..."
        )
    """
```

### 7.2 获取长期任务列表

```python
def get_long_running_tasks(self, plugin_id: Optional[str] = None) -> List[LongRunningTask]:
    """
    获取长期任务列表

    Args:
        plugin_id: 可选的插件 ID，如果提供则只返回该插件的任务

    Returns:
        长期任务列表
    """
```

> **注意**: `get_task()` 和 `get_task_status()` 方法**不包含长期任务**。查询长期任务必须显式调用 `get_long_running_tasks()`。

---

## 8. 回调函数

### 8.1 回调签名

```python
def task_callback(
    task_id: str,
    status: TaskStatus,
    result: Any,
    error: Optional[str]
):
    """
    任务完成回调

    Args:
        task_id: 任务 ID
        status: 最终状态 (COMPLETED / FAILED / CANCELLED)
        result: 任务返回值（如果成功）
        error: 错误信息（如果失败）
    """
    pass
```

### 8.2 使用示例

```python
def on_task_complete(task_id, status, result, error):
    if status == TaskStatus.COMPLETED:
        print(f"任务 {task_id} 完成，结果: {result}")
    elif status == TaskStatus.FAILED:
        print(f"任务 {task_id} 失败: {error}")

# 注册任务
task_id = manager.register_async_task(
    plugin_id="my-plugin",
    name="后台任务",
    func=my_function,
    callback=on_task_complete,
    args=(arg1, arg2),
    kwargs={"key": "value"}
)
```


---

## 9. 持久化存储

### 9.1 tasks.json 结构

```json
{
    "tasks": {
        "task-uuid-1": {
            "task_id": "task-uuid-1",
            "plugin_id": "plugin-uuid",
            "name": "异步任务",
            "task_type": "async",
            "status": "completed",
            "result": {},
            "error": null,
            "created_at": "2026-01-01T10:00:00",
            "started_at": "2026-01-01T10:00:00",
            "finished_at": "2026-01-01T10:00:05"
        }
    },
    "scheduled_tasks": {
        "scheduled-uuid-1": {
            "task_id": "scheduled-uuid-1",
            "plugin_id": "plugin-uuid",
            "name": "定时备份",
            "interval": 3600,
            "enabled": true,
            "last_run": "2026-01-01T10:00:00",
            "next_run": "2026-01-01T11:00:00"
        }
    },
    "long_running_tasks": {
        "long-running-uuid-1": {
            "task_id": "long-running-uuid-1",
            "plugin_id": "plugin-uuid",
            "name": "Web服务",
            "enabled": true,
            "auto_restart": true,
            "current_status": "running",
            "error": null,
            "created_at": "2026-01-01T10:00:00",
            "last_started_at": "2026-01-01T10:00:05",
            "restart_count": 0
        }
    }
}
```


---

## 10. 相关文档

- [后台任务 API 参考](api-reference.md)
- [后台任务存储](task-storage.md)
- [插件开发指南](../plugin-system/plugin-development.md)
- [接口层概述](../interfaces/overview.md)

---

*本文档由 Claude Code 自动生成*
