# LLM 模块测试文档

> LLM 模块的测试策略、测试用例和维护指南

---

## 1. 测试概述

**被测模块**: `core/llm/`
**测试文件数**: 18 个
**测试用例总数**: 283 个（pytest 收集数）
**测试函数总数**: 272 个（可收集的 `def test_*`，统计口径见 §1.3）

实测命令（工作目录 = 项目根）：

```powershell
.venv\Scripts\python.exe -m pytest test/core/llm --collect-only -q -p no:cacheprovider
```

### 1.1 测试文件分布

| 测试文件 | 测试类数 | 测试用例数 | 主要覆盖（测试文件模块 docstring） |
|---------|---------|-----------|--------------------------------|
| `test_adapter_registry.py` | 2 | 6 | 适配器注册表测试（core/llm/providers/__init__.py） |
| `test_catalog.py` | 3 | 10 | 预设目录测试（core/llm/catalog/） |
| `test_config_v2.py` | 5 | 14 | 配置 schema v2 与 v1→v2 迁移测试（core/llm/config.py） |
| `test_conversation_api.py` | 3 | 7 | 会话 API 测试（LLMPluginService 会话管理） |
| `test_conversation_manager.py` | 9 | 16 | core.llm.conversation_manager.ConversationManager 的 pytest 测试。 |
| `test_llm_config.py` | 7 | 20 | core/llm/config.py 的 pytest 测试。 |
| `test_llm_exceptions.py` | 6 | 35 | core/llm/exceptions.py 异常继承体系的 pytest 测试。 |
| `test_llm_provider.py` | 19 | 35 | core.llm.llm_provider.LLMProvider 的 pytest 测试。 |
| `test_llm_provider_runtime.py` | 6 | 12 | LLMProvider 运行时测试（core/llm/llm_provider.py） |
| `test_llm_types.py` | 8 | 23 | core/llm/types.py 领域类型的 pytest 测试。 |
| `test_model_check.py` | 2 | 8 | check_provider / check_model 连通性探测测试（core/llm/llm_provider.py） |
| `test_model_schema.py` | 5 | 13 | 统一模型 schema 测试（core/llm/model_schema.py） |
| `test_plugin_interface.py` | 5 | 12 | ILLMService 接口契约测试（core/interfaces/i_llm_service.py + plugin_service.py） |
| `test_plugin_service.py` | 6 | 11 | test_plugin_service.py — LLMPluginService 单元测试。 |
| `test_secure_keys.py` | 3 | 13 | core.llm.secure_keys 的 pytest 测试。 |
| `test_tool_call_executor.py` | 6 | 23 | core.llm.tool_call_executor 中 ToolRegistry 与 ToolCallExecutor 的 pytest 测试。 |
| `test_tool_calling.py` | 5 | 11 | 工具调用类型化测试（core/llm/tool_call_executor.py + types.py） |
| `test_usage_record_store.py` | 7 | 14 | UsageRecordStore 单元测试 |
| **合计** | **107** | **283** | — |

### 1.2 覆盖范围

按 `core/llm/` 的功能域归并（用例数为 pytest 收集数，合计 283）：

| 功能域 | 测试文件 | 测试用例数 |
|-------|---------|-----------|
| 适配器注册表与预设目录 | `test_adapter_registry.py`, `test_catalog.py` | 16 |
| Provider 配置与密钥存储 | `test_config_v2.py`, `test_llm_config.py`, `test_secure_keys.py` | 47 |
| Provider 运行时与路由 | `test_llm_provider.py`, `test_llm_provider_runtime.py` | 47 |
| 模型 schema 与连通性检查 | `test_model_schema.py`, `test_model_check.py` | 21 |
| 会话管理 | `test_conversation_manager.py`, `test_conversation_api.py` | 23 |
| 工具调用 | `test_tool_call_executor.py`, `test_tool_calling.py` | 34 |
| 插件门面与接口契约 | `test_plugin_service.py`, `test_plugin_interface.py` | 23 |
| 类型定义与异常体系 | `test_llm_types.py`, `test_llm_exceptions.py` | 58 |
| 用量记录 | `test_usage_record_store.py` | 14 |

### 1.3 统计口径

- **用例数**：`pytest --collect-only` 的收集数，共 283 个；
- **测试函数数**：源码中 `def test_` 开头的定义共 273 处，其中 1 处为测试函数内部定义的本地 handler（`test_tool` @ `test_tool_call_executor.py` 第 343 行），pytest 不收集；**可收集的测试函数共 272 个**（§3 共 272 行，按「测试文件 + 测试类 + 函数名」三元组计）；
- **名称去重**：273 处定义对应 261 个唯一名称（含上述本地 handler）；按可收集的 272 个测试函数计为 260 个唯一名称——8 个名称在多个测试类中重复出现，合计多出 12 行（如 `test_defaults`、`test_all_fields`、`test_returns_false_for_missing_id`）；
- 用例数与测试函数数的差值 11 来自参数化展开（`@pytest.mark.parametrize`）：
  - `test_llm_exceptions.py::TestExceptionInheritance::test_all_exceptions_inherit_from_llm_exception`：9 个参数 → 9 个用例（+8）
  - `test_secure_keys.py::TestRoundTrip::test_round_trip`：4 个参数 → 4 个用例（+3）
- 本文档 §3 的用例清单**按测试函数逐行列出**（272 行），参数化函数在「用例函数名」列标注展开例数；
- 「说明」列一律为中文，取自该测试函数 docstring 的**中文原文或中文直译**（保留标识符原文），英文 docstring 的原文附在同类的说明行中；测试函数无 docstring 时按**函数名 + 所属测试类**归纳，此类行说明粒度较粗（详见 §3 前言）。

---

## 2. 测试策略

### 2.1 隔离措施

- `LLMConfig` 被 mock 以避免文件系统访问
- 使用 `_make_provider()` 辅助函数创建隔离的 LLMProvider 实例
- `ConversationManager` 使用 mock LLM 返回可预测的 `ChatResponse`
- 单例由 `test/conftest.py` 的 `reset_singletons` fixture（autouse）自动重置
- 整个 `test/core/llm/` 目录由 `test/core/llm/conftest.py` 的 `isolated_llm_environment` fixture（autouse）隔离：配置路径常量与会话持久化路径指向 `tmp_path`（不读写真实 `config/` 与 `data/`），并注册可控的 `mock-adapter` 适配器家族键，全程无真实网络访问

### 2.2 测试数据

- Mock LLM 返回可配置的 `content` 和 `usage`
- 工具测试使用简单的 handler 函数（如 `lambda x: x * 2`）
- 对话测试使用 UUID 格式验证

### 2.3 关键测试辅助函数

```python
# test_llm_provider.py
def _make_provider(mocker):
    """返回隔离的 LLMProvider 实例，LLMConfig 被 mock"""
    mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
    mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
    mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)
    return lp_module.LLMProvider()

# test_conversation_manager.py
def _make_mock_llm(content="hello", usage=None, tool_calls=None):
    """返回可预测的 mock LLM"""
    mock.chat.return_value = ChatResponse(content=content, ...)
    return mock
```

`test/core/llm/conftest.py` 提供的共享 fixture：

| fixture | 作用（conftest docstring 原文） |
|---------|------------------------------|
| `isolated_llm_environment`（autouse） | 隔离 LLM 运行环境（autouse） |
| `config_file` | 隔离后的配置文件路径（llm_providers.json） |
| `write_config` | 写入配置文件工具：data -> 落盘 JSON 并返回路径 |
| `v1_config_data` | v1 配置样本工厂（每次调用返回全新样本） |
| `v2_config_data` | v2 配置样本工厂 |
| `mock_config_factory` | Mock 适配器实例配置工厂 |

---

## 3. 测试用例

本节按**测试文件 → 测试类**分组列出全部用例，用例名即代码中的测试函数名。

> **「说明」列的来源与口径**：
> 1. 说明文字**一律为中文**，全部由被测测试代码的 docstring 或紧邻注释**翻译 / 归纳**而来，未新增任何代码中不存在的断言、步骤或优先级；
> 2. 代码 docstring 为中文时直接引用原文；为英文时做**中文直译**（保留函数名、类名、字段名、参数名等标识符原文），并在类/文件说明行附上英文原文便于核对；
> 3. 测试函数**没有 docstring** 时，按**函数名 + 所属测试类**归纳其意图——此类行的说明**粒度较粗**，仅用于定位用例，不代表逐条断言；相关文件（`test_llm_exceptions.py`、`test_llm_types.py`、`test_usage_record_store.py`）在各自小节开头另有「说明粒度」提示；
> 4. 历史版本中的 `TC-LLM-NNN` 计划编号与「优先级 / 前置条件 / 测试步骤 / 预期结果」段落已废弃（其为编写计划，与现有代码不对应），用例以真实函数名标识。
### 3.1 `test_adapter_registry.py`

> **被测模块 docstring**: 适配器注册表测试（core/llm/providers/__init__.py）
>
> 覆盖：adapter 键查类、未注册异常路径、旧名薄别名等价、 同 adapter 多实例共存。

**测试用例数**: 6（测试类 2 个）

#### 3.1.1 `TestAdapterRegistry`

> 类 docstring：适配器家族注册表

| 用例函数名 | 说明 |
|-----------|------|
| `test_builtin_adapters_registered` | 内置 6 个适配器家族键全部注册，且映射到 BaseProvider 子类 |
| `test_unknown_adapter_returns_none` | 查询未注册的 adapter 键返回 None（异常路径不抛异常） |
| `test_register_adapter_roundtrip` | register_adapter 注册新键可查，返回原类（可作装饰器） |
| `test_legacy_aliases_equivalent` | 旧名薄别名与新函数语义一致（适配器家族） |

#### 3.1.2 `TestMultiInstanceSameAdapter`

> 类 docstring：同一 adapter 多实例共存

| 用例函数名 | 说明 |
|-----------|------|
| `test_two_instances_share_adapter` | 两个实例共用 mock-adapter，运行时各自独立创建 |
| `test_unknown_adapter_instance_skipped` | 未知 adapter 的实例被跳过且不崩溃，不影响其余实例 |

---

### 3.2 `test_catalog.py`

> **被测模块 docstring**: 预设目录测试（core/llm/catalog/）
>
> 覆盖：目录完整性（适配器注册、Logo 文件、端点拼接）、兜底适配器、 目录数据不可变约束、预设模型目录一致性。

**测试用例数**: 10（测试类 3 个）

#### 3.2.1 `TestProviderPresets`

> 类 docstring：提供商预设目录数据

| 用例函数名 | 说明 |
|-----------|------|
| `test_preset_table_complete` | 目录包含 5 家内置预设，键与 preset_id 一致 |
| `test_every_preset_adapter_registered` | 每个预设的 adapter 均已在适配器注册表中注册 |
| `test_every_preset_logo_exists` | 每个预设的 Logo 文件存在于 catalog/logos/ 并可解析 |
| `test_endpoint_concatenation_legal` | default_base_url 与 chat_endpoint_path 拼接为合法 http(s) 地址 |
| `test_preset_is_frozen` | 目录数据为 frozen dataclass，不允许运行时修改 |
| `test_get_provider_preset_unknown_returns_none` | 查询不存在的预设返回 None（边界） |

#### 3.2.2 `TestCustomAdapter`

> 类 docstring：自定义 OpenAI 兼容兜底适配器

| 用例函数名 | 说明 |
|-----------|------|
| `test_custom_adapter_registered` | CUSTOM_ADAPTER 为 openai-compatible 且已注册 |
| `test_custom_adapter_reuses_openai_protocol` | 兜底适配器复用 OpenAIProvider 协议实现（子类关系） |

#### 3.2.3 `TestPresetModels`

> 类 docstring：预设模型目录

| 用例函数名 | 说明 |
|-----------|------|
| `test_preset_models_keys_subset_of_presets` | PRESET_MODELS 的键均为已注册预设（当前收录 glm / minimax） |
| `test_preset_model_entries_normalized` | 预设模型条目均为统一 schema（capabilities 合法、键齐备） |

---

### 3.3 `test_config_v2.py`

> **被测模块 docstring**: 配置 schema v2 与 v1→v2 迁移测试（core/llm/config.py）
>
> 覆盖：迁移（备份、字段映射、双 schema 规范化、密钥编解码）、 读写往返、不再自动补齐、单例与变更订阅。

**测试用例数**: 14（测试类 5 个）

#### 3.3.1 `TestV1ToV2Migration`

> 类 docstring：v1 → v2 自动迁移

| 用例函数名 | 说明 |
|-----------|------|
| `test_migration_fields_and_backup` | 迁移后字段映射正确且生成时间戳 .bak 备份 |
| `test_migration_unifies_mixed_custom_models` | v1 混合双 schema 的 custom_models 迁移后统一为新 schema |
| `test_migration_api_key_decoded` | 迁移路径 api_key 落盘编码不变、加载后解码为明文 |

#### 3.3.2 `TestV2RoundTrip`

> 类 docstring：v2 读写往返

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_v2_and_field_roundtrip` | v2 加载字段守恒（含 order 与自定义实例） |
| `test_save_then_reload_consistent` | save 后重置单例重新加载：字段守恒、密钥编码还原、order 持久化 |
| `test_api_key_encoded_on_disk` | api_key 落盘为 b64: 编码（明文不落盘） |

#### 3.3.3 `TestNoDefaultBackfill`

> 类 docstring：不再自动补齐默认 provider

| 用例函数名 | 说明 |
|-----------|------|
| `test_first_run_creates_empty_v2` | 配置文件不存在时创建空 providers 的 v2 文件（目录即默认值） |
| `test_removed_instance_not_revived` | 删除实例后重新加载不复活 |

#### 3.3.4 `TestSingletonAndSubscription`

> 类 docstring：单例与变更订阅

| 用例函数名 | 说明 |
|-----------|------|
| `test_singleton_identity` | 多处 LLMConfig() 与 get_llm_config() 为同一实例 |
| `test_subscribe_notified_and_version_increments` | add/remove/save 触发回调（事件名与实例 id），version 单调递增 |
| `test_callback_exception_does_not_break_others` | 订阅回调异常被吞并记日志，不影响主流程与其余回调 |
| `test_unsubscribe_stops_notification` | 退订后不再收到通知 |

#### 3.3.5 `TestProviderConfigDict`

> 类 docstring：ProviderConfig 序列化

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_dict_from_dict_roundtrip` | to_dict / from_dict 字段守恒（v2 字段集 + extra） |
| `test_from_dict_drops_legacy_provider_type` | from_dict 静默丢弃 v1 残留的 provider_type 键（不落入 extra） |

---

### 3.4 `test_conversation_api.py`

> **被测模块 docstring**: 会话 API 测试（LLMPluginService 会话管理）
>
> 覆盖：create/send/stream/get/list/delete 全流程、返回类型一致性、 model/provider 临时覆盖、Message.from_dict 宽松解析、用量统计。

**测试用例数**: 7（测试类 3 个）

#### 3.4.1 `TestConversationLifecycle`

> 类 docstring：会话全流程

| 用例函数名 | 说明 |
|-----------|------|
| `test_full_lifecycle` | create/send/get/list/delete 全流程正常路径 |
| `test_send_to_missing_conversation_raises` | 向不存在的会话发送消息抛 ValueError（异常路径） |
| `test_temporary_override_keeps_binding` | send_message 的 model/provider 临时覆盖不修改会话绑定 |
| `test_stream_send_message` | 流式发送：callback 逐块回调（StreamChunk 实填）+ 完整文本 + 历史追加 |

#### 3.4.2 `TestMessageLenientParsing`

> 类 docstring：dict 消息宽松解析

| 用例函数名 | 说明 |
|-----------|------|
| `test_dict_messages_with_extended_keys` | 含 images/tool_calls 扩展键的 dict 消息经 chat 不炸 |
| `test_unknown_keys_go_extra` | 未知键收入 extra，不影响调用（边界） |

#### 3.4.3 `TestUsageStats`

> 类 docstring：用量统计

| 用例函数名 | 说明 |
|-----------|------|
| `test_usage_accumulated` | 带 UsageInfo 的响应自动累计 token 与费用统计 |

---

### 3.5 `test_conversation_manager.py`

> **被测模块 docstring（中文直译）**: core.llm.conversation_manager.ConversationManager 的 pytest 测试。
>
> 原文：pytest tests for core.llm.conversation_manager.ConversationManager.

**测试用例数**: 16（测试类 9 个）

#### 3.5.1 `TestCreateConversation`

> 代码分节注释（中文直译）：create_conversation 的测试｜原文：Test: create_conversation

| 用例函数名 | 说明 |
|-----------|------|
| `test_creates_conversation_and_returns_uuid` | create_conversation() 生成 UUID 并存入 _conversations。 |
| `test_create_conversation_with_system_prompt` | create_conversation() 传入 system_prompt 时会将其设置到 Conversation 上。 |

#### 3.5.2 `TestGetConversation`

> 代码分节注释（中文直译）：get_conversation 的测试｜原文：Test: get_conversation

| 用例函数名 | 说明 |
|-----------|------|
| `test_returns_conversation_when_exists` | get_conversation() 返回 Conversation 对象。 |
| `test_returns_none_for_missing_id` | get_conversation() 对不存在的 ID 返回 None。 |

#### 3.5.3 `TestListConversations`

> 代码分节注释（中文直译）：list_conversations 的测试｜原文：Test: list_conversations

| 用例函数名 | 说明 |
|-----------|------|
| `test_returns_list_of_all_conversations` | list_conversations() 返回全部会话的列表。 |

#### 3.5.4 `TestDeleteConversation`

> 代码分节注释（中文直译）：delete_conversation 的测试｜原文：Test: delete_conversation

| 用例函数名 | 说明 |
|-----------|------|
| `test_removes_conversation_and_returns_true` | delete_conversation() 删除会话并返回 True。 |
| `test_returns_false_for_missing_id` | delete_conversation() 对不存在的 ID 返回 False。 |

#### 3.5.5 `TestSendMessage`

> 代码分节注释（中文直译）：send_message 的测试｜原文：Test: send_message

| 用例函数名 | 说明 |
|-----------|------|
| `test_raises_value_error_for_missing_conversation` | 向不存在的会话 send_message() 抛出 ValueError。 |
| `test_builds_messages_and_calls_llm_chat` | send_message() 构造消息列表并调用 _llm.chat()。 |
| `test_adds_response_to_conversation_messages` | send_message() 把用户消息与助手响应都追加到 conversation.messages。 |

#### 3.5.6 `TestStreamSendMessage`

> 代码分节注释（中文直译）：stream_send_message 的测试｜原文：Test: stream_send_message

| 用例函数名 | 说明 |
|-----------|------|
| `test_raises_value_error_for_missing_conversation` | 向不存在的会话 stream_send_message() 抛出 ValueError。 |
| `test_calls_llm_stream_chat_with_callback` | stream_send_message() 带 callback 调用 _llm.stream_chat()。 |

#### 3.5.7 `TestEstimateCost`

> 代码分节注释（中文直译）：_estimate_cost 的测试｜原文：Test: _estimate_cost

| 用例函数名 | 说明 |
|-----------|------|
| `test_returns_correct_float` | _estimate_cost() 返回正确的费用计算结果。 |

#### 3.5.8 `TestGetOrRaise`

> 代码分节注释（中文直译）：_get_or_raise 的测试｜原文：Test: _get_or_raise

| 用例函数名 | 说明 |
|-----------|------|
| `test_raises_value_error_for_missing_conversation` | _get_or_raise() 对不存在的会话抛出 ValueError。 |

#### 3.5.9 `TestGetUsageStats`

> 代码分节注释（中文直译）：get_usage_stats 的测试｜原文：Test: get_usage_stats

| 用例函数名 | 说明 |
|-----------|------|
| `test_aggregates_across_all_conversations` | get_usage_stats() 不传参时聚合全部会话的统计。 |
| `test_returns_stats_for_specific_conversation` | get_usage_stats(conv_id) 只返回该会话的统计。 |

---

### 3.6 `test_llm_config.py`

> **被测模块 docstring（中文直译）**: core/llm/config.py 的 pytest 测试。
>
> 原文：pytest tests for core/llm/config.py

**测试用例数**: 20（测试类 7 个）

#### 3.6.1 `TestProviderConfig`

> 类 docstring（中文直译）：ProviderConfig.to_dict / from_dict 的测试。｜原文：Tests for ProviderConfig.to_dict / from_dict.

| 用例函数名 | 说明 |
|-----------|------|
| `test_to_dict_roundtrip` | to_dict() 保留全部字段（含 extra 中的额外 kwargs）。 |
| `test_from_dict_preserves_extra` | from_dict() 把未知字段存入 extra。 |
| `test_from_dict_to_dict_roundtrip` | to_dict → from_dict 往返后全部字段保持不变。 |

#### 3.6.2 `TestLLMConfigCreateDefault`

> 类 docstring：Tests for LLMConfig._create_default_config()（v2：目录即默认值，不再补齐内置 Provider）。

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_default_config_empty_providers` | _create_default_config() 创建空 providers 配置（v2 不再自动补齐内置提供商）。 |
| `test_create_default_config_saves_to_disk` | _create_default_config() 写入 version=当前 schema 版本、空 providers 的配置文件。 |

#### 3.6.3 `TestLLMConfigLoad`

> 类 docstring（中文直译）：LLMConfig._load_config() 的测试。｜原文：Tests for LLMConfig._load_config().

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_config_parses_existing_json` | _load_config() 能正确解析已存在的 JSON 文件。 |
| `test_load_config_skips_default_creation_when_file_exists` | CONFIG_FILE 已存在时 _load_config() 不调用 _create_default_config。 |

#### 3.6.4 `TestLLMConfigSave`

> 类 docstring（中文直译）：LLMConfig.save_config() 的测试。｜原文：Tests for LLMConfig.save_config().

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_config_writes_valid_json` | save_config() 写出合法、可解析的 JSON 文件。 |

#### 3.6.5 `TestLLMConfigGet`

> 类 docstring（中文直译）：get_provider / get_all_providers / get_enabled_providers 的测试。｜原文：Tests for get_provider / get_all_providers / get_enabled_providers.

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_provider_returns_config` | provider 存在时 get_provider() 返回其 ProviderConfig。 |
| `test_get_provider_returns_none_for_missing` | provider 不存在时 get_provider() 返回 None。 |
| `test_get_all_providers_returns_copy` | get_all_providers() 返回副本，而不是内部字典本身。 |
| `test_get_enabled_providers_chat` | get_enabled_providers('chat') 只返回 enabled_chat=True 的 provider。 |
| `test_get_enabled_providers_embedding` | get_enabled_providers('embedding') 只返回 enabled_embedding=True 的 provider。 |

#### 3.6.6 `TestLLMConfigAddRemove`

> 类 docstring（中文直译）：add_provider / remove_provider 的测试。｜原文：Tests for add_provider / remove_provider.

| 用例函数名 | 说明 |
|-----------|------|
| `test_add_provider_saves_and_updates_memory` | add_provider() 更新内存中的配置并持久化到磁盘。 |
| `test_remove_provider_removes_and_saves` | remove_provider() 从内存移除、落盘保存并返回 True。 |
| `test_remove_provider_returns_false_for_missing` | provider 不存在时 remove_provider() 返回 False。 |

#### 3.6.7 `TestLLMConfigModelsCache`

> 类 docstring（中文直译）：模型缓存相关操作的测试。｜原文：Tests for models cache operations.

| 用例函数名 | 说明 |
|-----------|------|
| `test_save_and_load_models_cache_roundtrip` | save_models_cache / load_models_cache 读写往返可用。 |
| `test_load_models_cache_returns_none_for_unknown_provider` | provider 不在缓存中时 load_models_cache() 返回 None。 |
| `test_load_models_cache_returns_empty_dict_if_file_absent` | MODELS_CACHE_FILE 不存在时 _load_models_cache() 返回 {}。 |
| `test_load_models_cache_returns_empty_dict_on_corrupted_json` | 文件内容不是合法 JSON 时 _load_models_cache() 返回 {}。 |

---

### 3.7 `test_llm_exceptions.py`

> **被测模块 docstring（中文直译）**: core/llm/exceptions.py 异常继承体系的 pytest 测试。
>
> 原文：pytest tests for core/llm/exceptions.py exception hierarchy.

**测试用例数**: 35（测试类 6 个）
**说明粒度**：本文件测试函数与测试类均无 docstring，「说明」列按**函数名 + 所属测试类**归纳，粒度较粗，仅用于定位用例意图。

#### 3.7.1 `TestExceptionInheritance`

> 类 docstring（中文直译）：验证全部 9 个异常类均继承自 LLMException。｜原文：Test that all 9 exception classes inherit from LLMException.

| 用例函数名 | 说明 |
|-----------|------|
| `test_all_exceptions_inherit_from_llm_exception`（参数化 9 例） | 逐个校验异常类是否为 LLMException 的子类（参数化覆盖 9 个异常类）。 |
| `test_rate_limit_error_inherits_from_api_error` | 校验 RateLimitError 继承自 APIError。 |
| `test_api_error_inherits_from_llm_exception` | 校验 APIError 继承自 LLMException。 |

#### 3.7.2 `TestAPIErrorAttributes`

> 类 docstring（中文直译）：验证 APIError 的 status_code 与 provider 属性可访问。｜原文：Test APIError has accessible status_code and provider attributes.

| 用例函数名 | 说明 |
|-----------|------|
| `test_api_error_with_status_code_and_provider` | 构造带 status_code 与 provider 的 APIError，校验两个属性及 args[0] 中的消息。 |
| `test_api_error_without_args` | 仅传消息构造 APIError 时，status_code 与 provider 均为 None。 |
| `test_api_error_message_only` | 校验 APIError 的消息保存在 args[0]。 |

#### 3.7.3 `TestConnectionErrorAttributes`

> 类 docstring（中文直译）：验证 ConnectionError 的 provider 与 extra 属性可访问。｜原文：Test ConnectionError has accessible provider and extra attributes.

| 用例函数名 | 说明 |
|-----------|------|
| `test_connection_error_with_provider_and_extra` | 构造带 provider 与 extra 的 ConnectionError，校验 provider 与 extra 属性。 |
| `test_connection_error_empty_message` | 空消息构造的 ConnectionError，其 args[0] 为空字符串。 |
| `test_connection_error_with_multiple_extra_kwargs` | 多个额外 kwargs（timeout/url 等）均被存入 ConnectionError.extra。 |

#### 3.7.4 `TestTimeoutErrorAttributes`

> 类 docstring（中文直译）：验证 TimeoutError 的 provider 与 extra 属性可访问。｜原文：Test TimeoutError has accessible provider and extra attributes.

| 用例函数名 | 说明 |
|-----------|------|
| `test_timeout_error_with_provider_and_extra` | 构造带 provider 与 extra 的 TimeoutError，校验 provider 与 extra 属性。 |
| `test_timeout_error_empty_message` | 空消息构造的 TimeoutError，其 args[0] 为空字符串。 |
| `test_timeout_error_with_multiple_extra_kwargs` | 多个额外 kwargs（timeout/endpoint 等）均被存入 TimeoutError.extra。 |

#### 3.7.5 `TestExceptionCatching`

> 类 docstring（中文直译）：验证各异常均可按基类 LLMException 捕获。｜原文：Test that exceptions can be caught as LLMException (base class).

| 用例函数名 | 说明 |
|-----------|------|
| `test_configuration_error_caught_as_llm_exception` | 抛出 ConfigurationError 后可被基类 LLMException 捕获。 |
| `test_authentication_error_caught_as_llm_exception` | 抛出 AuthenticationError 后可被基类 LLMException 捕获。 |
| `test_api_error_caught_as_llm_exception` | 抛出 APIError 后可被基类 LLMException 捕获。 |
| `test_rate_limit_error_caught_as_llm_exception` | 抛出 RateLimitError 后可被基类 LLMException 捕获。 |
| `test_invalid_request_error_caught_as_llm_exception` | 抛出 InvalidRequestError 后可被基类 LLMException 捕获。 |
| `test_model_not_supported_error_caught_as_llm_exception` | 抛出 ModelNotSupportedError 后可被基类 LLMException 捕获。 |
| `test_connection_error_caught_as_llm_exception` | 抛出 ConnectionError 后可被基类 LLMException 捕获。 |
| `test_timeout_error_caught_as_llm_exception` | 抛出 TimeoutError 后可被基类 LLMException 捕获。 |
| `test_streaming_error_caught_as_llm_exception` | 抛出 StreamingError 后可被基类 LLMException 捕获。 |

#### 3.7.6 `TestExceptionSeparation`

> 类 docstring（中文直译）：验证 ConfigurationError 与 APIError 相互独立（继承关系不同）。｜原文：Test that ConfigurationError is separate from APIError (different inheritance).

| 用例函数名 | 说明 |
|-----------|------|
| `test_configuration_error_is_not_api_error` | 校验 ConfigurationError 不是 APIError 的子类。 |
| `test_authentication_error_is_not_api_error` | 校验 AuthenticationError 不是 APIError 的子类。 |
| `test_rate_limit_error_is_api_error` | 校验 RateLimitError 是 APIError 的子类。 |
| `test_raising_configuration_error_does_not_match_api_error` | 抛出 ConfigurationError 时按 ConfigurationError 捕获（不与 APIError 混淆）。 |
| `test_raising_api_error_does_not_match_configuration_error` | 抛出 APIError 时按 APIError 捕获（不与 ConfigurationError 混淆）。 |
| `test_rate_limit_error_caught_as_api_error` | 抛出 RateLimitError 后可被 APIError 捕获。 |

---

### 3.8 `test_llm_provider.py`

> **被测模块 docstring（中文直译）**: core.llm.llm_provider.LLMProvider 的 pytest 测试。
>
> 原文：pytest tests for core.llm.llm_provider.LLMProvider.

**测试用例数**: 35（测试类 19 个）

#### 3.8.1 `TestSingleton`

> 代码分节注释（中文直译）：1. 单例——双重检查锁定，实例只创建一次｜原文：1. Singleton — double-checked locking, instance created once

| 用例函数名 | 说明 |
|-----------|------|
| `test_singleton_returns_same_instance` | 重复调用 LLMProvider() 返回同一实例。 |
| `test_singleton_idempotent_init` | 多次调用时 __init__ 只执行一次。 |
| `test_singleton_double_checked_locking` | 双重检查锁定：两个线程拿到同一实例。 |

#### 3.8.2 `TestCreateProvider`

> 代码分节注释（中文直译）：2. _create_provider 对未知 provider_type 抛出 ConfigurationError｜原文：2. _create_provider raises ConfigurationError for unknown provider_type

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_provider_skips_unknown_adapter` | _create_provider 遇到未注册适配器时跳过该实例（返回 None、不注册，不抛异常）。 |
| `test_create_provider_success` | _create_provider 创建 provider 实例并存储。 |

#### 3.8.3 `TestChat`

> 代码分节注释（中文直译）：3. chat——默认路由与错误｜原文：3. chat — default routing, errors

| 用例函数名 | 说明 |
|-----------|------|
| `test_chat_default_selects_first_enabled` | chat(provider='default') 选择第一个启用的 chat provider。 |
| `test_chat_raises_no_enabled_providers` | 没有任何启用的 provider 时 chat() 抛出 ConfigurationError。 |
| `test_chat_raises_provider_not_found` | 指定的 provider 不存在时 chat() 抛出 ConfigurationError。 |
| `test_chat_passes_messages_to_provider` | chat() 把 Message 对象与 dict 原样传给 provider.chat。 |
| `test_chat_named_provider_routes_correctly` | chat(provider='prov_b') 调用正确的 provider 实例。 |

#### 3.8.4 `TestStreamChat`

> 代码分节注释（中文直译）：7. stream_chat 路由与错误｜原文：7. stream_chat routing and errors

| 用例函数名 | 说明 |
|-----------|------|
| `test_stream_chat_default_selects_first_enabled` | stream_chat(provider='default') 选择第一个启用的 provider。 |
| `test_stream_chat_raises_no_enabled_providers` | 没有任何启用的 provider 时 stream_chat() 抛出 ConfigurationError。 |

#### 3.8.5 `TestEmbed`

> 代码分节注释（中文直译）：9. embed 路由与错误｜原文：9. embed routing and errors

| 用例函数名 | 说明 |
|-----------|------|
| `test_embed_default_selects_first_enabled_embedding` | embed(provider='default') 选择第一个启用的 embedding provider。 |
| `test_embed_raises_no_enabled_embedding_providers` | 没有启用的 embedding provider 时 embed() 抛出 ConfigurationError。 |

#### 3.8.6 `TestAddProvider`

> 代码分节注释（中文直译）：11. add_provider｜原文：11. add_provider

| 用例函数名 | 说明 |
|-----------|------|
| `test_add_provider_saves_and_creates_instance` | add_provider() 保存到配置并创建 provider 实例。 |

#### 3.8.7 `TestRemoveProvider`

> 代码分节注释（中文直译）：12. remove_provider｜原文：12. remove_provider

| 用例函数名 | 说明 |
|-----------|------|
| `test_remove_provider_closes_removes_and_deletes_config` | remove_provider() 关闭实例、从字典移除并从配置中删除。 |

#### 3.8.8 `TestReloadConfig`

> 代码分节注释（中文直译）：13. reload_config｜原文：13. reload_config

| 用例函数名 | 说明 |
|-----------|------|
| `test_reload_config_closes_all_recreates_providers` | reload_config() 关闭全部 provider 并按新配置重建。 |

#### 3.8.9 `TestGetProvider`

> 代码分节注释（中文直译）：14. get_provider｜原文：14. get_provider

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_provider_returns_instance` | provider 存在时 get_provider() 返回该实例。 |
| `test_get_provider_returns_none_for_missing` | provider 不存在时 get_provider() 返回 None。 |

#### 3.8.10 `TestGetAllProviders`

> 代码分节注释（中文直译）：15. get_all_providers｜原文：15. get_all_providers

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_all_providers_returns_copy` | get_all_providers() 返回副本——修改它不影响内部字典。 |

#### 3.8.11 `TestGetCachedModels`

> 代码分节注释（中文直译）：16. get_cached_models｜原文：16. get_cached_models

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_cached_models_returns_list` | 已知 provider 时 get_cached_models() 返回缓存的模型列表。 |
| `test_get_cached_models_returns_empty_for_unknown` | 未知 provider 时 get_cached_models() 返回 []。 |

#### 3.8.12 `TestGetEnabledProviders`

> 代码分节注释（中文直译）：17-18. get_enabled_providers——chat / embedding｜原文：17-18. get_enabled_providers — chat / embedding

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_enabled_providers_chat` | get_enabled_providers('chat') 返回 enabled_chat=True 的 provider。 |
| `test_get_enabled_providers_embedding` | get_enabled_providers('embedding') 返回 enabled_embedding=True 的 provider。 |

#### 3.8.13 `TestAsyncChat`

> 代码分节注释（中文直译）：19. async_chat｜原文：19. async_chat

| 用例函数名 | 说明 |
|-----------|------|
| `test_async_chat_default_routing` | async_chat(provider='default') 委托给第一个启用的 provider。 |
| `test_async_chat_named_provider` | async_chat(provider='prov_b') 路由到指定的具名 provider。 |

#### 3.8.14 `TestClose`

> 代码分节注释（中文直译）：20. close｜原文：20. close

| 用例函数名 | 说明 |
|-----------|------|
| `test_close_clears_all_providers` | close() 对每个 provider 调用 close() 并清空字典。 |

#### 3.8.15 `TestRefreshProviderModels`

> 代码分节注释（中文直译）：补充覆盖：refresh_provider_models、get_models、available_providers｜原文：Additional coverage: refresh_provider_models, get_models, available_providers

| 用例函数名 | 说明 |
|-----------|------|
| `test_refresh_provider_models_success` | refresh_provider_models 调用 provider.refresh_models 并更新缓存。 |
| `test_refresh_provider_models_unknown_provider` | 未知 provider 时 refresh_provider_models 返回 []。 |

#### 3.8.16 `TestGetModels`

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_models_specific_provider` | get_models('prov') 只返回该 provider 的模型列表。 |
| `test_get_models_all_providers` | get_models() 返回全部 provider 的模型列表。 |

#### 3.8.17 `TestAvailableProviders`

| 用例函数名 | 说明 |
|-----------|------|
| `test_available_providers_returns_registry_keys` | available_providers 返回 list(PROVIDER_REGISTRY.keys())。 |

#### 3.8.18 `TestChatParameterFiltering`

> 代码分节注释（中文直译）：12. 参数过滤与默认值解析｜原文：12. Parameter filtering and default resolution

| 用例函数名 | 说明 |
|-----------|------|
| `test_filter_none_kwargs_removes_none_values` | _filter_none_kwargs 剔除值为 None 的键。 |
| `test_model_default_resolved_to_none` | model='default' 会被解析为 None，不会传给底层 provider。 |

#### 3.8.19 `TestStreamChatCallback`

| 用例函数名 | 说明 |
|-----------|------|
| `test_stream_callback_receives_chunks_and_done` | stream_chat 正确调用 callback 并传递 chunk 和 done 标志。 |

---

### 3.9 `test_llm_provider_runtime.py`

> **被测模块 docstring**: LLMProvider 运行时测试（core/llm/llm_provider.py）
>
> 覆盖：adapter 分发、健康查询、配置版本惰性刷新、默认实例解析与 粘性缓存、实例增删同步。

**测试用例数**: 12（测试类 6 个）

#### 3.9.1 `TestEmptyConfig`

> 类 docstring：空配置的优雅处理

| 用例函数名 | 说明 |
|-----------|------|
| `test_empty_config_basics` | 空配置：初始化不崩、无启用实例、默认解析为 None |
| `test_chat_without_provider_raises` | 空配置 chat 抛出 ConfigurationError（异常路径） |

#### 3.9.2 `TestAdapterDispatch`

> 类 docstring：按 adapter 分发创建实例

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_provider_by_adapter` | _create_provider 按 adapter 键查注册表创建实例 |
| `test_get_llm_provider_singleton` | get_llm_provider() 返回单例 |

#### 3.9.3 `TestHealthTracking`

> 类 docstring：健康状态查询（get_provider_health 签名修复回归）

| 用例函数名 | 说明 |
|-----------|------|
| `test_health_full_dict_when_none` | name=None 返回全量健康字典（修复前端零参调用被吞的回归） |
| `test_health_single_and_failure_recorded` | 带参返回单个元组；调用失败后记录 (False, 错误) |

#### 3.9.4 `TestLazyRefresh`

> 类 docstring：配置版本比对惰性刷新

| 用例函数名 | 说明 |
|-----------|------|
| `test_entry_refreshes_after_config_change` | 经 LLMConfig 直接增配后，公开入口自动刷新（无需手动 reload） |
| `test_lazy_refresh_syncs_version` | 惰性刷新后版本号同步，不重复全量刷新 |

#### 3.9.5 `TestDefaultProviderResolution`

> 类 docstring：默认实例解析与粘性缓存

| 用例函数名 | 说明 |
|-----------|------|
| `test_default_resolution_and_sticky_cache` | DEFAULT_PROVIDER 解析为首个启用实例并粘性记忆 |
| `test_default_reselected_after_removal` | 默认实例被移除后自动重新选择 |

#### 3.9.6 `TestAddRemoveSync`

> 类 docstring：实例增删的运行时同步

| 用例函数名 | 说明 |
|-----------|------|
| `test_add_remove_provider_runtime` | add/remove 后运行时实例表同步增删，健康状态清理 |
| `test_add_then_chat_uses_mock_adapter` | 新增实例后 chat 路由到 Mock 适配器（正常路径） |

---

### 3.10 `test_llm_types.py`

> **被测模块 docstring（中文直译）**: core/llm/types.py 领域类型的 pytest 测试。
>
> 原文：pytest tests for core/llm/types.py domain types.

**测试用例数**: 23（测试类 8 个）
**说明粒度**：本文件测试函数与测试类均无 docstring，「说明」列按**函数名 + 所属测试类**归纳，粒度较粗，仅用于定位用例意图。

#### 3.10.1 `TestConversationToLlmFormat`

> 类 docstring（中文直译）：验证 Conversation.to_llm_format() 的行为。｜原文：Test Conversation.to_llm_format() behavior.

| 用例函数名 | 说明 |
|-----------|------|
| `test_without_system_prompt_returns_just_messages` | 未设置 system_prompt 时 to_llm_format() 只返回消息列表。 |
| `test_with_system_prompt_prepends_system_role_message` | 设置 system_prompt 后 to_llm_format() 在首位插入 role=system 的消息。 |
| `test_with_system_prompt_only_no_messages` | 只有 system_prompt、没有消息时，返回仅含 system 消息的列表。 |
| `test_empty_conversation_returns_empty_list` | 空会话的 to_llm_format() 返回空列表。 |

#### 3.10.2 `TestConversationAddMessage`

> 类 docstring（中文直译）：验证 Conversation.add_message() 与 token/费用累计。｜原文：Test Conversation.add_message() and token/cost accumulation.

| 用例函数名 | 说明 |
|-----------|------|
| `test_add_message_with_usage_accumulates` | add_message() 传入 UsageInfo 时累计 total_tokens 与 total_cost，并记录消息内容。 |
| `test_add_message_accumulates_multiple` | 多次 add_message() 的 token 与费用累计相加。 |
| `test_add_message_without_usage_does_not_change_stats` | 不传 usage 时统计值保持默认不变，消息内容仍被记录。 |
| `test_add_message_with_extra_fields_via_kwargs` | add_message() 的额外 kwargs（images、tags 等）写入消息字典。 |

#### 3.10.3 `TestToolResult`

> 类 docstring（中文直译）：验证 ToolResult 的字段。｜原文：Test ToolResult fields.

| 用例函数名 | 说明 |
|-----------|------|
| `test_required_fields` | 只传 tool_name 与 arguments 时，result/error/duration_ms 均为 None。 |
| `test_all_fields` | 传入全部字段后各字段值原样可读。 |
| `test_error_field` | error 字段可被直接设置（如网络超时信息）。 |

#### 3.10.4 `TestUsageStats`

> 类 docstring（中文直译）：验证 UsageStats 的默认值。｜原文：Test UsageStats default values.

| 用例函数名 | 说明 |
|-----------|------|
| `test_defaults` | 默认构造的 UsageStats 各计数字段为 0，by_provider 为空字典。 |
| `test_custom_values` | 传入自定义值时各字段按传入值保存。 |

#### 3.10.5 `TestImageResult`

> 类 docstring（中文直译）：验证 ImageResult 的字段初始化与默认值。｜原文：Test ImageResult field initialization and defaults.

| 用例函数名 | 说明 |
|-----------|------|
| `test_defaults` | 默认构造的 ImageResult：url/base64/revised_prompt 为 None，model/provider 为空字符串。 |
| `test_with_url_and_model` | 传入 url/model/provider/revised_prompt 后字段可读，base64 仍为 None。 |
| `test_with_base64` | 传入 base64 与 model/provider 后字段可读，url 为 None。 |

#### 3.10.6 `TestAudioResult`

> 类 docstring（中文直译）：验证 AudioResult 的字段初始化与默认值。｜原文：Test AudioResult field initialization and defaults.

| 用例函数名 | 说明 |
|-----------|------|
| `test_defaults` | 默认构造的 AudioResult：audio_data/url/duration_seconds 为 None，model/provider 为空字符串。 |
| `test_with_url_and_duration` | 传入 url/duration_seconds/model/provider 后字段可读，audio_data 仍为 None。 |

#### 3.10.7 `TestProviderInfo`

> 类 docstring：Test ProviderInfo field initialization（v2 字段集：实例 id/预设/适配器/健康状态）。

| 用例函数名 | 说明 |
|-----------|------|
| `test_required_fields` | 传入 v2 必填字段后各字段原样可读。 |
| `test_optional_defaults` | 未传 models 时默认值为空列表。 |
| `test_all_fields` | 传入 models 与不健康状态后各字段原样可读。 |

#### 3.10.8 `TestStreamChunk`

> 类 docstring（中文直译）：验证 StreamChunk 的字段默认值。｜原文：Test StreamChunk field defaults.

| 用例函数名 | 说明 |
|-----------|------|
| `test_defaults` | 默认构造的 StreamChunk：done=False、full_response 为空、tool_calls 为空列表、其余可选字段为 None。 |
| `test_all_fields` | 传入全部字段后各字段可读，usage 为传入的 UsageInfo。 |

---

### 3.11 `test_model_check.py`

> **被测模块 docstring**: check_provider / check_model 连通性探测测试（core/llm/llm_provider.py）
>
> 覆盖：chat / embed 两种探测路径、成功 / 异常 / 跳过三路径、 超时临时覆盖与恢复、模型缓存写入。

**测试用例数**: 8（测试类 2 个）

#### 3.11.1 `TestCheckModel`

> 类 docstring：单模型连通性探测

| 用例函数名 | 说明 |
|-----------|------|
| `test_chat_probe_success` | 聊天模型走 chat 最小请求探测：成功 + 延迟非负 + 探测参数契约 |
| `test_embedding_model_uses_embed_probe` | 声明嵌入能力的模型走 embed 探测（不走 chat） |
| `test_probe_failure_records_error` | 探测抛异常：ok=False + error 非空 + 延迟非负（异常路径） |
| `test_missing_instance_skipped` | 实例不存在：skipped=True + 中文原因 + 无延迟（边界路径） |
| `test_timeout_override_and_restore` | timeout 经临时覆盖生效，探测结束后恢复原值 |

#### 3.11.2 `TestCheckProvider`

> 类 docstring：实例级连通性检查

| 用例函数名 | 说明 |
|-----------|------|
| `test_success_returns_model_count_and_caches` | 成功：返回模型数、更新模型缓存、记录健康 |
| `test_refresh_failure_returns_error` | 拉取失败：返回错误信息并记录不健康（异常路径） |
| `test_missing_instance` | 实例不存在：返回 (False, 中文错误, 0)，不抛异常（边界路径） |

---

### 3.12 `test_model_schema.py`

> **被测模块 docstring**: 统一模型 schema 测试（core/llm/model_schema.py）
>
> 覆盖：历史双 schema 规范化、定价键迁移、能力闭集过滤、互斥规则、 分组推断、三路合并。

**测试用例数**: 13（测试类 5 个）

#### 3.12.1 `TestNormalizeLegacyBoolSchema`

> 类 docstring：模板式（support_* 布尔键）schema 转换

| 用例函数名 | 说明 |
|-----------|------|
| `test_bool_keys_mapped_to_capabilities` | 模板式布尔键转换为 capabilities（vision/function_calling/embedding） |
| `test_ui_schema_passthrough_and_defaults` | UI 式（capabilities 列表）透传并补全缺失键默认值 |
| `test_invalid_capabilities_filtered_and_unknown_keys_kept` | 非法 capabilities 值过滤、非列表按空处理；未知额外键保留 |

#### 3.12.2 `TestPriceKeyMigration`

> 类 docstring：历史 per_1k 定价键迁移

| 用例函数名 | 说明 |
|-----------|------|
| `test_per_1k_migrated_to_per_1m_times_1000` | per_1k 键迁移为 per_1m 键（×1000）并删除旧键 |
| `test_per_1m_wins_when_both_present` | per_1k 与 per_1m 并存时以 per_1m 为准并删除 per_1k |

#### 3.12.3 `TestCapabilityExclusion`

> 类 docstring：能力互斥规则

| 用例函数名 | 说明 |
|-----------|------|
| `test_mutually_exclusive_groups_constant` | 互斥规则常量：embedding 与 rerank 同属一个互斥组 |
| `test_embedding_selected_disables_all_others` | 选中 embedding 时除自身外全部能力禁用 |
| `test_chat_capability_selected_disables_nothing` | 选中非互斥能力（vision）时不禁用任何能力 |

#### 3.12.4 `TestGroupInference`

> 类 docstring：模型分组推断与聚合

| 用例函数名 | 说明 |
|-----------|------|
| `test_keyword_hit` | 关键字命中返回对应系列分组名 |
| `test_path_fallback_and_other` | 未命中关键字时取路径首段；无路径时归「其他」 |
| `test_models_to_groups_ungrouped` | 空组名条目归入「未分组」，其余按原组聚合 |

#### 3.12.5 `TestMergeModelEntries`

> 类 docstring：三路合并（目录预设 + API 拉取 + 用户覆写）

| 用例函数名 | 说明 |
|-----------|------|
| `test_merge_priority_and_order` | 同 id 后者覆盖（用户覆写优先），顺序为首次出现顺序 |
| `test_merge_normalizes_and_skips_missing_id` | 合并过程逐项规范化；缺少 id 的条目跳过 |

---

### 3.13 `test_plugin_interface.py`

> **被测模块 docstring**: ILLMService 接口契约测试（core/interfaces/i_llm_service.py + plugin_service.py）
>
> 重构核心保障：接口即契约（显式继承、签名一致）、消除底层泄漏、 ProviderInfo 字段来自真实配置、默认解析、配置变更定价热更新。

**测试用例数**: 12（测试类 5 个）

#### 3.13.1 `TestInterfaceContract`

> 类 docstring：接口即契约

| 用例函数名 | 说明 |
|-----------|------|
| `test_service_is_illm_service_instance` | LLMPluginService 显式继承 ILLMService（isinstance 成立） |
| `test_abstract_methods_signatures_match` | 全部抽象方法已实现且参数签名与接口一致（名称/默认值/种类比对） |
| `test_plugin_services_annotation_is_interface` | PluginServices.llm_facade 类型标注为 ILLMService 接口 |
| `test_leaky_methods_removed` | 底层泄漏方法已从插件面移除（get_raw_provider 等） |

#### 3.13.2 `TestProviderInfoFromRealConfig`

> 类 docstring：ProviderInfo 字段来自真实配置

| 用例函数名 | 说明 |
|-----------|------|
| `test_list_providers_fields` | list_providers：启用状态/适配器/预设关联/名称与配置一致，按 order 排序 |
| `test_provider_info_has_no_api_key` | ProviderInfo 不携带 api_key 等敏感字段 |

#### 3.13.3 `TestQueryApis`

> 类 docstring：实例与模型查询

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_models_by_instance_and_default` | get_models 按实例 id 工作；DEFAULT_PROVIDER 解析为默认实例 |
| `test_resolve_provider_id` | resolve_provider_id：非默认引用原样返回；默认引用解析为实例 id |
| `test_get_default_provider_id_none_when_empty` | 无可用实例时 get_default_provider_id 返回 None（不抛异常） |

#### 3.13.4 `TestPricingHotReload`

> 类 docstring：配置变更订阅驱动的定价热更新

| 用例函数名 | 说明 |
|-----------|------|
| `test_pricing_refreshed_on_config_change` | custom_models 定价修改后，定价表自动重建并热注入 ConversationManager |

#### 3.13.5 `TestImageUtils`

> 类 docstring：load_image_as_base64 新位置

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_image_as_base64` | utils.image_utils.load_image_as_base64 行为与原门面方法一致 |
| `test_load_image_missing_file_raises` | 文件不存在抛出 OSError（异常路径） |

---

### 3.14 `test_plugin_service.py`

> **被测模块 docstring（中文直译）**: test_plugin_service.py — LLMPluginService 单元测试。
>
> 原文：test_plugin_service.py — LLMPluginService 单元测试
>
> 测试 core/llm/plugin_service.py 中的 LLMPluginService 类。

**测试用例数**: 11（测试类 6 个）

#### 3.14.1 `TestSingleton`

> 类 docstring：测试单例模式

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_llm_plugin_service_returns_same_instance` | 多次调用 get_llm_plugin_service() 返回同一实例 |

#### 3.14.2 `TestChatDelegation`

> 类 docstring：测试 chat / stream_chat 委托

| 用例函数名 | 说明 |
|-----------|------|
| `test_chat_converts_dict_messages_to_message_objects` | chat() 将字典消息转换为 Message 对象后委托 |
| `test_stream_chat_converts_dict_messages` | stream_chat() 将字典消息转换为 Message 对象 |

#### 3.14.3 `TestToolExecutor`

> 类 docstring：测试工具执行器访问

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_tool_executor_returns_tool_executor_instance` | get_tool_executor() 返回 ToolCallExecutor 实例 |
| `test_get_shared_tool_registry_returns_registry` | get_shared_tool_registry() 返回共享的 ToolRegistry |

#### 3.14.4 `TestEmbed`

> 类 docstring：测试 embed 委托

| 用例函数名 | 说明 |
|-----------|------|
| `test_embed_delegates_to_llm_provider` | embed() 正确委托给底层 LLM |
| `test_embed_with_list_of_texts` | embed() 支持文本列表 |

#### 3.14.5 `TestConversationManagement`

> 类 docstring：测试对话管理委托

| 用例函数名 | 说明 |
|-----------|------|
| `test_create_conversation_delegates_to_conversation_manager` | create_conversation() 委托给 ConversationManager |
| `test_get_conversation_delegates` | get_conversation() 委托给 ConversationManager |
| `test_delete_conversation_delegates` | delete_conversation() 委托给 ConversationManager |

#### 3.14.6 `TestUsageStats`

> 类 docstring：测试用量统计

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_usage_stats_delegates_to_conversation_manager` | get_usage_stats() 委托给 ConversationManager |

---

### 3.15 `test_secure_keys.py`

> **被测模块 docstring（中文直译）**: core.llm.secure_keys 的 pytest 测试。
>
> 原文：pytest tests for core.llm.secure_keys.

**测试用例数**: 13（测试类 3 个）

#### 3.15.1 `TestEncodeSecret`

> 类 docstring（中文直译）：encode_secret() 的测试。｜原文：Tests for encode_secret().

| 用例函数名 | 说明 |
|-----------|------|
| `test_encode_plain_value` | 普通字符串应编码为 b64:<base64> 形式。 |
| `test_encode_unicode_value` | Unicode 字符串应正确编码。 |
| `test_encode_empty_string_returns_empty` | 空字符串应保持为空，不添加前缀。 |
| `test_encode_none_returns_none` | 传入 None 时按空值处理，返回 None。 |

#### 3.15.2 `TestDecodeSecret`

> 类 docstring（中文直译）：decode_secret() 的测试。｜原文：Tests for decode_secret().

| 用例函数名 | 说明 |
|-----------|------|
| `test_decode_b64_prefixed_value` | b64: 前缀的值应解码为明文。 |
| `test_decode_plain_value_backward_compatible` | 无前缀的旧明文配置应原样返回。 |
| `test_decode_empty_string` | 空字符串应原样返回。 |
| `test_decode_invalid_base64_returns_raw` | 非法 Base64 解码失败时按原文返回。 |
| `test_decode_none_returns_none` | 传入 None 时原样返回 None（startswith 短路）。 |

#### 3.15.3 `TestRoundTrip`

> 类 docstring（中文直译）：编码/解码往返的测试。｜原文：Tests for encode/decode round-trip.

| 用例函数名 | 说明 |
|-----------|------|
| `test_round_trip`（参数化 4 例） | 任意明文先编码再解码应等于原值。 |

---

### 3.16 `test_tool_call_executor.py`

> **被测模块 docstring（中文直译）**: core.llm.tool_call_executor 中 ToolRegistry 与 ToolCallExecutor 的 pytest 测试。
>
> 原文：pytest tests for core.llm.tool_call_executor.ToolRegistry and ToolCallExecutor.

**测试用例数**: 23（测试类 6 个）

#### 3.16.1 `TestToolRegistry`

> 代码分节注释（中文直译）：测试：ToolRegistry｜原文：Test: ToolRegistry

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_stores_tool` | register() 把工具存入 _tools 与 _handlers。 |
| `test_register_raises_on_duplicate_name` | 同名工具已存在时 register() 抛出 ValueError。 |
| `test_unregister_removes_from_both_dicts` | unregister() 同时从 _tools 与 _handlers 移除并返回 True。 |
| `test_unregister_returns_false_for_missing_name` | 工具不存在时 unregister() 返回 False。 |
| `test_get_tools_returns_list_of_tool_dicts` | get_tools() 返回工具定义 dict 组成的列表。 |
| `test_get_handler_returns_callable_or_none` | get_handler() 返回已注册的可调用对象，缺失时为 None。 |
| `test_list_tools_returns_names` | list_tools() 返回工具名称列表。 |

#### 3.16.2 `TestChatWithToolsNoTools`

> 代码分节注释（中文直译）：测试：ToolCallExecutor——无工具时委托｜原文：Test: ToolCallExecutor — no-tools delegation

| 用例函数名 | 说明 |
|-----------|------|
| `test_delegates_to_llm_chat_when_no_tools` | 未注册任何工具时，chat_with_tools() 委托给 _llm.chat()。 |
| `test_delegates_to_llm_stream_chat_when_no_tools_and_stream` | 未注册工具且 stream=True 时，委托给 _llm.stream_chat()。 |

#### 3.16.3 `TestChatWithToolsSingleTurn`

> 代码分节注释（中文直译）：测试：ToolCallExecutor——含工具调用的单轮｜原文：Test: ToolCallExecutor — single turn with tool call

| 用例函数名 | 说明 |
|-----------|------|
| `test_one_turn_llm_returns_tool_calls_executor_calls_handler` | 单轮流程：LLM 返回 tool_calls → 调用 handler → 第二次 LLM 调用 → 得到最终结果。 |
| `test_respects_max_turns_limit` | 达到 max_turns 上限时循环退出并返回。 |
| `test_handler_raises_tool_result_error_contains_exception` | handler 抛异常时，ToolResult.error 包含异常信息。 |
| `test_handler_not_found_result_starts_with_error` | handler 未找到时，ToolResult.result 以 'Error: tool' 开头。 |
| `test_arguments_as_json_string_parsed` | arguments 为 JSON 字符串时能被正确解析。 |
| `test_arguments_as_invalid_json_falls_back_to_empty_dict` | arguments 为非法 JSON 字符串时回退为 {}。 |
| `test_empty_tool_calls_exits_loop_immediately` | tool_calls 为空或 None 时循环立即退出并返回。 |
| `test_stream_accumulates_chunks_via_stream_callback` | stream=True 时通过 stream_callback 聚合响应分块。 |
| `test_no_content_but_tool_calls_still_processes_tools` | 响应没有 content 但有 tool_calls 时仍会处理工具调用。 |

#### 3.16.4 `TestChatWithToolsStream`

> 代码分节注释（中文直译）：测试：chat_with_tools_stream（类型化 callback 版本）｜原文：Test: chat_with_tools_stream (typed callback version)

| 用例函数名 | 说明 |
|-----------|------|
| `test_delegates_to_chat_with_tools_with_stream_true` | chat_with_tools_stream() 以 stream=True 调用 chat_with_tools()。 |

#### 3.16.5 `TestToolRegistryReplace`

> 代码分节注释（中文直译）：测试：ToolRegistry——replace 参数｜原文：Test: ToolRegistry — replace parameter

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_replace_false_raises_on_duplicate` | replace=False 时重复注册同名工具抛出 ValueError。 |
| `test_register_replace_true_overwrites_handler` | replace=True 时覆盖旧处理函数。 |

#### 3.16.6 `TestToolCallExecutorEdgeCases`

> 代码分节注释（中文直译）：测试：ToolCallExecutor——非法参数与并行工具调用｜原文：Test: ToolCallExecutor — invalid arguments & parallel tool calls

| 用例函数名 | 说明 |
|-----------|------|
| `test_invalid_arguments_produces_error_tool_result` | 参数 JSON 非法时，ToolResult 携带错误信息。 |
| `test_parallel_tool_calls_produce_single_assistant_message` | 多个 tool_calls 合并为一条 assistant 消息后紧跟多条 tool 消息。 |

---

### 3.17 `test_tool_calling.py`

> **被测模块 docstring**: 工具调用类型化测试（core/llm/tool_call_executor.py + types.py）
>
> 覆盖：ToolRegistry 双注册路径、ToolChatResult 结构化返回（stream 与否 字段类型固定）、多轮循环至 max_turns 终止、handler 异常、StreamChunk 实填、ToolCall 解析。

**测试用例数**: 11（测试类 5 个）
**非测试辅助类**（不含测试函数，不计入测试类）: `StubLLM`

#### 3.17.1 `TestToolRegistry`

> 类 docstring：工具注册表

| 用例函数名 | 说明 |
|-----------|------|
| `test_register_and_lookup` | register 原签名：注册后可查定义与 handler |
| `test_register_typed_equivalent` | register_typed(ToolDefinition) 与 register 等效 |
| `test_unregister` | 注销后查询返回 None（边界） |

#### 3.17.2 `TestChatWithoutTools`

> 类 docstring：未注册工具时退化为普通对话

| 用例函数名 | 说明 |
|-----------|------|
| `test_no_tools_degrades` | 无工具注册：直接一轮对话，tool_results 为空 |

#### 3.17.3 `TestToolCallLoop`

> 类 docstring：多轮工具调用循环

| 用例函数名 | 说明 |
|-----------|------|
| `test_single_tool_turn` | 一轮工具调用：handler 执行 + 消息序列 + 最终文本 |
| `test_loop_terminates_at_max_turns` | 模型持续要求调用：循环至 max_turns 终止并追加说明消息 |
| `test_handler_error_recorded_and_loop_continues` | handler 抛异常：记录 error 并把错误回传模型，循环继续 |

#### 3.17.4 `TestStreamToolCalling`

> 类 docstring：流式工具调用（ToolChatResult 字段类型固定）

| 用例函数名 | 说明 |
|-----------|------|
| `test_stream_result_shape` | 流式路径：tool_calls 从聚合响应提取，结果结构与非流式一致 |
| `test_service_stream_callback_receives_stream_chunk` | chat_with_tools_stream：callback 收到字段实填的 StreamChunk |

#### 3.17.5 `TestToolCallParsing`

> 类 docstring：ToolCall 解析

| 用例函数名 | 说明 |
|-----------|------|
| `test_from_openai_format` | 标准 OpenAI 格式解析（arguments 为 JSON 字符串） |
| `test_from_flat_format_and_invalid_json` | 扁平格式解析；非法 JSON 回退空参数并保留原文（异常路径） |

---

### 3.18 `test_usage_record_store.py`

> **被测模块 docstring**: UsageRecordStore 单元测试
>
> 覆盖用量记录的保存、查询、聚合、裁剪及异步持久化行为。

**测试用例数**: 14（测试类 7 个）
**说明粒度**：本文件测试函数与测试类均无 docstring，「说明」列按**函数名 + 所属测试类**归纳，粒度较粗，仅用于定位用例意图。

#### 3.18.1 `TestSingleton`

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_usage_record_store_returns_same_instance` | 多次调用 get_usage_record_store() 返回同一实例。 |

#### 3.18.2 `TestRecord`

| 用例函数名 | 说明 |
|-----------|------|
| `test_record_appends_to_cache` | record() 把记录追加进内存缓存。 |
| `test_record_generates_id_when_missing` | 记录 id 为空时 record() 自动生成 id。 |
| `test_record_persists_to_disk` | record() 异步落盘，文件中的记录与缓存一致。 |

#### 3.18.3 `TestGetRecords`

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_records_without_filters` | 不带过滤条件时返回全部记录。 |
| `test_get_records_filters_by_provider` | 按 provider 过滤记录。 |
| `test_get_records_filters_by_conversation_id` | 按 conversation_id 过滤记录。 |
| `test_get_records_filters_by_time_range` | 按起始时间（start_time）过滤记录。 |
| `test_get_records_pagination` | 按 limit/offset 分页返回记录。 |

#### 3.18.4 `TestAggregate`

| 用例函数名 | 说明 |
|-----------|------|
| `test_aggregate_by_provider` | 按 provider 聚合并分组统计请求数与 token 数。 |
| `test_aggregate_by_day` | 按天聚合，不同日期分为两组。 |

#### 3.18.5 `TestTotalStats`

| 用例函数名 | 说明 |
|-----------|------|
| `test_get_total_stats` | 汇总统计：请求数、输入/输出/总 token 与平均耗时。 |

#### 3.18.6 `TestPrune`

| 用例函数名 | 说明 |
|-----------|------|
| `test_prune_removes_old_records` | prune() 删除早于指定时间的记录并返回删除条数。 |

#### 3.18.7 `TestCorruptionFallback`

| 用例函数名 | 说明 |
|-----------|------|
| `test_load_from_disk_returns_default_on_corrupted_json` | 记录文件为非法 JSON 时 _load_from_disk() 回退为空结构。 |

---

## 4. 维护指南

### 4.1 添加新测试

当 `core/llm/` 添加新功能时：
1. 在对应的测试文件中找到测试类
2. 添加新测试函数，遵循命名规范
3. 在测试函数 docstring 首句写明测试目的（本文档 §3 的「说明」列即取自该句的中文原文或中文直译）
4. 使用 `_make_provider()` 或 `_make_mock_llm()` 辅助函数

### 4.2 修复失败的测试

1. 查看测试的 docstring 了解测试目的
2. 检查被测代码是否有 bug
3. 如果是 mock 相关问题，检查辅助函数是否正确

### 4.3 覆盖率目标

- 当前覆盖率: **未实测**（本环境未安装 `pytest-cov`，`pytest --cov` 不可用；本文档不保留历史估算值）
- 目标覆盖率: 85%
- 未覆盖的关键路径:
  - 真实 API 调用（需要网络）
  - 复杂错误恢复场景
- 测量命令（安装 `pytest-cov` 后）：
  `.venv\Scripts\python.exe -m pytest test/core/llm --cov=core.llm --cov-report=term-missing`

---

## 5. 相关文档

- [LLM Provider API 参考](../../docs/core/llm-provider/api-reference.md)
- [LLM Provider 概述](../../docs/core/llm-provider/overview.md)
- [测试主文档](../TESTING.md)

---
