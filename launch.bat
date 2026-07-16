@echo off
cd /d "%~dp0"

echo Starting AAC Editor...
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

REM Replace an older copy still serving this port with the current checkout.
python -c "import json,time,urllib.request as u; b='http://127.0.0.1:8765'; c=json.load(u.urlopen(b+'/api/config',timeout=1)); u.urlopen(u.Request(b+'/api/quit',data=b'',headers={'X-TDSnap-Token':c['token']}),timeout=2).read(); time.sleep(1)" >nul 2>&1

echo.
echo Opening the app in your browser...
python -m tdsnap.web

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
