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

# RESERVED
#create_desktop_entry() {
#    local desktop_file_name="stewart.desktop"
#    local desktop_file_path="$HOME/.local/share/applications/$desktop_file_name"
#    local icon_path="$DIR/data/images/stewart.png"
#    local exec_path="$DIR/launch.sh"
#
#    # Ensure applications directory exists
#    mkdir -p "$HOME/.local/share/applications"
#
#    # Create the .desktop file
#    cat > "$desktop_file_path" <<EOF
#[Desktop Entry]
#Name=Stewart
#GenericName=Voice Assistant
#Comment=Useful voice assistant
#Exec=$exec_path
#Icon=$icon_path
#Terminal=true
#Type=Application
#Categories=Utility;Application;
#EOF
#
#    # Make it executable
#    chmod +x "$desktop_file_path"
#
#    echo "Desktop shortcut created at: $desktop_file_path"
#}

launch_in_terminal() {
    CMD="cd '$DIR' && source venv/bin/activate && python3.11 main.py; exec bash"

    declare -A terminals=(
        [gnome-terminal]="-- bash -c \"$CMD\""
        [konsole]="--noclose -e bash -c \"$CMD\""
        [xfce4-terminal]="--command=\"bash -c '$CMD'\""
        [tilix]="-e bash -c \"$CMD\""
        [kitty]="bash -c \"$CMD\""
        [alacritty]="-e bash -c \"$CMD\""
        [wezterm]="start -- bash -c \"$CMD\""
        [lxterminal]="-e bash -c \"$CMD\""
        [terminator]="-x bash -c \"$CMD\""
        [mate-terminal]="-- bash -c \"$CMD\""
        [urxvt]="-e bash -c \"$CMD\""
        [st]="-e bash -c \"$CMD\""
        [xterm]="-hold -e bash -c \"$CMD\""
        [x-terminal-emulator]="-e bash -c \"$CMD\""
    )

    for term in "${!terminals[@]}"; do
        if command -v "$term" &> /dev/null; then
            eval "$term ${terminals[$term]}" &
            return
        fi
    done

    echo "No supported terminal emulator found. Running in current shell."
    cd "$DIR"
    source venv/bin/activate
    python3.11 main.py
}

launch_in_terminal
