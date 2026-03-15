# LLM Provider API 参考

> LLM Provider 的完整 API 列表和详细说明

---

## 1. 类定义

### 1.1 LLMProvider (单例)

```python
from core.llm import get_llm_provider

# 获取单例实例
provider = get_llm_provider()
```

### 1.2 异常类

```python
from core.llm.exceptions import (
    LLMException,
    ConfigurationError,
    AuthenticationError,
    APIError,
    RateLimitError,
    TimeoutError,
    ConnectionError,
    InvalidRequestError
)
```

---

## 2. 数据类型

### 2.1 Message

```python
from core.llm.provider_interface import Message

# 创建消息
msg = Message(
    role="user",           # "user", "assistant", "system"
    content="你好",
    images=None,          # 可选，图片 base64 列表（用于 Vision）
    **extra               # 其他额外参数
)

# 转换为字典
msg.to_dict()
```

### 2.2 ChatResponse

```python
from core.llm.provider_interface import ChatResponse

# 属性
response.content           # str: 响应内容
response.model             # str: 使用的模型
response.role              # str: 响应角色
response.reasoning_content # str: 推理内容（如有）
response.tool_calls        # List[Dict]: 函数调用列表
response.extra             # Dict: 额外信息
```

### 2.3 EmbeddingResponse

```python
from core.llm.provider_interface import EmbeddingResponse

# 属性
response.embedding  # List[float]: 嵌入向量
response.model      # str: 使用的模型
response.extra      # Dict: 额外信息
```

### 2.4 ModelInfo

```python
from core.llm.provider_interface import ModelInfo

# 属性
model.id                 # str: 模型 ID
model.name               # str: 模型名称
model.support_chat       # bool: 是否支持 Chat
model.support_streaming  # bool: 是否支持流式
model.support_embedding  # bool: 是否支持 Embedding
model.support_vision     # bool: 是否支持 Vision
model.extra              # Dict: 额外信息

# 方法
model.to_dict()          # 转换为字典
ModelInfo.from_dict(d)   # 从字典创建
```

---

## 3. LLMProvider 方法

### 3.1 Provider 管理

#### get_provider()

```python
def get_provider(self, name: str) -> Optional[ILLM]
```

获取指定 Provider 实例。

**参数**:
- `name`: Provider 名称（如 "minimax", "siliconflow"）

**返回**:
- Provider 实例，不存在则返回 `None`

**示例**:
```python
provider = get_llm_provider()
minimax = provider.get_provider("minimax")
```

---

#### get_all_providers()

```python
def get_all_providers(self) -> Dict[str, ILLM]
```

获取所有已初始化的 Provider。

**返回**:
- Provider 字典 `{name: provider_instance}`

**示例**:
```python
all_providers = provider.get_all_providers()
for name, p in all_providers.items():
    print(f"{name}: {p.provider_name}")
```

---

#### get_enabled_providers()

```python
def get_enabled_providers(self, feature: str = "chat") -> Dict[str, ILLM]
```

获取已启用的 Provider。

**参数**:
- `feature`: 功能类型 ("chat" 或 "embedding")

**返回**:
- 启用的 Provider 字典

**示例**:
```python
# 获取支持 Chat 的 Provider
chat_providers = provider.get_enabled_providers("chat")

# 获取支持 Embedding 的 Provider
embedding_providers = provider.get_enabled_providers("embedding")
```

---

#### add_provider()

```python
def add_provider(self, name: str, config: ProviderConfig) -> None
```

添加或更新 Provider。

**参数**:
- `name`: Provider 名称
- `config`: Provider 配置

**示例**:
```python
from core.llm.config import ProviderConfig

config = ProviderConfig(
    provider_type="custom",
    api_key="your-key",
    base_url="https://api.example.com",
    chat_model="gpt-4",
    enabled=True,
    features=["chat"]
)
provider.add_provider("custom", config)
```

---

#### remove_provider()

```python
def remove_provider(self, name: str) -> bool
```

移除 Provider。

**参数**:
- `name`: Provider 名称

**返回**:
- 是否成功移除

**示例**:
```python
provider.remove_provider("custom")
```

---

#### reload_config()

```python
def reload_config(self) -> None
```

重新加载配置，关闭所有现有连接并重新初始化。

**示例**:
```python
provider.reload_config()
```

---

### 3.2 同步 Chat API

#### chat()

```python
def chat(
    self,
    messages: List[Union[Message, Dict]],
    provider: str = "default",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict]] = None,
    **kwargs
) -> ChatResponse
```

发送聊天请求（同步）。

**参数**:
- `messages`: 消息列表
- `provider`: Provider 名称（"default" 使用第一个启用的 Provider）
- `model`: 模型名称（可选）
- `temperature`: 温度参数（0.0-2.0）
- `max_tokens`: 最大 token 数（可选）
- `tools`: Function Calling 工具定义列表（可选）
- `**kwargs`: 其他参数

**返回**:
- `ChatResponse`: 聊天响应（包含 `tool_calls` 属性）

**示例**:
```python
# 基础使用
response = provider.chat(
    messages=[
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "你好"}
    ],
    provider="minimax",
    temperature=0.7
)
print(response.content)

# 使用 Function Calling
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"]
            }
        }
    }
]
response = provider.chat(
    messages=[{"role": "user", "content": "北京天气如何？"}],
    provider="minimax",
    tools=tools
)
if response.tool_calls:
    print(f"调用工具: {response.tool_calls}")
```

---

#### stream_chat()

```python
def stream_chat(
    self,
    messages: List[Union[Message, Dict]],
    provider: str = "default",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    callback: Optional[Callable[[ChatResponse], None]] = None,
    **kwargs
)
```

发送流式聊天请求（同步）。

**参数**:
- `messages`: 消息列表
- `provider`: Provider 名称
- `model`: 模型名称
- `temperature`: 温度参数
- `max_tokens`: 最大 token 数
- `callback`: 流式回调函数，接收每个 `ChatResponse`
- `**kwargs`: 其他参数

**返回**:
- `List[ChatResponse]`: 响应列表

**示例**:
```python
def on_chunk(response):
    print(response.content, end="", flush=True)

responses = provider.stream_chat(
    messages=[{"role": "user", "content": "讲个故事"}],
    provider="minimax",
    callback=on_chunk
)
```

---

### 3.3 同步 Embedding API

#### embed()

```python
def embed(
    self,
    texts: Union[str, List[str]],
    provider: str = "default",
    model: Optional[str] = None,
    **kwargs
) -> List[EmbeddingResponse]
```

发送嵌入请求（同步）。

**参数**:
- `texts`: 文本或文本列表
- `provider`: Provider 名称
- `model`: 模型名称
- `**kwargs`: 其他参数

**返回**:
- `List[EmbeddingResponse]`: 嵌入响应列表

**示例**:
```python
# 单文本
response = provider.embed(
    text="你好世界",
    provider="minimax"
)
embedding = response[0].embedding

# 多文本
responses = provider.embed(
    texts=["你好", "世界"],
    provider="minimax"
)
embeddings = [r.embedding for r in responses]
```

---

### 3.4 异步 Chat API

#### async_chat()

```python
async def async_chat(
    self,
    messages: List[Union[Message, Dict]],
    provider: str = "default",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs
) -> ChatResponse
```

发送聊天请求（异步）。

**参数**: 同 `chat()`

**返回**:
- `ChatResponse`: 聊天响应

**示例**:
```python
import asyncio

async def main():
    response = await provider.async_chat(
        messages=[{"role": "user", "content": "你好"}],
        provider="minimax"
    )
    print(response.content)

asyncio.run(main())
```

---

#### async_stream_chat()

```python
async def async_stream_chat(
    self,
    messages: List[Union[Message, Dict]],
    provider: str = "default",
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    **kwargs
) -> Any
```

发送流式聊天请求（异步）。

**参数**: 同 `stream_chat()`

**返回**:
- 异步迭代器 `AsyncIterator[ChatResponse]`

**示例**:
```python
import asyncio

async def main():
    async for response in provider.async_stream_chat(
        messages=[{"role": "user", "content": "你好"}],
        provider="minimax"
    ):
        print(response.content, end="", flush=True)

asyncio.run(main())
```

---

### 3.5 异步 Embedding API

#### async_embed()

```python
async def async_embed(
    self,
    texts: Union[str, List[str]],
    provider: str = "default",
    model: Optional[str] = None,
    **kwargs
) -> List[EmbeddingResponse]
```

发送嵌入请求（异步）。

**参数**: 同 `embed()`

**返回**:
- `List[EmbeddingResponse]`: 嵌入响应列表

**示例**:
```python
import asyncio

async def main():
    responses = await provider.async_embed(
        texts=["你好", "世界"],
        provider="minimax"
    )
    embeddings = [r.embedding for r in responses]

asyncio.run(main())
```

---

### 3.6 模型管理

#### get_models()

```python
def get_models(self, provider: Optional[str] = None) -> Dict[str, List[ModelInfo]]
```

获取可用模型列表。

**参数**:
- `provider`: Provider 名称（`None` 表示所有 Provider）

**返回**:
- `Dict[str, List[ModelInfo]]`: 每个 Provider 的模型列表

**示例**:
```python
# 获取所有模型
all_models = provider.get_models()
for name, models in all_models.items():
    print(f"{name}: {len(models)} 个模型")

# 获取指定 Provider 的模型
minimax_models = provider.get_models("minimax")
```

---

### 3.7 配置属性

#### config

```python
@property
def config(self) -> LLMConfig
```

获取配置管理器。

**示例**:
```python
config = provider.config
providers = config.get_all_providers()
```

---

#### available_providers

```python
@property
def available_providers(self) -> List[str]
```

获取可用 Provider 类型列表。

**示例**:
```python
print(provider.available_providers)
# ['minimax', 'siliconflow', 'glm', 'ollama']
```

---

#### close()

```python
def close(self) -> None
```

关闭所有 Provider 连接。

**示例**:
```python
provider.close()
```

---

## 4. Provider 实例方法

每个 Provider 实例（如 MiniMaxProvider）都有以下方法：

### 4.1 Chat

```python
# 同步
response = provider.chat(
    messages=[...],
    model="MiniMax-M2.1",
    temperature=0.7,
    max_tokens=1000
)

# 流式
responses = provider.stream_chat(
    messages=[...],
    callback=lambda r: print(r.content)
)

# 异步
response = await provider.async_chat(messages=[...])

# 异步流式
async for response in provider.async_stream_chat(messages=[...]):
    print(response.content)
```

### 4.2 Embedding

```python
# 同步
responses = provider.embed(texts=["hello", "world"])

# 异步
responses = await provider.async_embed(texts=["hello", "world"])
```

### 4.3 Models

```python
# 获取模型列表
models = provider.get_models()

# 异步
models = await provider.async_get_models()
```

### 4.4 配置验证

```python
# 验证配置是否有效
is_valid = provider.validate_config()
```

---

## 5. 完整示例

### 5.1 基础使用

```python
from core.llm import get_llm_provider
from core.llm.provider_interface import Message

# 获取 Provider
provider = get_llm_provider()

# 发送聊天
response = provider.chat(
    messages=[
        Message(role="user", content="你好"),
    ],
    provider="minimax",
    temperature=0.7
)

print(f"Model: {response.model}")
print(f"Response: {response.content}")
```

### 5.2 使用 Vision

```python
import base64

# 读取图片并转为 base64
with open("image.png", "rb") as f:
    img_base64 = base64.b64encode(f.read()).decode()

# 发送多模态消息
response = provider.chat(
    messages=[
        {
            "role": "user",
            "content": "描述这张图片",
            "images": [img_base64]
        }
    ],
    provider="minimax"
)

print(response.content)
```

### 5.3 并发调用

```python
import asyncio
from core.llm import get_llm_provider

provider = get_llm_provider()

async def concurrent_chat():
    # 并发调用多个 Provider
    results = await asyncio.gather(
        provider.async_chat(
            messages=[{"role": "user", "content": "你好"}],
            provider="minimax"
        ),
        provider.async_chat(
            messages=[{"role": "user", "content": "Hello"}],
            provider="siliconflow"
        ),
        provider.async_chat(
            messages=[{"role": "user", "content": "你好"}],
            provider="glm"
        ),
        return_exceptions=True  # 允许异常
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Provider {i} error: {result}")
        else:
            print(f"Provider {i}: {result.content}")

asyncio.run(concurrent_chat())
```

### 5.4 Embedding 相似度计算

```python
import numpy as np
from core.llm import get_llm_provider

provider = get_llm_provider()

# 获取两个文本的嵌入
responses = provider.embed(
    texts=["你好世界", "你好"],
    provider="minimax"
)

# 计算余弦相似度
vec1 = np.array(responses[0].embedding)
vec2 = np.array(responses[1].embedding)

similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
print(f"相似度: {similarity:.4f}")
```

### 5.5 Function Calling

```python
from core.llm import get_llm_provider

provider = get_llm_provider()

# 定义工具
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "获取指定城市的天气信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名称"}
                },
                "required": ["city"]
            }
        }
    }
]

# 模拟天气查询函数
def get_weather(city: str) -> str:
    return f"{city} 今天天气晴朗，25°C"

# 第一次调用：模型决定调用工具
response = provider.chat(
    messages=[{"role": "user", "content": "北京今天天气怎么样？"}],
    provider="minimax",
    tools=tools
)

print(f"模型回复: {response.content}")

# 检查是否有工具调用
if response.tool_calls:
    tool_call = response.tool_calls[0]
    func_name = tool_call['function']['name']
    func_args = tool_call['function']['arguments']

    print(f"调用工具: {func_name}")
    print(f"参数: {func_args}")

    # 执行工具函数
    result = get_weather(func_args.get('city', ''))

    # 将工具结果添加到对话
    messages = [
        {"role": "user", "content": "北京今天天气怎么样？"},
        {"role": "assistant", "content": response.content},
        {
            "role": "tool",
            "tool_call_id": tool_call.get('id', ''),
            "content": result
        }
    ]

    # 第二次调用：模型根据工具结果生成最终回复
    final_response = provider.chat(messages=messages, provider="minimax")
    print(f"最终回复: {final_response.content}")
```

---

## 6. 相关文档

- [LLM Provider 概述](overview.md)
- [插件开发指南](../plugin-system/plugin-development.md)

---

*本文档由 Claude Code 自动生成*
