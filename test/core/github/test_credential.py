"""GitHub 凭据与仓库模型单元测试。"""

from core.github import (
    GitHubCredential,
    GitHubExpirationSource,
    GitHubKeyStatus,
    GitHubRepositoryVisibility,
    GitHubTokenKind,
)


class TestCredentialModels:
    """验证敏感字段不会进入模型展示或调试表示。"""

    def test_credential_repr_redacts_token(self):
        """凭据 repr 不得包含 Token。"""
        credential = GitHubCredential(
            key_id="key-id",
            key_name="工作账号",
            token="secret-token",
            account_login="octocat",
        )

        text = repr(credential)

        assert "secret-token" not in text
        assert "key-id" in text
        assert "工作账号" in text

    def test_enum_string_values_are_stable(self):
        """持久化枚举值必须保持稳定字符串。"""
        assert GitHubTokenKind.FINE_GRAINED.value == "fine_grained"
        assert GitHubKeyStatus.INVALID.value == "invalid"
        assert GitHubRepositoryVisibility.PRIVATE.value == "private"
        assert GitHubExpirationSource.UNAVAILABLE.value == "unavailable"
