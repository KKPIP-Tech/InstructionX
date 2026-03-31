"""
pytest tests for core/plugin/config_manager.py (PluginConfigManager)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.plugin.config_manager import PluginConfigManager


class TestPluginConfigManager:
    """Tests for PluginConfigManager class."""

    @pytest.fixture
    def mock_logger(self):
        """Patch LoggerManager to suppress logging during tests."""
        with patch("core.plugin.config_manager.LoggerManager") as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance

    @pytest.fixture
    def config_dir(self, tmp_path, mock_logger):
        """Create a temporary config directory."""
        return tmp_path

    # ------------------------------------------------------------------
    # Test 1: File absent -> returns empty structure
    # ------------------------------------------------------------------
    def test_load_plugin_order_file_absent_returns_empty_structure(self, config_dir, mock_logger):
        """
        When the config file does not exist, load_plugin_order() should return
        {"official_plugins": [], "thirdparty_plugins": []}.
        """
        manager = PluginConfigManager(config_dir=config_dir)
        result = manager.load_plugin_order()

        assert result == {"official_plugins": [], "thirdparty_plugins": []}

    # ------------------------------------------------------------------
    # Test 2: File with invalid JSON -> returns empty structure
    # ------------------------------------------------------------------
    def test_load_plugin_order_invalid_json_returns_empty_structure(self, config_dir, mock_logger):
        """
        When the config file contains invalid JSON, load_plugin_order() should
        return the empty structure.
        """
        config_file = config_dir / "plugin_order.json"
        config_file.write_text("{ not valid json", encoding="utf-8")

        manager = PluginConfigManager(config_dir=config_dir)
        result = manager.load_plugin_order()

        assert result == {"official_plugins": [], "thirdparty_plugins": []}

    # ------------------------------------------------------------------
    # Test 3: File with partial data -> missing keys filled with []
    # ------------------------------------------------------------------
    def test_load_plugin_order_partial_data_fills_missing_keys(self, config_dir, mock_logger):
        """
        When the config file has some but not all keys, the missing keys
        should be filled with empty lists.
        """
        config_file = config_dir / "plugin_order.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"official_plugins": ["uuid-1", "uuid-2"]}, f)

        manager = PluginConfigManager(config_dir=config_dir)
        result = manager.load_plugin_order()

        assert result["official_plugins"] == ["uuid-1", "uuid-2"]
        assert result["thirdparty_plugins"] == []

    def test_load_plugin_order_only_thirdparty_key(self, config_dir, mock_logger):
        """Missing 'official_plugins' key is filled with []. """
        config_file = config_dir / "plugin_order.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"thirdparty_plugins": ["uuid-3"]}, f)

        manager = PluginConfigManager(config_dir=config_dir)
        result = manager.load_plugin_order()

        assert result["official_plugins"] == []
        assert result["thirdparty_plugins"] == ["uuid-3"]

    # ------------------------------------------------------------------
    # Test 4: save_plugin_order() writes valid JSON with correct keys
    # ------------------------------------------------------------------
    def test_save_plugin_order_writes_valid_json(self, config_dir, mock_logger):
        """save_plugin_order() writes a valid JSON file with both keys."""
        manager = PluginConfigManager(config_dir=config_dir)
        official = ["uuid-a", "uuid-b"]
        thirdparty = ["uuid-c"]

        result = manager.save_plugin_order(official, thirdparty)

        assert result is True
        assert manager.config_file.exists()

        with open(manager.config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["official_plugins"] == official
        assert data["thirdparty_plugins"] == thirdparty

    # ------------------------------------------------------------------
    # Test 5: update_official_order() updates only official, preserves thirdparty
    # ------------------------------------------------------------------
    def test_update_official_order_updates_only_official(self, config_dir, mock_logger):
        """
        update_official_order() should update only the official_plugins list
        and leave the thirdparty_plugins list unchanged.
        """
        config_file = config_dir / "plugin_order.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({
                "official_plugins": ["uuid-original"],
                "thirdparty_plugins": ["uuid-third"]
            }, f)

        manager = PluginConfigManager(config_dir=config_dir)
        new_official = ["uuid-new-1", "uuid-new-2"]
        result = manager.update_official_order(new_official)

        assert result is True

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["official_plugins"] == new_official
        assert data["thirdparty_plugins"] == ["uuid-third"]

    # ------------------------------------------------------------------
    # Test 6: update_thirdparty_order() updates only thirdparty, preserves official
    # ------------------------------------------------------------------
    def test_update_thirdparty_order_updates_only_thirdparty(self, config_dir, mock_logger):
        """
        update_thirdparty_order() should update only the thirdparty_plugins list
        and leave the official_plugins list unchanged.
        """
        config_file = config_dir / "plugin_order.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({
                "official_plugins": ["uuid-official"],
                "thirdparty_plugins": ["uuid-original"]
            }, f)

        manager = PluginConfigManager(config_dir=config_dir)
        new_thirdparty = ["uuid-new-third"]
        result = manager.update_thirdparty_order(new_thirdparty)

        assert result is True

        with open(config_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["official_plugins"] == ["uuid-official"]
        assert data["thirdparty_plugins"] == new_thirdparty
