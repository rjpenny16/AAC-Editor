"""
Build script to create single executable installer
Run this to create TDSnapInstaller.exe
"""

import subprocess
import sys
import os
from pathlib import Path

def install_pyinstaller():
    """Install PyInstaller if not present"""
    print("Installing PyInstaller...")
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller'],
                   check=True)
    print("✓ PyInstaller installed\n")

def build_exe():
    """Build the executable"""
    print("Building executable installer...")
    print("This may take a few minutes...\n")

    # PyInstaller command
    cmd = [
        'pyinstaller',
        '--onefile',  # Single file
        '--windowed',  # No console window
        '--name=TDSnapInstaller',  # Output name
        '--icon=NONE',  # Add icon file path here if you have one
        '--add-data=td_snap_ai_assistant_free.py;.',  # Include main app
        'td_snap_auto_installer.py'
    ]

    try:
        subprocess.run(cmd, check=True)
        print("\n" + "="*60)
        print("✓ BUILD SUCCESSFUL!")
        print("="*60)
        print("\nYour installer is ready:")
        print("  📁 dist/TDSnapInstaller.exe")
        print("\nDistribute this single file to users!")
        print("They just double-click and everything installs automatically!")
        print("\nFile size: ~50-80 MB (includes everything)")

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure all files are in the same directory")
        print("2. Try running: pip install --upgrade pyinstaller")
        print("3. Check that td_snap_ai_assistant_free.py exists")

def main():
    """Main build process"""
    print("="*60)
    print("TD Snap AI Assistant - Build Installer")
    print("="*60)
    print()

    # Check if files exist
    if not Path("td_snap_ai_assistant_free.py").exists():
        print("❌ Error: td_snap_ai_assistant_free.py not found!")
        print("Make sure you're running this from the project directory.")
        return

    if not Path("td_snap_auto_installer.py").exists():
        print("❌ Error: td_snap_auto_installer.py not found!")
        return

    # Install PyInstaller
    try:
        import PyInstaller
    except ImportError:
        install_pyinstaller()

    # Build
    build_exe()

if __name__ == "__main__":
    main()
