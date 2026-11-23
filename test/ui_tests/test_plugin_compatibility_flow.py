"""三个插件安装入口的兼容性提示集成测试。"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel

from core.plugin.framework_compatibility import evaluate_framework_compatibility
from core.plugin.github_plugin_installer import (
    LocalInstallPlan,
    LocalPackageInspection,
    PluginInfo,
    ReleaseInfo,
    RepoInspectionResult,
)
from core.plugin.package_discovery import PluginCandidate
from core.version import APP_VERSION
from ui.dialog import github_plugin_install_dialog as github_module
from ui.dialog import local_package_install_dialog as local_module
from ui.dialog import plugin_management_dialog as management_module
from ui.dialog.github_plugin_install_dialog import PluginInfoWidget
from ui.dialog.local_package_install_dialog import LocalPackageInstallDialog
from ui.dialog.plugin_management_dialog import PluginManagementDialog


CURRENT = APP_VERSION.to_string()


def _compatibility(versions):
    """构造当前框架的真实兼容性结果；None 表示旧数据模型。"""
    if versions is None:
        return None
    return evaluate_framework_compatibility({"compatible_framework_versions": versions})


def _plugin(name, path="", versions=None):
    """构造仓库插件信息。"""
    return PluginInfo(
        plugin_id=name.lower(), name=name, version="release.1.0.0",
        main="entrance.py", path=path,
        framework_compatibility=_compatibility(versions),
    )


def _local_dialog(qtbot, name="Legacy", versions=None):
    """构造带一个本地安装计划的真实对话框。"""
    dialog = LocalPackageInstallDialog(installer=MagicMock())
    qtbot.addWidget(dialog)
    candidate = PluginCandidate(
        descriptor_id=name.lower(), name=name, version="release.1.0.0",
        main="entrance.py", framework_compatibility=_compatibility(versions),
    )
    plan = LocalInstallPlan(candidate=candidate, default_selected=True)
    dialog._on_inspect_finished(LocalPackageInspection(kind="single", plans=[plan]))
    return dialog


@pytest.fixture
def github_dialog(qtbot, mocker):
    """构造公共单插件安装对话框，屏蔽既有私有仓库确认。"""
    mocker.patch.object(github_module, "GitHubPluginInstaller", return_value=MagicMock())
    manager = MagicMock()
    manager.list_keys.return_value = []
    dialog = github_module.GitHubPluginInstallDialog(key_manager=manager)
    qtbot.addWidget(dialog)
    dialog.url_input.setText("https://github.com/acme/plugins")
    dialog._confirm_private_install = MagicMock(return_value=True)
    return dialog


def test_github_details_show_declared_framework_versions(qtbot):
    """GitHub 详情必须显示作者声明的全部框架版本。"""
    widget = PluginInfoWidget(_plugin("Demo", versions=["alpha.1.0.0", CURRENT]))
    qtbot.addWidget(widget)

    text = "\n".join(label.text() for label in widget.findChildren(QLabel))

    assert "alpha.1.0.0" in text and CURRENT in text


def test_github_cancel_unverified_never_starts_worker(github_dialog, mocker):
    """用户取消未验证提示时不得创建 GitHub 安装线程。"""
    github_dialog.repo_result = RepoInspectionResult.single(_plugin("Legacy"))
    confirm = mocker.patch.object(
        github_module, "confirm_unverified_compatibility",
        return_value=False, raising=False)
    worker = mocker.patch.object(github_module, "GitHubInstallWorker")

    github_dialog._on_install()

    confirm.assert_called_once()
    worker.assert_not_called()


def test_github_force_install_starts_worker(github_dialog, mocker):
    """用户明确选择仍然安装后才创建安装线程。"""
    github_dialog.repo_result = RepoInspectionResult.single(_plugin("Legacy"))
    confirm = mocker.patch.object(
        github_module, "confirm_unverified_compatibility",
        return_value=True, raising=False)
    worker = mocker.patch.object(github_module, "GitHubInstallWorker")

    github_dialog._on_install()

    confirm.assert_called_once()
    worker.assert_called_once()


def test_github_multi_only_confirms_checked_plugins(github_dialog, mocker):
    """插件集确认清单不能包含未勾选插件。"""
    first = _plugin("First", path="first", versions=[CURRENT])
    second = _plugin("Second", path="second")
    github_dialog.repo_result = RepoInspectionResult.multi([first, second])
    github_dialog._show_multi_plugins([first, second])
    github_dialog.plugin_checkboxes[1].setChecked(False)
    confirm = mocker.patch.object(
        github_module, "confirm_unverified_compatibility",
        return_value=False, raising=False)
    mocker.patch.object(github_module, "GitHubInstallWorker")

    github_dialog._on_install()

    items = confirm.call_args.args[1]
    assert [name for name, _result in items] == ["First"]


def test_local_details_show_framework_compatibility(qtbot):
    """本地包元信息应显示声明版本与当前匹配状态。"""
    dialog = _local_dialog(qtbot, versions=[CURRENT])

    text = "\n".join(label.text() for label in dialog.findChildren(QLabel))

    assert CURRENT in text


def test_local_cancel_unverified_never_starts_worker(qtbot, mocker):
    """本地包取消兼容性确认后不得启动安装线程。"""
    dialog = _local_dialog(qtbot)
    confirm = mocker.patch.object(
        local_module, "confirm_unverified_compatibility",
        return_value=False, raising=False)
    worker = mocker.patch.object(local_module, "_InstallWorker")

    dialog._on_install_clicked()

    confirm.assert_called_once()
    worker.assert_not_called()


def test_local_force_install_starts_worker(qtbot, mocker):
    """本地包允许用户明确强制安装未验证插件。"""
    dialog = _local_dialog(qtbot)
    confirm = mocker.patch.object(
        local_module, "confirm_unverified_compatibility",
        return_value=True, raising=False)
    worker = mocker.patch.object(local_module, "_InstallWorker")

    dialog._on_install_clicked()

    confirm.assert_called_once()
    worker.assert_called_once()


def _management_dialog():
    """构造 Release 安装所需的轻量对话框依赖。"""
    installer = MagicMock()
    installer.parse_github_url.return_value = ("owner", "repo")
    pm = SimpleNamespace(
        official_plugin_dir=Path("official"),
        thirdparty_plugin_dir=Path("thirdparty"),
    )
    return SimpleNamespace(
        installer=installer,
        pm=pm,
        _run_background=MagicMock(),
        _on_install_results=MagicMock(),
    )


def _release(versions=None):
    """构造带兼容性结果的 Release。"""
    return ReleaseInfo(
        tag="v2", name="V2", version="release.2.0.0",
        framework_compatibility=_compatibility(versions),
    )


def _record():
    """构造公共 Release 来源记录。"""
    return {
        "version": "release.1.0.0", "name": "Demo",
        "source_visibility": "public",
        "source_url": "https://github.com/owner/repo",
        "scope": "thirdparty", "source_path": "", "source_key_id": "",
    }


def test_release_confirmation_contains_selected_tag_compatibility(mocker):
    """Release 确认页必须附带所选 Tag 的兼容结果。"""
    dialog = _management_dialog()
    release = _release(["alpha.1.0.0"])
    confirm = mocker.patch.object(
        management_module, "confirm_installation_with_compatibility",
        return_value=False, raising=False)
    mocker.patch.object(management_module, "_confirm", return_value=False)

    PluginManagementDialog._confirm_and_install_release(
        dialog, "uuid", _record(), release)

    confirm.assert_called_once()
    assert "Demo" in confirm.call_args.args[2]
    assert confirm.call_args.args[3] is release.framework_compatibility
    dialog.installer.install_release.assert_not_called()


def test_release_force_confirmation_starts_selected_install(mocker):
    """接受含兼容性风险的确认页后仍安装用户选择的 Release。"""
    dialog = _management_dialog()
    release = _release(["alpha.1.0.0"])
    confirm = mocker.patch.object(
        management_module, "confirm_installation_with_compatibility",
        return_value=True, raising=False)
    mocker.patch.object(management_module, "_confirm", return_value=True)
    dialog._run_background.side_effect = lambda action, _success: action()

    PluginManagementDialog._confirm_and_install_release(
        dialog, "uuid", _record(), release)

    confirm.assert_called_once()
    dialog.installer.install_release.assert_called_once()
    assert dialog.installer.install_release.call_args.args[2] == "v2"
