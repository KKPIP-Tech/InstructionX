# TaskStorage 任务持久化存储

> 后台任务数据的持久化管理，支持原子写入和缓存机制

---

## 1. 概述

`TaskStorage` 是 [BackgroundTaskManager](overview.md) 的持久化层，负责将任务数据保存到 `data/tasks.json` 文件中。

**注意**: `TaskStorage` 是 `BackgroundTaskManager` 的内部持久化层。插件通过 `BackgroundTaskManager` 间接使用，无需直接调用此类。

**文件位置**: `core/task/task_storage.py`

**模式**: 单例模式

---

## 2. 核心特性

- **单例模式**: 全局唯一实例
- **原子写入**: 使用临时文件 + 重命名保证数据一致性
- **内存缓存**: 维护内存缓存，减少磁盘 I/O
- **脏标记**: 使用脏标记避免不必要的写入
- **分离存储**: 异步任务、定时任务、长期任务分开存储

---

## 3. 存储文件

**文件位置**: `data/tasks.json`

**结构**:
```json
{
    "tasks": {
        "<task_id>": { ... }
    },
    "scheduled_tasks": {
        "<task_id>": { ... }
    },
    "long_running_tasks": {
        "<task_id>": { ... }
    }
}
```

---

## 4. 异步任务管理

### save_task()

```python
def save_task(self, task: BackgroundTask)
```

保存或更新异步任务。

### get_task()

```python
def get_task(self, task_id: str) -> Optional[BackgroundTask]
```

根据 ID 获取任务。

### get_all_tasks()

```python
def get_all_tasks(self) -> List[BackgroundTask]
```

获取所有异步任务。

### get_tasks_by_plugin()

```python
def get_tasks_by_plugin(self, plugin_id: str) -> List[BackgroundTask]
```

获取指定插件的所有异步任务。

### delete_task()

```python
def delete_task(self, task_id: str) -> bool
```

删除指定任务。

### clear_completed_tasks()

```python
def clear_completed_tasks(self, plugin_id: Optional[str] = None) -> int
```

清理已完成的任务。返回清理数量。

---

## 5. 定时任务管理

### save_scheduled_task()

```python
def save_scheduled_task(self, task: ScheduledTask)
```

保存或更新定时任务。

### get_scheduled_task()

```python
def get_scheduled_task(self, task_id: str) -> Optional[ScheduledTask]
```

根据 ID 获取定时任务。

### get_all_scheduled_tasks()

```python
def get_all_scheduled_tasks(self) -> List[ScheduledTask]
```

获取所有定时任务。

### get_scheduled_tasks_by_plugin()

```python
def get_scheduled_tasks_by_plugin(self, plugin_id: str) -> List[ScheduledTask]
```

获取指定插件的所有定时任务。

### delete_scheduled_task()

```python
def delete_scheduled_task(self, task_id: str) -> bool
```

删除定时任务。返回是否成功删除。

### update_scheduled_task()

```python
def update_scheduled_task(self, task: ScheduledTask)
```

更新定时任务。

---

## 6. 长期任务管理

### save_long_running_task()

```python
def save_long_running_task(self, task: LongRunningTask)
```

保存或更新长期任务。

### get_long_running_task()

```python
def get_long_running_task(self, task_id: str) -> Optional[LongRunningTask]
```

根据 ID 获取长期任务。

### get_all_long_running_tasks()

```python
def get_all_long_running_tasks(self) -> List[LongRunningTask]
```

获取所有长期任务。

### get_long_running_tasks_by_plugin()

```python
def get_long_running_tasks_by_plugin(self, plugin_id: str) -> List[LongRunningTask]
```

获取指定插件的所有长期任务。

### delete_long_running_task()

```python
def delete_long_running_task(self, task_id: str) -> bool
```

删除长期任务。返回是否成功删除。

### update_long_running_task()

```python
def update_long_running_task(self, task: LongRunningTask)
```

更新长期任务。

---

## 7. 缓存管理

### load_data()

```python
def load_data(self, force_reload: bool = False) -> Dict[str, Any]
```

从磁盘加载数据到缓存。返回数据字典；若缓存为空则默认返回 `{"tasks": {}, "scheduled_tasks": {}, "long_running_tasks": {}}`，正常情况下数据包含键 `tasks`、`scheduled_tasks`、`long_running_tasks`。`force_reload=True` 时强制从磁盘重新读取。

### save_data()

```python
def save_data(self) -> None
```

将当前缓存数据保存到磁盘。

### clear_cache()

```python
def clear_cache(self)
```

清除内存缓存。下次访问时从磁盘重新加载。

---

## 8. 原子写入机制

```python
def _write_to_disk(self, data: Dict[str, Any]) -> None:
    # 1. 写入临时文件
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 2. 原子重命名
    os.replace(temp_file, data_file)
```

---

## 9. 相关文档

- [后台任务概述](overview.md)
- [后台任务 API 参考](api-reference.md)
