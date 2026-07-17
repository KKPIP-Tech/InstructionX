# -*- coding: utf-8 -*-
"""冒烟测试用的最小 stdio MCP Server（由 smoke 脚本以子进程方式启动）"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("smoke-stdio")


@mcp.tool()
def echo(text: str) -> str:
    """回显输入文本"""
    return f"echo:{text}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
