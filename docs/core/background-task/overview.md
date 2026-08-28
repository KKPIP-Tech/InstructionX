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

- **特点**: 立即执行，**在调用方线程中运行**（不是主线程——`SYNC` 任务的同步性是相对异步/定时/长期而言的，调用方应理解任务将阻塞自身线程）
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
- **参数传递**: `SchedulerCallback.execute_scheduled_task()` 以 `execute_func(*task.args, **task.kwargs)` 方式调用任务函数（见 `core/task/scheduler.py` 的 `execute_scheduled_task` 方法），`args` 与 `kwargs` 可同时传递、互不排斥。
- **调度实现**: `TaskScheduler` 类目前仅作为**轻量生命周期占位**（仅保留 `start()` / `stop()` / `is_running`），其历史空转方法 `_check_and_run_tasks()`（早期为空实现 `pass`）已**整体移除**。实际的定时任务检查与执行由 `BackgroundTaskManager._check_scheduled_tasks()` daemon 线程（`ScheduledTaskChecker`）完成，该线程使用 `SchedulerCallback.should_run()` 判断到期，并通过 `SchedulerCallback.execute_scheduled_task()` 执行任务。**插件开发者请勿直接调用 `TaskScheduler`，仅在 `BackgroundTaskManager` 上下文中使用**。
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

#### 2.5.1 长期任务自动重启退避机制

`auto_restart=True` 的长期任务异常退出后，`BackgroundTaskManager` 按**指数退避**重启（`core/task/background_task.py` 模块级常量）：

| 常量 | 值 | 含义 |
|------|----|------|
| `AUTO_RESTART_INITIAL_DELAY` | 5.0 秒 | 首次重启延迟 |
| `AUTO_RESTART_MAX_DELAY` | 300.0 秒（5 分钟）| 单次延迟上限（指数增长封顶值） |
| `MAX_AUTO_RESTARTS` | 10 次 | 单次任务生命周期内最大重启次数；超过后任务标记为 `failed` 并停止后续重启（需插件手动重新注册） |

退避序列：`5s → 10s → 20s → 40s → 80s → 160s → 300s → 300s → ...`，第 11 次异常后停止重启并落 `failed` 状态。退避期间任务在 `_restart_timers` 中以 `threading.Timer` 形式排队；调用 `shutdown()` 时会统一取消所有待重启定时器。

---

## 3. 任务状态

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

> **注意**：`STOPPED` 枚举值在恢复长期任务时被用作过滤条件（`current_status in ("completed", "failed", "stopped")` 的任务不会被恢复），但任务对象不会通过 `mark_stopped()` 设置，目前也尚未在代码中为任务对象显式赋值。

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
    Note: STOPPED 枚举用于恢复过滤，但任务对象不会通过 mark_stopped() 设置
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

> **注意**：`TaskScheduler` 类目前仅作为**轻量生命周期占位**（仅保留 `start()` / `stop()` / `is_running`），其历史空转方法 `_check_and_run_tasks()`（早期为空实现 `pass`）已**整体移除**；不要直接调用 `TaskScheduler` 来安排定时任务。实际的定时任务检查逻辑在 `BackgroundTaskManager._check_scheduled_tasks()` daemon 线程（`ScheduledTaskChecker`）中执行，该线程使用 `SchedulerCallback.should_run()` 判断到期，并通过 `SchedulerCallback.execute_scheduled_task()` 执行任务。

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
    func: Optional[Callable]  # 执行函数
    callback: Optional[Callable]  # 回调函数
    args: tuple               # 函数参数
    kwargs: dict              # 关键字参数
    result: Any               # 执行结果
    error: Optional[str]      # 错误信息
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
    func_name: str            # 任务函数标识（func.__qualname__），用于重启后精确匹配工厂函数
    enabled: bool             # 是否启用
    args: tuple               # 函数参数
    kwargs: dict              # 关键字参数

    # 运行时属性（不参与序列化）
    func: Optional[Callable]   # 执行函数
    callback: Optional[Callable]  # 回调函数

    # 时间戳
    last_run: Optional[datetime]  # 上次执行时间
    next_run: Optional[datetime]  # 下次执行时间
    created_at: datetime      # 创建时间
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
    func_name: str            # 任务函数标识（func.__qualname__），用于重启后精确匹配工厂函数

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

### 6.3 工厂注册机制（双级键归档）

> 定时任务工厂与长期任务工厂均为**双级键结构**：`{plugin_id: {"func": ..., "callback": ..., "funcs": {func_name: {...}}}}`（见 `core/task/background_task.py` 的 `_archive_scheduled_factory` / `_archive_long_running_factory`）。同一插件可注册**多个不同函数**，按 `func.__qualname__` 归档到 `funcs` 子表，互不覆盖；顶层 `func`/`callback` 等键仅保留最近注册的值，用于兼容旧结构。
>
> 注册任务时会把 `func.__qualname__` 记入任务的 `func_name` 字段并持久化；重启恢复时按 `plugin_id + func_name` 精确匹配工厂。旧版记录（无 `func_name`）回退到该插件唯一工厂；该插件注册了多个工厂时使用第一个并记 warning。

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

### 9.0 生命周期管理：shutdown() 限时优雅关闭

`main.py` 在 `application.exec()` 返回后调用 `BackgroundTaskManager.shutdown()`，流程**严格限时**，保证应用不会因任务未结束而卡死：

1. **拒绝新任务**：`self._is_shutdown = True`，后续 `register_async_task` / `register_scheduled_task` / `register_long_running_task` 均返回 `None`；
2. **停止定时任务检查线程**：`_stop_event.set()` + `_schedule_check_thread.join(timeout=CHECK_THREAD_JOIN_TIMEOUT)`；
3. **取消待重启定时器**：遍历 `_restart_timers` 全部 `timer.cancel()`；
4. **停止长期任务**：先逐个调用 `stop_callback`（让任务尽快收到停止信号），再 `future.result(timeout=LONG_TASK_STOP_TIMEOUT=3.0s)` 限时等待；超时任务记 WARNING 并 `future.cancel()` 放弃等待；正常退出的长期任务标记为 `STOPPED` 状态并落存储（**正常退出语义**——重启后不自动恢复；「崩溃中断」的任务会在下次启动时由 `_backfill_registry` / 工厂恢复路径恢复）；
5. **关闭线程池**：在独立 `BackgroundTaskExecutorShutdown` daemon 线程中调用 `executor.shutdown(wait=True, cancel_futures=True)`；总上限 `EXECUTOR_SHUTDOWN_TIMEOUT=10s`，超时记 WARNING 放弃等待；
6. **清理单例**：`BackgroundTaskManager._instance = None`，下次 `BackgroundTaskManager()` 重新构造（典型场景：单元测试 / 重启）。

可配常量均位于 `BackgroundTaskManager` 模块顶部（`LONG_TASK_STOP_TIMEOUT` / `EXECUTOR_SHUTDOWN_TIMEOUT` / `CHECK_THREAD_JOIN_TIMEOUT`）。

### 9.0.1 启动期自动清理过期任务

`BackgroundTaskManager.__init__()` 启动时调用 `cleanup_old_tasks(max_age_days=TASK_RECORD_MAX_AGE_DAYS=30)`，删除 `finished_at` 距今超过 30 天的已完成/失败任务，**避免 `data/tasks.json` 长期膨胀**。`max_age_days` 由插件通过 `cleanup_old_tasks(max_age_days=N)` 手动调用覆盖。

### 9.0.2 TaskStorage 损坏防护

`TaskStorage` 读取 `data/tasks.json` 时：

- **首次失败**（JSON 解析异常 / 读盘异常）：将原文件备份为 `data/tasks.json.corrupt.bak`（**固定文件名，会覆盖旧备份**），写入空 `{"tasks":{}, "scheduled_tasks":{}, "long_running_tasks":{}}`，记 WARNING 日志；`Application` 启动不受阻断；同时清除 `_read_ok` 标志，**防止后续 save 在未重读的情况下用空数据覆盖磁盘**；
- **首次失败后再次重读**：基于空配置继续运行（除非空配置本身也无法解析）。

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
            "func_name": "backup_task",
            "enabled": true,
            "args": [],
            "kwargs": {},
            "last_run": "2026-01-01T10:00:00",
            "next_run": "2026-01-01T11:00:00",
            "created_at": "2026-01-01T09:00:00"
        }
    },
    "long_running_tasks": {
        "long-running-uuid-1": {
            "task_id": "long-running-uuid-1",
            "plugin_id": "plugin-uuid",
            "name": "Web服务",
            "enabled": true,
            "auto_restart": true,
            "func_name": "web_service",
            "current_status": "running",
            "error": null,
            "args": [],
            "kwargs": {},
            "created_at": "2026-01-01T10:00:00",
            "last_started_at": "2026-01-01T10:00:05",
            "last_stopped_at": null,
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
