#Requires -Version 5.1
<#
.SYNOPSIS
    在 Windows 本机构建并打包 InstructionX Setup 的 x64 / ARM64 版本。
.DESCRIPTION
    x64 使用 MSVC；ARM64 使用 LLVM-MinGW 交叉编译。工具链仅写入项目 temp/，
    进程退出后不会留下系统 PATH 修改。发布资产写入 tools/setup/。
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup/build_windows.ps1
.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup/build_windows.ps1 -Architecture aarch64
#>
[CmdletBinding()]
param(
    [ValidateSet('all', 'x86_64', 'aarch64')][string]$Architecture = 'all',
    [string]$CargoPath = '',
    [string]$LlvmMingwPath = '',
    [string]$TargetRoot = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$SetupRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $SetupRoot
$Manifest = Join-Path $SetupRoot 'Cargo.toml'
$OutputDirectory = Join-Path $ProjectRoot 'tools\setup'
$Script:LlvmRelease = '20261104'
$Script:LlvmPackages = @{
    X64 = @{ Suffix = 'ucrt-x86_64'; Hash = '552191b5754c49a5a20723276a6fc56541ea1922c4c50b7b669022333fc1b40f' }
    Arm64 = @{ Suffix = 'ucrt-aarch64'; Hash = '7d7f8387a8706639b0b47a629d6e23f8b3ef9acce67e9832b8cd4c5bb2816eab' }
}
$Script:BuildTargets = @{
    x86_64 = @{ Target = 'x86_64-pc-windows-msvc'; Asset = 'instructionx-setup-windows-x86_64.exe'; Machine = 0x8664 }
    aarch64 = @{ Target = 'aarch64-pc-windows-gnullvm'; Asset = 'instructionx-setup-windows-aarch64.exe'; Machine = 0xaa64 }
}
$Script:PeOffsetPointer = 0x3c
$Script:PeMachineOffset = 4
$Script:PeSignature = 0x4550

function Resolve-Cargo {
    param([string]$Requested)
    if ($Requested) {
        if (-not (Test-Path -LiteralPath $Requested -PathType Leaf)) {
            throw "Cargo 不存在: $Requested"
        }
        return (Resolve-Path -LiteralPath $Requested).Path
    }
    $command = Get-Command cargo -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $localCargo = Join-Path $ProjectRoot 'temp\cargo\bin\cargo.exe'
    if (Test-Path -LiteralPath $localCargo) {
        if (-not $env:CARGO_HOME) { $env:CARGO_HOME = Join-Path $ProjectRoot 'temp\cargo' }
        if (-not $env:RUSTUP_HOME) { $env:RUSTUP_HOME = Join-Path $ProjectRoot 'temp\rustup' }
        return $localCargo
    }
    throw '未找到 Cargo。请先安装 Rust，或使用 -CargoPath 指定 cargo.exe。'
}

function Install-RustTarget {
    param([string]$Target)
    $command = Get-Command rustup -ErrorAction SilentlyContinue
    $rustup = if ($command) { $command.Source } else { Join-Path $ProjectRoot 'temp\cargo\bin\rustup.exe' }
    if (-not (Test-Path -LiteralPath $rustup)) { return }
    & $rustup target add $Target | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "无法安装 Rust 目标: $Target" }
}

function Resolve-LlvmMingw {
    param([string]$Requested)
    if ($Requested) { return (Resolve-Path -LiteralPath $Requested).Path }
    $hostArchitecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    $package = $Script:LlvmPackages[$hostArchitecture]
    if ($null -eq $package) { throw "不支持在该 Windows 架构上获取 LLVM-MinGW: $hostArchitecture" }
    $directoryName = "llvm-mingw-$Script:LlvmRelease-$($package.Suffix)"
    $toolRoot = Join-Path $ProjectRoot "temp\llvm-mingw\$directoryName"
    $compiler = Join-Path $toolRoot 'bin\aarch64-w64-mingw32-clang.exe'
    if (Test-Path -LiteralPath $compiler) { return $toolRoot }
    $archive = Join-Path $ProjectRoot "temp\$directoryName.zip"
    $url = "https://github.com/mstorsjo/llvm-mingw/releases/download/$Script:LlvmRelease/$directoryName.zip"
    Write-Host "下载开发者交叉编译工具链: $url"
    Invoke-WebRequest -Uri $url -OutFile $archive -UseBasicParsing
    $actual = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -ne $package.Hash) { throw 'LLVM-MinGW 的 SHA256 校验失败，已停止构建。' }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $ProjectRoot 'temp\llvm-mingw') -Force
    if (-not (Test-Path -LiteralPath $compiler)) { throw 'LLVM-MinGW 解压后缺少 ARM64 编译器。' }
    return $toolRoot
}

function Set-Arm64BuildEnvironment {
    param([string]$ToolRoot)
    $bin = Join-Path $ToolRoot 'bin'
    $compiler = Join-Path $bin 'aarch64-w64-mingw32-clang.exe'
    $archiver = Join-Path $bin 'llvm-ar.exe'
    if (-not (Test-Path -LiteralPath $compiler)) { throw "ARM64 编译器不存在: $compiler" }
    if (-not (Test-Path -LiteralPath $archiver)) { throw "LLVM 归档工具不存在: $archiver" }
    $env:CARGO_TARGET_AARCH64_PC_WINDOWS_GNULLVM_LINKER = $compiler
    $env:CC_aarch64_pc_windows_gnullvm = $compiler
    $env:AR_aarch64_pc_windows_gnullvm = $archiver
    $env:PATH = "$bin;$env:PATH"
}

function Assert-PeArchitecture {
    param([string]$Path, [int]$ExpectedMachine)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    $offset = [int][System.BitConverter]::ToUInt32($bytes, $Script:PeOffsetPointer)
    $signature = [System.BitConverter]::ToUInt16($bytes, $offset)
    $machine = [System.BitConverter]::ToUInt16($bytes, $offset + $Script:PeMachineOffset)
    if ($signature -ne $Script:PeSignature -or $machine -ne $ExpectedMachine) {
        throw ('PE 架构校验失败: {0}，实际机器码 0x{1:X4}' -f $Path, $machine)
    }
}

function Invoke-WindowsBuild {
    param([string]$Cargo, [string]$Name)
    $configuration = $Script:BuildTargets[$Name]
    $target = $configuration.Target
    Write-Host "构建 Windows $Name ($target)..."
    & $Cargo build --manifest-path $Manifest --locked --release --target $target | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Cargo 构建失败: $target" }
    $source = Join-Path $TargetRoot "$target\release\instructionx-setup.exe"
    $destination = Join-Path $OutputDirectory $configuration.Asset
    Copy-Item -LiteralPath $source -Destination $destination -Force
    Assert-PeArchitecture -Path $destination -ExpectedMachine $configuration.Machine
    if ($Name -eq 'x86_64') {
        & $destination --version | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'x64 构建产物的版本检查失败。' }
    }
    Write-Host "已生成并校验: $destination"
}

function Write-SetupChecksums {
    $lines = @()
    foreach ($name in @('x86_64', 'aarch64')) {
        $asset = Join-Path $OutputDirectory $Script:BuildTargets[$name].Asset
        if (Test-Path -LiteralPath $asset) {
            $hash = (Get-FileHash -LiteralPath $asset -Algorithm SHA256).Hash.ToLowerInvariant()
            $lines += "$hash  $($Script:BuildTargets[$name].Asset)"
        }
    }
    $path = Join-Path $OutputDirectory 'SHA256SUMS'
    $content = ($lines -join "`n") + "`n"
    [System.IO.File]::WriteAllText($path, $content, [System.Text.Encoding]::ASCII)
}

if ($env:OS -ne 'Windows_NT') { throw '此构建脚本仅支持 Windows 开发者主机。' }
if (-not $TargetRoot) { $TargetRoot = Join-Path $ProjectRoot 'temp\setup-build' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $TargetRoot -Force | Out-Null
$env:CARGO_TARGET_DIR = $TargetRoot
$cargo = Resolve-Cargo -Requested $CargoPath
$names = if ($Architecture -eq 'all') { @('x86_64', 'aarch64') } else { @($Architecture) }
foreach ($name in $names) { Install-RustTarget -Target $Script:BuildTargets[$name].Target }
if ($names -contains 'aarch64') {
    $llvm = Resolve-LlvmMingw -Requested $LlvmMingwPath
    Set-Arm64BuildEnvironment -ToolRoot $llvm
}
foreach ($name in $names) { Invoke-WindowsBuild -Cargo $cargo -Name $name }
Write-SetupChecksums
Write-Host 'Windows Setup 构建与校验已完成。'
