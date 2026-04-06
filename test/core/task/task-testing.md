# 任务系统测试文档

> 后台任务系统模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/task/`
**测试文件数**: 2 个
**测试用例总数**: 27+ 个

### 1.1 测试文件分布

| 测试文件 | 测试用例数 | 主要覆盖 |
|---------|-----------|---------|
| `test_background_task.py` | 20+ | BackgroundTaskManager 单例、任务注册、执行、取消、shutdown |
| `test_task_model.py` | 5+ | TaskModel 状态、结果、错误 |

### 1.2 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例模式 | 1 | `BackgroundTaskManager()` |
| 同步任务注册 | 3 | `register_sync_task()` |
| 异步任务注册 | 3 | `register_async_task()` |
| 长时任务注册 | 3 | `register_long_running_task()` |
| 任务取消 | 2 | `cancel_task()` |
| 任务获取 | 2 | `get_task()`, `get_all_tasks()` |
| Shutdown 行为 | 2 | `shutdown()` |
| 任务状态 | 3 | `TaskModel`, `status`, `result`, `error` |
| 任务存储 | 2 | `TaskStorage`, `save()`, `load()` |
| Shutdown 任务丢失 (R-03) | 2 | `executor.shutdown(wait=False)` |
| 定时任务恢复 (R-06) | 2 | `_restore_all_scheduled_tasks()` |
| 任务执行边界 | 2 | 超时清理、空队列 shutdown |

---

## 2. 测试策略

### 2.1 隔离措施

- `BackgroundTaskManager` 单例由 `reset_singletons` fixture 自动重置
- 使用 `_make_btm()` 辅助函数创建完全 mock 的 BackgroundTaskManager
- `TaskStorage`, `ThreadPoolExecutor`, `TaskScheduler` 都被 mock
- 不实际创建线程或访问文件系统

### 2.2 测试数据

- Mock 函数返回可配置的值
- 任务 ID 使用字符串
- 状态枚举使用 `TaskStatus` 枚举值

### 2.3 关键辅助函数

```python
# test_background_task.py
def _make_btm(mocker):
    """
    返回完全初始化的 BackgroundTaskManager，所有外部依赖都被 mock。
    使用 __new__ patch 绕过单例机制。
    """
    # Mock TaskStorage, ThreadPoolExecutor, TaskScheduler
    # 返回 (manager, mock_storage, mock_executor, mock_scheduler)
```

---

## 3. 测试用例

### 3.1 BackgroundTaskManager 单例模式

#### TC-TASK-001: 单例返回相同实例
- **测试类**: (模块级测试)
- **测试函数**: `test_singleton_returns_same_instance`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 重置单例状态
  2. 调用 `_make_btm()` 创建实例
  3. 再次调用 `BackgroundTaskManager()`
  4. 验证返回同一对象
- **预期结果**: `mgr1 is mgr2`

---

### 3.2 同步任务注册

#### TC-TASK-002: register_sync_task 立即执行
- **测试类**: TestRegisterSyncTask
- **测试函数**: `test_register_sync_task_executes_immediately`
- **优先级**: P0
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 创建 mock 函数返回 42
  2. 调用 `register_sync_task(func, callback)`
  3. 验证函数被调用
- **预期结果**: 函数被立即执行，返回 42

#### TC-TASK-003: register_sync_task 返回 task_id
- **测试类**: TestRegisterSyncTask
- **测试函数**: `test_register_sync_task_returns_task_id`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 调用 `register_sync_task(func, callback)`
  2. 验证返回值包含 task_id
- **预期结果**: 返回 task_id 字符串

#### TC-TASK-004: register_sync_task 回调被调用
- **测试类**: TestRegisterSyncTask
- **测试函数**: `test_register_sync_task_callback_invoked`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 创建 mock callback
  2. 调用 `register_sync_task(func, callback)`
  3. 验证 callback 被调用
- **预期结果**: callback 收到正确参数

---

### 3.3 异步任务注册

#### TC-TASK-005: register_async_task 提交到线程池
- **测试类**: TestRegisterAsyncTask
- **测试函数**: `test_register_async_task_submits_to_executor`
- **优先级**: P0
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 创建 async 函数
  2. 调用 `register_async_task(func, callback)`
  3. 验证 executor.submit 被调用
- **预期结果**: 任务被提交到线程池

#### TC-TASK-006: register_async_task 返回 task_id
- **测试类**: TestRegisterAsyncTask
- **测试函数**: `test_register_async_task_returns_task_id`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 调用 `register_async_task(func, callback)`
  2. 验证返回值包含 task_id
- **预期结果**: 返回 task_id 字符串

#### TC-TASK-007: 异步任务结果通过回调返回
- **测试类**: TestRegisterAsyncTask
- **测试函数**: `test_async_task_result_via_callback`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 创建返回值的 async 函数
  2. 调用 `register_async_task(func, callback)`
  3. 验证 callback 收到结果
- **预期结果**: callback 收到正确结果

---

### 3.4 长时任务注册

#### TC-TASK-008: register_long_running_task 注册长时任务
- **测试类**: TestRegisterLongRunningTask
- **测试函数**: `test_register_long_running_task`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 创建长时任务函数
  2. 调用 `register_long_running_task(func, callback)`
- **预期结果**: 任务被注册，返回 task_id

#### TC-TASK-009: 长时任务独立追踪
- **测试类**: TestRegisterLongRunningTask
- **测试函数**: `test_long_running_tasks_tracked_separately`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 注册长时任务
  2. 获取所有长时任务
- **预期结果**: 长时任务独立于普通任务追踪

---

### 3.5 任务取消

#### TC-TASK-010: cancel_task 取消任务
- **测试类**: TestCancelTask
- **测试函数**: `test_cancel_task_cancels`
- **优先级**: P1
- **前置条件**: 任务已注册
- **测试步骤**:
  1. 注册任务
  2. 调用 `cancel_task(task_id)`
  3. 验证任务被取消
- **预期结果**: 任务状态变为 cancelled

#### TC-TASK-011: 取消不存在任务无异常
- **测试类**: TestCancelTask
- **测试函数**: `test_cancel_nonexistent_no_error`
- **优先级**: P2
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 调用 `cancel_task("nonexistent-id")`
- **预期结果**: 无异常，或返回 False

---

### 3.6 任务获取

#### TC-TASK-012: get_task 返回任务
- **测试类**: TestGetTask
- **测试函数**: `test_get_task_returns_task`
- **优先级**: P1
- **前置条件**: 任务已注册
- **测试步骤**:
  1. 注册任务
  2. 调用 `get_task(task_id)`
- **预期结果**: 返回 TaskModel

#### TC-TASK-013: get_all_tasks 返回所有任务
- **测试类**: TestGetAllTasks
- **测试函数**: `test_get_all_tasks`
- **优先级**: P1
- **前置条件**: 多个任务已注册
- **测试步骤**:
  1. 注册多个任务
  2. 调用 `get_all_tasks()`
- **预期结果**: 返回所有任务的列表

---

### 3.7 Shutdown 行为

#### TC-TASK-014: shutdown 等待所有任务完成
- **测试类**: TestShutdown
- **测试函数**: `test_shutdown_waits_for_tasks`
- **优先级**: P1
- **前置条件**: 任务正在执行
- **测试步骤**:
  1. 注册多个任务
  2. 调用 `shutdown()`
- **预期结果**: 所有任务完成或取消

#### TC-TASK-015: shutdown 关闭执行器
- **测试类**: TestShutdown
- **测试函数**: `test_shutdown_closes_executor`
- **优先级**: P1
- **前置条件**: Manager 已创建
- **测试步骤**:
  1. 调用 `shutdown()`
  2. 验证 executor.shutdown 被调用
- **预期结果**: 执行器被关闭

---

### 3.8 TaskModel 任务模型

#### TC-TASK-016: TaskModel 状态转换
- **测试类**: TestTaskModel
- **测试函数**: `test_task_model_status_transitions`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 TaskModel
  2. 更新状态
  3. 验证状态转换正确
- **预期结果**: pending → running → completed

#### TC-TASK-017: TaskModel 结果存储
- **测试类**: TestTaskModel
- **测试函数**: `test_task_model_stores_result`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 TaskModel
  2. 设置结果
  3. 获取结果
- **预期结果**: 结果被正确存储

#### TC-TASK-018: TaskModel 错误处理
- **测试类**: TestTaskModel
- **测试函数**: `test_task_model_stores_error`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 TaskModel
  2. 设置错误
  3. 获取错误
- **预期结果**: 错误被正确存储

---

### 3.9 任务存储

#### TC-TASK-019: TaskStorage 保存任务
- **测试类**: TestTaskStorage
- **测试函数**: `test_task_storage_save`
- **优先级**: P1
- **前置条件**: TaskStorage 已创建
- **测试步骤**:
  1. 创建 TaskModel
  2. 调用 `save(task)`
- **预期结果**: 任务被保存

#### TC-TASK-020: TaskStorage 加载任务
- **测试类**: TestTaskStorage
- **测试函数**: `test_task_storage_load`
- **优先级**: P1
- **前置条件**: 任务已保存
- **测试步骤**:
  1. 保存任务
  2. 调用 `load(task_id)`
- **预期结果**: 返回任务

---

### 3.10 Shutdown 任务丢失风险 (R-03 风险覆盖)

#### TC-TASK-021: shutdown 不等待任务完成导致数据丢失
- **测试类**: TestShutdownTaskLoss
- **测试函数**: `test_shutdown_with_wait_false_may_lose_tasks`
- **优先级**: P1
- **前置条件**: 有正在执行的任务
- **测试步骤**:
  1. 注册一个异步任务
  2. 在任务执行过程中调用 `shutdown()`
  3. 验证 `executor.shutdown(wait=False)` 被调用
- **预期结果**: 警告：任务可能未完成就被强制终止
- **风险关联**: R-03

#### TC-TASK-022: shutdown 正确清理资源
- **测试类**: TestShutdownCleanup
- **测试函数**: `test_shutdown_cleans_up_resources`
- **优先级**: P1
- **前置条件**: 有注册的任务
- **测试步骤**:
  1. 注册多个任务
  2. 调用 `shutdown()`
  3. 验证所有资源被清理
- **预期结果**: 无资源泄漏
- **风险关联**: R-03

---

### 3.11 定时任务恢复 (R-06 风险覆盖)

#### TC-TASK-023: 定时任务在 Manager 初始化后自动恢复
- **测试类**: TestScheduledTaskRestore
- **测试函数**: `test_scheduled_tasks_restore_after_init`
- **优先级**: P1
- **前置条件**: 存在已保存的定时任务
- **测试步骤**:
  1. 保存一个定时任务到存储
  2. 创建新的 BackgroundTaskManager 实例
  3. 验证定时任务被自动恢复
- **预期结果**: 定时任务被重新调度
- **风险关联**: R-06

#### TC-TASK-024: _restore_all_scheduled_tasks 在 init 中被调用
- **测试类**: TestScheduledTaskRestore
- **测试函数**: `test_restore_called_during_init`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. Mock `TaskStorage.load_all_scheduled_tasks()`
  2. 创建 BackgroundTaskManager 实例
  3. 验证 `load_all_scheduled_tasks()` 被调用
- **预期结果**: 初始化时调用恢复方法
- **风险关联**: R-06

---

### 3.12 长时任务自动重启

#### TC-TASK-025: 长时任务自动重启间隔
- **测试类**: TestLongRunningTaskRestart
- **测试函数**: `test_long_running_task_auto_restart_delay`
- **优先级**: P2
- **前置条件**: 长时任务正在运行
- **测试步骤**:
  1. 注册长时任务
  2. 任务崩溃
  3. 验证重启前有 5 秒等待
- **预期结果**: 重启间隔为 5 秒

---

### 3.13 任务执行边界条件

#### TC-TASK-026: 任务执行超时后的清理行为
- **测试类**: TestTaskExecutionTimeout
- **测试函数**: `test_task_timeout_cleanup`
- **优先级**: P2
- **前置条件**: 任务正在执行
- **测试步骤**:
  1. 注册一个长时间运行的任务
  2. 设置超时时间
  3. 等待任务超时
  4. 验证资源被清理
- **预期结果**: 超时后任务被清理，无资源泄漏

#### TC-TASK-027: 空任务队列时的 shutdown
- **测试类**: TestShutdownEmptyQueue
- **测试函数**: `test_shutdown_with_empty_queue`
- **优先级**: P2
- **前置条件**: 无注册任务
- **测试步骤**:
  1. 创建 BackgroundTaskManager 实例
  2. 不注册任何任务
  3. 调用 `shutdown()`
- **预期结果**: shutdown 正常完成，无异常

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/task/` 添加新功能时：
1. 在 `test_background_task.py` 或 `test_task_model.py` 中添加测试
2. 使用 `_make_btm()` 辅助函数创建隔离的 Manager
3. 遵循 TC-TASK-XXX 格式的 docstring

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查 `_make_btm()` 是否正确

### 4.3 覆盖率目标

- 当前覆盖率: ~80%
- 目标覆盖率: 85%
- 未覆盖的关键路径:
  - 真实线程执行
  - 任务调度器复杂逻辑
  - 错误恢复场景

---

## 5. 相关文档

- [任务系统概述](../../docs/core/task/overview.md)
- [任务 API 参考](../../docs/core/task/api-reference.md)
- [测试主文档](../TESTING.md)

---
