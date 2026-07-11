#!/bin/bash

echo "Starting TD Snap Page Builder..."
echo ""

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python from https://www.python.org/downloads/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

if ! python3 -c "import flask, requests" 2>/dev/null; then
    echo "Installing required packages..."
    if ! python3 -m pip install -r requirements.txt; then
        echo "ERROR: Failed to install dependencies"
        echo ""
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

echo ""
echo "Opening the app in your browser..."
python3 -m tdsnap.web

if [ $? -ne 0 ]; then
    echo ""
    echo "Application exited with an error."
    read -p "Press Enter to exit..."
fi
