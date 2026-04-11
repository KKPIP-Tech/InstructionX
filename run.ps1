# InstructionX Launcher Script
# Uses uv to manage environment and dependencies

# Set console encoding to UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# Get script directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($ScriptDir)) {
    $ScriptDir = Get-Location
}
Set-Location $ScriptDir

# Clear VIRTUAL_ENV to avoid conflicts
Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  InstructionX Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Check if .venv exists
if (-not (Test-Path ".venv\Scripts\pip.exe")) {
    Write-Host "[Setup] Creating virtual environment..." -ForegroundColor Yellow
    uv venv
}
Write-Host ""

# Install dependencies from requirements.txt with uv
Write-Host "[1/3] Installing dependencies with uv..." -ForegroundColor Yellow
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
& uv pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
Write-Host "All dependencies installed successfully" -ForegroundColor Green
Write-Host ""

# Launch application
Write-Host "[2/3] Launching InstructionX..." -ForegroundColor Yellow
Write-Host "--------------------------------------------" -ForegroundColor DarkGray
& .venv\Scripts\python.exe main.py
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Host "--------------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "Application exited with code: $exitCode" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit $exitCode
}
