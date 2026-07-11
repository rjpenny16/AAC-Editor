@echo off
echo Starting TD Snap Page Builder...
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python from https://www.python.org/downloads/
    echo and tick "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

REM Install dependencies if missing
python -c "import flask, requests" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Opening the app in your browser...
python -m tdsnap.web

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
