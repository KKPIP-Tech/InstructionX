# 任务系统测试文档

> 后台任务系统模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/task/`
**测试文件数**: 4 个（另有 `conftest.py` 提供公共 fixtures，不含用例）
**测试用例总数**: 72 个（实测）

> 实测命令（工作目录 = 项目根）：
> `.venv\Scripts\python.exe -m pytest test/core/task --collect-only -q -p no:cacheprovider`
> 收集结果汇总行为 `72 tests collected`，与本文 §3 的 72 行用例清单一一对应。

### 1.1 测试文件分布

| 测试文件 | 测试用例数 | 主要覆盖 |
|---------|-----------|---------|
| `test_background_task.py` | 28 | BackgroundTaskManager 单例与生命周期、同步/异步/定时/长时任务的注册与注销、取消与查询、shutdown 状态 |
| `test_background_task_shutdown.py` | 7 | shutdown 行为与资源清理（R-03）、定时任务恢复（R-06）、长时任务重启、超时清理、空队列 shutdown |
| `test_task_model.py` | 15 | TaskType / TaskStatus 枚举、三类任务的序列化往返、BackgroundTask 状态转换方法、TaskThreadLocal |
| `test_task_storage.py` | 22 | TaskStorage 单例与初始化、三类任务 CRUD、内存缓存行为、损坏回退、过期记录清理 |
| **合计** | **72** | — |

### 1.2 覆盖范围

下表按被测能力汇总，每个用例只归属一个分组，合计 72 个（与 §3 清单一致）。

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例与生命周期 | 6 | `BackgroundTaskManager()`、`shutdown()`、`_is_shutdown`、`_instance` |
| 同步任务注册 | 1 | `register_sync_task()` |
| 异步任务注册与取消 | 2 | `register_async_task()`、`cancel_task()` |
| 定时任务注册、查询与注销 | 6 | `register_scheduled_task_factory()`、`restore_scheduled_tasks()`、`get_scheduled_tasks()`、`unregister_scheduled_task()` |
| 长时任务注册、停止与状态 | 10 | `register_long_running_task()`、`stop_long_running_task()`、`update_long_running_task_status()`、`is_long_task_running()` |
| 任务查询与清理 | 3 | `get_task()`、`get_all_tasks()`、`clear_completed_tasks()` |
| shutdown 与资源清理（R-03） | 3 | `shutdown()`、`executor.shutdown(wait=True, cancel_futures=True)` |
| 定时任务恢复（R-06） | 2 | `register_scheduled_task_factory()` → `restore_scheduled_tasks()` |
| 长时任务自动重启 | 1 | 长时任务失败后的重启等待路径 |
| 任务执行超时清理 | 1 | `cancel_task()` 的资源清理行为 |
| 任务模型枚举 | 2 | `TaskType`、`TaskStatus` |
| 任务模型序列化往返 | 6 | `BackgroundTask` / `ScheduledTask` / `LongRunningTask` 的 `to_dict()` / `from_dict()`、`calculate_next_run()` |
| 任务状态转换 | 4 | `mark_running()`、`mark_completed()`、`mark_failed()`、`mark_cancelled()` |
| 任务线程本地存储 | 3 | `TaskThreadLocal.set_current_task()` / `get_current_task()` / `clear_current_task()` |
| TaskStorage 单例与初始化 | 3 | `TaskStorage()`、`load_data()` |
| TaskStorage CRUD | 12 | `save_task()` / `get_task()` / `get_all_tasks()` / `get_tasks_by_plugin()` / `delete_task()`、`save_scheduled_task()` / `get_scheduled_task()` / `update_scheduled_task()` / `delete_scheduled_task()`、`save_long_running_task()` / `get_long_running_task()` / `get_long_running_tasks_by_plugin()` / `delete_long_running_task()` |
| TaskStorage 缓存、回退与清理 | 7 | `load_data()`、`save_data()`、`clear_cache()`、`clear_completed_tasks()`、`cleanup_old_tasks()` |

---

## 2. 测试策略

### 2.1 隔离措施

- **单例重置**：`test/conftest.py` 的 autouse fixture `reset_singletons` 在每个用例前后重置 `BackgroundTaskManager._instance` / `_initialized` 与 `TaskStorage._instance`（重置前会先尝试 `shutdown()`）；同文件 autouse fixture `mock_logger` 替换各处 `LoggerManager`，避免写入 `logs/`。
- **background_task 类测试**（`test_background_task.py`、`test_background_task_shutdown.py`）：由 `_make_btm(mocker)` 构建 Manager，`TaskStorage`、`ThreadPoolExecutor`、`TaskScheduler`、`SchedulerCallback` 全部被 mock，并 patch `time.sleep` 与 `threading.Thread`；用例内还会显式把 `BackgroundTaskManager._instance` / `_initialized` 置空，之后正常构造实例（`__init__` 在依赖被 mock 的前提下真实执行）。
- **task_model 测试**：纯数据模型用例，不涉及 I/O 与线程；仅 `TestTaskThreadLocal::test_thread_local_isolation` 创建一个真实 `threading.Thread` 验证线程隔离。
- **task_storage 测试**：使用真实 `TaskStorage` + `tmp_path` 临时目录（`storage` fixture），每个用例独立的 `tasks.json`，不触碰项目 `data/` 目录。

### 2.2 测试数据

- Mock 函数与回调由 `unittest.mock.MagicMock` 提供，可配置返回值；存储桩初始化为空数据（`get_task → None`，各 `get_* → []`）。
- 任务 ID 使用字符串（如 `"task-1"`、`"scheduled-task-001"`、`"t1"`）。
- 状态使用 `TaskStatus` 枚举值（`PENDING` / `RUNNING` / `COMPLETED` / `FAILED` / `CANCELLED` / `STOPPED`）。
- 序列化往返用例显式指定 `created_at` / `started_at` / `finished_at` 等时间戳，保证比较可预期。

### 2.3 关键辅助函数与 fixtures

```python
# test_background_task.py:22-68、test_background_task_shutdown.py:28-72
def _make_btm(mocker):
    """
    Return a fully-initialised BackgroundTaskManager with all heavy deps mocked.
    Uses __new__ patch so the singleton machinery is bypassed.
    """
    # Mock TaskStorage / ThreadPoolExecutor / TaskScheduler / SchedulerCallback
    # 返回 (manager, mock_storage, mock_executor, mock_scheduler) 四元组
```

> 注：`_make_btm()` 的 docstring 写作 "Uses __new__ patch"，但实现方式是重置类级单例属性后直接实例化；`test_background_task.py:15` 在模块导入期另存了真实 `__new__`（`_REAL_BTM_NEW`），该变量在 `_make_btm()` 中未被使用。

| fixture / 辅助 | 定义位置 | 作用 |
|---------------|---------|------|
| `_make_btm(mocker)` | `test_background_task.py:22`、`test_background_task_shutdown.py:28` | 构造依赖全 mock 的 Manager，返回四元组 |
| `btm_objects` | `test/core/task/conftest.py:17` | 返回 `_make_btm()` 的四元组；同名 fixture 亦在两个 background_task 测试文件内本地重定义（`test_background_task.py:75`、`test_background_task_shutdown.py:79`） |
| `manager` | `test_background_task.py:81`、`test_background_task_shutdown.py:85` | 只返回 Manager 本身 |
| `mock_task` | `test/core/task/conftest.py:70` | 返回一个 `MagicMock` 背景任务（`task_id` / `name` / `plugin_id` / `status`） |
| `storage` | `test_task_storage.py:15` | 返回以 `tmp_path` 为数据目录的 `TaskStorage` |
| `reset_singletons` | `test/conftest.py:29`（autouse） | 每个用例前后重置各单例 |
| `mock_logger` | `test/conftest.py:166`（autouse） | 禁用 `LoggerManager` 实际写日志 |

> 注：两个 background_task 测试文件中的 `btm_objects` / `manager` fixture 当前未被用例使用——用例内均直接调用 `_make_btm(mocker)`。

---

## 3. 测试用例

> **清单来源约定**：`说明` 列严格取自代码中该测试函数的 **docstring 首句**，无 docstring 时取 **紧邻的分段注释**（`test_background_task.py` 中的编号注释）；两者均缺失时（集中在 `test_task_storage.py`）仅按函数名与所在测试类归纳被测操作，**不补充代码之外的断言细节、测试步骤或优先级**。
> **分组方式**：按「测试文件 → 测试类」分组；`test_background_task.py` 全部为模块级测试函数（无测试类）。每个用例在本文中有且仅有一行。

### 3.1 `test_background_task.py`（28 个用例，模块级测试函数）

| 用例函数名 | 说明 |
|-----------|------|
| `test_singleton_returns_same_instance` | 连续两次调用 `BackgroundTaskManager()` 必须返回同一对象 |
| `test_register_sync_task_executes_immediately` | `register_sync_task()` 立即执行，并返回 task_id、触发 callback |
| `test_register_async_task_submits_to_executor` | `register_async_task()` 提交到执行器并返回 task_id |
| `test_register_async_task_after_shutdown_returns_none` | shutdown 之后再注册异步任务返回 None |
| `test_cancel_task_cancels_and_marks_cancelled` | `cancel_task()` 取消 future 并标记为 CANCELLED |
| `test_get_task_falls_back_to_storage` | 任务不在运行时表时 `get_task()` 回退到存储查询 |
| `test_register_scheduled_task_factory_calls_restore` | `register_scheduled_task_factory()` 会调用 `restore_scheduled_tasks()` |
| `test_restore_scheduled_tasks_skips_func_set_and_disabled` | `restore_scheduled_tasks()` 跳过 func 已设置的任务与已禁用的任务 |
| `test_register_long_running_task_auto_restart_true` | `register_long_running_task(auto_restart=True)` 返回 task_id |
| `test_register_long_running_task_after_shutdown_returns_none` | shutdown 之后再注册长时任务返回 None |
| `test_stop_long_running_task_delete_false_updates_status_only` | `stop_long_running_task(delete_from_storage=False)` 仅更新状态 |
| `test_stop_long_running_task_delete_true_deletes_from_storage` | `stop_long_running_task(delete_from_storage=True)` 删除存储记录 |
| `test_shutdown_sets_is_shutdown_true` | `shutdown()` 置 `_is_shutdown=True` |
| `test_shutdown_rejects_async_tasks` | `shutdown()` 拒绝新异步任务（返回 None） |
| `test_shutdown_clears_singleton_instance` | `shutdown()` 清空 `BackgroundTaskManager._instance` |
| `test_update_long_running_task_status_calls_callback` | `update_long_running_task_status()` 调用 status_callback |
| `test_get_all_tasks_combines_running_and_stored` | `get_all_tasks()` 返回运行中与已存储的全部任务 |
| `test_get_scheduled_tasks_returns_list` | `get_scheduled_tasks()` 返回定时任务列表 |
| `test_clear_completed_tasks_delegates_to_storage` | `clear_completed_tasks()` 委托给存储层 |
| `test_unregister_scheduled_task_removes_running_and_storage` | 启用态定时任务注销：同时摘除运行表并删除存储记录 |
| `test_unregister_scheduled_task_disabled_task_deletes_storage` | 回归：禁用态定时任务（不在运行表、存储记录仍在）必须可注销 |
| `test_unregister_scheduled_task_not_found_returns_false` | 存储中不存在的任务注销返回 False（不存在的判定以存储为准） |
| `test_is_long_task_running_true_when_in_running_table` | 任务在运行时表中时返回 True |
| `test_is_long_task_running_unaffected_by_status_text` | 回归：插件上报自由文本状态后运行态判定不受影响 |
| `test_is_long_task_running_false_when_not_in_table` | 任务不在运行时表中（停止/不存在）返回 False |
| `test_stop_long_task_removes_stopped_storage_residue` | 回归：已停止（不在运行时表）但存储残留的记录可经停止（删除语义）清除 |
| `test_stop_long_task_missing_record_returns_false` | 不在运行时表且存储无记录：删除语义返回 False |
| `test_stop_long_task_not_running_no_delete_returns_false` | 不在运行时表且 `delete_from_storage=False`：无停止对象，返回 False |

### 3.2 `test_background_task_shutdown.py`（7 个用例）

#### `TestShutdownTaskLoss` — shutdown 行为测试

| 用例函数名 | 说明 |
|-----------|------|
| `test_shutdown_waits_for_tasks_to_prevent_data_loss` | TC-TASK-021: shutdown 等待任务完成以防止数据丢失 |
| `test_shutdown_cleans_up_resources` | TC-TASK-022: shutdown 正确清理资源 |

#### `TestScheduledTaskRestore` — 定时任务恢复测试

| 用例函数名 | 说明 |
|-----------|------|
| `test_scheduled_tasks_restore_after_init` | TC-TASK-023: 定时任务在 Manager 初始化后自动恢复 |
| `test_restore_called_during_init` | TC-TASK-024: `_restore_all_scheduled_tasks` 在 init 中被调用 |

#### `TestLongRunningTaskRestart` — 长时任务重启测试

| 用例函数名 | 说明 |
|-----------|------|
| `test_long_running_task_auto_restart_delay` | TC-TASK-025: 长时任务自动重启间隔 |

#### `TestTaskExecutionTimeout` — 任务超时清理测试

| 用例函数名 | 说明 |
|-----------|------|
| `test_task_timeout_cleanup` | TC-TASK-026: 任务执行超时后的清理行为 |

#### `TestShutdownEmptyQueue` — 空任务队列 shutdown 测试

| 用例函数名 | 说明 |
|-----------|------|
| `test_shutdown_with_empty_queue` | TC-TASK-027: 空任务队列时的 shutdown |

> 本文件是唯一保留 `TC-TASK-0NN` 编号的测试文件：编号写在用例 docstring 首句与段落注释中（如 `test_background_task_shutdown.py:92`、`:100`）。

### 3.3 `test_task_model.py`（15 个用例）

#### `TestTaskTypeEnum` — TaskType 枚举取值

| 用例函数名 | 说明 |
|-----------|------|
| `test_task_type_values` | TaskType 枚举值与预期字符串一致 |

#### `TestTaskStatusEnum` — TaskStatus 枚举取值

| 用例函数名 | 说明 |
|-----------|------|
| `test_task_status_values` | TaskStatus 枚举值与预期字符串一致 |

#### `TestBackgroundTaskRoundtrip` — BackgroundTask 序列化往返

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_dict_from_dict_preserves_all_fields` | 序列化往返保留全部字段 |
| `test_uuid_is_auto_generated` | BackgroundTask 的 uuid 由 default_factory 自动生成 |

#### `TestBackgroundTaskStateTransitions` — BackgroundTask 状态转换

| 用例函数名 | 说明 |
|-----------|------|
| `test_mark_running_sets_status_and_started_at` | `mark_running()` 置状态为 RUNNING 并填充 started_at |
| `test_mark_completed_sets_status_result_and_finished_at` | `mark_completed()` 置状态为 COMPLETED，并写入 result 与 finished_at |
| `test_mark_failed_sets_status_error_and_finished_at` | `mark_failed()` 置状态为 FAILED，并写入 error 与 finished_at |
| `test_mark_cancelled_sets_status_and_finished_at` | `mark_cancelled()` 置状态为 CANCELLED 并写入 finished_at |

#### `TestScheduledTaskRoundtrip` — ScheduledTask 序列化往返

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_dict_from_dict_preserves_all_fields` | 序列化往返保留全部字段 |
| `test_calculate_next_run_sets_future_time` | `calculate_next_run()` 将 next_run 置为未来时间（当前时间 + interval） |

#### `TestLongRunningTaskRoundtrip` — LongRunningTask 序列化往返

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_dict_from_dict_preserves_all_fields` | 序列化往返保留全部字段（含 auto_restart） |
| `test_auto_restart_default_true` | `LongRunningTask.auto_restart` 默认为 True |

#### `TestTaskThreadLocal` — 任务线程本地存储

| 用例函数名 | 说明 |
|-----------|------|
| `test_set_and_get_current_task` | `set_current_task()` / `get_current_task()` 存取任务 |
| `test_clear_current_task_removes_association` | `clear_current_task()` 移除任务关联 |
| `test_thread_local_isolation` | 在一个线程中设置的任务对另一个线程不可见 |

### 3.4 `test_task_storage.py`（22 个用例）

#### `TestSingleton` — 单例

| 用例函数名 | 说明 |
|-----------|------|
| `test_same_instance` | 同一实例（多次构造返回同一 TaskStorage 对象） |

#### `TestInitialization` — 初始化

| 用例函数名 | 说明 |
|-----------|------|
| `test_creates_default_file_when_missing` | 存储文件缺失时创建默认文件 |
| `test_uses_existing_file` | 使用已存在的存储文件 |

#### `TestBackgroundTaskCrud` — 背景任务 CRUD

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_and_get_task` | `save_task()` / `get_task()` 往返 |
| `test_get_task_returns_none_for_missing` | 查询不存在的任务返回 None |
| `test_get_all_tasks` | `get_all_tasks()` 返回全部任务 |
| `test_get_tasks_by_plugin` | `get_tasks_by_plugin()` 按插件过滤 |
| `test_delete_task_removes_and_returns_true` | `delete_task()` 删除记录并返回 True |
| `test_delete_task_returns_false_for_missing` | 删除不存在的任务返回 False |

#### `TestClearCompletedTasks` — 清理已完成任务

| 用例函数名 | 说明 |
|-----------|------|
| `test_clears_completed_failed_cancelled` | 清理 completed / failed / cancelled 任务记录 |
| `test_clear_completed_tasks_filters_by_plugin` | `clear_completed_tasks()` 按插件过滤 |

#### `TestScheduledTaskCrud` — 定时任务 CRUD

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_and_get_scheduled_task` | 定时任务 `save_scheduled_task()` / `get_scheduled_task()` 往返 |
| `test_update_scheduled_task` | `update_scheduled_task()` 更新定时任务字段 |
| `test_delete_scheduled_task` | `delete_scheduled_task()` 删除定时任务记录 |

#### `TestLongRunningTaskCrud` — 长时任务 CRUD

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_and_get_long_running_task` | 长时任务 `save_long_running_task()` / `get_long_running_task()` 往返 |
| `test_get_long_running_tasks_by_plugin` | `get_long_running_tasks_by_plugin()` 按插件过滤 |
| `test_delete_long_running_task` | `delete_long_running_task()` 删除长时任务记录 |

#### `TestCorruptionFallback` — 损坏回退

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_data_returns_default_on_corrupted_json` | JSON 损坏时 `load_data()` 返回默认数据结构 |

#### `TestCacheBehavior` — 缓存行为

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_data_returns_copy` | `load_data()` 返回副本 |
| `test_save_data_writes_cache` | `save_data()` 写入缓存 |

#### `TestCleanupOldTasks` — 过期任务清理

| 用例函数名 | 说明 |
|-----------|------|
| `test_cleanup_old_tasks_removes_completed_records` | cleanup_old_tasks 删除超过保留天数的已完成任务 |
| `test_cleanup_old_tasks_keeps_long_running_tasks` | cleanup_old_tasks 不清理长期任务记录 |

### 3.5 风险关联用例（R-03 / R-06）

原文档的风险编号体系保留如下，覆盖状态按**当前代码实际行为**据实标注。

#### R-03：shutdown 不等待任务完成可能导致任务丢失

**覆盖状态**：已覆盖（代码已修复为等待任务完成）。

| 用例函数名 | 说明 |
|-----------|------|
| `TestShutdownTaskLoss::test_shutdown_waits_for_tasks_to_prevent_data_loss` | TC-TASK-021: shutdown 等待任务完成以防止数据丢失 |
| `TestShutdownTaskLoss::test_shutdown_cleans_up_resources` | TC-TASK-022: shutdown 正确清理资源 |

- 依据（代码）：`core/task/background_task.py:1291` 实际调用 `self._executor.shutdown(wait=True, cancel_futures=True)`（在独立守护线程中限时等待运行中任务结束，上限 `EXECUTOR_SHUTDOWN_TIMEOUT`，见同文件 `:1289-1300`）。
- 依据（用例）：断言位于 `test/core/task/test_background_task_shutdown.py:136`（`mock_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=True)`）；资源清理断言位于同文件 `:184-187`（清空 `_running_tasks` / `_running_long_running_tasks` / `_futures`，并置 `_is_shutdown=True`）。
- 附带覆盖：`test_background_task_shutdown.py:446`（`TestShutdownEmptyQueue::test_shutdown_with_empty_queue`）同样断言 `wait=True, cancel_futures=True`。
- 更正说明：原文档"验证 `executor.shutdown(wait=False)` 被调用 / 警告：任务可能未完成就被强制终止"的结论与当前代码不符，已按实测改为"已覆盖（已修复）"。

#### R-06：`_restore_all_scheduled_tasks` 未在 init 调用

**覆盖状态**：已覆盖（以"锁定当前行为"的方式），但**当前代码中已不存在 `_restore_all_scheduled_tasks` 方法**。

| 用例函数名 | 说明 |
|-----------|------|
| `TestScheduledTaskRestore::test_scheduled_tasks_restore_after_init` | TC-TASK-023: 定时任务在 Manager 初始化后自动恢复 |
| `TestScheduledTaskRestore::test_restore_called_during_init` | TC-TASK-024: `_restore_all_scheduled_tasks` 在 init 中被调用 |

- 依据（代码）：全 `core/` 检索 `_restore_all_scheduled_tasks` 无匹配；`BackgroundTaskManager.__init__`（`core/task/background_task.py:97-164`）不触发任何定时任务恢复；实际恢复路径为 `register_scheduled_task_factory()`（同文件 `:479`）→ `restore_scheduled_tasks()`（`:502`），后者按插件读取存储（`self._storage.get_scheduled_tasks_by_plugin(plugin_id)`，`:515`）。
- 依据（用例）：`test_restore_called_during_init` 的实际断言是 `mock_storage.get_all_scheduled_tasks.assert_not_called()`（`test/core/task/test_background_task_shutdown.py:296`），即验证 `__init__` 期间**未**做全量定时任务恢复这一现状；其 docstring 标题沿用旧编号表述。
- 依据（用例）：`test_scheduled_tasks_restore_after_init` 通过 `register_scheduled_task_factory(...)`（同文件 `:235-239`）触发恢复，并断言任务进入 `_running_scheduled_tasks` 且 `func` / `callback` 被还原（`:242-247`）。
- 阅读提示：结合当前实现，该用例 docstring 中的"初始化后自动恢复"应理解为"插件注册工厂后恢复"。

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/task/` 添加新功能时：

1. 按被测对象选择测试文件：
   - `background_task.py` 的注册/查询/生命周期 → `test_background_task.py`
   - shutdown、恢复、重启、超时清理类行为 → `test_background_task_shutdown.py`
   - 数据模型（`task_model.py`） → `test_task_model.py`
   - 存储层（`task_storage.py`） → `test_task_storage.py`
2. `background_task` 相关用例使用 `_make_btm(mocker)`（或 `btm_objects` / `manager` fixture）创建依赖全 mock 的 Manager；存储层用例使用 `storage` fixture（基于 `tmp_path`）。
3. 新增用例需写中文 docstring，首句为单句摘要；同时在本文件 §3 对应表格中新增一行，`说明` 取该 docstring 首句。

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查 `_make_btm()` 的 mock 配置是否覆盖了目标依赖
4. 如果出现跨用例污染，确认 `test/conftest.py` 的 autouse fixture `reset_singletons` / `mock_logger` 是否生效，以及 `BackgroundTaskManager._instance` / `TaskStorage._instance` 是否已重置

### 4.3 覆盖率与未覆盖路径

- 覆盖率不在本仓库中记录为固定数值；如需统计（`pytest-cov` 已在 `.[test]` 中声明）：

  ```powershell
  .venv\Scripts\python.exe -m pytest test/core/task -q --cov=core/task --cov-report=term-missing -p no:cacheprovider
  ```

- 当前测试未覆盖（或未断言）的关键路径：
  - `TaskScheduler` / `SchedulerCallback` 的真实调度逻辑——background_task 类测试中两者均被 mock
  - 真实线程池执行与 `_execute_async_task` / `_execute_callback` 的异常链路——`ThreadPoolExecutor` 被 mock，仅 `test_task_model.py::TestTaskThreadLocal::test_thread_local_isolation` 创建了真实线程
  - 长时任务自动重启的真实等待与重启循环——`TestLongRunningTaskRestart::test_long_running_task_auto_restart_delay` 仅构造并触发任务函数，未对 `time.sleep(5)` 或重启次数做断言（`test_background_task_shutdown.py:341-352`）
  - 存储损坏时的备份产物 `_backup_corrupt_file()`——`TestCorruptionFallback::test_load_data_returns_default_on_corrupted_json` 只断言回退默认结构
  - 定时任务检查线程 `_check_scheduled_tasks()` 的到期触发与跳过逻辑

---

## 5. 相关文档

- [任务系统概述](../../docs/core/background-task/overview.md)
- [任务 API 参考](../../docs/core/background-task/api-reference.md)
- [任务存储](../../docs/core/background-task/task-storage.md)
- [测试主文档](../TESTING.md)

---
