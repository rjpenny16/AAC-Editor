# Installation Guide - TD Snap AI Assistant Advanced Edition

## 📋 System Requirements

### Minimum Requirements
- **Operating System:** Windows 10/11, macOS 10.14+, or Linux
- **Python:** 3.7 or higher
- **RAM:** 4GB minimum, 8GB recommended
- **Disk Space:** 500MB free space
- **Internet:** Required for AI features
- **TD Snap:** Latest version recommended

### Additional Requirements
- **Anthropic API Key** (required for AI features)
- **Tesseract OCR** (optional, for vocabulary analysis)

---

## 🪟 Windows Installation

### Step 1: Install Python

1. Download Python from https://www.python.org/downloads/
2. Run installer
3. ✅ **IMPORTANT:** Check "Add Python to PATH"
4. Click "Install Now"
5. Wait for installation to complete

**Verify Installation:**
```cmd
python --version
```
Should show: `Python 3.x.x`

### Step 2: Download Project

Option A - Git Clone:
```cmd
git clone https://github.com/yourusername/aac-editor.git
cd aac-editor
```

Option B - Download ZIP:
1. Download ZIP file
2. Extract to `C:\AAC-Editor`
3. Open Command Prompt in that folder

### Step 3: Install Python Dependencies

```cmd
pip install -r requirements.txt
```

This will install:
- pyautogui==0.9.54
- pillow==10.3.0
- requests==2.31.0
- keyboard==0.13.5
- pygetwindow==0.0.9
- pytesseract==0.3.10
- opencv-python==4.9.0.80
- cryptography==42.0.5
- anthropic==0.25.1

**Wait for all packages to install** (~2-5 minutes depending on internet speed)

### Step 4: Install Tesseract OCR (Optional but Recommended)

1. Download installer: https://github.com/UB-Mannheim/tesseract/wiki
2. Run `tesseract-ocr-w64-setup-v5.x.x.exe`
3. Install to default location: `C:\Program Files\Tesseract-OCR`
4. Add to PATH:
   - Open System Properties → Environment Variables
   - Edit "Path" under System variables
   - Add: `C:\Program Files\Tesseract-OCR`
   - Click OK

**Verify Installation:**
```cmd
tesseract --version
```

### Step 5: Get API Key

1. Visit https://console.anthropic.com/
2. Sign up or log in
3. Go to "API Keys"
4. Click "Create Key"
5. Copy the key (starts with `sk-ant-`)
6. Save it securely (you'll need it later)

### Step 6: Launch Application

**Double-click:** `launch_advanced.bat`

Or from command prompt:
```cmd
python td_snap_ai_assistant_advanced.py
```

### Step 7: Configure Application

1. **Settings Tab:**
   - Paste your API key
   - Click "Save API Key"
   - Click "Test Connection"

2. **Setup Coordinates Tab:**
   - Open TD Snap in edit mode
   - Record all 5 coordinates

3. **Command Tab:**
   - Try: "Add colors category"
   - Click "Process Command"

✅ **You're all set!**

---

## 🍎 macOS Installation

### Step 1: Install Python

macOS usually comes with Python, but it might be outdated.

**Check current version:**
```bash
python3 --version
```

**If needed, install via Homebrew:**
```bash
# Install Homebrew (if not installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python3
```

### Step 2: Download Project

```bash
git clone https://github.com/yourusername/aac-editor.git
cd aac-editor
```

Or download and extract ZIP file.

### Step 3: Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

**If you get permission errors:**
```bash
pip3 install --user -r requirements.txt
```

### Step 4: Install Tesseract OCR (Optional)

```bash
brew install tesseract
```

**Verify:**
```bash
tesseract --version
```

### Step 5: Get API Key

Same as Windows (see Windows Step 5)

### Step 6: Launch Application

```bash
chmod +x launch_advanced.sh
./launch_advanced.sh
```

Or:
```bash
python3 td_snap_ai_assistant_advanced.py
```

### Step 7: Configure Application

Same as Windows (see Windows Step 7)

---

## 🐧 Linux Installation

### Step 1: Install Python

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3 python3-pip python3-tk
```

**Fedora:**
```bash
sudo dnf install python3 python3-pip python3-tkinter
```

**Arch:**
```bash
sudo pacman -S python python-pip tk
```

**Verify:**
```bash
python3 --version
```

### Step 2: Download Project

```bash
git clone https://github.com/yourusername/aac-editor.git
cd aac-editor
```

### Step 3: Install Python Dependencies

```bash
pip3 install -r requirements.txt
```

**If you need user install:**
```bash
pip3 install --user -r requirements.txt
```

### Step 4: Install Tesseract OCR (Optional)

**Ubuntu/Debian:**
```bash
sudo apt install tesseract-ocr
```

**Fedora:**
```bash
sudo dnf install tesseract
```

**Arch:**
```bash
sudo pacman -S tesseract
```

**Verify:**
```bash
tesseract --version
```

### Step 5: Install Additional Dependencies

For GUI automation:
```bash
# Ubuntu/Debian
sudo apt install scrot python3-tk python3-dev

# For X11 systems
sudo apt install xdotool
```

### Step 6: Get API Key

Same as Windows (see Windows Step 5)

### Step 7: Launch Application

```bash
chmod +x launch_advanced.sh
./launch_advanced.sh
```

Or:
```bash
python3 td_snap_ai_assistant_advanced.py
```

### Step 8: Configure Application

Same as Windows (see Windows Step 7)

---

## 🔧 Troubleshooting Installation

### Python Not Found

**Windows:**
- Reinstall Python with "Add to PATH" checked
- Or manually add to PATH: `C:\Users\YourName\AppData\Local\Programs\Python\Python3x`

**macOS/Linux:**
- Try `python3` instead of `python`
- Install via package manager

### pip Not Found

```bash
# Windows
python -m ensurepip --upgrade

# macOS/Linux
python3 -m ensurepip --upgrade
```

### Package Installation Fails

**Error: "No module named pip"**
```bash
python -m ensurepip --default-pip
```

**Error: "Permission denied"**
```bash
pip install --user -r requirements.txt
```

**Error: "SSL Certificate error"**
```bash
pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -r requirements.txt
```

### Tkinter Not Found

**Ubuntu/Debian:**
```bash
sudo apt install python3-tk
```

**macOS:**
- Reinstall Python from python.org (includes Tkinter)

**Windows:**
- Reinstall Python (Tkinter included by default)

### PyAutoGUI Issues

**Linux - "Failed to find xdisplay":**
```bash
sudo apt install xdotool
export DISPLAY=:0
```

**macOS - "Accessibility permissions":**
1. System Preferences → Security & Privacy
2. Privacy → Accessibility
3. Add Terminal or Python

### Tesseract Not Found

**Error: "pytesseract.TesseractNotFoundError"**

**Windows:**
- Add Tesseract to PATH
- Or set path in code: `pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'`

**macOS/Linux:**
- Install via package manager: `brew install tesseract` or `apt install tesseract-ocr`

### Import Errors

**Error: "No module named 'cv2'"**
```bash
pip install opencv-python
```

**Error: "No module named 'anthropic'"**
```bash
pip install anthropic
```

**Error: "No module named 'cryptography'"**
```bash
pip install cryptography
```

### TD Snap Not Found

Make sure:
- TD Snap is installed and running
- Window title is exactly "TD Snap"
- Try manual window positioning

---

## ✅ Verification Checklist

After installation, verify:

- [ ] Python 3.7+ installed (`python --version`)
- [ ] All pip packages installed (`pip list | grep anthropic`)
- [ ] Tesseract installed (optional) (`tesseract --version`)
- [ ] Application launches without errors
- [ ] Settings tab accessible
- [ ] API key can be saved
- [ ] Coordinates can be recorded
- [ ] Activity log shows messages

---

## 🆘 Getting Additional Help

### Check Installation
```bash
# Verify Python
python --version

# Verify packages
pip list

# Test imports
python -c "import anthropic; print('OK')"
python -c "import cv2; print('OK')"
python -c "import pyautogui; print('OK')"
```

### Collect System Info
```bash
# Windows
systeminfo

# macOS/Linux
uname -a
python3 --version
pip3 --version
```

### Log Files

Check Activity Log in application for errors.

---

## 🎓 Next Steps

After successful installation:

1. ✅ Read [QUICKSTART_ADVANCED.md](QUICKSTART_ADVANCED.md)
2. ✅ Configure API key
3. ✅ Record coordinates
4. ✅ Try first command
5. ✅ Explore features

---

## 📦 Offline Installation

If you need to install on a machine without internet:

### 1. Download Dependencies on Internet-Connected Machine

```bash
pip download -r requirements.txt -d packages/
```

### 2. Transfer Files

Copy entire project folder including `packages/` to offline machine.

### 3. Install on Offline Machine

```bash
pip install --no-index --find-links=packages/ -r requirements.txt
```

---

## 🔄 Updating

### Update Python Packages

```bash
pip install --upgrade -r requirements.txt
```

### Update Application

```bash
git pull origin main
```

Or download new version and replace files.

### Preserve Settings

Your settings are saved in:
- `.config/` folder (API key)
- `td_snap_coordinates.json` (coordinates)

Keep these when updating!

---

## 🗑️ Uninstallation

### Remove Application

Simply delete the project folder.

### Remove Python Packages (Optional)

```bash
pip uninstall -r requirements.txt -y
```

### Remove Configuration

Delete:
- `.config/` folder
- `td_snap_coordinates.json`

---

**Installation complete!** 🎉

See [QUICKSTART_ADVANCED.md](QUICKSTART_ADVANCED.md) to start using the application.
