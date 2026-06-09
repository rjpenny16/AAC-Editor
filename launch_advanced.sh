#!/bin/bash

echo "===================================="
echo "TD Snap AI Assistant - Advanced Edition"
echo "===================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null
then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python 3.7 or higher"
    exit 1
fi

echo "Checking dependencies..."
echo ""

# Check if requirements are installed
if ! python3 -c "import anthropic" 2>/dev/null; then
    echo "Installing required dependencies..."
    pip3 install -r requirements.txt
    echo ""
fi

echo "Starting TD Snap AI Assistant Advanced Edition..."
echo ""
python3 td_snap_ai_assistant_advanced.py

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Application failed to start"
    echo "Please check the error messages above"
    read -p "Press Enter to continue..."
    exit 1
fi
