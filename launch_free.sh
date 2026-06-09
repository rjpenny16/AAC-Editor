#!/bin/bash

echo "===================================="
echo "TD Snap AI Assistant - FREE Edition"
echo "100% Free with Local AI!"
echo "===================================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null
then
    echo "ERROR: Python 3 not installed"
    exit 1
fi

echo "Checking dependencies..."
if ! python3 -c "import pyautogui" 2>/dev/null; then
    echo "Installing dependencies..."
    pip3 install -r requirements_free.txt
    echo ""
fi

echo ""
echo "===================================="
echo "RECOMMENDED: Install Ollama for FREE AI"
echo ""
echo "Mac: brew install ollama"
echo "Linux: curl https://ollama.ai/install.sh | sh"
echo ""
echo "Then run: ollama pull llama3"
echo ""
echo "Restart this application after installing!"
echo "===================================="
echo ""
read -p "Press Enter to continue..."

echo "Starting FREE Edition..."
python3 td_snap_ai_assistant_free.py
