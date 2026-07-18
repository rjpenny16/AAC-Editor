#!/bin/bash

cd -- "$(dirname -- "$0")" || exit 1

echo "Starting AAC Editor..."
echo ""

if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed"
    echo "Please install Python from https://www.python.org/downloads/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

if ! python3 -c "import flask" 2>/dev/null; then
    echo "Installing required packages..."
    if ! python3 -m pip install .; then
        echo "ERROR: Failed to install dependencies"
        echo ""
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Replace an older copy still serving this port with the current checkout.
python3 -c "import json,time,urllib.request as u; b='http://127.0.0.1:8765'; c=json.load(u.urlopen(b+'/api/config',timeout=1)); u.urlopen(u.Request(b+'/api/quit',data=b'',headers={'X-TDSnap-Token':c['token']}),timeout=2).read(); time.sleep(1)" >/dev/null 2>&1

echo ""
echo "Opening the app in your browser..."
python3 -m tdsnap.web

if [ $? -ne 0 ]; then
    echo ""
    echo "Application exited with an error."
    read -p "Press Enter to exit..."
fi
