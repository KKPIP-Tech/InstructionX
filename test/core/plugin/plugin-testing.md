# 插件系统测试文档

> 插件系统核心模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/plugin/`
**测试文件数**: 4 个
**测试用例总数**: 34+ 个

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试用例数 | 主要覆盖 |
|---------|---------|-----------|---------|
| `test_plugin_manager.py` | 8 | 17+ | PluginManager 单例、插件加载、注册/注销、API 管理 |
| `test_plugin_identity.py` | 3+ | 6+ | PluginIdentity 标识、ID 生成 |
| `test_plugin_config_manager.py` | 3+ | 5+ | PluginConfigManager 配置管理 |
| `test_plugin_version.py` | 3+ | 5+ | PluginVersion 版本比较 |

### 1.2 覆盖范围

| 功能分组 | 测试用例数 | 覆盖的公开 API |
|---------|-----------|---------------|
| 单例模式 | 1 | `PluginManager()` |
| 官方插件加载 | 5 | `load_official_plugins()`, `_load_plugin_from_directory()` |
| 插件注册/注销 | 6 | `register_plugin()`, `unregister_plugin()` |
| API 管理 | 4 | `get_plugin_api()`, `has_api_method()` |
| 方法调用 | 3 | `call_plugin_method()` |
| 函数工具生成 | 2 | `generate_function_tools()` |
| 插件重新加载 | 2 | `reload_plugin()` |
| 插件标识 | 6 | `PluginIdentity`, `plugin_id`, `plugin_name` |
| 配置管理 | 5 | `load_config()`, `save_config()`, `get_plugin_config()` |
| 版本管理 | 5 | `PluginVersion`, `from_string()`, `compare()` |
| API 自动注册 (R-01) | 2 | `_auto_register_plugin_api()` |
| API 自动注册边界 | 2 | 空 Service、无公开方法 |

---

## 2. 测试策略

### 2.1 隔离措施

- `PluginManager` 单例由 `reset_singletons` fixture 自动重置
- 插件加载使用 `create_minimal_plugin()` 工具函数创建临时插件
- 使用 `plugin_dir_from_test` fixture 创建相对于测试文件的临时目录
- Mock 所有外部依赖（LoggerManager, 文件 I/O）

### 2.2 测试数据

- 使用 `create_minimal_plugin()` 创建最小有效测试插件
- Mock 插件使用 `MagicMock()` 创建
- 版本测试使用 `PluginVersion.from_string()` 解析字符串版本

### 2.3 关键 Fixtures

```python
# test/conftest.py
temp_plugin_dir      # 临时插件目录
reset_singletons     # 重置所有单例

# test/conftest_utils.py
create_minimal_plugin(plugin_dir, plugin_name, has_service, service_methods, has_information)

# test_plugin_manager.py
plugin_dir_from_test  # 构造插件测试目录（相对于测试文件）
```

---

## 3. 测试用例

### 3.1 PluginManager 单例模式

#### TC-PLUGIN-001: 单例返回相同实例
- **测试类**: TestSingleton
- **测试函数**: `test_singleton_two_calls_return_same_instance`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `PluginManager()` 两次
  2. 验证返回同一对象引用
- **预期结果**: `mgr1 is mgr2`

---

### 3.2 官方插件加载

#### TC-PLUGIN-002: 跳过 '_' 前缀目录
- **测试类**: TestLoadOfficialPlugins
- **测试函数**: `test_load_official_plugins_skips_underscore_prefix_dirs`
- **优先级**: P1
- **前置条件**: 存在有效插件和 '_' 前缀插件
- **测试步骤**:
  1. 创建有效插件目录和 '_hidden_plugin' 目录
  2. 调用 `load_official_plugins()`
  3. 验证有效插件被加载，'_' 前缀插件被跳过
- **预期结果**: "ValidPlugin" 在列表中，"_hidden_plugin" 不在

#### TC-PLUGIN-003: 缺少 entrance.py 返回 None
- **测试类**: TestLoadOfficialPlugins
- **测试函数**: `test_load_plugin_from_directory_no_entrance_returns_none`
- **优先级**: P1
- **前置条件**: 插件目录缺少 entrance.py
- **测试步骤**:
  1. 创建空目录
  2. 调用 `_load_plugin_from_directory()`
- **预期结果**: 返回 None

#### TC-PLUGIN-004: 不包含 IPlugin 子类返回 None
- **测试类**: TestLoadOfficialPlugins
- **测试函数**: `test_load_plugin_from_directory_no_iplugin_subclass_returns_none`
- **优先级**: P1
- **前置条件**: entrance.py 不定义 IPlugin 子类
- **测试步骤**:
  1. 创建只包含 `x = 1` 的 entrance.py
  2. 调用 `_load_plugin_from_directory()`
- **预期结果**: 返回 None

---

### 3.3 插件注册/注销

#### TC-PLUGIN-005: register_plugin 维护三个注册表
- **测试类**: TestRegisterUnregister
- **测试函数**: `test_register_plugin_maintains_all_three_registries`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 Mock 插件
  2. 调用 `register_plugin(mock_plugin, is_official=True)`
  3. 验证三个注册表
- **预期结果**:
  - `_plugin_registry` 包含插件
  - `_plugin_name_to_id` 映射正确
  - 插件在官方列表中

#### TC-PLUGIN-006: 第三方插件注册
- **测试类**: TestRegisterUnregister
- **测试函数**: `test_register_plugin_thirdparty_maintains_registry`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建 Mock 插件
  2. 调用 `register_plugin(mock_plugin, is_official=False)`
  3. 验证插件在第三方列表中
- **预期结果**: 插件在 `_thirdparty_plugins` 中

#### TC-PLUGIN-007: 重复注册抛出异常
- **测试类**: TestRegisterUnregister
- **测试函数**: `test_register_duplicate_raises`
- **优先级**: P1
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 注册插件
  2. 再次注册同一插件
- **预期结果**: 抛出 `PluginError` 或类似异常

#### TC-PLUGIN-008: unregister_plugin 移除插件
- **测试类**: TestRegisterUnregister
- **测试函数**: `test_unregister_plugin_removes_from_registry`
- **优先级**: P1
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 注册插件
  2. 调用 `unregister_plugin(plugin_id)`
  3. 验证插件已移除
- **预期结果**: 插件不在注册表中

#### TC-PLUGIN-009: 注销不存在的插件抛出异常
- **测试类**: TestRegisterUnregister
- **测试函数**: `test_unregister_nonexistent_raises`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `unregister_plugin("nonexistent-id")`
- **预期结果**: 抛出异常

---

### 3.4 API 管理

#### TC-PLUGIN-010: get_plugin_api 返回 PluginAPI 对象
- **测试类**: TestPluginAPI
- **测试函数**: `test_get_plugin_api_returns_plugin_api`
- **优先级**: P0
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 注册插件
  2. 调用 `get_plugin_api(plugin_id)`
- **预期结果**: 返回 `PluginAPI` 对象

#### TC-PLUGIN-011: has_api_method 检查方法存在
- **测试类**: TestPluginAPI
- **测试函数**: `test_has_api_method_returns_correctly`
- **优先级**: P1
- **前置条件**: 插件有服务方法
- **测试步骤**:
  1. 注册带方法的插件
  2. 调用 `has_api_method(plugin_id, method_name)`
- **预期结果**: 返回 True/False

#### TC-PLUGIN-012: 获取不存在的插件 API 抛出异常
- **测试类**: TestPluginAPI
- **测试函数**: `test_get_api_for_nonexistent_raises`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `get_plugin_api("nonexistent-id")`
- **预期结果**: 抛出异常

---

### 3.5 方法调用

#### TC-PLUGIN-013: call_plugin_method 执行方法
- **测试类**: TestMethodCall
- **测试函数**: `test_call_plugin_method_executes`
- **优先级**: P0
- **前置条件**: 插件已注册且有方法
- **测试步骤**:
  1. 注册带方法的插件
  2. 调用 `call_plugin_method(plugin_id, method_name, args)`
- **预期结果**: 方法被执行，返回结果

#### TC-PLUGIN-014: 调用不存在的方法抛出异常
- **测试类**: TestMethodCall
- **测试函数**: `test_call_nonexistent_method_raises`
- **优先级**: P1
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 调用 `call_plugin_method(plugin_id, "nonexistent", ...)`
- **预期结果**: 抛出异常

---

### 3.6 函数工具生成

#### TC-PLUGIN-015: generate_function_tools 生成工具定义
- **测试类**: TestFunctionTools
- **测试函数**: `test_generate_function_tools_creates_tools`
- **优先级**: P1
- **前置条件**: 插件有服务方法
- **测试步骤**:
  1. 注册带 information.py 的插件
  2. 调用 `generate_function_tools()`
- **预期结果**: 返回符合 MCP 格式的工具定义列表

---

### 3.7 插件重新加载

#### TC-PLUGIN-016: reload_plugin 重新加载插件
- **测试类**: TestReloadPlugin
- **测试函数**: `test_reload_plugin_reloads`
- **优先级**: P1
- **前置条件**: 插件已注册
- **测试步骤**:
  1. 注册插件
  2. 调用 `reload_plugin(plugin_id)`
- **预期结果**: 插件被重新加载

---

### 3.8 PluginIdentity 标识

#### TC-PLUGIN-017: PluginIdentity 生成唯一 ID
- **测试类**: TestPluginIdentity
- **测试函数**: `test_plugin_identity_generates_unique_id`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 创建 PluginIdentity 实例
  2. 验证 plugin_id 格式
- **预期结果**: plugin_id 是唯一的字符串

#### TC-PLUGIN-018: PluginIdentity 从文件加载/保存
- **测试类**: TestPluginIdentity
- **测试函数**: `test_plugin_identity_save_load`
- **优先级**: P1
- **前置条件**: 存在 .plugin_id 文件
- **测试步骤**:
  1. 创建 PluginIdentity 并保存
  2. 创建新实例并加载
- **预期结果**: plugin_id 一致

---

### 3.9 PluginVersion 版本管理

#### TC-PLUGIN-019: from_string 解析版本字符串
- **测试类**: TestPluginVersion
- **测试函数**: `test_from_string_parses_version`
- **优先级**: P0
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `PluginVersion.from_string("release.1.0.0")`
  2. 验证版本属性
- **预期结果**: 版本被正确解析

#### TC-PLUGIN-020: 版本比较
- **测试类**: TestPluginVersion
- **测试函数**: `test_version_compare`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 创建两个版本
  2. 比较版本
- **预期结果**: 比较结果正确

#### TC-PLUGIN-021: 无效版本字符串处理
- **测试类**: TestPluginVersion
- **测试函数**: `test_invalid_version_string_raises`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 调用 `from_string("invalid")`
- **预期结果**: 抛出异常或返回默认值

---

### 3.10 PluginConfigManager 配置管理

#### TC-PLUGIN-022: load_config 加载配置
- **测试类**: TestPluginConfigManager
- **测试函数**: `test_load_config_loads_existing`
- **优先级**: P1
- **前置条件**: 配置文件存在
- **测试步骤**:
  1. 创建临时配置文件
  2. 调用 `load_config()`
- **预期结果**: 配置被加载

#### TC-PLUGIN-023: save_config 保存配置
- **测试类**: TestPluginConfigManager
- **测试函数**: `test_save_config_persists`
- **优先级**: P1
- **前置条件**: 无
- **测试步骤**:
  1. 修改配置
  2. 调用 `save_config()`
  3. 重新加载
- **预期结果**: 配置被持久化

#### TC-PLUGIN-024: 获取插件配置
- **测试类**: TestPluginConfigManager
- **测试函数**: `test_get_plugin_config_returns_config`
- **优先级**: P1
- **前置条件**: 插件有配置
- **测试步骤**:
  1. 注册插件
  2. 调用 `get_plugin_config(plugin_id)`
- **预期结果**: 返回插件配置

---

### 3.11 API 自动注册 (R-01 风险覆盖)

#### TC-PLUGIN-025: API 自动注册支持自定义 Service 类名
- **测试类**: TestAutoRegisterAPI
- **测试函数**: `test_auto_register_with_custom_service_class`
- **优先级**: P1
- **前置条件**: 插件使用非标准 Service 类名
- **测试步骤**:
  1. 创建使用 `MyService` 类名的插件
  2. 调用 `load_plugins()`
  3. 验证 API 是否被正确注册
- **预期结果**: 支持自定义类名，或有明确错误提示
- **风险关联**: R-01

#### TC-PLUGIN-026: API 自动注册仅注册 Service 类的方法
- **测试类**: TestAutoRegisterAPI
- **测试函数**: `test_auto_register_only_service_methods`
- **优先级**: P1
- **前置条件**: 插件 Service 类有公共方法和内部方法
- **测试步骤**:
  1. 创建带 `public_method` 和 `_private_method` 的 Service
  2. 加载插件
  3. 调用 `get_all_function_tools()`
- **预期结果**: 仅 `public_method` 被注册为 API
- **风险关联**: R-01

---

### 3.12 API 自动注册边界条件

#### TC-PLUGIN-027: 空 Service 类不注册任何 API
- **测试类**: TestAutoRegisterAPI
- **测试函数**: `test_auto_register_empty_service_no_api`
- **优先级**: P2
- **前置条件**: 插件 Service 类为空
- **测试步骤**:
  1. 创建空 Service 类 `class MyService: pass`
  2. 加载插件
  3. 调用 `get_all_function_tools()`
- **预期结果**: 返回空列表，无 API 注册
- **风险关联**: R-01

#### TC-PLUGIN-028: Service 类仅有私有方法时不注册 API
- **测试类**: TestAutoRegisterAPI
- **测试函数**: `test_auto_register_only_private_methods_no_api`
- **优先级**: P2
- **前置条件**: 插件 Service 类仅有 `_private_method`
- **测试步骤**:
  1. 创建仅有私有方法的 Service
  2. 加载插件
  3. 调用 `get_all_function_tools()`
- **预期结果**: 返回空列表
- **风险关联**: R-01

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/plugin/` 添加新功能时：
1. 在对应的测试文件中找到测试类
2. 添加新测试函数，遵循命名规范
3. 使用 TC-PLUGIN-XXX 格式的 docstring
4. 使用 `create_minimal_plugin()` 创建测试插件

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 fixture 问题，检查 `plugin_dir_from_test` 是否正确

### 4.3 覆盖率目标

- 当前覆盖率: ~80%
- 目标覆盖率: 85%
- 未覆盖的关键路径:
  - 真实文件系统操作
  - 复杂插件依赖关系
  - 插件热拔插场景

---

## 5. 相关文档

- [插件系统概述](../../docs/core/plugin-system/overview.md)
- [插件开发指南](../../docs/core/plugin-system/plugin-development.md)
- [测试主文档](../TESTING.md)

---
