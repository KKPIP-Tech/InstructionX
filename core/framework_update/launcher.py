"""在独立控制台中启动原生 Setup 执行框架 Release 升级。"""

import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from core.version import APP_VERSION

from .models import FrameworkRelease, parse_release_tag

GIT_STATUS_TIMEOUT_SECONDS = 10
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
SETUP_BINARY_NAME = "instructionx-setup"
SETUP_ASSETS = {
    ("windows", "x86_64"): "instructionx-setup-windows-x86_64.exe",
    ("windows", "aarch64"): "instructionx-setup-windows-aarch64.exe",
    ("macos", "x86_64"): "instructionx-setup-macos-x86_64",
    ("macos", "aarch64"): "instructionx-setup-macos-aarch64",
    ("linux", "x86_64"): "instructionx-setup-linux-x86_64",
    ("linux", "aarch64"): "instructionx-setup-linux-aarch64",
}


def _bundled_setup_asset(system: str, machine: str) -> Optional[str]:
    """把 Python 平台名称映射为随包 Setup 文件名。"""
    system_name = {
        "win32": "windows",
        "darwin": "macos",
    }.get(system, "linux" if system.startswith("linux") else system)
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "aarch64",
        "aarch64": "aarch64",
    }.get(machine.lower())
    return SETUP_ASSETS.get((system_name, architecture))


class UpdateLaunchError(Exception):
    """更新目标无效或原生 Setup 无法启动。"""


class FrameworkUpdateLauncher:
    """校验用户选择并启动指定 Tag 的原生升级流程。"""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        process_starter: Optional[Callable[..., Any]] = None,
        status_runner: Optional[Callable[..., Any]] = None,
        setup_locator: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        """初始化启动器；外部依赖可注入以便无副作用测试。"""
        self._project_root = project_root or Path(__file__).resolve().parents[2]
        self._process_starter = process_starter or subprocess.Popen
        self._status_runner = status_runner or subprocess.run
        self._setup_locator = setup_locator or self._find_setup_binary

    def launch(self, release: FrameworkRelease) -> None:
        """启动用户明确选择的更高版本，成功返回时不退出当前进程。

        Args:
            release: 用户在 Release 列表中选中的目标版本。

        Raises:
            UpdateLaunchError: 版本无效、本地修改可能被覆盖或进程启动失败。
        """
        self._validate_release(release)
        self._ensure_clean_tracked_files()
        command = self._build_command(release.tag_name)
        self._start_update_process(command)

    @staticmethod
    def _validate_release(release: FrameworkRelease) -> None:
        """校验目标版本可识别、高于当前版本且与 Tag 一致。"""
        if release.version is None:
            raise UpdateLaunchError("无法识别所选 Release 的版本号")
        if release.version <= APP_VERSION:
            raise UpdateLaunchError("所选版本不高于当前版本，无需更新")
        if parse_release_tag(release.tag_name) != release.version:
            raise UpdateLaunchError("Release Tag 与版本信息不一致")

    def _ensure_clean_tracked_files(self) -> None:
        """Git 安装存在已跟踪文件修改时阻止压缩包覆盖。"""
        if not (self._project_root / ".git").exists():
            return
        try:
            result = self._status_runner(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=str(self._project_root), capture_output=True, text=True,
                encoding="utf-8", errors="replace", check=False,
                timeout=GIT_STATUS_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise UpdateLaunchError(f"无法检查本地修改: {exc}") from exc
        if result.returncode != 0:
            raise UpdateLaunchError("无法检查本地修改，已取消更新")
        if result.stdout.strip():
            raise UpdateLaunchError("存在已跟踪文件的本地修改，请先自行处理后再更新")

    def _build_command(self, tag_name: str) -> list[str]:
        """构造原生 Setup 参数数组，不经过 shell。"""
        executable = self._setup_locator(SETUP_BINARY_NAME)
        if not executable:
            raise UpdateLaunchError("找不到原生 Setup 程序 instructionx-setup")
        return [
            executable, "--action", "upgrade", "--yes",
            "--release-tag", tag_name,
        ]

    def _find_setup_binary(self, name: str) -> Optional[str]:
        """只返回 tools/setup 中与当前系统和架构匹配的原生程序。"""
        asset_name = _bundled_setup_asset(sys.platform, platform.machine())
        if asset_name is None:
            return None
        candidate = self._project_root / "tools" / "setup" / asset_name
        return str(candidate) if candidate.is_file() else None

    def _start_update_process(self, command: list[str]) -> None:
        """在独立控制台启动向导，避免应用退出时终止更新进程。"""
        try:
            self._process_starter(
                command, cwd=str(self._project_root),
                creationflags=CREATE_NEW_CONSOLE, close_fds=True,
            )
        except OSError as exc:
            raise UpdateLaunchError(f"启动安装向导失败: {exc}") from exc
