"""
工具名净化工具

提供将任意名称净化为符合 OpenAI function 命名规范的工具名的能力，
供插件 API 注册与 MCP 工具桥接共用（单一职责模块）。
"""

import re


# OpenAI function 命名规范允许的最大工具名长度
MAX_TOOL_NAME_LENGTH = 64

# 工具名合法字符集（[a-zA-Z0-9_-]）之外的字符统一替换为下划线
_ILLEGAL_CHAR_PATTERN = re.compile(r'[^a-zA-Z0-9_-]')


def sanitize_tool_name(name: str) -> str:
    """将工具名净化为符合 OpenAI function 命名规范的形式

    规范要求：^[a-zA-Z0-9_-]{1,64}$
    规则：所有不在 [a-zA-Z0-9_-] 内的字符替换为 '_'，结果截断到 64 字符。

    Args:
        name: 原始工具名（如 "{plugin_id}__{method_name}"）

    Returns:
        净化后的合法工具名
    """
    return _ILLEGAL_CHAR_PATTERN.sub('_', name)[:MAX_TOOL_NAME_LENGTH]
