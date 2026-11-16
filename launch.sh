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

# Suggestions need the AI extra (llama-cpp-python), which the installed app
# bundles. Install a prebuilt copy if one exists for this Python; never
# compile. If none installs, the suggestions panel says that AI is not
# included when started this way, and everything else works as usual.
if ! python3 -c "import llama_cpp" 2>/dev/null; then
    echo "Installing the suggestion engine (optional)..."
    python3 -m pip install ".[ai]" --only-binary llama-cpp-python --prefer-binary \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu >/dev/null 2>&1
    if ! python3 -c "import llama_cpp" 2>/dev/null; then
        echo "Suggestions are not included when AAC Editor is started this way."
        echo "Use the installed app for suggestions. Everything else works."
    fi
fi

# If AAC Editor is already open (this checkout or the installed app), the
# next line brings it to the front instead of starting a second copy. It is
# never closed from here: closing it would lose unsaved work.

echo ""
echo "Opening the app in your browser..."
python3 -m tdsnap.web

if [ $? -ne 0 ]; then
    echo ""
    echo "Application exited with an error."
    read -p "Press Enter to exit..."
fi
