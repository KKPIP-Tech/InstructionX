"""pytest tests for core/llm/config.py"""

import json

import pytest


@pytest.fixture
def llm_config_with_default(mocker, tmp_path):
    """
    LLMConfig with default config created in a temp directory.

    CONFIG_DIR and CONFIG_FILE point to the same temp tree so
    _create_default_config can write the file successfully.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = config_dir / "llm_providers.json"
    cache_file = config_dir / "cache.json"

    mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
    mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
    mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

    from core.llm.config import LLMConfig

    return LLMConfig(), cfg_file


@pytest.fixture
def llm_config_with_empty_providers(mocker, tmp_path):
    """
    LLMConfig backed by an empty providers dict (no default providers).
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = config_dir / "llm_providers.json"
    cache_file = config_dir / "cache.json"
    cfg_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")

    mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
    mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
    mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

    from core.llm.config import LLMConfig

    return LLMConfig(), cfg_file


class TestProviderConfig:
    """Tests for ProviderConfig.to_dict / from_dict."""

    def test_to_dict_roundtrip(self, mocker, tmp_path):
        """to_dict() preserves all fields including extra kwargs."""
        mocker.patch("core.llm.config.CONFIG_DIR", tmp_path / "config")
        mocker.patch("core.llm.config.CONFIG_FILE", tmp_path / "config" / "llm_providers.json")
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", tmp_path / "config" / "cache.json")

        from core.llm.config import ProviderConfig

        config = ProviderConfig(
            name="TestProvider",
            provider_type="test",
            api_key="key123",
            base_url="https://example.com",
            chat_model="model-a",
            embedding_model="embed-b",
            enabled_chat=False,
            enabled_embedding=True,
            support_vision=False,
            custom_field="custom_value",
            max_tokens=4096,
        )
        d = config.to_dict()
        assert d["name"] == "TestProvider"
        assert d["provider_type"] == "test"
        assert d["api_key"] == "key123"
        assert d["base_url"] == "https://example.com"
        assert d["chat_model"] == "model-a"
        assert d["embedding_model"] == "embed-b"
        assert d["enabled_chat"] is False
        assert d["enabled_embedding"] is True
        assert d["support_vision"] is False
        assert d["custom_field"] == "custom_value"
        assert d["max_tokens"] == 4096

    def test_from_dict_preserves_extra(self, mocker, tmp_path):
        """from_dict() stores unknown fields in extra."""
        mocker.patch("core.llm.config.CONFIG_DIR", tmp_path / "config")
        mocker.patch("core.llm.config.CONFIG_FILE", tmp_path / "config" / "llm_providers.json")
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", tmp_path / "config" / "cache.json")

        from core.llm.config import ProviderConfig

        data = {
            "name": "ExtraProvider",
            "provider_type": "extra",
            "api_key": "",
            "base_url": "http://localhost",
            "chat_model": "llama3",
            "embedding_model": "",
            "enabled_chat": True,
            "enabled_embedding": False,
            "support_vision": True,
            "priority": 1,
            "timeout": 30,
        }
        config = ProviderConfig.from_dict(data)
        assert config.name == "ExtraProvider"
        assert config.provider_type == "extra"
        assert config.extra["priority"] == 1
        assert config.extra["timeout"] == 30

    def test_from_dict_to_dict_roundtrip(self, mocker, tmp_path):
        """to_dict -> from_dict roundtrip preserves all fields."""
        mocker.patch("core.llm.config.CONFIG_DIR", tmp_path / "config")
        mocker.patch("core.llm.config.CONFIG_FILE", tmp_path / "config" / "llm_providers.json")
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", tmp_path / "config" / "cache.json")

        from core.llm.config import ProviderConfig

        original = ProviderConfig(
            name="RoundTrip",
            provider_type="rt",
            api_key="abc",
            base_url="https://rt.example",
            chat_model="gpt-4",
            embedding_model="text-embedding-3",
            enabled_chat=True,
            enabled_embedding=True,
            support_vision=False,
            tier="premium",
        )
        restored = ProviderConfig.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.provider_type == original.provider_type
        assert restored.api_key == original.api_key
        assert restored.base_url == original.base_url
        assert restored.chat_model == original.chat_model
        assert restored.embedding_model == original.embedding_model
        assert restored.enabled_chat == original.enabled_chat
        assert restored.enabled_embedding == original.enabled_embedding
        assert restored.support_vision == original.support_vision
        assert restored.extra["tier"] == "premium"


class TestLLMConfigCreateDefault:
    """Tests for LLMConfig._create_default_config()."""

    def test_create_default_config_five_providers(self, mocker, tmp_path):
        """_create_default_config() creates minimax, siliconflow, glm, ollama, openai."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig

        cfg = LLMConfig()
        assert len(cfg._providers) == 5
        assert "minimax" in cfg._providers
        assert "siliconflow" in cfg._providers
        assert "glm" in cfg._providers
        assert "ollama" in cfg._providers
        assert "openai" in cfg._providers

    def test_create_default_config_saves_to_disk(self, mocker, tmp_path):
        """_create_default_config() writes llm_providers.json to disk."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig

        LLMConfig()
        assert cfg_file.exists()
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "providers" in data
        assert len(data["providers"]) == 5


class TestLLMConfigLoad:
    """Tests for LLMConfig._load_config()."""

    def test_load_config_parses_existing_json(self, mocker, tmp_path):
        """_load_config() correctly parses existing JSON file."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        cfg_file.write_text(
            json.dumps({
                "providers": {
                    "myprovider": {
                        "name": "MyProvider",
                        "provider_type": "myprovider",
                        "api_key": "secret",
                        "base_url": "https://api.myprovider.com",
                        "chat_model": "my-model",
                        "embedding_model": "my-embed",
                        "enabled_chat": True,
                        "enabled_embedding": False,
                        "support_vision": True,
                    }
                }
            }, indent=4),
            encoding="utf-8",
        )

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig

        cfg = LLMConfig()
        provider = cfg.get_provider("myprovider")
        assert provider is not None
        assert provider.name == "MyProvider"
        assert provider.api_key == "secret"
        assert provider.chat_model == "my-model"

    def test_load_config_skips_default_creation_when_file_exists(self, mocker, tmp_path):
        """When CONFIG_FILE exists, _load_config() does not call _create_default_config."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        cfg_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig

        spy = mocker.patch(
            "core.llm.config.LLMConfig._create_default_config",
            wraps=lambda self: None,
        )
        LLMConfig()
        spy.assert_not_called()


class TestLLMConfigSave:
    """Tests for LLMConfig.save_config()."""

    def test_save_config_writes_valid_json(self, mocker, tmp_path):
        """save_config() writes a valid, parseable JSON file."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        cfg_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig, ProviderConfig

        cfg = LLMConfig()
        cfg.add_provider(
            "newprovider",
            ProviderConfig(
                name="NewProvider",
                provider_type="newprovider",
                api_key="xyz",
                base_url="https://api.new.com",
                chat_model="new-model",
                embedding_model="new-embed",
                enabled_chat=True,
                enabled_embedding=True,
                support_vision=False,
            ),
        )
        cfg.save_config()

        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "providers" in data
        assert "newprovider" in data["providers"]
        assert data["providers"]["newprovider"]["api_key"] == "xyz"


class TestLLMConfigGet:
    """Tests for get_provider / get_all_providers / get_enabled_providers."""

    def test_get_provider_returns_config(self, llm_config_with_default):
        """get_provider() returns the ProviderConfig when provider exists."""
        cfg, _ = llm_config_with_default
        provider = cfg.get_provider("minimax")
        assert provider is not None
        assert provider.name == "MiniMax"

    def test_get_provider_returns_none_for_missing(self, llm_config_with_default):
        """get_provider() returns None when provider does not exist."""
        cfg, _ = llm_config_with_default
        assert cfg.get_provider("nonexistent") is None

    def test_get_all_providers_returns_copy(self, llm_config_with_default):
        """get_all_providers() returns a copy, not the internal dict."""
        cfg, _ = llm_config_with_default
        providers = cfg.get_all_providers()
        providers.clear()
        assert len(cfg._providers) > 0  # internal dict unchanged

    def test_get_enabled_providers_chat(self, llm_config_with_default):
        """get_enabled_providers('chat') returns only providers with enabled_chat=True."""
        cfg, _ = llm_config_with_default
        chat_providers = cfg.get_enabled_providers("chat")
        assert all(p.enabled_chat for p in chat_providers.values())
        # All 5 default providers have enabled_chat=True
        assert len(chat_providers) == 5

    def test_get_enabled_providers_embedding(self, llm_config_with_default):
        """get_enabled_providers('embedding') returns only providers with enabled_embedding=True."""
        cfg, _ = llm_config_with_default
        embed_providers = cfg.get_enabled_providers("embedding")
        assert all(p.enabled_embedding for p in embed_providers.values())
        # All 5 default providers have enabled_embedding=True in default config
        assert len(embed_providers) == 5


class TestLLMConfigAddRemove:
    """Tests for add_provider / remove_provider."""

    def test_add_provider_saves_and_updates_memory(self, mocker, tmp_path):
        """add_provider() updates memory and persists to disk."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        cfg_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig, ProviderConfig

        cfg = LLMConfig()
        assert cfg.get_provider("added") is None

        new_config = ProviderConfig(
            name="AddedProvider",
            provider_type="added",
            api_key="key",
            base_url="https://added.com",
            chat_model="added-model",
            embedding_model="",
            enabled_chat=True,
            enabled_embedding=False,
            support_vision=True,
        )
        cfg.add_provider("added", new_config)

        assert cfg.get_provider("added") is not None
        assert cfg.get_provider("added").name == "AddedProvider"

        # Verify disk
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "added" in data["providers"]

    def test_remove_provider_removes_and_saves(self, llm_config_with_default):
        """remove_provider() removes from memory, saves, and returns True."""
        cfg, cfg_file = llm_config_with_default
        assert cfg.get_provider("ollama") is not None
        result = cfg.remove_provider("ollama")

        assert result is True
        assert cfg.get_provider("ollama") is None
        data = json.loads(cfg_file.read_text(encoding="utf-8"))
        assert "ollama" not in data["providers"]

    def test_remove_provider_returns_false_for_missing(self, llm_config_with_default):
        """remove_provider() returns False when provider does not exist."""
        cfg, _ = llm_config_with_default
        result = cfg.remove_provider("nonexistent")
        assert result is False


class TestLLMConfigModelsCache:
    """Tests for models cache operations."""

    def test_save_and_load_models_cache_roundtrip(self, llm_config_with_empty_providers):
        """save_models_cache / load_models_cache roundtrip works."""
        cfg, _ = llm_config_with_empty_providers
        models = [
            {"id": "model-1", "name": "Model One"},
            {"id": "model-2", "name": "Model Two"},
        ]
        cfg.save_models_cache("minimax", models)

        loaded = cfg.load_models_cache("minimax")
        assert loaded == models

    def test_load_models_cache_returns_none_for_unknown_provider(
        self, llm_config_with_empty_providers
    ):
        """load_models_cache() returns None when provider not in cache."""
        cfg, _ = llm_config_with_empty_providers
        assert cfg.load_models_cache("unknown_provider") is None

    def test_load_models_cache_returns_empty_dict_if_file_absent(
        self, llm_config_with_empty_providers
    ):
        """_load_models_cache() returns {} when MODELS_CACHE_FILE does not exist."""
        cfg, _ = llm_config_with_empty_providers
        result = cfg._load_models_cache()
        assert result == {}

    def test_load_models_cache_returns_empty_dict_on_corrupted_json(
        self, mocker, tmp_path
    ):
        """_load_models_cache() returns {} when file contains invalid JSON."""
        config_dir = tmp_path / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file = config_dir / "llm_providers.json"
        cache_file = config_dir / "cache.json"

        cfg_file.write_text(json.dumps({"providers": {}}), encoding="utf-8")
        cache_file.write_text("{ invalid json content", encoding="utf-8")

        mocker.patch("core.llm.config.CONFIG_DIR", config_dir)
        mocker.patch("core.llm.config.CONFIG_FILE", cfg_file)
        mocker.patch("core.llm.config.MODELS_CACHE_FILE", cache_file)

        from core.llm.config import LLMConfig

        cfg = LLMConfig()
        result = cfg._load_models_cache()
        assert result == {}
