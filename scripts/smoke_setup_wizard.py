# -*- coding: utf-8 -*-
"""安装向导（原生版）冒烟测试。

覆盖（不需要联网、不修改真实环境）：

1. 文案完整性：中英键集合一致、无空文案、无残留 `{占位符}`；
2. 脚本存在与编码约束：`setup.ps1` 为 UTF-8 with BOM，且两个脚本正文均为纯 ASCII；
3. 界面一致性：两个脚本的菜单键/页面键、状态字段名、规则线宽度一致；
4. 渲染一致性：分别用 Windows PowerShell 与 Git Bash 渲染全部页面并逐行比对
   （只允许平台名与路径风格不同）；
5. 体检与状态导出：`--check` 退出码语义正确，`--state` 字段齐备；
6. 干跑安全：`--action install --dry-run --yes` 只展示命令、退出码 0、不创建 `.venv`；
7. 无 Python 残留：Python 版向导文件已移除（向导本身不依赖 Python）。

运行方式（工作目录 = 项目根）：
    .venv\\Scripts\\python.exe scripts\\smoke_setup_wizard.py
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

POWERSHELL = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")
GIT_BASH = Path(r"C:\Program Files\Git\bin\bash.exe")

#: 需要逐行比对渲染结果的页面（不含依赖实时环境的取值差异）
PREVIEW_PAGES = ("menu", "language", "help", "cleanup")

#: 状态导出必须包含的字段（两平台同名）
STATE_FIELDS = (
    "project_root", "uv_path", "uv_version", "venv_exists", "python_exists",
    "python_version", "framework_version", "has_lock", "has_requirements",
    "git_available", "git_branch", "git_commit", "git_dirty", "venv_bytes",
    "platform", "missing_imports", "env_ready",
)

#: 允许中英文案完全相同的键（语言中立：通用缩写与双语菜单项）
SAME_TEXT_ALLOWED = {"common.ok", "menu.language", "lang.name.zh", "lang.name.en"}

#: 渲染比对时忽略的行（平台名与路径风格天然不同）
IGNORE_LINE = re.compile(r"Windows |macOS |^ ?[A-Z]:\\|^ ?/")

_passed = 0
_failed = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    """记录一项断言"""
    global _passed, _failed
    if condition:
        _passed += 1
        print(f"  [PASS] {name}")
    else:
        _failed += 1
        print(f"  [FAIL] {name} {detail}")


def load_text(lang: str) -> dict:
    """读取 setup_text/<lang>.txt"""
    table = {}
    path = ROOT / "setup_text" / f"{lang}.txt"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\r")
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        table[key.strip()] = value
    return table


def script_body(path: Path) -> str:
    """读取脚本正文（去掉 UTF-8 BOM）"""
    return path.read_text(encoding="utf-8-sig")


def run_command(argv: list, timeout: int = 300) -> subprocess.CompletedProcess:
    """执行命令并返回结果（文本模式，UTF-8 解码）"""
    return subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def powershell_args(*extra: str) -> list:
    """构造 Windows PowerShell 调用参数"""
    return [str(POWERSHELL), "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ROOT / "setup.ps1"), *extra]


def bash_available() -> bool:
    """Git Bash 是否可用（用于 macOS 脚本的等价验证）"""
    if not GIT_BASH.is_file():
        return False
    try:
        return run_command([str(GIT_BASH), "-c", "echo ok"], timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_entry_scripts(bash: bool) -> None:
    """2.1 双击入口的编码与可执行性（cmd 对 BOM / 纯 LF 都敏感）"""
    print("== 2.1 双击入口 ==")
    bat = ROOT / "setup.bat"
    bat_bytes = bat.read_bytes()
    check("setup.bat 无 BOM", bat_bytes[:3] != b"\xef\xbb\xbf")
    check("setup.bat 为 CRLF 行尾（cmd 要求）", b"\r\n" in bat_bytes)
    check("setup.bat 纯 ASCII",
          not any(byte > 127 for byte in bat_bytes))
    command = ROOT / "setup.command"
    command_bytes = command.read_bytes()
    check("setup.command 无 BOM", command_bytes[:3] != b"\xef\xbb\xbf")
    check("setup.command 以 shebang 开头", command_bytes.startswith(b"#!/bin/bash"))
    check("setup.command 为 LF 行尾（bash 要求）", b"\r\n" not in command_bytes)
    if POWERSHELL.is_file():
        result = run_command(["cmd", "/c", "setup.bat", "-Check"], timeout=300)
        check("cmd 双击入口可运行（-Check 退出码 0）", result.returncode == 0,
              f"exit={result.returncode}")
    if bash:
        result = run_command([str(GIT_BASH), str(ROOT / "setup.command"), "--check",
                              "--lang", "zh", "--no-color"], timeout=300)
        check("setup.command 可运行（--check 退出码 0 或 1）", result.returncode in (0, 1),
              f"exit={result.returncode}")


def check_text_tables() -> None:
    """1. 文案完整性"""
    print("== 1. 文案完整性 ==")
    zh, en = load_text("zh"), load_text("en")
    check("中英键集合一致", set(zh) == set(en),
          f"zh 独有 {sorted(set(zh) - set(en))[:5]} / en 独有 {sorted(set(en) - set(zh))[:5]}")
    empty = [key for key in sorted(zh) if not zh[key].strip() or not en[key].strip()]
    check("无空文案", not empty, str(empty[:5]))
    identical = {key for key in zh if zh[key] == en[key]}
    check("中英文案确有区分（白名单除外）", identical <= SAME_TEXT_ALLOWED,
          str(sorted(identical - SAME_TEXT_ALLOWED)[:5]))
    placeholder = re.compile(r"\{([a-z_]+)\}")
    known = {"python", "cmd", "url", "detail", "count", "path", "name", "code", "seconds",
             "items", "platform", "advice", "version", "exe"}
    stray = [f"{key}:{match}" for key in zh for match in placeholder.findall(zh[key])
             if match not in known]
    check("无未知占位符", not stray, str(stray[:5]))


def code_part(line: str) -> str:
    """取一行的代码部分（去掉行尾注释；两平台脚本的注释都在行内或独立成行）"""
    stripped = line.strip()
    if stripped.startswith("<#") or stripped.startswith("#"):
        return ""
    return line.split("#", 1)[0]


def non_ascii_code_lines(text: str) -> list:
    """脚本正文（代码部分）中的非 ASCII 行号

    注释允许中文；正文必须纯 ASCII —— Windows PowerShell 5.1 用系统代码页解码无 BOM 的
    .ps1，正文里的中文会变成乱码（这是本项目实际踩过的坑），因此把「正文纯 ASCII」纳入守卫。
    """
    result = []
    in_block = False
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("<#"):
            in_block = True
        if in_block:
            if stripped.endswith("#>"):
                in_block = False
            continue
        if any(ord(char) > 127 for char in code_part(line)):
            result.append(number)
    return result


def check_scripts() -> None:
    """2/3. 脚本存在、编码约束与界面常量一致"""
    print("== 2. 脚本与编码约束 ==")
    ps1, sh = ROOT / "setup.ps1", ROOT / "setup.sh"
    for path in (ps1, sh, ROOT / "setup.bat", ROOT / "setup.command"):
        check(f"{path.name} 存在", path.is_file())
    check("setup.ps1 为 UTF-8 with BOM", ps1.read_bytes()[:3] == b"\xef\xbb\xbf")

    ps_body = script_body(ps1)
    sh_text = sh.read_text(encoding="utf-8")
    check("setup.ps1 正文纯 ASCII", not non_ascii_code_lines(ps_body),
          str(non_ascii_code_lines(ps_body)[:5]))
    check("setup.sh 正文纯 ASCII", not non_ascii_code_lines(sh_text),
          str(non_ascii_code_lines(sh_text)[:5]))

    print("== 3. 界面常量一致 ==")
    check("规则线宽度一致",
          "RULE_WIDTH=78" in sh_text and "$Script:RuleWidth = 78" in ps_body)
    menu_pattern = r"menu\.(status|install|upgrade|manage|doctor|cleanup|launch|language|help)"
    ps_keys = re.findall(menu_pattern, ps_body)
    sh_keys = re.findall(menu_pattern, sh_text)
    ordered_ps = list(dict.fromkeys(ps_keys))
    ordered_sh = list(dict.fromkeys(sh_keys))
    expected = ["status", "install", "upgrade", "manage", "doctor", "cleanup", "launch",
                "language", "help"]
    check("菜单项顺序两平台一致且完整", ordered_sh == expected and set(ordered_ps) == set(expected),
          f"win={ordered_ps} / posix={ordered_sh}")
    check("页面渲染函数两平台一一对应",
          all(f"Show-{name}Page" in ps_body for name in
              ("Status", "Install", "Upgrade", "Manage", "Doctor", "Cleanup", "Launch",
               "Language", "Help"))
          and all(f"show_{name}_page" in sh_text for name in
                  ("status", "install", "upgrade", "manage", "doctor", "cleanup", "launch",
                   "language", "help")))
    check("非交互动作集合一致",
          all(name in ps_body for name in ("install", "repair", "upgrade", "doctor",
                                           "clean-temp", "uninstall"))
          and all(name in sh_text for name in ("install", "repair", "upgrade", "doctor",
                                               "clean-temp", "uninstall")))
    print("== 3.1 uv 命令口径 ==")
    check("初次安装使用 uv sync（排除 dev 与项目自身）",
          "'sync', '--no-dev', '--no-install-project'" in ps_body
          and "sync --no-dev --no-install-project" in sh_text)
    check("修复使用依赖清单增量安装",
          "'pip', 'install', '-r', 'requirements.txt'" in ps_body
          and "pip install -r requirements.txt" in sh_text)
    check("锁文件不可用时回退到依赖清单",
          "Test-LockUsable" in ps_body and "is_lock_usable" in sh_text)
    check("子进程工作目录固定为项目根",
          "Push-Location -LiteralPath $Script:ProjectRoot" in ps_body
          and 'cd "$PROJECT_ROOT" &&' in sh_text)
    print("== 3.2 升级安全契约 ==")
    preserve_win = re.search(r"PreserveDirs\s*=\s*@\(([^)]*)\)", ps_body)
    preserve_nix = re.search(r'PRESERVE_DIRS="([^"]*)"', sh_text)
    win_names = sorted(re.findall(r"'([^']+)'", preserve_win.group(1))) if preserve_win else []
    nix_names = sorted(preserve_nix.group(1).split()) if preserve_nix else []
    check("升级保护清单两平台一致", win_names and win_names == nix_names,
          f"win={win_names} / posix={nix_names}")
    check("保护清单覆盖用户数据与本地环境",
          {"config", "data", "logs", "plugin", "custom_plugin", ".venv", ".tui",
           "temp"} <= set(win_names))
    skip_win = re.search(r"SkipDirs\s*=\s*@\(([^)]*)\)", ps_body)
    skip_nix = re.search(r'SKIP_DIRS="([^"]*)"', sh_text)
    check("仓库元数据跳过清单两平台一致",
          bool(skip_win) and bool(skip_nix)
          and sorted(re.findall(r"'([^']+)'", skip_win.group(1))) == sorted(skip_nix.group(1).split()))
    check("目录覆盖用显式合并（避免 core/core 错位）",
          "function Copy-DirectoryMerge" in ps_body
          and "不能用 ``Copy-Item -Recurse``" in ps_body)
    check("支持本地压缩包离线升级",
          "[string]$ArchivePath" in ps_body and 'OPT_ARCHIVE' in sh_text)
    check("解压具备多工具回退（unzip/ditto/tar）",
          all(name in sh_text for name in ("unzip -q", "ditto -x -k", "tar -xf"))
          and "Expand-Archive" in ps_body)
    check("解压容忍 unzip 的警告退出码",
          'if [ "$code" -le 1 ]' in sh_text)
    print("== 3.3 桌面快捷方式 ==")
    check("快捷方式创建/删除两平台成对存在",
          "Install-DesktopShortcut" in ps_body and "Remove-DesktopShortcut" in ps_body
          and "create_desktop_launcher" in sh_text and "remove_desktop_launcher" in sh_text)
    check("Windows 用 pythonw 启动（双击无控制台窗口）", "pythonw.exe" in ps_body)
    check("macOS 用 .app 启动器（双击不开 Terminal）",
          "InstructionX.app" in sh_text and "CFBundleExecutable" in sh_text)
    check("快捷方式含软件 Logo（ico 直接引用 / png 转 icns）",
          "logo.ico" in ps_body and "iconutil" in sh_text and "logo.png" in sh_text)
    check("首次安装成功才创建（两平台挂接一致）",
          "if ($first) { [void](Install-DesktopShortcut) }" in ps_body
          and '"$first" = "1"' in sh_text)
    check("卸载流程挂接快捷方式删除（定义之外至少一处调用）",
          ps_body.count("Remove-DesktopShortcut") >= 2
          and sh_text.count("remove_desktop_launcher") >= 2)
    check("环境管理页提供重建快捷方式动作（两平台一致）",
          "Invoke-RecreateShortcut" in ps_body and "run_recreate_shortcut" in sh_text)
    check("重建动作挂接在相同编号（管理页第 7 项）",
          "elseif ($Key -eq '7') { Invoke-RecreateShortcut }" in ps_body
          and "manage:7) run_recreate_shortcut" in sh_text)


def check_python_removed() -> None:
    """7. Python 版向导已移除"""
    print("== 7. 无 Python 向导残留 ==")
    for name in ("tui_setup.py", "tools/tui", "scripts/smoke_tui_setup.py"):
        check(f"已移除 {name}", not (ROOT / name).exists())
    check("入口不经过 Python",
          "python" not in (ROOT / "setup.bat").read_text(encoding="utf-8").lower()
          or "python.exe" not in (ROOT / "setup.bat").read_text(encoding="utf-8").lower())
    check("setup.command 直接调用 bash",
          "/bin/bash" in (ROOT / "setup.command").read_text(encoding="utf-8"))


def check_state_and_check() -> None:
    """5. 状态导出与文本体检"""
    print("== 5. 状态导出与体检 ==")
    result = run_command(powershell_args("-State", "-Lang", "zh", "-NoColor"))
    fields = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            fields[key.strip()] = value.strip()
    missing = [name for name in STATE_FIELDS if name not in fields]
    check("状态字段齐备", not missing, str(missing))
    check("状态值自洽",
          fields.get("framework_version", "") != ""
          and fields.get("env_ready") in ("True", "False"))

    check_result = run_command(powershell_args("-Check", "-Lang", "zh", "-NoColor"))
    lines = [line for line in check_result.stdout.splitlines() if line.startswith("[")]
    check("体检 9 项", len(lines) == 9, str(len(lines)))
    check("体检退出码语义正确",
          check_result.returncode in (0, 1)
          and (check_result.returncode == 0) == all("[OK]" in line for line in lines),
          f"exit={check_result.returncode}")


def check_dry_run_safety() -> None:
    """6. 干跑安全"""
    print("== 6. 干跑安全 ==")
    venv_existed = (ROOT / ".venv" / "pyvenv.cfg").is_file()
    result = run_command(powershell_args("-Action", "install", "-Yes", "-DryRun",
                                        "-Lang", "zh", "-NoColor"))
    check("干跑安装退出码为 0", result.returncode == 0, f"exit={result.returncode}")
    check("干跑只展示命令",
          "试运行" in result.stdout or "dry run" in result.stdout.lower())
    check("干跑未改动环境", venv_existed == (ROOT / ".venv" / "pyvenv.cfg").is_file())
    check("干跑未创建升级临时目录", not (ROOT / ".tui" / "work").exists())
    uninstall = run_command(powershell_args("-Action", "uninstall", "-Yes", "-DryRun",
                                           "-Lang", "zh", "-NoColor"))
    check("干跑卸载退出码为 0", uninstall.returncode == 0, f"exit={uninstall.returncode}")
    check("干跑卸载展示快捷方式删除", "删除桌面快捷方式" in uninstall.stdout)
    check("干跑卸载未删除真实目录",
          (ROOT / "config").is_dir() and (ROOT / "data").is_dir())


def check_parity(bash: bool) -> None:
    """4. 两平台渲染一致性"""
    print("== 4. 两平台渲染一致性 ==")
    for page in PREVIEW_PAGES:
        win = run_command(powershell_args("-Preview", page, "-Lang", "zh", "-NoColor"))
        if not bash:
            check(f"{page} 页面可渲染（仅 Windows）", win.returncode == 0)
            continue
        nix = run_command([str(GIT_BASH), str(ROOT / "setup.sh"), "--preview", page,
                           "--lang", "zh", "--no-color"])
        win_lines = [line for line in win.stdout.splitlines() if not IGNORE_LINE.search(line)]
        nix_lines = [line for line in nix.stdout.splitlines() if not IGNORE_LINE.search(line)]
        check(f"{page} 页面两平台逐行一致", win_lines == nix_lines,
              f"win={len(win_lines)} 行 / posix={len(nix_lines)} 行")


def main() -> int:
    """执行全部冒烟检查"""
    print(f"项目根: {ROOT}\n")
    check_text_tables()
    check_scripts()
    if not POWERSHELL.is_file():
        print("== 4/5/6. 跳过（未找到 Windows PowerShell）==")
        check_python_removed()
        print(f"\n结果: {_passed} 通过, {_failed} 失败")
        return 1 if _failed else 0
    bash = bash_available()
    if not bash:
        print("  [注意] 未检测到可用的 Git Bash，macOS 脚本仅做静态检查\n")
    check_entry_scripts(bash)
    check_parity(bash)
    check_state_and_check()
    check_dry_run_safety()
    check_python_removed()
    print(f"\n结果: {_passed} 通过, {_failed} 失败")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
