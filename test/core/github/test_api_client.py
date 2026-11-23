"""GitHubApiClient 请求构造与状态映射测试。"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests

from core.github import (
    GitHubApiClient,
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyInvalidError,
    GitHubNetworkError,
    GitHubRateLimitError,
    GitHubRepositoryAccessError,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
)


def _credential(token: str = "github_pat_test") -> GitHubCredential:
    """创建测试凭据。"""
    return GitHubCredential("key-id", "工作账号", token, "octocat")


class TestAuthentication:
    """验证 Token 身份与请求头。"""

    def test_identity_parses_account_expiration_and_scopes(
        self, api_client, fake_response
    ):
        """身份响应应解析账号、过期头和经典 scope。"""
        client, session = api_client
        session.request.return_value = fake_response(
            payload={"login": "octocat"},
            headers={
                "github-authentication-token-expiration": "2026-12-01",
                "X-OAuth-Scopes": "repo, read:org",
            },
        )

        identity = client.get_authenticated_user(_credential("ghp_classic"))

        assert identity.account_login == "octocat"
        assert identity.token_kind == GitHubTokenKind.CLASSIC
        assert identity.expires_at == "2026-12-01"
        assert identity.expiration_source == GitHubExpirationSource.GITHUB_HEADER
        assert identity.oauth_scopes == ("repo", "read:org")

    def test_identity_without_login_is_invalid(self, api_client, fake_response):
        """用户响应缺少登录名时必须拒绝。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={})

        with pytest.raises(GitHubKeyInvalidError, match="账号"):
            client.get_authenticated_user(_credential())

    def test_missing_expiration_is_explicitly_unavailable(
        self, api_client, fake_response
    ):
        """GitHub 未返回过期头时不得推测时间。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={"login": "user"})

        identity = client.get_authenticated_user(_credential())

        assert identity.expires_at is None
        assert (
            identity.expiration_source
            is GitHubExpirationSource.UNAVAILABLE
        )

    def test_authorization_header_uses_bearer(self, api_client, fake_response):
        """PAT 必须通过 Bearer Authorization 发送。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={"login": "user"})

        client.get_authenticated_user(_credential("secret-token"))

        headers = session.request.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer secret-token"

    def test_anonymous_request_has_no_authorization(
        self, api_client, fake_response
    ):
        """匿名请求不得包含 Authorization。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={})

        client.get_repository("owner", "repo")

        headers = session.request.call_args.kwargs["headers"]
        assert "Authorization" not in headers


class TestRepositoryStatus:
    """验证公共、私有和错误状态映射。"""

    def test_private_repository_is_detected(self, api_client, fake_response):
        """认证后的 private=true 必须映射为私有。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={
            "private": True,
            "visibility": "private",
            "default_branch": "main",
            "permissions": {"pull": True},
        })

        repository = client.get_repository("owner", "repo", _credential())

        assert repository.visibility is GitHubRepositoryVisibility.PRIVATE
        assert repository.default_branch == "main"
        assert repository.can_pull is True
        assert repository.auth_key_id == "key-id"

    def test_public_repository_is_detected(self, api_client, fake_response):
        """private=false 必须映射为公共。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={"private": False})

        repository = client.get_repository("owner", "repo")

        assert repository.visibility is GitHubRepositoryVisibility.PUBLIC

    def test_unauthenticated_404_requests_key(self, api_client, fake_response):
        """匿名 404 必须提示选择 Key，而不是武断标为私有。"""
        client, session = api_client
        session.request.return_value = fake_response(status_code=404)

        with pytest.raises(GitHubRepositoryAccessError) as exc_info:
            client.get_repository("owner", "repo")

        assert exc_info.value.authenticated is False
        assert "选择" in str(exc_info.value)
        session.request.return_value.close.assert_called_once()

    def test_authenticated_404_reports_no_permission(
        self, api_client, fake_response
    ):
        """认证后 404 必须提示 Key 无权限或仓库不存在。"""
        client, session = api_client
        session.request.return_value = fake_response(status_code=404)

        with pytest.raises(GitHubRepositoryAccessError) as exc_info:
            client.get_repository("owner", "repo", _credential())

        assert exc_info.value.authenticated is True
        assert "无权访问" in str(exc_info.value)

    def test_401_marks_key_invalid(self, api_client, fake_response):
        """401 必须映射为 Key 无效。"""
        client, session = api_client
        session.request.return_value = fake_response(status_code=401)

        with pytest.raises(GitHubKeyInvalidError):
            client.get_repository("owner", "repo", _credential())

    def test_rate_limit_requires_exhausted_header(
        self, api_client, fake_response
    ):
        """403 仅在剩余配额为零时映射为限流。"""
        client, session = api_client
        session.request.return_value = fake_response(
            status_code=403,
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"},
        )

        with pytest.raises(GitHubRateLimitError) as exc_info:
            client.get_repository("owner", "repo")

        assert exc_info.value.reset_at == "123"

    def test_403_permission_error_is_not_rate_limit(
        self, api_client, fake_response
    ):
        """普通 403 必须提示权限或 SSO，而不是限流。"""
        client, session = api_client
        session.request.return_value = fake_response(
            status_code=403,
            headers={"X-RateLimit-Remaining": "42"},
        )

        with pytest.raises(GitHubRepositoryAccessError, match="SSO"):
            client.get_repository("owner", "repo", _credential())

    def test_429_is_rate_limited(self, api_client, fake_response):
        """HTTP 429 无论剩余头如何都按限流处理。"""
        client, session = api_client
        session.request.return_value = fake_response(status_code=429)

        with pytest.raises(GitHubRateLimitError):
            client.get_repository("owner", "repo")

    def test_invalid_repository_payload_is_rejected(
        self, api_client, fake_response
    ):
        """仓库响应不是对象时返回网络协议错误。"""
        client, session = api_client
        session.request.return_value = fake_response(payload=[])

        with pytest.raises(GitHubNetworkError, match="结构"):
            client.get_repository("owner", "repo")


class TestContentAndDownload:
    """验证 Contents、Release 和 zipball 行为。"""

    def test_file_json_is_base64_decoded(self, api_client, fake_response):
        """JSON 文件内容应正确解码。"""
        client, session = api_client
        raw = json.dumps({"id": "plugin"}).encode()
        session.request.return_value = fake_response(payload={
            "encoding": "base64",
            "content": base64.b64encode(raw).decode(),
        })

        result = client.get_file_json("owner", "repo", "IXPlugin.json")

        assert result == {"id": "plugin"}

    def test_non_base64_file_returns_none(self, api_client, fake_response):
        """非 Base64 Contents 响应不应抛出未处理异常。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={"content": "x"})

        assert client.get_file_json("owner", "repo", "IXPlugin.json") is None

    def test_corrupt_base64_file_returns_none(
        self, api_client, fake_response
    ):
        """损坏 Base64 内容应返回 None。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={
            "encoding": "base64",
            "content": "not-valid!",
        })

        assert client.get_file_json("owner", "repo", "IXPlugin.json") is None

    def test_directory_contents_returns_list(self, api_client, fake_response):
        """目录接口返回列表。"""
        client, session = api_client
        session.request.return_value = fake_response(payload=[{"name": "x"}])

        assert client.get_directory_contents("owner", "repo", "dir") == [
            {"name": "x"},
        ]

    def test_directory_non_list_returns_empty(
        self, api_client, fake_response
    ):
        """目录接口非列表响应安全回退为空。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={})

        assert client.get_directory_contents("owner", "repo", "dir") == []

    def test_release_pagination_stops_on_short_page(
        self, api_client, fake_response
    ):
        """Release 分页应在短页停止。"""
        from core.github.api_client import RELEASES_PER_PAGE

        client, session = api_client
        first_page = [{"tag_name": str(i)} for i in range(RELEASES_PER_PAGE)]
        session.request.side_effect = [
            fake_response(payload=first_page),
            fake_response(payload=[{"tag_name": "last"}]),
        ]

        releases = client.list_releases("owner", "repo")

        assert len(releases) == RELEASES_PER_PAGE + 1
        assert session.request.call_count == 2

    def test_release_non_list_page_stops(self, api_client, fake_response):
        """分页响应非列表时停止。"""
        client, session = api_client
        session.request.return_value = fake_response(payload={})

        assert client.list_releases("owner", "repo") == []

    def test_zipball_uses_api_and_stream(self, api_client, fake_response):
        """zipball 必须走 API 并保持流式响应。"""
        client, session = api_client
        response = fake_response(payload=b"zip")
        session.request.return_value = response

        result = client.stream_zipball("owner", "repo", "release/1.0", _credential())

        assert result is response
        args, kwargs = session.request.call_args
        assert args[1].endswith("/zipball/release%2F1.0")
        assert kwargs["stream"] is True

    def test_timeout_becomes_network_error(self, api_client):
        """requests 超时必须转为领域网络错误。"""
        client, session = api_client
        session.request.side_effect = requests.Timeout()

        with pytest.raises(GitHubNetworkError, match="超时"):
            client.get_repository("owner", "repo")

    def test_request_exception_becomes_network_error(self, api_client):
        """其他 requests 异常转为领域网络错误。"""
        client, session = api_client
        session.request.side_effect = requests.ConnectionError()

        with pytest.raises(GitHubNetworkError, match="网络"):
            client.get_repository("owner", "repo")

    def test_invalid_json_becomes_network_error(
        self, api_client, fake_response
    ):
        """无效 JSON 必须转为领域网络错误。"""
        client, session = api_client
        response = fake_response()
        response.json.side_effect = ValueError("bad json")
        session.request.return_value = response

        with pytest.raises(GitHubNetworkError, match="JSON"):
            client.get_repository("owner", "repo")

    @pytest.mark.integration
    def test_cross_host_redirect_drops_authorization(self):
        """跨主机重定向不得继续发送 Authorization。"""
        captured = {}

        class TargetHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                captured["authorization"] = self.headers.get("Authorization")
                body = b'{"private": true, "default_branch": "main"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
        target_url = f"http://127.0.0.1:{target.server_port}/repo"

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header("Location", target_url)
                self.end_headers()

            def log_message(self, *_args):
                return

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        threads = [
            threading.Thread(target=server.serve_forever, daemon=True)
            for server in (target, redirect)
        ]
        for thread in threads:
            thread.start()
        try:
            client = GitHubApiClient(
                api_base_url=(
                    f"http://127.0.0.1:{redirect.server_port}"))
            client.get_repository("owner", "repo", _credential("secret"))
        finally:
            redirect.shutdown()
            target.shutdown()
            redirect.server_close()
            target.server_close()

        assert captured["authorization"] is None
