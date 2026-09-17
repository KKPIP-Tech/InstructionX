# 插件系统测试文档

> 插件系统核心模块的测试策略、测试用例和维护指南
>
> **本文档已按 `test/core/plugin/` 实际代码刷新（2026-09-15）**：11 个 `test_*.py`、48 个测试类、208 个 `def test_*` 测试函数，pytest 实测收集 **225 个用例**。§3 用例清单与代码双向核对，代码中每个测试函数在清单中有且仅有一行。

---

## 1. 测试概述

- **被测模块**: `core/plugin/`
- **测试目录**: `test/core/plugin/`
- **测试文件数**: 11 个（`test_*.py`；同目录下 `conftest.py`、`__init__.py` 为辅助文件、不收集用例）
- **测试类数**: 48 个
- **测试函数数**: 208 个
- **实测收集用例数**: 225 个

实测命令（工作目录 = 项目根）：

```powershell
.venv\Scripts\python.exe -m pytest test/core/plugin --collect-only -q -p no:cacheprovider
```

> 208 与 225 的差额来自参数化：`test_dependency_manager.py` 的 `TestDependencyManagerVersionConstraint::test_operators` 由 `@pytest.mark.parametrize` 展开为 15 例（+14）、`test_package_discovery.py` 的 `TestDescriptorValidation::test_invalid_descriptor_marked_not_installable` 展开为 3 例（+2）、`test_local_package_install.py` 的 `TestTempDirectoryCleanup::test_temp_dir_removed` 展开为 2 例（+1），合计 208 + 17 = 225。§3 清单按**测试函数**列行（共 208 行），统计口径中的「用例数」按 pytest 实际收集结果（225）计。

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试函数数 | 实测用例数 | 主要覆盖 |
|---------|---------|-----------|-----------|---------|
| `test_plugin_manager.py` | 11 | 32 | 32 | `PluginManager` 单例、插件加载、注册/注销、插件查询、自定义排序、API 注册管理、跨插件方法调用、函数工具生成、重新加载、工具名净化 |
| `test_plugin_api_auto_register.py` | 1 | 4 | 4 | `_auto_register_plugin_api()` API 自动注册（R-01 风险覆盖） |
| `test_plugin_identity.py` | 1 | 13 | 13 | `PluginIdentity` UUID 加载/生成/重建、`registered_at`、读写异常路径 |
| `test_plugin_config_manager.py` | 1 | 7 | 7 | `PluginConfigManager` 插件排序文件读写与更新 |
| `test_plugin_version.py` | 6 | 30 | 30 | `PluginVersion` / `VersionType` 解析、比较、显示、字符串表示、哈希 |
| `test_plugin_icon.py` | 3 | 23 | 23 | `PluginIcon` / `IconType` 工厂方法与 `load_icon()` 各分支 |
| `test_dependency_manager.py` | 8 | 30 | 44 | `DependencyManager` 依赖检查/安装、版本约束比较、pip 调用、结果数据类 |
| `test_package_discovery.py` | 5 | 23 | 25 | `inspect_package()` / `validate_descriptor()`：单插件/插件集/无效分类、包装层穿透、`IXRepo.json` 索引驱动、递归扫描规则、描述文件校验、诊断信息与深度上限 |
| `test_local_package_install.py` | 7 | 25 | 26 | `GitHubPluginInstaller.install_from_zip()` / `inspect_local_package()`：单插件包、插件集一次安装与子集筛选、安装关系（新装/升级/降级）预演、默认勾选策略、无效包诊断、临时目录清理、**目标范围（官方/第三方）与已安装插件不搬家**、包外文件快照集成 |
| `test_plugin_backup.py` | 2 | 9 | 9 | `collect_extra_files()` / `snapshot_plugin_dir()`：包外文件检测与排除规则、整目录快照命名与内容、快照份数裁剪 |
| `test_plugin_move.py` | 3 | 12 | 12 | `PluginManager.move_plugin_to_scope()` / `_scope_directory()`：目录移动、UUID 随迁、注册表分类更新、分组排序清理、拒绝路径（未加载/非法范围/同分类/同名目录/移动失败回滚） |
| **合计** | **48** | **208** | **225** | — |

### 1.2 覆盖范围

| 功能分组 | 测试函数数 | 实测用例数 | 覆盖的公开 API / 对象 | 对应测试类 |
|---------|-----------|-----------|---------------------|-----------|
| 单例模式 | 1 | 1 | `PluginManager()` | §3.1.1 `TestSingleton` |
| 官方插件加载 | 3 | 3 | `load_official_plugins()`, `_load_plugin_from_directory()` | §3.1.2 `TestLoadOfficialPlugins` |
| 插件注册/注销 | 4 | 4 | `register_plugin()`, `unregister_plugin()` | §3.1.3 `TestRegisterUnregister` |
| 插件查询 | 6 | 6 | `get_plugin_by_name()`, `get_plugin_by_id()`, `get_plugin_id_by_type_id()` | §3.1.4 `TestPluginQueries` |
| 排序与顺序持久化 | 3 | 3 | `apply_custom_order()`, `save_plugin_order()` | §3.1.5 `TestApplyCustomOrder`、§3.1.6 `TestSavePluginOrder` |
| 插件 API 注册管理 | 5 | 5 | `register_plugin_api()`, `unregister_plugin_api()`, `get_plugin_api()` | §3.1.7 `TestPluginApiManagement` |
| 跨插件方法调用 | 4 | 4 | `call_plugin_method()` | §3.1.8 `TestCallPluginMethod` |
| 函数工具生成 | 2 | 2 | `get_all_function_tools()` | §3.1.9 `TestGetAllFunctionTools` |
| 插件重新加载 | 1 | 1 | `reload_plugins()` | §3.1.10 `TestReloadPlugins` |
| 工具名净化 | 3 | 3 | `sanitize_tool_name()` | §3.1.11 `TestSanitizeToolName` |
| API 自动注册（R-01） | 4 | 4 | `_auto_register_plugin_api()`（经 `load_plugins()` 触发） | §3.2.1 `TestAutoRegisterAPI` |
| 插件身份标识 | 13 | 13 | `PluginIdentity.load_or_create_id()`, `regenerate_id()`, `plugin_id`, `registered_at`, `_load_from_file()`, `_save_to_file()` | §3.3.1 `TestPluginIdentity` |
| 排序配置管理 | 7 | 7 | `PluginConfigManager.load_plugin_order()`, `save_plugin_order()`, `update_official_order()`, `update_thirdparty_order()` | §3.4.1 `TestPluginConfigManager` |
| 版本管理 | 30 | 30 | `VersionType`（成员/优先级/显示名）、`PluginVersion.from_string()`, `to_string()`, `get_display_version()`、比较运算符、`__str__` / `__repr__` / 哈希 | §3.5.1–§3.5.6 |
| 插件图标 | 23 | 23 | `IconType`、`PluginIcon.builtin()` / `from_file()` / `from_resource()` / `from_base64()` / `none()`、`load_icon()` | §3.6.1–§3.6.3 |
| 依赖管理 | 30 | 44 | `DependencyManager.check_dependencies()`, `get_missing_dependencies()`, `install_dependencies()`, `_is_package_installed()`, `_parse_version_from_pip_show()`, `_check_version_constraint()`, `_normalize_version()`, `_pip_install()`；`DependencyCheckResult` / `DependencyInstallResult` | §3.7.1–§3.7.8 |
| 本地插件包识别 | 23 | 25 | `inspect_package()`, `validate_descriptor()`；`PluginCandidate` / `PackageInspection`、`PACKAGE_KIND_*` / `MAX_DISCOVERY_DEPTH` 常量 | §3.8.1–§3.8.5 |
| 本地包安装与关系预演 | 20 | 21 | `install_from_zip()`, `inspect_local_package()`；`LocalInstallPlan` / `LocalPackageInspection`、`selected_plugins` 筛选、注册表登记与包外文件备份集成 | §3.9.1–§3.9.6 |
| 本地安装目标范围 | 5 | 5 | `inspect_local_package(target_scope=...)`, `install_from_zip(target_scope=...)`；`SCOPE_OFFICIAL` / `SCOPE_THIRDPARTY`、`target_dir` 优先级、已安装插件沿用原目录 | §3.9.7 `TestTargetScope` |
| 包外文件兜底快照 | 9 | 9 | `collect_extra_files()`, `snapshot_plugin_dir()`；`MAX_BACKUPS_PER_PLUGIN` | §3.10.1–§3.10.2 |
| 插件分类移动 | 12 | 12 | `move_plugin_to_scope()`, `_scope_directory()`；注册表 `set_scope()`、UUID 文件随迁、分组排序清理、拒绝路径与移动失败回滚 | §3.11.1–§3.11.3 |
| **合计** | **208** | **225** | — | — |

---

## 2. 测试策略

### 2.1 隔离措施

- `test/core/plugin/conftest.py::reset_plugin_manager`（autouse）：测试前后重置 `PluginManager._instance` / `_initialized`
- `test/conftest.py::reset_singletons`（autouse）：每个用例前后重置全部单例（含 `PluginManager`、`DataProvider`、`BackgroundTaskManager`、`LLMProvider` 等）
- `test/conftest.py::mock_logger`（autouse）：Mock 各模块的 `LoggerManager`，避免用例写 `logs/`
- 插件加载使用 `create_minimal_plugin()` 工具函数创建临时插件
- `plugin_dir_from_test` fixture 返回 `tmp_path / "plugins"`，为每个用例提供独立插件目录
- 通过 `mocker.patch` / `patch` 拦截外部依赖（`subprocess.run`、`builtins.open`、`LoggerManager`、`QApplication.instance`、`QStyleFactory.create`、`base64.b64decode` 等）

### 2.2 测试数据

- 使用 `create_minimal_plugin()` 创建最小有效测试插件（可控制 `has_service` / `service_methods` / `has_information`）
- Mock 插件使用 `MagicMock()` 创建（`plugin_id` / `plugin_name` / `plugin_info` 等属性按用例需要赋值）
- 版本测试使用 `PluginVersion.from_string()` 解析字符串版本
- 图标测试使用 `minimal_png_bytes` / `minimal_png_base64` 构造最小 1×1 PNG 数据
- 身份与配置测试在 `tmp_path` 下写临时文件（`.plugin_info.json`、`plugin_order.json`）
- 本地包识别测试用 `make_plugin()` / `make_index()` 在 `tmp_path` 下构造包目录树（可覆盖描述文件内容）
- 本地包安装测试用 `make_plugin_zip()` 现场生成 zip（可控制包装层目录名、插件目录与版本、`IXRepo.json` 索引、附加文件与描述内容）
- 包外文件快照测试用 `make_dir()` 按 `{相对路径: 内容}` 构造新旧目录对照

### 2.3 关键 Fixtures

```python
# test/conftest.py
reset_singletons         # autouse：重置全部单例（含 PluginManager）
mock_logger              # autouse：Mock LoggerManager，禁止写 logs/
temp_plugin_dir          # 临时插件目录（tmp_path / "plugins"）
qapp_instance            # session 级 QApplication（offscreen）

# test/core/plugin/conftest.py
reset_plugin_manager     # autouse：重置 PluginManager._instance / _initialized
mock_plugin_services     # Mock PluginServices（data_provider / task_manager /
                         #   llm_provider / mcp_client / mcp_server）

# test/conftest_utils.py
create_minimal_plugin(plugin_dir, plugin_name, has_service, service_methods, has_information)

# test_plugin_manager.py / test_plugin_api_auto_register.py
plugin_dir_from_test     # 返回 tmp_path / "plugins"

# test_plugin_identity.py / test_plugin_config_manager.py
plugin_dir / config_dir  # 临时插件目录 / 临时配置目录（均为 tmp_path）
mock_logger              # 局部 fixture：patch 所在模块的 LoggerManager

# test_plugin_icon.py
minimal_png_bytes        # 最小 1×1 PNG 字节数据
minimal_png_base64       # 上述 PNG 的 base64 字符串

# test_local_package_install.py
isolated_pm              # 官方/第三方插件目录与 config 全部指向 tmp_path 的 PluginManager
installer                # 基于 isolated_pm 的 GitHubPluginInstaller
```

---

## 3. 测试用例

> **说明列取值规则**：
>
> 1. 测试函数有 docstring 时，说明为 docstring 首句的中文直译或中文归纳（docstring 本身为中文时原文引用）；docstring 以冒号引出要点时，拼接其后的要点行并译为中文。方法名、类名、字段名、类型名等专业术语保留原文。
> 2. 测试函数无 docstring 时，说明按「函数名 + 所属测试类」归纳，统一以「归纳：」开头；这类说明**粒度较粗**，仅用于定位用例，具体断言仍以代码为准。
> 3. 全部说明均来自代码（docstring / 紧邻注释 / 函数名与所属测试类），未添加代码之外的断言、步骤或优先级。

### 3.1 `test_plugin_manager.py`

> 测试类 11 个，测试函数 32 个，实测用例 32 个。被测对象：`core/plugin/manager.py` 的 `PluginManager`、`PluginAPI` 与 `sanitize_tool_name`；范围：单例模式、插件加载、注册与注销、API 管理、方法调用、函数工具生成、重新加载。本文件测试函数均自带中文 docstring，说明为原文引用。

#### 3.1.1 TestSingleton

| 用例函数名 | 说明 |
|-----------|------|
| `test_singleton_two_calls_return_same_instance` | 两次调用 `PluginManager()` 应返回同一实例对象。 |

#### 3.1.2 TestLoadOfficialPlugins

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_official_plugins_skips_underscore_prefix_dirs` | `load_official_plugins()` 应跳过以 '_' 开头的目录。 |
| `test_load_plugin_from_directory_no_entrance_returns_none` | `_load_plugin_from_directory()` 在插件目录缺少 entrance.py 时应返回 None。 |
| `test_load_plugin_from_directory_no_iplugin_subclass_returns_none` | `_load_plugin_from_directory()` 在 entrance.py 不包含 IPlugin 子类时返回 None。 |

#### 3.1.3 TestRegisterUnregister

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_plugin_maintains_all_three_registries` | `register_plugin()` 应同时将插件添加到注册表、名称映射以及官方/第三方列表。 |
| `test_register_plugin_thirdparty_maintains_registry` | `register_plugin(is_official=False)` 应将插件添加到第三方列表 |
| `test_unregister_plugin_removes_from_all_three_registries` | `unregister_plugin()` 应从注册表、名称映射以及两个插件列表中完全移除插件。 |
| `test_unregister_plugin_idempotent` | 重复调用 unregister_plugin 不应抛出异常 |

#### 3.1.4 TestPluginQueries

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_plugin_by_name_returns_plugin` | 已注册的插件可通过名称正确查询 |
| `test_get_plugin_by_name_returns_none_for_unknown` | 不存在的插件名称应返回 None |
| `test_get_plugin_by_id_returns_plugin` | 已注册的插件可通过 ID 正确查询 |
| `test_get_plugin_by_id_returns_none_for_unknown` | 不存在的插件 ID 应返回 None |
| `test_get_plugin_id_by_type_id_returns_uuid` | 可通过 plugin_info.plugin_type_id 查询到对应的 plugin_id |
| `test_get_plugin_id_by_type_id_returns_none_for_unknown` | 不存在的 plugin_type_id 应返回 None |

#### 3.1.5 TestApplyCustomOrder

| 用例函数名 | 说明 |
|-----------|------|
| `test_apply_custom_order_orders_plugins_correctly` | `apply_custom_order()` 应按配置文件中的 UUID 顺序排序，并将未列入配置的新插件追加到末尾。 |
| `test_apply_custom_order_with_empty_config_appends_all` | 配置文件为空时应保留原始顺序（所有插件均视为新增） |

#### 3.1.6 TestSavePluginOrder

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_plugin_order_delegates_to_config_manager` | `save_plugin_order()` 应将调用委托给 `config_manager.save_plugin_order()` |

#### 3.1.7 TestPluginApiManagement

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_plugin_api_raises_valueerror_for_unknown_plugin` | `register_plugin_api()` 在 plugin_id 未注册时应抛出 ValueError。 |
| `test_register_plugin_api_stores_api_entry` | `register_plugin_api()` 成功注册后应能在 `_api_registry` 中查到 |
| `test_unregister_plugin_api_removes_entry` | `unregister_plugin_api()` 应从 `_api_registry` 中删除对应条目 |
| `test_get_plugin_api_returns_dict` | `get_plugin_api()` 应返回包含 plugin_id、plugin_name、methods 等字段的字典 |
| `test_get_plugin_api_returns_none_for_unknown` | `get_plugin_api()` 在 plugin_id 不存在时应返回 None |

#### 3.1.8 TestCallPluginMethod

| 用例函数名 | 说明 |
|-----------|------|
| `test_call_plugin_method_normal_call_succeeds` | 正常调用应返回方法返回值 |
| `test_call_plugin_method_raises_valueerror_for_missing_plugin` | 调用未注册的 plugin_id 应抛出 ValueError |
| `test_call_plugin_method_raises_valueerror_for_missing_method` | 调用不存在的方法名应抛出 ValueError |
| `test_call_plugin_method_wraps_handler_exception_in_runtime_error` | 方法内部抛出的异常应被包装为 RuntimeError |

#### 3.1.9 TestGetAllFunctionTools

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_all_function_tools_produces_mcp_format` | `get_all_function_tools()` 应返回符合 MCP 规范的列表，每个工具包含 `type="function"`、function.name、function.description、function.parameters 等字段。 |
| `test_get_all_function_tools_empty_when_no_apis` | 没有任何 API 注册时，应返回空列表 |

#### 3.1.10 TestReloadPlugins

| 用例函数名 | 说明 |
|-----------|------|
| `test_reload_plugins_clears_all_registries_and_rescans` | `reload_plugins()` 应清空 `_official_plugins`、`_thirdparty_plugins`、`_plugin_registry`、`_plugin_name_to_id`、`_api_registry`，然后重新扫描插件目录。 |

#### 3.1.11 TestSanitizeToolName

| 用例函数名 | 说明 |
|-----------|------|
| `test_keeps_valid_characters` | 合法字符保持不变。 |
| `test_replaces_invalid_characters_with_underscore` | 非法字符替换为下划线。 |
| `test_truncates_to_64_chars` | 结果超过 64 字符时截断。 |

---

### 3.2 `test_plugin_api_auto_register.py`

> 测试类 1 个，测试函数 4 个，实测用例 4 个。被测对象：`core/plugin/manager.py` 的 `_auto_register_plugin_api()`；范围：自定义 Service 类名、公共方法过滤、空 Service 类、私有方法过滤。文件头 docstring 标注风险关联 R-01（见 §3.12），4 个用例的 docstring 均为中文原文引用。

#### 3.2.1 TestAutoRegisterAPI

| 用例函数名 | 说明 |
|-----------|------|
| `test_auto_register_with_custom_service_class` | TC-PLUGIN-025: API 自动注册支持自定义 Service 类名 |
| `test_auto_register_only_service_methods` | TC-PLUGIN-026: API 自动注册仅注册 Service 类的方法 |
| `test_auto_register_empty_service_no_api` | TC-PLUGIN-027: 空 Service 类不注册任何 API |
| `test_auto_register_only_private_methods_no_api` | TC-PLUGIN-028: Service 类仅有私有方法时不注册 API |

---

### 3.3 `test_plugin_identity.py`

> 测试类 1 个，测试函数 13 个，实测用例 13 个。被测对象：`core/plugin/plugin_identity.py` 的 `PluginIdentity`。说明为英文 docstring 的中文直译（以冒号引出要点者拼接要点行）。

#### 3.3.1 TestPluginIdentity

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_or_create_id_file_absent_generates_uuid_and_saves` | 当 info 文件不存在时，`load_or_create_id()` 应：生成新 UUID；将其保存到 .plugin_info.json；返回生成的 UUID |
| `test_load_or_create_id_file_present_loads_existing_uuid` | 当 info 文件存在且数据有效时，`load_or_create_id()` 应：从文件加载已有 UUID；不生成新 UUID；返回加载到的 UUID |
| `test_load_or_create_id_corrupted_json_generates_new_uuid` | 当 info 文件内容为损坏的 JSON 时，`load_or_create_id()` 应：记录 warning 日志；生成新 UUID（加载失败后 `_plugin_id` 为 None）；将新 UUID 保存到文件 |
| `test_regenerate_id_creates_new_uuid_and_overwrites_file` | `regenerate_id()` 应：生成与已有 UUID 不同的全新 UUID；用新 UUID 覆盖已有文件；返回新 UUID |
| `test_registered_at_parsed_from_iso_format` | 从有效文件加载时，`registered_at` 应由 ISO 格式字符串解析为 datetime 对象。 |
| `test_plugin_id_property_returns_correct_uuid` | `plugin_id` 属性应返回 `load_or_create_id()` 已加载或生成的 UUID。 |
| `test_file_present_but_missing_plugin_id_generates_new_uuid` | 文件存在但缺少 `plugin_id` 时，生成新 UUID。 |
| `test_file_present_with_empty_plugin_id_generates_new_uuid` | `plugin_id` 为空字符串时，视为缺失并生成新 UUID。 |
| `test_invalid_registered_at_logs_warning_and_generates_new_uuid` | 非法的 ISO datetime 应被捕获并触发新 UUID 生成。 |
| `test_load_from_file_ioerror_logs_warning_and_generates_new_uuid` | `_load_from_file` 期间发生 IOError 时应记录 warning 日志并生成新 UUID。 |
| `test_save_to_file_ioerror_logs_error` | `_save_to_file` 期间发生 IOError 应被捕获并记录日志。 |
| `test_multiple_load_calls_return_same_uuid` | 重复调用 `load_or_create_id` 应返回同一 UUID。 |
| `test_regenerate_id_updates_registered_at` | `regenerate_id` 应更新 `registered_at` 时间戳。 |

---

### 3.4 `test_plugin_config_manager.py`

> 测试类 1 个，测试函数 7 个，实测用例 7 个。被测对象：`core/plugin/config_manager.py` 的 `PluginConfigManager`。说明为英文 docstring 的中文直译。

#### 3.4.1 TestPluginConfigManager

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_plugin_order_file_absent_returns_empty_structure` | 配置文件不存在时，`load_plugin_order()` 应返回 {"official_plugins": [], "thirdparty_plugins": []}。 |
| `test_load_plugin_order_invalid_json_returns_empty_structure` | 配置文件包含非法 JSON 时，`load_plugin_order()` 应返回空结构。 |
| `test_load_plugin_order_partial_data_fills_missing_keys` | 配置文件只含部分键时，缺失的键应填充为空列表。 |
| `test_load_plugin_order_only_thirdparty_key` | 缺少 'official_plugins' 键时填充为 []。 |
| `test_save_plugin_order_writes_valid_json` | `save_plugin_order()` 写出包含两个键的合法 JSON 文件。 |
| `test_update_official_order_updates_only_official` | `update_official_order()` 应只更新 official_plugins 列表，保持不变更 thirdparty_plugins 列表。 |
| `test_update_thirdparty_order_updates_only_thirdparty` | `update_thirdparty_order()` 应只更新 thirdparty_plugins 列表，保持不变更 official_plugins 列表。 |

---

### 3.5 `test_plugin_version.py`

> 测试类 6 个，测试函数 30 个，实测用例 30 个。被测对象：`core/plugin/plugin_version.py` 的 `PluginVersion` 与 `VersionType`。说明为英文 docstring 的中文直译（`TestPluginVersionHashable` 的 3 个用例 docstring 本身为中文，原文引用）。

#### 3.5.1 TestVersionType

| 用例函数名 | 说明 |
|-----------|------|
| `test_version_types_exist` | `VersionType` 枚举应包含全部预期成员。 |
| `test_priority_order` | 优先级顺序：INTERNAL(1) < ALPHA(2) < BETA(3) < PRE_RELEASE(4) < RELEASE(5)。 |
| `test_display_names` | `get_display_name()` 返回正确的中文名称。 |

#### 3.5.2 TestPluginVersionFromString

| 用例函数名 | 说明 |
|-----------|------|
| `test_parse_release` | `from_string('release.1.0.0')` 解析正确。 |
| `test_parse_beta` | `from_string('beta.2.3.4')` 解析正确。 |
| `test_parse_alpha` | `from_string('alpha.3.2.1')` 解析正确。 |
| `test_parse_internal` | `from_string('internal.0.0.1')` 解析正确。 |
| `test_parse_pre_release` | `from_string('pre-release.5.4.3')` 解析正确。 |
| `test_parse_invalid_format_not_four_parts` | `from_string('invalid')` 抛出 ValueError（段数不是 4）。 |
| `test_parse_invalid_format_only_three_parts` | `from_string('release.1.0')` 抛出 ValueError（只有 3 段）。 |
| `test_parse_unknown_version_type` | `from_string('unknown.1.0.0.0')` 对未知类型抛出 ValueError。 |
| `test_parse_negative_numbers_raises` | `from_string('release.-1.0.0')` 对负数抛出 ValueError。 |

#### 3.5.3 TestPluginVersionComparison

| 用例函数名 | 说明 |
|-----------|------|
| `test_version_type_priority_release_gt_beta` | release 版本高于 beta。 |
| `test_version_type_priority_beta_gt_alpha` | beta 版本高于 alpha。 |
| `test_version_type_priority_alpha_gt_internal` | alpha 版本高于 internal。 |
| `test_patch_version_comparison_1_2_3_gt_1_2_2` | 1.2.3 > 1.2.2（类型、major/minor 相同，patch 更高）。 |
| `test_minor_version_comparison_2_0_0_gt_1_9_9` | 2.0.0 > 1.9.9（类型相同，major 更高）。 |
| `test_equality_same_fields` | 各字段相同时相等。 |
| `test_inequality_different_fields` | 字段不同时不相等。 |
| `test_le_and_ge` | `__le__` 与 `__ge__` 行为正确。 |
| `test_compare_different_types_same_numbers` | 数字相同但类型不同：release.1.0.0 > beta.1.0.0。 |

#### 3.5.4 TestPluginVersionDisplay

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_display_version_includes_chinese_name` | `get_display_version()` 结果包含中文类型名。 |
| `test_get_display_version_beta` | beta 的 `get_display_version()` 结果包含「测试版」。 |

#### 3.5.5 TestPluginVersionString

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_string_format` | `to_string()` 返回正确的 '<type>.<major>.<minor>.<patch>' 格式。 |
| `test_to_string_beta` | beta 的 `to_string()` 返回 'beta.x.y.z'。 |
| `test_str_delegates_to_to_string` | `__str__` 委托给 `to_string()`。 |
| `test_repr_format` | `__repr__` 返回 PluginVersion('<string>') 格式。 |

#### 3.5.6 TestPluginVersionHashable

| 用例函数名 | 说明 |
|-----------|------|
| `test_can_be_used_as_dict_key` | PluginVersion 可作为字典 key 使用。 |
| `test_same_versions_have_same_hash` | 相同版本对象哈希值相同。 |
| `test_can_be_added_to_set` | PluginVersion 可加入集合。 |

---

### 3.6 `test_plugin_icon.py`

> 测试类 3 个，测试函数 23 个，实测用例 23 个。被测对象：`core/plugin/plugin_icon.py` 的 `PluginIcon` 与 `IconType`。说明为英文 docstring 的中文直译；`TestPluginIconFactories` 的 5 个用例未写 docstring，说明按函数名与所属测试类归纳（见下）。

#### 3.6.1 TestIconType

| 用例函数名 | 说明 |
|-----------|------|
| `test_icon_type_values` | `IconType` 枚举成员应具有预期的字符串值。 |

#### 3.6.2 TestPluginIconFactories

> 本类 5 个用例均无 docstring，说明按「函数名 + 所属测试类（PluginIcon 工厂类方法）」归纳，**粒度较粗**。

| 用例函数名 | 说明 |
|-----------|------|
| `test_builtin_factory` | 归纳：`PluginIcon.builtin()` 工厂方法构造 BUILTIN 类型图标。 |
| `test_from_file_factory` | 归纳：`PluginIcon.from_file()` 工厂方法构造 FILE 类型图标。 |
| `test_from_resource_factory` | 归纳：`PluginIcon.from_resource()` 工厂方法构造 RESOURCE 类型图标。 |
| `test_from_base64_factory` | 归纳：`PluginIcon.from_base64()` 工厂方法构造 BASE64 类型图标。 |
| `test_none_factory` | 归纳：`PluginIcon.none()` 工厂方法构造 NONE 类型图标。 |

#### 3.6.3 TestPluginIconLoad

| 用例函数名 | 说明 |
|-----------|------|
| `test_none_type_returns_none` | `IconType.NONE` 始终返回 None。 |
| `test_builtin_valid_standard_pixmap` | BUILTIN 使用合法的 QStyle.StandardPixmap 名称时应返回 QIcon。 |
| `test_builtin_invalid_name_returns_none` | BUILTIN 使用非法名称时应返回 None。 |
| `test_builtin_no_value_returns_none` | BUILTIN 无 value 时应返回 None。 |
| `test_builtin_without_qapplication` | `QApplication.instance()` 返回 None 时 BUILTIN 仍应可用。 |
| `test_builtin_style_factory_returns_none` | `QStyleFactory.create` 返回 None 时，BUILTIN 应返回 None。 |
| `test_file_missing_without_plugin_dir_returns_none` | FILE 未提供 plugin_dir 时应返回 None。 |
| `test_file_missing_file_returns_none` | FILE 指向不存在的路径时应返回 None。 |
| `test_file_existing_icon_returns_qicon` | FILE 指向已存在的图片文件时应返回 QIcon。 |
| `test_file_no_value_returns_none` | FILE 无 value 时应返回 None。 |
| `test_resource_with_value_returns_qicon` | RESOURCE 有 value 时应返回 QIcon。 |
| `test_resource_no_value_returns_none` | RESOURCE 无 value 时应返回 None。 |
| `test_base64_valid_image_returns_qicon` | BASE64 为合法 PNG 数据时应返回 QIcon。 |
| `test_base64_no_value_returns_none` | BASE64 无 value 时应返回 None。 |
| `test_base64_invalid_base64_returns_none` | BASE64 为非法 base64 时应捕获异常并返回 None。 |
| `test_base64_non_image_data_returns_none` | BASE64 为合法 base64 但非图片数据时应返回 None。 |
| `test_load_icon_exception_returns_none_and_logs` | `load_icon` 期间任何未预期异常都应被捕获并返回 None。 |

---

### 3.7 `test_dependency_manager.py`

> 测试类 8 个，测试函数 30 个，实测用例 44 个。被测对象：`core/plugin/dependency_manager.py` 的 `DependencyManager`、`DependencyCheckResult`、`DependencyInstallResult`。
>
> 本文件仅 `test_dependency_install_result_post_init` 有 docstring（英文，已中译）；其余用例无 docstring，说明按「函数名 + 所属测试类」归纳，统一以「归纳：」开头，**粒度较粗**——具体断言（如期望的 `missing` 列表、`satisfied` 取值、回调消息文案）以代码为准。

#### 3.7.1 TestDataClasses

| 用例函数名 | 说明 |
|-----------|------|
| `test_dependency_check_result_defaults` | 归纳：`DependencyCheckResult` 的默认字段取值。 |
| `test_dependency_install_result_post_init` | `DependencyInstallResult` 应将 `failed_packages` 初始化为空列表。 |
| `test_dependency_install_result_preserves_failed_packages` | 归纳：`DependencyInstallResult` 保留传入的 `failed_packages`。 |

#### 3.7.2 TestDependencyManagerCheck

| 用例函数名 | 说明 |
|-----------|------|
| `test_empty_dependencies_returns_satisfied` | 归纳（所属测试类 `check_dependencies`）：依赖为空时返回已满足。 |
| `test_all_dependencies_satisfied` | 归纳（所属测试类 `check_dependencies`）：全部依赖均满足的情形。 |
| `test_some_dependencies_missing` | 归纳（所属测试类 `check_dependencies`）：部分依赖缺失的情形。 |
| `test_all_dependencies_missing` | 归纳（所属测试类 `check_dependencies`）：全部依赖缺失的情形。 |

#### 3.7.3 TestDependencyManagerGetMissing

| 用例函数名 | 说明 |
|-----------|------|
| `test_returns_missing_package_names` | 归纳（所属测试类 `get_missing_dependencies`）：返回缺失依赖的包名。 |

#### 3.7.4 TestDependencyManagerInstall

| 用例函数名 | 说明 |
|-----------|------|
| `test_empty_dependencies` | 归纳（所属测试类 `install_dependencies`）：依赖为空时的安装结果。 |
| `test_already_satisfied` | 归纳（所属测试类 `install_dependencies`）：依赖已满足时的安装结果。 |
| `test_successful_install` | 归纳（所属测试类 `install_dependencies`）：依赖安装成功的路径。 |
| `test_partial_failure` | 归纳（所属测试类 `install_dependencies`）：部分依赖安装失败的路径。 |
| `test_callback_invoked` | 归纳（所属测试类 `install_dependencies`）：安装过程的进度回调调用。 |
| `test_callback_failure_message` | 归纳（所属测试类 `install_dependencies`）：安装失败时的回调消息。 |

#### 3.7.5 TestDependencyManagerIsPackageInstalled

| 用例函数名 | 说明 |
|-----------|------|
| `test_installed_no_constraint` | 归纳（所属测试类 `_is_package_installed`）：包已安装且无版本约束。 |
| `test_not_installed` | 归纳（所属测试类 `_is_package_installed`）：包未安装。 |
| `test_installed_with_constraint_satisfied` | 归纳（所属测试类 `_is_package_installed`）：包已安装且版本约束满足。 |
| `test_installed_with_constraint_not_satisfied` | 归纳（所属测试类 `_is_package_installed`）：包已安装但版本约束不满足。 |
| `test_installed_version_parse_failure` | 归纳（所属测试类 `_is_package_installed`）：已安装但版本号解析失败。 |
| `test_timeout` | 归纳（所属测试类 `_is_package_installed`）：依赖检查过程超时。 |
| `test_exception_during_check` | 归纳（所属测试类 `_is_package_installed`）：依赖检查过程抛出异常。 |

#### 3.7.6 TestDependencyManagerParseVersion

| 用例函数名 | 说明 |
|-----------|------|
| `test_parses_version_line` | 归纳（所属测试类 `_parse_version_from_pip_show`）：解析 pip show 输出中的版本行。 |
| `test_missing_version_returns_none` | 归纳（所属测试类 `_parse_version_from_pip_show`）：缺少版本行时返回 None。 |

#### 3.7.7 TestDependencyManagerVersionConstraint

> `test_operators` 为参数化用例，由 `@pytest.mark.parametrize` 展开为 15 组（installed, constraint, expected）组合，故本类 3 个测试函数对应 17 个实测用例。

| 用例函数名 | 说明 |
|-----------|------|
| `test_operators` | 归纳（所属测试类 `_check_version_constraint`）：参数化校验版本约束运算符，15 组 installed/constraint/expected 组合。 |
| `test_unparseable_constraint` | 归纳（所属测试类 `_check_version_constraint`）：无法解析的约束表达式。 |
| `test_normalize_version_none` | 归纳：`_normalize_version()` 对非法版本字符串返回 None。 |

#### 3.7.8 TestDependencyManagerPipInstall

| 用例函数名 | 说明 |
|-----------|------|
| `test_success` | 归纳（所属测试类 `_pip_install`）：依赖安装成功。 |
| `test_failure` | 归纳（所属测试类 `_pip_install`）：依赖安装失败。 |
| `test_timeout` | 归纳（所属测试类 `_pip_install`）：依赖安装过程超时。 |
| `test_exception` | 归纳（所属测试类 `_pip_install`）：依赖安装过程抛出异常。 |

---

### 3.8 `test_package_discovery.py`

> 测试类 5 个，测试函数 23 个，实测用例 25 个。被测对象：`core/plugin/package_discovery.py` 的 `inspect_package()`、`validate_descriptor()` 与 `PluginCandidate` / `PackageInspection`；范围：单插件/插件集/无效包分类、包装层穿透、`IXRepo.json` 索引驱动、目录扫描规则、描述文件校验、诊断信息与深度上限。
>
> 本文件测试函数与测试类均自带中文 docstring，说明为原文引用。
>
> `test_invalid_descriptor_marked_not_installable` 为参数化用例，由 `@pytest.mark.parametrize` 展开为 3 组（缺少必需字段 / 版本号格式无效 / ID 格式无效），故本类 4 个测试函数对应 6 个实测用例。

#### 3.8.1 TestClassification

| 用例函数名 | 说明 |
|-----------|------|
| `test_root_directory_is_single_plugin` | 描述文件位于包根 → single，且 rel_path 为空串 |
| `test_github_style_wrapper_is_unwrapped` | GitHub 下载的 repo-main/ 包装层被穿透 → single |
| `test_double_wrapper_is_unwrapped` | 用户二次打包（外层/仓库名/插件） → single |
| `test_parallel_plugins_are_collection` | 并列多个插件目录 → multi |
| `test_rel_path_is_relative_posix` | 候选的 rel_path 是相对包根的 posix 路径（非绝对路径） |

#### 3.8.2 TestIndexDriven

| 用例函数名 | 说明 |
|-----------|------|
| `test_index_order_and_declared_flag` | 索引项优先且按索引顺序，declared_in_index 为 True |
| `test_undeclared_plugin_is_extra_candidate` | 索引未声明但实际存在的插件也作为候选，且带警告 |
| `test_missing_declared_directory_reported` | 索引声明的目录不存在 → 该条目不可安装并给出原因（不静默丢弃） |
| `test_index_path_escape_rejected` | 索引路径越出包根 → 拒绝并说明原因 |
| `test_broken_index_falls_back_to_scan` | 索引文件损坏时退回目录扫描，并把原因作为警告 |

#### 3.8.3 TestScanRules

| 用例函数名 | 说明 |
|-----------|------|
| `test_deep_nesting_is_found` | monorepo 多层嵌套仍能命中（包装层下潜 + 递归扫描） |
| `test_macos_noise_directory_ignored` | __MACOSX 等噪声目录不影响判定 |
| `test_underscore_prefixed_directory_skipped` | 下划线前缀目录被跳过（与插件加载器约定一致） |
| `test_inner_plugin_directory_not_scanned` | 插件目录内部再嵌套插件目录时不误判（命中即停止下潜） |
| `test_duplicate_id_keeps_first_and_marks_rest` | 同一包内重复 ID：保留首个，其余标记不可安装 |
| `test_depth_limit_truncates_with_warning` | 超过深度上限的插件不被识别，并给出截断警告 |

#### 3.8.4 TestDescriptorValidation

| 用例函数名 | 说明 |
|-----------|------|
| `test_invalid_descriptor_marked_not_installable` | 缺字段 / 版本号非法 / ID 非法 → 该候选不可安装并给出具体原因（参数化 3 组） |
| `test_non_json_descriptor_reported` | 描述文件不是合法 JSON → 报告读取失败而非崩溃 |
| `test_invalid_candidate_does_not_block_others` | 一个候选非法不影响同包内其他插件的识别 |
| `test_validate_descriptor_accepts_valid_minimum` | 最小合法描述文件通过校验 |

#### 3.8.5 TestDiagnostics

| 用例函数名 | 说明 |
|-----------|------|
| `test_empty_package_is_invalid_with_stats` | 无任何插件 → invalid，诊断含扫描统计与指引 |
| `test_missing_root_is_invalid` | 解压目录不存在 → invalid（不抛异常） |
| `test_has_index_false_without_index_file` | 无索引文件的包 has_index 为 False（决定默认勾选策略） |

---

### 3.9 `test_local_package_install.py`

> 测试类 7 个，测试函数 25 个，实测用例 26 个。被测对象：`core/plugin/github_plugin_installer.py` 的 `install_from_zip()` / `inspect_local_package()` 及 `LocalInstallPlan` / `LocalPackageInspection`；范围：单插件包安装（旧签名行为不变）、插件集一次安装与子集筛选、安装关系预演与默认勾选策略、目标范围（官方/第三方）与已安装插件不搬家、无效包诊断、临时目录清理、包外文件快照集成。
>
> 本文件测试函数与测试类均自带中文 docstring，说明为原文引用。全部用例通过 `isolated_pm` fixture 把官方/第三方插件目录与配置指向 `tmp_path`，不触碰仓库真实 `plugin/`、`custom_plugin/`、`config/`。
>
> `test_temp_dir_removed` 为参数化用例，由 `@pytest.mark.parametrize` 展开为 2 组（success / invalid），故 §3.9.5 的 1 个测试函数对应 2 个实测用例。

#### 3.9.1 TestSinglePluginPackage

| 用例函数名 | 说明 |
|-----------|------|
| `test_install_single_plugin_zip` | 旧签名 install_from_zip(zip_path) 仍安装单个插件并登记注册表 |
| `test_inspect_single_plugin` | 识别单插件包：kind=single、计划一项、默认勾选 |
| `test_inspect_does_not_install` | 识别是只读操作：不产生插件目录、不改注册表 |

#### 3.9.2 TestCollectionPackage

| 用例函数名 | 说明 |
|-----------|------|
| `test_install_collection_in_one_call` | 插件集一次安装全部插件，并记录 source_type / source_path |
| `test_install_subset_by_rel_path` | selected_plugins 按包内相对路径筛选，未选插件不落盘 |
| `test_install_subset_by_descriptor_id` | selected_plugins 也可用插件 id 匹配（目录名与 id 不一致时） |
| `test_empty_selection_installs_nothing` | 未选中任何插件时返回空列表且不落盘 |
| `test_invalid_candidate_skipped_without_blocking` | 不可安装候选被跳过，其余插件照常安装 |

#### 3.9.3 TestRelationsAndSelection

| 用例函数名 | 说明 |
|-----------|------|
| `test_upgrade_relation_and_prev_version` | 已装低版本后识别为升级，并带出已装版本号 |
| `test_downgrade_relation` | 已装高版本后识别为降级 |
| `test_index_declared_selected_undeclared_not` | 有索引时：索引声明项默认勾选，未声明项默认不勾选 |
| `test_no_index_selects_all_by_default` | 无索引时全部默认勾选 |

#### 3.9.4 TestInvalidPackage

| 用例函数名 | 说明 |
|-----------|------|
| `test_invalid_package_reports_diagnostics` | 无插件的压缩包 → invalid + 扫描统计与指引 |
| `test_invalid_package_install_returns_error` | 对无效包执行安装 → 单条错误结果，且不产生任何插件目录 |
| `test_missing_zip_reports_error` | zip 不存在 → 单条错误结果 |

#### 3.9.5 TestTempDirectoryCleanup

| 用例函数名 | 说明 |
|-----------|------|
| `test_temp_dir_removed` | 安装结束后安装器创建的临时目录必须被删除（参数化 2 组：成功 / 无效包） |

#### 3.9.6 TestExtraFileBackup

| 用例函数名 | 说明 |
|-----------|------|
| `test_upgrade_backs_up_extra_files` | 升级前发现包外文件 → 生成快照并在结果里提示 |
| `test_no_backup_without_extra_files` | 无包外文件时不提示、不产生快照 |
| `test_fresh_install_has_no_backup` | 全新安装（无旧目录）不触发快照 |
| `test_backup_failure_does_not_block_install` | 快照失败时降级为提示，不影响安装成功 |

#### 3.9.7 TestTargetScope

| 用例函数名 | 说明 |
|-----------|------|
| `test_inspect_uses_target_scope` | 识别预演的范围跟随 target_scope（官方 Tab → official） |
| `test_inspect_defaults_to_thirdparty` | 未指定范围时保持旧行为（第三方目录） |
| `test_install_into_official_scope` | target_scope=official 时装进官方目录，注册表登记为 official |
| `test_target_dir_wins_over_scope` | 显式 target_dir 优先级高于 target_scope |
| `test_installed_plugin_keeps_its_directory` | 已安装插件即使在另一侧范围下重复安装也保持原地，不产生第二份安装 |

---

### 3.10 `test_plugin_backup.py`

> 测试类 2 个，测试函数 9 个，实测用例 9 个。被测对象：`core/plugin/plugin_backup.py` 的 `collect_extra_files()`、`snapshot_plugin_dir()` 与 `MAX_BACKUPS_PER_PLUGIN`；范围：包外文件检测与排除规则（`.plugin_info.json`、字节码缓存）、整目录快照的命名与内容、旧目录缺失、版本号分隔符消毒、快照份数裁剪。
>
> 本文件测试函数与测试类均自带中文 docstring，说明为原文引用；无参数化，测试函数数与实测用例数一致。

#### 3.10.1 TestCollectExtraFiles

| 用例函数名 | 说明 |
|-----------|------|
| `test_detects_files_missing_from_package` | 旧目录中包内没有的文件被识别出来（按相对路径排序） |
| `test_ignores_plugin_info_and_bytecode` | UUID 文件与字节码缓存不算包外文件 |
| `test_identical_dirs_have_no_extra` | 新旧目录内容一致时无包外文件 |
| `test_missing_old_dir_returns_empty` | 旧目录不存在时返回空列表（全新安装场景） |

#### 3.10.2 TestSnapshotPluginDir

| 用例函数名 | 说明 |
|-----------|------|
| `test_snapshot_copies_content_with_timestamp_and_version` | 快照包含旧目录内容，目录名带时间戳与版本号 |
| `test_snapshot_keeps_plugin_info_and_skips_bytecode` | 快照保留 .plugin_info.json（追溯数据归属），忽略 __pycache__/pyc |
| `test_missing_dir_returns_none` | 旧目录不存在时不产生快照 |
| `test_version_separators_sanitized` | 版本号中的路径分隔符被消毒，不产生额外目录层级 |
| `test_prunes_old_snapshots` | 快照份数超过上限时淘汰最旧的，只保留最近 MAX_BACKUPS_PER_PLUGIN 份 |

---

### 3.11 `test_plugin_move.py`

> 测试类 3 个，测试函数 12 个，实测用例 12 个。被测对象：`core/plugin/manager.py` 的 `PluginManager.move_plugin_to_scope()` / `_scope_directory()`、`_check_move()` 与 `core/plugin/plugin_registry.py` 的 `PluginRegistry.set_scope()`；范围：官方 ↔ 第三方目录移动的正常路径（目录、UUID 文件、注册表分类、分组/排序记录、重新加载后的归属）、拒绝路径（未加载、非法范围、同分类、同名目录冲突）与移动失败的恢复。
>
> 本文件测试类与测试函数均自带中文 docstring，说明为原文引用；无参数化，测试函数数与实测用例数一致。全部用例使用隔离的 `PluginManager`（目录指向 `tmp_path`）与最小假插件（`make_fake_plugin()`），不触碰仓库真实 `plugin/`、`custom_plugin/`、`config/`。

#### 3.11.1 TestScopeDirectory

| 用例函数名 | 说明 |
|-----------|------|
| `test_known_scopes` | official / thirdparty 解析到对应目录 |
| `test_unknown_scope_returns_none` | 非法范围返回 None（由调用方转为失败结果） |

#### 3.11.2 TestMoveSuccess

| 用例函数名 | 说明 |
|-----------|------|
| `test_move_official_to_thirdparty` | 移动后目录、注册表分类与加载列表全部跟随目标分类 |
| `test_uuid_preserved_after_move` | UUID 随目录迁移保持不变（插件数据与语言覆盖以 UUID 为键） |
| `test_move_back_to_official` | 第三方 → 官方往返移动 |
| `test_sort_and_group_records_cleared` | 原分类的排序与分组记录被清除（移动后按未分组处理） |
| `test_registry_entry_fields_preserved` | 移动只改 scope：版本 / 来源 / 安装时间保持不变 |

#### 3.11.3 TestMoveRejected

| 用例函数名 | 说明 |
|-----------|------|
| `test_plugin_not_loaded` | 插件未加载（UUID 不存在）时返回失败 |
| `test_unknown_target_scope` | 目标范围非法时返回失败 |
| `test_same_scope_rejected` | 插件已在目标分类中时返回失败（不重复移动） |
| `test_same_name_directory_conflict` | 目标分类已存在同名目录时拒绝，插件留在原目录 |
| `test_directory_move_failure` | 目录移动抛错时返回失败，并重新扫描目录恢复插件列表 |

---

### 3.12 风险关联（R-01）

| 风险 ID | 描述 | 用例编号 | 覆盖情况 | 状态 |
|---------|------|---------|---------|------|
| R-01 | 插件 API 自动注册硬编码 `"Service"` 类名（服务类未以 `Service` 命名时不会被自动注册） | TC-PLUGIN-025～028 | §3.2.1 `TestAutoRegisterAPI` 全部 4 个用例：自定义 Service 类名（025）、仅注册 Service 类公共方法（026）、空 Service 类不注册（027）、仅私有方法不注册（028） | 已覆盖 |

> `test/core/plugin/` 下代码仅出现 R-01 一个风险标注（见 `test_plugin_api_auto_register.py` 文件头 docstring 与各用例 docstring 的「风险关联」行）。R-02～R-06 属 MCP / 后台任务模块的标注，不在本模块范围内，故本表无「关联待确认」条目；跨模块风险总表见 `test/TESTING.md` §6.1。

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/plugin/` 添加新功能时：
1. 在对应的测试文件中找到测试类（新模块则新建 `test_<模块名>.py`）
2. 添加 `test_*` 测试函数，遵循现有命名规范（`test_<被测行为>_<预期结果>`）
3. docstring 写明测试目的（建议中文），风格与所在文件现有一致；R-01 相关用例沿用 `TC-PLUGIN-0xx` 编号（见 §3.2、§3.12）
4. 使用 `create_minimal_plugin()` 创建测试插件，目录取自 `plugin_dir_from_test` / `tmp_path`
5. 同步更新本文档 §3 清单——代码中每个 `def test_*` 在清单中有且仅有一行，说明按 §3 前言的中译/归纳规则填写，并核对 §1 的统计数字
6. 运行以下命令确认收集数与执行结果：

```powershell
.venv\Scripts\python.exe -m pytest test/core/plugin --collect-only -q -p no:cacheprovider
.venv\Scripts\python.exe -m pytest test/core/plugin -q --tb=short -p no:cacheprovider
```

### 4.2 修复失败的测试

1. 查看测试函数 docstring（或所属测试类 docstring）了解测试目的；标注「归纳：」的用例说明粒度较粗，需直接阅读代码
2. 检查被测代码是否有 bug
3. 如果是 fixture 问题，检查 `plugin_dir_from_test`（返回 `tmp_path / "plugins"`）与 autouse 的 `reset_plugin_manager` / `reset_singletons` 是否生效
4. 日志断言类用例（`warning.assert_called_once()`、`error.assert_called_once()`、`assert_not_called()`）失败时，先确认 `mock_logger` fixture 是否被同名局部 fixture 覆盖

### 4.3 覆盖率目标

- 目标覆盖率: 85%（`core/plugin` 模块）
- 当前覆盖率: **未实测**——本轮刷新未采集覆盖率（`.venv` 未安装 `pytest-cov`，`pytest --cov` 不可用），不引用历史估算值
- 关注的关键路径:
  - 真实文件系统操作（插件目录的实际加载 / 卸载）
  - 复杂插件依赖关系
  - 插件热拔插场景

---

## 5. 相关文档

- [插件系统概述](../../../docs/core/plugin-system/overview.md)
- [插件开发指南](../../../docs/core/plugin-system/plugin-development.md)
- [测试主文档](../TESTING.md)（§6.1 风险覆盖清单）

---
