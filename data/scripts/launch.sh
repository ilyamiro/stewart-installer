#!/bin/bash

set -euo pipefail

DIR=${1:-}

# Check if install directory was passed
if [[ -z "$DIR" ]]; then
    echo "Usage: $0 <app_install_dir>"
    exit 1
fi

# Check if Python 3.11 is installed
if ! command -v python3.11 &> /dev/null; then
    echo "Error: python3.11 is not installed or not in PATH."
    exit 1
fi

# Check if the directory exists
if [[ ! -d "$DIR" ]]; then
    echo "Error: App install directory '$DIR' does not exist."
    exit 1
fi

# Check if the virtual environment exists
if [[ ! -f "$DIR/venv/bin/activate" ]]; then
    echo "Error: Virtual environment not found in '$DIR/venv'."
    exit 1
fi

# Check if main.py exists
if [[ ! -f "$DIR/main.py" ]]; then
    echo "Error: main.py not found in '$DIR'."
    exit 1
fi

# Activate venv and run the app
cd "$DIR"
source venv/bin/activate
python3.11 main.py
