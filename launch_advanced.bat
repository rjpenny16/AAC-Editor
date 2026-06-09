@echo off
echo ====================================
echo TD Snap AI Assistant - Advanced Edition
echo ====================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.7 or higher from https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Checking dependencies...
echo.

REM Check if requirements are installed
pip show anthropic >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing required dependencies...
    pip install -r requirements.txt
    echo.
)

echo Starting TD Snap AI Assistant Advanced Edition...
echo.
python td_snap_ai_assistant_advanced.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: Application failed to start
    echo Please check the error messages above
    pause
    exit /b 1
)

pause
