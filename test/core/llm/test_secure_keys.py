"""pytest tests for core.llm.secure_keys."""
import base64

import pytest

from core.llm.secure_keys import (
    ENCODED_PREFIX,
    decode_secret,
    encode_secret,
)


class TestEncodeSecret:
    """Tests for encode_secret()."""

    def test_encode_plain_value(self):
        """普通字符串应编码为 b64:<base64> 形式。"""
        assert encode_secret("xyz") == "b64:eHl6"

    def test_encode_unicode_value(self):
        """Unicode 字符串应正确编码。"""
        plain = "中文密钥"
        encoded = encode_secret(plain)
        assert encoded.startswith(ENCODED_PREFIX)
        assert base64.b64decode(encoded[len(ENCODED_PREFIX):]).decode("utf-8") == plain

    def test_encode_empty_string_returns_empty(self):
        """空字符串应保持为空，不添加前缀。"""
        assert encode_secret("") == ""

    def test_encode_none_returns_none(self):
        """传入 None 时按空值处理，返回 None。"""
        assert encode_secret(None) is None


class TestDecodeSecret:
    """Tests for decode_secret()."""

    def test_decode_b64_prefixed_value(self):
        """b64: 前缀的值应解码为明文。"""
        assert decode_secret("b64:eHl6") == "xyz"

    def test_decode_plain_value_backward_compatible(self):
        """无前缀的旧明文配置应原样返回。"""
        assert decode_secret("plain-old-key") == "plain-old-key"

    def test_decode_empty_string(self):
        """空字符串应原样返回。"""
        assert decode_secret("") == ""

    def test_decode_invalid_base64_returns_raw(self):
        """非法 Base64 解码失败时按原文返回。"""
        invalid = "b64:not-base64!!!"
        assert decode_secret(invalid) == invalid

    def test_decode_none_returns_none(self):
        """传入 None 时原样返回 None（startswith 短路）。"""
        assert decode_secret(None) is None


class TestRoundTrip:
    """Tests for encode/decode round-trip."""

    @pytest.mark.parametrize("plain", ["xyz", "中文", "special!@#$%", "a" * 1024])
    def test_round_trip(self, plain):
        """任意明文先编码再解码应等于原值。"""
        assert decode_secret(encode_secret(plain)) == plain
