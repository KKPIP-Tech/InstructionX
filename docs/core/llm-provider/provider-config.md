# LLM Provider 配置

> ProviderConfig 和 LLMConfig 配置管理类（配置 schema v2）

---

## 1. 概述

LLM Provider 的配置管理由两个核心类负责：`ProviderConfig` 管理单个提供商**实例**的配置，`LLMConfig`（单例）管理所有实例的配置集合并提供变更订阅。

**文件位置**: `core/llm/config.py`

**核心概念**：

- **预设与实例分离**：配置中的每个 Provider 是一个**实例**，通过 `preset_id` 关联 `core/llm/catalog/` 中的预设目录（`preset_id=None` 表示完全自定义，固定使用 `openai-compatible` 兜底适配器）。
- **目录即默认值**：首次运行不再自动写入内置提供商模板，配置文件只存用户显式创建/修改的实例；删除的实例不会在下次启动时复活。
- **schema v2**：配置文件顶层含 `version: 2`；无 `version` 键的历史文件按 v1 处理，加载时自动迁移（先备份再写回）。

---

## 2. ProviderConfig

### 2.1 类定义

```python
from core.llm.config import ProviderConfig

config = ProviderConfig(
    name="我的自定义服务",
    preset_id=None,                    # None = 完全自定义
    adapter="openai-compatible",       # 适配器家族键
    api_key="sk-...",
    base_url="https://api.example.com/v1",
    chat_model="my-model",
    embedding_model="",
    enabled_chat=True,
    enabled_embedding=False,
    support_vision=False,
    order=0,
    timeout=60          # 其他未列出的字段会存入 extra
)
```

### 2.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | 实例显示名称（可改名的显示名） |
| `preset_id` | `Optional[str]` | 否 | 关联的预设目录 ID（如 `"glm"`）；`None` = 完全自定义 |
| `adapter` | `str` | 是 | 适配器家族键（对应 `PROVIDER_REGISTRY` 的键，如 `"glm"`、`"openai-compatible"`） |
| `api_key` | `str` | 建议配置 | API 密钥（内存中始终为明文；Ollama 等可留空） |
| `base_url` | `str` | 建议配置 | API 端点基础 URL（空串表示使用目录默认地址） |
| `chat_model` | `str` | 建议配置 | 默认聊天模型名称 |
| `embedding_model` | `str` | 建议配置 | 默认嵌入模型名称 |
| `enabled_chat` | `bool` | 建议配置 | 是否启用 Chat 功能（默认 True） |
| `enabled_embedding` | `bool` | 建议配置 | 是否启用 Embedding 功能（默认 False） |
| `support_vision` | `bool` | 否 | 是否支持 Vision（默认 True） |
| `order` | `int` | 否 | 列表排序权重（默认 0，UI 排序持久化） |
| `cache_fields` | `dict` | 否 | 缓存字段配置（用于 OpenAI 兼容接口的缓存偏好设置） |
| `extra` | `dict` | 否 | 其他扩展配置（通过 `**kwargs` 吸收未定义字段，如 `timeout`、`custom_models` 等） |

> **说明**：v1 的 `provider_type` 字段已废弃，迁移时映射为 `preset_id` 与 `adapter`；`from_dict` 会静默丢弃残留的 `provider_type` 键。

### 2.3 方法

#### to_dict()

```python
def to_dict(self) -> dict
```

将配置转换为字典（输出 v2 字段集：`preset_id` / `adapter` / `order` 等）。

#### from_dict()

```python
@classmethod
def from_dict(cls, data: dict) -> "ProviderConfig"
```

从字典创建 ProviderConfig 实例。`custom_models` 列表逐项经 `normalize_model_entry()` 规范化为统一模型 schema（历史布尔能力键转 capabilities、per_1k → per_1m 定价迁移）；未知字段存入 `extra`。

---

## 3. LLMConfig（单例）

### 3.1 类定义

```python
from core.llm.config import get_llm_config

config = get_llm_config()  # LLMConfig 单例，加载 config/llm_providers.json
```

`LLMConfig` 是**单例**（双重检查锁），全进程共享同一份内存配置。构造函数加载 `config/llm_providers.json`：

- 文件不存在时创建**空 providers 的 v2 文件**（不再自动补齐内置提供商模板）；
- 顶层无 `version` 键的历史文件按 v1 处理，**先备份再迁移**为 v2（见 §5）。

### 3.2 单例与变更订阅

```python
config = get_llm_config()

# 变更订阅：实例增删 / save_config 后触发回调
def on_changed(event: str, provider_name: str | None):
    print(event, provider_name)  # event 为 EVENT_PROVIDERS_CHANGED

config.subscribe(on_changed)
config.unsubscribe(on_changed)

# 变更计数：每次变更（add/remove/save）递增 1，供消费方（如 LLMProvider）惰性刷新比对
print(config.version)
```

- 订阅回调签名为 `callback(event: str, provider_name: Optional[str])`；`event` 取值为 `EVENT_PROVIDERS_CHANGED`（`"providers_changed"`），`provider_name` 为变更涉及的实例 id（批量保存时为 `None`）。
- 回调中的异常被捕获并记 WARNING 日志，不影响主流程与其余回调。

### 3.3 方法

#### get_provider()

```python
def get_provider(self, name: str) -> Optional[ProviderConfig]
```

根据实例 id 获取配置。

#### add_provider()

```python
def add_provider(self, name: str, config: ProviderConfig) -> None
```

添加或更新实例配置（无返回值）。写入内存后**立即落盘**，并随保存触发变更通知。

#### remove_provider()

```python
def remove_provider(self, name: str) -> bool
```

移除实例配置并立即落盘（目录即默认值，移除的实例不会在下次加载时复活）。

#### get_enabled_providers()

```python
def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ProviderConfig]
```

根据功能类型筛选已启用的实例。

**参数**:
- `feature`: 功能类型，`"chat"` 或 `"embedding"`

#### get_all_providers()

```python
def get_all_providers(self) -> Dict[str, ProviderConfig]
```

获取所有实例配置（实例 id → ProviderConfig 的映射副本）。

#### config_file_path

```python
@property
def config_file_path(self) -> Path
```

获取配置文件路径（`config/llm_providers.json`）。

#### save_config()

```python
def save_config(self) -> None
```

将全部实例配置序列化为 v2 schema 并原子写入 `config/llm_providers.json`（api_key 落盘前做 Base64 编码，仅为编码非加密），随后触发变更通知（`version + 1`）。

---

## 4. 模型缓存

`LLMConfig` 还管理模型缓存文件 `config/llm_models_cache.json`，存储各实例的可用模型列表（**缓存键为实例 id**）。

#### save_models_cache()

```python
def save_models_cache(self, provider_name: str, models: List[Dict[str, Any]]) -> None
```

保存指定实例的模型列表到缓存文件。

#### load_models_cache()

```python
def load_models_cache(self, provider_name: str) -> Optional[List[Dict[str, Any]]]
```

从缓存加载指定实例的模型列表；读取端兼容 TTL 信封 `{"timestamp", "models"}` 与纯 list 旧格式，原样返回由调用方解释。不存在时返回 `None`。

---

## 5. 配置 schema v2 与 v1 → v2 迁移

### 5.1 schema v2 结构

`config/llm_providers.json`：

```jsonc
{
    "version": 2,
    "providers": {
        "<instance_id>": {              // 实例唯一键（预设默认实例 = preset_id；新建实例 = 短码 id）
            "preset_id": "siliconflow", // null = 完全自定义
            "name": "SiliconFlow",      // 可改名的显示名
            "adapter": "siliconflow",   // 适配器家族键（冗余落盘，目录变更不影响实例）
            "api_key": "b64:...",       // Base64 编码（仅为编码非加密）
            "base_url": "",             // 空串 = 使用目录默认地址
            "chat_model": "",
            "embedding_model": "",
            "enabled_chat": true,
            "enabled_embedding": false,
            "support_vision": true,
            "order": 0,                 // 排序权重
            "custom_models": [],        // 统一模型 schema（经 normalize_model_entry 规范化）
            "cache_fields": {}
        }
    }
}
```

### 5.2 v1 → v2 自动迁移

加载时检测到顶层无 `version` 键即按 v1 处理，自动迁移：

1. **备份**：原文件复制为 `config/llm_providers.migrated-<UTC时间戳>.bak`（命名风格与 data 层迁移备份一致）；
2. **条目映射**：`provider_type` → `preset_id`（同名映射，无 `provider_type` 时为 `None`）；`adapter = provider_type`；`order` 按原顺序分配 `0..n`；实例 id 保持旧键名不变（向后兼容）；
3. **模型规范化**：`custom_models` 逐项经 `normalize_model_entry()` 规范化（历史 `support_*` 布尔键转 `capabilities`，`input_price_per_1k` / `output_price_per_1k` 迁移为 per_1m 键 ×1000）；
4. **原子写回**：迁移结果以 v2 schema 原子写回原文件并加载。

> **说明**：模型缓存文件 `llm_models_cache.json` 中历史 `per_1k` 键的值实际已是 per_1m 语义，由 `ModelInfo.from_dict` 原样读取，不做数值换算（与配置迁移路径语义不同）。

---

## 6. 异常类

`core/llm/exceptions.py` 中定义了以下异常类：

| 异常类 | 说明 |
|--------|------|
| `LLMException` | 所有 LLM 相关异常的基类 |
| `ConfigurationError` | 配置错误（配置文件格式错误、缺少必需配置项） |
| `AuthenticationError` | 认证错误（API 密钥无效或已过期） |
| `APIError` | API 调用错误（含 `status_code` 和 `provider` 属性） |
| `RateLimitError` | 速率限制异常（继承自 `APIError`） |
| `InvalidRequestError` | 无效请求异常（参数不合法、超出 token 限制等） |
| `ModelNotSupportedError` | 模型不支持异常 |
| `ConnectionError` | 连接错误异常 |
| `TimeoutError` | 超时异常 |
| `StreamingError` | 流式输出错误异常 |

---

## 7. 使用示例

### 添加自定义 Provider 实例

```python
from core.llm.config import ProviderConfig, get_llm_config

config = get_llm_config()

new_provider = ProviderConfig(
    name="My Custom LLM",
    preset_id=None,                    # 完全自定义
    adapter="openai-compatible",       # 兜底适配器
    api_key="sk-my-key",
    base_url="https://api.my-llm.com/v1",
    chat_model="my-model",
    enabled_chat=True,
    enabled_embedding=False,
)

config.add_provider("custom-a1b2c3d4", new_provider)  # 写入内存并立即落盘
```

---

## 8. 相关文档

- [LLM Provider 概述](overview.md)
- [LLM Provider API 参考](api-reference.md)

---

*本文档由 Claude Code 自动生成*
