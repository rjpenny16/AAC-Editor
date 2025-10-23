# TD Snap AI Assistant

AI-powered automation tool for TD Snap that helps you quickly add categories and words using natural language.

## Quick Start

### 1. Install and Run (One Step!)

**Windows:** Double-click `launch.bat`
**Mac/Linux:** Double-click `launch.sh` (or run `./launch.sh` in terminal)

That's it! The launcher automatically installs everything you need.

### 2. Setup Coordinates (First Time Only - 3 minutes)

1. Open TD Snap and enter **edit mode**
2. In TD Snap AI Assistant, go to **"Setup Coordinates"** tab
3. For each button, click "Record" then hover over the target in TD Snap:
   - Add Category Button
   - Add New Button/Word
   - Button Label Field
   - Category Name Field
   - Save Button

### 3. Start Using

Go to the **"Command"** tab and type natural language commands like:
- "Add restaurants category"
- "Add colors"
- "Create animals with 15 items"
- "Add food category"

Click "Process Command" and watch the automation work!

## Example Results

**"Add restaurants"** generates:
McDonald's, Burger King, Subway, Pizza Hut, Taco Bell, Wendy's, KFC, Chick-fil-A, Olive Garden, Chipotle

**"Add colors"** generates:
Red, Blue, Green, Yellow, Orange, Purple, Pink, Brown, Black, White

**"Add animals with 15 items"** generates:
Dog, Cat, Bird, Fish, Horse, Cow, Pig, Chicken, Rabbit, Turtle, Bear, Lion, Elephant, Monkey, Giraffe

## Requirements

- **Python 3.7+** (download from [python.org](https://www.python.org/downloads/))
- **TD Snap** installed
- **Internet connection** (for AI features)

The launcher handles all Python package installation automatically.

## Settings

Adjust in the **Settings** tab:
- **Delay between actions**: Speed of automation (default: 1 second)
- **Items per category**: Default number to generate (default: 10)
- **Countdown before start**: Time to position windows (default: 5 seconds)
- **Typing speed**: How fast to type (default: 0.05 seconds/character)

## Troubleshooting

**Clicks in wrong place:**
- Re-record coordinates in Setup tab
- Keep TD Snap in same window position
- Check screen resolution hasn't changed

**AI not working:**
- Check internet connection
- Wait 30 seconds and retry (free API has rate limits)

**Too fast/slow:**
- Adjust "Delay between actions" in Settings
- Increase typing speed if characters are missed

**Missing coordinates:**
- Go to Setup Coordinates tab and record all positions

## Tips

- Test with small categories first (5 items)
- Keep TD Snap window in same position
- Save TD Snap work before large batches
- Use Stop button to interrupt anytime
- Watch Activity Log for errors

## How It Works

1. **Natural Language → AI**: Your command is sent to Claude AI
2. **AI Generates Items**: Claude creates appropriate category items
3. **Automation**: App uses recorded coordinates to click and type in TD Snap
4. **Results**: Category and items appear in TD Snap automatically

## Safety

- Always supervise automation
- Save your work before running
- Test with small batches first
- Keep backups of TD Snap configuration

## What's Included

- `td_snap_ai_assistant.py` - Main application
- `launch.bat` - Windows launcher (auto-installs dependencies)
- `launch.sh` - Mac/Linux launcher (auto-installs dependencies)
- `requirements.txt` - Python dependencies (auto-installed)
- `README.md` - This file

## Manual Installation (Optional)

If you prefer manual installation:
```bash
pip install -r requirements.txt
python td_snap_ai_assistant.py
```

## Support

**For this tool:** Check Activity Log in the app for error messages
**For TD Snap:** Contact Tobii Dynavox support

---

**Made for the AAC community to make vocabulary building faster and easier**
