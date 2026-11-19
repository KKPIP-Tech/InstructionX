#Requires -Version 5.1
# InstructionX native Setup launcher. No TUI is implemented in this file.
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
$AssetName = switch ($Architecture) {
    'X64' { 'instructionx-setup-windows-x86_64.exe' }
    'Arm64' { 'instructionx-setup-windows-aarch64.exe' }
    default { throw "Unsupported Windows architecture: $Architecture" }
}
$Native = Join-Path $ProjectRoot "tools\setup\$AssetName"
if (-not (Test-Path -LiteralPath $Native -PathType Leaf)) {
    throw "Bundled native Setup is missing: tools/setup/$AssetName. Restore the original Release archive."
}
$env:INSTRUCTIONX_PROJECT_ROOT = $ProjectRoot
& $Native @args
exit $LASTEXITCODE
