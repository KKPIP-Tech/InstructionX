# TUI 安装向导（原生版）

> 面向**大夫 / 教师 / 艺术家**等非技术用户的安装、升级与环境管理界面。
> Windows 用 `setup.ps1`（PowerShell 5.1），macOS 用 `setup.sh`（bash 3.2），**两个脚本界面逐字一致**。
> 最后更新：2026-09-17（原生重写：向导本身不再依赖 Python）。

---

## 1. 为什么是原生脚本

向导必须在「这台电脑上**连 Python 都没有**」的机器上跑起来——否则就成了鸡生蛋问题。
因此：

- **不依赖 Python、不依赖任何第三方库**：Windows 只用系统自带的 PowerShell 5.1，
  macOS 只用系统自带的 bash 3.2 与 `curl` / `unzip` / `open`；
- **不需要预装 uv**：先征得用户同意，再用 uv 官方安装脚本装 uv，然后由 uv 准备 Python 3.14；
- Python 只在「安装」动作里被 uv 装进来，用于运行 InstructionX 应用本身；
- 界面由脚本自己绘制（ANSI 颜色 + 文字排版），不需要图形界面，SSH / 终端里同样可用。

一句话：**原生脚本负责「把 Python 请进来」，Python 负责「请进来之后的应用」。**

## 2. 启动方式

| 场景 | 操作 |
|------|------|
| Windows（推荐） | 双击 `setup.bat`（内部调用 `setup.ps1`） |
| Windows（命令行） | `powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1` |
| macOS（推荐） | 双击 `setup.command`（内部调用 `setup.sh`） |
| macOS（命令行） | `./setup.sh` |

macOS 首次双击若提示「来自身份不明的开发者」，在「系统设置 → 隐私与安全性」点「仍要打开」，
或执行：`chmod +x setup.command setup.sh && xattr -d com.apple.quarantine setup.command`。

### 2.1 命令行参数（两平台同名，便于脚本化）

| 参数 | 说明 |
|------|------|
| `--check` / `-Check` | 只做环境体检并打印文本报告，有问题时退出码为 1 |
| `--state` / `-State` | 打印环境状态（`key=value`，供排错与自动化解析） |
| `--preview PAGE` | 渲染一次指定页面后退出（`menu`/`status`/`install`/`upgrade`/`manage`/`doctor`/`cleanup`/`launch`/`language`/`help`），用于无终端环境验证与两平台一致性比对 |
| `--action NAME` | 非交互执行单个动作：`install` / `repair` / `upgrade` / `doctor` / `clean-temp` / `uninstall`（配合 `--yes`，适合脚本与远程排错） |
| `--archive FILE` / `-ArchivePath FILE` | 用**本地**代码包升级（离线/内网环境）：跳过下载，走完全相同的解压 + 覆盖 + 依赖同步流程 |
| `--dry-run` | 试运行：只展示将要执行的命令，不真正改动电脑 |
| `--yes` | 自动确认所有提问 |
| `--lang zh\|en` | 指定界面语言（默认：参数 > `.tui/lang` > 系统区域 > 英文） |
| `--no-color` | 关闭彩色输出（旧终端或日志采集） |

## 3. 界面规范（两平台必须一致）

### 3.1 文案单一来源

所有界面文字放在 **`setup_text/zh.txt`** 与 **`setup_text/en.txt`**（`key=value` 行，值内换行写作 `\n`）。
两个脚本都显式按 UTF-8 读取同一份数据，所以：

- 改文案只改一处，两平台同步生效；
- 脚本正文保持**纯 ASCII**（装饰字符用码位/字节构造）：即使文件编码被改动，
  Windows PowerShell 5.1 也不会把中文读成乱码；
- `scripts/smoke_setup_wizard.py` 会校验两种语言的键集合一致、无空文案、无未替换的 `{占位符}`。

### 3.2 屏幕结构

```
──────────────────────────────────────────────────────────────  ← 分隔线（宽度 78，两平台一致）
 InstructionX 环境向导  ·  安装环境 · 升级框架 · 环境管理
 Windows 11 … · 中文          ← 平台与当前语言（这两项按实际平台显示）
──────────────────────────────────────────────────────────────
  1 ▸ 环境总览                ← 主菜单：9 项，▸ 为当前项，数字键可直接跳转
  2   安装 / 修复环境
  …
  9   使用帮助
──────────────────────────────────────────────────────────────
 ↑↓ 选择    Enter 确认    r 刷新    l 语言    q 退出
──────────────────────────────────────────────────────────────
```

页面结构统一为：标题 → 说明 → 状态/计划 → 动作列表（编号即快捷键）→ 按键提示。
页面页脚带 `Esc 返回` 提示（主菜单页脚无返回项）；过程输出不上界面面板
（避免长日志换行把界面越撑越长），全程统一写入 `logs/tui_setup.log`。
确认弹窗统一为：`请确认` + 问句 + `按 Y 确认    按 N 取消`；危险操作（卸载）用红色显示。

### 3.3 按键

| 按键 | 作用 |
|------|------|
| ↑ / ↓ | 菜单内移动 |
| 1–9 | 直接选择菜单项；在页面内触发对应编号的动作 |
| Enter | 确认 / 进入 |
| Esc（或 `b`） | 返回上一级（确认弹窗中等于「取消」） |
| `r` | 刷新当前信息 |
| `l` | 切换中英文（立即生效并记入 `.tui/lang`） |
| `q` | 退出向导 |
| `y` / `n` | 确认弹窗：是 / 否 |

## 4. 环境管理策略（重要）

| 场景 | 使用命令 | 原因 |
|------|---------|------|
| **初次安装**（无 `.venv` 且 `uv.lock` 可用） | `uv sync --no-dev --no-install-project` | 按锁文件精确安装；不装项目自身、不含测试依赖 |
| **修复 / 升级依赖**（已有 `.venv`） | `uv pip install -r requirements.txt` | 只做增量补齐，**绝不使用 `uv sync`**——它会移除插件经框架安装的额外依赖 |
| **锁文件为空或损坏** | 自动回退到 `uv pip install -r requirements.txt` 并在日志中说明 | 避免 `uv sync` 抛出「Failed to parse uv.lock」这类用户看不懂的错误而卡死安装 |
| 准备 Python | `uv python install 3.14` | **失败只警告、不判定整体失败**：系统已有 3.14 时后续步骤仍可成功（环境是否可用由最后的自检决定） |
| 安装后自检 | 在 `.venv` 中逐个 `importlib.util.find_spec` 检查关键依赖 | 只有关键组件齐全才算安装成功 |

关键依赖清单：`PySide6`、`numpy`、`requests`、`orjson`、`mcp`、`packaging`（与 `requirements.txt` 口径一致）。

## 5. 升级策略

- **有 Git 仓库且 git 可用** → `git pull --ff-only`（不做合并提交）；
  升级前会检查已跟踪文件的本地修改并提示用户，避免自动升级把本地改动搞乱。
- **没有 Git** → 下载 `https://codeload.github.com/KKPIP-Tech/InstructionX/zip/refs/heads/main`
  并**覆盖程序文件**。
- 覆盖时**一律跳过**这些目录（用户数据与本地环境）：

  `config` `data` `logs` `plugin` `custom_plugin` `.venv` `.tui` `temp`，以及 `.git` `__pycache__`。

- 升级完成后自动执行依赖同步（同上表），并重新自检。

## 6. 一键体检（9 项）

| 检查项 | 通过条件 | 不通过时的建议 |
|--------|---------|---------------|
| uv 是否可用 | 能定位到 uv 并读出 `--version` | 请安装 uv（向导可自动完成） |
| Python 3.14 是否可用 | `.venv` 解释器版本可读 | uv 在但环境缺失 → 执行「安装 / 修复环境」；uv 也不在 → 先装 uv |
| 应用运行环境是否存在 | `.venv` 存在且解释器在 | 执行「安装 / 修复环境」 |
| 关键组件是否可导入 | 缺失清单为空 | 执行「安装 / 修复环境」 |
| 配置 / 数据目录是否可写 | 写入探针成功（试运行不写） | 清理磁盘空间后重试 |
| 依赖清单与锁文件是否同步 | `requirements.txt` 与 `uv.lock` 均存在 | 执行「安装 / 修复环境」 |
| 能否访问软件源（PyPI） | 能连上 pypi.org | 检查网络或代理；离线时可用压缩包离线安装 |
| 系统平台是否受支持 | Windows 为主平台（macOS 功能可能受限会给出提示） | — |
| 磁盘剩余空间是否充足 | 剩余 ≥ 2 GB | 清理磁盘空间后重试 |

## 7. 安全约定

- **破坏性操作一律先确认**：重新安装环境、删除环境、彻底卸载（卸载需两次确认且第二次标红）；
  确认弹窗对 `--yes` 之外的任何输入都按「取消」处理。
- **`--dry-run` 只展示命令**，不产生任何改动（连 `config` / `data` 探针目录都不会创建）。
- **工作目录恒定为项目根**：所有子进程（uv / git）都在脚本所在目录下执行，
  这样即使从别处调用脚本，也绝不会作用到「调用者所在的那个项目」。
- **外部命令输出不当错误处理**：uv 的进度信息写在 stderr，脚本不会因此中断安装。
- **过程全程留痕**：界面日志面板 + `logs/tui_setup.log`（用户反馈问题时把这个文件发给开发者即可）。
- **卸载只删数据**：`.venv` `config` `data` `logs` `.tui` 与桌面快捷方式；程序文件与 `plugin/` 保留。

## 8. 目录与文件

```
setup.bat / setup.command   # Windows / macOS 双击入口（只负责调用对应脚本）
setup.ps1                   # Windows 原生向导（PowerShell 5.1）
setup.sh                    # macOS 原生向导（bash 3.2）
setup_text/zh.txt, en.txt   # 中英双语文案（两个脚本共用的唯一来源）
桌面 InstructionX.lnk / InstructionX.app   # 首次安装成功创建的快捷方式 / 启动器（含 Logo，卸载时删除）
.tui/venv, .tui/work, .tui/lang   # 向导运行时目录（语言偏好、升级下载残留；.gitignore 已忽略）
logs/tui_setup.log          # 向导过程日志
scripts/smoke_setup_wizard.py     # 向导冒烟测试（文案完整性、界面一致性、干跑安全）
```

## 9. 完全没有 Python / uv 的电脑

1. 双击入口 → 向导先找 uv：`PATH` → `~/.local/bin` → WinGet/Homebrew/`/usr/local/bin` → `~/.cargo/bin`；
2. 找不到时弹确认框并展示官方安装命令，用户同意后执行（Windows：PowerShell 脚本；macOS：`curl … | sh`）；
3. 由 uv 准备 Python 3.14（失败也不影响已有解释器的机器）；
4. 创建 `.venv` 并安装依赖，最后自检关键组件；**首次安装成功后自动在桌面创建快捷方式**
   （Windows 为 `InstructionX.lnk`，macOS 为 `InstructionX.app` 启动器，均含软件 Logo，
   双击直接启动、无控制台 / 终端窗口）；之后日常启动用桌面快捷方式，
   向导内的「启动应用」保留运行输出、仅作调试用途。

## 10. 常见问题（FAQ）

**Q：向导会不会动我的系统 Python？**
不会。所有操作都在项目内的 `.venv` 里，通过 uv 完成；系统 Python 与全局包不受影响。

**Q：安装到一半关掉了窗口怎么办？**
重新打开向导执行「安装 / 修复环境」即可；已经装好的部分会被复用（修复路径是增量的）。

**Q：升级会不会删掉我的配置、数据和插件？**
不会。升级只覆盖程序文件，`config/`、`data/`、`logs/`、`plugin/`、`custom_plugin/` 一律保留，
升级前还会生成插件目录的兜底快照（见 `data/plugin_backup/`）。

**Q：插件自己装的依赖会不会被删掉？**
不会。修复与升级都走 `uv pip install -r requirements.txt`，不使用会「对齐锁文件」的 `uv sync`。

**Q：体检说「能否访问软件源」不通过，还能安装吗？**
可以先按提示检查网络/代理；**完全离线**的内网环境可以用本地代码包升级（覆盖程序文件、保留全部用户数据）：

```powershell
# Windows：管理员把官方 main 压缩包拷到本机后执行
powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1 -Action upgrade -Yes -ArchivePath D:\InstructionX-main.zip
```

```bash
# macOS
./setup.sh --action upgrade --yes --archive ~/Downloads/InstructionX-main.zip
```

解压优先用 `unzip`（macOS 自带），失败时依次回退 `ditto`、`tar`；Windows 上打包的压缩包
（路径使用反斜杠）也能正常解压——向导只把 `unzip` 的警告退出码视为成功。

**Q：我想让开发同事看日志。**
把 `logs/tui_setup.log` 发给他即可，里面有每条命令、返回码与耗时。

## 11. 开发者说明

- **加文案**：往 `setup_text/zh.txt` 与 `en.txt` 各加一行同名 key，然后运行
  `python scripts/smoke_setup_wizard.py` 校验完整性。
- **加页面/动作**：在 `setup.ps1` 与 `setup.sh` 中同步新增对应函数与菜单/动作分派
  （菜单键 `menu_keys()` / `menu_pages()` 两处必须保持一致，冒烟测试会比对）。
- **加诊断信息**：`-State` / `--state` 输出 `key=value`，两个脚本的字段名必须一致（冒烟测试会比对）。
- **验证两平台一致**：`scripts/smoke_setup_wizard.py` 会分别用 Windows PowerShell 与
  Git Bash 渲染全部页面并逐行比对（只允许平台名与路径风格不同）。
- **注意**：`setup.ps1` 必须保存为 **UTF-8 with BOM**（PowerShell 5.1 用系统代码页解码无 BOM 文件，
  中文注释会乱码）；脚本正文本身不依赖这一点（正文纯 ASCII），冒烟测试会同时检查两项。
- **注意**：`setup.bat` 必须是 **纯 ASCII + CRLF 行尾、无 BOM**——cmd.exe 会误解析纯 LF 的批处理
  （实测首个字符丢失导致入口报错），也不会去掉 UTF-8 BOM；`setup.command` 反过来必须是 **LF、无 BOM**
  且以 `#!/bin/bash` 开头。这些约束都已纳入冒烟测试，改完入口文件请务必重跑。

## 12. English summary

The installer is a **native terminal UI**: `setup.ps1` (Windows PowerShell 5.1) and
`setup.sh` (macOS bash 3.2), launched by `setup.bat` / `setup.command`. It requires **no Python and no
third-party packages** — that is the point: it must run on a machine that has neither Python nor uv.

Both scripts read the same bilingual strings from `setup_text/{zh,en}.txt`, so the two interfaces are
identical word for word (only the platform label and path style differ). They cover: environment
overview, install/repair (uv sync for first install, `uv pip install -r requirements.txt` for repair —
never `uv sync`, which would remove plugin-installed packages), framework upgrade (`git pull --ff-only`,
or overlaying the official main archive while preserving config/data/logs/plugins), environment
management, a nine-item health check, cleanup/uninstall with confirmations, launching the app, and
`zh`/`en` switching. Non-interactive modes (`--check`, `--state`, `--preview`, `--action`) support
scripting, CI and support diagnostics.
