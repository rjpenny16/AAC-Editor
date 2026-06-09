@echo off
echo ====================================
echo TD Snap AI Assistant - FREE Edition
echo 100%% Free with Local AI!
echo ====================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not installed
    echo Install from: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Checking dependencies...
pip show pyautogui >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    pip install -r requirements_free.txt
    echo.
)

echo.
echo ====================================
echo RECOMMENDED: Install Ollama for FREE AI
echo.
echo 1. Visit: https://ollama.ai
echo 2. Download and install
echo 3. Run: ollama pull llama3
echo.
echo Then restart this application!
echo ====================================
echo.
pause

echo Starting FREE Edition...
python td_snap_ai_assistant_free.py

pause
