@echo off
echo ============================================
echo Building TD Snap Installer EXE
echo ============================================
echo.

echo Step 1: Installing PyInstaller...
pip install pyinstaller
echo.

echo Step 2: Building executable...
echo This will take 2-5 minutes...
echo.

python build_installer.py

echo.
echo ============================================
echo BUILD COMPLETE!
echo ============================================
echo.
echo Your installer is ready:
echo   dist\TDSnapInstaller.exe
echo.
echo This single file contains everything!
echo Users just double-click to install.
echo.
pause
