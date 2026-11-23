"""
utils/themes.py 单元测试

- detect_system_theme 覆盖 Windows 注册表成功/失败、非 Windows 平台。
- set_style_qss_theme / set_light_theme 验证其正确委托给底层实现，
  不实际修改全局 QApplication 样式。
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import utils.themes as themes


def test_detect_system_theme_returns_light_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert themes.detect_system_theme() == "light"


def test_detect_system_theme_dark_on_windows(monkeypatch, mocker):
    monkeypatch.setattr(sys, "platform", "win32")
    mock_winreg = mocker.MagicMock()
    mock_winreg.QueryValueEx.return_value = (0, 1)  # AppsUseLightTheme == 0 => dark
    mocker.patch.dict("sys.modules", {"winreg": mock_winreg})

    assert themes.detect_system_theme() == "dark"
    mock_winreg.OpenKey.assert_called_once_with(
        mock_winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
    )
    mock_winreg.CloseKey.assert_called_once()


def test_detect_system_theme_light_on_windows(monkeypatch, mocker):
    monkeypatch.setattr(sys, "platform", "win32")
    mock_winreg = mocker.MagicMock()
    mock_winreg.QueryValueEx.return_value = (1, 1)
    mocker.patch.dict("sys.modules", {"winreg": mock_winreg})

    assert themes.detect_system_theme() == "light"


def test_detect_system_theme_fallback_on_registry_error(monkeypatch, mocker):
    monkeypatch.setattr(sys, "platform", "win32")
    mock_winreg = mocker.MagicMock()
    mock_winreg.OpenKey.side_effect = OSError("registry access denied")
    mocker.patch.dict("sys.modules", {"winreg": mock_winreg})

    assert themes.detect_system_theme() == "light"


def test_set_style_qss_theme_delegates_to_internal_function(mocker, qapp_instance):
    mock_set = mocker.patch("utils.themes._set_style_qss_theme")
    themes.set_style_qss_theme(qapp_instance, "dark")
    mock_set.assert_called_once_with(qapp_instance, theme="dark")


def test_set_style_qss_theme_auto_delegates_without_local_detection(
    mocker, qapp_instance
):
    """utils.themes.set_style_qss_theme 不自行解析 auto，直接透传。"""
    mock_set = mocker.patch("utils.themes._set_style_qss_theme")
    themes.set_style_qss_theme(qapp_instance, "auto")
    mock_set.assert_called_once_with(qapp_instance, theme="auto")


def test_set_style_qss_theme_default_is_auto(mocker, qapp_instance):
    mock_set = mocker.patch("utils.themes._set_style_qss_theme")
    themes.set_style_qss_theme(qapp_instance)
    mock_set.assert_called_once_with(qapp_instance, theme="auto")


def test_set_light_theme_delegates_to_internal_function(mocker, qapp_instance):
    """set_light_theme 为 utils.style_qss 的兼容 re-export，内部委托 set_style_qss_theme。"""
    mock_set = mocker.patch("utils.style_qss.set_style_qss_theme")
    themes.set_light_theme(qapp_instance)
    mock_set.assert_called_once_with(qapp_instance, "light")
