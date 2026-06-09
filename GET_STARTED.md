# 🎯 Get Started - TD Snap AI Assistant Advanced Edition

**Your complete guide to getting up and running in 15 minutes!**

---

## 📚 Documentation Overview

**New here? Start with this guide! ⬇️**

### Quick Reference

| Document | Purpose | Time | When to Read |
|----------|---------|------|--------------|
| **GET_STARTED.md** | Complete setup guide | 15 min | **START HERE** |
| QUICKSTART_ADVANCED.md | Minimal setup | 10 min | If you're in a hurry |
| README_ADVANCED.md | Full reference | 30 min | For complete understanding |
| ADVANCED_FEATURES.md | Feature deep-dive | 20 min | To explore capabilities |
| INSTALLATION.md | Platform-specific setup | 15 min | If installation fails |
| WHATS_NEW.md | What changed | 10 min | If upgrading from Pro |
| IMPLEMENTATION_SUMMARY.md | Technical details | 15 min | For developers |

---

## 🎬 15-Minute Complete Setup

### ⏱️ Minute 0-3: Pre-Flight Check

**What you need:**
- [ ] Computer (Windows/Mac/Linux)
- [ ] TD Snap installed
- [ ] Internet connection
- [ ] 15 minutes of time
- [ ] Credit card for Anthropic API (free tier available)

**Check Python:**
```bash
python --version
# Should show Python 3.7 or higher
# If not, download from python.org
```

---

### ⏱️ Minute 3-6: Install Everything

**Step 1: Download/Clone Project**
```bash
# Option A: Git clone
git clone [repository-url]
cd AAC-Editor

# Option B: Download ZIP and extract
```

**Step 2: Install Python Packages**
```bash
pip install -r requirements.txt
```

Wait for installation... (~2-3 minutes)

**Step 3: Optional - Install Tesseract OCR**

**Windows:**
- Download: https://github.com/UB-Mannheim/tesseract/wiki
- Install (1 minute)

**Mac:**
```bash
brew install tesseract
```

**Linux:**
```bash
sudo apt install tesseract-ocr
```

**Skip if you don't need AI suggestions yet - you can install later!**

---

### ⏱️ Minute 6-9: Get API Access

**Step 1: Create Anthropic Account**
1. Go to https://console.anthropic.com/
2. Sign up (email + password)
3. Verify email

**Step 2: Get API Key**
1. Navigate to "API Keys"
2. Click "Create Key"
3. Copy the key (starts with `sk-ant-...`)
4. **Save it somewhere safe!**

**Step 3: Add Credits (Optional)**
- Free tier: $5 credit
- Paid: Add payment method
- For testing: Free tier is fine

---

### ⏱️ Minute 9-10: Launch Application

**Windows:**
```bash
launch_advanced.bat
```

**Mac/Linux:**
```bash
chmod +x launch_advanced.sh
./launch_advanced.sh
```

**Direct:**
```bash
python td_snap_ai_assistant_advanced.py
```

Application should open!

---

### ⏱️ Minute 10-12: Configure API

**In the application:**

1. Click **Settings** tab
2. Paste your API key in "Anthropic API Key" field
3. Click **Save API Key**
4. Click **Test Connection**

**Expected result:**
```
✓ API test successful: API test successful
```

If you see this, you're good! ✅

**If it fails:**
- Check internet connection
- Verify API key copied correctly
- Check API credits at console.anthropic.com

---

### ⏱️ Minute 12-15: Setup Coordinates

**Prepare:**
1. Open TD Snap
2. Go to Edit Mode
3. Position window where you can see both apps

**In the application:**

1. Click **Setup Coordinates** tab
2. For each button:

   **a) Add Category Button:**
   - Click "Record"
   - You have 3 seconds!
   - Move mouse over "Add Category" button in TD Snap
   - Position recorded ✓

   **b) Add New Button/Word:**
   - Click "Record"
   - Move mouse over "Add Button" in TD Snap
   - Position recorded ✓

   **c) Button Label Field:**
   - Click "Record"
   - Move mouse over text field for button names
   - Position recorded ✓

   **d) Category Name Field:**
   - Click "Record"
   - Move mouse over category name field
   - Position recorded ✓

   **e) Save Button:**
   - Click "Record"
   - Move mouse over Save button
   - Position recorded ✓

3. **Verify each coordinate:**
   - Click "Verify" next to each one
   - Look for green ✓ (good) or red ✗ (re-record)

---

### ⏱️ Minute 15: First Success! 🎉

**Go to Command tab:**

1. Type: `Add colors category`
2. Click **Process Command**

**Watch the magic:**
```
[12:34:56] Processing command: Add colors category
[12:34:57] Analyzing command with AI...
[12:34:59] Understood: add_category - colors
[12:34:59] Generating items with AI...
[12:35:02] Generated 10 items
[12:35:02] Items: Red, Blue, Green, Yellow, Orange,
           Purple, Pink, Brown, Black, White
[12:35:02] Starting automation...
[12:35:07] 5...4...3...2...1...
[12:35:07] Step 1: Creating category 'colors'
[12:35:09] Step 2: Adding 10 items to category
[12:35:10]   [1/10] Adding 'Red'...
[12:35:12]   [2/10] Adding 'Blue'...
...
[12:35:28] ✓ Successfully processed category 'colors'
           with 10 items!
```

**Check TD Snap:**
- You should see a "colors" category
- With 10 color words!

**🎉 Congratulations! You're all set up!**

---

## 🎯 What to Try Next (Your First Hour)

### Task 1: Try Different Categories (10 min)

```
Add animals category
Add food category
Add emotions with 12 items
Add restaurants category
```

### Task 2: Use Quick Examples (5 min)

Click the quick example buttons in the Command tab - they auto-fill!

### Task 3: Try Window Focus (2 min)

1. Move TD Snap window around
2. Click "Focus TD Snap" button
3. Watch it come to front automatically!

### Task 4: Explore AI Suggestions (10 min)

1. Go to **AI Suggestions** tab
2. Click **Generate Suggestions**
3. Read AI recommendations
4. Try adding one of the suggested categories

### Task 5: Try Batch Operations (15 min)

1. Go to **Batch Operations** tab
2. Click **Import from CSV**
3. Select `example_batch.csv`
4. Click **Process Queue**
5. Watch it process 10 categories automatically!

### Task 6: Use Keyboard Shortcuts (5 min)

- Type a command and press **Enter** (instead of clicking button)
- Try **Ctrl+Z** to undo
- Try **Esc** to stop during automation

### Task 7: Customize Settings (10 min)

1. Go to **Settings** tab
2. Try adjusting "Delay between actions"
   - Increase if TD Snap is slow
   - Decrease for faster automation
3. Change "Default items per category"
4. Test with new settings

---

## 🔥 Common First-Day Questions

### Q: How many items should I add per category?
**A:** Start with 10 (default). Common range is 8-15. AI knows what's important for each category.

### Q: What categories should I start with?
**A:** Try the AI Suggestions feature! It recommends based on AAC best practices. Common starters:
- Colors
- Animals
- Family members
- Emotions
- Food
- Common actions (eat, drink, sleep, etc.)

### Q: Can I customize the words generated?
**A:** Yes! The AI generates smart defaults, but you can:
1. Generate items
2. Review in Activity Log
3. Manually edit in TD Snap after automation
4. Or specify in your command: "Add restaurants with fast food chains"

### Q: What if I make a mistake?
**A:**
- Stop automation with Esc or Stop button
- Undo tracking helps you see what was added
- Manually remove from TD Snap (automation doesn't delete)
- Re-run with corrected command

### Q: Is my API key secure?
**A:** Yes!
- Encrypted with AES 128-bit (Fernet)
- Stored locally only (`.config/` folder)
- Never logged or transmitted except to Anthropic
- Can be deleted by removing `.config/` folder

### Q: How much does the API cost?
**A:**
- Free tier: $5 credit
- After that: ~$0.01 per category (~$1 for 100 categories)
- Very affordable for personal use
- See pricing at anthropic.com

### Q: What if coordinates stop working?
**A:**
- Screen resolution changed? Re-record
- TD Snap updated? Re-record
- Window moved? Try "Focus TD Snap" button
- Click "Verify" to check which ones need re-recording

---

## 🎓 Learning Path

### Week 1: Basic Mastery
**Goal:** Get comfortable with core features

- Day 1: Setup + try 5 simple commands
- Day 2: Explore AI Suggestions
- Day 3: Try batch operations
- Day 4: Customize settings
- Day 5: Build comprehensive vocabulary
- Day 6-7: Refine and practice

**By end of week:** Confident with basic workflow

### Week 2: Advanced Features
**Goal:** Master advanced capabilities

- Day 1: Learn keyboard shortcuts
- Day 2: Create custom batch CSVs
- Day 3: Experiment with profiles
- Day 4: Try OCR vocabulary reading
- Day 5: Optimize your workflow
- Day 6-7: Build complete vocabulary set

**By end of week:** Power user!

### Beyond: Expert Level
- Create reusable batch templates
- Share vocabularies with others
- Contribute to documentation
- Help others get started

---

## 🆘 Troubleshooting Your First Day

### Issue: "API Key Required" error
**Solution:**
1. Go to Settings tab
2. Make sure API key is entered
3. Click "Save API Key" (not just enter!)
4. Test connection

### Issue: "Setup Required" error
**Solution:**
1. Go to Setup Coordinates tab
2. Record all 5 positions
3. Verify each one shows coordinates (not "Not set")

### Issue: Clicks in wrong place
**Solution:**
1. Re-record the wrong coordinate
2. Click "Verify" to check
3. Make sure TD Snap window hasn't moved
4. Keep TD Snap in same position during automation

### Issue: Too fast/too slow
**Solution:**
1. Settings tab
2. Adjust "Delay between actions"
   - Too fast? Increase to 2.0
   - Too slow? Decrease to 0.5
3. Try again

### Issue: Items not being added
**Solution:**
1. Check TD Snap is in edit mode
2. Verify coordinates are correct (use Verify button)
3. Check Activity Log for specific errors
4. Enable "Error recovery & retry" in Settings

### Issue: Can't find TD Snap window
**Solution:**
1. Make sure TD Snap is running
2. Check window title is exactly "TD Snap"
3. Try clicking "Focus TD Snap" manually
4. If that fails, position windows manually

---

## 📊 Quick Reference Card

**Print this for your desk!**

### Common Commands
```
Add [category] category
Add [category] with [number] items
Create [category] category
```

### Keyboard Shortcuts
```
Enter  - Process command
Ctrl+Z - Undo
Ctrl+Y - Redo
Ctrl+S - Save coordinates
Esc    - Stop
```

### Five Tabs
```
1. Command        - Main interface
2. AI Suggestions - Smart recommendations
3. Batch Ops      - Multiple categories
4. Coordinates    - Setup positions
5. Settings       - API key, preferences
```

### Support Resources
```
Activity Log       - See what's happening
QUICKSTART.md      - Quick reference
README.md          - Full documentation
ADVANCED_FEATURES  - Feature details
```

---

## 🎯 Your First Week Goals

### Day 1: Setup ✅
- Install application
- Configure API key
- Record coordinates
- Process first command

### Day 2: Basic Use
- Add 10 categories
- Try different item counts
- Use quick examples
- Review Activity Log

### Day 3: AI Features
- Generate suggestions
- Analyze vocabulary
- Try batch operations

### Day 4: Optimization
- Adjust settings
- Verify coordinates
- Test error recovery
- Learn shortcuts

### Day 5: Production Use
- Build complete vocabulary
- Create batch CSVs
- Setup profiles
- Share with others

---

## 💡 Pro Tips for Day 1

1. **Start small** - Try 5 items before 50
2. **Verify early** - Use Verify button after recording coordinates
3. **Watch first** - Observe the first automation completely
4. **Save often** - Save TD Snap work before large batches
5. **Check log** - Activity Log shows everything that's happening
6. **Test connection** - Use Test API Connection before starting
7. **Use examples** - Quick examples are pre-tested commands
8. **Read feedback** - Application gives helpful error messages
9. **Take notes** - Note what works for your specific TD Snap setup
10. **Ask questions** - Documentation is comprehensive!

---

## 🎉 Success Checklist

After first day, you should have:

- [ ] Application installed and running
- [ ] API key configured and tested
- [ ] All 5 coordinates recorded and verified
- [ ] Successfully added at least 1 category
- [ ] Tried AI suggestions
- [ ] Explored batch operations
- [ ] Customized at least 1 setting
- [ ] Know where to find help
- [ ] Comfortable with basic workflow
- [ ] Ready to build comprehensive vocabulary!

---

## 🚀 You're Ready!

You now have:
- ✅ Complete installation
- ✅ Working configuration
- ✅ Understanding of features
- ✅ First successful automation
- ✅ Resources for learning more

**Go build amazing AAC vocabularies!** 🌟

---

## 📞 Where to Get Help

1. **Activity Log** - Built into application
2. **QUICKSTART_ADVANCED.md** - Quick reference
3. **README_ADVANCED.md** - Comprehensive guide
4. **ADVANCED_FEATURES.md** - Feature documentation
5. **INSTALLATION.md** - Setup help
6. **WHATS_NEW.md** - Recent changes

**Can't find answer?**
- Check the specific feature documentation
- Review troubleshooting sections
- Verify all prerequisites met

---

**Welcome to the TD Snap AI Assistant Advanced Edition!**

**You've got this!** 💪

Happy vocabulary building! 🎊
