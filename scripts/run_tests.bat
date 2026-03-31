@echo off
setlocal enabledelayedexpansion

echo ========================================
echo InstructionX Test Runner
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.14+
    pause
    exit /b 1
)

REM Check dependencies
echo [1/5] Checking test dependencies...
pip show pytest >nul 2>&1
if errorlevel 1 (
    echo Installing test dependencies...
    pip install pytest pytest-qt pytest-mock pytest-cov
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies
        pause
        exit /b 1
    )
)
echo Dependencies OK
echo.

REM Run tests
echo [2/5] Running unit tests...
echo.
pytest tests\unit\ -v --tb=short
set UNIT_RESULT=!errorlevel!
echo.

echo [3/5] Running integration tests...
echo.
pytest tests\integration\ -v --tb=short
set INTEGRATION_RESULT=!errorlevel!
echo.

echo [4/5] Running GUI tests...
echo.
pytest tests\gui\ -v --tb=short
set GUI_RESULT=!errorlevel!
echo.

echo [5/5] Generating coverage report...
pytest --cov=core --cov=ui --cov=utils --cov-report=html --cov-report=term --tb=short
set COVERAGE_RESULT=!errorlevel!
echo.

echo ========================================
echo Test Results Summary
echo ========================================
if !UNIT_RESULT! equ 0 (
    echo [OK] Unit tests passed
) else (
    echo [FAIL] Unit tests failed
)

if !INTEGRATION_RESULT! equ 0 (
    echo [OK] Integration tests passed
) else (
    echo [FAIL] Integration tests failed
)

if !GUI_RESULT! equ 0 (
    echo [OK] GUI tests passed
) else (
    echo [FAIL] GUI tests failed
)

echo.
if !COVERAGE_RESULT! equ 0 (
    echo Coverage report generated: htmlcov\index.html
)
echo.

pause
