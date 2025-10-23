# TD Snap AI Assistant

AI-powered automation tool for TD Snap that helps you quickly add categories and words using natural language.

**NEW:** Now uses Ollama for local, private AI processing - no internet required!

## Quick Start

### 1. Install Ollama (One-Time Setup)

**Windows:** Download from [ollama.com/download](https://ollama.com/download)
**Mac/Linux:** Run `curl -fsSL https://ollama.com/install.sh | sh`

Then pull a model:
```bash
ollama pull llama3.2
```

### 2. Install and Run the App (One Click!)

**Windows:** Double-click `launch.bat`
**Mac/Linux:** Double-click `launch.sh` (or run `./launch.sh` in terminal)

That's it! The launcher automatically installs all Python dependencies.

### 3. Setup Coordinates (First Time Only - 3 minutes)

1. Open TD Snap and enter **edit mode**
2. In TD Snap AI Assistant, go to **"Setup Coordinates"** tab
3. For each button, click "Record" then hover over the target in TD Snap:
   - Add Category Button
   - Add New Button/Word
   - Button Label Field
   - Category Name Field
   - Save Button

### 4. Configure Ollama (First Time Only)

1. Go to **Settings** tab
2. Verify **Ollama Host**: `http://localhost:11434`
3. Select **Model**: `llama3.2` (or your preferred model)
4. Click **Test Ollama Connection** to verify

### 5. Start Using!

Go to the **"Command"** tab and type natural language commands like:
- "Add restaurants category"
- "Add colors"
- "Create animals with 15 items"
- "Add food category"

Click "Process Command" and watch the automation work!

## Why Ollama?

- **Privacy**: All processing happens locally - your data never leaves your device
- **Offline**: Works without internet connection
- **Free**: No API costs
- **Fast**: Quick responses on decent hardware

## Example Results

**"Add restaurants"** generates:
McDonald's, Burger King, Subway, Pizza Hut, Taco Bell, Wendy's, KFC, Chick-fil-A, Olive Garden, Chipotle

**"Add colors"** generates:
Red, Blue, Green, Yellow, Orange, Purple, Pink, Brown, Black, White

**"Add animals with 15 items"** generates:
Dog, Cat, Bird, Fish, Horse, Cow, Pig, Chicken, Rabbit, Turtle, Bear, Lion, Elephant, Monkey, Giraffe

## Requirements

- **Python 3.7+** (download from [python.org](https://www.python.org/downloads/))
- **Ollama** with a model installed (see step 1 above)
- **TD Snap** installed
- **8GB RAM recommended** (for running local AI models)

The launcher handles all Python package installation automatically.

## Settings

Adjust in the **Settings** tab:
- **Delay between actions**: Speed of automation (default: 1 second)
- **Items per category**: Default number to generate (default: 10)
- **Countdown before start**: Time to position windows (default: 5 seconds)
- **Typing speed**: How fast to type (default: 0.05 seconds/character)
- **Ollama Host**: Local Ollama server address (default: localhost:11434)
- **Ollama Model**: Which AI model to use (e.g., llama3.2)

## Recommended Ollama Models

| Model | Size | Best For |
|-------|------|----------|
| llama3.2 | 2GB | Most users - fast & accurate |
| llama3.1 | 4.7GB | Better quality, slower |
| phi3 | 2.3GB | Low-end hardware |

To install a model:
```bash
ollama pull <model-name>
```

## Troubleshooting

**Cannot connect to Ollama:**
- Check Ollama is running: `ollama list`
- Start Ollama if needed: `ollama serve`
- Verify port 11434 is accessible

**Clicks in wrong place:**
- Re-record coordinates in Setup tab
- Keep TD Snap in same window position
- Check screen resolution hasn't changed

**Too fast/slow:**
- Adjust "Delay between actions" in Settings
- Increase typing speed if characters are missed

**Missing coordinates:**
- Go to Setup Coordinates tab and record all positions

**Ollama too slow:**
- Try a smaller model (phi3)
- Close other applications
- Ensure you have enough RAM

## Tips

- Test with small categories first (5 items)
- Keep TD Snap window in same position
- Save TD Snap work before large batches
- Use Stop button to interrupt anytime
- Watch Activity Log for errors

## How It Works

1. **Natural Language → AI**: Your command is sent to Ollama running locally
2. **AI Generates Items**: Ollama creates appropriate category items
3. **Automation**: App uses recorded coordinates to click and type in TD Snap
4. **Results**: Category and items appear in TD Snap automatically

## Safety & Privacy

- **100% Local**: All AI processing happens on your computer
- **No Cloud**: No data sent to external servers
- **Offline Capable**: Works completely offline once set up
- **Always supervise**: Watch the automation as it runs
- **Backup**: Keep backups of TD Snap configuration

## What's Included

- `td_snap_ai_assistant.py` - Main application
- `launch.bat` - Windows launcher (auto-installs dependencies)
- `launch.sh` - Mac/Linux launcher (auto-installs dependencies)
- `requirements.txt` - Python dependencies (auto-installed)
- `README.md` - This file
- `OLLAMA_INTEGRATION.md` - Technical details about Ollama integration

## Advanced Users

For technical details about Ollama integration, API usage, and architecture, see [OLLAMA_INTEGRATION.md](OLLAMA_INTEGRATION.md).

## Manual Installation (Optional)

If you prefer manual installation:
```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Ollama and pull a model
ollama pull llama3.2

# Run the app
python td_snap_ai_assistant.py
```

## Support

**For this tool:** Check Activity Log in the app for error messages
**For Ollama:** Visit [github.com/ollama/ollama](https://github.com/ollama/ollama)
**For TD Snap:** Contact Tobii Dynavox support

---

**Made for the AAC community to make vocabulary building faster, easier, and more private**
