# -*- coding: utf-8 -*-
"""框架手动检查更新核心链路无网冒烟测试。

覆盖 Release Tag 解析、时间线排序、当前版本定位和指定 Tag 的更新命令。
运行方式：.venv\\Scripts\\python.exe scripts\\smoke_framework_update.py
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

from core.framework_update import FrameworkUpdateChecker, parse_release_tag
from core.framework_update.launcher import FrameworkUpdateLauncher
from core.framework_update.models import FrameworkRelease

_passed = 0
_failed = 0


def check(name: str, condition: bool) -> None:
    """记录一项检查结果。"""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
        return
    _failed += 1
    print(f"  [FAIL] {name}")


def _api_release(release_id: int, tag: str, published_at: str) -> dict:
    """构造无网 Release API 条目。"""
    return {
        "id": release_id,
        "name": tag,
        "tag_name": tag,
        "published_at": published_at,
        "prerelease": True,
        "draft": False,
        "body": "notes",
        "html_url": "https://github.com/KKPIP-Tech/InstructionX/releases",
    }


def check_release_timeline() -> None:
    """验证全部 Release 保留、时间排序和当前版本定位。"""
    api = MagicMock()
    api.list_all_releases.return_value = [
        _api_release(1, "alpha-v1.1.4", "2026-02-01T00:00:00Z"),
        _api_release(2, "alpha-v1.2.0", "2026-03-01T00:00:00Z"),
        _api_release(3, "nightly", "2026-04-01T00:00:00Z"),
    ]
    result = FrameworkUpdateChecker(api_client=api).check()
    check("Release Tag 解析", parse_release_tag("alpha-v1.2.3").to_string() == "alpha.1.2.3")
    check("Release 按时间倒序", [item.release_id for item in result.releases] == [3, 2, 1])
    check("当前版本位置正确", result.current_release_id == 1)
    check("非标准 Tag 保留展示", result.releases[0].version is None)
    check("新版本可以更新", result.can_update(2))
    check("当前版本不可更新", not result.can_update(1))


def check_update_command() -> None:
    """验证随包原生向导接收用户选择的 Tag，且不真正启动进程。"""
    with TemporaryDirectory(dir=Path("temp")) as directory:
        root = Path(directory)
        starter = MagicMock()
        runner = MagicMock(return_value=subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout="", stderr=""))
        launcher = FrameworkUpdateLauncher(
            project_root=root,
            process_starter=starter,
            status_runner=runner,
            setup_locator=lambda _name: "instructionx-setup",
        )
        release = FrameworkRelease(
            release_id=2,
            name="Alpha 1.2.0",
            tag_name="alpha-v1.2.0",
            version=parse_release_tag("alpha-v1.2.0"),
            prerelease=True,
            published_at=datetime.now(timezone.utc),
            body="notes",
            html_url="https://github.com/KKPIP-Tech/InstructionX/releases/2",
        )
        launcher.launch(release)
        command = starter.call_args.args[0]
        check("更新命令包含所选 Tag", command[command.index("--release-tag") + 1] == "alpha-v1.2.0")
        check("更新动作交给原生 Setup", command[command.index("--action") + 1] == "upgrade")
        check("更新不再依赖 PowerShell", "powershell.exe" not in command)


def main() -> int:
    """执行全部无网检查并返回进程退出码。"""
    print("== 框架 Release 时间线 ==")
    check_release_timeline()
    print("== 框架更新启动命令 ==")
    check_update_command()
    print(f"\n结果: {_passed} 通过, {_failed} 失败")
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
