# DataProvider 测试文档

> DataProvider 模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/data/data_provider.py`（含后端 `core/data/sqlite_backend.py`）
**测试文件**: `test/core/data/test_data_provider.py`（本模块测试文件数：1）
**测试类数量**: 16 个
**测试用例总数**: 36 个

> 最后一次核对：2026-09-14，实测命令
> `.venv\Scripts\python.exe -m pytest test/core/data --collect-only -q -p no:cacheprovider`
> → `36 tests collected`。本文档的用例清单与统计均以该命令的收集结果为准。

### 1.1 覆盖范围

| 测试类 | 用例数 | 代码中实际调用的 API |
|--------|-------|--------------------|
| TestSingleton | 2 | `DataProvider()`、`_backend.db_file` |
| TestRegisterUnregister | 4 | `register_plugin()`、`unregister_plugin()`、`set_plugin_data()`、`get_plugin_data()`、`_backend.plugin_exists()` |
| TestActiveInstance | 2 | `set_active_instance()`、`get_active_instance()` |
| TestPluginData | 4 | `set_plugin_data()`、`get_plugin_data()`（PRIVATE 命名空间、`default`、序列化校验） |
| TestPubSub | 3 | `subscribe()`、`set_plugin_data()`（PUBLIC / PRIVATE、`notify=False`） |
| TestCache | 2 | `load_data()`、`clear_cache()`、`save_data()`、`get_plugin_data()` |
| TestResetAllData | 1 | `reset_all_data()`、`get_plugin_data()` |
| TestMigration | 1 | 启动期 JSON → SQLite 迁移、`get_plugin_data()`、`get_active_instance()`、`_backend.plugin_exists()` |
| TestSchemaVersion | 1 | 经 `_backend.db_file` 读取 `db_metadata.schema_version` |
| TestSerializationCompatibility | 2 | `set_plugin_data()`、`get_plugin_data()`（IntEnum 键、NaN 拒绝） |
| TestLRUCache | 3 | `_backend._value_cache`（容量淘汰、写入失效） |
| TestMigrationFailure | 1 | `SQLiteBackend._migrate_json_to_sqlite`（monkeypatch 注入故障） |
| TestNotifyLockOrder | 2 | `_file_lock`、`subscribe()`、`set_plugin_data()` |
| TestConcurrency | 1 | `set_plugin_data()`、`get_plugin_data()`（多线程） |
| TestAssets | 4 | `save_asset()`、`load_asset()`、`get_asset_path()` |
| TestSchemaUpgrade | 3 | `db_metadata.schema_version` 校验与 legacy 库升级 |
| **合计** | **36** | — |

---

## 2. 测试策略

### 2.1 隔离措施

- 每个测试使用独立的 `DataProvider` 实例（由本文件内的 `_provider(tmp_path)` 辅助函数构造：先置 `DataProvider._instance = None`，再以 `data_dir=tmp_path, data_filename="test.json"` 新建）
- 磁盘 I/O 发生在 pytest `tmp_path` 临时目录中（数据文件 `test.json`、后端文件 `test.db`）
- `LoggerManager` 由 `test/conftest.py` 的 autouse fixture `mock_logger` 全局替换，测试不写入真实 `logs/`
- 单例由 `test/conftest.py` 的 autouse fixture `reset_singletons` 自动重置；本文件另有 `_reset_singleton()` 做显式重置

### 2.2 测试数据

- 插件数据使用内存中的字典与标量值（如 `{"nested": [1, 2, 3]}`）
- 资源文件使用二进制数据（`b"fake image data"`）模拟
- 并发测试使用 4 线程 × 每线程 50 次写入（共 200 个 key）
- 迁移测试直接构造旧版 `test.json`（`{"plugins": {...}, "active_instances": {...}}`）

### 2.3 测试环境

- 临时数据目录由 pytest 内置 `tmp_path` fixture 提供
- 日志输出由 autouse fixture `mock_logger` 禁用
- 单例由 autouse fixture `reset_singletons` 与本文件 `_reset_singleton()` 重置
- 运行命令：`.venv\Scripts\python.exe -m pytest test/core/data -q -p no:cacheprovider`

---

## 3. 测试用例

> 下表按测试类分组列出 `test_data_provider.py` 中的全部用例（共 36 个，与 pytest 收集结果一一对应）。
> 「说明」列一律取自代码：优先取该测试函数的 docstring 首句，其次取函数体内最近的中文注释（多条时用「；」连接），两者都没有时取该测试类上方的分组注释。
> 代码中未提供的信息（断言细节、优先级、风险关联）不在本表补充。原 `TC-DP-XXX` 编号体系已取消，用例统一按「测试类 + 函数名」定位。

### 3.1 单例模式（`TestSingleton`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_singleton` | 单例测试 |
| `test_db_file_derived_from_json` | 单例测试 |

### 3.2 插件注册/注销（`TestRegisterUnregister`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_and_exists` | 插件注册/注销 |
| `test_register_duplicate_raises` | 插件注册/注销 |
| `test_unregister_removes_data` | 插件注册/注销 |
| `test_unregister_nonexistent_raises` | 插件注册/注销 |

### 3.3 活跃实例（`TestActiveInstance`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_set_and_get_active` | 活跃实例 |
| `test_only_one_active_per_type` | 活跃实例 |

### 3.4 插件数据（`TestPluginData`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_private_round_trip` | 插件数据 |
| `test_default_value` | 插件数据 |
| `test_external_modification_does_not_pollute` | 插件数据 |
| `test_non_serializable_raises` | 插件数据 |

### 3.5 发布订阅（`TestPubSub`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_public_notify_triggers_callback` | Pub/Sub |
| `test_private_does_not_trigger` | Pub/Sub |
| `test_notify_false_does_not_trigger` | Pub/Sub |

### 3.6 缓存（`TestCache`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_data_returns_deep_copy` | 缓存 |
| `test_clear_cache_then_save_raises` | 缓存 |

### 3.7 数据重置（`TestResetAllData`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_reset_clears_data` | 重置 |

### 3.8 迁移（`TestMigration`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_json_migrated_to_sqlite` | 备份文件应生成 |

### 3.9 Schema 版本（`TestSchemaVersion`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_new_database_has_version_1` | Schema 版本 |

### 3.10 序列化兼容性（`TestSerializationCompatibility`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_int_enum_key` | 序列化兼容性 |
| `test_nan_rejected` | 序列化兼容性 |

### 3.11 LRU 缓存（`TestLRUCache`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_none_value_is_cached` | 第一次读取填充缓存；第二次读取应命中缓存并仍然返回 None（不是默认值） |
| `test_capacity_evicts_oldest` | 读取填充缓存；k1 应该被淘汰 |
| `test_invalidation_on_write` | LRU 缓存 |

### 3.12 迁移失败回滚（`TestMigrationFailure`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_migration_failure_cleans_up_db_and_keeps_json` | data.db 应被清理；原始 json 应保留 |

### 3.13 锁顺序（`TestNotifyLockOrder`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_callback_not_under_file_lock` | 锁顺序 |
| `test_callback_can_reenter_dataprovider` | 回调中再次读取数据不应死锁；如果死锁，上面的调用不会返回 |

### 3.14 并发（`TestConcurrency`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_concurrent_set_get` | 最终一致 |

### 3.15 资源文件（`TestAssets`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_and_load_asset` | 资源文件 |
| `test_get_asset_path_rejects_traversal` | 资源文件 |
| `test_save_asset_rejects_path_traversal` | save_asset 拒绝包含 .. 的路径穿越文件名。 |
| `test_save_asset_rejects_empty_filename` | save_asset 拒绝空文件名。 |

### 3.16 Schema 升级（`TestSchemaUpgrade`）

| 用例函数名 | 说明 |
|-----------|------|
| `test_high_version_rejected` | Schema 升级 |
| `test_corrupt_version_rejected` | Schema 升级 |
| `test_legacy_database_upgraded` | 模拟一个有核心表但无 db_metadata 的旧数据库；应补齐 schema_version 为 1，且不丢数据 |

---

## 4. 维护指南

### 4.1 添加新测试

当 `DataProvider` 添加新 API 时：
1. 在 `test_data_provider.py` 中找到对应的测试类（必要时新增 `Test*` 类，并在类上方补一行中文分组注释）
2. 添加新测试函数，遵循命名规范 `test_<场景描述>`
3. 为测试函数补中文 docstring，首句说明测试目的（本文档「说明」列取该首句）
4. 同步更新本文档对应测试类的用例清单表，以及「1.1 覆盖范围」的用例数（合计须等于 pytest 收集数）
5. 确保测试独立、可重复（统一用 `_provider(tmp_path)` 构造实例）

### 4.2 修复失败的测试

1. 查看失败测试的 docstring 了解测试目的（无 docstring 时见本文档该用例的「说明」）
2. 检查被测代码是否有 bug
3. 如果是测试问题，修复测试而非被测代码
4. 如果是测试环境问题，检查 fixtures

### 4.3 覆盖率目标

- 当前覆盖率：**未实测**（本模块测试以 `.venv` 运行，当前环境未安装 `pytest-cov`，`--cov` 参数不可用；本文档不给出未经测量的覆盖率数字）
- 目标覆盖率: 90%
- 测量命令（需先安装 `pytest-cov`）：`.venv\Scripts\python.exe -m pytest test/core/data -q -p no:cacheprovider --cov=core.data --cov-report=term-missing`
- 待补强的方向（沿用原文档判断，未经测量确认）:
  - 错误恢复路径
  - 边界条件
  - 复杂并发场景

---

## 5. 相关文档

- [DataProvider API 参考](../../../docs/core/data-provider/api-reference.md)
- [DataProvider 概述](../../../docs/core/data-provider/overview.md)
- [测试主文档](../../TESTING.md)

---
