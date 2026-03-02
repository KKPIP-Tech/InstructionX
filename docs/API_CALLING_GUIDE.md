# DataProvider API 调用指南

## 概述

DataProvider 不仅提供数据持久化和发布/订阅功能，还支持插件间的直接 API 调用。这使得插件可以：

1. **跨插件调用方法**: 一个插件可以直接调用另一个插件的方法
2. **生成 Function Tools**: 自动生成符合 MCP/OpenAI function calling 规范的工具定义
3. **动态 API 发现**: 插件可以查询其他插件可用的 API 方法

## 核心概念

### API 注册表

DataProvider 使用 `APIRegistry` 来管理所有插件的 API 接口：

```python
from core.data.data_provider import DataProvider
from core.data.api_registry import APIDescription
```

### API 描述结构

每个 API 方法都需要提供描述信息：

```python
APIDescription(
    name="add_task",
    description="添加一个新任务到任务列表",
    parameters={
        "title": {
            "type": "string",
            "description": "任务标题",
            "required": True
        },
        "priority": {
            "type": "string",
            "description": "任务优先级 (low/normal/high)",
            "required": False
        }
    },
    returns={
        "type": "object",
        "description": "创建的任务对象"
    }
)
```

## 插件 API 注册

### 步骤 1: 定义 API 方法

在插件的 `service.py` 中定义可被其他插件调用的方法：

```python
class TaskManagerService:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
        self.tasks = []
    
    def add_task(self, title: str, priority: str = "normal") -> Dict[str, Any]:
        """
        添加一个新任务
        
        Args:
            title: 任务标题
            priority: 任务优先级
            
        Returns:
            任务字典
        """
        task = {
            "id": f"task_{datetime.now().timestamp()}",
            "title": title,
            "priority": priority,
            "status": "pending",
            "created_at": datetime.now().isoformat()
        }
        self.tasks.append(task)
        return task
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取指定任务"""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None
    
    def list_tasks(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        列出所有任务
        
        Args:
            status: 可选，按状态筛选
            
        Returns:
            任务列表
        """
        if status:
            return [t for t in self.tasks if t["status"] == status]
        return self.tasks.copy()
```

### 步骤 2: 定义 API 描述

```python
from core.data.api_registry import APIDescription

# 定义 API 描述
API_DESCRIPTIONS = {
    "add_task": APIDescription(
        name="add_task",
        description="添加一个新任务到任务列表",
        parameters={
            "title": {
                "type": "string",
                "description": "任务标题",
                "required": True
            },
            "priority": {
                "type": "string",
                "description": "任务优先级 (low/normal/high)",
                "required": False
            }
        },
        returns={
            "type": "object",
            "description": "创建的任务对象"
        }
    ),
    
    "get_task": APIDescription(
        name="get_task",
        description="获取指定任务的详细信息",
        parameters={
            "task_id": {
                "type": "string",
                "description": "任务ID",
                "required": True
            }
        },
        returns={
            "type": "object",
            "description": "任务对象，如果不存在则返回 None"
        }
    ),
    
    "list_tasks": APIDescription(
        name="list_tasks",
        description="列出所有任务，可按状态筛选",
        parameters={
            "status": {
                "type": "string",
                "description": "可选，任务状态 (pending/in_progress/completed/cancelled)",
                "required": False
            }
        },
        returns={
            "type": "array",
            "description": "任务列表"
        }
    )
}
```

### 步骤 3: 注册 API 到 DataProvider

在插件的 `entrance.py` 中注册 API：

```python
from core.plugin.plugin_interface import IPlugin

class TaskManagerPlugin(IPlugin):
    def get_widget(self, parent=None, data_provider=None):
        # 确保 plugin_id 存在
        plugin_id = self.plugin_id if self.plugin_id else "task-manager-default"
        
        # 创建服务实例
        service = TaskManagerService(plugin_id)
        
        # 注册插件
        if data_provider:
            try:
                data_provider.register_plugin(plugin_id, "TaskManager")
                data_provider.set_active_instance(plugin_id)
            except:
                pass
            
            # 注册 API 方法
            api_methods = {
                "add_task": service.add_task,
                "get_task": service.get_task,
                "list_tasks": service.list_tasks
            }
            
            data_provider.register_plugin_api(
                plugin_id=plugin_id,
                api_methods=api_methods,
                api_descriptions=API_DESCRIPTIONS
            )
        
        # 创建 UI...
        widget = QWidget(parent)
        # ... UI 代码
        return widget
```

## 跨插件调用

### 基本调用

插件 A 调用插件 B 的方法：

```python
from core.data.data_provider import DataProvider

class ReporterService:
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
    
    def generate_report(self, task_manager_id: str):
        """生成任务报告"""
        
        # 调用任务管理器的 list_tasks 方法
        all_tasks = self.data_provider.call_plugin_method(
            caller_id=self.plugin_id,
            plugin_id=task_manager_id,
            method_name="list_tasks",
            status="completed"
        )
        
        # 处理返回的数据
        report = {
            "total_completed": len(all_tasks),
            "tasks": all_tasks
        }
        return report
```

### 错误处理

```python
try:
    result = self.data_provider.call_plugin_method(
        caller_id=self.plugin_id,
        plugin_id=task_manager_id,
        method_name="add_task",
        title="新任务",
        priority="high"
    )
except Exception as e:
    print(f"调用失败: {e}")
```

## Function Tools 生成

### 获取所有 Function Tools

用于 MCP 或 OpenAI Function Calling：

```python
# 获取所有可用的 function tools
provider = DataProvider()
tools = provider.get_all_function_tools()

# tools 格式符合 OpenAI function calling 规范
# 示例输出：
[
    {
        "type": "function",
        "function": {
            "name": "task-manager-default.add_task",
            "description": "[TaskManager] 添加一个新任务到任务列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "任务标题"
                    },
                    "priority": {
                        "type": "string",
                        "description": "任务优先级 (low/normal/high)"
                    }
                },
                "required": ["title"]
            }
        }
    }
]
```

### 集成到 MCP 服务器

```python
from mcp.server import Server

# 创建 MCP 服务器
mcp_server = Server("instructionx-plugins")

# 注册所有插件 API 为 MCP tools
provider = DataProvider()
tools = provider.get_all_function_tools()

for tool in tools:
    function_name = tool["function"]["name"]
    
    # 提取插件 ID 和方法名
    parts = function_name.split(".")
    plugin_id, method_name = parts[0], ".".join(parts[1:])
    
    # 注册到 MCP
    @mcp_server.tool(function_name)
    async def call_plugin(**kwargs):
        try:
            result = provider.call_plugin_method(
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

client = openai.OpenAI()

# 获取所有 function tools
provider = DataProvider()
tools = provider.get_all_function_tools()

# 发送聊天请求
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "user", "content": "帮我添加一个高优先级的任务：完成文档编写"}
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
        result = provider.call_plugin_method(
            caller_id="openai-assistant",
            plugin_id=function_name.split(".")[0],
            method_name=".".join(function_name.split(".")[1:]),
            **function_args
        )
        
        print(f"调用结果: {result}")
```

## API 发现和查询

### 获取所有 API 信息

```python
provider = DataProvider()

# 获取所有插件的 API
all_apis = provider.get_all_apis()

for plugin_id, api_info in all_apis.items():
    print(f"插件: {plugin_id}")
    print(f"类型: {api_info['plugin_type']}")
    print(f"可用方法: {', '.join(api_info['methods'])}")
    print()
```

### 获取特定插件的 API 描述

```python
# 获取任务管理器的所有 API 描述
task_manager_api = provider.get_api_description("task-manager-default")

for method_name, desc in task_manager_api.items():
    print(f"方法: {desc['name']}")
    print(f"描述: {desc['description']}")
    print(f"参数: {desc['parameters']}")
    print(f"返回: {desc['returns']}")
    print()
```

### 获取单个方法的描述

```python
# 获取 add_task 方法的详细描述
add_task_desc = provider.get_api_description(
    "task-manager-default",
    "add_task"
)

print(f"方法名: {add_task_desc['name']}")
print(f"描述: {add_task_desc['description']}")
print(f"参数: {add_task_desc['parameters']}")
print(f"返回值: {add_task_desc['returns']}")
```

## 完整示例

### 示例 1: 任务管理器 + 自动助手

```python
from core.data.data_provider import DataProvider

class AutoAssistantService:
    """自动助手服务 - 使用 AI 调用插件 API"""
    
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
    
    def process_natural_language(self, text: str):
        """
        处理自然语言命令
        
        示例输入:
        - "添加一个任务：完成代码审查"
        - "列出所有待办任务"
        - "将任务 123 标记为已完成"
        """
        # 简单的关键词匹配（实际项目中可以使用 NLP 或 LLM）
        if "添加" in text and "任务" in text:
            # 提取任务标题
            title = text.split("：")[-1].strip() if "：" in text else text
            
            # 调用任务管理器的 API
            result = self.data_provider.call_plugin_method(
                caller_id=self.plugin_id,
                plugin_id="task-manager-default",
                method_name="add_task",
                title=title
            )
            
            return f"✅ 已创建任务: {result['id']}"
        
        elif "列出" in text and "任务" in text:
            # 调用任务管理器的 API
            tasks = self.data_provider.call_plugin_method(
                caller_id=self.plugin_id,
                plugin_id="task-manager-default",
                method_name="list_tasks"
            )
            
            return f"📋 共有 {len(tasks)} 个任务"
        
        else:
            return "❓ 无法理解命令"
```

### 示例 2: 插件编排

```python
class WorkflowService:
    """工作流服务 - 编排多个插件的 API"""
    
    def __init__(self, plugin_id: str):
        self.plugin_id = plugin_id
        self.data_provider = DataProvider()
    
    def complete_document_workflow(self, doc_title: str):
        """
        完成文档工作流
        
        1. 创建任务
        2. 生成报告
        3. 通知用户
        """
        # 步骤 1: 创建任务
        task = self.data_provider.call_plugin_method(
            caller_id=self.plugin_id,
            plugin_id="task-manager-default",
            method_name="add_task",
            title=doc_title,
            priority="high"
        )
        
        # 步骤 2: 生成统计报告
        report = self.data_provider.call_plugin_method(
            caller_id=self.plugin_id,
            plugin_id="task-reporter-default",
            method_name="get_statistics_report",
            task_manager_id="task-manager-default"
        )
        
        # 步骤 3: 返回工作流结果
        return {
            "task_id": task["id"],
            "report": report,
            "status": "completed"
        }
```

## 最佳实践

### 1. API 设计原则

- **单一职责**: 每个方法只做一件事
- **幂等性**: 相同参数多次调用结果一致
- **清晰的参数**: 参数命名和类型要明确
- **完整的文档**: 提供详细的描述信息

### 2. 错误处理

```python
try:
    result = provider.call_plugin_method(
        caller_id=self.plugin_id,
        plugin_id=target_plugin,
        method_name="some_method",
        **kwargs
    )
except ValueError as e:
    # 插件或方法不存在
    print(f"API 不可用: {e}")
except RuntimeError as e:
    # 方法执行失败
    print(f"API 调用失败: {e}")
except Exception as e:
    # 其他错误
    print(f"未知错误: {e}")
```

### 3. 性能优化

- **批量操作**: 尽量批量调用而非单个调用
- **缓存结果**: 对于不频繁变化的数据缓存结果
- **异步调用**: 考虑使用异步 API（未来版本）

### 4. 安全考虑

- **权限验证**: 在方法内部验证调用者权限
- **参数校验**: 验证所有输入参数
- **敏感操作**: 对删除、修改等操作进行二次确认

## 总结

DataProvider 的 API 调用功能为插件系统提供了强大的互操作能力：

1. **解耦合**: 插件通过接口通信，不依赖具体实现
2. **可发现**: 动态发现和调用其他插件的功能
3. **标准化**: 统一的调用接口和错误处理
4. **AI 友好**: 自动生成 function tools 定义

这使得构建 MCP 服务器、AI 助手、工作流引擎等高级功能变得简单而强大！