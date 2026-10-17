@echo off
REM SpinalCure Test Suite Runner for Windows
REM Convenient script for running different test configurations

if "%1"=="" (
    echo SpinalCure Test Suite
    echo ====================
    echo.
    echo Usage: run_tests.bat [command]
    echo.
    echo Commands:
    echo   all              - Run all tests
    echo   unit             - Run unit tests only (fast)
    echo   integration      - Run integration tests only
    echo   otp              - Run OTP security tests
    echo   security         - Run all security tests
    echo   coverage         - Run with coverage report
    echo   models           - Test models only
    echo   validators       - Test validators only
    echo   permissions      - Test permissions only
    echo   clean            - Clean test artifacts
    exit /b 1
)

setlocal enabledelayedexpansion

if "%1"=="all" (
    echo Running all tests...
    pytest tests/ -v --tb=short
    goto :end
)

if "%1"=="unit" (
    echo Running unit tests (fast)...
    pytest tests\unit\ -v --tb=short
    goto :end
)

if "%1"=="integration" (
    echo Running integration tests...
    pytest tests\integration\ -v --tb=short
    goto :end
)

if "%1"=="otp" (
    echo Running OTP security tests...
    pytest tests\unit\test_otp.py -v --tb=short -m otp
    goto :end
)

if "%1"=="security" (
    echo Running security tests...
    pytest tests\ -v --tb=short -m security
    goto :end
)

if "%1"=="coverage" (
    echo Running tests with coverage...
    pytest tests\ --cov=. --cov-report=html --cov-report=term-missing -v
    echo Coverage report generated in htmlcov/index.html
    goto :end
)

if "%1"=="models" (
    echo Testing models...
    pytest tests\unit\test_models.py -v --tb=short
    goto :end
)

if "%1"=="validators" (
    echo Testing validators...
    pytest tests\unit\test_validators.py -v --tb=short
    goto :end
)

if "%1"=="permissions" (
    echo Testing permissions...
    pytest tests\unit\test_permissions.py -v --tb=short
    goto :end
)

if "%1"=="clean" (
    echo Cleaning test artifacts...
    if exist ".pytest_cache" rmdir /s /q .pytest_cache
    if exist "htmlcov" rmdir /s /q htmlcov
    if exist ".coverage" del .coverage
    for /r . %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
    echo Cleaned!
    goto :end
)

echo Unknown command: %1
exit /b 1

:end
endlocal
