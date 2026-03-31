"""工具注册示例

展示如何注册工具供 LLM 调用。
"""

from core.llm import get_llm_plugin_service


def calculate(expression: str) -> str:
    """执行数学表达式计算

    Args:
        expression: 数学表达式，如 "2+3*4"

    Returns:
        计算结果的字符串表示
    """
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"计算错误: {e}"


def get_current_time() -> str:
    """获取当前时间

    Returns:
        当前时间的字符串表示
    """
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_sample_tools() -> list:
    """返回示例工具定义列表

    Returns:
        OpenAI function calling 格式的工具定义
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "calculate",
                "description": "执行数学表达式计算。输入为标准数学表达式字符串，如 '2+3*4'。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "数学表达式，如 '2+3*4'",
                        },
                    },
                    "required": ["expression"],
                },
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_current_time",
                "description": "获取当前系统时间。无需参数。",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
        },
    ]


def register_sample_tools():
    """注册示例工具到共享工具注册表

    将 calculate 和 get_current_time 注册到 LLMPluginService 的共享工具注册表。
    """
    svc = get_llm_plugin_service()
    registry = svc.get_shared_tool_registry()

    # 注册计算器工具
    registry.register(
        name="calculate",
        description="执行数学表达式计算。输入为标准数学表达式字符串。",
        parameters={
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，如 '2+3*4'",
                },
            },
            "required": ["expression"],
        },
        handler=calculate,
    )

    # 注册时间工具
    registry.register(
        name="get_current_time",
        description="获取当前系统时间。无需参数。",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
        handler=get_current_time,
    )
