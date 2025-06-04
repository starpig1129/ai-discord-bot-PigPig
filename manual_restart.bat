@echo off
chcp 65001 >nul 2>&1
REM PigPig Discord Bot Manual Restart Script
REM Use this script when automatic restart fails

echo ========================================
echo PigPig Discord Bot Manual Restart Script
echo ========================================
echo.

REM Check current directory
echo Current Directory: %CD%
echo.

REM Check important files
echo Checking important files...
if exist "main.py" (
    echo [OK] main.py exists
) else (
    echo [ERROR] main.py not found!
    echo Please confirm you are in the correct Bot directory
    pause
    exit /b 1
)

if exist "bot.py" (
    echo [OK] bot.py exists
) else (
    echo [WARNING] bot.py not found!
)

if exist "settings.json" (
    echo [OK] settings.json exists
) else (
    echo [WARNING] settings.json not found!
    echo Please check if configuration file is correct
)
echo.

REM Check virtual environment
echo Checking Python environment...
set PYTHON_CMD=python

REM Try to find Python in virtual environment first
if exist "dcbot\Scripts\python.exe" (
    echo [OK] Found dcbot virtual environment
    set PYTHON_CMD="dcbot\Scripts\python.exe"
) else if exist "venv\Scripts\python.exe" (
    echo [OK] Found venv virtual environment
    set PYTHON_CMD="venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
    echo [OK] Found .venv virtual environment  
    set PYTHON_CMD=".venv\Scripts\python.exe"
) else if defined VIRTUAL_ENV (
    echo [OK] Detected virtual environment: %VIRTUAL_ENV%
    set PYTHON_CMD="%VIRTUAL_ENV%\Scripts\python.exe"
    if not exist %PYTHON_CMD% (
        echo [WARNING] Virtual environment Python not found, using system Python
        set PYTHON_CMD=python
    )
) else (
    echo [INFO] No virtual environment detected, using system Python
    REM Try python3 command as fallback
    python3 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set PYTHON_CMD=python3
    )
)

REM Test Python command
echo.
echo Testing Python command...
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] Python command available
    for /f "tokens=*" %%i in ('%PYTHON_CMD% --version 2^>^&1') do echo %%i
) else (
    echo [ERROR] Python command not available!
    echo Please check Python installation or environment variables
    echo.
    echo Trying alternative Python commands...
    
    REM Try py launcher
    py --version >nul 2>&1
    if %errorlevel% equ 0 (
        echo [OK] Found Python via py launcher
        set PYTHON_CMD=py
        py --version
    ) else (
        echo [ERROR] All Python commands failed!
        echo Please install Python or check your PATH environment variable
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo Ready to start PigPig Discord Bot
echo ========================================
echo Using Python: %PYTHON_CMD%
echo Start command: %PYTHON_CMD% main.py
echo.

REM Ask whether to continue
set /p continue="Continue to start Bot? (Y/n): "
if /i "%continue%"=="n" (
    echo Startup cancelled
    pause
    exit /b 0
)

echo.
echo Starting PigPig Discord Bot...
echo Press Ctrl+C to stop Bot
echo ========================================
echo.

REM Start Bot
%PYTHON_CMD% main.py

REM Handle Bot termination
set BOT_EXIT_CODE=%errorlevel%
echo.
echo ========================================
echo Bot has terminated
echo ========================================
echo Exit code: %BOT_EXIT_CODE%

if %BOT_EXIT_CODE% neq 0 (
    echo [WARNING] Bot terminated abnormally (Error code: %BOT_EXIT_CODE%)
    echo Please check error messages and confirm configuration is correct
) else (
    echo [OK] Bot terminated normally
)

echo.
echo Press any key to close window...
pause >nul