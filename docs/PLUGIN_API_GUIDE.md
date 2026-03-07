# 插件 API 调用指南

## 概述

PluginManager 提供了插件间的 API 调用功能，使得插件可以：

1. **跨插件调用方法**: 一个插件可以直接调用另一个插件的方法
2. **生成 Function Tools**: 自动生成符合 MCP/OpenAI function calling 规范的工具定义
3. **动态 API 发现**: 插件可以查询其他插件可用的 API 方法

## 架构设计

### API 注册流程

```
┌─────────────────────────────────────────┐
│    information.py (元数据层)         │
│  ┌──────────────────────────────────┐   │
│  │ - service_api 定义               │  │
│  │ - 参数和返回值说明               │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
         ▲
         │ 读取
         │
┌────────┴─────────────────────────────┐
│    PluginManager (管理器)           │
│  ┌──────────────────────────────────┐   │
│  │ - 加载插件                      │  │
│  │ - 读取 information.py            │  │
│  │ - 自动注册 API                 │  │
│  │ - 管理调用                    │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
         ▲
         │ 调用
         │
┌────────┴─────────────────────────────┐
│    其他插件                         │
│  ┌──────────────────────────────────┐   │
│  │ - 通过 PluginManager 调用 API  │  │
│  │ - 获取 Function Tools          │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## 核心概念

### 1. Service 类

Service 类包含插件的业务逻辑方法，这些方法可以被其他插件调用。

```python
# plugin/text_formatting/service.py
class Service:
    """文本格式化服务"""
    
    def to_uppercase(self, text: str) -> str:
        """将文本转换为大写"""
        return text.upper()
```

### 2. service_api 定义

在 `information.py` 的 `service_api` 属性中定义 API 接口：

```python
# plugin/text_formatting/information.py
class TextFormattingPluginInfo(IPluginInfo):
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "大写后的文本"
                }
            }
        }
```

### 3. API 参数说明

#### 参数结构

```python
{
    "method_name": {
        "description": "方法描述",
        "parameters": {
            "param_name": {
                "type": "str|int|float|bool|list|dict|any",
                "description": "参数描述",
                "required": True/False,
                "default": "默认值（可选）"
            }
        },
        "returns": {
            "type": "返回类型",
            "description": "返回值描述"
        }
    }
}
```

#### 参数类型

- `str`: 字符串
- `int`: 整数
- `float`: 浮点数
- `bool`: 布尔值
- `list`: 列表
- `dict`: 字典
- `any`: 任意类型

## API 自动注册

PluginManager 会在加载插件时自动注册 API，无需手动调用。

### 注册流程

1. PluginManager 扫描插件目录
2. 加载 `entrance.py` 实例化插件
3. 读取 `information.py` 获取 `service_api`
4. 创建 Service 实例
5. 自动注册 API 到 PluginManager

### 完整示例

#### service.py

```python
"""
文本格式化服务
"""

class Service:
    """文本格式化服务类"""
    
    def to_uppercase(self, text: str) -> str:
        """
        将文本转换为大写
        
        Args:
            text: 输入文本
            
        Returns:
            大写文本
        """
        return text.upper()
    
    def to_lowercase(self, text: str) -> str:
        """
        将文本转换为小写
        
        Args:
            text: 输入文本
            
        Returns:
            小写文本
        """
        return text.lower()
    
    def reverse_text(self, text: str) -> str:
        """
        反转文本
        
        Args:
            text: 输入文本
            
        Returns:
            反转后的文本
        """
        return text[::-1]
```

#### information.py

```python
"""
文本格式化插件元数据
"""

from core.plugin.plugin_info_interface import IPluginInfo
from core.plugin.plugin_version import PluginVersion
from core.plugin.plugin_icon import PluginIcon
from typing import Dict, Any

class TextFormattingPluginInfo(IPluginInfo):
    """文本格式化插件元数据"""
    
    @property
    def version(self) -> PluginVersion:
        return PluginVersion.from_string("release.1.0.0")
    
    @property
    def developer(self) -> str:
        return "KKPIP-Tech"
    
    @property
    def developer_email(self) -> str:
        return "support@example.com"
    
    @property
    def developer_website(self) -> str:
        return "https://github.com/KKPIP-Tech/InstructionX"
    
    @property
    def is_free(self) -> bool:
        return True
    
    @property
    def description(self) -> str:
        return """
        文本格式化插件提供常用的文本处理工具，包括：
        - 文本大小写转换（大写、小写）
        - 文本反转
        - 支持批量文本处理
        
        该插件适用于需要快速格式化文本的场景，
        如数据处理、内容编辑等。
        """
    
    @property
    def service_api(self) -> Dict[str, Any]:
        """Service API 定义"""
        return {
            "to_uppercase": {
                "description": "将文本转换为大写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "大写后的文本"
                }
            },
            "to_lowercase": {
                "description": "将文本转换为小写",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "小写后的文本"
                }
            },
            "reverse_text": {
                "description": "反转文本",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "输入文本",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "反转后的文本"
                }
            }
        }
    
    @property
    def skill_icon(self) -> PluginIcon:
        return PluginIcon.builtin("SP_FileIcon")
    
    @property
    def skill_description(self) -> str:
        return "提供文本格式化工具"
    
    @property
    def tags(self) -> list[str]:
        return ["text", "formatting", "utility"]
```

#### entrance.py

```python
"""
文本格式化插件 - UI 界面入口
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton
from core.plugin.plugin_interface import IPlugin

class TextFormattingPlugin(IPlugin):
    """文本格式化插件"""
    
    @property
    def plugin_name(self) -> str:
        return "文本格式化"
    
    def _create_widget(self, parent=None, data_provider=None):
        # 注意：API 由 PluginManager 自动注册，无需手动注册
        widget = QWidget(parent)
        layout = QVBoxLayout(widget)
        
        # UI 代码...
        label = QLabel("文本格式化工具")
        layout.addWidget(label)
        
        return widget
```

## 跨插件调用

### 基本调用

```python
from core.plugin.manager import PluginManager

# 获取 PluginManager 实例
manager = PluginManager()

# 调用文本格式化插件的 API
result = manager.call_plugin_method(
    caller_id="my-plugin-id",
    plugin_id="text-formatting-plugin-id",  # 目标插件 ID
    method_name="to_uppercase",
    text="hello world"
)

print(result)  # 输出: "HELLO WORLD"
```

### 获取插件 ID

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 方法 1: 通过名称获取 ID
plugin_id = manager.get_plugin_id_by_name("文本格式化")

# 方法 2: 遍历所有插件
all_plugins = manager.get_all_plugins()
for plugin in all_plugins:
    print(f"插件名称: {plugin.plugin_name}")
    print(f"插件 ID: {plugin.plugin_id}")
```

### 错误处理

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

try:
    result = manager.call_plugin_method(
        caller_id="my-plugin-id",
        plugin_id="target-plugin-id",
        method_name="to_uppercase",
        text="hello"
    )
    print(f"成功: {result}")
    
except ValueError as e:
    # 插件或方法不存在
    print(f"API 不可用: {e}")
    
except RuntimeError as e:
    # 方法执行失败
    print(f"API 调用失败: {e}")
```

## API 发现

### 获取所有 API 信息

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取所有插件的 API
all_apis = manager.get_all_apis()

for plugin_id, api_info in all_apis.items():
    print(f"\n插件: {api_info['plugin_name']}")
    print(f"ID: {plugin_id}")
    print(f"可用方法:")
    for method in api_info['methods']:
        print(f"  - {method}")
```

### 获取特定插件的 API

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取文本格式化插件的 API
plugin_api = manager.get_plugin_api("text-formatting-plugin-id")

if plugin_api:
    print(f"插件名称: {plugin_api['plugin_name']}")
    print(f"可用方法:")
    for method in plugin_api['methods']:
        print(f"  - {method}")
```

### 获取 API 详细描述

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取特定方法的详细描述
desc = manager.get_api_description(
    "text-formatting-plugin-id",
    "to_uppercase"
)

print(f"方法名: {desc['name']}")
print(f"描述: {desc['description']}")
print(f"参数: {desc['parameters']}")
print(f"返回值: {desc['returns']}")
```

## Function Tools 生成

### 获取所有 Function Tools

用于 MCP 或 OpenAI Function Calling：

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取所有 function tools
tools = manager.get_all_function_tools()

# tools 格式符合 OpenAI function calling 规范
for tool in tools:
    print(f"\n工具: {tool['function']['name']}")
    print(f"描述: {tool['function']['description']}")
```

### 集成到 MCP 服务器

```python
from mcp.server import Server
from core.plugin.manager import PluginManager

# 创建 MCP 服务器
mcp_server = Server("instructionx-plugins")

# 注册所有插件 API 为 MCP tools
manager = PluginManager()
tools = manager.get_all_function_tools()

for tool in tools:
    function_name = tool["function"]["name"]
    
    # 提取插件 ID 和方法名
    parts = function_name.split(".")
    plugin_id, method_name = parts[0], ".".join(parts[1:])
    
    # 注册到 MCP
    @mcp_server.tool(function_name)
    async def call_plugin(**kwargs):
        try:
            result = manager.call_plugin_method(
                caller_id="mcp-server",
                plugin_id=plugin_id,
                method_name=method_name,
                **kwargs
            )
            return {"result": result}
        except Exception as e:
            return {"error": str(e)}
```

### 集成到 OpenAI Function Calling

```python
import openai
from core.plugin.manager import PluginManager

client = openai.OpenAI()

# 获取所有 function tools
manager = PluginManager()
tools = manager.get_all_function_tools()

# 发送聊天请求
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "帮我将文本 'hello' 转换为大写"}
    ],
    tools=tools,
    tool_choice="auto"
)

# 处理 function call
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)
        
        # 调用插件方法
        parts = function_name.split(".")
        plugin_id, method_name = parts[0], ".".join(parts[1:])
        
        result = manager.call_plugin_method(
            caller_id="openai-assistant",
            plugin_id=plugin_id,
            method_name=method_name,
            **function_args
        )
        
        print(f"调用结果: {result}")
```

## 完整示例：插件协作

### 示例：颜色转换插件调用文本格式化插件

#### color_converter/service.py

```python
"""
颜色转换服务
"""

class Service:
    """颜色转换服务"""
    
    def hex_to_rgb(self, hex_str: str) -> str:
        """将 HEX 颜色转换为 RGB"""
        # 实现颜色转换逻辑
        return "rgb(255, 87, 51)"
    
    def format_color_description(self, plugin_manager, hex_str: str) -> str:
        """
        格式化颜色描述（调用其他插件）
        
        Args:
            plugin_manager: PluginManager 实例
            hex_str: HEX 颜色字符串
            
        Returns:
            格式化后的描述
        """
        # 调用文本格式化插件转换为大写
        result = plugin_manager.call_plugin_method(
            caller_id=self.plugin_id,
            plugin_id="text-formatting-plugin-id",
            method_name="to_uppercase",
            text=hex_str
        )
        
        return f"颜色代码: {result}"
```

## 最佳实践

### 1. API 设计原则

- **单一职责**: 每个方法只做一件事
- **幂等性**: 相同参数多次调用结果一致
- **清晰的参数**: 参数命名和类型要明确
- **完整的文档**: 提供详细的描述信息

### 2. 参数验证

```python
class Service:
    def process_data(self, data: str, max_length: int = 100) -> dict:
        """
        处理数据
        
        Args:
            data: 输入数据
            max_length: 最大长度
            
        Returns:
            处理结果
        """
        # 参数验证
        if not isinstance(data, str):
            raise ValueError("data 必须是字符串")
        
        if max_length <= 0:
            raise ValueError("max_length 必须大于 0")
        
        # 业务逻辑
        return {"result": data[:max_length]}
```

### 3. 错误处理

```python
class Service:
    def safe_operation(self, param: str) -> str:
        """
        安全操作
        
        Args:
            param: 参数
            
        Returns:
            操作结果
        """
        try:
            # 业务逻辑
            return param.upper()
        except Exception as e:
            # 返回友好的错误信息
            return f"错误: {str(e)}"
```

### 4. 性能优化

- **缓存结果**: 对于不频繁变化的数据缓存结果
- **批量操作**: 提供批量处理方法减少调用次数
- **异步支持**: 考虑使用异步方法（未来版本）

### 5. 安全考虑

- **权限验证**: 在方法内部验证调用者权限
- **参数校验**: 验证所有输入参数
- **敏感操作**: 对删除、修改等操作进行二次确认

## 常见问题

### Q1: API 什么时候注册？

A: PluginManager 会在加载插件时自动注册 API，无需手动调用。

### Q2: 如何获取插件 ID？

A: 可以通过以下方式获取：
```python
manager = PluginManager()
plugin_id = manager.get_plugin_id_by_name("插件名称")
```

### Q3: 如何调试 API 调用？

A: 可以使用以下方法：
```python
try:
    result = manager.call_plugin_method(...)
except Exception as e:
    print(f"错误类型: {type(e).__name__}")
    print(f"错误信息: {e}")
    import traceback
    traceback.print_exc()
```

### Q4: API 方法可以有默认参数吗？

A: 可以。在 `service_api` 中标注 `required: False`：
```python
{
    "method_name": {
        "parameters": {
            "optional_param": {
                "type": "str",
                "description": "可选参数",
                "required": False,
                "default": "default_value"
            }
        }
    }
}
```

### Q5: 如何处理复杂的返回值？

A: 使用 JSON 兼容的类型：
```python
{
    "method_name": {
        "returns": {
            "type": "dict",
            "description": "复杂返回值",
            "example": {
                "status": "success",
                "data": {...}
            }
        }
    }
}
```

## 总结

PluginManager 的 API 调用功能为插件系统提供了强大的互操作能力：

1. **自动注册**: 无需手动注册，PluginManager 自动处理
2. **解耦合**: 插件通过接口通信，不依赖具体实现
3. **可发现**: 动态发现和调用其他插件的功能
4. **标准化**: 统一的调用接口和错误处理
5. **AI 友好**: 自动生成 function tools 定义

这使得构建 MCP 服务器、AI 助手、工作流引擎等高级功能变得简单而强大！