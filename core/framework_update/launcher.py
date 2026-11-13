"""在独立控制台中启动框架 Release 安装向导。"""

import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from core.version import APP_VERSION

from .models import FrameworkRelease, parse_release_tag

GIT_STATUS_TIMEOUT_SECONDS = 10
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


class UpdateLaunchError(Exception):
    """更新目标无效或外部安装向导无法启动。"""


class FrameworkUpdateLauncher:
    """校验用户选择并启动指定 Tag 的外部升级流程。"""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        process_starter: Optional[Callable[..., Any]] = None,
        status_runner: Optional[Callable[..., Any]] = None,
        powershell_locator: Optional[Callable[[str], Optional[str]]] = None,
    ) -> None:
        """初始化启动器；外部依赖可注入以便无副作用测试。"""
        self._project_root = project_root or Path(__file__).resolve().parents[2]
        self._process_starter = process_starter or subprocess.Popen
        self._status_runner = status_runner or subprocess.run
        self._powershell_locator = powershell_locator or shutil.which

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
        """构造不使用 shell 的 PowerShell 参数数组。"""
        setup_script = self._project_root / "setup.ps1"
        if not setup_script.is_file():
            raise UpdateLaunchError("找不到安装向导 setup.ps1")
        powershell = self._powershell_locator("powershell.exe")
        if not powershell:
            raise UpdateLaunchError("找不到 PowerShell，无法启动安装向导")
        return [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(setup_script), "-Action", "upgrade", "-Yes",
            "-ReleaseTag", tag_name,
        ]

    def _start_update_process(self, command: list[str]) -> None:
        """在独立控制台启动向导，避免应用退出时终止更新进程。"""
        try:
            self._process_starter(
                command, cwd=str(self._project_root),
                creationflags=CREATE_NEW_CONSOLE, close_fds=True,
            )
        except OSError as exc:
            raise UpdateLaunchError(f"启动安装向导失败: {exc}") from exc
