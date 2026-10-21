"""GitHub 私有仓库访问子系统的领域异常。"""


class GitHubError(Exception):
    """GitHub 子系统基础异常。

    异常消息禁止包含 PAT 明文或 Authorization 请求头。
    """


class GitHubKeyNotFoundError(GitHubError):
    """指定 Key ID 在本地配置中不存在。"""


class GitHubKeyInvalidError(GitHubError):
    """Key 已失效、被撤销或无法通过 GitHub 身份验证。"""


class GitHubRepositoryAccessError(GitHubError):
    """当前 Key 无法访问目标仓库，或仓库不存在。"""

    def __init__(
        self,
        message: str,
        *,
        authenticated: bool = False,
        status_code: int = 0,
    ):
        """初始化仓库访问异常。

        Args:
            message: 面向开发者的脱敏错误说明。
            authenticated: 请求是否携带了已解析的 GitHub 凭据。
            status_code: GitHub HTTP 状态码；非 HTTP 错误时为零。
        """
        super().__init__(message)
        self.authenticated = authenticated
        self.status_code = status_code


class GitHubRateLimitError(GitHubError):
    """GitHub API 请求达到频率限制。"""

    def __init__(self, message: str, *, reset_at: str = ""):
        """初始化限流异常。

        Args:
            message: 面向开发者的脱敏错误说明。
            reset_at: GitHub 返回的限流重置时间，无法获取时为空串。
        """
        super().__init__(message)
        self.reset_at = reset_at


class GitHubNetworkError(GitHubError):
    """GitHub 请求发生超时或网络错误。"""


class GitHubCredentialVaultError(GitHubError):
    """凭据加密、解密或安全存储失败。"""
