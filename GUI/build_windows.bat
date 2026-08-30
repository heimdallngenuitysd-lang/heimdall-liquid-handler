@echo off
setlocal
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
    echo Python was not found.
    echo Install Python 3.12 from python.org and check "Add python.exe to PATH".
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment in GUI\.venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the virtual environment.
        pause
        exit /b 1
    )
)

echo Installing packages into .venv ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :install_failed

echo Building LiquidHandler.exe ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm LiquidHandler.spec
if errorlevel 1 (
    echo PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo Done. Double-click:
echo   dist\LiquidHandler\LiquidHandler.exe
echo.
echo Packages live only in GUI\.venv and will not change your other Python installs.
pause
exit /b 0

:install_failed
echo Package install failed.
pause
exit /b 1
