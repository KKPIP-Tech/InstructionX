"""pytest tests for core.llm.llm_provider.LLMProvider."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ---------------------------------------------------------------------------
# Shared helper to create a clean LLMProvider instance with no real I/O.
# Patches LLMConfig at the class level so __init__ is a no-op.
# ---------------------------------------------------------------------------

def _make_provider(mocker):
    """
    Return a fresh LLMProvider instance with LLMConfig mocked to a no-op.

    All provider-level tests use this helper to avoid hitting the real
    filesystem (CONFIG_DIR lives in config.py, not llm_provider.py).
    """
    import core.llm.llm_provider as lp_module

    lp_module.LLMProvider._instance = None
    lp_module.LLMProvider._initialized = False

    mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
    mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
    mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)

    return lp_module.LLMProvider()


# ===========================================================================
# 1. Singleton — double-checked locking, instance created once
# ===========================================================================

class TestSingleton:
    def test_singleton_returns_same_instance(self, mocker):
        """LLMProvider() returns the same instance on repeated calls."""
        import core.llm.llm_provider as lp_module
        lp_module.LLMProvider._instance = None
        lp_module.LLMProvider._initialized = False

        mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
        mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
        mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)

        inst1 = lp_module.LLMProvider()
        inst2 = lp_module.LLMProvider()
        assert inst1 is inst2

    def test_singleton_idempotent_init(self, mocker):
        """__init__ runs only once even when called multiple times."""
        import core.llm.llm_provider as lp_module
        lp_module.LLMProvider._instance = None
        lp_module.LLMProvider._initialized = False

        init_mock = mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
        mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
        mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)

        lp_module.LLMProvider()
        lp_module.LLMProvider()

        # LLMConfig.__init__ should be called exactly once
        assert init_mock.call_count == 1

    def test_singleton_double_checked_locking(self, mocker):
        """Double-checked locking: two threads get the same instance."""
        import core.llm.llm_provider as lp_module
        import threading

        lp_module.LLMProvider._instance = None
        lp_module.LLMProvider._initialized = False

        mocker.patch.object(lp_module.LLMConfig, "__init__", return_value=None)
        mocker.patch.object(lp_module.LLMConfig, "get_all_providers", return_value={})
        mocker.patch.object(lp_module.LLMConfig, "load_models_cache", return_value=None)

        results = []

        def get_instance():
            inst = lp_module.LLMProvider()
            results.append(inst)

        t1 = threading.Thread(target=get_instance)
        t2 = threading.Thread(target=get_instance)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results[0] is results[1]


# ===========================================================================
# 2. _create_provider raises ConfigurationError for unknown provider_type
# ===========================================================================

class TestCreateProvider:
    def test_create_provider_skips_unknown_adapter(self, mocker):
        """_create_provider 遇到未注册适配器时跳过该实例（返回 None、不注册，不抛异常）。"""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mocker.patch.object(lp_module, "get_adapter_class", return_value=None)

        result = inst._create_provider("bad", {"adapter": "nonexistent"})
        assert result is None
        assert "bad" not in inst._providers

    def test_create_provider_success(self, mocker):
        """_create_provider creates the provider instance and stores it."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mocker.patch.object(lp_module, "get_adapter_class", return_value=lambda cfg, **kw: mock_provider)

        result = inst._create_provider("test", {"adapter": "mock"})
        assert result is mock_provider
        assert "test" in inst._providers


# ===========================================================================
# 3. chat — default routing, errors
# ===========================================================================

class TestChat:
    def test_chat_default_selects_first_enabled(self, mocker):
        """chat(provider='default') selects the first enabled chat provider."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        mock_response = MagicMock(content="hello", model="m")
        mock_response.usage = None
        mock_provider.chat.return_value = mock_response
        inst._providers["first"] = mock_provider

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={"first": mock_provider})

        result = inst.chat([Message("user", "hi")], provider="default")
        assert result.content == "hello"
        mock_provider.chat.assert_called_once()

    def test_chat_raises_no_enabled_providers(self, mocker):
        """chat() raises ConfigurationError when no providers are enabled."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()
        inst._providers["p"] = MagicMock()

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={})

        with pytest.raises(lp_module.ConfigurationError, match="No enabled chat provider"):
            inst.chat([{"role": "user", "content": "hi"}], provider="default")

    def test_chat_raises_provider_not_found(self, mocker):
        """chat() raises ConfigurationError when named provider does not exist."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        with pytest.raises(lp_module.ConfigurationError, match="Provider not found"):
            inst.chat([{"role": "user", "content": "hi"}], provider="nonexistent")

    def test_chat_passes_messages_to_provider(self, mocker):
        """chat() passes Message objects and dicts as-is to provider.chat."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        mock_response = MagicMock(content="ok", model="m")
        mock_response.usage = None
        mock_provider.chat.return_value = mock_response
        inst._providers["prov"] = mock_provider

        messages = [
            Message("system", "be helpful"),
            Message("user", "hello"),
            {"role": "assistant", "content": "hi"},
        ]

        inst.chat(messages, provider="prov")

        call_kwargs = mock_provider.chat.call_args.kwargs
        passed = call_kwargs["messages"]
        assert passed is messages  # raw objects passed through unchanged
        assert isinstance(passed[0], Message)
        assert isinstance(passed[1], Message)
        assert isinstance(passed[2], dict)

    def test_chat_named_provider_routes_correctly(self, mocker):
        """chat(provider='prov_b') calls the correct provider instance."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_a = MagicMock()
        mock_a.chat.return_value = MagicMock(content="a", model="m1", usage=None)
        mock_b = MagicMock()
        mock_b.chat.return_value = MagicMock(content="b", model="m2", usage=None)
        mock_a.refresh_models.return_value = []
        mock_b.refresh_models.return_value = []
        inst._providers["prov_a"] = mock_a
        inst._providers["prov_b"] = mock_b

        result = inst.chat([{"role": "user", "content": "x"}], provider="prov_b")
        assert result.content == "b"
        mock_a.chat.assert_not_called()
        mock_b.chat.assert_called_once()


# ===========================================================================
# 7. stream_chat routing and errors
# ===========================================================================

class TestStreamChat:
    def test_stream_chat_default_selects_first_enabled(self, mocker):
        """stream_chat(provider='default') selects the first enabled provider."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        mock_provider.stream_chat.return_value = iter([MagicMock(content="chunk")])
        inst._providers["prov"] = mock_provider

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={"prov": mock_provider})

        inst.stream_chat([Message("user", "hi")], provider="default")
        mock_provider.stream_chat.assert_called_once()

    def test_stream_chat_raises_no_enabled_providers(self, mocker):
        """stream_chat() raises ConfigurationError when no providers are enabled."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()
        inst._providers["p"] = MagicMock()

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={})

        with pytest.raises(lp_module.ConfigurationError, match="No enabled chat provider"):
            inst.stream_chat([{"role": "user", "content": "hi"}], provider="default")


# ===========================================================================
# 9. embed routing and errors
# ===========================================================================

class TestEmbed:
    def test_embed_default_selects_first_enabled_embedding(self, mocker):
        """embed(provider='default') selects the first enabled embedding provider."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        mock_provider.embed.return_value = [MagicMock(embedding=[0.1], model="emb")]
        inst._providers["emb_prov"] = mock_provider

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={"emb_prov": mock_provider})

        result = inst.embed("hello world", provider="default")
        assert len(result) == 1
        mock_provider.embed.assert_called_once()

    def test_embed_raises_no_enabled_embedding_providers(self, mocker):
        """embed() raises ConfigurationError when no embedding providers are enabled."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()
        inst._providers["p"] = MagicMock()

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={})

        with pytest.raises(lp_module.ConfigurationError, match="No enabled embedding provider"):
            inst.embed("text", provider="default")


# ===========================================================================
# 11. add_provider
# ===========================================================================

class TestAddProvider:
    def test_add_provider_saves_and_creates_instance(self, mocker):
        """add_provider() saves to config and creates the provider instance."""
        import core.llm.llm_provider as lp_module
        from core.llm.config import ProviderConfig

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()
        inst._config = MagicMock()

        mock_provider = MagicMock()
        mock_provider.refresh_models.return_value = []
        mocker.patch.object(lp_module, "get_adapter_class", return_value=lambda cfg, **kw: mock_provider)

        config = ProviderConfig(name="new", adapter="mock", api_key="key123")
        inst.add_provider("new", config)

        inst._config.add_provider.assert_called_once_with("new", config)
        assert "new" in inst._providers
        assert inst._providers["new"] is mock_provider


# ===========================================================================
# 12. remove_provider
# ===========================================================================

class TestRemoveProvider:
    def test_remove_provider_closes_removes_and_deletes_config(self, mocker):
        """remove_provider() closes, removes from dict, and deletes from config."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_provider = MagicMock()
        inst._providers["to_remove"] = mock_provider
        inst._config = MagicMock()
        inst._config.remove_provider.return_value = True

        result = inst.remove_provider("to_remove")

        mock_provider.close.assert_called_once()
        assert "to_remove" not in inst._providers
        inst._config.remove_provider.assert_called_once_with("to_remove")
        assert result is True


# ===========================================================================
# 13. reload_config
# ===========================================================================

class TestReloadConfig:
    def test_reload_config_closes_all_recreates_providers(self, mocker):
        """reload_config() closes all providers and re-initializes from new config."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_a = MagicMock()
        mock_b = MagicMock()
        inst._providers["a"] = mock_a
        inst._providers["b"] = mock_b

        mocker.patch.object(inst, "_init_providers")

        inst.reload_config()

        mock_a.close.assert_called_once()
        mock_b.close.assert_called_once()
        assert inst._providers == {}
        inst._init_providers.assert_called_once()


# ===========================================================================
# 14. get_provider
# ===========================================================================

class TestGetProvider:
    def test_get_provider_returns_instance(self, mocker):
        """get_provider() returns the provider instance when it exists."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_p = MagicMock()
        inst._providers["found"] = mock_p

        assert inst.get_provider("found") is mock_p

    def test_get_provider_returns_none_for_missing(self, mocker):
        """get_provider() returns None when the provider does not exist."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        assert inst.get_provider("missing") is None


# ===========================================================================
# 15. get_all_providers
# ===========================================================================

class TestGetAllProviders:
    def test_get_all_providers_returns_copy(self, mocker):
        """get_all_providers() returns a copy — modifying it doesn't affect internal dict."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_p = MagicMock()
        inst._providers["x"] = mock_p

        result = inst.get_all_providers()
        result["x"] = MagicMock()

        assert inst._providers["x"] is mock_p  # original unchanged


# ===========================================================================
# 16. get_cached_models
# ===========================================================================

class TestGetCachedModels:
    def test_get_cached_models_returns_list(self, mocker):
        """get_cached_models() returns the cached model list for a known provider."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import ModelInfo

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        models = [ModelInfo(id="m1", name="Model 1")]
        inst._models_cache["prov"] = models

        result = inst.get_cached_models("prov")
        assert result == models

    def test_get_cached_models_returns_empty_for_unknown(self, mocker):
        """get_cached_models() returns [] for an unknown provider."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()

        result = inst.get_cached_models("unknown")
        assert result == []


# ===========================================================================
# 17-18. get_enabled_providers — chat / embedding
# ===========================================================================

class TestGetEnabledProviders:
    def test_get_enabled_providers_chat(self, mocker):
        """get_enabled_providers('chat') returns providers with enabled_chat=True."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()

        mock_chat = MagicMock()
        mock_emb = MagicMock()
        inst._providers["chat_prov"] = mock_chat
        inst._providers["emb_prov"] = mock_emb

        mock_config_chat = MagicMock()
        mock_config_chat.enabled_chat = True
        mock_config_emb = MagicMock()
        mock_config_emb.enabled_chat = False
        inst._config = MagicMock()
        inst._config.get_enabled_providers.return_value = {"chat_prov": mock_config_chat}

        result = inst.get_enabled_providers("chat")
        assert "chat_prov" in result
        assert result["chat_prov"] is mock_chat

    def test_get_enabled_providers_embedding(self, mocker):
        """get_enabled_providers('embedding') returns providers with enabled_embedding=True."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()

        mock_provider = MagicMock()
        inst._providers["emb_prov"] = mock_provider

        mock_config = MagicMock()
        mock_config.enabled_embedding = True
        inst._config = MagicMock()
        inst._config.get_enabled_providers.return_value = {"emb_prov": mock_config}

        result = inst.get_enabled_providers("embedding")
        assert "emb_prov" in result
        assert result["emb_prov"] is mock_provider


# ===========================================================================
# 19. async_chat
# ===========================================================================

class TestAsyncChat:
    def test_async_chat_default_routing(self, mocker):
        """async_chat(provider='default') delegates to the first enabled provider."""
        import asyncio
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message, ChatResponse

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_response = ChatResponse(content="async hello", model="async-model")
        mock_provider = MagicMock()
        mock_provider.async_chat = AsyncMock(return_value=mock_response)
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        inst._providers["async_prov"] = mock_provider

        mocker.patch.object(lp_module.LLMProvider, "get_enabled_providers", return_value={"async_prov": mock_provider})

        result = asyncio.run(inst.async_chat([Message("user", "hi")], provider="default"))
        assert result.content == "async hello"
        mock_provider.async_chat.assert_awaited_once()

    def test_async_chat_named_provider(self, mocker):
        """async_chat(provider='prov_b') routes to the correct named provider."""
        import asyncio
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_a = MagicMock()
        mock_a.async_chat = AsyncMock(return_value=MagicMock(content="a"))
        mock_b = MagicMock()
        mock_b.async_chat = AsyncMock(return_value=MagicMock(content="b"))
        mock_a.refresh_models.return_value = []
        mock_b.refresh_models.return_value = []
        inst._providers["prov_a"] = mock_a
        inst._providers["prov_b"] = mock_b

        result = asyncio.run(inst.async_chat([{"role": "user", "content": "x"}], provider="prov_b"))
        assert result.content == "b"
        mock_a.async_chat.assert_not_awaited()
        mock_b.async_chat.assert_awaited_once()


# ===========================================================================
# 20. close
# ===========================================================================

class TestClose:
    def test_close_clears_all_providers(self, mocker):
        """close() calls close() on each provider and clears the dict."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_a = MagicMock()
        mock_b = MagicMock()
        inst._providers["a"] = mock_a
        inst._providers["b"] = mock_b

        inst.close()

        mock_a.close.assert_called_once()
        mock_b.close.assert_called_once()
        assert inst._providers == {}


# ===========================================================================
# Additional coverage: refresh_provider_models, get_models, available_providers
# ===========================================================================

class TestRefreshProviderModels:
    def test_refresh_provider_models_success(self, mocker):
        """refresh_provider_models calls provider.refresh_models and updates cache."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import ModelInfo

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_provider = MagicMock()
        models = [ModelInfo(id="m1", name="Model 1")]
        mock_provider.refresh_models.return_value = models
        inst._providers["prov"] = mock_provider
        inst._config = MagicMock()
        # 配置版本号与已加载版本对齐，避免入口处的惰性配置刷新触发全量 reload
        inst._config.version = inst._loaded_config_version

        result = inst.refresh_provider_models("prov", force=True)
        assert result == models
        assert inst._models_cache["prov"] == models
        mock_provider.refresh_models.assert_called_once_with(force=True)

    def test_refresh_provider_models_unknown_provider(self, mocker):
        """refresh_provider_models returns [] for unknown provider."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        result = inst.refresh_provider_models("unknown")
        assert result == []


class TestGetModels:
    def test_get_models_specific_provider(self, mocker):
        """get_models('prov') returns only that provider's model list."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import ModelInfo

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_provider = MagicMock()
        models = [ModelInfo(id="m1", name="Model 1")]
        mock_provider.get_models.return_value = models
        inst._providers["prov"] = mock_provider

        result = inst.get_models("prov")
        assert result == {"prov": models}

    def test_get_models_all_providers(self, mocker):
        """get_models() returns model lists for all providers."""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import ModelInfo

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        mock_a = MagicMock()
        mock_a.get_models.return_value = [ModelInfo(id="a1", name="A1")]
        mock_b = MagicMock()
        mock_b.get_models.return_value = [ModelInfo(id="b1", name="B1")]
        inst._providers["a"] = mock_a
        inst._providers["b"] = mock_b

        result = inst.get_models()
        assert "a" in result
        assert "b" in result


class TestAvailableProviders:
    def test_available_providers_returns_registry_keys(self, mocker):
        """available_providers returns list(PROVIDER_REGISTRY.keys())."""
        import core.llm.llm_provider as lp_module

        _make_provider(mocker)
        inst = lp_module.LLMProvider()

        # available_providers calls list(PROVIDER_REGISTRY.keys())
        result = inst.available_providers
        assert isinstance(result, list)
        # All actual registry keys should be present
        from core.llm.providers import PROVIDER_REGISTRY
        assert set(result) == set(PROVIDER_REGISTRY.keys())


# ===========================================================================
# 12. Parameter filtering and default resolution
# ===========================================================================

class TestChatParameterFiltering:
    def test_filter_none_kwargs_removes_none_values(self):
        """_filter_none_kwargs 剔除值为 None 的键。"""
        import core.llm.llm_provider as lp_module
        result = lp_module.LLMProvider._filter_none_kwargs({
            "model": "m1",
            "temperature": None,
            "max_tokens": 100,
            "top_p": None,
        })
        assert result == {"model": "m1", "max_tokens": 100}

    def test_model_default_resolved_to_none(self, mocker):
        """model='default' 会被解析为 None，不会传给底层 provider。"""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        mock_provider = MagicMock()
        mock_response = MagicMock(content="ok", model="m", usage=None)
        mock_provider.chat.return_value = mock_response
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        inst._providers["prov"] = mock_provider

        inst.chat([Message("user", "hi")], provider="prov", model="default")

        call_kwargs = mock_provider.chat.call_args.kwargs
        assert "model" not in call_kwargs


class TestStreamChatCallback:
    def test_stream_callback_receives_chunks_and_done(self, mocker):
        """stream_chat 正确调用 callback 并传递 chunk 和 done 标志。"""
        import core.llm.llm_provider as lp_module
        from core.llm.provider_interface import Message

        _make_provider(mocker)
        inst = lp_module.LLMProvider()
        inst._providers.clear()

        chunks = [MagicMock(content="hello ", done=False),
                  MagicMock(content="world", done=False),
                  MagicMock(content="", done=True)]
        mock_provider = MagicMock()
        mock_provider.stream_chat.return_value = iter(chunks)
        mock_provider.refresh_models.return_value = []
        mock_provider.get_models.return_value = []
        inst._providers["prov"] = mock_provider

        received = []
        def cb(chunk, done):
            received.append((chunk, done))

        inst.stream_chat([Message("user", "hi")], provider="prov", callback=cb)

        assert len(received) >= 2
        texts = [c for c, d in received if c]
        assert "".join(texts) == "hello world"
        assert received[-1][1] is True
