"""
pytest tests for core/plugin/plugin_identity.py (PluginIdentity)
"""

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.plugin.plugin_identity import PluginIdentity


class TestPluginIdentity:
    """Tests for PluginIdentity class."""

    @pytest.fixture
    def mock_logger(self):
        """Patch LoggerManager to suppress logging during tests."""
        with patch("core.plugin.plugin_identity.LoggerManager") as mock:
            instance = MagicMock()
            mock.return_value = instance
            yield instance

    @pytest.fixture
    def plugin_dir(self, tmp_path, mock_logger):
        """Create a temporary plugin directory."""
        return tmp_path

    # ------------------------------------------------------------------
    # Test 1: File absent -> generates UUID, saves to .plugin_info.json
    # ------------------------------------------------------------------
    def test_load_or_create_id_file_absent_generates_uuid_and_saves(self, plugin_dir, mock_logger):
        """
        When the info file does not exist, load_or_create_id() should:
        - Generate a new UUID
        - Save it to .plugin_info.json
        - Return the generated UUID
        """
        identity = PluginIdentity(plugin_dir)

        result = identity.load_or_create_id()

        # Verify a valid UUID was generated and returned
        uuid.UUID(result)  # raises if not a valid UUID

        # Verify file was created
        assert identity.info_file.exists()

        # Verify file content
        with open(identity.info_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["plugin_id"] == result
        assert "registered_at" in data
        assert identity.plugin_id == result

    # ------------------------------------------------------------------
    # Test 2: File present with valid data -> loads UUID, does NOT regenerate
    # ------------------------------------------------------------------
    def test_load_or_create_id_file_present_loads_existing_uuid(self, plugin_dir, mock_logger):
        """
        When the info file exists with valid data, load_or_create_id() should:
        - Load the existing UUID from the file
        - NOT generate a new one
        - Return the loaded UUID
        """
        existing_uuid = str(uuid.uuid4())
        existing_registered = "2024-01-15T10:30:00"

        info_file = plugin_dir / ".plugin_info.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump({"plugin_id": existing_uuid, "registered_at": existing_registered}, f)

        identity = PluginIdentity(plugin_dir)
        result = identity.load_or_create_id()

        assert result == existing_uuid
        assert identity.plugin_id == existing_uuid

    # ------------------------------------------------------------------
    # Test 3: File present with corrupted JSON -> logs warning, generates new UUID
    # ------------------------------------------------------------------
    def test_load_or_create_id_corrupted_json_generates_new_uuid(self, plugin_dir, mock_logger):
        """
        When the info file contains corrupted JSON, load_or_create_id() should:
        - Log a warning
        - Generate a new UUID (since _plugin_id will be None after load failure)
        - Save the new UUID to the file
        """
        info_file = plugin_dir / ".plugin_info.json"
        info_file.write_text("{ this is not valid json }", encoding="utf-8")

        identity = PluginIdentity(plugin_dir)
        result = identity.load_or_create_id()

        # A new UUID should have been generated
        uuid.UUID(result)

        # File should now contain the new UUID
        with open(info_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["plugin_id"] == result

        # Warning should have been logged
        mock_logger.warning.assert_called()

    # ------------------------------------------------------------------
    # Test 4: regenerate_id() creates new UUID, overwrites file
    # ------------------------------------------------------------------
    def test_regenerate_id_creates_new_uuid_and_overwrites_file(self, plugin_dir, mock_logger):
        """
        regenerate_id() should:
        - Generate a brand-new UUID different from any existing one
        - Overwrite the existing file with the new UUID
        - Return the new UUID
        """
        # First create an initial identity
        identity = PluginIdentity(plugin_dir)
        first_uuid = identity.load_or_create_id()

        # Regenerate
        new_uuid = identity.regenerate_id()

        # Verify it's a valid UUID
        uuid.UUID(new_uuid)

        # Verify it's different from the first one
        assert new_uuid != first_uuid

        # Verify file was updated
        with open(identity.info_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert data["plugin_id"] == new_uuid

        # Verify property returns the new UUID
        assert identity.plugin_id == new_uuid

    # ------------------------------------------------------------------
    # Test 5: registered_at parsed from ISO format string correctly
    # ------------------------------------------------------------------
    def test_registered_at_parsed_from_iso_format(self, plugin_dir, mock_logger):
        """
        When loading from a valid file, registered_at should be parsed
        from the ISO format string into a datetime object.
        """
        expected_registered = "2024-06-20T08:45:30.123456"
        existing_uuid = str(uuid.uuid4())

        info_file = plugin_dir / ".plugin_info.json"
        with open(info_file, "w", encoding="utf-8") as f:
            json.dump({"plugin_id": existing_uuid, "registered_at": expected_registered}, f)

        identity = PluginIdentity(plugin_dir)
        identity.load_or_create_id()

        assert identity.registered_at is not None
        assert identity.registered_at.isoformat() == expected_registered

    # ------------------------------------------------------------------
    # Test 6: plugin_id property returns the loaded/generated UUID
    # ------------------------------------------------------------------
    def test_plugin_id_property_returns_correct_uuid(self, plugin_dir, mock_logger):
        """
        The plugin_id property should return whatever UUID was loaded
        or generated by load_or_create_id().
        """
        identity = PluginIdentity(plugin_dir)

        # Before loading, should be None
        assert identity.plugin_id is None

        result = identity.load_or_create_id()

        # After loading, should match the returned value
        assert identity.plugin_id == result
