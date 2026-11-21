# -*- coding: utf-8 -*-
"""原生 Setup 启动器、兼容 CLI 与 dry-run 安全冒烟测试。"""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
ASSET_NAMES = (
    "instructionx-setup-windows-x86_64.exe",
    "instructionx-setup-windows-aarch64.exe",
    "instructionx-setup-macos-x86_64",
    "instructionx-setup-macos-aarch64",
    "instructionx-setup-linux-x86_64",
    "instructionx-setup-linux-aarch64",
)
NATIVE = ROOT / "tools" / "setup" / ASSET_NAMES[0]
_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """记录一项断言。"""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name} {detail}")


def run_command(argv: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """执行命令并捕获 UTF-8 输出。"""
    return subprocess.run(
        argv, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout,
    )


def script_body(path: Path) -> str:
    """读取脚本正文并移除 UTF-8 BOM。"""
    return path.read_text(encoding="utf-8-sig")


def check_launchers() -> None:
    """检查薄启动器、随包资产和禁止联网回退的约定。"""
    print("== 原生启动器 ==")
    ps1 = ROOT / "setup.ps1"
    sh = ROOT / "setup.sh"
    bat = ROOT / "setup.bat"
    command = ROOT / "setup.command"
    check("setup.ps1 为 UTF-8 with BOM", ps1.read_bytes()[:3] == b"\xef\xbb\xbf")
    check("setup.ps1 正文纯 ASCII", script_body(ps1).isascii())
    check("setup.sh 正文纯 ASCII", all(byte < 128 for byte in sh.read_bytes()))
    check("setup.sh 使用 LF", b"\r\n" not in sh.read_bytes())
    check("setup.bat 使用 CRLF", b"\r\n" in bat.read_bytes())
    check("setup.command 使用 shebang", command.read_text(encoding="utf-8").startswith("#!/bin/bash"))
    for path in (ps1, sh, bat, command):
        check(f"{path.name} 存在", path.is_file())
    for legacy in ("Show-Menu", "Invoke-Upgrade", "run_upgrade", "Show-UpgradePage"):
        check(f"启动器不含旧 TUI 逻辑 {legacy}",
              legacy not in script_body(ps1) and legacy not in script_body(sh))
    check("Windows x64/ARM64 资产均已随包",
          all((ROOT / "tools" / "setup" / name).is_file() for name in ASSET_NAMES[:2]))
    check("启动器覆盖全部资产名称",
          all(name in script_body(sh) for name in ASSET_NAMES[2:])
          and all(name in script_body(ps1) for name in ASSET_NAMES[:2]))
    check("启动器只使用 tools/setup 随包文件",
          "tools\\setup" in script_body(ps1) and "tools/setup" in script_body(sh))
    check("启动器不再下载 Setup",
          all(token not in script_body(ps1) for token in ("Invoke-RestMethod", "Invoke-WebRequest"))
          and all(token not in script_body(sh) for token in ("curl", "API_URL", "download_native_setup")))


def check_native_cli() -> None:
    """检查真实原生二进制的版本、独立操作项、预览和 dry-run。"""
    print("== 原生 CLI ==")
    check("原生 Setup 已构建", NATIVE.is_file(), str(NATIVE))
    if not NATIVE.is_file():
        return
    result = run_command([str(NATIVE), "--help"])
    check("--help 可运行", result.returncode == 0 and "InstructionX native setup TUI" in result.stdout)
    result = run_command([str(NATIVE), "--version"])
    version = result.stdout.strip().rsplit(" ", 1)[-1] if result.stdout.strip() else ""
    check("--version 显示 Setup 版本", result.returncode == 0
          and result.stdout.startswith("instructionx-setup ") and bool(version))
    result = run_command([str(NATIVE), "--preview", "overview", "--lang", "en"])
    check("总览预览可运行且标题正确", result.returncode == 0
          and "Overview" in result.stdout and bool(version) and version in result.stdout
          and "BIOS" not in result.stdout)
    result = run_command([str(NATIVE), "--state"])
    check("状态输出包含 Setup 版本", result.returncode == 0
          and f"setup_version={version}\n" in result.stdout)
    result = run_command([str(NATIVE), "--preview", "misc", "--lang", "en"])
    check("杂项显示独立操作项", result.returncode == 0
          and "Create desktop shortcut" in result.stdout and "TUI language" in result.stdout)
    result = run_command([str(NATIVE), "--preview", "environment", "--lang", "en"])
    check("环境页显示独立操作项", result.returncode == 0
          and "Query package list" in result.stdout and "Rebuild environment" in result.stdout)
    with tempfile.TemporaryDirectory(prefix="setup-dry-run-", dir=ROOT / "temp") as work:
        result = run_command([
            str(NATIVE), "--action", "upgrade", "--yes", "--dry-run",
            "--release-tag", "alpha-v9.9.9", "--project-root", work,
        ])
        check("dry-run 接受 Release Tag", result.returncode == 0 and "alpha-v9.9.9" in result.stdout)
        check("dry-run 未创建下载目录", not (Path(work) / ".tui" / "work").exists())
    check_operation_feedback()


def check_operation_feedback() -> None:
    """真实操作必须显示步骤、结果并留下持久日志。"""
    print("== 进度与结果反馈 ==")
    preview = run_command([str(NATIVE), "--preview", "misc", "--lang", "en"])
    check("界面包含 Activity 区域", preview.returncode == 0 and "Activity" in preview.stdout)
    check("界面显示日志位置", "logs/tui_setup.log" in preview.stdout)
    with tempfile.TemporaryDirectory(prefix="setup-feedback-", dir=ROOT / "temp") as work:
        result = run_command([str(NATIVE), "--action", "clean-temp", "--project-root", work])
        check("CLI 显示执行步骤", result.returncode == 0 and "[1/1] Clean temporary files" in result.stdout,
              result.stdout + result.stderr)
        check("CLI 显示完成结果", "Temporary files cleaned" in result.stdout)
        log = Path(work) / "logs/tui_setup.log"
        check("操作写入持久日志", log.is_file() and "Operation completed" in log.read_text(encoding="utf-8"))
        localized_action = run_command([
            str(NATIVE), "--action", "clean-temp", "--project-root", work, "--lang", "zh",
        ])
        check("CLI 步骤与结果跟随中文", localized_action.returncode == 0
              and "清理临时文件" in localized_action.stdout
              and "临时文件已清理" in localized_action.stdout)
    localized = run_command([str(NATIVE), "--preview", "misc", "--lang", "zh"])
    compact = "".join(localized.stdout.split())
    check("Activity 状态与日志标签跟随中文", localized.returncode == 0
          and "状态：已就绪" in compact and "日志：" in compact)
    install_preview = run_command([str(NATIVE), "--preview", "install", "--lang", "zh"])
    install_compact = "".join(install_preview.stdout.split())
    check("安装页工具与空 Release 提示跟随中文", install_preview.returncode == 0
          and "工具：" in install_compact and "尚未加载Release" in install_compact
          and "Tools:" not in install_preview.stdout and "No Releases loaded" not in install_preview.stdout)


def check_wrapper_cli() -> None:
    """检查旧启动参数通过各薄启动器传到随包原生程序。"""
    print("== 兼容启动入口 ==")
    if POWERSHELL.is_file() and NATIVE.is_file():
        result = run_command([
            str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "setup.ps1"), "-Preview", "overview", "-Lang", "en",
        ])
        check("PowerShell 启动器转发预览", result.returncode == 0 and "Overview" in result.stdout)
        result = run_command([
            "cmd.exe", "/c", str(ROOT / "setup.bat"), "--preview", "overview", "--lang", "en",
        ])
        check("setup.bat 转发预览", result.returncode == 0 and "Overview" in result.stdout)
    if GIT_BASH.is_file() and NATIVE.is_file():
        result = run_command([
            str(GIT_BASH), str(ROOT / "setup.command"),
            "--preview", "overview", "--lang", "en",
        ])
        check("Unix 启动器转发预览", result.returncode == 0 and "Overview" in result.stdout)
        syntax = run_command([str(GIT_BASH), "-n", str(ROOT / "setup.sh")])
        check("setup.sh 语法正确", syntax.returncode == 0)


def check_external_working_directory() -> None:
    """从项目外启动时仍必须操作启动器所在的框架根目录。"""
    print("== 项目外启动 ==")
    with tempfile.TemporaryDirectory(prefix="setup-launcher-", dir=ROOT / "temp") as work:
        commands = []
        if POWERSHELL.is_file():
            commands.append(("PowerShell", [
                str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "setup.ps1"), "-State",
            ]))
        if GIT_BASH.is_file():
            commands.append(("Unix", [str(GIT_BASH), str(ROOT / "setup.sh"), "--state"]))
        for name, argv in commands:
            result = subprocess.run(
                argv, cwd=work, capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=120,
            )
            expected = (f"project_root={ROOT}\n", f"project_root={ROOT.as_posix()}\n")
            root_correct = any(line in result.stdout for line in expected)
            check(f"{name} 启动器固定项目根目录", result.returncode == 0 and root_correct,
                  result.stdout + result.stderr)


def main() -> int:
    """执行全部检查并返回退出码。"""
    print(f"项目根: {ROOT}\n")
    check_launchers()
    check_native_cli()
    check_wrapper_cli()
    check_external_working_directory()
    print(f"\n结果: {_passed} 通过, {_failed} 失败")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
