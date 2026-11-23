"""MCP Server 暴露边界、Host、TLS 与凭据配置测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from core.github.secret_vault import DPAPI_PREFIX, DpapiSecretVault
from core.mcp.config import MCPConfig, MCPServerConfig
from core.mcp.manager import MCPManager
from core.mcp.server import (
    MCPHostServer,
    ServerSecurityPolicy,
    _HostValidationMiddleware,
    _RateLimitMiddleware,
)


def _scope(host="example.com:8765", client=("127.0.0.1", 1234)):
    return {
        "type": "http",
        "client": client,
        "headers": [(b"host", host.encode("ascii"))],
    }


async def _downstream(scope, receive, send):
    scope["downstream_called"] = True


async def _exercise(app, scope):
    messages = []

    async def send(message):
        messages.append(message)

    await app(scope, None, send)
    called = [scope["type"]] if scope.get("downstream_called") else []
    return messages, called


def test_non_loopback_without_token_is_rejected():
    """非回环 HTTP 无 token 必须拒绝启动，不能仅警告后暴露。"""
    config = MCPServerConfig(host="0.0.0.0", transport="streamable-http", auth_token=None)
    with pytest.raises(ValueError, match="非回环"):
        ServerSecurityPolicy.validate(config)


def test_non_loopback_with_token_and_tls_is_allowed():
    """非回环具备 token 和完整 TLS 配置时允许启动。"""
    config = MCPServerConfig(
        host="0.0.0.0", transport="streamable-http", auth_token="secret",
        tls_certfile="cert.pem", tls_keyfile="key.pem",
    )
    ServerSecurityPolicy.validate(config)


def test_tls_requires_cert_and_key_pair():
    """TLS 证书和私钥必须成对配置。"""
    config = MCPServerConfig(
        host="127.0.0.1", transport="streamable-http", tls_certfile="cert.pem"
    )
    with pytest.raises(ValueError, match="tls_certfile 与 tls_keyfile"):
        ServerSecurityPolicy.validate(config)


def test_host_validation_rejects_unlisted_host_with_403():
    """配置 allowed_hosts 后，不匹配的 Host 头必须返回 403。"""
    app = _HostValidationMiddleware(_downstream, ["localhost"])
    messages, called = asyncio.run(_exercise(app, _scope("evil.example")))
    assert messages[0]["status"] == 403
    assert called == []


@pytest.mark.parametrize("host", ["example.com:8765", "EXAMPLE.COM.", "[::1]:8765"])
def test_host_validation_allows_listed_host(host):
    """白名单匹配忽略大小写、末尾点和端口，并支持 IPv6。"""
    allowed = ["::1"] if host.startswith("[") else ["example.com"]
    app = _HostValidationMiddleware(_downstream, allowed)
    _, called = asyncio.run(_exercise(app, _scope(host)))
    assert called == ["http"]


def test_rate_limit_rejects_excess_requests_without_blocking_other_clients():
    """超过窗口上限返回 429，其他客户端不受牵连。"""
    app = _RateLimitMiddleware(_downstream, 2)
    assert asyncio.run(_exercise(app, _scope()))[1] == ["http"]
    assert asyncio.run(_exercise(app, _scope()))[1] == ["http"]
    messages, called = asyncio.run(_exercise(app, _scope()))
    assert messages[0]["status"] == 429
    assert called == []
    _, other_called = asyncio.run(_exercise(app, _scope(client=("127.0.0.2", 1234))))
    assert other_called == ["http"]


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_invalid_rate_limit_is_rejected(value):
    """限流配置必须为正整数或显式 None。"""
    with pytest.raises(ValueError, match="max_requests_per_minute"):
        MCPHostServer(max_requests_per_minute=value)


def test_stop_does_not_report_success_when_thread_is_alive():
    """服务器线程未退出时必须保留运行状态并报告失败。"""

    class StuckThread:
        def is_alive(self):
            return True

        def join(self, timeout):
            return None

    server = MCPHostServer()
    server._running = True
    server._thread = StuckThread()
    with pytest.raises(RuntimeError, match="不能报告停止成功"):
        server.stop()
    assert server.is_running


def test_auth_token_uses_dpapi_and_legacy_base64_still_reads():
    """新配置使用真实 DPAPI，旧 Base64 配置仍能读取。"""
    config = MCPServerConfig(auth_token="secret-token")
    data = config.to_dict()
    assert data["auth_token"].startswith(DPAPI_PREFIX)
    assert "secret-token" not in data["auth_token"]
    restored = MCPServerConfig.from_dict(data)
    assert restored.auth_token == "secret-token"
    assert DpapiSecretVault().decrypt(data["auth_token"]) == "secret-token"
    legacy = MCPServerConfig.from_dict({"auth_token": "b64:c2VjcmV0LXRva2Vu"})
    assert legacy.auth_token == "secret-token"



def test_empty_schema_tool_does_not_require_kwargs():
    """无参数工具必须生成空签名，不能把 **kwargs 当成必填字段。"""
    server = MCPHostServer()
    handler = server._create_tool_handler(
        "p__t", "p", "t", {"type": "object", "properties": {}}
    )
    assert list(handler.__signature__.parameters) == []



def test_fastmcp_import_failure_is_retried_at_startup(monkeypatch):
    """暂时缺少 SDK 的模块状态不得永久污染后续真实启动。"""

    class FakeFastMCP:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs

    modules = {
        "mcp.server.fastmcp": SimpleNamespace(FastMCP=FakeFastMCP),
        "mcp.server.fastmcp.tools": SimpleNamespace(Tool=object),
    }
    monkeypatch.setattr("core.mcp.server.FastMCP", None)
    monkeypatch.setattr("core.mcp.server.Tool", None)
    monkeypatch.setattr("core.mcp.server._MCP_IMPORT_ERROR", ImportError("暂时缺失"))
    monkeypatch.setattr(
        "core.mcp.server.importlib.import_module", lambda name: modules[name]
    )
    server = MCPHostServer()
    fastmcp = server._init_fastmcp()
    assert isinstance(fastmcp, FakeFastMCP)



def test_server_url_uses_https_when_tls_is_configured():
    """TLS 服务地址必须返回 HTTPS，避免客户端使用错误协议。"""
    manager = MCPManager.__new__(MCPManager)
    manager._server = object()
    manager._config = MCPConfig(
        server=MCPServerConfig(
            host="127.0.0.1",
            port=8765,
            tls_certfile="cert.pem",
            tls_keyfile="key.pem",
        )
    )
    assert manager.get_server_url() == "https://127.0.0.1:8765"
