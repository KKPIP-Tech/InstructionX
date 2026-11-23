"""
pytest tests for core/plugin/dependency_manager.py
"""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from core.plugin.dependency_manager import (
    DependencyCheckResult,
    DependencyInstallResult,
    DependencyManager,
)


class TestDataClasses:
    """Tests for result dataclasses."""

    def test_dependency_check_result_defaults(self):
        result = DependencyCheckResult(satisfied=True, missing=[])
        assert result.satisfied is True
        assert result.missing == []

    def test_dependency_install_result_post_init(self):
        """DependencyInstallResult should initialize failed_packages to empty list."""
        result = DependencyInstallResult(success=True, message="ok")
        assert result.failed_packages == []

    def test_dependency_install_result_preserves_failed_packages(self):
        result = DependencyInstallResult(
            success=False, message="failed", failed_packages=["pkg"]
        )
        assert result.failed_packages == ["pkg"]


class TestDependencyManagerCheck:
    """Tests for DependencyManager.check_dependencies."""

    @pytest.fixture
    def manager(self):
        return DependencyManager()

    def test_empty_dependencies_returns_satisfied(self, manager):
        result = manager.check_dependencies({})
        assert result.satisfied is True
        assert result.missing == []

    def test_all_dependencies_satisfied(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=True)

        result = manager.check_dependencies({"pkg1": ">=1.0", "pkg2": ""})
        assert result.satisfied is True
        assert result.missing == []

    def test_some_dependencies_missing(self, manager, mocker):
        mocker.patch.object(
            manager, "_is_package_installed", side_effect=lambda pkg, _: pkg == "pkg1"
        )

        result = manager.check_dependencies({"pkg1": ">=1.0", "pkg2": ""})
        assert result.satisfied is False
        assert result.missing == ["pkg2"]

    def test_all_dependencies_missing(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=False)

        result = manager.check_dependencies({"pkg1": ">=1.0", "pkg2": ">=2.0"})
        assert result.satisfied is False
        assert sorted(result.missing) == ["pkg1", "pkg2"]


class TestDependencyManagerGetMissing:
    """Tests for DependencyManager.get_missing_dependencies."""

    def test_returns_missing_package_names(self, mocker):
        manager = DependencyManager()
        mocker.patch.object(
            manager, "_is_package_installed", side_effect=lambda pkg, _: pkg == "found"
        )

        missing = manager.get_missing_dependencies(
            {"found": ">=1.0", "missing": ">=2.0"}
        )
        assert missing == ["missing"]


class TestDependencyManagerInstall:
    """Tests for DependencyManager.install_dependencies."""

    @pytest.fixture
    def manager(self):
        return DependencyManager()

    def test_empty_dependencies(self, manager):
        result = manager.install_dependencies({})
        assert result.success is True
        assert result.message == "无依赖需要安装"

    def test_already_satisfied(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=True)

        result = manager.install_dependencies({"pkg1": ">=1.0"})
        assert result.success is True
        assert result.message == "所有依赖已满足"

    def test_successful_install(self, manager, mocker):
        mocker.patch.object(
            manager, "_is_package_installed", side_effect=lambda pkg, _: pkg == "already"
        )
        pip_mock = mocker.patch.object(manager, "_pip_install", return_value=True)

        result = manager.install_dependencies(
            {"already": ">=1.0", "new": ">=2.0", "noversion": ""}
        )

        assert result.success is True
        assert "成功安装" in result.message
        pip_mock.assert_any_call("new>=2.0")
        pip_mock.assert_any_call("noversion")

    def test_partial_failure(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=False)
        mocker.patch.object(
            manager, "_pip_install", side_effect=lambda spec: spec == "ok>=1.0"
        )

        result = manager.install_dependencies({"ok": ">=1.0", "fail": ">=2.0"})

        assert result.success is False
        assert "fail>=2.0" in result.failed_packages

    def test_callback_invoked(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=False)
        mocker.patch.object(manager, "_pip_install", return_value=True)
        callback = mocker.MagicMock()

        manager.install_dependencies({"pkg": ">=1.0"}, callback=callback)

        callback.assert_any_call("开始安装依赖: pkg>=1.0")
        callback.assert_any_call("正在安装 pkg>=1.0...")
        callback.assert_any_call("已安装: pkg>=1.0")

    def test_callback_failure_message(self, manager, mocker):
        mocker.patch.object(manager, "_is_package_installed", return_value=False)
        mocker.patch.object(manager, "_pip_install", return_value=False)
        callback = mocker.MagicMock()

        manager.install_dependencies({"pkg": ">=1.0"}, callback=callback)

        callback.assert_any_call("安装失败: pkg>=1.0")


class TestDependencyManagerIsPackageInstalled:
    """Tests for DependencyManager._is_package_installed."""

    @pytest.fixture
    def manager(self):
        return DependencyManager()

    def test_installed_no_constraint(self, manager, mocker):
        run_mock = mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="Version: 1.0.0\n"),
        )

        assert manager._is_package_installed("pkg", "") is True
        run_mock.assert_called_once_with(
            [sys.executable, "-m", "pip", "show", "pkg"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_not_installed(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="not found"),
        )

        assert manager._is_package_installed("pkg", ">=1.0") is False

    def test_installed_with_constraint_satisfied(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="Version: 2.0.0\n"),
        )

        assert manager._is_package_installed("pkg", ">=1.5") is True

    def test_installed_with_constraint_not_satisfied(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="Version: 1.0.0\n"),
        )

        assert manager._is_package_installed("pkg", ">=1.5") is False

    def test_installed_version_parse_failure(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="No version line\n"),
        )

        assert manager._is_package_installed("pkg", ">=1.0") is False

    def test_timeout(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip show", timeout=30),
        )

        assert manager._is_package_installed("pkg", "") is False

    def test_exception_during_check(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            side_effect=OSError("cannot run pip"),
        )

        assert manager._is_package_installed("pkg", "") is False


class TestDependencyManagerParseVersion:
    """Tests for DependencyManager._parse_version_from_pip_show."""

    def test_parses_version_line(self):
        manager = DependencyManager()
        output = "Name: pkg\nVersion: 1.2.3\nSummary: test"
        assert manager._parse_version_from_pip_show(output) == "1.2.3"

    def test_missing_version_returns_none(self):
        manager = DependencyManager()
        assert manager._parse_version_from_pip_show("Name: pkg\n") is None


class TestDependencyManagerVersionConstraint:
    """Tests for DependencyManager._check_version_constraint."""

    @pytest.fixture
    def manager(self):
        return DependencyManager()

    @pytest.mark.parametrize(
        "installed,constraint,expected",
        [
            ("2.0.0", ">=1.0", True),
            ("1.0.0", ">=1.0", True),
            ("0.9.0", ">=1.0", False),
            ("2.0.0", ">1.0", True),
            ("1.0.0", ">1.0", False),
            ("1.0.0", "<=1.0", True),
            ("1.1.0", "<=1.0", False),
            ("0.9.0", "<1.0", True),
            ("1.0.0", "<1.0", False),
            ("1.0.0", "==1.0", True),
            ("1.0.1", "==1.0", False),
            ("1.0.1", "!=1.0", True),
            ("1.0.0", "!=1.0", False),
            ("1.0.0.post1", ">=1.0", True),
            ("1.0.0a1", ">=1.0", True),
        ],
    )
    def test_operators(self, manager, installed, constraint, expected):
        assert manager._check_version_constraint(installed, constraint) == expected

    def test_unparseable_constraint(self, manager, mocker):
        logger_mock = mocker.MagicMock()
        mocker.patch.object(manager, "_logger", logger_mock)

        assert manager._check_version_constraint("1.0.0", "~=1.0") is False
        logger_mock.warning.assert_called_once()

    def test_normalize_version_none(self, manager):
        assert manager._normalize_version("not-a-version") is None


class TestDependencyManagerPipInstall:
    """Tests for DependencyManager._pip_install."""

    @pytest.fixture
    def manager(self):
        return DependencyManager()

    def test_success(self, manager, mocker):
        run_mock = mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        )

        assert manager._pip_install("pkg>=1.0") is True
        run_mock.assert_called_once_with(
            [sys.executable, "-m", "pip", "install", "pkg>=1.0", "--quiet"],
            capture_output=True,
            text=True,
            timeout=300,
        )

    def test_failure(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            return_value=MagicMock(returncode=1, stdout="", stderr="installation failed"),
        )

        assert manager._pip_install("pkg>=1.0") is False

    def test_timeout(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pip install", timeout=300),
        )

        assert manager._pip_install("pkg>=1.0") is False

    def test_exception(self, manager, mocker):
        mocker.patch(
            "core.plugin.dependency_manager.subprocess.run",
            side_effect=OSError("cannot run pip"),
        )

        assert manager._pip_install("pkg>=1.0") is False

