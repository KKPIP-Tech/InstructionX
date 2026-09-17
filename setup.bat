@echo off
rem ===========================================================================
rem InstructionX setup wizard - Windows double-click entry point
rem
rem This file only locates PowerShell and runs setup.ps1 with a bypass policy:
rem the real UI and logic live in setup.ps1 (native TUI, no Python required).
rem The macOS counterpart is setup.command (calls setup.sh, identical UI).
rem
rem NOTE FOR MAINTAINERS: keep this file ASCII-only with CRLF line endings.
rem cmd.exe misparses LF-only batch files (it loses the first characters of a
rem line) and does not strip a UTF-8 BOM.
rem ===========================================================================
setlocal
chcp 65001 >nul 2>&1
cd /d "%~dp0"

set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS%" set "PS=powershell.exe"

"%PS%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
    echo.
    echo [X] Wizard exit code: %CODE%
    echo     See logs\tui_setup.log for details.
    pause
)
endlocal & exit /b %CODE%
