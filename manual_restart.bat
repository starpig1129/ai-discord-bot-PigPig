@echo off
REM PigPig Discord Bot 手動重啟腳本
REM 當自動重啟失敗時使用此腳本

echo ========================================
echo PigPig Discord Bot 手動重啟腳本
echo ========================================
echo.

REM 檢查當前目錄
echo 當前目錄: %CD%
echo.

REM 檢查重要文件
echo 檢查重要文件...
if exist "main.py" (
    echo [✓] main.py 存在
) else (
    echo [✗] main.py 不存在！
    echo 請確認您在正確的 Bot 目錄中
    pause
    exit /b 1
)

if exist "bot.py" (
    echo [✓] bot.py 存在
) else (
    echo [✗] bot.py 不存在！
)

if exist "settings.json" (
    echo [✓] settings.json 存在
) else (
    echo [✗] settings.json 不存在！
    echo 請確認配置文件是否正確
)
echo.

REM 檢查虛擬環境
echo 檢查 Python 環境...
if defined VIRTUAL_ENV (
    echo [✓] 檢測到虛擬環境: %VIRTUAL_ENV%
    set PYTHON_CMD="%VIRTUAL_ENV%\Scripts\python.exe"
    if exist %PYTHON_CMD% (
        echo [✓] 虛擬環境 Python 存在
    ) else (
        echo [✗] 虛擬環境 Python 不存在，使用系統 Python
        set PYTHON_CMD=python
    )
) else (
    echo [!] 未檢測到虛擬環境，使用系統 Python
    set PYTHON_CMD=python
)

REM 測試 Python 命令
echo.
echo 測試 Python 命令...
%PYTHON_CMD% --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [✓] Python 命令可用
    %PYTHON_CMD% --version
) else (
    echo [✗] Python 命令不可用！
    echo 請檢查 Python 安裝或環境變數設定
    pause
    exit /b 1
)

echo.
echo ========================================
echo 準備啟動 PigPig Discord Bot
echo ========================================
echo 使用的 Python: %PYTHON_CMD%
echo 啟動命令: %PYTHON_CMD% main.py
echo.

REM 詢問是否繼續
set /p continue="是否繼續啟動 Bot？(Y/n): "
if /i "%continue%"=="n" (
    echo 已取消啟動
    pause
    exit /b 0
)

echo.
echo 正在啟動 PigPig Discord Bot...
echo 按 Ctrl+C 停止 Bot
echo ========================================
echo.

REM 啟動 Bot
%PYTHON_CMD% main.py

REM Bot 結束後的處理
echo.
echo ========================================
echo Bot 已結束
echo ========================================
echo 退出代碼: %errorlevel%

if %errorlevel% neq 0 (
    echo [!] Bot 非正常結束（錯誤代碼: %errorlevel%）
    echo 請檢查錯誤訊息並確認配置是否正確
) else (
    echo [✓] Bot 正常結束
)

echo.
echo 按任意鍵關閉視窗...
pause >nul