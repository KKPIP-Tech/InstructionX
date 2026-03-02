# API 调用演示指南

## 概述

本指南展示了如何使用 InstructionX 插件系统的 API 调用功能。我们创建了两个演示插件：

1. **string_tools** - 提供 API 的插件，包含各种字符串处理方法
2. **api_demo** - 调用其他插件 API 的演示插件

## 插件结构

### 1. string_tools 插件（提供 API）

```
plugin/string_tools/
├── __init__.py          # 包标识
├── service.py           # 服务类，包含 API 方法
├── information.py       # 插件元数据，包含 service_api 定义
└── entrance.py          # UI 界面入口
```

### 2. api_demo 插件（调用 API）

```
custom_plugin/api_demo/
├── __init__.py          # 包标识
├── information.py       # 插件元数据
└── entrance.py          # UI 界面入口，演示 API 调用
```

## 功能展示

### string_tools 插件提供的 API

该插件提供以下 7 个 API 方法：

| 方法名 | 描述 | 参数 | 返回值 |
|--------|------|------|--------|
| `to_uppercase` | 转换为大写 | `text: str` | `str` |
| `to_lowercase` | 转换为小写 | `text: str` | `str` |
| `reverse_text` | 反转文本 | `text: str` | `str` |
| `capitalize_words` | 单词首字母大写 | `text: str` | `str` |
| `count_words` | 统计单词数 | `text: str` | `int` |
| `count_chars` | 统计字符数 | `text: str, include_spaces: bool=False` | `int` |
| `remove_whitespace` | 移除空白字符 | `text: str` | `str` |

### api_demo 插件功能

该插件演示以下功能：

1. **API 列表浏览** - 查看字符串工具插件的所有可用 API 方法
2. **动态调用** - 通过 PluginManager 动态调用其他插件的方法
3. **API 发现** - 查询所有已注册插件的 API
4. **Function Tools** - 查看自动生成的 Function Tools 定义
5. **错误处理** - 演示如何处理 API 调用错误

## 使用方法

### 方法 1：通过 UI 界面使用

1. 启动主程序
2. 在技能面板中找到"API 调用演示"插件
3. 点击打开插件界面
4. 在左侧列表中选择一个 API 方法
5. 在输入框中输入文本
6. 点击"执行 API 调用"按钮
7. 查看调用结果

### 方法 2：通过代码调用

```python
from core.plugin.manager import PluginManager

# 获取 PluginManager 实例
manager = PluginManager()

# 获取字符串工具插件的 ID
string_tools_id = manager.get_plugin_id_by_name("字符串工具")

# 调用 API
result = manager.call_plugin_method(
    caller_id="my-plugin-id",
    plugin_id=string_tools_id,
    method_name="to_uppercase",
    text="hello world"
)

print(result)  # 输出: "HELLO WORLD"
```

### 方法 3：查看所有 API

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取所有插件的 API
all_apis = manager.get_all_apis()

for plugin_id, api_info in all_apis.items():
    print(f"插件: {api_info['plugin_name']}")
    print(f"方法: {', '.join(api_info['methods'])}")
    print("-" * 50)
```

### 方法 4：获取 Function Tools

```python
from core.plugin.manager import PluginManager

manager = PluginManager()

# 获取所有 function tools（用于 MCP/OpenAI）
tools = manager.get_all_function_tools()

for tool in tools:
    print(f"工具名称: {tool['function']['name']}")
    print(f"描述: {tool['function']['description']}")
```

## 技术细节

### API 自动注册流程

PluginManager 在加载插件时自动执行以下步骤：

1. 扫描插件目录
2. 加载 `entrance.py` 实例化插件
3. 导入 `information.py` 获取 `service_api` 定义
4. 导入 `service.py` 创建 Service 实例
5. 自动注册 API 到 PluginManager 的 `_api_registry`

### API 调用机制

```python
def call_plugin_method(self,
                     caller_id: str,
                     plugin_id: str,
                     method_name: str,
                     **kwargs) -> Any:
    """
    跨插件调用方法
    
    1. 验证插件是否存在
    2. 验证方法是否已注册
    3. 执行方法并传递参数
    4. 处理异常并返回结果
    """
```

### Function Tools 生成

Function Tools 自动从 `service_api` 定义生成，格式符合 OpenAI/MCP 规范：

```json
{
  "type": "function",
  "function": {
    "name": "plugin-id.method_name",
    "description": "方法描述",
    "parameters": {
      "type": "object",
      "properties": {
        "param": {
          "type": "string",
          "description": "参数描述"
        }
      },
      "required": ["param"]
    }
  }
}
```

## 开发指南

### 创建提供 API 的插件

1. 在 `service.py` 中实现业务逻辑方法
2. 在 `information.py` 的 `service_api` 中定义 API 接口
3. PluginManager 自动处理注册

示例：

```python
# service.py
class Service:
    def my_method(self, text: str) -> str:
        return text.upper()

# information.py
class MyPluginInfo(IPluginInfo):
    @property
    def service_api(self) -> Dict[str, Any]:
        return {
            "my_method": {
                "description": "描述",
                "parameters": {
                    "text": {
                        "type": "str",
                        "description": "参数",
                        "required": True
                    }
                },
                "returns": {
                    "type": "str",
                    "description": "返回值"
                }
            }
        }
```

### 创建调用 API 的插件

1. 在插件中获取 PluginManager 实例
2. 使用 `call_plugin_method()` 调用其他插件
3. 处理调用结果和错误

示例：

```python
# entrance.py
from core.plugin.manager import PluginManager

class MyPlugin(IPlugin):
    def __init__(self):
        self.manager = PluginManager()
    
    def call_other_plugin(self):
        target_id = self.manager.get_plugin_id_by_name("目标插件名")
        
        try:
            result = self.manager.call_plugin_method(
                caller_id="my-plugin-id",
                plugin_id=target_id,
                method_name="method_name",
                param="value"
            )
            return result
        except Exception as e:
            return f"错误: {e}"
```

## 最佳实践

### 1. API 设计

- **单一职责**：每个方法只做一件事
- **幂等性**：相同参数多次调用结果一致
- **清晰命名**：方法名要能清楚表达功能
- **完整文档**：提供详细的参数和返回值说明

### 2. 错误处理

```python
try:
    result = manager.call_plugin_method(...)
except ValueError as e:
    # 插件或方法不存在
    handle_not_found_error(e)
except RuntimeError as e:
    # 方法执行失败
    handle_execution_error(e)
except Exception as e:
    # 未知错误
    handle_unknown_error(e)
```

### 3. 性能优化

- **缓存结果**：对于不频繁变化的数据缓存结果
- **批量操作**：提供批量处理方法减少调用次数
- **异步支持**：考虑使用异步方法（未来版本）

### 4. 安全考虑

- **参数验证**：在方法内部验证所有输入参数
- **权限检查**：验证调用者是否有权限执行操作
- **敏感操作**：对删除、修改等操作进行二次确认

## 扩展应用

### 集成到 MCP 服务器

```python
from mcp.server import Server
from core.plugin.manager import PluginManager

mcp_server = Server("instructionx-plugins")
manager = PluginManager()

# 注册所有插件 API 为 MCP tools
for tool in manager.get_all_function_tools():
    function_name = tool["function"]["name"]
    
    @mcp_server.tool(function_name)
    async def call_plugin(**kwargs):
        # 提取插件 ID 和方法名
        parts = function_name.split(".")
        plugin_id, method_name = parts[0], ".".join(parts[1:])
        
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
manager = PluginManager()
tools = manager.get_all_function_tools()

response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "将文本转大写"}],
    tools=tools,
    tool_choice="auto"
)

# 处理 function call
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        function_args = json.loads(tool_call.function.arguments)
        
        parts = tool_call.function.name.split(".")
        plugin_id, method_name = parts[0], ".".join(parts[1:])
        
        result = manager.call_plugin_method(
            caller_id="openai-assistant",
            plugin_id=plugin_id,
            method_name=method_name,
            **function_args
        )
```

## 故障排除

### 问题 1：找不到插件

**现象**：`get_plugin_id_by_name()` 返回 None

**解决方案**：
1. 检查插件是否在 `plugin/` 或 `custom_plugin/` 目录下
2. 检查插件是否有 `entrance.py` 和 `information.py`
3. 确认插件已加载：`manager.get_all_plugins()`

### 问题 2：API 未注册

**现象**：`get_plugin_api()` 返回 None

**解决方案**：
1. 检查 `information.py` 中是否定义了 `service_api`
2. 检查 `service.py` 中的方法名是否与 `service_api` 定义一致
3. 重新加载插件：`manager.reload_plugins()`

### 问题 3：方法调用失败

**现象**：`call_plugin_method()` 抛出 RuntimeError

**解决方案**：
1. 检查方法参数是否正确
2. 查看异常消息中的具体错误
3. 检查 Service 类中方法的实现

## 总结

通过这个演示，您可以：

1. ✅ 理解如何创建提供 API 的插件
2. ✅ 理解如何创建调用 API 的插件
3. ✅ 掌握 PluginManager 的 API 调用功能
4. ✅ 了解 Function Tools 的生成机制
5. ✅ 学习插件间协作的最佳实践

更多详细信息，请参考：
- `docs/PLUGIN_API_GUIDE.md` - 完整的 API 调用指南
- `docs/PLUGIN_DESIGN.md` - 插件设计文档