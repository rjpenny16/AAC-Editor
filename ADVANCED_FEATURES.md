# TD Snap AI Assistant - Advanced Edition Features

## 🚀 What's New in the Advanced Edition

The Advanced Edition includes all features from the Pro version plus these powerful enhancements:

### 1. **Secure API Key Management** 🔐
- Encrypted storage of your Anthropic API key
- Easy setup in Settings tab
- Test connection button to verify API access
- Keys stored securely using industry-standard encryption

**How to Set Up:**
1. Go to Settings tab
2. Enter your Anthropic API key (get one at https://console.anthropic.com/)
3. Click "Save API Key"
4. Click "Test Connection" to verify

### 2. **AI-Powered Suggestions** 💡
- Analyzes your current TD Snap vocabulary
- Suggests missing categories and words
- Context-aware recommendations
- Based on AAC best practices

**How to Use:**
1. Go to "AI Suggestions" tab
2. Click "Analyze Current Vocabulary" (requires OCR setup)
3. Click "Generate Suggestions" for AI recommendations
4. Review suggestions and apply what's useful

### 3. **Batch Operations** 📦
- Process multiple categories at once
- Import from CSV files
- Queue management
- Automated batch processing

**How to Use:**
1. Go to "Batch Operations" tab
2. Add commands to queue manually or import CSV
3. Click "Process Queue" to automate all

**CSV Format:**
```csv
command
Add restaurants category
Add colors with 15 items
Create emotions category
```

### 4. **Visual Verification System** 👁️
- Screenshot-based button detection
- Verifies coordinates are correct
- Reduces automation errors
- Auto-verify after recording coordinates

**How to Use:**
- Enabled by default in Settings
- Click "Verify" button next to coordinates
- Green checkmark = verified, Red X = needs adjustment

### 5. **Window Detection & Auto-Focus** 🪟
- Automatically finds TD Snap window
- Brings TD Snap to front before automation
- Works across multiple monitors
- No manual window positioning needed

**How to Use:**
- Click "Focus TD Snap" button in Command tab
- Or enable auto-focus in Settings (automatic before automation)

### 6. **OCR Vocabulary Reading** 📖
- Reads current vocabulary from TD Snap
- Identifies existing words and categories
- Powers the AI suggestions feature
- Helps avoid duplicates

**Requirements:**
- Install Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- Install pytesseract: `pip install pytesseract`

### 7. **Error Recovery & Retry** 🔄
- Automatically retries failed operations
- Detects and handles errors gracefully
- Configurable retry behavior
- Comprehensive error logging

**How to Use:**
- Enable "Error recovery & retry" in Settings
- Automation will retry failed clicks automatically
- Check Activity Log for error details

### 8. **Undo/Redo System** ↩️
- Track all changes made
- Undo recent additions (up to 50 changes)
- Redo undone changes
- Change history visible in status bar

**How to Use:**
- Press Ctrl+Z to undo
- Press Ctrl+Y to redo
- Status bar shows available undo/redo actions

**Note:** Undo tracking is for reference only - you must manually remove items from TD Snap

### 9. **User Profiles** 👤
- Different settings for different users
- Switch between child/adult vocabularies
- Custom profile support
- Save preferences per profile

**Profiles:**
- **Default**: General purpose
- **Child**: Age-appropriate vocabulary
- **Adult**: Adult communication needs
- **Custom**: Your own configuration

### 10. **Keyboard Shortcuts** ⌨️
- Ctrl+Z: Undo last change
- Ctrl+Y: Redo change
- Ctrl+S: Save coordinates
- Esc: Stop current operation
- Enter: Process command (in command field)

## 🛠️ Technical Improvements

### Enhanced API Integration
- Now uses official Anthropic Python SDK
- Better error handling
- More reliable API calls
- Supports latest Claude models (Claude 3.5 Sonnet)

### Improved Automation
- Safe click with error detection
- Visual verification before clicks
- Retry logic for failed operations
- Better timing and delays

### Better Error Handling
- Comprehensive try/catch blocks
- Detailed error messages in log
- Graceful degradation if features unavailable
- User-friendly error dialogs

## 📋 Setup Requirements

### Required
- Python 3.7+
- All packages from requirements.txt
- Anthropic API key
- TD Snap application

### Optional (for full features)
- Tesseract OCR (for vocabulary analysis)
- pygetwindow (for window detection - Windows only)

## 🔧 Installation

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Install Tesseract OCR (Optional but Recommended)

**Windows:**
- Download installer: https://github.com/UB-Mannheim/tesseract/wiki
- Run installer
- Add to PATH

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

### 3. Get Anthropic API Key
1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Go to API Keys section
4. Create a new API key
5. Copy the key

### 4. Launch Advanced Edition
```bash
# Windows
launch_advanced.bat

# Mac/Linux
./launch_advanced.sh
```

## 📊 Feature Comparison

| Feature | Basic | Pro | Advanced |
|---------|-------|-----|----------|
| Natural language commands | ✅ | ✅ | ✅ |
| AI content generation | ✅ | ✅ | ✅ |
| Coordinate recording | ✅ | ✅ | ✅ |
| GUI automation | ✅ | ✅ | ✅ |
| Tabbed interface | ❌ | ✅ | ✅ |
| Settings persistence | ❌ | ✅ | ✅ |
| Secure API key storage | ❌ | ❌ | ✅ |
| AI suggestions | ❌ | ❌ | ✅ |
| Batch operations | ❌ | ❌ | ✅ |
| Visual verification | ❌ | ❌ | ✅ |
| Window detection | ❌ | ❌ | ✅ |
| OCR vocabulary reading | ❌ | ❌ | ✅ |
| Error recovery | ❌ | ❌ | ✅ |
| Undo/Redo | ❌ | ❌ | ✅ |
| User profiles | ❌ | ❌ | ✅ |
| Keyboard shortcuts | ❌ | ❌ | ✅ |

## 💡 Usage Tips

### Best Practices
1. **Always test with small batches first** - Try 5 items before doing 50
2. **Keep TD Snap visible** - Window detection works best when TD Snap is on screen
3. **Verify coordinates regularly** - Use the Verify button after recording
4. **Save your work** - TD Snap should be saved before large batch operations
5. **Monitor the Activity Log** - Check for errors or warnings during automation

### Performance Optimization
- Enable visual verification for reliability
- Enable error recovery for unstable systems
- Adjust delays if TD Snap is slow to respond
- Use batch operations for multiple categories

### Troubleshooting

**API calls failing?**
- Check your API key in Settings
- Click "Test Connection" to verify
- Check internet connection
- Verify API key hasn't been rate limited

**Coordinates not working?**
- Re-record coordinates
- Click "Verify" to check positions
- Make sure TD Snap window hasn't moved
- Check screen resolution hasn't changed

**OCR not working?**
- Install Tesseract OCR
- Make sure pytesseract is installed
- TD Snap text should be clearly visible
- Try increasing TD Snap font size

**Window detection failing?**
- Make sure TD Snap is running
- Try clicking "Focus TD Snap" manually
- Check TD Snap window title matches "TD Snap"
- Verify pygetwindow is installed (Windows)

## 🎯 Common Workflows

### Workflow 1: Quick Category Addition
1. Type command: "Add restaurants category"
2. Press Enter or click "Process Command"
3. Wait for AI to generate items
4. Watch automation complete

### Workflow 2: Batch Processing
1. Create CSV with multiple categories
2. Import CSV in Batch Operations tab
3. Review queue
4. Click "Process Queue"

### Workflow 3: Getting AI Suggestions
1. Go to AI Suggestions tab
2. Click "Generate Suggestions"
3. Review recommended categories
4. Manually add commands for desired categories

### Workflow 4: Setting Up New Device
1. Record coordinates once (Setup Coordinates tab)
2. Get AI suggestions for essential categories
3. Create batch queue of top categories
4. Process batch queue
5. Save TD Snap configuration

## 🔐 Security & Privacy

### What's Stored Locally
- Encrypted API key (`.config/` folder)
- Coordinates (JSON file)
- Application settings
- Change history (in memory only)

### What's Sent to Anthropic API
- Your commands (text only)
- Category names
- Item count preferences

### What's NEVER Sent
- Your TD Snap data
- Screen coordinates
- Personal information
- Vocabulary content

### API Key Security
- Encrypted using Fernet (symmetric encryption)
- Stored locally only
- Never transmitted except to Anthropic
- Can be deleted by removing `.config/` folder

## 🚀 Future Enhancements

Planned features for future versions:
- Voice command input
- Image/symbol selection
- Cloud sync of settings
- Multi-language support
- Custom AI prompt templates
- Template library
- Advanced vocabulary analytics
- Export/import configurations
- Integration with other AAC apps

## 📞 Support

### Getting Help
1. Check Activity Log for error messages
2. Review this documentation
3. Check QUICKSTART.md for common issues
4. Review README.md for basic troubleshooting

### Reporting Issues
When reporting issues, include:
- Activity Log output
- Steps to reproduce
- Error messages
- Python version
- Operating system

## 🎉 Acknowledgments

Built with:
- Python & Tkinter (UI)
- Anthropic Claude API (AI)
- PyAutoGUI (Automation)
- Cryptography (Security)
- OpenCV (Visual verification)
- Pytesseract (OCR)

Designed for the AAC community to make communication easier and more accessible.

---

**Made with ❤️ for AAC users, therapists, educators, and families**
