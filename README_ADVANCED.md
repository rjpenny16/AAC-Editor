# TD Snap AI Assistant - Advanced Edition

**An AI-powered desktop application that revolutionizes AAC vocabulary building with intelligent automation, smart suggestions, and comprehensive features.**

![Version](https://img.shields.io/badge/version-2.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.7+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

---

## 🌟 Overview

The TD Snap AI Assistant Advanced Edition is a comprehensive tool designed to help speech therapists, educators, parents, and AAC users quickly build and customize TD Snap vocabularies using the power of AI.

### What Makes It "Advanced"?

This edition includes **all Pro features** plus:

- 🔐 **Secure API Key Management** - Encrypted storage
- 💡 **AI-Powered Suggestions** - Smart vocabulary recommendations
- 📦 **Batch Operations** - Process multiple categories at once
- 👁️ **Visual Verification** - Screenshot-based coordinate verification
- 🪟 **Window Detection** - Auto-find and focus TD Snap
- 📖 **OCR Vocabulary Reading** - Analyze existing vocabulary
- 🔄 **Error Recovery** - Automatic retry on failures
- ↩️ **Undo/Redo System** - Track and revert changes
- 👤 **User Profiles** - Multiple user support
- ⌨️ **Keyboard Shortcuts** - Fast workflows

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Get API Key
Get your Anthropic API key at: https://console.anthropic.com/

### 3. Launch Application
```bash
# Windows
launch_advanced.bat

# Mac/Linux
./launch_advanced.sh
```

### 4. Configure
- Settings tab → Add API key → Save
- Setup Coordinates tab → Record 5 positions
- Command tab → Type "Add colors" → Process!

**See [QUICKSTART_ADVANCED.md](QUICKSTART_ADVANCED.md) for detailed setup.**

---

## 📋 Features

### Core Features (from Pro)

✅ **Natural Language Commands**
```
"Add restaurants category"
"Create animals with 15 items"
"Add emotions"
```

✅ **AI Content Generation**
- Generates contextually appropriate items
- Based on AAC best practices
- Customizable item counts

✅ **GUI Automation**
- Automated clicking and typing
- Works with any screen resolution
- Configurable delays and timing

✅ **Coordinate Recording**
- Visual tool to record button positions
- Save and reuse coordinates
- Verification system

### Advanced Features (New!)

#### 🔐 Secure API Key Management
- Industry-standard encryption (Fernet)
- Local storage only
- Never exposed in logs
- Easy setup in Settings tab

#### 💡 AI-Powered Suggestions
- Analyzes current vocabulary
- Recommends missing categories
- Context-aware suggestions
- Based on communication needs

#### 📦 Batch Operations
- Queue multiple commands
- Import from CSV
- Process automatically
- Track progress

**Example CSV:**
```csv
command
Add restaurants category
Add animals with 15 items
Create emotions category
```

#### 👁️ Visual Verification
- Screenshot-based verification
- Confirms coordinate accuracy
- Reduces automation errors
- Auto-verify option

#### 🪟 Window Detection
- Auto-finds TD Snap window
- Brings to front automatically
- Multi-monitor support
- One-click focus button

#### 📖 OCR Vocabulary Reading
- Reads current TD Snap vocabulary
- Identifies existing items
- Powers AI suggestions
- Helps avoid duplicates

**Requires:** Tesseract OCR

#### 🔄 Error Recovery & Retry
- Automatic retry on failures
- Graceful error handling
- Detailed error logging
- Configurable retry behavior

#### ↩️ Undo/Redo System
- Track up to 50 changes
- Undo with Ctrl+Z
- Redo with Ctrl+Y
- Change history in status bar

**Note:** For reference only - manual TD Snap changes needed

#### 👤 User Profiles
- Default, Child, Adult, Custom
- Different settings per profile
- Switch profiles easily
- Save preferences

#### ⌨️ Keyboard Shortcuts
- `Enter` - Process command
- `Ctrl+Z` - Undo
- `Ctrl+Y` - Redo
- `Ctrl+S` - Save coordinates
- `Esc` - Stop processing

---

## 📖 Usage

### Basic Workflow

1. **Enter Command**
   ```
   Type: "Add restaurants category"
   Press Enter or click "Process Command"
   ```

2. **AI Processing**
   ```
   AI analyzes → Generates items → Shows in log
   ```

3. **Automation**
   ```
   5-second countdown → Automated clicking → Done!
   ```

### Advanced Workflow

#### Using AI Suggestions

1. Go to **AI Suggestions** tab
2. Click **Generate Suggestions**
3. Review recommended categories
4. Apply suggestions

#### Batch Processing

1. Go to **Batch Operations** tab
2. Import CSV or add commands manually
3. Click **Process Queue**
4. Monitor progress in Activity Log

#### Window Management

1. Click **Focus TD Snap** to bring window forward
2. Or enable auto-focus in Settings
3. Works automatically before each automation

---

## 🛠️ Installation

### Prerequisites

- Python 3.7 or higher
- TD Snap application
- Internet connection (for AI features)
- Anthropic API key

### Required Python Packages

```bash
pip install -r requirements.txt
```

Installs:
- `pyautogui` - GUI automation
- `anthropic` - AI SDK
- `cryptography` - Secure storage
- `opencv-python` - Visual verification
- `pytesseract` - OCR
- `pygetwindow` - Window detection
- `pillow` - Image processing
- `requests` - HTTP client
- `keyboard` - Keyboard support

### Optional: Tesseract OCR

For vocabulary analysis and AI suggestions:

**Windows:**
1. Download: https://github.com/UB-Mannheim/tesseract/wiki
2. Install and add to PATH

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

---

## ⚙️ Configuration

### API Key Setup

1. Go to Settings tab
2. Enter your Anthropic API key
3. Click "Save API Key"
4. Click "Test Connection" to verify

**Get API key:** https://console.anthropic.com/

### Coordinate Setup

1. Open TD Snap in edit mode
2. Go to Setup Coordinates tab
3. Record each position:
   - Add Category Button
   - Add New Button/Word
   - Button Label Field
   - Category Name Field
   - Save Button
4. Click Verify to confirm

### Automation Settings

- **Delay between actions:** 0.5-5 seconds (default: 1.0)
- **Items per category:** 1-100 (default: 10)
- **Countdown:** 0-10 seconds (default: 5)
- **Typing speed:** 0.01-0.2 sec/char (default: 0.05)
- **Visual verification:** On/Off (default: On)
- **Error recovery:** On/Off (default: On)

---

## 📝 Examples

### Simple Commands

```
Add colors category
Add animals
Create restaurants category
Add emotions with 12 items
Add food
```

### With Custom Counts

```
Add sports with 20 items
Create weather with 8 items
Add clothing with 15 items
```

### Expected Output

```
[10:15:23] Processing command: Add colors category
[10:15:24] Understood: add_category - colors
[10:15:27] Generated 10 items
[10:15:27] Items: Red, Blue, Green, Yellow, Orange, Purple, Pink, Brown, Black, White
[10:15:27] Starting automation...
[10:15:32] Successfully processed category 'colors' with 10 items!
```

### Batch CSV Example

Create `my_categories.csv`:
```csv
command
Add restaurants category
Add animals with 15 items
Add colors
Add emotions with 12 items
Add family members
```

Then:
1. Batch Operations tab
2. Import from CSV
3. Process Queue

---

## 🎯 Use Cases

### For Speech Therapists
- Quickly set up vocabulary for new clients
- Customize vocabularies by communication needs
- Batch process multiple client devices
- Use AI suggestions for comprehensive coverage

### For Parents
- Build age-appropriate vocabulary
- Add child's interests and preferences
- Expand vocabulary as child grows
- Save time on device setup

### For Educators
- Create lesson-specific vocabularies
- Set up classroom communication boards
- Standardize across multiple devices
- Quick updates for changing needs

### For AAC Users
- Personalize device vocabulary
- Add new interests and activities
- Keep vocabulary current and relevant
- Efficient vocabulary expansion

---

## 🔍 Troubleshooting

### API Issues

**"API Key Required" Error**
- Configure API key in Settings tab
- Click "Save API Key"
- Verify key starts with `sk-ant-`

**"API test failed" Error**
- Check internet connection
- Verify API key is correct
- Check API credits at console.anthropic.com
- Review Activity Log for details

### Automation Issues

**Clicks in Wrong Place**
- Re-record coordinates
- Click "Verify" to check positions
- Ensure TD Snap window hasn't moved
- Check screen resolution unchanged

**Too Fast/Slow**
- Adjust "Delay between actions" in Settings
- Increase for slower systems
- Decrease for faster automation

**Items Not Added**
- Check TD Snap is in edit mode
- Verify coordinates are correct
- Enable visual verification
- Review Activity Log for errors

### Feature Issues

**OCR Not Working**
- Install Tesseract OCR
- Verify pytesseract installed: `pip install pytesseract`
- Check TD Snap text is visible
- Try increasing TD Snap font size

**Window Detection Failing**
- Ensure TD Snap is running
- Check window title is "TD Snap"
- Try manual "Focus TD Snap" button
- Verify pygetwindow installed (Windows)

**Batch Processing Stops**
- Check for errors in Activity Log
- Verify all coordinates set
- Enable error recovery in Settings
- Process smaller batches

---

## 🔐 Security & Privacy

### Data Storage

**Stored Locally:**
- Encrypted API key (`.config/` folder)
- Coordinates (`td_snap_coordinates.json`)
- Application settings
- Change history (memory only)

**Sent to Anthropic:**
- User commands (text)
- Category names
- Item count preferences

**Never Sent:**
- TD Snap data
- Screen coordinates
- Personal information
- Vocabulary content
- User data

### API Key Security

- Encrypted using Fernet (AES 128-bit)
- Stored locally only
- Never logged or transmitted except to Anthropic
- Can be deleted by removing `.config/` folder

### Best Practices

1. Keep API key confidential
2. Don't share configuration files
3. Regularly update dependencies
4. Review Activity Log for unexpected activity
5. Use profiles for multiple users

---

## 📊 Performance

### Typical Timings

- Command parsing: 2-3 seconds
- Item generation: 3-5 seconds
- Automation countdown: 5 seconds (configurable)
- Per-item addition: 1-2 seconds
- **Total for 10 items:** ~20-25 seconds

### Comparison

**Manual Entry:**
- ~20-30 seconds per word
- ~5 minutes for 10 words
- ~1 hour for 100 words

**With Assistant:**
- ~1-2 seconds per word
- ~25 seconds for 10 words
- ~5 minutes for 100 words

**Time Saved:** 90%+ for large vocabularies

---

## 🎓 Tips & Best Practices

### Getting Started
1. Start with small batches (5-10 items)
2. Verify coordinates work correctly
3. Test with simple categories (colors, animals)
4. Gradually increase complexity

### Optimization
1. Enable visual verification for reliability
2. Enable error recovery for stability
3. Adjust delays based on system speed
4. Use batch operations for efficiency

### Maintenance
1. Verify coordinates after TD Snap updates
2. Re-record if screen resolution changes
3. Check API key validity periodically
4. Update dependencies regularly

### Vocabulary Building
1. Use AI suggestions for comprehensive coverage
2. Organize by communication context
3. Prioritize high-frequency words
4. Customize to user needs and interests

---

## 🤝 Contributing

This project is designed to help the AAC community. Contributions welcome!

### Ways to Contribute
- Report bugs and issues
- Suggest new features
- Improve documentation
- Share usage tips
- Create templates

---

## 📄 License

MIT License - Free for personal and commercial use

---

## 🙏 Acknowledgments

Built with:
- **Python & Tkinter** - UI framework
- **Anthropic Claude** - AI capabilities
- **PyAutoGUI** - Automation
- **Cryptography** - Security
- **OpenCV** - Visual verification
- **Pytesseract** - OCR

Designed for:
- AAC users and families
- Speech-language pathologists
- Special education teachers
- AAC device administrators

---

## 📞 Support

### Documentation
- [QUICKSTART_ADVANCED.md](QUICKSTART_ADVANCED.md) - Quick setup guide
- [ADVANCED_FEATURES.md](ADVANCED_FEATURES.md) - Feature documentation
- [README.md](README.md) - Original documentation

### Getting Help
1. Check Activity Log for errors
2. Review documentation
3. Verify configuration
4. Check TD Snap compatibility

### Reporting Issues
Include:
- Activity Log output
- Steps to reproduce
- Error messages
- Python version
- Operating system
- TD Snap version

---

## 🗺️ Roadmap

### Planned Features
- 🎤 Voice command input
- 🖼️ Image/symbol selection
- ☁️ Cloud sync
- 🌍 Multi-language support
- 📚 Template library
- 📊 Advanced analytics
- 🔗 API for other AAC apps
- 📱 Mobile companion app

---

## 💖 Made for the AAC Community

This tool was created to make AAC vocabulary building faster, easier, and more accessible for everyone. Whether you're a therapist setting up devices for clients, a parent customizing your child's communication tool, or an AAC user expanding your vocabulary, we hope this makes your life easier.

**Communication is a fundamental human right. Let's make it easier together.** 🌟

---

**Version:** 2.0 Advanced Edition
**Last Updated:** 2024
**Author:** Built with ❤️ for AAC users everywhere
