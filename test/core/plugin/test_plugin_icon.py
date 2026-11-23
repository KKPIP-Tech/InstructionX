"""
pytest tests for core/plugin/plugin_icon.py (PluginIcon, IconType)
"""

import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QByteArray, QBuffer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QStyleFactory

from core.plugin.plugin_icon import PluginIcon, IconType


class TestIconType:
    """Tests for IconType enum."""

    def test_icon_type_values(self):
        """IconType enum members should have expected string values."""
        assert IconType.BUILTIN.value == "builtin"
        assert IconType.FILE.value == "file"
        assert IconType.RESOURCE.value == "resource"
        assert IconType.BASE64.value == "base64"
        assert IconType.NONE.value == "none"


class TestPluginIconFactories:
    """Tests for PluginIcon factory classmethods."""

    def test_builtin_factory(self):
        icon = PluginIcon.builtin("SP_FileIcon")
        assert icon.icon_type == IconType.BUILTIN
        assert icon.value == "SP_FileIcon"

    def test_from_file_factory(self):
        icon = PluginIcon.from_file("icons/icon.png")
        assert icon.icon_type == IconType.FILE
        assert icon.value == "icons/icon.png"

    def test_from_resource_factory(self):
        icon = PluginIcon.from_resource(":/icons/icon.png")
        assert icon.icon_type == IconType.RESOURCE
        assert icon.value == ":/icons/icon.png"

    def test_from_base64_factory(self):
        icon = PluginIcon.from_base64("dGVzdA==")
        assert icon.icon_type == IconType.BASE64
        assert icon.value == "dGVzdA=="

    def test_none_factory(self):
        icon = PluginIcon.none()
        assert icon.icon_type == IconType.NONE
        assert icon.value is None


@pytest.fixture
def minimal_png_bytes() -> bytes:
    """Return a minimal valid 1x1 PNG as bytes using PySide6."""
    pixmap = QPixmap(1, 1)
    pixmap.fill()
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(byte_array)


@pytest.fixture
def minimal_png_base64(minimal_png_bytes: bytes) -> str:
    """Return a minimal valid PNG encoded as base64."""
    return base64.b64encode(minimal_png_bytes).decode("ascii")


class TestPluginIconLoad:
    """Tests for PluginIcon.load_icon."""

    def test_none_type_returns_none(self):
        """IconType.NONE should always return None."""
        icon = PluginIcon(IconType.NONE)
        assert icon.load_icon() is None

    # ------------------------------------------------------------------
    # BUILTIN
    # ------------------------------------------------------------------
    def test_builtin_valid_standard_pixmap(self, qapp_instance):
        """BUILTIN with a valid QStyle.StandardPixmap name should return QIcon."""
        icon = PluginIcon(IconType.BUILTIN, "SP_FileIcon")
        result = icon.load_icon()
        assert isinstance(result, QIcon)

    def test_builtin_invalid_name_returns_none(self, qapp_instance):
        """BUILTIN with an invalid name should return None."""
        icon = PluginIcon(IconType.BUILTIN, "SP_NotARealIcon")
        assert icon.load_icon() is None

    def test_builtin_no_value_returns_none(self, qapp_instance):
        """BUILTIN without a value should return None."""
        icon = PluginIcon(IconType.BUILTIN)
        assert icon.load_icon() is None

    def test_builtin_without_qapplication(self, qapp_instance):
        """BUILTIN should work when QApplication.instance() returns None."""
        icon = PluginIcon(IconType.BUILTIN, "SP_FileIcon")
        with patch.object(QApplication, "instance", return_value=None):
            result = icon.load_icon()
        assert isinstance(result, QIcon)

    def test_builtin_style_factory_returns_none(self, qapp_instance):
        """If QStyleFactory.create returns None, BUILTIN should return None."""
        icon = PluginIcon(IconType.BUILTIN, "SP_FileIcon")
        with patch.object(QApplication, "instance", return_value=None):
            with patch.object(QStyleFactory, "create", return_value=None):
                assert icon.load_icon() is None

    # ------------------------------------------------------------------
    # FILE
    # ------------------------------------------------------------------
    def test_file_missing_without_plugin_dir_returns_none(self):
        """FILE without plugin_dir should return None."""
        icon = PluginIcon(IconType.FILE, "icons/icon.png")
        assert icon.load_icon() is None

    def test_file_missing_file_returns_none(self, tmp_path: Path):
        """FILE with a non-existent path should return None."""
        icon = PluginIcon(IconType.FILE, "icons/icon.png")
        assert icon.load_icon(plugin_dir=tmp_path) is None

    def test_file_existing_icon_returns_qicon(
        self, tmp_path: Path, minimal_png_bytes: bytes
    ):
        """FILE with an existing image file should return a QIcon."""
        icon_path = tmp_path / "icons" / "icon.png"
        icon_path.parent.mkdir(parents=True)
        icon_path.write_bytes(minimal_png_bytes)

        icon = PluginIcon(IconType.FILE, "icons/icon.png")
        result = icon.load_icon(plugin_dir=tmp_path)
        assert isinstance(result, QIcon)

    def test_file_no_value_returns_none(self, tmp_path: Path):
        """FILE without a value should return None."""
        icon = PluginIcon(IconType.FILE)
        assert icon.load_icon(plugin_dir=tmp_path) is None

    # ------------------------------------------------------------------
    # RESOURCE
    # ------------------------------------------------------------------
    def test_resource_with_value_returns_qicon(self):
        """RESOURCE with a value should return a QIcon."""
        icon = PluginIcon(IconType.RESOURCE, ":/icons/icon.png")
        result = icon.load_icon()
        assert isinstance(result, QIcon)

    def test_resource_no_value_returns_none(self):
        """RESOURCE without a value should return None."""
        icon = PluginIcon(IconType.RESOURCE)
        assert icon.load_icon() is None

    # ------------------------------------------------------------------
    # BASE64
    # ------------------------------------------------------------------
    def test_base64_valid_image_returns_qicon(self, minimal_png_base64: str):
        """BASE64 with valid PNG data should return a QIcon."""
        icon = PluginIcon(IconType.BASE64, minimal_png_base64)
        result = icon.load_icon()
        assert isinstance(result, QIcon)

    def test_base64_no_value_returns_none(self):
        """BASE64 without a value should return None."""
        icon = PluginIcon(IconType.BASE64)
        assert icon.load_icon() is None

    def test_base64_invalid_base64_returns_none(self):
        """BASE64 with malformed base64 should catch exception and return None."""
        icon = PluginIcon(IconType.BASE64, "not-valid-base64!!!")
        assert icon.load_icon() is None

    def test_base64_non_image_data_returns_none(self):
        """BASE64 with valid base64 but non-image data should return None."""
        icon = PluginIcon(
            IconType.BASE64, base64.b64encode(b"hello world").decode("ascii")
        )
        assert icon.load_icon() is None

    # ------------------------------------------------------------------
    # Exception path
    # ------------------------------------------------------------------
    def test_load_icon_exception_returns_none_and_logs(
        self, minimal_png_base64: str, mocker
    ):
        """Any unexpected exception during load_icon should be caught and return None."""
        icon = PluginIcon(IconType.BASE64, minimal_png_base64)
        logger_mock = mocker.MagicMock()
        mocker.patch.object(icon, "_logger", logger_mock)

        with patch("base64.b64decode", side_effect=RuntimeError("boom")):
            result = icon.load_icon()

        assert result is None
        logger_mock.error.assert_called_once()
