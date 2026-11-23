"""框架更新启动器的安全边界与随包原生 Setup 定位测试。"""

import importlib
import subprocess
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from core.framework_update.models import FrameworkRelease, parse_release_tag
from core.version import APP_VERSION


@pytest.fixture
def launcher_module():
    """加载使用当前工作树实现的更新启动器模块。"""
    return importlib.import_module("core.framework_update.launcher")


def _release(tag: str = "alpha-v1.2.0") -> FrameworkRelease:
    """构造用于启动测试的 Release。"""
    return FrameworkRelease(
        release_id=1,
        name="Alpha 1.2.0",
        tag_name=tag,
        version=parse_release_tag(tag),
        prerelease=True,
        published_at=datetime.now(timezone.utc),
        body="notes",
        html_url="https://github.com/KKPIP-Tech/InstructionX/releases/1",
    )


def _launcher(module, tmp_path, starter=None, runner=None, locator=None):
    """创建全部外部依赖均可控的启动器。"""
    return module.FrameworkUpdateLauncher(
        project_root=tmp_path,
        process_starter=starter or MagicMock(),
        status_runner=runner or MagicMock(),
        setup_locator=locator or (lambda _name: "instructionx-setup"),
    )


class TestFrameworkUpdateLauncher:
    """验证只有明确选择更高版本时才能启动随包原生向导。"""

    def test_launches_selected_release(self, launcher_module, tmp_path):
        """启动参数必须携带用户选择的 Release Tag。"""
        starter = MagicMock()
        launcher = _launcher(launcher_module, tmp_path, starter=starter)

        launcher.launch(_release())

        command = starter.call_args.args[0]
        assert command[command.index("--release-tag") + 1] == "alpha-v1.2.0"
        assert "--action" in command and "upgrade" in command
        assert starter.call_args.kwargs["cwd"] == str(tmp_path)

    def test_rejects_same_or_older_version(self, launcher_module, tmp_path):
        """当前版本和旧版本均不得进入外部更新流程。"""
        starter = MagicMock()
        launcher = _launcher(launcher_module, tmp_path, starter=starter)

        with pytest.raises(launcher_module.UpdateLaunchError, match="不高于"):
            launcher.launch(_release(APP_VERSION.to_string().replace(".", "-v", 1)))

        starter.assert_not_called()

    def test_rejects_unparseable_version(self, launcher_module, tmp_path):
        """无法解析版本的 Release 只能浏览，不能更新。"""
        release = _release()
        object.__setattr__(release, "version", None)
        launcher = _launcher(launcher_module, tmp_path)

        with pytest.raises(launcher_module.UpdateLaunchError, match="无法识别"):
            launcher.launch(release)

    def test_blocks_dirty_tracked_files(self, launcher_module, tmp_path):
        """Git 已跟踪文件有修改时不得被压缩包覆盖。"""
        (tmp_path / ".git").mkdir()
        runner = MagicMock(return_value=subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=" M core/version.py\n", stderr=""))
        starter = MagicMock()
        launcher = _launcher(
            launcher_module, tmp_path, starter=starter, runner=runner)

        with pytest.raises(launcher_module.UpdateLaunchError, match="本地修改"):
            launcher.launch(_release())

        status_args = runner.call_args.args[0]
        assert "--untracked-files=no" in status_args
        starter.assert_not_called()

    def test_reports_process_start_failure(self, launcher_module, tmp_path):
        """外部进程启动失败应转换为领域错误，让应用继续运行。"""
        starter = MagicMock(side_effect=OSError("cannot start"))
        launcher = _launcher(launcher_module, tmp_path, starter=starter)

        with pytest.raises(launcher_module.UpdateLaunchError, match="启动安装向导失败"):
            launcher.launch(_release())

    def test_requires_bundled_native_setup(self, launcher_module, tmp_path):
        """找不到随包原生 Setup 时不得尝试启动更新。"""
        launcher = _launcher(
            launcher_module, tmp_path, locator=lambda _name: None)

        with pytest.raises(launcher_module.UpdateLaunchError, match="原生 Setup"):
            launcher.launch(_release())

    @pytest.mark.parametrize(("system", "machine", "filename"), [
        ("win32", "AMD64", "instructionx-setup-windows-x86_64.exe"),
        ("win32", "ARM64", "instructionx-setup-windows-aarch64.exe"),
        ("darwin", "x86_64", "instructionx-setup-macos-x86_64"),
        ("darwin", "arm64", "instructionx-setup-macos-aarch64"),
        ("linux", "x86_64", "instructionx-setup-linux-x86_64"),
        ("linux", "aarch64", "instructionx-setup-linux-aarch64"),
    ])
    def test_maps_every_release_architecture(
            self, launcher_module, system, machine, filename):
        """六种发布资产必须与启动器的系统和架构别名一致。"""
        assert launcher_module._bundled_setup_asset(system, machine) == filename

    def test_uses_bundled_binary_instead_of_legacy_cache(
            self, launcher_module, tmp_path, monkeypatch):
        """即使旧缓存存在，也只能返回 tools/setup 中的当前架构程序。"""
        monkeypatch.setattr(launcher_module.sys, "platform", "win32")
        monkeypatch.setattr(launcher_module.platform, "machine", lambda: "AMD64")
        bundled = tmp_path / "tools/setup/instructionx-setup-windows-x86_64.exe"
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"test")
        legacy = tmp_path / ".tui/bin/instructionx-setup.exe"
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"legacy")
        launcher = launcher_module.FrameworkUpdateLauncher(project_root=tmp_path)

        assert launcher._find_setup_binary("instructionx-setup") == str(bundled)

    def test_missing_bundled_binary_has_no_path_fallback(
            self, launcher_module, tmp_path, monkeypatch):
        """随包文件缺失时不得回退到 PATH 中来源不明的程序。"""
        monkeypatch.setattr(launcher_module.sys, "platform", "darwin")
        monkeypatch.setattr(launcher_module.platform, "machine", lambda: "arm64")
        launcher = launcher_module.FrameworkUpdateLauncher(project_root=tmp_path)

        assert launcher._find_setup_binary("instructionx-setup") is None
