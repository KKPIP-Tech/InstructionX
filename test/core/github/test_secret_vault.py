"""SecretVault 加密后端单元测试。"""

import os

import pytest

from core.github import (
    DpapiSecretVault,
    GitHubCredentialVaultError,
    InMemorySecretVault,
)


class TestInMemorySecretVault:
    """验证测试凭据后端及通用错误边界。"""

    def test_round_trip_returns_plaintext(self):
        """内存后端应正确往返 Token。"""
        vault = InMemorySecretVault()

        encrypted = vault.encrypt("github-token")

        assert encrypted != "github-token"
        assert vault.decrypt(encrypted) == "github-token"

    def test_empty_token_is_rejected(self):
        """空 Token 必须拒绝。"""
        vault = InMemorySecretVault()

        with pytest.raises(GitHubCredentialVaultError):
            vault.encrypt("")

    def test_unknown_ciphertext_is_rejected(self):
        """不存在的测试密文必须拒绝。"""
        vault = InMemorySecretVault()

        with pytest.raises(GitHubCredentialVaultError):
            vault.decrypt("memory:v1:missing")


class TestDpapiSecretVault:
    """验证 Windows DPAPI 的真实加密往返。"""

    def test_round_trip_and_no_plaintext(self):
        """DPAPI 密文不得包含明文且可恢复。"""
        if os.name != "nt":
            pytest.skip("DPAPI 仅支持 Windows")
        vault = DpapiSecretVault()
        token = "github_pat_dpapi_test"

        encrypted = vault.encrypt(token)

        assert encrypted.startswith("dpapi:v1:")
        assert token not in encrypted
        assert vault.decrypt(encrypted) == token

    def test_invalid_prefix_is_rejected(self):
        """非法前缀不得进入 DPAPI。"""
        vault = DpapiSecretVault()

        with pytest.raises(GitHubCredentialVaultError):
            vault.decrypt("b64:invalid")

    def test_invalid_base64_is_rejected(self):
        """损坏 Base64 必须转换为领域异常。"""
        vault = DpapiSecretVault()

        with pytest.raises(GitHubCredentialVaultError):
            vault.decrypt("dpapi:v1:not-base64!")
