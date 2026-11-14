# -*- coding: utf-8 -*-
"""core/mcp 修复后的冒烟测试（真实 mcp==1.27.0 SDK，不依赖外部网络）

覆盖：
a. MCPHostServer 注册工具后可被 FastMCP ToolManager 列出，参数校验模型工作
b. MCPClientManager._ensure_loop 后 run_coroutine_threadsafe 能在 1 秒内完成
c. client 侧净化工具名符合 OpenAI 正则
d. stdio 真实连接/调用/断开，无遗留子进程与 session 警告
e. HTTP 模式真实启动/认证中间件/真正关停
"""
import asyncio
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

RECONNECT_CYCLES = 100
CLEANUP_WARNING_MARKERS = (
    "cancel scope",
    "task was destroyed",
    "resourcewarning",
    "unclosed",
    "generatorexit",
)


class StderrGuard:
    """原样输出 stderr，同时保留清理警告供最终门禁判定。"""

    def __init__(self, stream):
        self._stream = stream
        self.content = []

    def write(self, text):
        self.content.append(text)
        return self._stream.write(text)

    def flush(self):
        self._stream.flush()

    def fileno(self):
        return self._stream.fileno()

    def isatty(self):
        return self._stream.isatty()

    def warning_text(self):
        text = "".join(self.content).lower()
        return "\n".join(marker for marker in CLEANUP_WARNING_MARKERS if marker in text)


stderr_guard = StderrGuard(sys.stderr)
sys.stderr = stderr_guard
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OPENAI_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail}")


def count_stdio_processes():
    """通过 Windows 进程表统计尚未退出的冒烟子进程。"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "(Get-CimInstance Win32_Process | Where-Object "
         "{$_.ProcessId -ne $PID -and $_.Name -like 'python%' -and "
         "$_.CommandLine -like '*_mcp_smoke_stdio_server*'} | "
         "Measure-Object).Count"],
        capture_output=True, text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "查询失败"


def run_reconnect_cycles(client, config, registry, expected_text, with_text):
    """执行真实连接、调用、断开循环，返回首轮资源或调用错误。"""
    failures = []
    server_id = config.server_id
    for index in range(RECONNECT_CYCLES):
        try:
            client.connect(config)
            tools = client.list_tools(server_id)
            if len(tools) != 1:
                raise RuntimeError(f"工具数量异常: {tools}")
            arguments = {"text": f"cycle-{index}"} if with_text else {}
            result = registry.tools[tools[0]]["handler"](**arguments)
            if expected_text not in str(result):
                raise RuntimeError(f"调用结果异常: {result}")
        except Exception as exc:
            failures.append(f"第 {index + 1} 次调用: {exc}")
        finally:
            client.disconnect(server_id)
            failures.extend(client._lifecycle_errors)
            client._lifecycle_errors = []
        if registry.tools or server_id in client.list_connected_servers():
            failures.append(f"第 {index + 1} 次断开后仍有工具或连接")
        if failures:
            break
    return failures


# ─── a. Server 工具注册 ─────────────────────────────────────────
from core.mcp.server import MCPHostServer

server = MCPHostServer(name="smoke", host="127.0.0.1", port=8877)
server.add_tool(
    name="smoke-plugin__do_thing",
    description="测试工具",
    parameters={
        "type": "object",
        "properties": {"x": {"type": "string"}, "n": {"type": "integer"}},
        "required": ["x"],
    },
    plugin_id="smoke-plugin",
    method_name="do_thing",
)
tm = server._fastmcp._tool_manager
names = [t.name for t in tm.list_tools()]
check("a1 工具可被 ToolManager 列出", "smoke-plugin__do_thing" in names, str(names))
tool = tm.get_tool("smoke-plugin__do_thing")
check(
    "a2 对外 JSON Schema 为注册时提供的 schema",
    tool.parameters.get("properties", {}).get("n", {}).get("type") == "integer",
    str(tool.parameters),
)
# 参数校验模型：缺必填参数应被拒绝，合法参数应通过（handler 内部调用会失败，
# 但失败应发生在校验之后 —— 用 from_function 的 arg_model 直接验证）
try:
    tool.fn_metadata.arg_model.model_validate({"n": 1})
    check("a3 缺少必填参数被校验模型拒绝", False, "未抛出校验错误")
except Exception:
    check("a3 缺少必填参数被校验模型拒绝", True)
parsed = tool.fn_metadata.arg_model.model_validate({"x": "a", "n": 3})
check("a4 合法参数通过校验模型", parsed.x == "a" and parsed.n == 3)
# 重名覆盖：应替换而非静默忽略
server.add_tool(
    name="smoke-plugin__do_thing",
    description="覆盖后的工具",
    parameters={"type": "object", "properties": {}},
    plugin_id="smoke-plugin",
    method_name="do_thing",
)
tool2 = tm.get_tool("smoke-plugin__do_thing")
check("a5 同名工具被显式替换", tool2.description == "覆盖后的工具", tool2.description)
server.remove_tool("smoke-plugin__do_thing")
check("a6 remove_tool 生效", tm.get_tool("smoke-plugin__do_thing") is None)


# ─── b/c. Client loop 与净化命名 ────────────────────────────────
class StubRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, name, description, parameters, handler, **kw):
        if name in self.tools:
            raise ValueError(f"duplicate tool: {name}")
        self.tools[name] = {
            "description": description,
            "parameters": parameters,
            "handler": handler,
        }

    def unregister(self, name):
        self.tools.pop(name, None)


from core.mcp.client import MCPClientManager

registry = StubRegistry()
client = MCPClientManager(registry, timeout=30.0)
loop = client._ensure_loop()
t0 = time.monotonic()
asyncio.run_coroutine_threadsafe(asyncio.sleep(0.01), loop).result(timeout=1.0)
elapsed = time.monotonic() - t0
check("b1 loop 在线程中运行(run_coroutine_threadsafe <1s)", elapsed < 1.0, f"{elapsed:.3f}s")
check(
    "b2 loop 线程为 daemon",
    client._loop_thread is not None
    and client._loop_thread.is_alive()
    and client._loop_thread.daemon,
)

from core.plugin.manager import PluginManager, sanitize_tool_name

san = sanitize_tool_name("mcp__my-server__tool.name:with@chars")
check("c1 净化名符合 OpenAI 正则", bool(OPENAI_RE.match(san)), san)
san2 = sanitize_tool_name("mcp__srv__" + "x" * 100)
check("c2 净化名截断到 64 字符", len(san2) == 64 and bool(OPENAI_RE.match(san2)))


# ─── d. stdio 真实连接端到端 ────────────────────────────────────
from core.mcp.config import MCPRemoteServerConfig

server_script = PROJECT_ROOT / "scripts" / "_mcp_smoke_stdio_server.py"
cfg = MCPRemoteServerConfig(
    server_id="smoke.stdio:server",  # 含点与冒号，验证净化
    name="Smoke Stdio",
    transport="stdio",
    command=sys.executable,
    args=[str(server_script)],
)
client.connect(cfg)
tools = client.list_tools("smoke.stdio:server")
check("d1 stdio 连接成功并列出工具", len(tools) == 1, str(tools))
check(
    "d2 工具名为净化命名空间名",
    tools and tools[0] == sanitize_tool_name("mcp__smoke.stdio:server__echo"),
    str(tools),
)
# 真实调用远端工具
entry = registry.tools[tools[0]]
ret = entry["handler"](text="hello")
check("d3 远端工具调用返回结果", "echo:hello" in str(ret), str(ret)[:80])
# 重连（同 server_id）：先断后连，不应抛重名错误
client.connect(cfg)
tools_after = client.list_tools("smoke.stdio:server")
check("d4 同 server_id 重连无重名冲突", tools_after == tools, str(tools_after))
client.disconnect("smoke.stdio:server")
check("d5 disconnect 后工具已注销", len(registry.tools) == 0, str(registry.tools))
check("d6 disconnect 后连接列表为空", client.list_connected_servers() == [])
stdio_failures = run_reconnect_cycles(
    client, cfg, registry, expected_text="echo:cycle-", with_text=True
)
check(
    "d7 100 次真实 stdio 连接/调用/断开无泄漏",
    not stdio_failures,
    "; ".join(stdio_failures[:3]),
)
time.sleep(1.0)
ps = count_stdio_processes()
check("d8 无遗留 stdio 子进程", ps == "0", f"剩余进程数={ps}")
shutdown_errors = client.shutdown()
check(
    "d9 shutdown 后 loop 线程退出且无清理错误",
    not shutdown_errors and client._loop_thread is None and client._async_loop is None,
    "; ".join(shutdown_errors),
)


# ─── e. HTTP 模式真实启动/认证/关停 ─────────────────────────────
import httpx

http_server = MCPHostServer(
    name="smoke-http",
    host="127.0.0.1",
    port=8878,
    auth_token="secret-token",
    allowed_hosts=["127.0.0.1", "localhost"],
    max_requests_per_minute=None,
)
http_server.add_tool(
    name="p__t", description="t",
    parameters={"type": "object", "properties": {}},
    plugin_id="p", method_name="t",
)
http_server.run_http()
check("e1 HTTP Server 真实启动", http_server.is_running)
try:
    r = httpx.post("http://127.0.0.1:8878/mcp", json={"jsonrpc": "2.0", "id": 1},
                   timeout=5.0)
    check("e2 无 token 请求被 401 拒绝", r.status_code == 401, str(r.status_code))
    auth_headers = {
        "Authorization": "Bearer secret-token",
        "Accept": "application/json, text/event-stream",
    }
    r2 = httpx.post(
        "http://127.0.0.1:8878/mcp",
        headers=auth_headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=5.0,
    )
    check("e3 带 token 请求通过认证(非 401)", r2.status_code != 401, str(r2.status_code))
    r3 = httpx.post(
        "http://127.0.0.1:8878/mcp",
        headers={**auth_headers, "Host": "evil.example"},
        json={"jsonrpc": "2.0", "id": 1},
        timeout=5.0,
    )
    check("e4 非白名单 Host 被 403 拒绝", r3.status_code == 403, str(r3.status_code))
    try:
        MCPHostServer(host="0.0.0.0", port=8879).run_http()
    except ValueError as exc:
        check("e5 非回环无认证直接拒绝启动", "非回环" in str(exc), str(exc))
    else:
        check("e5 非回环无认证直接拒绝启动", False, "未抛出 ValueError")
    http_cfg = MCPRemoteServerConfig(
        server_id="smoke.http.server",
        name="Smoke HTTP",
        transport="streamable-http",
        url="http://127.0.0.1:8878/mcp",
        auth_token="secret-token",
    )
    with patch.object(PluginManager, "call_plugin_method", return_value="http-ok"):
        http_failures = run_reconnect_cycles(
            client, http_cfg, registry, expected_text="http-ok", with_text=False
        )
    check(
        "e6 100 次真实 HTTP 连接/调用/断开无泄漏",
        not http_failures,
        "; ".join(http_failures[:3]),
    )
finally:
    shutdown_errors = client.shutdown()
    http_server.stop()
check(
    "e7 stop() 真正关停且客户端无清理错误",
    not shutdown_errors
    and not http_server.is_running
    and (http_server._thread is None or not http_server._thread.is_alive()),
    "; ".join(shutdown_errors),
)
# 关停后端口应不可用（优雅关停可能有短暂延迟，轮询最多 4 秒）
port_closed = False
for _ in range(20):
    try:
        httpx.get("http://127.0.0.1:8878/mcp", timeout=1.0)
        time.sleep(0.2)
    except Exception:
        port_closed = True
        break
check("e8 关停后端口已释放", port_closed)

stderr_guard.flush()
sys.stderr = stderr_guard._stream
cleanup_warnings = stderr_guard.warning_text()
check("f1 无 cancel scope/未关闭资源/遗留任务警告", not cleanup_warnings, cleanup_warnings)

print()
failed = [r for r in results if not r[1]]
print(f"=== {len(results) - len(failed)}/{len(results)} 冒烟项通过 ===")
sys.exit(1 if failed else 0)
