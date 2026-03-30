# LLM Provider 配置

> ProviderConfig 和 LLMConfig 配置管理类

---

## 1. 概述

LLM Provider 的配置管理由两个核心类负责：`ProviderConfig` 管理单个 Provider 的配置，`LLMConfig` 管理所有 Provider 的配置集合。

**文件位置**: `core/llm/config.py`

---

## 2. ProviderConfig

### 2.1 类定义

```python
from core.llm.config import ProviderConfig

config = ProviderConfig(
    name="My Provider",
    provider_type="custom",
    api_key="sk-...",
    base_url="https://api.example.com/v1",
    chat_model="gpt-4",
    embedding_model="text-embedding-3-small",
    enabled_chat=True,
    enabled_embedding=True,
    support_vision=False,
    extra={}
)
```

### 2.2 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | Provider 显示名称 |
| `provider_type` | `str` | 是 | Provider 类型标识（如 `"minimax"`, `"glm"`） |
| `api_key` | `str` | 建议配置 | API 密钥（Ollama 可留空） |
| `base_url` | `str` | 建议配置 | API 端点基础 URL |
| `chat_model` | `str` | 建议配置 | 默认聊天模型名称 |
| `embedding_model` | `str` | 建议配置 | 默认嵌入模型名称 |
| `enabled_chat` | `bool` | 建议配置 | 是否启用 Chat 功能 |
| `enabled_embedding` | `bool` | 建议配置 | 是否启用 Embedding 功能 |
| `support_vision` | `bool` | 否 | 是否支持 Vision（默认 False） |
| `extra` | `dict` | 否 | 其他扩展配置 |

### 2.3 方法

#### to_dict()

```python
def to_dict(self) -> dict
```

将配置转换为字典格式。

#### from_dict()

```python
@classmethod
def from_dict(cls, data: dict) -> "ProviderConfig"
```

从字典创建 ProviderConfig 实例。

---

## 3. LLMConfig

### 3.1 类定义

```python
from core.llm.config import LLMConfig

config = LLMConfig()  # 加载 config/llm_providers.json
```

构造函数加载 `config/llm_providers.json` 配置文件。如果文件不存在，自动创建包含 MiniMax、SiliconFlow、GLM、Ollama 四个默认 Provider 的配置。

### 3.2 方法

#### get_provider()

```python
def get_provider(self, name: str) -> Optional[ProviderConfig]
```

根据名称获取 Provider 配置。

#### add_provider()

```python
def add_provider(self, name: str, provider_config: ProviderConfig)
```

添加或更新 Provider 配置。

#### remove_provider()

```python
def remove_provider(self, name: str) -> bool
```

移除 Provider 配置。

#### get_all_providers()

```python
def get_all_providers(self) -> Dict[str, ProviderConfig]
```

获取所有 Provider 配置。

#### save()

```python
def save(self) -> bool
```

保存配置到 `config/llm_providers.json`。

#### reload()

```python
def reload(self)
```

重新从文件加载配置。

---

## 4. 模型缓存

`LLMConfig` 还管理模型缓存文件 `config/llm_models_cache.json`，存储各 Provider 的可用模型列表。

```python
config = LLMConfig()
config.save()  # 保存 Provider 配置到 llm_providers.json
```

---

## 5. 使用示例

### 添加自定义 Provider

```python
from core.llm.config import LLMConfig, ProviderConfig

config = LLMConfig()

new_provider = ProviderConfig(
    name="My Custom LLM",
    provider_type="custom",
    api_key="sk-my-key",
    base_url="https://api.my-llm.com/v1",
    chat_model="my-model",
    embedding_model="my-embedding",
    enabled_chat=True,
    enabled_embedding=False,
    support_vision=True
)

config.add_provider("custom", new_provider)
config.save()
```

---

## 6. 相关文档

- [LLM Provider 概述](overview.md)
- [LLM Provider API 参考](api-reference.md)

---

*本文档由 Claude Code 自动生成*
