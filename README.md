# TD Snap AI Assistant

An AI-powered desktop application that automates TD Snap (AAC communication software) to help you quickly add categories and words using natural language commands.

## Features

- 🤖 **AI-Powered**: Uses Claude AI to understand natural language commands and generate appropriate category items
- 🎯 **Easy Automation**: Automate adding entire categories with common items
- 📍 **Coordinate Recording**: Built-in tool to teach the app where to click in TD Snap
- ⚙️ **Customizable**: Adjust delays, item counts, and typing speed
- 🚀 **User-Friendly**: Simple GUI with activity logging

## Two Versions

### Basic Version (`td_snap_ai_assistant.py`)
- Simpler interface
- Good for getting started
- Manual coordinate configuration

### Pro Version (`td_snap_ai_assistant_pro.py`) ⭐ RECOMMENDED
- Coordinate recording tool
- Tabbed interface
- Saved configurations
- More robust automation

## Installation

### Prerequisites
- Python 3.7 or higher
- TD Snap application installed
- Windows, macOS, or Linux

### Setup Steps

1. **Install Python** (if not already installed)
   - Download from [python.org](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"

2. **Download this project**
   ```bash
   # Extract the files to a folder like C:\TDSnapAssistant
   ```

3. **Install dependencies**
   Open a terminal/command prompt in the project folder and run:
   ```bash
   pip install -r requirements.txt
   ```

   Or install individually:
   ```bash
   pip install pyautogui pillow requests keyboard
   ```

## Usage

### Step 1: Launch the Application

Run the Pro version (recommended):
```bash
python td_snap_ai_assistant_pro.py
```

Or use the launcher:
- **Windows**: Double-click `launch.bat`
- **Mac/Linux**: Run `./launch.sh`

### Step 2: Configure Coordinates (First Time Only)

1. Open TD Snap and enter **edit mode**
2. In the TD Snap AI Assistant, go to the **"Setup Coordinates"** tab
3. For each button (Add Category, Add Button, etc.):
   - Click the "Record" button
   - Within 3 seconds, move your mouse over the target button in TD Snap
   - The position will be recorded
4. Repeat for all required coordinates

**Important coordinate points:**
- **Add Category Button**: The button to create a new category
- **Add New Button/Word**: The button to add a new word/button
- **Button Label Field**: The text field where you type the word/label
- **Category Name Field**: Where you type the category name
- **Save Button**: The button to save changes

### Step 3: Use Natural Language Commands

Once coordinates are set up, you can use commands like:

- "Add restaurants category"
- "Add animals category with 15 items"
- "Create a colors category"
- "Add food category"

The AI will:
1. Understand your request
2. Generate appropriate items for the category
3. Automatically add them to TD Snap

## Example Commands and Results

### Command: "Add restaurants category"
**AI Generates:**
- McDonald's
- Burger King
- Subway
- Pizza Hut
- Taco Bell
- Wendy's
- KFC
- Chick-fil-A
- Olive Garden
- Chipotle

### Command: "Add colors category"
**AI Generates:**
- Red
- Blue
- Green
- Yellow
- Orange
- Purple
- Pink
- Brown
- Black
- White

### Command: "Add animals category with 15 items"
**AI Generates:**
- Dog
- Cat
- Bird
- Fish
- Horse
- Cow
- Pig
- Chicken
- Rabbit
- Turtle
- Bear
- Lion
- Elephant
- Monkey
- Giraffe

## Settings

### Automation Settings (Settings Tab)
- **Delay between actions**: Time to wait between clicks (default: 1 second)
- **Default items per category**: How many items to generate (default: 10)
- **Countdown before start**: Time to position windows before automation starts (default: 5 seconds)
- **Typing speed**: How fast to type text (default: 0.05 seconds per character)

### Tips for Best Results

1. **Screen Resolution**: Coordinates are screen-position dependent. If you change your screen resolution or move TD Snap to a different monitor, you'll need to re-record coordinates.

2. **Window Position**: Keep TD Snap in the same position on your screen for consistent automation.

3. **Test First**: Start with a small category (5-10 items) to test your coordinate setup.

4. **Delays**: If automation is too fast for TD Snap, increase the delay in settings.

5. **Stop Anytime**: Click the "Stop" button if you need to interrupt automation.

## Troubleshooting

### "Missing coordinates" error
- You need to set up coordinates first in the "Setup Coordinates" tab

### Clicks are in the wrong place
- Re-record the coordinates
- Make sure TD Snap is in the same window position as when you recorded
- Check your screen resolution hasn't changed

### AI not generating items
- Check your internet connection (required for AI)
- The free AI API has rate limits - wait a moment and try again

### Automation is too fast/slow
- Adjust the "Delay between actions" in Settings
- Increase countdown time if you need more time to position windows

### Items aren't being typed correctly
- Adjust the "Typing speed" in Settings
- Make sure TD Snap window is active and in focus

## How It Works

1. **Natural Language Processing**: Your command is sent to Claude AI to understand what category you want and how many items

2. **Content Generation**: Claude AI generates appropriate, practical items for that category based on AAC best practices

3. **GUI Automation**: The app uses `pyautogui` to simulate mouse clicks and keyboard typing to interact with TD Snap

4. **Coordinate System**: You teach the app where to click by recording positions, which are saved for future use

## Advanced Usage

### Custom Item Counts
Add a number to your command:
- "Add restaurants category with 20 items"
- "Create animals with 5 items"

### Editing Coordinates File
Coordinates are saved in `td_snap_coordinates.json`. You can manually edit this file if needed:
```json
{
  "add_category": {"x": 100, "y": 200},
  "add_button": {"x": 150, "y": 250}
}
```

## Safety Notes

- ⚠️ **Always supervise automation** - Don't leave it unattended
- ⚠️ **Save your TD Snap work** before running automation
- ⚠️ **Test with small batches** first
- ⚠️ **Keep backups** of your TD Snap configuration

## Future Enhancements

Possible future features:
- Image/symbol selection
- Category organization
- Batch operations
- Voice command input
- Import/export word lists
- Template categories

## System Requirements

- **OS**: Windows 10/11, macOS 10.14+, or Linux
- **Python**: 3.7 or higher
- **RAM**: 4GB minimum
- **TD Snap**: Latest version recommended
- **Internet**: Required for AI features

## Support

For issues with:
- **TD Snap software**: Contact Tobii Dynavox support
- **This automation tool**: Check the Activity Log for error messages

## License

This is a helper tool for TD Snap. TD Snap is owned by Tobii Dynavox. This automation tool is provided as-is for personal use.

## Credits

- Built with Python and Tkinter
- AI powered by Claude (Anthropic)
- GUI automation using PyAutoGUI
- Designed for the AAC community

---

**Made with ❤️ to help AAC users communicate more effectively**
