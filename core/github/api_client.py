"""GitHub REST API 访问客户端。"""

import base64
import json
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote

import requests

from .credential import (
    GitHubAuthIdentity,
    GitHubCredential,
    GitHubExpirationSource,
    GitHubRepositoryInfo,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
)
from .exceptions import (
    GitHubKeyInvalidError,
    GitHubNetworkError,
    GitHubRateLimitError,
    GitHubRepositoryAccessError,
)

GITHUB_API_BASE_URL = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
GITHUB_USER_AGENT = "InstructionX"
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_DOWNLOAD_TIMEOUT = 60
RELEASES_PER_PAGE = 30
MAX_RELEASE_PAGES = 10
FINE_GRAINED_TOKEN_PREFIX = "github_pat_"
CLASSIC_TOKEN_PREFIXES = ("ghp_", "gho_", "ghu_", "ghs_", "ghr_")
RATE_LIMIT_STATUS_CODES = (403, 429)


class GitHubApiClient:
    """提供 GitHub 鉴权、仓库元数据、内容和归档下载能力。

    生产构造使用固定 ``https://api.github.com``。测试可注入 Session
    和同协议测试基址，但 Authorization 仍只由本类构造。
    """

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        api_base_url: str = GITHUB_API_BASE_URL,
    ):
        """初始化 GitHub API 客户端。

        Args:
            session: 可选 requests Session，便于复用连接和测试。
            api_base_url: GitHub REST API 基础地址。
        """
        self._session = session or requests.Session()
        self._api_base_url = api_base_url.rstrip("/")

    def get_authenticated_user(
        self, credential: GitHubCredential
    ) -> GitHubAuthIdentity:
        """验证 Token 并返回账号、类型和可选过期信息。

        Args:
            credential: 内存中的 GitHub 凭据。

        Returns:
            GitHubAuthIdentity: 验证后的 GitHub 身份信息。

        Raises:
            GitHubKeyInvalidError: Token 无效或已过期。
            GitHubRateLimitError: GitHub API 达到限流。
            GitHubNetworkError: 网络请求失败。
        """
        response = self._request("GET", "/user", credential, timeout=DEFAULT_REQUEST_TIMEOUT)
        data = self._parse_json(response)
        login = str(data.get("login", "")).strip()
        if not login:
            raise GitHubKeyInvalidError("GitHub 用户响应缺少账号信息")
        expiration = response.headers.get("github-authentication-token-expiration")
        scopes = self._parse_scopes(response.headers.get("X-OAuth-Scopes", ""))
        return GitHubAuthIdentity(
            account_login=login,
            token_kind=self._detect_token_kind(credential.token),
            expires_at=expiration or None,
            expiration_source=(
                GitHubExpirationSource.GITHUB_HEADER
                if expiration else GitHubExpirationSource.UNAVAILABLE
            ),
            oauth_scopes=scopes,
        )

    def get_repository(
        self,
        owner: str,
        repo: str,
        credential: Optional[GitHubCredential] = None,
    ) -> GitHubRepositoryInfo:
        """获取仓库元数据并判定访问状态。

        Args:
            owner: GitHub 仓库所属账号或组织。
            repo: 仓库名称。
            credential: 可选凭据；None 表示匿名请求。

        Returns:
            GitHubRepositoryInfo: 仓库可见性、默认分支和权限信息。

        Raises:
            GitHubRepositoryAccessError: 无权限或仓库不存在。
        """
        path = f"/repos/{self._segment(owner)}/{self._segment(repo)}"
        response = self._request(
            "GET", path, credential, timeout=DEFAULT_REQUEST_TIMEOUT)
        data = self._parse_json(response)
        return self._repository_from_json(
            owner, repo, data, response, credential)

    def get_file_json(
        self,
        owner: str,
        repo: str,
        file_path: str,
        ref: str = "",
        credential: Optional[GitHubCredential] = None,
    ) -> Optional[Dict[str, Any]]:
        """通过 Contents API 获取并解析 JSON 文件。"""
        path = self._contents_path(owner, repo, file_path)
        params = {"ref": ref} if ref else None
        response = self._request(
            "GET", path, credential, params=params,
            timeout=DEFAULT_REQUEST_TIMEOUT)
        data = self._parse_json(response)
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            return None
        content = str(data.get("content", "")).replace("\n", "")
        try:
            decoded = base64.b64decode(content, validate=True).decode("utf-8")
            parsed = json.loads(decoded)
        except (ValueError, UnicodeDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    def get_directory_contents(
        self,
        owner: str,
        repo: str,
        directory_path: str = "",
        credential: Optional[GitHubCredential] = None,
    ) -> list[Dict[str, Any]]:
        """通过 Contents API 获取目录内容。"""
        path = self._contents_path(owner, repo, directory_path)
        response = self._request(
            "GET", path, credential, timeout=DEFAULT_REQUEST_TIMEOUT)
        data = self._parse_json(response)
        return data if isinstance(data, list) else []

    def list_releases(
        self,
        owner: str,
        repo: str,
        credential: Optional[GitHubCredential] = None,
    ) -> list[Dict[str, Any]]:
        """分页获取仓库 Release 列表。"""
        path = f"/repos/{self._segment(owner)}/{self._segment(repo)}/releases"
        releases: list[Dict[str, Any]] = []
        for page in range(1, MAX_RELEASE_PAGES + 1):
            response = self._request(
                "GET", path, credential,
                params={"per_page": RELEASES_PER_PAGE, "page": page},
                timeout=DEFAULT_REQUEST_TIMEOUT)
            page_items = self._parse_json(response)
            if not isinstance(page_items, list):
                break
            releases.extend(item for item in page_items if isinstance(item, dict))
            if len(page_items) < RELEASES_PER_PAGE:
                break
        return releases

    def stream_zipball(
        self,
        owner: str,
        repo: str,
        ref: str,
        credential: Optional[GitHubCredential] = None,
    ) -> requests.Response:
        """打开仓库 zipball 流，由调用方负责关闭响应。"""
        path = (
            f"/repos/{self._segment(owner)}/{self._segment(repo)}"
            f"/zipball/{quote(ref, safe='')}"
        )
        return self._request(
            "GET", path, credential, stream=True,
            timeout=DEFAULT_DOWNLOAD_TIMEOUT, allow_not_found=True)

    def _request(self, method: str, path: str, credential, **kwargs):
        """发送请求并集中映射 GitHub HTTP 错误。"""
        url = self._api_base_url + path
        allow_not_found = bool(kwargs.pop("allow_not_found", False))
        try:
            response = self._session.request(
                method, url, headers=self._build_headers(credential), **kwargs)
        except requests.Timeout as exc:
            raise GitHubNetworkError("GitHub 请求超时") from exc
        except requests.RequestException as exc:
            raise GitHubNetworkError("GitHub 网络请求失败") from exc
        self._raise_for_status(
            response,
            authenticated=credential is not None,
            allow_not_found=allow_not_found,
        )
        return response

    @staticmethod
    def _build_headers(credential) -> Dict[str, str]:
        """构造不包含日志副作用的 GitHub 请求头。"""
        headers = {
            "Accept": GITHUB_ACCEPT_HEADER,
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
            "User-Agent": GITHUB_USER_AGENT,
        }
        if credential is not None:
            headers["Authorization"] = f"Bearer {credential.token}"
        return headers

    @staticmethod
    def _raise_for_status(
        response, *, authenticated: bool, allow_not_found: bool = False
    ) -> None:
        """把 HTTP 状态转换为领域异常并关闭失败流。"""
        if response.status_code == 401:
            GitHubApiClient._raise_invalid(response)
        if response.status_code == 404:
            if allow_not_found:
                return
            GitHubApiClient._raise_not_found(response, authenticated)
        GitHubApiClient._raise_forbidden_or_rate(response, authenticated)
        if response.status_code >= 400:
            response.close()
            raise GitHubRepositoryAccessError(
                f"GitHub API 请求失败: HTTP {response.status_code}",
                authenticated=authenticated,
                status_code=response.status_code,
            )

    @staticmethod
    def _raise_invalid(response) -> None:
        """关闭响应并抛出 Key 无效异常。"""
        response.close()
        raise GitHubKeyInvalidError("GitHub Key 无效、已过期或已撤销")

    @staticmethod
    def _raise_not_found(response, authenticated: bool) -> None:
        """关闭响应并按认证状态说明 404 语义。"""
        response.close()
        message = (
            "当前 GitHub Key 无权访问该仓库，或仓库不存在"
            if authenticated else
            "仓库可能为私有或不存在；请选择有权限的 GitHub Key"
        )
        raise GitHubRepositoryAccessError(
            message,
            authenticated=authenticated,
            status_code=response.status_code,
        )

    @staticmethod
    def _raise_forbidden_or_rate(response, authenticated: bool) -> None:
        """区分限流、SSO/权限和普通错误。"""
        remaining = response.headers.get("X-RateLimit-Remaining", "")
        rate_limited = (
            response.status_code == 429
            or (
                response.status_code == 403
                and remaining == "0"
            )
        )
        if rate_limited:
            reset_at = response.headers.get("X-RateLimit-Reset", "")
            response.close()
            raise GitHubRateLimitError("GitHub API 请求达到频率限制", reset_at=reset_at)
        if response.status_code == 403:
            response.close()
            raise GitHubRepositoryAccessError(
                "GitHub 权限不足；组织仓库可能需要完成 SSO 授权",
                authenticated=authenticated,
                status_code=response.status_code,
            )

    @staticmethod
    def _parse_json(response) -> Any:
        """解析响应 JSON，失败时抛出明确网络层错误。"""
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            response.close()
            raise GitHubNetworkError("GitHub API 返回了无效 JSON") from exc

    @staticmethod
    def _repository_from_json(owner, repo, data, response, credential):
        """从仓库响应构造仓库模型。"""
        if not isinstance(data, dict):
            raise GitHubNetworkError("GitHub 仓库响应结构无效")
        visibility = (
            GitHubRepositoryVisibility.PRIVATE
            if bool(data.get("private"))
            else GitHubRepositoryVisibility.PUBLIC
        )
        permissions = data.get("permissions")
        permission_map = permissions if isinstance(permissions, dict) else {}
        return GitHubRepositoryInfo(
            owner=owner,
            repo=repo,
            visibility=visibility,
            default_branch=str(data.get("default_branch", "")),
            can_pull=bool(permission_map.get("pull", True)),
            auth_key_id=credential.key_id if credential else "",
            auth_key_name=credential.key_name if credential else "",
            auth_account_login=credential.account_login if credential else "",
            raw_permissions=permission_map or None,
        )

    @staticmethod
    def _parse_scopes(raw: str) -> tuple[str, ...]:
        """解析经典 PAT scope 请求头。"""
        return tuple(item.strip() for item in raw.split(",") if item.strip())

    @staticmethod
    def _detect_token_kind(token: str) -> GitHubTokenKind:
        """根据 GitHub Token 前缀做最佳努力分类。"""
        if token.startswith(FINE_GRAINED_TOKEN_PREFIX):
            return GitHubTokenKind.FINE_GRAINED
        if token.startswith(CLASSIC_TOKEN_PREFIXES):
            return GitHubTokenKind.CLASSIC
        return GitHubTokenKind.UNKNOWN

    @staticmethod
    def _segment(value: str) -> str:
        """安全编码 URL 路径段。"""
        return quote(value, safe="")

    @classmethod
    def _contents_path(cls, owner: str, repo: str, file_path: str) -> str:
        """构造 Contents API 路径。"""
        suffix = f"/{quote(file_path.lstrip('/'), safe='/')}" if file_path else ""
        return f"/repos/{cls._segment(owner)}/{cls._segment(repo)}/contents{suffix}"
