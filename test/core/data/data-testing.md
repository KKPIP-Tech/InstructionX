# DataProvider 测试文档

> DataProvider 模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/data/data_provider.py`
**测试文件**: `test/core/data/test_data_provider.py`
**测试类数量**: 15+ 个测试类
**测试用例总数**: 30+ 个

### 1.1 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例模式 | 1 | `DataProvider()` |
| 数据文件初始化 | 2 | `_ensure_data_file()`, `_read_from_disk()` |
| 数据加载 | 4 | `load_data()`, `clear_cache()` |
| 数据写入 | 2 | `_write_to_disk()`, `save_data()` |
| 插件注册 | 2 | `register_plugin()`, `get_plugin_info()` |
| 插件注销 | 3 | `unregister_plugin()`, 订阅清理 |
| 活跃实例管理 | 3 | `set_active_instance()`, `get_active_instance()` |
| 数据存取 | 4 | `get_plugin_data()`, `set_plugin_data()` |
| 发布订阅 | 8 | `subscribe()`, `unsubscribe()`, `_notify_subscribers()` |
| 资源管理 | 4 | `save_asset()`, `get_asset_path()`, `load_asset()` |
| 并发安全 | 1 | 多线程写入压力测试 |
| 数据重置 | 2 | `reset_all_data()` |

---

## 2. 测试策略

### 2.1 隔离措施

- 每个测试使用独立的 `DataProvider` 实例（通过 `temp_data_dir` fixture）
- 磁盘 I/O 发生在临时目录中
- Mock 所有外部依赖（LoggerManager）
- 单例由 `reset_singletons` fixture 自动重置

### 2.2 测试数据

- 插件数据使用内存中的字典操作
- 资源文件使用二进制数据（如 `b"\x89PNG..."`）模拟
- 并发测试使用 4 线程 x 50 次写入

### 2.3 测试环境

- 临时数据目录由 `temp_data_dir` fixture 提供
- 日志输出由 `mock_logger` fixture 禁用
- 单例由 `reset_singletons` fixture 重置

---

## 3. 测试用例

### 3.1 单例模式

#### TC-DP-001: 单例返回相同实例
- **测试类**: TestSingleton
- **测试函数**: `test_singleton_returns_same_instance`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 `DataProvider` 实例
  2. 再次调用 `DataProvider()`
  3. 验证两次返回同一对象引用
- **预期结果**: `second is dp`（同一对象）

---

### 3.2 数据文件初始化

#### TC-DP-002: 文件不存在时创建默认结构
- **测试类**: TestEnsureDataFile
- **测试函数**: `test_ensure_data_file_creates_default_structure`
- **优先级**: P1
- **前置条件**: `data.json` 不存在
- **测试步骤**:
  1. 确认临时目录中无 `data.json`
  2. 创建 `DataProvider` 实例
  3. 验证 `data.json` 已创建
  4. 验证内容为默认结构 `{"plugins": {}, "active_instances": {}}`
- **预期结果**: 文件存在且内容正确

#### TC-DP-003: 损坏的 JSON 文件抛出异常
- **测试类**: TestReadFromDisk
- **测试函数**: `test_read_from_disk_raises_on_corrupted_json`
- **优先级**: P1
- **前置条件**: `data.json` 包含无效 JSON
- **测试步骤**:
  1. 创建包含无效 JSON 的 `data.json`
  2. 创建 `DataProvider` 实例
  3. 调用 `_read_from_disk()`
- **预期结果**: 抛出 `DataProviderError`，匹配 "JSON 解析失败"

---

### 3.3 数据加载

#### TC-DP-004: load_data 使用缓存
- **测试类**: TestLoadData
- **测试函数**: `test_load_data_uses_cache`
- **优先级**: P1
- **前置条件**: 已填充缓存
- **测试步骤**:
  1. 调用 `load_data()` 两次
  2. 使用 mock 监控 `_read_from_disk()` 调用次数
- **预期结果**: 第二次调用不触发磁盘读取

#### TC-DP-005: force_reload 绕过缓存
- **测试类**: TestLoadData
- **测试函数**: `test_load_data_force_reload_bypasses_cache`
- **优先级**: P1
- **前置条件**: 已填充缓存
- **测试步骤**:
  1. 调用 `load_data()`
  2. 调用 `load_data(force_reload=True)`
- **预期结果**: 第二次调用触发磁盘读取

#### TC-DP-006: load_data 返回副本
- **测试类**: TestLoadData
- **测试函数**: `test_load_data_returns_copy`
- **优先级**: P1
- **前置条件**: 已注册插件
- **测试步骤**:
  1. 调用 `load_data()` 获取数据
  2. 修改返回数据的嵌套值
  3. 再次调用 `load_data()`
- **预期结果**: 缓存共享嵌套对象引用，但 clear_cache 后恢复原始值

---

### 3.4 数据写入

#### TC-DP-007: 原子写入流程
- **测试类**: TestWriteToDisk
- **测试函数**: `test_write_to_disk_uses_temp_then_replace`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. Mock `os.replace` 和 `builtins.open`
  2. 调用 `_write_to_disk()`
  3. 验证临时文件先被写入，然后调用 `os.replace`
- **预期结果**: `replace(src, dst)` 中 src 为临时文件，dst 为数据文件

#### TC-DP-008: save_data 持久化到磁盘
- **测试类**: TestSaveData
- **测试函数**: `test_save_data_persists_to_disk`
- **优先级**: P1
- **前置条件**: 已注册插件
- **测试步骤**:
  1. 调用 `set_plugin_data()` 设置数据
  2. 创建新的 `DataProvider` 实例（强制重新加载）
  3. 验证数据已持久化
- **预期结果**: 新实例能读取到之前设置的数据

---

### 3.5 插件注册

#### TC-DP-009: 重复注册抛出异常
- **测试类**: TestRegisterPlugin
- **测试函数**: `test_register_plugin_raises_on_duplicate`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `register_plugin("plugin-a", "VideoEditor")`
  2. 再次调用 `register_plugin("plugin-a", "VideoEditor")`
- **预期结果**: 抛出 `DataProviderError`，匹配 "plugin-a"

---

### 3.6 插件注销

#### TC-DP-010: 注销不存在的插件抛出异常
- **测试类**: TestUnregisterPlugin
- **测试函数**: `test_unregister_plugin_raises_if_not_found`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `unregister_plugin("not-exist")`
- **预期结果**: 抛出 `DataProviderError`，匹配 "not-exist"

#### TC-DP-011: 注销插件时清除订阅
- **测试类**: TestUnregisterPlugin
- **测试函数**: `test_unregister_plugin_cleans_subscriptions`
- **优先级**: P1
- **前置条件**: 两个已注册插件，已建立订阅
- **测试步骤**:
  1. 注册 plugin-a 和 plugin-b
  2. plugin-b 订阅 plugin-a 的 key-a
  3. 注销 plugin-a
  4. 验证订阅已清除
- **预期结果**: 订阅键 `("plugin-b", "plugin-a", "key-a")` 不在订阅列表中

---

### 3.7 活跃实例管理

#### TC-DP-012: 设置不存在的活跃实例抛出异常
- **测试类**: TestSetActiveInstance
- **测试函数**: `test_set_active_instance_raises_if_not_found`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `set_active_instance("not-exist")`
- **预期结果**: 抛出 `DataProviderError`，匹配 "not-exist"

#### TC-DP-013: 同一类型旧实例被标记为非活跃
- **测试类**: TestSetActiveInstance
- **测试函数**: `test_set_active_instance_deactivates_same_type`
- **优先级**: P1
- **前置条件**: 两个同类型插件
- **测试步骤**:
  1. 注册 plugin-a1 和 plugin-a2（类型均为 VideoEditor）
  2. 设置 plugin-a1 为活跃
  3. 设置 plugin-a2 为活跃
  4. 验证 plugin-a1 的 active 为 False，plugin-a2 的 active 为 True
- **预期结果**: 同一类型同时只有一个活跃实例

#### TC-DP-014: get_active_instance 返回类型对应的实例
- **测试类**: TestSetActiveInstance
- **测试函数**: `test_set_active_instance_updates_active_instances_dict`
- **优先级**: P1
- **前置条件**: 两个不同类型插件
- **测试步骤**:
  1. 注册 plugin-a (VideoEditor) 和 plugin-b (Exporter)
  2. 设置 plugin-a 为活跃
  3. 验证 `get_active_instance("VideoEditor")` 返回 "plugin-a"
  4. 设置 plugin-b 为活跃
  5. 验证 `get_active_instance("Exporter")` 返回 "plugin-b"
- **预期结果**: 不同类型独立管理活跃实例

---

### 3.8 数据存取

#### TC-DP-015: get_plugin_data 返回已存储的值
- **测试类**: TestGetPluginData
- **测试函数**: `test_get_plugin_data_returns_value`
- **优先级**: P0
- **前置条件**: 已注册插件并设置数据
- **测试步骤**:
  1. 调用 `set_plugin_data("plugin-a", "name", "MyProject", DataNamespace.PRIVATE)`
  2. 调用 `get_plugin_data("plugin-a", "name")`
- **预期结果**: 返回 "MyProject"

#### TC-DP-016: get_plugin_data 键不存在时返回默认值
- **测试类**: TestGetPluginData
- **测试函数**: `test_get_plugin_data_returns_default`
- **优先级**: P1
- **前置条件**: 已注册插件
- **测试步骤**:
  1. 调用 `get_plugin_data("plugin-a", "nonexistent", default="fallback")`
- **预期结果**: 返回 "fallback"

#### TC-DP-017: get_plugin_data 插件不存在时抛出异常
- **测试类**: TestGetPluginData
- **测试函数**: `test_get_plugin_data_raises_if_plugin_missing`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `get_plugin_data("not-exist", "key")`
- **预期结果**: 抛出 `DataProviderError`，匹配 "not-exist"

---

### 3.9 发布订阅

#### TC-DP-018: PUBLIC 数据触发订阅回调
- **测试类**: TestSetPluginData
- **测试函数**: `test_set_plugin_data_public_triggers_callback`
- **优先级**: P0
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. publisher 和 subscriber 已注册
  2. subscriber 订阅 publisher 的 "score" key
  3. publisher 设置 PUBLIC 数据 100
  4. publisher 再次设置 PUBLIC 数据 200
- **预期结果**:
  - 第一次 callback 收到 `(None, 100)`
  - 第二次 callback 收到 `(100, 200)`

#### TC-DP-019: PRIVATE 数据不触发订阅回调
- **测试类**: TestSetPluginData
- **测试函数**: `test_set_plugin_data_private_does_not_trigger_callback`
- **优先级**: P0
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. subscriber 订阅 publisher 的 PRIVATE key
  2. publisher 设置 PRIVATE 数据
- **预期结果**: callback 未被调用

#### TC-DP-020: notify=False 抑制回调
- **测试类**: TestSetPluginData
- **测试函数**: `test_set_plugin_data_notify_false_suppresses_callback`
- **优先级**: P1
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. subscriber 订阅 publisher 的 key
  2. publisher 调用 `set_plugin_data(..., notify=False)`
- **预期结果**: callback 未被调用

#### TC-DP-021: publish 等价于 set_plugin_data PUBLIC
- **测试类**: TestPublish
- **测试函数**: `test_publish_updates_public_data`
- **优先级**: P1
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. subscriber 订阅 publisher 的 "event_key"
  2. 调用 `publish("publisher", "event_key", "new_value")`
- **预期结果**: callback 收到 `(None, "new_value")`

#### TC-DP-022: 订阅不存在的目标插件抛出异常
- **测试类**: TestSubscribe
- **测试函数**: `test_subscribe_raises_if_target_missing`
- **优先级**: P1
- **前置条件**: subscriber 已注册，publisher 未注册
- **测试步骤**:
  1. 调用 `subscribe("subscriber", "publisher-missing", "key", callback)`
- **预期结果**: 抛出 `DataProviderError`

#### TC-DP-023: unsubscribe 清除所有订阅
- **测试类**: TestUnsubscribe
- **测试函数**: `test_unsubscribe_all_removes_all_for_subscriber`
- **优先级**: P1
- **前置条件**: 两个已注册插件，建立两个订阅
- **测试步骤**:
  1. plugin-b 订阅 plugin-a 的 key1 和 key2
  2. 调用 `unsubscribe("plugin-b")`
  3. 验证订阅列表长度为 0
- **预期结果**: 所有以 plugin-b 为订阅者的订阅都被清除

#### TC-DP-024: unsubscribe 清除指定目标的订阅
- **测试类**: TestUnsubscribe
- **测试函数**: `test_unsubscribe_target_removes_only_matching`
- **优先级**: P1
- **前置条件**: 已注册插件，建立两个订阅
- **测试步骤**:
  1. plugin-b 订阅 plugin-a 的 key1 和 plugin-c 的 key2
  2. 调用 `unsubscribe("plugin-b", "plugin-a")`
  3. 验证只剩一个订阅
- **预期结果**: 只清除目标为 plugin-a 的订阅

#### TC-DP-025: 回调异常被捕获不传播
- **测试类**: TestNotifySubscribers
- **测试函数**: `test_notify_subscribers_catches_callback_exception`
- **优先级**: P1
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. subscriber 订阅 publisher 的 key
  2. callback 抛出 RuntimeError
  3. 调用 `_notify_subscribers()`
- **预期结果**: 异常被捕获，不向外传播

---

### 3.10 资源管理

#### TC-DP-026: 路径遍历攻击防护
- **测试类**: TestAsset
- **测试函数**: `test_get_asset_path_rejects_path_traversal`
- **优先级**: P1
- **前置条件**: 插件已注册，已保存资源
- **测试步骤**:
  1. 调用 `get_asset_path("assets/plugins/plugin-a/../../../etc/passwd")`
- **预期结果**: 抛出 `DataProviderError`，匹配 "无效的相对路径"

#### TC-DP-027: 合法相对路径返回绝对路径
- **测试类**: TestAsset
- **测试函数**: `test_get_asset_path_returns_absolute_path`
- **优先级**: P1
- **前置条件**: 插件已注册，已保存资源
- **测试步骤**:
  1. 保存资源 `config.json`
  2. 调用 `get_asset_path(rel_path)`
- **预期结果**: 返回 resolve 后的绝对路径，文件存在

#### TC-DP-028: 资源往返存储
- **测试类**: TestAsset
- **测试函数**: `test_asset_roundtrip`
- **优先级**: P1
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 保存二进制资源 `thumbnail.png`
  2. 获取资源路径
  3. 加载资源
  4. 验证数据一致
- **预期结果**: 加载的数据与原始数据一致

#### TC-DP-029: 加载不存在的资源抛出异常
- **测试类**: TestAsset
- **测试函数**: `test_load_asset_raises_if_missing`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `load_asset("assets/plugins/plugin-a/nonexistent.png")`
- **预期结果**: 抛出 `DataProviderError`

---

### 3.11 并发安全

#### TC-DP-030: 多线程并发写入后 JSON 仍有效
- **测试类**: TestConcurrentWrites
- **测试函数**: `test_concurrent_writes_produce_valid_json`
- **优先级**: P1
- **前置条件**: 两个已注册插件
- **测试步骤**:
  1. 启动 4 个并发写入线程
  2. 每个线程执行 50 次写入
  3. 等待所有线程完成
  4. 读取 `data.json` 验证是有效 JSON
- **预期结果**:
  - 无异常抛出
  - JSON 文件可解析
  - 所有写入数据存在

---

### 3.12 数据重置

#### TC-DP-031: reset_all_data 清空所有数据
- **测试类**: TestResetAllData
- **测试函数**: `test_reset_all_data`
- **优先级**: P1
- **前置条件**: 已注册插件
- **测试步骤**:
  1. 调用 `reset_all_data()`
  2. 调用 `load_data()`
- **预期结果**: 数据为默认结构 `{"plugins": {}, "active_instances": {}}`

---

## 4. 维护指南

### 4.1 添加新测试

当 `DataProvider` 添加新 API 时：
1. 在 `test_data_provider.py` 中找到对应的测试类
2. 添加新测试函数，遵循命名规范 `test_<场景描述>`
3. 使用 TC-DP-XXX 格式的 docstring
4. 确保测试独立、可重复

### 4.2 修复失败的测试

1. 查看失败测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是测试问题，修复测试而非被测代码
4. 如果是测试环境问题，检查 fixtures

### 4.3 覆盖率目标

- 当前覆盖率: ~85%
- 目标覆盖率: 90%
- 未覆盖的关键路径:
  - 错误恢复路径
  - 边界条件
  - 复杂并发场景

---

## 5. 相关文档

- [DataProvider API 参考](../../docs/core/data-provider/api-reference.md)
- [DataProvider 概述](../../docs/core/data-provider/overview.md)
- [测试主文档](../TESTING.md)

---
