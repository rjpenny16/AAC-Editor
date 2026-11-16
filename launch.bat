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

REM Install the project and its Windows automation dependency if missing
python -c "import flask, uiautomation" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    python -m pip install .
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies
        echo.
        pause
        exit /b 1
    )
)

REM Suggestions need the AI extra (llama-cpp-python), which the installed app
REM bundles. Install a prebuilt copy if one exists for this Python; never
REM compile. If none installs, the suggestions panel says that AI is not
REM included when started this way, and everything else works as usual.
python -c "import llama_cpp" >nul 2>&1
if errorlevel 1 (
    echo Installing the suggestion engine (optional^)...
    python -m pip install ".[ai]" --only-binary llama-cpp-python --prefer-binary --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu >nul 2>&1
    python -c "import llama_cpp" >nul 2>&1
    if errorlevel 1 (
        echo Suggestions are not included when AAC Editor is started this way.
        echo Use the installed app for suggestions. Everything else works.
    )
)

REM If AAC Editor is already open (this checkout or the installed app), the
REM next line brings it to the front instead of starting a second copy. It is
REM never closed from here: closing it would lose unsaved work.

echo.
echo Opening the app in your browser...
python -m tdsnap.web

if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
