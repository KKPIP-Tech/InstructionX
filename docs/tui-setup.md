# InstructionX 原生 Setup / TUI

> Windows / macOS / Linux 共用的原生安装、升级与环境管理程序。
> 界面由 **Rust + Ratatui + Crossterm** 实现，不使用 Python、PowerShell 或 Bash 编写 TUI。

## 1. 用户不需要安装 Rust

当前 Release 源码压缩包直接携带 Windows 预编译的 `instructionx-setup`，位于 `tools/setup/`：

| 平台与架构 | 随包文件 |
|------------|----------|
| Windows 10/11 x64 | `instructionx-setup-windows-x86_64.exe` |
| Windows 10/11 ARM64 | `instructionx-setup-windows-aarch64.exe` |

- `setup.bat` 调用 `setup.ps1`，由后者按 Windows CPU 架构选择对应文件；脚本不包含界面逻辑。
- `setup.ps1` 与 `setup.sh` 都通过 `INSTRUCTIONX_PROJECT_ROOT` 把启动器所在目录显式传给原生程序。即从其他工作目录调用启动器，也不会误查或误改调用者目录；命令行 `--project-root` 仍可显式覆盖。
- 启动器不下载 Setup，也不使用旧下载缓存。随包文件缺失时明确报错并提示恢复原始 Release 压缩包。
- Windows 离线环境可以直接启动随包 Setup，不要求 Rust、Cargo、Python 或系统包管理器。安装框架及依赖时仍需按功能联网。
- `SHA256SUMS` 记录这两个随包文件的校验值。
- macOS 预编译版本是未来选项；macOS/Linux 的启动器映射和 Rust 平台实现保留，但本次不生成或随包其原生资产。

### Setup 对外版本号

当前 Setup 基础版本为 **`20261114-01`**。格式为 `YYYYMMDD-NN`：日期表示打包日，`NN` 从 `01` 开始，表示当天第几个打包版本；同日再次打包时递增序号。它与框架的 `core/version.py` 相互独立，单一来源为 `setup/src/version.rs` 的 `SETUP_VERSION`。

完整构建版本由基础版本、目标平台和架构组成：Windows x64 为 **`20261114-01.win.x86_64`**，Windows ARM64 为 **`20261114-01.win.aarch64`**。平台与架构由编译目标自动生成，不需要另行手工维护。

用户可以在所有界面顶部看到完整构建版本，也可以执行 `instructionx-setup --version`；`--state` 的 `setup_version` 同样包含平台和架构。每次修改基础版本后必须重新构建两个 Windows 资产并更新 `SHA256SUMS`。

构建完全在开发者本机进行，不使用 GitHub Actions 构建或发布 Setup。发布 Tag 前必须把当前源码对应的 Windows 构建结果写入 `tools/setup/` 并提交，GitHub 自动生成的 Release 源码压缩包才会包含这些程序。

## 2. 首次语言选择

首次启动首先显示语言页，默认焦点为 **English**，确认后才进入总览：

- 中文 `zh`
- English `en`（默认）
- Français `fr`
- Русский `ru`

偏好原子写入 `.tui/preferences.toml`，后续启动直接生效；旧 `.tui/lang` 自动读取迁移。按 `l` 或选择杂项页面的独立“TUI 语言”操作可重新选择。`--lang zh|en|fr|ru` 只覆盖本次运行，不写偏好。

## 3. 页面、操作项与按键

| 页面 | 独立操作项与数据 |
|------|------------------|
| 0 总览 | 操作系统、CPU、内存条、物理磁盘与卷、显示器、网卡与 IP、TUI/框架状态、桌面入口 |
| 1 安装与修复 | 安装 InstructionX、修复 InstructionX、检查 GitHub Releases |
| 2 环境配置与修复 | 查询包列表、更新所选、移除所选、重建环境、安装插件依赖；下方显示可选包列表 |
| 3 升级管理 | 检查更新、升级到所选版本；下方显示 Release 时间线 |
| 4 插件列表 | 刷新插件列表、检查插件更新、安装插件依赖；下方显示插件明细 |
| 5 杂项 | 创建桌面快捷方式、TUI 语言；后续功能继续添加为独立操作项 |

采用单一高亮选择模型。启动后默认位于左侧菜单；进入功能页后，右侧首先显示带高亮标记的操作项，而不是要求用户记住隐藏快捷键。

通用按键：

- `↑` / `↓`：移动左侧页面、右侧操作项或数据列表的高亮；`0–5`：直接跳转页面。
- `→` / `Enter`：从左侧进入右侧；在操作项上按 Enter 选择该操作，再按提示确认。
- `←`：返回左侧菜单，不切换页面；`Esc` 取消尚未执行的确认。
- `Tab`：按“操作区 → 数据区 → 左侧菜单”切换焦点；没有数据区时在操作区与菜单间切换。
- `PageUp` / `PageDown`：翻页；`Home` / `End`：到顶部/底部；鼠标滚轮同样可滚动并聚焦内容区。
- `Space`：在环境数据区勾选/取消包。
- `c`、`r`、`u` / `d` 保留为兼容快捷键，但所有对应功能都有可见的独立操作项，不依赖这些按键。
- `g` / `v`：安装 Git / uv；`p`：在总览中手动获取公网 IP。
- `l`：切换语言；`q`：退出。后台操作尚未结束时不会直接退出，避免留下半截安装或维护任务。

### Activity 进度与结果区域

所有安装、维护和查询操作都由后台工作线程执行，界面持续刷新，不因网络或包管理命令而停止响应。页面底部的 **Activity** 固定区域显示：

- 当前操作、`[当前步骤/总步骤]` 和正在处理的目标；
- 最近的过程消息，以及明确的成功、部分失败或失败结果；
- 结果详情（例如复制文件数、备份目录、Release 列表、插件依赖失败原因）；
- 持久日志位置 `logs/tui_setup.log`，日志包含时间戳、步骤、结果详情和错误，便于反馈问题。

Activity 按实际包装后的行数自动滚动到最新内容，长下载地址和多行输出不会把新结果挤出可视区。winget 等子进程的标准输出/错误输出通过管道进入 Activity，清理 ANSI 控制序列并按 `\r` 进度更新分行，不再绕过界面直接覆盖终端。步骤只更新 Progress，不与历史消息重复显示。

选择新操作并进入二次确认时立即清空上一项操作的活动内容，确认文字只保留一份；历史过程仍可从日志追溯。Activity 标题、状态、步骤、确认、结果及页面静态内容使用结构化消息键与参数，随当前界面语言立即切换；子进程原始输出保持原文。非交互 `--action` 同样读取已保存的语言偏好，并支持 `--lang` 覆盖。

操作进行中不能重复启动另一项操作。非交互操作使用同一执行器，逐步输出到标准输出，失败返回非零退出码；网络查询只由明确操作触发，不自动检查框架更新。

## 4. 总览信息

- 系统名称、版本、内核、架构、主机名。
- CPU 型号、物理/逻辑核心数。
- 总内存、可用内存；Windows 还显示每条内存的容量、厂商、型号、频率与插槽。
- 物理磁盘型号与容量；挂载卷的文件系统、总容量与剩余空间。
- 显示器名称、分辨率和刷新率（可获取时）。
- 网卡名称、MAC、IPv4/IPv6。
- TUI 路径、框架安装标记、版本、Git、uv、`.venv` 和桌面入口。

Windows 使用 WMI/Win32，macOS 使用系统原生工具，Linux 读取 `/proc`、`/sys` 并使用 `lsblk`、`xrandr` 等。虚拟机、无权限、无显示器或 Wayland 环境下无法获取的字段显示未知，不导致程序崩溃。公网 IP 仅在按 `p` 后请求，失败时显示原因且不持久化。

## 5. 安装、修复与升级

### 安装

1. 检查 `main.py`、`core/version.py`、`pyproject.toml` 判断是否已安装；已安装时停止并提示，不覆盖。
2. 检查 uv。交互操作确认后自动安装缺失的 uv；CLI 在缺少 uv 时需要 `--yes` 才允许自动安装。系统 `PATH` 与项目 `.tui/tools/` 中的 uv 都可直接使用。
3. 尚未加载 Release 时自动获取完整时间线并选择最新发布；也可以先手动检查并选择目标。时间线按 `published_at` 倒序排列，包含 Pre-release、排除 Draft。
4. 按七个阶段显示工具准备、Release 解析、下载、归档复制、依赖安装和自检进度。首次安装会复制 `plugin/` 与 `custom_plugin/`，优先执行 `uv sync --locked --no-dev --no-install-project`，锁文件不可用时回退到 `uv pip install -r requirements.txt`。
5. 使用新建环境的 Python 实际导入 `PySide6`、`numpy`、`requests`、`orjson`、`mcp`、`packaging`；任一失败都不会报告安装成功。

### 修复

- 自动读取当前版本并定位完全匹配的 Release，不受 Release 列表中“最新版”默认选择影响。
- 下载到暂存区后先备份，再执行**只覆盖、不删除**的合并。
- 保留 `plugin/`、`custom_plugin/`、`config/`、`data/`、`logs/`、`.venv`、`.tui/`、`temp/`、`.git` 和 `__pycache__`。
- 覆盖后执行 `uv pip install -r requirements.txt` 增量补齐依赖，不使用可能移除插件额外依赖的 `uv sync`；随后执行相同的 Python 导入自检，失败时恢复程序文件备份并报告错误。
- Git 已跟踪文件存在修改时默认中止，避免覆盖本地工作。

### 升级

- 仅在用户主动检查后获取完整 Release 列表；直接执行升级且尚未加载列表时会先获取。
- 当前版本在列表中明确标记，最新发布位于第一行。
- 只允许选择高于当前版本的 Release，不自动更新、不自动重启。
- 与修复一样使用增量依赖安装和 Python 导入自检，保留插件及其额外依赖。
- 归档包含当前正在运行的 Setup 时，先把旧可执行文件移动到本次备份目录，再写入新文件，避免 Windows 文件占用导致升级失败；写入失败会立即恢复原文件，其他阶段失败也会保留原始错误并执行回滚。

### Git / uv 预检

- 没有 Git 时仍可使用 Release 压缩包；`g` 可通过 winget、Homebrew 或 Linux 包管理器安装 Git，提权前需要确认。
- `v` 可单独安装 uv；安装、修复和升级也会在确认后自动准备缺失的 uv。
- 自动安装的 uv 保存在项目 `.tui/tools/`，安装后验证可执行文件，后续启动无需依赖系统 `PATH`。

## 6. 环境配置与修复

### 包管理

使用：

```text
uv pip list --format json
uv pip list --outdated --format json
```

显示当前版本和最新候选版本，支持多选更新与移除。框架 `requirements.txt` 中的依赖受保护，不能被移除。实际兼容结果由 uv 解析，冲突与网络错误均明确显示。

### 环境修复

1. 二次确认后删除并重建 `.venv`。
2. 优先 `uv sync --locked --no-dev --no-install-project`；锁文件不可用时回退到 `uv pip install -r requirements.txt`。
3. 逐插件调用 `core.plugin.setup_dependency_cli`，一个完成后再处理下一个。
4. 单插件失败不阻断后续插件，最终列出成功项、失败包和原因。

## 7. 插件列表

直接读取 `IXPlugin.json` 与 `config/plugin_registry.json`：

- 官方 / 第三方分类。
- 多语言名称与描述、当前版本。
- 更新状态：未检查、已是最新、有更新、检查失败。
- 开发者主页，缺失时回退到来源仓库。

只有手动检查后才调用 `GitHubPluginInstaller.get_available_versions()`，不自动下载或升级插件。

## 8. 无窗口桌面入口

- Windows：带 `ui/logo.ico` 的 `.lnk`，通过无窗口启动器调用 `uv run --frozen pythonw main.py`。
- macOS：`.app`，由 LaunchServices 启动，不打开 Terminal。
- Linux：`.desktop`，包含 Logo、`Path` 和 `Terminal=false`。

创建后验证快捷方式、Logo、工作目录和 uv 参数。卸载时删除快捷方式，但保留程序文件和插件。

## 9. 非交互接口

| 参数 | 说明 |
|------|------|
| `--version` | 显示包含 `YYYYMMDD-NN`、平台和架构的 Setup 完整构建版本 |
| `--check` / `-Check` | 输出环境体检 |
| `--state` / `-State` | 输出 `key=value` 状态 |
| `--preview PAGE` | 渲染一个页面后退出 |
| `--action NAME` | `install` / `repair` / `upgrade` / `environment-repair` / `check-updates` / `create-shortcut` / `clean-temp` / `uninstall` |
| `--archive FILE` / `-ArchivePath FILE` | 使用本地 Release 包 |
| `--release-tag TAG` / `-ReleaseTag TAG` | 使用指定 Release |
| `--dry-run` | 只展示计划，不下载、不创建目录、不写配置、不删除环境 |
| `--yes` | 允许自动安装缺失工具和卸载确认 |
| `--lang zh\|en\|fr\|ru` | 覆盖本次语言 |
| `--no-color` | 禁用颜色（兼容参数） |
| `--project-root PATH` | 显式指定框架根目录 |

框架 GUI 的更新弹窗也通过 `FrameworkUpdateLauncher` 调用原生 Setup 的 `--action upgrade --yes --release-tag <tag>`。

## 10. 构建与验证

开发者在 Windows 本机运行正式构建脚本：

```powershell
# 构建 x64 与 ARM64，并更新 tools/setup/ 和 SHA256SUMS
powershell -ExecutionPolicy Bypass -File setup/build_windows.ps1

# 只构建一个架构
powershell -ExecutionPolicy Bypass -File setup/build_windows.ps1 -Architecture x86_64
powershell -ExecutionPolicy Bypass -File setup/build_windows.ps1 -Architecture aarch64
```

脚本自动安装 Rust 目标、按开发者主机架构下载并校验固定版本的 LLVM-MinGW、构建两个目标、验证 PE 架构、复制正式资产并生成校验清单。x64 使用 `x86_64-pc-windows-msvc`，需要本机 MSVC 环境；ARM64 使用 `aarch64-pc-windows-gnullvm`，由 LLVM-MinGW 提供交叉编译器和链接器。

- `-CargoPath`：指定已有 `cargo.exe`；默认使用 PATH 或项目 `temp/cargo/`。
- `-LlvmMingwPath`：使用已有 LLVM-MinGW 解压目录，跳过下载。
- `-TargetRoot`：覆盖 Cargo 中间产物目录，默认为 `temp/setup-build/`。

所有工具链和中间产物默认只写入项目 `temp/`，环境变量仅影响脚本进程，不修改系统 PATH。每次 Setup 源码变化后，发布前都要用该脚本重新构建两个 Windows 资产并随源码提交；不使用 GitHub Actions 构建或发布这些二进制。

另需运行：

```powershell
.venv\Scripts\python.exe scripts\smoke_setup_wizard.py
python -m pytest test/ -q --tb=short -p no:cacheprovider
```

Rust 集成测试位于 `test` 分支；`dev` 只包含实现与正式冒烟脚本。所有写操作测试均使用临时目录，不在真实用户环境执行。
