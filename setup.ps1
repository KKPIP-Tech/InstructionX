#Requires -Version 5.1
<#
.SYNOPSIS
    InstructionX 安装向导（Windows 原生版，PowerShell 5.1）。

.DESCRIPTION
    面向大夫 / 教师 / 艺术家等非技术用户：双击 setup.bat 即可安装、升级与维护运行环境。

    **为什么用原生脚本**：向导必须在「电脑上连 Python 都没有」的机器上运行，
    因此本脚本不依赖 Python（也不依赖任何第三方模块），界面由 PowerShell 自己绘制；
    macOS 版是同样界面的 setup.sh（两份脚本读取同一份文案 setup_text/*.txt，
    保证两平台界面逐字一致）。Python 只在向导的「安装」动作中被 uv 安装，用于运行应用本身。

    功能：环境总览 / 安装与修复（uv sync、uv pip install）/ 升级框架（git pull 或官方压缩包覆盖）
    / 环境管理（重建、清缓存、打开目录、删除环境）/ 一键体检 / 清理与卸载 / 中英双语。
    首次安装成功后自动创建桌面快捷方式（含 Logo，pythonw 启动、无控制台窗口），卸载时删除；
    向导内的「启动应用」保留运行输出，仅作调试用途。

.PARAMETER Check
    只做环境体检并打印文本报告（不启动界面，适合排错与自动化），有问题时退出码为 1。

.PARAMETER DryRun
    试运行：只展示将要执行的命令，不真正改动电脑。

.PARAMETER Yes
    自动确认所有提问（无人值守；常与 -Check / -DryRun 配合）。

.PARAMETER Lang
    界面语言：zh 或 en（默认跟随系统区域，其次读取 .tui/lang）。

.PARAMETER NoColor
    关闭彩色输出（旧版控制台或日志采集）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup.ps1 -Check
#>
[CmdletBinding()]
param(
    [switch]$Check,
    [switch]$State,
    [switch]$DryRun,
    [switch]$Yes,
    [ValidateSet('', 'zh', 'en')][string]$Lang = '',
    [string]$Preview = '',
    [ValidateSet('', 'install', 'repair', 'upgrade', 'doctor', 'clean-temp', 'uninstall')]
    [string]$Action = '',
    [string]$ArchivePath = '',
    [string]$Keys = '',
    [switch]$NoColor
)

$ErrorActionPreference = 'Stop'

# ============================================================================
# 1. 常量（与 setup.sh 保持同名同值：单一事实来源）
# ============================================================================

#: 界面宽度（规则线长度，两个平台一致）
$Script:RuleWidth = 78
#: 项目根目录（脚本所在目录）
$Script:ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
#: 共享文案目录
$Script:TextDir = Join-Path $Script:ProjectRoot 'setup_text'
#: 向导日志（面向用户的可反馈文件，与文档约定一致）
$Script:LogFile = Join-Path $Script:ProjectRoot 'logs\tui_setup.log'
#: 界面语言偏好（两平台共用的运行时文件）
$Script:LangFile = Join-Path $Script:ProjectRoot '.tui\lang'
#: 升级临时工作目录
$Script:WorkDir = Join-Path $Script:ProjectRoot '.tui\work'
#: 应用虚拟环境目录
$Script:AppVenv = Join-Path $Script:ProjectRoot '.venv'
#: 框架要求的 Python 版本
$Script:RequiredPython = '3.14'
#: 初次安装：按 uv.lock 精确安装，不装项目自身与测试依赖
$Script:SyncArgs = @('sync', '--no-dev', '--no-install-project')
#: 修复 / 升级依赖：增量安装，绝不使用 uv sync（会删除插件自装依赖）
$Script:PipArgs = @('pip', 'install', '-r', 'requirements.txt')
#: 关键依赖（安装后自检）
$Script:RequiredImports = @('PySide6', 'numpy', 'requests', 'orjson', 'mcp', 'packaging')
#: 升级覆盖时必须保留的目录（用户数据与本地环境）
$Script:PreserveDirs = @('config', 'data', 'logs', 'plugin', 'custom_plugin', '.venv', '.tui', 'temp')
#: 升级覆盖时跳过的仓库元数据
$Script:SkipDirs = @('.git', '__pycache__')
#: 彻底卸载时删除的目录（程序文件不在此列）
$Script:UninstallDirs = @('.venv', 'config', 'data', 'logs', '.tui')
#: 桌面快捷方式（首次安装成功后创建、卸载时删除；pythonw 启动无控制台窗口）
$Script:ShortcutName = 'InstructionX.lnk'
#: 快捷方式图标（框架自带 ICO；不存在时退回系统默认图标）
$Script:ShortcutIcon = Join-Path $Script:ProjectRoot 'ui\logo.ico'
#: 官方资源
$Script:RepoUrl = 'https://github.com/KKPIP-Tech/InstructionX.git'
$Script:ZipUrl = 'https://codeload.github.com/KKPIP-Tech/InstructionX/zip/refs/heads/main'
$Script:UvInstallCmd = 'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
$Script:PythonUrl = 'https://www.python.org/downloads/'
#: 超时（秒）
$Script:TimeoutProbe = 30
$Script:TimeoutDownload = 600
$Script:TimeoutCache = 300
#: 磁盘剩余空间下限（低于此值提醒）
$Script:MinFreeDiskBytes = 2GB
#: 统计运行环境体积时的文件数上限
$Script:MaxCountedFiles = 20000
#: 命令输出重绘节流（每 N 行刷新一次界面）
$Script:RedrawEvery = 5

#： 界面装饰字符（用码位构造，脚本正文保持纯 ASCII：即使 BOM 丢失也不会乱码）
$Script:RuleChar = [char]0x2500      # 分隔线
$Script:CursorMark = [char]0x25B8    # 选中标记
$Script:TitleSep = [char]0x00B7      # 标题分隔符

#: 运行时状态
$Script:Text = @{}
$Script:UiLang = 'zh'
$Script:LogLines = New-Object System.Collections.ArrayList
$Script:ColorEnabled = $false
$Script:Esc = [char]27
#: 非交互模式（-Action）：不渲染「正在执行」页、结果页不等待按键
$Script:NonInteractive = $false
#: 脚本化按键序列（-Keys）：用于无终端环境复现/回归测试界面流程
$Script:KeyQueue = New-Object System.Collections.ArrayList
$Script:UseKeyQueue = $false

# ============================================================================
# 2. 文案（读取 setup_text/<语言>.txt，与 setup.sh 共用同一份数据）
# ============================================================================

function Import-TextTable {
    <#
    .SYNOPSIS
        读取某语言的文案表。
    .PARAMETER Lang
        语言代码（zh / en）。
    .OUTPUTS
        Hashtable：key -> 文案（\n 已还原为换行）。
    #>
    param([Parameter(Mandatory = $true)][string]$Lang)

    $table = @{}
    $path = Join-Path $Script:TextDir "$Lang.txt"
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing text file: $path"
    }
    foreach ($line in [System.IO.File]::ReadAllLines($path, [System.Text.Encoding]::UTF8)) {
        if ($line -eq '' -or $line.StartsWith('#')) { continue }
        $index = $line.IndexOf('=')
        if ($index -lt 1) { continue }
        $key = $line.Substring(0, $index).Trim()
        $value = $line.Substring($index + 1).Replace('\n', "`n")
        $table[$key] = $value
    }
    return $table
}

function Get-Text {
    <#
    .SYNOPSIS
        取词并替换 {name} 形式的占位符。
    .PARAMETER Key
        文案键。
    .PARAMETER Params
        占位符键值对。
    .OUTPUTS
        String：当前语言的文案；缺失时返回 key 本身（避免界面出现空白）。
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Key,
        [hashtable]$Params = @{}
    )

    $text = $Script:Text[$Key]
    if ($null -eq $text) { return $Key }
    foreach ($name in $Params.Keys) {
        $text = $text.Replace("{$name}", [string]$Params[$name])
    }
    return $text
}

function Get-SystemLanguage {
    <#
    .SYNOPSIS
        推断界面语言：参数 > .tui/lang > 系统区域 > 英文。
    .OUTPUTS
        String：zh 或 en。
    #>
    if ($Lang -in @('zh', 'en')) { return $Lang }
    if (Test-Path -LiteralPath $Script:LangFile) {
        $saved = ([System.IO.File]::ReadAllText($Script:LangFile)).Trim().ToLower()
        if ($saved -in @('zh', 'en')) { return $saved }
    }
    $culture = [System.Globalization.CultureInfo]::CurrentUICulture.Name
    if ($culture -like 'zh*') { return 'zh' }
    return 'en'
}

# ============================================================================
# 3. 终端与绘制（两个平台的输出必须逐字一致）
# ============================================================================

function Initialize-Console {
    <#
    .SYNOPSIS
        统一控制台编码并启用 ANSI 颜色（失败时自动降级为无色，界面结构不变）。
    #>
    try {
        [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
        $OutputEncoding = [Console]::OutputEncoding
    } catch { }
    if ($NoColor) { return }
    try {
        $definition = @'
using System;
using System.Runtime.InteropServices;
public static class IxVt {
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern IntPtr GetStdHandle(int handle);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetConsoleMode(IntPtr handle, out uint mode);
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool SetConsoleMode(IntPtr handle, uint mode);
    public static bool Enable() {
        IntPtr handle = GetStdHandle(-11);
        uint mode;
        if (!GetConsoleMode(handle, out mode)) { return false; }
        return SetConsoleMode(handle, mode | 0x0004);
    }
}
'@
        if (-not ('IxVt' -as [type])) { Add-Type -TypeDefinition $definition -ErrorAction Stop }
        $Script:ColorEnabled = [IxVt]::Enable()
    } catch {
        $Script:ColorEnabled = $false
    }
}

function Format-Color {
    <#
    .SYNOPSIS
        按语义着色（无颜色能力时原样返回）。
    .PARAMETER Text
        文本。
    .PARAMETER Tone
        ok / warn / fail / info / title / dim / accent。
    .OUTPUTS
        String
    #>
    param([string]$Text, [string]$Tone = '')

    if (-not $Script:ColorEnabled -or $Tone -eq '') { return $Text }
    $codes = @{ ok = '32'; warn = '33'; fail = '31'; info = '36'; title = '1;36'; dim = '90'; accent = '1;37' }
    $code = $codes[$Tone]
    if ($null -eq $code) { return $Text }
    return "$Script:Esc[$code" + "m$Text$Script:Esc[0m"
}

function Write-Rule {
    <#
    .SYNOPSIS
        输出一条分隔线（长度由 $Script:RuleWidth 决定，两平台一致）。
    #>
    Write-Host (Format-Color ([string]$Script:RuleChar * $Script:RuleWidth) 'dim')
}

function Write-Out {
    <#
    .SYNOPSIS
        输出一行界面文本（自动清理行尾空白，保持两平台输出一致）。
    .PARAMETER Text
        文本。
    .PARAMETER Tone
        语义色。
    #>
    param([string]$Text = '', [string]$Tone = '')

    Write-Host (Format-Color $Text.TrimEnd() $Tone)
}

function Clear-Screen {
    <#
    .SYNOPSIS
        清屏（非交互环境忽略失败）。
    #>
    try { Clear-Host } catch { }
}

function Write-Header {
    <#
    .SYNOPSIS
        输出顶部标题区（应用名 + 副标题 + 平台与语言）。
    #>
    Write-Rule
    $left = ' ' + (Get-Text 'app.title') + "  $Script:TitleSep  " + (Get-Text 'app.subtitle')
    $right = (Get-PlatformLabel) + " $Script:TitleSep " + (Get-Text ("lang.name.$Script:UiLang"))
    Write-Out $left 'title'
    Write-Out (' ' + $right) 'dim'
    Write-Rule
}

function Write-Footer {
    <#
    .SYNOPSIS
        输出底部按键提示；-Page 时带「Esc 返回」提示（页面页脚），主菜单不带。
    #>
    param([switch]$Page)

    Write-Rule
    if ($Page) { Write-Out (' ' + (Get-Text 'ui.footer_page')) 'dim' }
    else { Write-Out (' ' + (Get-Text 'ui.footer')) 'dim' }
    Write-Rule
}

function Get-PlatformLabel {
    <#
    .SYNOPSIS
        返回人类可读的平台描述。
    .OUTPUTS
        String：如 Windows 11 (10.0.26100)。
    #>
    $os = [System.Environment]::OSVersion.Version
    return "Windows $($os.Major).$($os.Minor).$($os.Build)"
}

function ConvertTo-KeyInfo {
    <#
    .SYNOPSIS
        把脚本化按键标记转换为按键信息（自动化测试用）。
    .PARAMETER Token
        up / down / enter / escape、``u+XXXX``（按码位构造字符，避免命令行编码干扰）
        或单个字符。
    .OUTPUTS
        Hashtable：key（ConsoleKey 名称）/ char。
    #>
    param([string]$Token)

    $trimmed = $Token.Trim()
    switch ($trimmed.ToLower()) {
        'up' { return @{ key = 'UpArrow'; char = '' } }
        'down' { return @{ key = 'DownArrow'; char = '' } }
        'enter' { return @{ key = 'Enter'; char = [string][char]13 } }
        'escape' { return @{ key = 'Escape'; char = [string][char]27 } }
    }
    if ($trimmed -match '^u\+([0-9a-fA-F]{4})$') {
        return @{ key = ''; char = [string][char][Convert]::ToInt32($Matches[1], 16) }
    }
    return @{ key = ''; char = $trimmed }
}

function ConvertTo-HalfWidthDigit {
    <#
    .SYNOPSIS
        把数字按键归一化为半角字符。

    .NOTES
        中文输入法「全角」模式下按数字键产生的是全角字符（``１`` 而非 ``1``），
        ``[1-9]`` 正则匹配不到——用户表现为「按了没反应」（实测：向导里选不了语言）。
        这里统一归一化，全角与半角数字都能操作界面。
    .PARAMETER Char
        单个字符。
    .OUTPUTS
        String：半角数字；不是数字时返回空串。
    #>
    param([string]$Char)

    if ([string]::IsNullOrEmpty($Char)) { return '' }
    $code = [int][char]$Char[0]
    if ($code -ge 0xFF10 -and $code -le 0xFF19) { return [string][char]($code - 0xFEE0) }
    if ($code -ge 0x31 -and $code -le 0x39) { return [string][char]$code }
    return ''
}

function Set-KeyQueue {
    <#
    .SYNOPSIS
        注入脚本化按键序列（``-Keys`` 使用），用于无终端环境复现与回归测试界面流程。
    .PARAMETER Sequence
        逗号分隔的按键标记，例如 ``8,2,1,q``。
    #>
    param([string]$Sequence)

    $Script:UseKeyQueue = $true
    foreach ($token in ($Sequence -split ',')) {
        if ($token.Trim() -ne '') { [void]$Script:KeyQueue.Add($token.Trim()) }
    }
}

function Read-KeyRaw {
    <#
    .SYNOPSIS
        读取一个原始按键。
    .OUTPUTS
        Hashtable：key（ConsoleKey 名称）/ char。

    .NOTES
        默认读真实控制台；``-Keys`` 注入队列后按队列返回，队列耗尽即视为 ``q``（避免死循环）。
        这个接缝让「菜单导航 / 选语言 / 确认弹窗」这些交互路径可以被自动化测试真实覆盖。
    #>
    if ($Script:UseKeyQueue) {
        if ($Script:KeyQueue.Count -eq 0) { return @{ key = ''; char = 'q' } }
        $token = [string]$Script:KeyQueue[0]
        $Script:KeyQueue.RemoveAt(0)
        return ConvertTo-KeyInfo $token
    }
    try {
        $info = [Console]::ReadKey($true)
        return @{ key = [string]$info.Key; char = [string]$info.KeyChar }
    } catch {
        # 部分宿主（PowerShell ISE、重定向输入等）不支持 [Console]::ReadKey；
        # 退回 $Host.UI.RawUI.ReadKey，两者都不可用时明确提示用户换终端，而不是崩掉向导
        return Read-HostKeyFallback
    }
}

function Read-HostKeyFallback {
    <#
    .SYNOPSIS
        [Console]::ReadKey 不可用时的按键读取退路。
    .OUTPUTS
        Hashtable：key / char（无法读取时返回 ``q``，让向导安全退出）。
    #>
    try {
        $raw = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
        $virtual = [int]$raw.VirtualKeyCode
        $name = switch ($virtual) {
            38 { 'UpArrow' }
            40 { 'DownArrow' }
            13 { 'Enter' }
            27 { 'Escape' }
            default { '' }
        }
        return @{ key = $name; char = [string]$raw.Character }
    } catch {
        Write-Host ''
        Write-Out (' ' + (Get-Text 'log.no_console')) 'fail'
        return @{ key = ''; char = 'q' }
    }
}

function Read-MenuKey {
    <#
    .SYNOPSIS
        读取一个按键并归一化为动作名。
    .OUTPUTS
        String：up / down / enter / escape / refresh / lang / quit / abort / 数字字符。
    #>
    $key = Read-KeyRaw
    switch ($key.key) {
        'UpArrow' { return 'up' }
        'DownArrow' { return 'down' }
        'Enter' { return 'enter' }
        'Escape' { return 'escape' }
        default {
            $char = [string]$key.char
            $digit = ConvertTo-HalfWidthDigit $char
            if ($digit -ne '') { return $digit }
            switch ($char.ToLower()) {
                'r' { return 'refresh' }
                'l' { return 'lang' }
                'z' { return 'zh' }
                'e' { return 'en' }
                'q' { return 'quit' }
                'y' { return 'yes' }
                'n' { return 'no' }
                'b' { return 'escape' }
            }
            return ''
        }
    }
}

function Wait-AnyKey {
    <#
    .SYNOPSIS
        等待用户按任意键（结果页 / 帮助页返回用；非交互模式下直接返回）。
    #>
    if ($Script:NonInteractive) { return }
    Write-Host ''
    Write-Out (' ' + (Get-Text 'ui.press_any')) 'dim'
    [void](Read-KeyRaw)
}

# ============================================================================
# 4. 日志与结果
# ============================================================================

function Add-Log {
    <#
    .SYNOPSIS
        记录一行过程日志（内存缓冲，供「正在执行」页展示 + logs/tui_setup.log）。
    .PARAMETER Level
        info / cmd / output / warn / error。
    .PARAMETER Message
        文本（可含多行，逐行展开）。
    #>
    param([string]$Level, [string]$Message)

    $prefix = switch ($Level) { 'warn' { '! ' } 'error' { 'x ' } 'cmd' { '$ ' } 'output' { '  ' } default { '* ' } }
    foreach ($raw in ([string]$Message) -split "`n") {
        $line = $raw.TrimEnd()
        if ($line -eq '' -and $Level -eq 'output') { continue }
        [void]$Script:LogLines.Add($prefix + $line)
        Write-WizardLog ($prefix + $line)
        # 非交互模式（-Action）没有界面，必须把过程打到标准输出，脚本与 CI 才能看到进展
        if ($Script:NonInteractive) { Write-Host ($prefix + $line) }
    }
    if ($Script:LogLines.Count -gt 400) {
        $Script:LogLines.RemoveRange(0, $Script:LogLines.Count - 400)
    }
}

function Write-WizardLog {
    <#
    .SYNOPSIS
        追加写入向导日志文件（失败不影响主流程）。
    .PARAMETER Message
        已带前缀的日志行。
    #>
    param([string]$Message)

    try {
        $dir = Split-Path -Parent $Script:LogFile
        if (-not (Test-Path -LiteralPath $dir)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
        $stamp = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
        [System.IO.File]::AppendAllText($Script:LogFile, "[$stamp] $Message`r`n",
            [System.Text.Encoding]::UTF8)
    } catch { }
}

function Set-Status {
    <#
    .SYNOPSIS
        记录一条用户可见的结果（写入日志，供结果页展示）。
    .PARAMETER Tone
        ok / warn / fail / info。
    .PARAMETER Message
        文本。
    #>
    param([string]$Tone, [string]$Message)

    $level = switch ($Tone) { 'fail' { 'error' } 'warn' { 'warn' } default { 'info' } }
    Add-Log $level $Message
}

# ============================================================================
# 5. 命令执行（dry-run 一律只展示命令）
# ============================================================================

function Resolve-Executable {
    <#
    .SYNOPSIS
        把命令名解析为可执行文件的绝对路径（PATH 手工扫描，不依赖 PATHEXT）。

    .NOTES
        PowerShell 5.1 的 Get-Command 依赖 PATHEXT，实测会出现同一台机器上时有时无；
        手工扫描 `名字` + `.exe/.cmd/.bat` 稳定可靠。
    .PARAMETER Name
        命令名或路径（含路径分隔符时只做存在性检查）。
    .OUTPUTS
        String：绝对路径；找不到返回空串。
    #>
    param([string]$Name)

    if (-not $Name) { return '' }
    if ($Name -match '[\\/]') {
        if (Test-Path -LiteralPath $Name) { return $Name }
        return ''
    }
    foreach ($dir in ($env:PATH -split ';')) {
        if ($dir -eq '') { continue }
        foreach ($ext in @('', '.exe', '.cmd', '.bat')) {
            $candidate = Join-Path $dir ($Name + $ext)
            if (Test-Path -LiteralPath $candidate) { return $candidate }
        }
    }
    return ''
}

function Quote-Argument {
    <#
    .SYNOPSIS
        按 Windows 命令行规则给参数加引号（供 .NET Process 使用）。
    .PARAMETER Value
        原始参数。
    .OUTPUTS
        String：可直接拼接进命令行文本的参数。
    #>
    param([string]$Value)

    if ($Value -eq '') { return '""' }
    if ($Value -notmatch '[\s"]') { return $Value }
    $escaped = $Value -replace '(\\*)"', '$1$1\"'
    $escaped = $escaped -replace '(\\+)$', '$1$1'
    return '"' + $escaped + '"'
}

function Invoke-Capture {
    <#
    .SYNOPSIS
        执行命令并捕获输出（用于探测，带超时）。
    .PARAMETER Argv
        命令与参数数组。
    .PARAMETER TimeoutSec
        超时秒数。
    .OUTPUTS
        Hashtable：ok / code / lines / timeout。

    .NOTES
        使用 .NET Process 而不是 Start-Process：后者的 -ArgumentList 会重新拼接命令行，
        含引号/空格的参数（例如 Python 的 `-c "..."` 探测脚本）会被拆坏，导致自检
        误报「关键组件缺失」。这里自行按 Windows 规则加引号，参数边界可靠。
    #>
    param(
        [Parameter(Mandatory = $true)][string[]]$Argv,
        [int]$TimeoutSec = 30
    )

    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + ($Argv -join ' '))
        return @{ ok = $true; code = 0; lines = @(); timeout = $false }
    }
    $exe = Resolve-Executable $Argv[0]
    if ($exe -eq '') {
        Add-Log 'warn' ((Get-Text 'log.exe_not_found') + ": $($Argv[0])")
        return @{ ok = $false; code = 127; lines = @(); timeout = $false }
    }
    $rest = @()
    if ($Argv.Count -gt 1) { $rest = $Argv[1..($Argv.Count - 1)] }
    $quoted = ($rest | ForEach-Object { Quote-Argument ([string]$_) }) -join ' '
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = $exe
    $info.Arguments = $quoted
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    # 工作目录必须是项目根：uv / git 按工作目录识别项目，
    # 否则从别处调用脚本时会误操作「调用者所在的那个项目」
    $info.WorkingDirectory = $Script:ProjectRoot
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $info.StandardOutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $info.StandardErrorEncoding = New-Object System.Text.UTF8Encoding($false)
    try {
        $process = [System.Diagnostics.Process]::Start($info)
        # 异步读取：避免子进程输出填满管道时阻塞，也保证超时后仍能取回已产生的输出
        $outTask = $process.StandardOutput.ReadToEndAsync()
        $errTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSec * 1000)) {
            try { $process.Kill() } catch { }
            Add-Log 'warn' ((Get-Text 'log.command_timeout' @{ seconds = $TimeoutSec }) +
                ": $($Argv -join ' ')")
            return @{ ok = $false; code = -1; lines = @(); timeout = $true }
        }
        $text = ([string]$outTask.Result) + "`n" + ([string]$errTask.Result)
        $lines = @($text -split "`n" | Where-Object { $_.TrimEnd() -ne '' } |
            ForEach-Object { $_.TrimEnd() })
        return @{ ok = ($process.ExitCode -eq 0); code = $process.ExitCode; lines = $lines;
                  timeout = $false }
    } catch {
        Add-Log 'error' ((Get-Text 'log.command_failed' @{ exe = $exe }) + ": $($_.Exception.Message)")
        return @{ ok = $false; code = 127; lines = @($_.Exception.Message); timeout = $false }
    }
}

function Invoke-Stream {
    <#
    .SYNOPSIS
        执行命令并把输出实时写入日志面板（长任务用，界面显示「正在执行」）。
    .PARAMETER Argv
        命令与参数数组。
    .PARAMETER TitleKey
        正在执行页的标题文案键。
    .OUTPUTS
        Int：退出码（dry-run 恒为 0）。
    #>
    param(
        [Parameter(Mandatory = $true)][string[]]$Argv,
        [string]$TitleKey = 'ui.running_title'
    )

    $rendered = $Argv -join ' '
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ": $rendered")
        return 0
    }
    Add-Log 'cmd' $rendered
    Show-Running $TitleKey $rendered
    $exe = Resolve-Executable $Argv[0]
    if ($exe -eq '') {
        Add-Log 'warn' ((Get-Text 'log.exe_not_found') + ": $($Argv[0])")
        return 127
    }
    $rest = @()
    if ($Argv.Count -gt 1) { $rest = $Argv[1..($Argv.Count - 1)] }
    $counter = 0
    # uv / git 会把进度与提示写到 stderr，而本脚本的 ErrorActionPreference 是 Stop：
    # 若不临时放宽，合并输出（2>&1）产生的 ErrorRecord 会被当成终止错误，命令被中途打断
    # （实测表现为「Resolved 77 packages …」后安装中断）。这里只对子进程执行期间放宽。
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # 切到项目根再执行：uv / git 按工作目录识别项目，若沿用调用者目录，
        # 可能误改另一个项目的环境（实测会把别人的 .venv 当成目标并卸载其依赖）
        Push-Location -LiteralPath $Script:ProjectRoot
        & $exe @rest 2>&1 | ForEach-Object {
            Add-Log 'output' ([string]$_)
            $counter++
            if ($counter % $Script:RedrawEvery -eq 0) { Show-Running $TitleKey $rendered }
        }
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
        Add-Log 'info' (Get-Text 'log.exit_code' @{ code = $code })
        return $code
    } catch {
        Add-Log 'warn' ((Get-Text 'log.command_aborted') + ": " + $_.Exception.Message)
        return 130
    } finally {
        Pop-Location
        $ErrorActionPreference = $previousPreference
    }
}

# ============================================================================
# 6. 环境状态采集
# ============================================================================

function Get-UvPath {
    <#
    .SYNOPSIS
        定位 uv 可执行文件（手工扫描 PATH 优先，其次常见安装目录）。

    .NOTES
        不用 Get-Command 作首选：Windows PowerShell 5.1 的命令发现依赖 PATHEXT，
        实测在同一台机器上会时有时无（同一个脚本多次运行结果不一致）。手工按
        `uv.exe` 扫描 PATH 结果稳定，且不依赖 PATHEXT。
    .OUTPUTS
        String：路径；未安装返回空串。
    #>
    foreach ($dir in ($env:PATH -split ';')) {
        if ($dir -eq '') { continue }
        $candidate = Join-Path $dir 'uv.exe'
        if (Test-Path -LiteralPath $candidate) { return $candidate }
    }
    $candidates = @(
        (Join-Path $env:USERPROFILE '.local\bin\uv.exe'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Links\uv.exe'),
        (Join-Path $env:LOCALAPPDATA 'uv\uv.exe'),
        (Join-Path $env:USERPROFILE '.cargo\bin\uv.exe')
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return ''
}

function Get-FrameworkVersion {
    <#
    .SYNOPSIS
        读取框架版本号（core/version.py 的 VERSION 常量）。
    .OUTPUTS
        String：版本号；缺失返回空串。
    #>
    $file = Join-Path $Script:ProjectRoot 'core\version.py'
    if (-not (Test-Path -LiteralPath $file)) { return '' }
    $match = [regex]::Match([System.IO.File]::ReadAllText($file),
        '^VERSION\s*=\s*["'']([^"'']+)["'']', 'Multiline')
    if ($match.Success) { return $match.Groups[1].Value }
    return ''
}

function Get-VenvPython {
    <#
    .SYNOPSIS
        返回应用虚拟环境内的 Python 解释器路径。
    .OUTPUTS
        String
    #>
    return (Join-Path $Script:AppVenv 'Scripts\python.exe')
}

function Get-MissingImports {
    <#
    .SYNOPSIS
        在应用环境中检查关键依赖是否可导入。
    .OUTPUTS
        String[]：缺失的模块名（试运行下不做检查，视为齐全）。
    #>
    if ($DryRun) { return @() }
    $python = Get-VenvPython
    if (-not (Test-Path -LiteralPath $python)) { return $Script:RequiredImports }
    $quoted = ($Script:RequiredImports | ForEach-Object { "'$_'" }) -join ', '
    $code = "import importlib.util as u, json;print(json.dumps([n for n in [$quoted] if u.find_spec(n) is None]))"
    $result = Invoke-Capture @($python, '-c', $code) $Script:TimeoutProbe
    if ($result.timeout) { return $Script:RequiredImports }
    if (-not $result.ok -or $result.lines.Count -eq 0) { return $Script:RequiredImports }
    try {
        # ConvertFrom-Json 对空数组返回 $null、对数组返回 Object[]，这里统一摊平为字符串数组，
        # 否则 .Count 会因「嵌套数组」而恒为 1，导致环境被误判为损坏
        $missing = @()
        foreach ($item in @(ConvertFrom-Json ($result.lines[-1]))) {
            if ($null -ne $item -and "$item" -ne '') { $missing += [string]$item }
        }
        return $missing
    } catch {
        return $Script:RequiredImports
    }
}

function Get-DirSize {
    <#
    .SYNOPSIS
        统计目录占用字节数（超过文件数上限时提前返回）。
    .PARAMETER Path
        目录路径。
    .OUTPUTS
        Int64：字节数；目录不存在返回 0。
    #>
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    $total = 0
    $counted = 0
    foreach ($item in Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue) {
        $total += $item.Length
        $counted++
        if ($counted -ge $Script:MaxCountedFiles) { break }
    }
    return $total
}

function Format-Size {
    <#
    .SYNOPSIS
        把字节数格式化为人类可读文本。
    .PARAMETER Bytes
        字节数。
    .OUTPUTS
        String：如 1.2 GB。
    #>
    param([double]$Bytes)

    $units = @('B', 'KB', 'MB', 'GB', 'TB')
    $value = $Bytes
    foreach ($unit in $units) {
        if ($value -lt 1024 -or $unit -eq 'TB') {
            if ($unit -eq 'B') { return ('{0:N0} B' -f $value) }
            return ('{0:N1} {1}' -f $value, $unit)
        }
        $value = $value / 1024
    }
    return ('{0:N1} TB' -f $value)
}

function Get-EnvState {
    <#
    .SYNOPSIS
        采集环境状态（uv / 应用环境 / 依赖 / 版本 / Git / 体积）。
    .OUTPUTS
        Hashtable：界面与体检共用的事实集合。
    #>
    $state = @{
        uv_path = Get-UvPath
        uv_version = ''
        venv_exists = Test-Path -LiteralPath (Join-Path $Script:AppVenv 'pyvenv.cfg')
        python_exists = Test-Path -LiteralPath (Get-VenvPython)
        python_version = ''
        missing_imports = @()
        framework_version = Get-FrameworkVersion
        has_lock = Test-Path -LiteralPath (Join-Path $Script:ProjectRoot 'uv.lock')
        has_requirements = Test-Path -LiteralPath (Join-Path $Script:ProjectRoot 'requirements.txt')
        git_available = $false
        git_branch = ''
        git_commit = ''
        git_dirty = $false
        venv_bytes = 0
        platform = Get-PlatformLabel
    }
    if ($state.uv_path -ne '') {
        $version = Invoke-Capture @($state.uv_path, '--version') $Script:TimeoutProbe
        if ($version.ok -and $version.lines.Count -gt 0) { $state.uv_version = $version.lines[0].Trim() }
    }
    if ($state.venv_exists -and $state.python_exists) {
        $probe = Invoke-Capture @((Get-VenvPython), '-c',
            'import sys;print(".".join(str(p) for p in sys.version_info[:3]))') $Script:TimeoutProbe
        if ($probe.ok -and $probe.lines.Count -gt 0) { $state.python_version = $probe.lines[-1].Trim() }
        $state.missing_imports = @(Get-MissingImports)
    } elseif ($state.venv_exists) {
        $state.missing_imports = @('python')
    }
    if (Test-Path -LiteralPath (Join-Path $Script:ProjectRoot '.git')) {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if ($git) {
            $state.git_available = $true
            $branch = Invoke-Capture @('git', 'rev-parse', '--abbrev-ref', 'HEAD') $Script:TimeoutProbe
            if ($branch.ok -and $branch.lines.Count -gt 0) { $state.git_branch = $branch.lines[0].Trim() }
            $commit = Invoke-Capture @('git', 'rev-parse', '--short', 'HEAD') $Script:TimeoutProbe
            if ($commit.ok -and $commit.lines.Count -gt 0) { $state.git_commit = $commit.lines[0].Trim() }
            $status = Invoke-Capture @('git', 'status', '--porcelain') $Script:TimeoutProbe
            $state.git_dirty = ($status.ok -and $status.lines.Count -gt 0)
        }
    }
    if ($state.venv_exists) { $state.venv_bytes = Get-DirSize $Script:AppVenv }
    return $state
}

function Test-EnvReady {
    <#
    .SYNOPSIS
        环境是否可用（存在解释器且关键依赖齐全）。
    .PARAMETER State
        环境状态。
    .OUTPUTS
        Boolean
    #>
    param([hashtable]$State)

    return ($State.venv_exists -and $State.python_exists -and $State.missing_imports.Count -eq 0)
}

# ============================================================================
# 7. 屏幕绘制
# ============================================================================

function Show-Menu {
    <#
    .SYNOPSIS
        绘制主菜单（选中项以 ▸ 标记）。
    .PARAMETER Index
        当前选中项下标（从 1 开始）。
    #>
    param([int]$Index)

    Clear-Screen
    Write-Header
    $items = Get-MenuItems
    for ($i = 0; $i -lt $items.Count; $i++) {
        $number = $i + 1
        $marker = '  '
        $tone = ''
        if ($number -eq $Index) { $marker = "$Script:CursorMark "; $tone = 'accent' }
        Write-Out ("  $number $marker" + $items[$i].Label) $tone
    }
    Write-Footer
}

function Get-MenuItems {
    <#
    .SYNOPSIS
        返回菜单项（标题键 + 页面标识），两平台顺序一致。
    .OUTPUTS
        Hashtable 数组：key / page。
    #>
    return @(
        @{ key = 'menu.status'; page = 'status'; label = (Get-Text 'menu.status') },
        @{ key = 'menu.install'; page = 'install'; label = (Get-Text 'menu.install') },
        @{ key = 'menu.upgrade'; page = 'upgrade'; label = (Get-Text 'menu.upgrade') },
        @{ key = 'menu.manage'; page = 'manage'; label = (Get-Text 'menu.manage') },
        @{ key = 'menu.doctor'; page = 'doctor'; label = (Get-Text 'menu.doctor') },
        @{ key = 'menu.cleanup'; page = 'cleanup'; label = (Get-Text 'menu.cleanup') },
        @{ key = 'menu.launch'; page = 'launch'; label = (Get-Text 'menu.launch') },
        @{ key = 'menu.language'; page = 'language'; label = (Get-Text 'menu.language') },
        @{ key = 'menu.help'; page = 'help'; label = (Get-Text 'menu.help') }
    )
}

function Write-PageTitle {
    <#
    .SYNOPSIS
        输出页面标题与说明。
    .PARAMETER TitleKey
        标题文案键。
    .PARAMETER ExplainKey
        说明文案键（可空）。
    #>
    param([string]$TitleKey, [string]$ExplainKey = '')

    Write-Out (' ' + (Get-Text $TitleKey)) 'title'
    if ($ExplainKey -ne '') { Write-Out (' ' + (Get-Text $ExplainKey)) 'dim' }
    Write-Rule
}

function Write-ActionList {
    <#
    .SYNOPSIS
        输出页面动作列表（编号即快捷键）。
    .PARAMETER Actions
        Hashtable 数组：label / tone。
    #>
    param([array]$Actions)

    for ($i = 0; $i -lt $Actions.Count; $i++) {
        $tone = ''
        if ($Actions[$i].ContainsKey('tone')) { $tone = $Actions[$i].tone }
        Write-Out ("  $($i + 1) " + $Actions[$i].label) $tone
    }
}

function Show-StatusPage {
    <#
    .SYNOPSIS
        环境总览页：一行一项「名称: 值」，不依赖字符宽度计算，两平台输出一致。
    #>
    $state = Get-EnvState
    Clear-Screen
    Write-Header
    Write-PageTitle 'menu.status' 'status.header'
    Write-Out ('  ' + (Get-Text 'status.uv') + ': ' +
        (Format-Value $state.uv_version (Get-Text 'common.not_installed') ($state.uv_path -ne '')))
    Write-Out ('  ' + (Get-Text 'status.python') + ': ' +
        (Format-Value $state.python_version (Get-Text 'common.not_installed') ($state.python_version -ne '')))
    Write-Out ('  ' + (Get-Text 'status.venv') + ': ' + (Get-VenvText $state))
    Write-Out ('  ' + (Get-Text 'status.deps') + ': ' + (Get-DepsText $state))
    Write-Out ('  ' + (Get-Text 'status.framework') + ': ' +
        (Format-Value $state.framework_version (Get-Text 'common.unknown') $true))
    Write-Out ('  ' + (Get-Text 'status.git') + ': ' + (Get-GitText $state))
    Write-Out ('  ' + (Get-Text 'status.platform') + ': ' + $state.platform)
    Write-Out ('  ' + (Get-Text 'status.path') + ': ' + $Script:ProjectRoot)
    if ($state.venv_bytes -gt 0) {
        Write-Out ('  ' + (Get-Text 'manage.disk_usage') + ': ' + (Format-Size $state.venv_bytes))
    }
    Write-Rule
    $hint = if (Test-EnvReady $state) { 'status.next_hint_ready' } else { 'status.next_hint_missing' }
    Write-Out (' ' + (Get-Text $hint)) 'warn'
    Write-ActionList @(
        @{ label = (Get-Text 'menu.install'); tone = 'accent' },
        @{ label = (Get-Text 'menu.doctor') },
        @{ label = (Get-Text 'menu.launch') }
    )
    Write-Footer -Page
}

function Format-Value {
    <#
    .SYNOPSIS
        状态值展示：有值时显示值，无值时显示占位文案。
    .PARAMETER Value
        值。
    .PARAMETER Fallback
        占位文案。
    .PARAMETER Present
        是否视为存在。
    .OUTPUTS
        String
    #>
    param([string]$Value, [string]$Fallback, [bool]$Present)

    if ($Present -and $Value -ne '') { return $Value }
    return $Fallback
}

function Get-VenvText {
    <#
    .SYNOPSIS
        应用环境状态文案。
    .PARAMETER State
        环境状态。
    .OUTPUTS
        String
    #>
    param([hashtable]$State)

    if (Test-EnvReady $State) { return Get-Text 'status.venv_ready' }
    if ($State.venv_exists) { return Get-Text 'status.venv_broken' }
    return Get-Text 'status.venv_missing'
}

function Get-DepsText {
    <#
    .SYNOPSIS
        关键组件文案（缺失时列出模块名）。
    .PARAMETER State
        环境状态。
    .OUTPUTS
        String
    #>
    param([hashtable]$State)

    if ($State.missing_imports.Count -eq 0) { return Get-Text 'common.installed' }
    return ($State.missing_imports -join ', ')
}

function Get-GitText {
    <#
    .SYNOPSIS
        Git 信息文案。
    .PARAMETER State
        环境状态。
    .OUTPUTS
        String
    #>
    param([hashtable]$State)

    if (-not $State.git_available) { return Get-Text 'common.unknown' }
    $text = $State.git_branch
    if ($State.git_commit -ne '') { $text += " @ $($State.git_commit)" }
    if ($State.git_dirty) { $text += ' *' }
    return $text
}

function Show-Running {
    <#
    .SYNOPSIS
        绘制「正在执行」页（实时显示命令与输出尾部）。
    .PARAMETER TitleKey
        标题文案键。
    .PARAMETER Command
        正在执行的命令。
    #>
    param([string]$TitleKey, [string]$Command)

    if ($Script:NonInteractive) { return }
    Clear-Screen
    Write-Header
    Write-PageTitle $TitleKey
    Write-Out ('  $ ' + $Command) 'accent'
    Write-Rule
    foreach ($line in @($Script:LogLines | Select-Object -Last 12)) { Write-Out ('  ' + $line) 'dim' }
    Write-Rule
    Write-Out (' ' + (Get-Text 'ui.abort_hint')) 'dim'
}

function Show-Result {
    <#
    .SYNOPSIS
        绘制结果页并等待按键返回。
    .PARAMETER Tone
        ok / warn / fail。
    .PARAMETER MessageKey
        结果文案键。
    .PARAMETER Params
        占位符参数。
    #>
    param([string]$Tone, [string]$MessageKey, [hashtable]$Params = @{})

    Write-Rule
    # 注意：这里必须用 -Params 显式传参；写成 @Params 会被当成 splatting，
    # 把 detail/version 等键展开成不存在的参数名而报 ParameterBindingException
    Write-Out (' ' + (Get-Text -Key $MessageKey -Params $Params)) $Tone
    Wait-AnyKey
}

function Read-Confirm {
    <#
    .SYNOPSIS
        是 / 否确认弹窗（-Yes 时自动确认）。
    .PARAMETER MessageKey
        问句文案键。
    .PARAMETER Danger
        True 时用危险色显示。
    .OUTPUTS
        Boolean
    #>
    param([string]$MessageKey, [switch]$Danger)

    if ($Yes) {
        Add-Log 'info' ((Get-Text $MessageKey) + ' -> -Yes')
        return $true
    }
    Write-Rule
    Write-Out (' ' + (Get-Text 'common.confirm')) $(if ($Danger) { 'fail' } else { 'warn' })
    Write-Out (' ' + (Get-Text $MessageKey)) ''
    Write-Out (' ' + (Get-Text 'ui.dialog_keys')) 'dim'
    while ($true) {
        $key = Read-MenuKey
        if ($key -eq 'yes' -or $key -eq 'enter') { return $true }
        if ($key -eq 'no' -or $key -eq 'escape' -or $key -eq 'quit') { return $false }
    }
}

# ============================================================================
# 8. 动作：安装与修复
# ============================================================================

function Get-UvArgv {
    <#
    .SYNOPSIS
        构造 uv 命令（未安装时用裸 uv，交由调用方先安装）。
    .PARAMETER UvArgs
        uv 子命令与参数。
    .OUTPUTS
        String[]
    #>
    param([string[]]$UvArgs)

    $uv = Get-UvPath
    if ($uv -eq '') { $uv = 'uv' }
    return @($uv) + $UvArgs
}

function Test-FirstInstall {
    <#
    .SYNOPSIS
        是否尚未创建应用运行环境（决定用 uv sync 还是 uv pip install）。
    .OUTPUTS
        Boolean
    #>
    return -not (Test-Path -LiteralPath (Join-Path $Script:AppVenv 'pyvenv.cfg'))
}

function Install-Uv {
    <#
    .SYNOPSIS
        确保 uv 可用；缺失时先征得用户同意再执行官方安装脚本。
    .OUTPUTS
        Boolean：uv 是否可用。
    #>
    if ((Get-UvPath) -ne '') { return $true }
    Add-Log 'warn' (Get-Text 'install.need_uv_confirm')
    if (-not (Read-Confirm 'install.need_uv_confirm')) {
        Add-Log 'warn' (Get-Text 'common.cancel')
        return $false
    }
    Add-Log 'info' (Get-Text 'install.uv_install_cmd' @{ cmd = $Script:UvInstallCmd })
    [void](Invoke-Stream @('powershell', '-NoProfile', '-ExecutionPolicy', 'ByPass',
        '-Command', 'irm https://astral.sh/uv/install.ps1 | iex') 'install.step_uv')
    if ((Get-UvPath) -eq '') {
        Set-Status 'fail' (Get-Text 'install.uv_manual' @{ cmd = $Script:UvInstallCmd })
        return $false
    }
    return $true
}

function Install-PythonRuntime {
    <#
    .SYNOPSIS
        准备项目要求的 Python（失败只警告：系统已有解释器时后续步骤仍可成功）。
    .OUTPUTS
        Boolean：uv 是否成功管理了该 Python 副本。
    #>
    $code = Invoke-Stream (Get-UvArgv @('python', 'install', $Script:RequiredPython)) 'install.step_python'
    if ($code -ne 0) {
        Add-Log 'warn' (Get-Text 'install.python_download_hint' @{ url = $Script:PythonUrl })
        return $false
    }
    return $true
}

function Test-LockUsable {
    <#
    .SYNOPSIS
        uv.lock 是否可用（存在、非空、且是 uv 的 TOML 锁文件）。

    .NOTES
        空文件或半截文件（下载/写入中断、被其他程序清空）会让 ``uv sync`` 直接报
        「Failed to parse uv.lock」，用户完全看不懂；这里提前识别并回退到
        ``uv pip install -r requirements.txt``，保证安装仍能完成。
    .OUTPUTS
        Boolean
    #>
    $lock = Join-Path $Script:ProjectRoot 'uv.lock'
    if (-not (Test-Path -LiteralPath $lock)) { return $false }
    try {
        $info = Get-Item -LiteralPath $lock
        if ($info.Length -le 0) { return $false }
        $head = [System.IO.File]::ReadAllText($lock)
        return $head.StartsWith('version =')
    } catch {
        return $false
    }
}

function Install-Dependencies {
    <#
    .SYNOPSIS
        安装或修复依赖：初次装用 uv sync，已有环境用 uv pip install（不删除插件自装依赖）。
    .OUTPUTS
        Int：命令退出码。
    #>
    if (Test-FirstInstall -and (Test-LockUsable)) {
        return Invoke-Stream (Get-UvArgv $Script:SyncArgs) 'install.step_deps'
    }
    if (Test-FirstInstall) {
        Add-Log 'warn' ((Get-Text 'log.lock_unusable') + ': uv.lock')
    }
    return Invoke-Stream (Get-UvArgv $Script:PipArgs) 'install.step_deps'
}

function Get-VerifyResult {
    <#
    .SYNOPSIS
        自检关键组件能否导入。
    .OUTPUTS
        Hashtable：ok / missing。
    #>
    if (-not (Test-Path -LiteralPath (Get-VenvPython))) {
        return @{ ok = $false; missing = @($Script:RequiredImports) }
    }
    $missing = @(Get-MissingImports)
    return @{ ok = ($missing.Count -eq 0); missing = $missing }
}

function Invoke-Install {
    <#
    .SYNOPSIS
        执行安装或修复，并按自检结果给出结论。
    .PARAMETER RepairOnly
        True 时只更新依赖（不询问 uv 安装、不准备 Python）。
    #>
    param([switch]$RepairOnly)

    $first = Test-FirstInstall
    Add-Log 'info' (Get-Text $(if ($first) { 'install.first_time' } else { 'install.repair' }))
    if (-not $RepairOnly) {
        if (-not (Install-Uv)) {
            Show-Result 'fail' 'common.failed'
            return
        }
        [void](Install-PythonRuntime)
    } elseif ((Get-UvPath) -eq '') {
        Set-Status 'fail' (Get-Text 'common.not_installed')
        Show-Result 'fail' 'common.failed'
        return
    }
    [void](Install-Dependencies)
    $verify = Get-VerifyResult
    if ($verify.ok) {
        if ($first) { [void](Install-DesktopShortcut) }
        $key = if ($RepairOnly) { 'install.repaired' } else { 'install.success' }
        Show-Result 'ok' $key
        return
    }
    Show-Result 'fail' 'install.verify_failed' @{ detail = ($verify.missing -join ', ') }
}

# ============================================================================
# 9. 动作：升级框架
# ============================================================================

function Get-UpgradeMode {
    <#
    .SYNOPSIS
        升级方式：有 git 仓库且 git 可用时用 git pull，否则下载官方压缩包。
    .OUTPUTS
        String：git / zip。
    #>
    if ((Test-Path -LiteralPath (Join-Path $Script:ProjectRoot '.git')) -and
        (Get-Command git -ErrorAction SilentlyContinue)) { return 'git' }
    return 'zip'
}

function Get-LocalChanges {
    <#
    .SYNOPSIS
        检测已跟踪文件的本地修改（未跟踪文件不影响 git pull）。
    .OUTPUTS
        String[]：git status 输出行。
    #>
    $result = Invoke-Capture @('git', 'status', '--porcelain', '--untracked-files=no') $Script:TimeoutProbe
    if (-not $result.ok) { return @() }
    return @($result.lines | Where-Object { $_.Trim() -ne '' })
}

function Get-RemoteArchive {
    <#
    .SYNOPSIS
        取升级用的代码压缩包：默认从官方地址下载，``-ArchivePath`` 指定时直接用本地压缩包。
    .OUTPUTS
        String：压缩包路径；失败返回空串。

    .NOTES
        ``-ArchivePath`` 支持离线升级（内网/无外网环境）：管理员把官方压缩包拷到本机，
        向导即可完成与在线升级完全相同的覆盖流程（同样保护用户数据）。
    #>
    if ($ArchivePath -ne '') {
        if (-not (Test-Path -LiteralPath $ArchivePath)) {
            Add-Log 'error' ((Get-Text 'log.archive_missing') + ": $ArchivePath")
            return ''
        }
        Add-Log 'info' ((Get-Text 'log.archive_local') + ": $ArchivePath")
        return (Resolve-Path -LiteralPath $ArchivePath).Path
    }
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ": $Script:ZipUrl")
        return ''
    }
    if (-not (Test-Path -LiteralPath $Script:WorkDir)) {
        [void](New-Item -ItemType Directory -Path $Script:WorkDir -Force)
    }
    $target = Join-Path $Script:WorkDir 'InstructionX-main.zip'
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $Script:ZipUrl -OutFile $target -UseBasicParsing -TimeoutSec $Script:TimeoutDownload
        return $target
    } catch {
        Add-Log 'error' ((Get-Text 'log.download_failed') + ": " + $_.Exception.Message)
        return ''
    }
}

function Expand-RemoteArchive {
    <#
    .SYNOPSIS
        解压压缩包并返回仓库根目录。
    .PARAMETER Archive
        压缩包路径。
    .OUTPUTS
        String：仓库根目录；失败返回空串。
    #>
    param([string]$Archive)

    $target = Join-Path $Script:WorkDir 'src'
    try {
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
        Expand-Archive -LiteralPath $Archive -DestinationPath $target -Force
    } catch {
        Add-Log 'error' ((Get-Text 'log.extract_failed') + ": " + $_.Exception.Message)
        return ''
    }
    $roots = @(Get-ChildItem -LiteralPath $target -Directory)
    if ($roots.Count -ne 1) {
        Add-Log 'error' (Get-Text 'log.archive_layout')
        return ''
    }
    return $roots[0].FullName
}

function Copy-DirectoryMerge {
    <#
    .SYNOPSIS
        把源目录的内容递归合并进目标目录（同名文件覆盖，缺失目录创建）。
    .PARAMETER Source
        源目录（新代码）。
    .PARAMETER Destination
        目标目录（现有程序目录）。

    .NOTES
        不能用 ``Copy-Item -Recurse``：当目标目录已存在时，PowerShell 会把**源目录本身**
        放进目标里，得到 ``core\core\...`` 这种错位结构（实测升级后程序文件全部错位）。
        这里显式逐层合并，并在任意层级跳过 ``__pycache__`` / ``.git``。
    #>
    param([string]$Source, [string]$Destination)

    if (-not (Test-Path -LiteralPath $Destination)) {
        [void](New-Item -ItemType Directory -Path $Destination -Force)
    }
    foreach ($child in Get-ChildItem -LiteralPath $Source -Force) {
        if ($Script:SkipDirs -contains $child.Name) { continue }
        $target = Join-Path $Destination $child.Name
        if ($child.PSIsContainer) {
            Copy-DirectoryMerge -Source $child.FullName -Destination $target
            continue
        }
        Copy-Item -LiteralPath $child.FullName -Destination $target -Force
    }
}

function Copy-ProgramFiles {
    <#
    .SYNOPSIS
        把新代码覆盖到项目根（保留用户数据与本地环境，跳过仓库元数据）。
    .PARAMETER SourceRoot
        解压后的仓库根目录。
    #>
    param([string]$SourceRoot)

    $copied = 0
    foreach ($item in Get-ChildItem -LiteralPath $SourceRoot -Force) {
        if ($Script:PreserveDirs -contains $item.Name -or $Script:SkipDirs -contains $item.Name) {
            continue
        }
        $destination = Join-Path $Script:ProjectRoot $item.Name
        try {
            if ($item.PSIsContainer) {
                Copy-DirectoryMerge -Source $item.FullName -Destination $destination
            } else {
                Copy-Item -LiteralPath $item.FullName -Destination $destination -Force
            }
            $copied++
        } catch {
            Add-Log 'warn' ((Get-Text 'log.overwrite_failed' @{ name = $item.Name }) + ": " + $_.Exception.Message)
        }
    }
    Add-Log 'info' ((Get-Text 'log.overwrite_done' @{ count = $copied }) + '; ' + (Get-Text 'log.preserved' @{ items = ($Script:PreserveDirs -join ', ') }))
}

function Invoke-Upgrade {
    <#
    .SYNOPSIS
        执行升级（git pull 或压缩包覆盖），随后同步依赖并汇报版本变化。
    #>
    $before = Get-FrameworkVersion
    $mode = Get-UpgradeMode
    if ($mode -eq 'git') {
        $changes = @(Get-LocalChanges)
        $code = Invoke-Stream @('git', 'pull', '--ff-only') 'upgrade.title'
        if ($code -ne 0) {
            $detail = if ($changes.Count -gt 0) { $changes[0] } else { "git exit $code" }
            Show-Result 'warn' 'upgrade.local_changes' @{ detail = $detail }
            return
        }
    } else {
        if (-not (Read-Confirm 'upgrade.need_git_confirm')) {
            Add-Log 'warn' (Get-Text 'common.cancel')
            return
        }
        $archive = Get-RemoteArchive
        if ($archive -eq '') { Show-Result 'fail' 'common.failed'; return }
        $root = Expand-RemoteArchive $archive
        if ($root -eq '') { Show-Result 'fail' 'common.failed'; return }
        Copy-ProgramFiles $root
    }
    [void](Install-Dependencies)
    $verify = Get-VerifyResult
    $after = Get-FrameworkVersion
    if ($verify.ok) {
        Show-Result 'ok' 'upgrade.success' @{ version = $after; before = $before }
    } else {
        Show-Result 'fail' 'install.verify_failed' @{ detail = ($verify.missing -join ', ') }
    }
    Remove-WorkDir
}

function Remove-WorkDir {
    <#
    .SYNOPSIS
        清理升级临时目录（失败不影响主流程）。
    #>
    if ($DryRun) { return }
    if (Test-Path -LiteralPath $Script:WorkDir) {
        Remove-Item -LiteralPath $Script:WorkDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ============================================================================
# 10. 动作：一键体检
# ============================================================================

function New-Check {
    <#
    .SYNOPSIS
        构造一项体检结果。
    .PARAMETER Key
        检查项文案键。
    .PARAMETER Tone
        ok / warn / fail。
    .PARAMETER Detail
        细节（已本地化的原始值）。
    .PARAMETER Advice
        建议文案键。
    .OUTPUTS
        Hashtable
    #>
    param([string]$Key, [string]$Tone, [string]$Detail = '', [string]$Advice = '')

    return @{ key = $Key; tone = $Tone; detail = $Detail; advice = $Advice }
}

function Test-FolderWritable {
    <#
    .SYNOPSIS
        检查目录是否可写（写入并删除探针文件）。
    .PARAMETER Name
        相对项目根的目录名（config / data）。
    .OUTPUTS
        String：空串表示可写，否则为失败原因。
    #>
    param([string]$Name)

    $folder = Join-Path $Script:ProjectRoot $Name
    try {
        if (-not (Test-Path -LiteralPath $folder)) { [void](New-Item -ItemType Directory -Path $folder -Force) }
        $probe = Join-Path $folder '.write_probe'
        [System.IO.File]::WriteAllText($probe, 'ok', [System.Text.Encoding]::UTF8)
        Remove-Item -LiteralPath $probe -Force
        return ''
    } catch {
        return "$Name`: $($_.Exception.Message)"
    }
}

function Test-Network {
    <#
    .SYNOPSIS
        能否访问软件源（PyPI:443）。
    .OUTPUTS
        Boolean
    #>
    if ($DryRun) { return $true }
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $task = $client.ConnectAsync('pypi.org', 443)
        if (-not $task.Wait(5000)) { return $false }
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Get-FreeDiskBytes {
    <#
    .SYNOPSIS
        返回项目所在磁盘的剩余空间。
    .OUTPUTS
        Int64：字节数；查询失败返回 -1。
    #>
    try {
        $root = [System.IO.Path]::GetPathRoot($Script:ProjectRoot)
        $drive = New-Object System.IO.DriveInfo $root
        return $drive.AvailableFreeSpace
    } catch {
        return -1
    }
}

function Get-DoctorChecks {
    <#
    .SYNOPSIS
        执行 9 项体检（界面与文本报告共用同一套判定）。
    .OUTPUTS
        Hashtable 数组：key / tone / detail / advice。
    #>
    $state = Get-EnvState
    $ready = Test-EnvReady $state
    $uvAdvice = if ($state.uv_path -ne '') { '' } else { 'doctor.advice_install_uv' }
    $checks = @()
    $checks += New-Check 'doctor.check_uv' $(if ($state.uv_path -ne '') { 'ok' } else { 'fail' }) `
        $state.uv_version $uvAdvice
    $pythonTone = if ($state.python_version -ne '') { 'ok' } elseif ($state.uv_path -ne '') { 'warn' } else { 'fail' }
    $pythonAdvice = if ($pythonTone -eq 'ok') { '' } elseif ($pythonTone -eq 'warn') { 'doctor.advice_run_install' } else { 'doctor.advice_install_uv' }
    $checks += New-Check 'doctor.check_python' $pythonTone $state.python_version $pythonAdvice
    $checks += New-Check 'doctor.check_venv' $(if ($ready) { 'ok' } else { 'fail' }) `
        $Script:AppVenv $(if ($ready) { '' } else { 'doctor.advice_run_install' })
    $importsDetail = if ($ready) { $Script:RequiredImports -join ', ' } else { $state.missing_imports -join ', ' }
    $checks += New-Check 'doctor.check_imports' $(if ($ready) { 'ok' } else { 'fail' }) `
        $importsDetail $(if ($ready) { '' } else { 'doctor.advice_run_install' })
    $checks += Get-FolderCheck
    $checks += Get-LockCheck $state
    $checks += Get-NetworkCheck
    $checks += Get-PlatformCheck
    $checks += Get-DiskCheck
    return $checks
}

function Get-FolderCheck {
    <#
    .SYNOPSIS
        「配置 / 数据目录是否可写」检查项。
    .OUTPUTS
        Hashtable
    #>
    if ($DryRun) { return New-Check 'doctor.check_writable' 'ok' 'dry-run' }
    $problems = @()
    foreach ($name in @('config', 'data')) {
        $problem = Test-FolderWritable $name
        if ($problem -ne '') { $problems += $problem }
    }
    if ($problems.Count -gt 0) {
        return New-Check 'doctor.check_writable' 'fail' ($problems -join '; ') 'doctor.advice_free_disk'
    }
    return New-Check 'doctor.check_writable' 'ok'
}

function Get-LockCheck {
    <#
    .SYNOPSIS
        「依赖清单与锁文件是否齐备」检查项。
    .PARAMETER State
        环境状态。
    .OUTPUTS
        Hashtable
    #>
    param([hashtable]$State)

    $missing = @()
    if (-not $State.has_requirements) { $missing += 'requirements.txt' }
    if (-not $State.has_lock) { $missing += 'uv.lock' }
    if ($missing.Count -gt 0) {
        return New-Check 'doctor.check_lock' 'warn' ($missing -join ', ') 'doctor.advice_run_install'
    }
    return New-Check 'doctor.check_lock' 'ok'
}

function Get-NetworkCheck {
    <#
    .SYNOPSIS
        「能否访问软件源」检查项。
    .OUTPUTS
        Hashtable
    #>
    if ($DryRun) { return New-Check 'doctor.check_network' 'ok' 'dry-run' }
    if (Test-Network) { return New-Check 'doctor.check_network' 'ok' 'pypi.org' }
    return New-Check 'doctor.check_network' 'warn' '' 'doctor.advice_check_network'
}

function Get-PlatformCheck {
    <#
    .SYNOPSIS
        「系统平台是否受支持」检查项（Windows 为框架主平台）。
    .OUTPUTS
        Hashtable
    #>
    return New-Check 'doctor.check_platform' 'ok' (Get-PlatformLabel)
}

function Get-DiskCheck {
    <#
    .SYNOPSIS
        「磁盘剩余空间是否充足」检查项。
    .OUTPUTS
        Hashtable
    #>
    $free = Get-FreeDiskBytes
    if ($free -lt 0) { return New-Check 'doctor.check_disk' 'warn' }
    if ($free -lt $Script:MinFreeDiskBytes) {
        return New-Check 'doctor.check_disk' 'warn' (Format-Size $free) 'doctor.advice_free_disk'
    }
    return New-Check 'doctor.check_disk' 'ok' (Format-Size $free)
}

function Get-CheckName {
    <#
    .SYNOPSIS
        体检项名称（含 python 版本等占位符）。
    .PARAMETER Key
        文案键。
    .OUTPUTS
        String
    #>
    param([string]$Key)

    return Get-Text $Key @{ python = $Script:RequiredPython; platform = (Get-PlatformLabel) }
}

function Get-AdviceText {
    <#
    .SYNOPSIS
        体检建议文案（无建议时返回空串）。
    .PARAMETER Check
        检查项。
    .OUTPUTS
        String
    #>
    param([hashtable]$Check)

    if ($Check.advice -eq '') { return '' }
    return Get-Text $Check.advice @{ platform = (Get-PlatformLabel); python = $Script:RequiredPython }
}

# ============================================================================
# 11. 动作：环境管理、清理、启动
# ============================================================================

function Get-DesktopShortcutPath {
    <#
    .SYNOPSIS
        返回桌面快捷方式的完整路径。
    .NOTES
        用 [Environment]::GetFolderPath 取桌面：OneDrive 重定向的桌面也能正确定位。
    .OUTPUTS
        String
    #>
    return (Join-Path ([Environment]::GetFolderPath('Desktop')) $Script:ShortcutName)
}

function Install-DesktopShortcut {
    <#
    .SYNOPSIS
        首次安装成功后创建桌面快捷方式（已存在则跳过）。
    .NOTES
        目标用 pythonw.exe 而不是 python.exe：双击启动 GUI 时不出现控制台黑窗；
        向导内「启动应用」仍走 python.exe（保留输出，仅作调试用途）。
    .OUTPUTS
        Boolean：快捷方式是否可用。
    #>
    $path = Get-DesktopShortcutPath
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + (Get-Text 'log.shortcut_create') + " $path")
        return $true
    }
    if (Test-Path -LiteralPath $path) { return $true }
    $pythonw = Join-Path $Script:AppVenv 'Scripts\pythonw.exe'
    if (-not (Test-Path -LiteralPath $pythonw)) {
        Add-Log 'warn' ((Get-Text 'log.shortcut_failed') + ': pythonw.exe')
        return $false
    }
    try {
        $link = (New-Object -ComObject WScript.Shell).CreateShortcut($path)
        $link.TargetPath = $pythonw
        $link.Arguments = '"{0}"' -f (Join-Path $Script:ProjectRoot 'main.py')
        $link.WorkingDirectory = $Script:ProjectRoot
        if (Test-Path -LiteralPath $Script:ShortcutIcon) { $link.IconLocation = $Script:ShortcutIcon }
        $link.Description = 'InstructionX'
        $link.WindowStyle = 1
        $link.Save()
        Add-Log 'info' (Get-Text 'log.shortcut_created' @{ path = $path })
        return $true
    } catch {
        # 快捷方式失败不影响安装结论：应用本身已就绪，仅提示用户可手动创建
        Add-Log 'warn' ((Get-Text 'log.shortcut_failed') + ': ' + $_.Exception.Message)
        return $false
    }
}

function Remove-DesktopShortcut {
    <#
    .SYNOPSIS
        删除桌面快捷方式（卸载时调用；不存在视为成功）。
    #>
    $path = Get-DesktopShortcutPath
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + (Get-Text 'log.shortcut_remove') + " $path")
        return
    }
    if (-not (Test-Path -LiteralPath $path)) { return }
    try {
        Remove-Item -LiteralPath $path -Force
        Add-Log 'info' (Get-Text 'log.shortcut_deleted' @{ path = $path })
    } catch {
        Add-Log 'warn' ((Get-Text 'log.delete_failed' @{ path = $path }) + ': ' + $_.Exception.Message)
    }
}

function Remove-AppVenv {
    <#
    .SYNOPSIS
        删除应用运行环境（数据保留）。
    .OUTPUTS
        Boolean：是否删除成功（目录本就不存在视为成功）。
    #>
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + (Get-Text 'log.delete_env') + " $Script:AppVenv")
        return $true
    }
    if (-not (Test-Path -LiteralPath $Script:AppVenv)) { return $true }
    try {
        Remove-Item -LiteralPath $Script:AppVenv -Recurse -Force
        Add-Log 'info' (Get-Text 'log.deleted' @{ path = $Script:AppVenv })
        return $true
    } catch {
        Add-Log 'error' ((Get-Text 'log.delete_failed' @{ path = $Script:AppVenv }) + ": " + $_.Exception.Message)
        return $false
    }
}

function Invoke-Rebuild {
    <#
    .SYNOPSIS
        重建运行环境：删除 .venv 后重新安装（配置与数据不动）。
    #>
    if (-not (Read-Confirm 'manage.rebuild_confirm')) { return }
    if (-not (Remove-AppVenv)) { Show-Result 'fail' 'common.failed'; return }
    Invoke-Install
}

function Invoke-RefreshDeps {
    <#
    .SYNOPSIS
        仅更新依赖组件（不删除环境、不询问 uv 安装）。
    #>
    [void](Install-Dependencies)
    $verify = Get-VerifyResult
    if ($verify.ok) { Show-Result 'ok' 'manage.refresh_done'; return }
    Show-Result 'fail' 'install.verify_failed' @{ detail = ($verify.missing -join ', ') }
}

function Invoke-CleanCache {
    <#
    .SYNOPSIS
        清理 uv 下载缓存（不影响已安装环境）。
    #>
    $code = Invoke-Stream (Get-UvArgv @('cache', 'clean')) 'manage.clear_cache'
    if ($code -eq 0) {
        $cache = if ($env:UV_CACHE_DIR) { $env:UV_CACHE_DIR } else { Join-Path $env:LOCALAPPDATA 'uv\cache' }
        Set-Status 'ok' (Get-Text 'manage.clear_cache_done' @{ path = $cache })
        Show-Result 'ok' 'manage.clear_cache_done' @{ path = $cache }
        return
    }
    Show-Result 'fail' 'common.failed'
}

function Open-Folder {
    <#
    .SYNOPSIS
        在文件管理器中打开项目内的目录（config / data / logs）。
    .PARAMETER Name
        目录名。
    #>
    param([string]$Name)

    $folder = Join-Path $Script:ProjectRoot $Name
    if (-not (Test-Path -LiteralPath $folder)) { [void](New-Item -ItemType Directory -Path $folder -Force) }
    if ($DryRun) {
        Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + (Get-Text 'log.open_folder') + " $folder")
        return
    }
    try {
        Start-Process -FilePath 'explorer.exe' -ArgumentList $folder | Out-Null
        Add-Log 'info' $folder
    } catch {
        Add-Log 'warn' ((Get-Text 'log.open_folder_failed') + ": " + $_.Exception.Message)
    }
}

function Invoke-RemoveVenv {
    <#
    .SYNOPSIS
        删除运行环境（仅 .venv，数据保留）。
    #>
    if (-not (Read-Confirm 'manage.remove_venv_confirm')) { return }
    if (Remove-AppVenv) { Show-Result 'ok' 'manage.remove_venv_done'; return }
    Show-Result 'fail' 'common.failed'
}

function Invoke-RecreateShortcut {
    <#
    .SYNOPSIS
        重建桌面快捷方式（误删后恢复；先删后建，图标或路径变更也能刷新）。
    .NOTES
        快捷方式目标为 .venv 的解释器，环境未安装时引导用户先执行「安装 / 修复环境」。
    #>
    $state = Get-EnvState
    if (-not ($state.venv_exists -and $state.python_exists)) {
        Show-Result 'warn' 'launch.need_install'
        return
    }
    Remove-DesktopShortcut
    if (Install-DesktopShortcut) { Show-Result 'ok' 'manage.recreate_shortcut_done'; return }
    Show-Result 'fail' 'common.failed'
}

function Invoke-CleanTemp {
    <#
    .SYNOPSIS
        清理向导临时文件（升级下载残留）。
    #>
    Remove-WorkDir
    Set-Status 'ok' (Get-Text 'cleanup.temp_done')
    Show-Result 'ok' 'cleanup.temp_done'
}

function Invoke-Uninstall {
    <#
    .SYNOPSIS
        彻底卸载：删除环境、配置与数据（程序文件保留，需两次确认）。
    #>
    if (-not (Read-Confirm 'cleanup.uninstall_warning' -Danger)) { return }
    if (-not (Read-Confirm 'cleanup.uninstall_confirm' -Danger)) { return }
    $failed = @()
    foreach ($name in $Script:UninstallDirs) {
        $target = Join-Path $Script:ProjectRoot $name
        if (-not (Test-Path -LiteralPath $target)) { continue }
        if ($DryRun) {
            Add-Log 'info' ((Get-Text 'common.dry_run') + ': ' + (Get-Text 'log.delete_env') + " $target")
            continue
        }
        try {
            Remove-Item -LiteralPath $target -Recurse -Force
            Add-Log 'info' (Get-Text 'log.deleted' @{ path = $target })
        } catch {
            $failed += "$name`: $($_.Exception.Message)"
            Add-Log 'error' ((Get-Text 'log.delete_failed' @{ path = $target }) + ": " + $_.Exception.Message)
        }
    }
    # 桌面快捷方式随卸载一并删除，避免残留指向已删除环境的失效入口
    Remove-DesktopShortcut
    if ($failed.Count -gt 0) {
        Show-Result 'fail' 'common.failed' @{ detail = ($failed -join '; ') }
        return
    }
    Show-Result 'ok' 'cleanup.uninstall_done'
}

function Invoke-Launch {
    <#
    .SYNOPSIS
        使用已安装环境启动应用（关闭应用窗口后回到向导）。
    #>
    $state = Get-EnvState
    if (-not (Test-EnvReady $state)) {
        Set-Status 'warn' (Get-Text 'launch.need_install')
        Show-Result 'warn' 'launch.need_install'
        return
    }
    Add-Log 'info' (Get-Text 'launch.starting')
    $code = Invoke-Stream @((Get-VenvPython), (Join-Path $Script:ProjectRoot 'main.py')) 'launch.title'
    Show-Result 'ok' 'launch.exit_code' @{ code = $code }
}

# ============================================================================
# 12. 页面
# ============================================================================

function Show-InstallPage {
    <#
    .SYNOPSIS
        安装 / 修复页：展示将要执行的步骤与命令，避免用户不知道向导在做什么。
    #>
    $first = Test-FirstInstall
    Clear-Screen
    Write-Header
    Write-PageTitle 'install.title' 'install.explain'
    Write-Out (' ' + (Get-Text $(if ($first) { 'install.first_time' } else { 'install.repair' }))) 'warn'
    Write-Rule
    Write-Out (' ' + (Get-Text 'install.plan')) 'dim'
    Write-Out ('   1. ' + (Get-Text 'install.step_uv'))
    Write-Out ('   2. ' + (Get-Text 'install.step_python' @{ python = $Script:RequiredPython }))
    Write-Out ('   3. ' + (Get-Text 'install.step_venv'))
    Write-Out ('   4. ' + (Get-Text 'install.step_deps'))
    Write-Out ('   5. ' + (Get-Text 'install.step_verify'))
    Write-Rule
    $command = if ($first) { Get-UvArgv $Script:SyncArgs } else { Get-UvArgv $Script:PipArgs }
    Write-Out ('   $ ' + ($command -join ' ')) 'dim'
    Write-Rule
    Write-ActionList @(
        @{ label = (Get-Text 'menu.install'); tone = 'accent' },
        @{ label = (Get-Text 'manage.refresh_deps') }
    )
    Write-Footer -Page
}

function Show-UpgradePage {
    <#
    .SYNOPSIS
        升级页：展示当前版本、升级方式与本地修改提醒。
    #>
    $state = Get-EnvState
    $mode = Get-UpgradeMode
    Clear-Screen
    Write-Header
    Write-PageTitle 'upgrade.title' 'upgrade.explain'
    Write-Out (' ' + (Get-Text 'upgrade.current_version') + ': ' +
        (Format-Value $state.framework_version (Get-Text 'common.unknown') $true))
    $modeKey = if ($mode -eq 'git') { 'upgrade.with_git' } else { 'upgrade.without_git' }
    Write-Out (' ' + (Get-Text $modeKey))
    Write-Out (' ' + (Get-Text 'upgrade.preserve' @{ items = ($Script:PreserveDirs -join ', ') })) 'dim'
    if ($mode -eq 'git') {
        $changes = @(Get-LocalChanges)
        if ($changes.Count -gt 0) {
            Write-Out (' ' + (Get-Text 'upgrade.local_changes' @{ detail = $changes[0] })) 'warn'
        }
    }
    Write-Rule
    Write-ActionList @(
        @{ label = (Get-Text 'menu.upgrade'); tone = 'accent' },
        @{ label = (Get-Text 'common.refresh') }
    )
    Write-Footer -Page
}

function Show-ManagePage {
    <#
    .SYNOPSIS
        环境管理页：重建、更新依赖、清缓存、打开目录、重建快捷方式、删除环境。
    #>
    $state = Get-EnvState
    Clear-Screen
    Write-Header
    Write-PageTitle 'manage.title'
    $size = if ($state.venv_bytes -gt 0) { Format-Size $state.venv_bytes } else { Get-Text 'common.unknown' }
    Write-Out (' ' + (Get-Text 'manage.disk_usage') + ': ' + $size)
    Write-Out (' ' + (Get-Text 'status.venv') + ': ' + (Get-VenvText $state))
    Write-Rule
    Write-ActionList @(
        @{ label = (Get-Text 'manage.rebuild'); tone = 'warn' },
        @{ label = (Get-Text 'manage.refresh_deps') },
        @{ label = (Get-Text 'manage.clear_cache') },
        @{ label = (Get-Text 'manage.open_config') },
        @{ label = (Get-Text 'manage.open_data') },
        @{ label = (Get-Text 'manage.open_logs') },
        @{ label = (Get-Text 'manage.recreate_shortcut') },
        @{ label = (Get-Text 'manage.remove_venv'); tone = 'fail' }
    )
    Write-Footer -Page
}

function Show-DoctorPage {
    <#
    .SYNOPSIS
        体检页：逐项展示检查结果与建议。
    #>
    Clear-Screen
    Write-Header
    Write-PageTitle 'doctor.title' 'doctor.explain'
    $checks = @(Get-DoctorChecks)
    $problems = @($checks | Where-Object { $_.tone -ne 'ok' })
    foreach ($check in $checks) {
        $mark = switch ($check.tone) { 'ok' { 'OK ' } 'warn' { '!  ' } default { 'X  ' } }
        $tone = switch ($check.tone) { 'ok' { 'ok' } 'warn' { 'warn' } default { 'fail' } }
        $line = "  $mark" + (Get-CheckName $check.key)
        if ($check.detail -ne '') { $line += "  ($($check.detail))" }
        Write-Out $line $tone
        $advice = Get-AdviceText $check
        if ($advice -ne '') { Write-Out ('       ' + (Get-Text 'doctor.advice' @{ advice = $advice })) 'dim' }
    }
    Write-Rule
    if ($problems.Count -eq 0) {
        Write-Out (' ' + (Get-Text 'doctor.all_ok')) 'ok'
    } else {
        Write-Out (' ' + (Get-Text 'doctor.has_problems' @{ count = $problems.Count })) 'warn'
    }
    Write-ActionList @(@{ label = (Get-Text 'menu.doctor'); tone = 'accent' })
    Write-Footer -Page
}

function Show-CleanupPage {
    <#
    .SYNOPSIS
        清理与卸载页：低风险清理与高风险卸载分级展示。
    #>
    Clear-Screen
    Write-Header
    Write-PageTitle 'cleanup.title' 'cleanup.explain'
    Write-Out (' ' + (Get-Text 'cleanup.uninstall_warning')) 'fail'
    Write-Rule
    Write-ActionList @(
        @{ label = (Get-Text 'cleanup.temp') },
        @{ label = (Get-Text 'manage.clear_cache') },
        @{ label = (Get-Text 'cleanup.uninstall'); tone = 'fail' }
    )
    Write-Footer -Page
}

function Show-LaunchPage {
    <#
    .SYNOPSIS
        启动页：环境未就绪时给出提示。
    #>
    $state = Get-EnvState
    Clear-Screen
    Write-Header
    Write-PageTitle 'launch.title' 'launch.explain'
    if (Test-EnvReady $state) {
        Write-Out (' ' + (Get-Text 'launch.starting')) 'ok'
        Write-Out ('   ' + (Get-VenvPython)) 'dim'
    } else {
        Write-Out (' ' + (Get-Text 'launch.need_install')) 'warn'
    }
    Write-Rule
    Write-ActionList @(@{ label = (Get-Text 'menu.launch'); tone = 'accent' })
    Write-Footer -Page
}

function Show-LanguagePage {
    <#
    .SYNOPSIS
        语言页：中英切换（立即生效，无需重启）。
    #>
    Clear-Screen
    Write-Header
    Write-PageTitle 'menu.language'
    $zhMark = if ($Script:UiLang -eq 'zh') { "$Script:CursorMark " } else { '  ' }
    $enMark = if ($Script:UiLang -eq 'en') { "$Script:CursorMark " } else { '  ' }
    Write-Out ("  1 $zhMark" + (Get-Text 'lang.name.zh')) $(if ($Script:UiLang -eq 'zh') { 'accent' } else { '' })
    Write-Out ("  2 $enMark" + (Get-Text 'lang.name.en')) $(if ($Script:UiLang -eq 'en') { 'accent' } else { '' })
    Write-Rule
    Write-Out (' ' + (Get-Text 'ui.lang_hint')) 'dim'
    Write-Footer -Page
}

function Show-HelpPage {
    <#
    .SYNOPSIS
        帮助页：面向非技术用户的操作顺序说明。
    #>
    Clear-Screen
    Write-Header
    Write-PageTitle 'help.title'
    foreach ($line in ((Get-Text 'help.body') -split "`n")) { Write-Out (' ' + $line) }
    Write-Rule
    Write-Out (' ' + $Script:LogFile) 'dim'
    Write-Footer -Page
}

function Show-Page {
    <#
    .SYNOPSIS
        按页面标识绘制对应页面。
    .PARAMETER Page
        页面标识（status / install / upgrade / manage / doctor / cleanup / launch / language）。
    #>
    param([string]$Page)

    switch ($Page) {
        'status' { Show-StatusPage }
        'install' { Show-InstallPage }
        'upgrade' { Show-UpgradePage }
        'manage' { Show-ManagePage }
        'doctor' { Show-DoctorPage }
        'cleanup' { Show-CleanupPage }
        'launch' { Show-LaunchPage }
        'language' { Show-LanguagePage }
        'help' { Show-HelpPage }
        default { Show-Menu 1 }
    }
}

function Set-Language {
    <#
    .SYNOPSIS
        切换界面语言并持久化到 .tui/lang（两平台共用）。
    .PARAMETER Target
        zh 或 en。
    #>
    param([string]$Target)

    $Script:UiLang = $Target
    $Script:Text = Import-TextTable $Target
    if (-not $DryRun) {
        try {
            $dir = Split-Path -Parent $Script:LangFile
            if (-not (Test-Path -LiteralPath $dir)) { [void](New-Item -ItemType Directory -Path $dir -Force) }
            [System.IO.File]::WriteAllText($Script:LangFile, $Target,
                (New-Object System.Text.UTF8Encoding($false)))
        } catch {
            Add-Log 'warn' ((Get-Text 'log.lang_save_failed') + ": " + $_.Exception.Message)
        }
    }
    Add-Log 'info' ((Get-Text 'menu.language') + ' -> ' + (Get-Text "lang.name.$Target"))
}

# ============================================================================
# 13. 页面动作与主循环
# ============================================================================

function Invoke-PageAction {
    <#
    .SYNOPSIS
        执行页面内的编号动作。
    .PARAMETER Page
        页面标识。
    .PARAMETER Key
        按键（数字字符）。
    #>
    param([string]$Page, [string]$Key)

    switch ($Page) {
        'status' {
            if ($Key -eq '1') { Invoke-Install }
            elseif ($Key -eq '2') { Invoke-Doctor }
            elseif ($Key -eq '3') { Invoke-Launch }
        }
        'install' {
            if ($Key -eq '1') { Invoke-Install }
            elseif ($Key -eq '2') { Invoke-Install -RepairOnly }
        }
        'upgrade' {
            if ($Key -eq '1') { Invoke-Upgrade }
        }
        'manage' {
            if ($Key -eq '1') { Invoke-Rebuild }
            elseif ($Key -eq '2') { Invoke-RefreshDeps }
            elseif ($Key -eq '3') { Invoke-CleanCache }
            elseif ($Key -eq '4') { Open-Folder 'config' }
            elseif ($Key -eq '5') { Open-Folder 'data' }
            elseif ($Key -eq '6') { Open-Folder 'logs' }
            elseif ($Key -eq '7') { Invoke-RecreateShortcut }
            elseif ($Key -eq '8') { Invoke-RemoveVenv }
        }
        'doctor' {
            if ($Key -eq '1') { Invoke-Doctor }
        }
        'cleanup' {
            if ($Key -eq '1') { Invoke-CleanTemp }
            elseif ($Key -eq '2') { Invoke-CleanCache }
            elseif ($Key -eq '3') { Invoke-Uninstall }
        }
        'launch' {
            if ($Key -eq '1') { Invoke-Launch }
        }
    }
}

function Invoke-Doctor {
    <#
    .SYNOPSIS
        执行体检并把结论写入日志（页面每帧重新渲染时会展示结果）。
    #>
    $checks = @(Get-DoctorChecks)
    $problems = @($checks | Where-Object { $_.tone -ne 'ok' })
    if ($problems.Count -eq 0) {
        Set-Status 'ok' (Get-Text 'doctor.all_ok')
        return
    }
    Set-Status 'warn' (Get-Text 'doctor.has_problems' @{ count = $problems.Count })
    foreach ($check in $problems) { Add-Log 'warn' (Get-CheckName $check.key) + ' -> ' + (Get-AdviceText $check) }
}

function Start-Page {
    <#
    .SYNOPSIS
        进入某个页面并处理按键，直到用户返回菜单。
    .PARAMETER Page
        页面标识。
    .OUTPUTS
        Boolean：True 表示用户按 q 退出整个向导。
    #>
    param([string]$Page)

    if ($Page -eq 'help') {
        Show-HelpPage
        # 走 Read-KeyRaw：支持 -Keys 队列注入，且在无控制台宿主上安全回退
        # （原直接调用 [Console]::ReadKey 会在输入重定向时抛 InvalidOperationException 使向导崩溃）
        [void](Read-KeyRaw)
        return $false
    }
    while ($true) {
        Show-Page $Page
        $key = Read-MenuKey
        if ($key -eq 'quit') { return $true }
        if ($key -eq 'escape' -or $key -eq 'enter' -or $key -eq 'no') { return $false }
        if ($key -eq 'refresh') { continue }
        if ($key -eq 'lang') { Set-Language $(if ($Script:UiLang -eq 'zh') { 'en' } else { 'zh' }); continue }
        if ($key -eq 'zh' -or $key -eq 'en') { Set-Language $key; continue }
        if ($Page -eq 'language' -and $key -match '^[12]$') {
            Set-Language $(if ($key -eq '1') { 'zh' } else { 'en' })
            return $false
        }
        Invoke-PageAction $Page $key
    }
}

function Start-Wizard {
    <#
    .SYNOPSIS
        向导主循环：菜单选择 → 页面 → 动作，界面始终保持可读。
    #>
    $items = Get-MenuItems
    $index = 1
    Add-Log 'info' (Get-Text 'app.title') + " $Script:TitleSep " + (Get-PlatformLabel)
    while ($true) {
        Show-Menu $index
        $key = Read-MenuKey
        if ($key -eq 'quit') { return }
        if ($key -eq 'up') { $index--; if ($index -lt 1) { $index = $items.Count }; continue }
        if ($key -eq 'down') { $index++; if ($index -gt $items.Count) { $index = 1 }; continue }
        if ($key -eq 'refresh') { continue }
        if ($key -eq 'lang') { Set-Language $(if ($Script:UiLang -eq 'zh') { 'en' } else { 'zh' }); continue }
        if ($key -eq 'zh' -or $key -eq 'en') { Set-Language $key; continue }
        if ($key -match '^[1-9]$') { $index = [int]$key }
        elseif ($key -ne 'enter') { continue }
        if (Start-Page $items[$index - 1].page) { return }
    }
}

# ============================================================================
# 14. 文本体检模式（-Check：不启动界面，便于排错与自动化）
# ============================================================================

function Invoke-TextCheck {
    <#
    .SYNOPSIS
        打印文本版体检报告。

    .NOTES
        报告必须用 Write-Host 输出：若用 Write-Output，调用方 `$code = Invoke-TextCheck`
        会把报告文本一并捕获进变量，用户什么都看不到（退出码也会被污染）。
    .OUTPUTS
        Int：0 全部通过；1 存在异常项。
    #>
    Write-Host ("== " + (Get-Text 'app.title') + " $Script:TitleSep " + (Get-Text 'doctor.title') + ' ==')
    Write-Host ("   " + $Script:ProjectRoot)
    $checks = @(Get-DoctorChecks)
    $failed = 0
    foreach ($check in $checks) {
        $mark = switch ($check.tone) { 'ok' { '[OK]' } 'warn' { '[!] ' } default { '[X] ' } }
        $line = "$mark " + (Get-CheckName $check.key)
        if ($check.detail -ne '') { $line += " -- $($check.detail)" }
        Write-Host $line
        $advice = Get-AdviceText $check
        if ($advice -ne '') { Write-Host ('     ' + (Get-Text 'doctor.advice' @{ advice = $advice })) }
        if ($check.tone -eq 'fail') { $failed++ }
    }
    $problems = @($checks | Where-Object { $_.tone -ne 'ok' })
    if ($failed -gt 0) {
        Write-Host ('=> ' + (Get-Text 'doctor.has_problems' @{ count = $problems.Count }))
        return 1
    }
    Write-Host ('=> ' + (Get-Text 'doctor.all_ok'))
    return 0
}

function Invoke-StateDump {
    <#
    .SYNOPSIS
        打印环境状态（key=value 单行形式，供排错与自动化测试解析）。
    .OUTPUTS
        Int：恒为 0。
    #>
    $state = Get-EnvState
    Write-Host "project_root=$Script:ProjectRoot"
    foreach ($name in @('uv_path', 'uv_version', 'venv_exists', 'python_exists', 'python_version',
            'framework_version', 'has_lock', 'has_requirements', 'git_available', 'git_branch',
            'git_commit', 'git_dirty', 'venv_bytes', 'platform')) {
        Write-Host "$name=$($state[$name])"
    }
    Write-Host ("missing_imports=" + ($state.missing_imports -join ','))
    Write-Host ("env_ready=" + (Test-EnvReady $state))
    foreach ($line in $Script:LogLines) { Write-Host "log=$line" }
    return 0
}

function Invoke-Action {
    <#
    .SYNOPSIS
        非交互执行单个动作（自动化与远程排错用，配合 -Yes）。
    .PARAMETER Name
        install / repair / upgrade / doctor / clean-temp / uninstall。
    .OUTPUTS
        Int：0 成功；1 失败（供脚本判断）。
    #>
    param([string]$Name)

    switch ($Name) {
        'doctor' {
            $exitCode = Invoke-TextCheck
            return $exitCode
        }
        'clean-temp' {
            Remove-WorkDir
            Add-Log 'info' (Get-Text 'cleanup.temp_done')
            return 0
        }
        'uninstall' {
            Invoke-Uninstall
            # dry-run 不真正删除，以「流程是否走完」判定结果，否则会因 .venv 仍在而误报失败
            if ($DryRun) { return 0 }
            return $(if (Test-Path -LiteralPath (Join-Path $Script:ProjectRoot '.venv')) { 1 } else { 0 })
        }
        'install' { Invoke-Install }
        'repair' { Invoke-Install -RepairOnly }
        'upgrade' { Invoke-Upgrade }
        default {
            Add-Log 'error' (Get-Text 'log.unknown_action' @{ name = $Name })
            return 2
        }
    }
    if (Test-EnvReady (Get-EnvState)) { return 0 }
    return 1
}

# ============================================================================
# 15. 入口
# ============================================================================

Initialize-Console
$Script:UiLang = Get-SystemLanguage
try {
    $Script:Text = Import-TextTable $Script:UiLang
} catch {
    Write-Host $_.Exception.Message
    exit 2
}
if ($State) {
    [void](Invoke-StateDump)
    exit 0
}
if ($Check) {
    $exitCode = Invoke-TextCheck
    exit $exitCode
}
if ($Preview -ne '') {
    # 渲染一次指定界面后退出（不读键盘）：供无终端环境验证渲染，也用于两平台一致性比对
    if ($Preview -eq 'menu') { Show-Menu 1 } else { Show-Page $Preview }
    exit 0
}
if ($Action -ne '') {
    # 非交互执行单个动作（自动化 / 远程排错用）：-Action install -Yes
    $Script:NonInteractive = $true
    $exitCode = Invoke-Action $Action
    exit $exitCode
}
if ($Keys -ne '') {
    # 脚本化按键驱动真实界面循环（无终端环境复现/回归测试）：-Keys "8,2,1,q"
    Set-KeyQueue $Keys
}
Start-Wizard
exit 0



