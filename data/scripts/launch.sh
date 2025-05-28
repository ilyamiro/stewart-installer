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

desktop_entry() {
    local desktop_file_name="stewart.desktop"
    local desktop_entry_name="stewart"
    local desktop_file_path="$HOME/.local/share/applications/$desktop_file_name"
    local icon_path="$DIR/data/images/stewart.png"
    local exec_path="$DIR/scripts/launch.sh $DIR"

    mkdir -p "$HOME/.local/share/applications"

    cat > "$desktop_file_path" <<EOF
[Desktop Entry]
Name=Stewart
GenericName=Voice Assistant
Comment=Useful voice assistant
Exec=$exec_path
Icon=$icon_path
Terminal=true
Type=Application
Categories=Utility;Application;
EOF

    chmod +x "$desktop_file_path"
    echo "Desktop shortcut created at: $desktop_file_path"

    echo "Attempting to launch the desktop entry..."

    # Try gtk-launch
    if command -v gtk-launch &> /dev/null; then
        gtk-launch "$desktop_entry_name" && return
    fi

    if command -v xdg-open &> /dev/null; then
        xdg-open "$desktop_file_path" && return
    fi

    if command -v gio &> /dev/null; then
        gio open "$desktop_file_path" && return
    fi

     # Try dbus-send (GNOME only)
    if command -v dbus-send &> /dev/null; then
        dbus-send --session --dest=org.freedesktop.Application.$desktop_entry_name \
            /org/freedesktop/Application/$desktop_entry_name \
            org.freedesktop.Application.Activate \
            &> /dev/null && return
    fi

    echo "Warning: Could not automatically launch Stewart. Please run it manually from your applications menu."
}

desktop_entry
