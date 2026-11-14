"""MCP Client 可选依赖导入与可用性检查。"""

from typing import Any

try:
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.stdio import (
        StdioServerParameters,
        get_default_environment,
        stdio_client,
    )
    from mcp.client.streamable_http import streamable_http_client
except ImportError:
    httpx = None
    ClientSession = None
    StdioServerParameters = None
    get_default_environment = None
    stdio_client = None
    streamable_http_client = None


def ensure_mcp_sdk() -> None:
    """确认 MCP SDK 可用，缺失时给出明确中文错误。"""
    if ClientSession is None:
        raise RuntimeError("缺少 MCP SDK 依赖，无法连接外部 MCP Server")


def create_http_client(**kwargs: Any) -> Any:
    """创建可选的认证 HTTP Client，缺少依赖时明确失败。"""
    if httpx is None:
        raise RuntimeError("缺少 httpx 依赖，无法使用带认证的 MCP HTTP 连接")
    return httpx.AsyncClient(**kwargs)
