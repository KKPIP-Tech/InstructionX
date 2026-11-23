"""pytest tests for core/llm/exceptions.py exception hierarchy."""

import pytest

from core.llm.exceptions import (
    LLMException,
    ConfigurationError,
    AuthenticationError,
    APIError,
    RateLimitError,
    InvalidRequestError,
    ModelNotSupportedError,
    ConnectionError,
    TimeoutError,
    StreamingError,
)


class TestExceptionInheritance:
    """Test that all 9 exception classes inherit from LLMException."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ConfigurationError,
            AuthenticationError,
            APIError,
            RateLimitError,
            InvalidRequestError,
            ModelNotSupportedError,
            ConnectionError,
            TimeoutError,
            StreamingError,
        ],
    )
    def test_all_exceptions_inherit_from_llm_exception(self, exc_class):
        assert issubclass(exc_class, LLMException)

    def test_rate_limit_error_inherits_from_api_error(self):
        assert issubclass(RateLimitError, APIError)

    def test_api_error_inherits_from_llm_exception(self):
        assert issubclass(APIError, LLMException)


class TestAPIErrorAttributes:
    """Test APIError has accessible status_code and provider attributes."""

    def test_api_error_with_status_code_and_provider(self):
        exc = APIError("rate limited", status_code=429, provider="glm")
        assert exc.status_code == 429
        assert exc.provider == "glm"
        assert exc.args[0] == "rate limited"

    def test_api_error_without_args(self):
        exc = APIError("error")
        assert exc.status_code is None
        assert exc.provider is None

    def test_api_error_message_only(self):
        exc = APIError("something went wrong")
        assert exc.args[0] == "something went wrong"


class TestConnectionErrorAttributes:
    """Test ConnectionError has accessible provider and extra attributes."""

    def test_connection_error_with_provider_and_extra(self):
        exc = ConnectionError(message="", provider="x", extra={"url": "y"})
        assert exc.provider == "x"
        # ConnectionError.__init__ stores kwargs as self.extra
        assert exc.extra == {"extra": {"url": "y"}}

    def test_connection_error_empty_message(self):
        exc = ConnectionError(message="", provider="test")
        assert exc.args[0] == ""

    def test_connection_error_with_multiple_extra_kwargs(self):
        exc = ConnectionError(provider="openai", timeout=30, url="http://api.example.com")
        assert exc.provider == "openai"
        # ConnectionError stores all kwargs as self.extra
        assert exc.extra.get("timeout") == 30
        assert exc.extra.get("url") == "http://api.example.com"


class TestTimeoutErrorAttributes:
    """Test TimeoutError has accessible provider and extra attributes."""

    def test_timeout_error_with_provider_and_extra(self):
        exc = TimeoutError(message="", provider="x", extra={"url": "y"})
        assert exc.provider == "x"
        # ConnectionError.__init__ stores kwargs as self.extra
        assert exc.extra == {"extra": {"url": "y"}}

    def test_timeout_error_empty_message(self):
        exc = TimeoutError(message="", provider="test")
        assert exc.args[0] == ""

    def test_timeout_error_with_multiple_extra_kwargs(self):
        exc = TimeoutError(provider="anthropic", timeout=60, endpoint="/v1/chat")
        assert exc.provider == "anthropic"
        assert exc.extra["timeout"] == 60
        assert exc.extra["endpoint"] == "/v1/chat"


class TestExceptionCatching:
    """Test that exceptions can be caught as LLMException (base class)."""

    def test_configuration_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise ConfigurationError("bad config")

    def test_authentication_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise AuthenticationError("invalid key")

    def test_api_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise APIError("api failed", status_code=500)

    def test_rate_limit_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise RateLimitError("too many requests", status_code=429)

    def test_invalid_request_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise InvalidRequestError("invalid param")

    def test_model_not_supported_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise ModelNotSupportedError("model not found")

    def test_connection_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise ConnectionError(provider="test")

    def test_timeout_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise TimeoutError(provider="test")

    def test_streaming_error_caught_as_llm_exception(self):
        with pytest.raises(LLMException):
            raise StreamingError("stream interrupted")


class TestExceptionSeparation:
    """Test that ConfigurationError is separate from APIError (different inheritance)."""

    def test_configuration_error_is_not_api_error(self):
        assert not issubclass(ConfigurationError, APIError)

    def test_authentication_error_is_not_api_error(self):
        assert not issubclass(AuthenticationError, APIError)

    def test_rate_limit_error_is_api_error(self):
        assert issubclass(RateLimitError, APIError)

    def test_raising_configuration_error_does_not_match_api_error(self):
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("config issue")

    def test_raising_api_error_does_not_match_configuration_error(self):
        with pytest.raises(APIError):
            raise APIError("api issue")

    def test_rate_limit_error_caught_as_api_error(self):
        with pytest.raises(APIError):
            raise RateLimitError("rate limited", status_code=429)
