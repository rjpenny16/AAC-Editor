# 🚀 QUICK START - Advanced Edition

## Get Up and Running in 10 Minutes!

### Step 1: Install Dependencies (3 minutes)

#### Install Python Packages
```bash
pip install -r requirements.txt
```

This installs:
- ✅ pyautogui (automation)
- ✅ anthropic (AI SDK)
- ✅ cryptography (secure storage)
- ✅ opencv-python (visual verification)
- ✅ pytesseract (OCR)
- ✅ pygetwindow (window detection)
- ✅ And more...

#### Optional: Install Tesseract OCR
For vocabulary analysis and suggestions:

**Windows:**
1. Download: https://github.com/UB-Mannheim/tesseract/wiki
2. Run installer
3. Add to PATH

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt-get install tesseract-ocr
```

### Step 2: Get Your API Key (2 minutes)

1. Go to https://console.anthropic.com/
2. Sign up or log in
3. Navigate to "API Keys"
4. Click "Create Key"
5. Copy your API key (starts with `sk-ant-...`)

**Keep this key secure!** You'll need it in Step 4.

### Step 3: Launch the Application (10 seconds)

**Windows:**
```bash
launch_advanced.bat
```

**Mac/Linux:**
```bash
chmod +x launch_advanced.sh
./launch_advanced.sh
```

Or run directly:
```bash
python td_snap_ai_assistant_advanced.py
```

### Step 4: Configure API Key (1 minute)

1. Go to **Settings** tab
2. Paste your API key in the "Anthropic API Key" field
3. Click **Save API Key**
4. Click **Test Connection** to verify

✅ You should see "API test successful!"

### Step 5: Setup Coordinates (3 minutes)

1. Open **TD Snap** and enter edit mode
2. Go to **Setup Coordinates** tab
3. For each button:
   - Click **Record**
   - Move mouse over the target in TD Snap within 3 seconds
   - Position is recorded automatically
4. Click **Verify** to confirm each position

**Required coordinates:**
- Add Category Button
- Add New Button/Word
- Button Label Field
- Category Name Field
- Save Button

### Step 6: Your First Command! (1 minute)

1. Go back to **Command** tab
2. Type: `Add colors category`
3. Click **Process Command**
4. Watch the magic happen! ✨

The AI will:
1. ✅ Understand your command
2. ✅ Generate 10 color words
3. ✅ Automatically add them to TD Snap

## 🎯 What to Try Next

### Try AI Suggestions
1. Go to **AI Suggestions** tab
2. Click **Generate Suggestions**
3. Review AI-recommended categories
4. Use suggestions to add to your vocabulary

### Try Batch Operations
1. Go to **Batch Operations** tab
2. Add multiple commands:
   - "Add animals category"
   - "Add food category"
   - "Add emotions category"
3. Click **Process Queue**
4. Sit back and watch!

### Test Window Detection
1. Move TD Snap window around
2. Click **Focus TD Snap** in Command tab
3. Window automatically comes to front!

## 💡 Quick Examples

### Simple Commands
```
Add restaurants category
Create colors with 15 items
Add emotions
Make a food category
Add family members
```

### Custom Counts
```
Add animals with 20 items
Create weather with 8 items
Add sports with 25 items
```

## ⚡ Pro Tips

### 🔧 For Best Results
1. **Verify coordinates** after recording (click Verify button)
2. **Enable visual verification** in Settings (on by default)
3. **Enable error recovery** in Settings (on by default)
4. **Keep TD Snap visible** during automation
5. **Save TD Snap** before large batches

### ⌨️ Keyboard Shortcuts
- `Enter` in command field → Process command
- `Ctrl+Z` → Undo last change
- `Ctrl+Y` → Redo change
- `Ctrl+S` → Save coordinates
- `Esc` → Stop current operation

### 🎯 Start Small, Scale Up
1. First try: "Add colors" (10 items)
2. Then try: "Add animals with 15 items"
3. Then try: Batch of 5 categories
4. Finally: Large vocabulary buildout

## ❓ Common First-Time Issues

### "API Key Required" Error
→ Go to Settings tab and configure your API key
→ Make sure you clicked "Save API Key"

### "Setup Required" Error
→ Go to Setup Coordinates tab
→ Record all 5 coordinate positions

### "API test failed" Error
→ Check your internet connection
→ Verify API key is correct (starts with sk-ant-)
→ Check you have API credits at console.anthropic.com

### Clicks in Wrong Place
→ Re-record coordinates
→ Make sure TD Snap window is in same position
→ Click "Verify" to check coordinates
→ Enable visual verification in Settings

### Automation Too Fast/Slow
→ Go to Settings tab
→ Adjust "Delay between actions"
→ Increase for slower, decrease for faster

### OCR Not Working
→ Install Tesseract OCR (see Step 1)
→ Make sure pytesseract is installed
→ Try `pip install pytesseract`

## 🎓 Learning Path

### Day 1: Get Familiar
- ✅ Install and configure
- ✅ Record coordinates
- ✅ Try 3-5 simple commands
- ✅ Review Activity Log

### Day 2: Explore Features
- ✅ Try AI Suggestions
- ✅ Use Batch Operations
- ✅ Test window detection
- ✅ Experiment with settings

### Week 1: Build Vocabulary
- ✅ Plan vocabulary needs
- ✅ Create batch queue
- ✅ Process systematically
- ✅ Review and refine

### Beyond: Advanced Usage
- ✅ Import from CSV
- ✅ Create custom workflows
- ✅ Use profiles for different users
- ✅ Optimize for your needs

## 🔥 Your First Success

Here's a guaranteed-to-work first test:

**Step-by-step:**
1. ✅ Setup: Record all 5 coordinates
2. ✅ Command: Type "Add colors category"
3. ✅ Click: "Process Command"
4. ✅ Result: 10 colors automatically added!

**Expected output:**
```
[12:34:56] Processing command: Add colors category
[12:34:57] Analyzing command with AI...
[12:34:59] Understood: add_category - colors
[12:34:59] Generating items with AI...
[12:35:02] Generated 10 items
[12:35:02] Items: Red, Blue, Green, Yellow, Orange, Purple, Pink, Brown, Black, White
[12:35:02] Starting automation...
[12:35:02] 5...4...3...2...1...
[12:35:07] Starting automation...
[12:35:07] Step 1: Creating category 'colors'
[12:35:09] Step 2: Adding 10 items to category
[12:35:10]   [1/10] Adding 'Red'...
[12:35:12]   [2/10] Adding 'Blue'...
...
[12:35:28] Successfully processed category 'colors' with 10 items!
```

## 📊 What You Get

### Categories You Can Add
- 🍽️ Food & Restaurants
- 🐕 Animals & Pets
- 🎨 Colors & Shapes
- 😊 Emotions & Feelings
- 👨‍👩‍👧 Family & People
- ⚽ Sports & Activities
- 🌤️ Weather
- 🏥 Medical & Health
- 🏫 School & Education
- 🚗 Transportation
- 🏠 Places & Locations
- ⏰ Time & Schedule
- And anything else you can think of!

### Time Saved
- **Manual:** ~4 minutes per 10-item category
- **With Assistant:** ~25 seconds per 10-item category
- **Time Saved:** ~3.5 minutes per category
- **20 categories:** Save over 1 hour!

## 🎁 Advanced Features Summary

✨ **AI Suggestions** - Get smart recommendations
📦 **Batch Processing** - Handle multiple categories
🔐 **Secure Storage** - Encrypted API key
👁️ **Visual Verification** - Confirm coordinates
🪟 **Window Detection** - Auto-focus TD Snap
📖 **OCR Reading** - Analyze vocabulary
🔄 **Error Recovery** - Retry failed operations
↩️ **Undo/Redo** - Track changes
👤 **User Profiles** - Multiple users
⌨️ **Shortcuts** - Fast workflows

## 🆘 Need Help?

### Check These First
1. **Activity Log** - Shows what's happening
2. **ADVANCED_FEATURES.md** - Complete feature guide
3. **README.md** - General troubleshooting

### Still Stuck?
- Make sure Python 3.7+ is installed
- Verify all dependencies installed
- Check TD Snap is running and in edit mode
- Try re-recording coordinates
- Restart the application

## 🎉 You're Ready!

You now have:
- ✅ Dependencies installed
- ✅ API key configured
- ✅ Coordinates recorded
- ✅ First command tested
- ✅ Understanding of features

**Go build amazing AAC vocabulary!** 🚀

---

**Total Setup Time: ~10 minutes**
**Lifetime Saved: Hours and hours!**

**Welcome to the Advanced Edition!** 🎊
